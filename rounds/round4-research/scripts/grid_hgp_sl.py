"""
Grid search: HYDROGEL_SOFT_LIMIT  (values 50 -> 200, step 25)

For each value this script:
  1. Creates a temp algo file with the patched constant.
  2. Runs the full 3-day R3 backtester (10k ticks/day, HGP+VFE PnL).
  3. Runs worst-case MC scenarios at 1000 ticks (platform-realistic):
       - hgp_extreme_down: anchor shifts to 9850 (sustained bear)
       - hgp_no_reversion: HGP becomes a random walk (no mean-rev)
     Reports p5 (5th percentile), median and mean from N_SIMS runs.

Output is a summary table so you can pick the best sl.

Usage:
    python scripts/grid_hgp_sl.py
    python scripts/grid_hgp_sl.py --sims 100     # more precision on MC
    python scripts/grid_hgp_sl.py --values 100 125 150 175  # custom range
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np

# ------------------------------------------------------------------
# Paths
# ------------------------------------------------------------------
ROOT    = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
ALGO    = ROOT / "v10_eval.py"

sys.path.insert(0, str(ROOT))
from montecarlo import (
    STRESS_SCENARIOS,
    MonteCarloResult,
    ProductModel,
    extract_stats,
    load_all_historical,
    load_trader,
    run_montecarlo,
)

# ------------------------------------------------------------------
# Config
# ------------------------------------------------------------------
DEFAULT_VALUES = [50, 75, 100, 125, 150, 175, 200]
N_SIMS   = 15    # sims per scenario -- enough to see relative differences quickly
N_TICKS  = 1000  # platform-realistic

CRASH_SCENARIOS = [
    "hgp_extreme_down",   # anchor shifts to 9850, kappa weakened
    "hgp_no_reversion",   # HGP becomes random walk (worst structural case)
]

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def patch_and_write(sl_value: int) -> Path:
    """Return path to a temp file with HYDROGEL_SOFT_LIMIT patched."""
    src = ALGO.read_text(encoding="utf-8")
    new_src, n = re.subn(
        r"^(HYDROGEL_SOFT_LIMIT\s*=\s*)(\d+)",
        lambda m: m.group(1) + str(sl_value),
        src,
        flags=re.MULTILINE,
    )
    if n == 0:
        raise RuntimeError("HYDROGEL_SOFT_LIMIT not found in source")
    tmp = ROOT / f"_sl_tmp_{sl_value}.py"
    tmp.write_text(new_src, encoding="utf-8")
    return tmp


def run_backtest(algo_path: Path) -> dict[str, float]:
    """Run full 3-day backtester in parallel, return per-day and total PnL."""
    def _run_day(day: int) -> tuple[int, float]:
        cmd = [sys.executable, str(SCRIPTS / "run_r3_backtest.py"), str(algo_path), str(day)]
        res = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT))
        out = res.stdout + res.stderr
        m = re.search(r"Total profit:\s*([\-\d,]+(?:\.\d+)?)", out)
        return day, (float(m.group(1).replace(",", "")) if m else 0.0)

    results: dict[str, float] = {}
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(_run_day, d): d for d in (0, 1, 2)}
        for fut in as_completed(futures):
            day, pnl = fut.result()
            results[f"d{day}"] = pnl
    results["total"] = sum(results[f"d{d}"] for d in (0, 1, 2))
    return results


def build_r3_models() -> list:
    historical = load_all_historical(str(ROOT))
    models = []
    for sym, ptype, pos_lim in [
        ("HYDROGEL_PACK",       "fixed_value",  200),
        ("VELVETFRUIT_EXTRACT", "random_walk",  200),
    ]:
        if sym in historical and len(historical[sym]) > 100:
            stats = extract_stats(historical[sym], sym)
            m = ProductModel.from_stats(stats, product_type=ptype, position_limit=pos_lim)
            m.make_fill_prob = 0.015
            if ptype == "fixed_value":
                m.mu = 10000.0
                m.fair_value = float(np.mean(stats.mid_prices))
            if sym == "HYDROGEL_PACK":
                m.kappa = max(0.0005, min(m.kappa, 0.005))
                m.sigma  = max(1.5,   min(m.sigma, 5.0))
                m.spread_mean = max(12.0, m.spread_mean)
            elif sym == "VELVETFRUIT_EXTRACT":
                m.kappa = max(0.0001, min(m.kappa, 0.003))
                m.sigma = max(0.5,    min(m.sigma, 4.0))
                if m.drift <= 0:
                    m.drift = 0.0015
        else:
            m = (ProductModel.default_hydrogel_pack() if sym == "HYDROGEL_PACK"
                 else ProductModel.default_velvetfruit_extract())
        m.make_fill_prob = 0.015
        models.append(m)
    return models


def run_mc_scenarios(algo_path: Path, base_models: list, scenarios: list[str], seed: int, n_sims: int, workers: int = 4) -> dict[str, MonteCarloResult]:
    trader = load_trader(str(algo_path))
    results: dict[str, MonteCarloResult] = {}
    for sc_name in scenarios:
        scenario = STRESS_SCENARIOS.get(sc_name)
        if scenario is None:
            print(f"  WARNING: scenario {sc_name!r} not found, skipping")
            continue
        r = run_montecarlo(
            trader_class=trader,
            models=base_models,
            n_sims=n_sims,
            n_ticks=N_TICKS,
            base_seed=seed,
            scenario=scenario,
            progress=False,
            workers=workers,
            trader_path=str(algo_path),
        )
        results[sc_name] = r
    return results


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sims",          type=int, default=N_SIMS, help="MC sims per scenario")
    parser.add_argument("--values",        type=int, nargs="+", default=DEFAULT_VALUES)
    parser.add_argument("--backtest-only", action="store_true", help="Skip MC, run backtest only (fast)")
    parser.add_argument("--workers",       type=int, default=4, help="MC parallel workers (default 4)")
    args = parser.parse_args()

    n_sims = args.sims
    sl_values: list[int] = sorted(args.values)
    backtest_only: bool = args.backtest_only

    print(f"\n{'='*70}")
    print(f"HYDROGEL_SOFT_LIMIT grid search  |  {n_sims} MC sims x {len(CRASH_SCENARIOS)} crash scenarios")
    print(f"SL values to test: {sl_values}")
    print(f"{'='*70}\n")

    # Build base product models once (only needed if running MC)
    base_models = []
    if not backtest_only:
        print("Calibrating product models from historical data...")
        base_models = build_r3_models()
    print()

    # --- Collect results ---
    bt_results:  dict[int, dict] = {}
    mc_results:  dict[int, dict] = {}
    tmp_files:   list[Path]      = []

    for sl in sl_values:
        print(f"-- SL={sl} ------------------------------------------")

        tmp = patch_and_write(sl)
        tmp_files.append(tmp)

        # 1. Backtester
        print(f"  Running 3-day backtester...", end="", flush=True)
        bt = run_backtest(tmp)
        bt_results[sl] = bt
        print(f"  d0={bt['d0']:+.0f}  d1={bt['d1']:+.0f}  d2={bt['d2']:+.0f}  total={bt['total']:+.0f}")

        # 2. MC crash scenarios
        if not backtest_only:
            print(f"  Running {n_sims} MC sims x {len(CRASH_SCENARIOS)} crash scenarios...", end="", flush=True)
            mc = run_mc_scenarios(tmp, base_models, CRASH_SCENARIOS, seed=42 + sl, n_sims=n_sims, workers=args.workers)
            mc_results[sl] = mc
            for sc_name, r in mc.items():
                print(f"\n    {sc_name:<22}  p5={r.pnl_p5:+8.0f}  median={r.pnl_median:+8.0f}  mean={r.pnl_mean:+8.0f}")

    # --- Cleanup temp files ---
    for f in tmp_files:
        try:
            f.unlink()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Summary table
    # ------------------------------------------------------------------
    COL = 10
    print(f"\n{'='*70}")
    print("SUMMARY TABLE")
    print(f"{'='*70}")

    # Backtester totals
    print("\n>> BACKTEST TOTAL PnL (10k ticks/day x 3 days):")
    header = f"  {'SL':>4} | {'Day 0':>{COL}} {'Day 1':>{COL}} {'Day 2':>{COL}} {'TOTAL':>{COL}}"
    print(header)
    print("  " + "-" * (len(header) - 2))
    for sl in sl_values:
        b = bt_results[sl]
        marker = " <-- current" if sl == 150 else ""
        print(f"  {sl:>4} | {b['d0']:>{COL}.0f} {b['d1']:>{COL}.0f} {b['d2']:>{COL}.0f} {b['total']:>{COL}.0f}{marker}")

    # MC crash p5 (most important: VaR / tail protection)
    if not backtest_only and mc_results:
        print(f"\n>> MC CRASH SCENARIO p5 (5th-percentile PnL | {n_sims} sims, {N_TICKS} ticks):")
        for sc_name in CRASH_SCENARIOS:
            print(f"\n  Scenario: {sc_name}")
            print(f"  {'SL':>4} | {'p5':>10} {'median':>10} {'mean':>10}")
            print("  " + "-" * 42)
            for sl in sl_values:
                r = mc_results[sl].get(sc_name)
                if r is None:
                    continue
                marker = " <-- current" if sl == 150 else ""
                print(f"  {sl:>4} | {r.pnl_p5:>10.0f} {r.pnl_median:>10.0f} {r.pnl_mean:>10.0f}{marker}")

    # Risk-adjusted score: backtest_total + 2x worst_p5 across crash scenarios
    if not backtest_only and mc_results:
        print(f"\n>> RISK-ADJUSTED SCORE = backtest_total + 2 * (worst p5 across crash scenarios):")
        print(f"  [higher is better; p5 dominates when it is very negative]")
        print(f"  {'SL':>4} | {'BT total':>10} {'worst p5':>10} {'score':>10}")
        print("  " + "-" * 42)
        best_score, best_sl = -1e18, None
        for sl in sl_values:
            bt_total = bt_results[sl]["total"]
            worst_p5 = min(
                mc_results[sl][sc].pnl_p5
                for sc in CRASH_SCENARIOS
                if sc in mc_results[sl]
            )
            score = bt_total + 2.0 * worst_p5
            if score > best_score:
                best_score, best_sl = score, sl
            marker = " <-- BEST" if sl == best_sl else (" <-- current" if sl == 150 else "")
            print(f"  {sl:>4} | {bt_total:>10.0f} {worst_p5:>10.0f} {score:>10.0f}{marker}")

        print(f"\n{'='*70}")
        print(f"RECOMMENDATION: HYDROGEL_SOFT_LIMIT = {best_sl}  (score={best_score:.0f})")
        print(f"{'='*70}\n")


if __name__ == "__main__":
    main()
