"""
R3 Monte Carlo Stress Test — Compare submission vs v10
=======================================================
Runs both algos against all stress scenarios at platform-realistic
tick count (1000 ticks) and reports a side-by-side comparison.

Usage:
    python scripts/run_r3_mc_stress.py [--sims N] [--ticks T]
"""
import sys
import os

# Ensure workspace root is on sys.path so montecarlo.py and datamodel.py resolve
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import numpy as np

# Import montecarlo infrastructure
from montecarlo import (
    run_montecarlo, print_report, STRESS_SCENARIOS,
    load_trader, load_all_historical, extract_stats,
    ProductModel, MonteCarloResult,
)

# ──────────────────────────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────────────────────────
N_SIMS   = 50           # 50 sims per scenario/algo combo (fast enough for comparison)
N_TICKS  = 1000         # platform-realistic session length
SEED     = 42

# Scenarios to run (full battery)
SCENARIOS_TO_RUN = [
    "baseline",
    "platform_like",
    "hgp_crash_down",       # THE disaster scenario
    "hgp_crash_up",
    "hgp_extreme_down",     # extreme: anchor shifts to 9850
    "hgp_no_reversion",     # HGP random walks (no mean-reversion)
    "vfe_no_drift",         # VFE earns nothing from drift
    "vfe_fast_drift",       # VFE drifts 2.7x faster
    "high_vol",
    "wide_spread",
    "thin_liquidity",
    "spread_shock",
    "full_stress",          # kitchen sink
]

# Only simulate the two main PnL products — options contribute <5% of total PnL
# per full backtester run and are slow to simulate (BS math × 10 strikes)
SIMULATE_OPTIONS = False  # set True to include VEV vouchers (much slower)

SUBMISSION_PATH = os.path.join(ROOT, "submission_eval.py")
V10_PATH        = os.path.join(ROOT, "v10_eval.py")

# ──────────────────────────────────────────────────────────────────
# Load product models (auto-calibrate from historical R3 data)
# ──────────────────────────────────────────────────────────────────

def build_r3_models(workspace: str) -> list:
    historical = load_all_historical(workspace)

    models = []
    _R3_DELTA1 = [
        ("HYDROGEL_PACK",       "fixed_value", 200, 0.015),
        ("VELVETFRUIT_EXTRACT", "random_walk", 200, 0.018),
    ]
    _R3_VOUCHERS = [
        ("VEV_4000", 300, 0.015), ("VEV_4500", 300, 0.015),
        ("VEV_5000", 300, 0.015), ("VEV_5100", 300, 0.015),
        ("VEV_5200", 300, 0.015), ("VEV_5300", 300, 0.015),
        ("VEV_5400", 300, 0.015), ("VEV_5500", 300, 0.015),
        ("VEV_6000", 300, 0.010), ("VEV_6500", 300, 0.010),
    ]

    for sym, ptype, pos_lim, fill_prob in _R3_DELTA1:
        if sym in historical and len(historical[sym]) > 100:
            stats = extract_stats(historical[sym], sym)
            m = ProductModel.from_stats(stats, product_type=ptype, position_limit=pos_lim)
            m.make_fill_prob = fill_prob
            # Force correct anchor for HGP
            if ptype == "fixed_value":
                m.mu = 10000.0
                m.fair_value = float(np.mean(stats.mid_prices))
            # Fix kappa: auto-calibrated kappa is often too large or zero
            # Use EDA-calibrated values as sanity bounds
            if sym == "HYDROGEL_PACK":
                m.kappa = max(0.0005, min(m.kappa, 0.005))
                m.sigma  = max(1.5,   min(m.sigma, 5.0))
                m.spread_mean = max(12.0, m.spread_mean)   # at least 12-tick spread
            elif sym == "VELVETFRUIT_EXTRACT":
                m.kappa  = max(0.0001, min(m.kappa, 0.003))
                m.sigma  = max(0.5,    min(m.sigma, 4.0))
                # Ensure drift is positive (VFE drifts up historically)
                if m.drift <= 0:
                    m.drift = 0.0015
            sys.stderr.write(
                f"  {sym}: calibrated  sigma={m.sigma:.3f}  kappa={m.kappa:.4f}"
                f"  drift={m.drift:.5f}  spread={m.spread_mean:.1f}\n"
            )
        else:
            if sym == "HYDROGEL_PACK":
                m = ProductModel.default_hydrogel_pack()
            else:
                m = ProductModel.default_velvetfruit_extract()
            sys.stderr.write(f"  {sym}: using default model\n")
        models.append(m)

    if SIMULATE_OPTIONS:
        _VOUCHER_DEFAULTS = {
            "VEV_4000": 1250.0, "VEV_4500": 750.0, "VEV_5000": 255.0,
            "VEV_5100": 167.0,  "VEV_5200": 96.0,  "VEV_5300": 47.0,
            "VEV_5400": 16.0,   "VEV_5500": 7.0,   "VEV_6000": 0.5,
            "VEV_6500": 0.5,
        }
        for sym, pos_lim, fill_prob in _R3_VOUCHERS:
            if sym in historical and len(historical[sym]) > 100:
                stats = extract_stats(historical[sym], sym)
                m = ProductModel.from_stats(stats, product_type="fixed_value", position_limit=pos_lim)
                m.make_fill_prob = fill_prob
                m.price_floor = 0.0
                fv = float(np.mean(stats.mid_prices))
                m.mu = fv
                m.fair_value = fv
                if fv < 5.0:
                    m.sigma = min(m.sigma, max(0.1, fv * 0.20))
                    m.spread_mean = min(m.spread_mean, max(1.0, fv * 0.30))
                    m.spread_std = min(m.spread_std, 0.5)
            else:
                fv = _VOUCHER_DEFAULTS.get(sym, 10.0)
                m = ProductModel(
                    symbol=sym, product_type="fixed_value", fair_value=fv,
                    position_limit=pos_lim, kappa=0.08, mu=fv,
                    sigma=max(0.5, fv * 0.04),
                    spread_mean=max(1.0, fv * 0.015),
                    spread_std=0.5,
                    vol_mean=12.0, vol_std=4.0,
                    make_fill_prob=fill_prob, price_floor=0.0,
                )
            models.append(m)

    return models


