"""
Variant validation: run each contingency variant through the relevant
Step-4 stress scenario and collect (mean PnL, breach count) for the
expected-performance section of the playbook.

Usage:
    python variants/validate_variants.py            # quick (5 sims, 500 ticks)
    python variants/validate_variants.py --sims 10 --ticks 1000
"""

from __future__ import annotations

import argparse
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import montecarlo as mc  # noqa: E402

# Variant -> primary scenario(s) it is designed for
PAIRS = [
    ("CONTINGENCY_BASE",            "baseline"),
    ("CONTINGENCY_P2_OFF",          "baseline"),
    ("CONTINGENCY_PAIR_OFF",        "baseline"),
    ("CONTINGENCY_R2_OFF",          "baseline"),
    ("CONTINGENCY_NO_INSIDER",      "no_insider"),
    ("CONTINGENCY_REGIME_SHIFT",    "regime_shift"),
    ("CONTINGENCY_CROWDED_TRADE",   "crowded_trade"),
    ("CONTINGENCY_DEFENSIVE",       "regime_shift"),
    ("CONTINGENCY_LIQUIDATE",       "limit_stress"),
    # V-series (Step-6 corrected) — mandated names, mapped to MC scenarios
    ("trader_V1_no_insider",        "no_insider"),
    ("trader_V2_high_vol",          "regime_shift"),
    ("trader_V3_adversarial",       "regime_shift"),     # closest analogue
    ("trader_V4_inventory_trap",    "limit_stress"),
    ("trader_V5_signal_loss",       "no_insider"),
    ("trader_V6_emergency_brake",   "limit_stress"),
]


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--sims", type=int, default=5)
    p.add_argument("--ticks", type=int, default=500)
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()

    historical = mc.load_r5_historical(ROOT)
    if not historical:
        sys.stderr.write("ERROR: no R5 historical data\n")
        return 2
    models = mc.build_r5_models(historical)
    bootstrap_gen = mc.BootstrapGenerator(historical, block_size=50, noise_scale=0.5)

    print(f"\n  Variant validation — {args.sims} sims × {args.ticks} ticks each")
    print(f"  {'Variant':28} {'Scenario':18} {'Mean PnL':>10} {'Std':>10} "
          f"{'Sharpe':>7} {'MaxDD':>8} {'Breach':>6} {'t(s)':>6}")
    print("  " + "-" * 100)
    total_breach = 0
    for vname, scen_name in PAIRS:
        path = os.path.join(ROOT, "variants", "built", vname + ".py")
        TraderClass = mc.load_trader(path)
        scen = mc.STRESS_SCENARIOS[scen_name]
        t0 = time.time()
        result = mc.run_montecarlo(
            TraderClass, models, n_sims=args.sims, n_ticks=args.ticks,
            base_seed=args.seed, scenario=scen, bootstrap_gen=bootstrap_gen,
            mode="parametric", progress=False, workers=1,
            trader_path=path, enable_noise_traders=True,
            informed_flow_default=True,
        )
        dt = time.time() - t0
        breach = getattr(result, "total_breaches", 0)
        total_breach += breach
        sharpe = getattr(result, "sharpe", 0.0) or 0.0
        max_dd = getattr(result, "max_drawdown_mean", 0.0) or 0.0
        print(f"  {vname:28} {scen_name:18} {result.pnl_mean:>10,.0f} "
              f"{result.pnl_std:>10,.0f} {sharpe:>7.2f} "
              f"{max_dd:>8,.0f} {breach:>6d} {dt:>6.1f}")

    print("  " + "-" * 100)
    print(f"  TOTAL BREACHES: {total_breach}  ({'PASS' if total_breach == 0 else 'FAIL'})")
    return 0 if total_breach == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
