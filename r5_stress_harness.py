"""
R5 Stress Test Harness
=======================
Runs `submission.py` through the five Step-4 stress scenarios and prints a
results table. Asserts zero position-limit breaches across every scenario.

Usage:
  python r5_stress_harness.py                      # full run (default sims/ticks)
  python r5_stress_harness.py --sims 20 --ticks 1000   # quick run
  python r5_stress_harness.py --workers 8

Required scenarios (per Step 4 / task spec):
  regime_shift, no_insider, crowded_trade, limit_stress, correlation_break
Plus baseline as a control.
"""

from __future__ import annotations

import argparse
import sys
import time
from typing import List, Tuple

import montecarlo as mc

REQUIRED_SCENARIOS: List[str] = [
    "baseline",
    "regime_shift",
    "no_insider",
    "crowded_trade",
    "limit_stress",
    "correlation_break",
]


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--trader", type=str, default="submission.py")
    p.add_argument("--sims", type=int, default=30)
    p.add_argument("--ticks", type=int, default=1000)
    p.add_argument("--workers", type=int, default=1)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--mode", type=str, default="parametric",
                   choices=["parametric", "bootstrap"])
    args = p.parse_args()

    workspace = __file__.rsplit("\\", 1)[0] if "\\" in __file__ else __file__.rsplit("/", 1)[0]
    trader_path = args.trader if "/" in args.trader or "\\" in args.trader else f"{workspace}/{args.trader}"

    sys.stderr.write(f"Loading trader from {trader_path}...\n")
    TraderClass = mc.load_trader(trader_path)

    sys.stderr.write("Loading R5 historical data...\n")
    historical = mc.load_r5_historical(workspace)
    if not historical:
        sys.stderr.write("ERROR: no R5 data\n"); return 2
    sys.stderr.write(f"  {len(historical)} products loaded\n")
    models = mc.build_r5_models(historical)
    bootstrap_gen = mc.BootstrapGenerator(historical, block_size=50, noise_scale=0.5)

    rows: List[Tuple[str, mc.MonteCarloResult, float]] = []
    t_total = time.time()
    for scen_name in REQUIRED_SCENARIOS:
        scen = mc.STRESS_SCENARIOS[scen_name]
        sys.stderr.write(f"\n[scenario] {scen_name}\n")
        t0 = time.time()
        result = mc.run_montecarlo(
            TraderClass, models, n_sims=args.sims, n_ticks=args.ticks,
            base_seed=args.seed, scenario=scen, bootstrap_gen=bootstrap_gen,
            mode=args.mode, progress=True, workers=args.workers,
            trader_path=trader_path, enable_noise_traders=True,
            informed_flow_default=True,
        )
        dt = time.time() - t0
        rows.append((scen_name, result, dt))

    # ------ summary table -------------------------------------------------
    print("\n" + "=" * 110)
    print("  R5 STRESS-SCENARIO RESULTS — {} sims × {} ticks each, mode={}"
          .format(args.sims, args.ticks, args.mode))
    print("=" * 110)
    hdr = (f"  {'Scenario':<20} {'PnL Mean':>10} {'PnL Std':>10} {'P5 (VaR)':>10} "
           f"{'P95':>10} {'Sharpe':>8} {'Win%':>6} {'MaxDD':>8} "
           f"{'Breach':>8} {'vs Shadow':>10} {'Time(s)':>8}")
    print(hdr); print("  " + "-" * 106)
    breach_total = 0
    for name, r, dt in rows:
        breach_total += r.limit_breach_total
        spread = r.pnl_mean - r.shadow_pnl_mean
        print(f"  {name:<20} {r.pnl_mean:>10,.0f} {r.pnl_std:>10,.0f} "
              f"{r.pnl_p5:>10,.0f} {r.pnl_p95:>10,.0f} {r.sharpe_mean:>8.2f} "
              f"{r.win_rate:>5.0%} {r.max_drawdown_mean:>8,.0f} "
              f"{r.limit_breach_total:>8,d} {spread:>+10,.0f} {dt:>8.1f}")
    print("=" * 110)

    # ------ per-strategy attribution (baseline only) ----------------------
    base = next((r for n, r, _ in rows if n == "baseline"), None)
    if base is not None and base.results:
        print("\n  Per-strategy mean PnL (baseline scenario):")
        agg = {}
        for r in base.results:
            for k, v in r.pnl_by_strategy.items():
                agg.setdefault(k, []).append(v)
        for k in sorted(agg.keys()):
            vals = agg[k]
            mean = sum(vals) / len(vals)
            std = (sum((v - mean) ** 2 for v in vals) / len(vals)) ** 0.5
            print(f"    {k:>10}: mean={mean:>10,.0f}  std={std:>9,.0f}")

    print(f"\n  Total elapsed: {time.time() - t_total:.1f}s")
    print(f"  TOTAL POSITION-LIMIT BREACHES: {breach_total}  "
          f"{'(FAIL — DEBUG REQUIRED)' if breach_total > 0 else '(PASS)'}")

    if breach_total > 0:
        # Detail per-scenario per-sim breach count for debugging
        print("\n  Breach detail:")
        for name, r, _ in rows:
            if r.limit_breach_total > 0:
                per_sim = [s.limit_breach_count for s in r.results]
                print(f"    {name}: total={r.limit_breach_total}, "
                      f"per-sim min={min(per_sim)} max={max(per_sim)} "
                      f"mean={sum(per_sim)/len(per_sim):.1f}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