# ──────────────────────────────────────────────────────────────────
# Comparison table printer
# ──────────────────────────────────────────────────────────────────

def print_comparison_table(results: dict):
    """Print side-by-side SUB vs V10 for all scenarios."""
    algos = ["submission", "v10"]
    hdr = f"\n{'='*92}\n  R3 MONTE CARLO STRESS TEST — {N_SIMS} sims × {N_TICKS} ticks (platform-scale)\n{'='*92}"
    print(hdr)

    fmt_h = f"  {'Scenario':<22}  {'SUB mean':>10}  {'SUB p5':>9}  {'SUB wr':>7}  "
    fmt_h += f"{'V10 mean':>10}  {'V10 p5':>9}  {'V10 wr':>7}  {'Winner':>8}"
    print(fmt_h)
    print("  " + "-"*88)

    for sc in SCENARIOS_TO_RUN:
        sub = results.get(("submission", sc))
        v10 = results.get(("v10", sc))
        if sub is None or v10 is None:
            continue

        winner = "V10 >>" if v10.pnl_mean > sub.pnl_mean else ("SUB >>" if sub.pnl_mean > v10.pnl_mean else "  TIE ")
        # Highlight disaster scenario
        flag = " (**)" if "crash" in sc or "extreme" in sc or "no_reversion" in sc or "full_stress" in sc else ""

        print(
            f"  {sc:<22}  "
            f"{sub.pnl_mean:>10,.0f}  {sub.pnl_p5:>9,.0f}  {sub.win_rate:>6.0%}  "
            f"{v10.pnl_mean:>10,.0f}  {v10.pnl_p5:>9,.0f}  {v10.win_rate:>6.0%}  "
            f"{winner}{flag}"
        )
    print("  " + "-"*88)
    print(f"\n  (**) = high-severity scenario\n")

    # Summary: count wins per algo
    sub_wins = sum(1 for sc in SCENARIOS_TO_RUN
                   if results.get(("submission", sc)) and results.get(("v10", sc))
                   and results[("submission", sc)].pnl_mean > results[("v10", sc)].pnl_mean)
    v10_wins = sum(1 for sc in SCENARIOS_TO_RUN
                   if results.get(("submission", sc)) and results.get(("v10", sc))
                   and results[("v10", sc)].pnl_mean > results[("submission", sc)].pnl_mean)
    print(f"  Scenario wins:  SUB={sub_wins}  V10={v10_wins}\n")
    print("=" * 92)


