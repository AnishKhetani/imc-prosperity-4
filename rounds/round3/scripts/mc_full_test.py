"""
Full Monte Carlo stress test: 1000 sims x 10 scenarios for v10_eval.py.
Run from workspace root:  python scripts/mc_full_test.py
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from montecarlo import (
    STRESS_SCENARIOS, ProductModel,
    extract_stats, load_all_historical, load_trader, run_montecarlo,
)

ALGO     = str(ROOT / "v10_eval.py")
N_SIMS   = 100
N_TICKS  = 10000  # final competition length (1000 = test/debug only)
WORKERS  = 1   # sequential — avoids Windows multiprocessing spawn overhead

SCENARIOS = [
    "baseline",
    "platform_like",
    "hgp_crash_down",
    "hgp_extreme_down",
    "hgp_no_reversion",
    "high_vol",
    "crash",
    "no_drift",
    "negative_drift",
    "vfe_no_drift",
]

def build_models():
    historical = load_all_historical(str(ROOT))
    models = []
    for sym, ptype, pos_lim in [
        ("HYDROGEL_PACK",       "fixed_value",  200),
        ("VELVETFRUIT_EXTRACT", "random_walk",  200),
    ]:
        if sym in historical and len(historical[sym]) > 100:
            stats = extract_stats(historical[sym], sym)
            m = ProductModel.from_stats(stats, product_type=ptype, position_limit=pos_lim)
            if ptype == "fixed_value":
                m.mu = 10000.0
            if sym == "HYDROGEL_PACK":
                m.kappa = max(0.0005, min(m.kappa, 0.005))
                m.sigma  = max(1.5,   min(m.sigma, 5.0))
                m.spread_mean = max(12.0, m.spread_mean)
            elif sym == "VELVETFRUIT_EXTRACT":
                m.kappa = max(0.0001, min(m.kappa, 0.003))
                m.sigma  = max(0.5,   min(m.sigma, 4.0))
                if m.drift <= 0:
                    m.drift = 0.0015
        else:
            m = (ProductModel.default_hydrogel_pack() if sym == "HYDROGEL_PACK"
                 else ProductModel.default_velvetfruit_extract())
        m.make_fill_prob = 0.015
        models.append(m)
    return models


def main():
    print(f"\n{'='*80}")
    print(f"Monte Carlo stress test  |  {N_SIMS} sims x {len(SCENARIOS)} scenarios  |  {N_TICKS} ticks each")
    print(f"Algorithm: v10_eval.py  (HYDROGEL_SOFT_LIMIT=180, competition-length: {N_TICKS} ticks)")
    print(f"{'='*80}\n")

    print("Loading trader and calibrating models...")
    trader = load_trader(ALGO)
    models = build_models()
    print(f"Running {N_SIMS * len(SCENARIOS):,} total simulations with {WORKERS} workers...\n")

    W = 22
    print(f"  {'Scenario':<{W}} {'mean':>8} {'p5':>8} {'p25':>8} {'median':>8} {'p75':>8} {'p95':>8} {'win%':>6} {'maxDD':>8}")
    print("  " + "-" * 82)

    for sc_name in SCENARIOS:
        scenario = STRESS_SCENARIOS[sc_name]
        r = run_montecarlo(
            trader_class=trader,
            models=models,
            n_sims=N_SIMS,
            n_ticks=N_TICKS,
            base_seed=42,
            scenario=scenario,
            progress=False,
            workers=WORKERS,
            trader_path=ALGO,
        )
        tag = " <-- LIVE" if sc_name == "platform_like" else ""
        print(
            f"  {sc_name:<{W}} "
            f"{r.pnl_mean:>8.0f} "
            f"{r.pnl_p5:>8.0f} "
            f"{r.pnl_p25:>8.0f} "
            f"{r.pnl_median:>8.0f} "
            f"{r.pnl_p75:>8.0f} "
            f"{r.pnl_p95:>8.0f} "
            f"{r.win_rate*100:>5.1f}% "
            f"{r.max_drawdown_mean:>8.0f}"
            f"{tag}"
        )

    print(f"\n{'='*80}\n")


if __name__ == "__main__":
    main()