# ──────────────────────────────────────────────────────────────────
# Detailed per-scenario report for worst-case scenarios
# ──────────────────────────────────────────────────────────────────

def print_disaster_detail(results: dict):
    """Detailed breakdown of the critical/disaster scenarios."""
    critical = ["hgp_crash_down", "hgp_extreme_down", "hgp_no_reversion", "full_stress"]
    print(f"\n{'='*72}")
    print(f"  CRITICAL SCENARIO DETAIL (disaster/extreme cases)")
    print(f"{'='*72}")
    for sc in critical:
        for algo_key, label in [("submission", "SUBMISSION"), ("v10", "V10")]:
            mc = results.get((algo_key, sc))
            if mc is None:
                continue
            print(f"\n  [{label}] Scenario: {sc}")
            print(f"    Mean PnL : {mc.pnl_mean:>10,.0f}   Std: {mc.pnl_std:>8,.0f}")
            print(f"    P5  PnL  : {mc.pnl_p5:>10,.0f}   P95: {mc.pnl_p95:>8,.0f}")
            print(f"    Win Rate : {mc.win_rate:.1%}   MaxDD p95: {mc.max_drawdown_p95:>8,.0f}")
            print(f"    Sharpe   : {mc.sharpe_mean:.3f}")
            # Per-product breakdown
            if mc.results:
                prods = ["HYDROGEL_PACK", "VELVETFRUIT_EXTRACT"]
                for prod in prods:
                    pnls = [r.pnl_by_product.get(prod, 0) for r in mc.results]
                    max_pos = [r.max_position.get(prod, 0) for r in mc.results]
                    print(f"    {prod:<28}: mean={np.mean(pnls):>8,.0f}  p5={np.percentile(pnls,5):>8,.0f}"
                          f"  maxPos_avg={np.mean(max_pos):.0f}")
    print(f"{'='*72}")


# ──────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────

def main():
    sys.stderr.write("=" * 60 + "\n")
    sys.stderr.write("  Building R3 product models...\n")
    sys.stderr.write("=" * 60 + "\n")

    models = build_r3_models(ROOT)

    algo_specs = [
        ("submission", SUBMISSION_PATH),
        ("v10", V10_PATH),
    ]

    # Verify both files exist
    for label, path in algo_specs:
        if not os.path.exists(path):
            sys.exit(f"ERROR: {path} not found. Run the backtest setup first.")

    results = {}

    for algo_label, algo_path in algo_specs:
        sys.stderr.write(f"\n{'='*60}\n  Loading algo: {algo_label} ({os.path.basename(algo_path)})\n{'='*60}\n")
        try:
            TraderClass = load_trader(algo_path)
        except Exception as e:
            sys.stderr.write(f"  ERROR loading {algo_path}: {e}\n")
            continue

        for sc_name in SCENARIOS_TO_RUN:
            scenario = STRESS_SCENARIOS[sc_name]
            sys.stderr.write(f"  Running [{algo_label}] x [{sc_name}] ...\n")
            sys.stderr.flush()
            try:
                mc = run_montecarlo(
                    trader_class=TraderClass,
                    models=models,
                    n_sims=N_SIMS,
                    n_ticks=N_TICKS,
                    base_seed=SEED,
                    scenario=scenario,
                    progress=False,
                )
                results[(algo_label, sc_name)] = mc
                sys.stderr.write(
                    f"    done: mean={mc.pnl_mean:,.0f}  p5={mc.pnl_p5:,.0f}"
                    f"  wr={mc.win_rate:.0%}\n"
                )
            except Exception as e:
                sys.stderr.write(f"    ERROR: {e}\n")

    print_comparison_table(results)
    print_disaster_detail(results)


if __name__ == "__main__":
    main()
