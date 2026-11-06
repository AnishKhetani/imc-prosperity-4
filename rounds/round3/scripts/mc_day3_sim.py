"""
scripts/mc_day3_sim.py
=======================
Monte Carlo simulation of the LIVE DAY 3 session for IMC Prosperity 4 Round 3.

Configuration:
  • Algorithm  : submission_r3_v11.py
  • TTE        : 5 days at timestamp=0 (live round wiki schedule)
  • Ticks      : 10,000 per sim (full session: ts 0→999,900, TTE 5→0.25d)
  • Simulations: 700 per scenario
  • Scenarios  : all from montecarlo.STRESS_SCENARIOS
  • Options    : VEV order books are Black-Scholes coupled to VFE_mid at each
                 tick with IV=0.23 (flat smile, calibrated from R3 EDA).
                 VEV fair values pre-computed with vectorized numpy BS.
  • Workers    : multiprocessing.cpu_count() — one shared pool for all
                 scenarios (eliminates per-scenario spawn overhead)

Output:
  mc_live_sim.png   — 4-panel figure saved to workspace root
  mc_live_sim.json  — raw scenario results (mean, std, percentiles, etc.)

Runtime target: ~40 min on 12 CPUs
"""

from __future__ import annotations

# ── CRITICAL: Set IMC_TTE_DAYS BEFORE any import of submission / montecarlo ──
import os
os.environ["IMC_TTE_DAYS"] = "5"

import copy
import json
import math
import multiprocessing as mp
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from montecarlo import (
    STRESS_SCENARIOS, StressScenario, ProductModel, apply_stress,
    FillEngine, load_trader,
    SimResult, MonteCarloResult,
    OrderDepth, Trade, TradingState, Observation, Listing,
    load_all_historical, extract_stats,
)


# ===========================================================================
# CONSTANTS
# ===========================================================================

N_SIMS         = 15
N_TICKS        = 10_000  # full session: ts 0 → 999,900 (live fidelity)
N_WORKERS      = 2        # low worker count avoids paging-file exhaustion
SEED           = 42
IV_FLAT        = 0.23        # flat-smile IV calibrated from R3 EDA
TTE_DAYS_T0    = 5.0         # live day 3 starting TTE
TS_PER_DAY     = 1_000_000.0
TTE_FLOOR_DAYS = 0.25

ALGO_PATH = str(ROOT / "submission_r3_v11.py")
OUT_PNG   = str(ROOT / "mc_live_sim.png")
OUT_JSON  = str(ROOT / "mc_live_sim.json")

# 11 highest-signal scenarios — chosen so 11×1000 sims/12 workers ≈ 40 min.
# Dropped: wide_spread, narrow_spread, no_drift, negative_drift, spread_shock,
#           low_fill, hgp_crash_up, vfe_no_drift, vfe_fast_drift
SCENARIOS = [
    "baseline",
    "high_vol",
    "low_vol",
    "crash",
    "full_stress",
    "platform_like",
    "hgp_crash_down",
    "hgp_extreme_down",
    "hgp_no_reversion",
    "double_drift",
    "thin_liquidity",
]

# VEV strikes and their historical bid-ask spreads (from EDA)
VEV_STRIKES = [4000, 4500, 5000, 5100, 5200, 5300, 5400, 5500, 6000, 6500]
VEV_LIMIT   = 300
VEV_SPREADS: Dict[int, float] = {
    4000: 21.0, 4500: 16.0, 5000: 6.0, 5100: 4.5, 5200: 3.0,
    5300: 2.2,  5400: 1.4,  5500: 1.2, 6000: 1.5, 6500: 2.0,
}
VEV_L1_VOL = 12   # typical L1 volume from EDA
VEV_FILL_PROB = 0.015  # platform-calibrated fill rate for passive VEV quotes

# HGP position limit (patch into ProductModel)
HGP_LIMIT = 200
VFE_LIMIT = 200


# ===========================================================================
# BLACK-SCHOLES (standalone, no import from submission needed here)
# ===========================================================================

_SQRT2    = math.sqrt(2.0)
_SQRT2PI  = math.sqrt(2.0 * math.pi)


def _ndcdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / _SQRT2))


def bs_call(S: float, K: float, T: float, sigma: float) -> float:
    """European call, no dividends, r=0."""
    if T <= 0.0 or sigma <= 0.0 or S <= 0.0:
        return max(S - K, 0.0)
    sst = sigma * math.sqrt(T)
    d1  = (math.log(S / K) + 0.5 * sigma * sigma * T) / sst
    return S * _ndcdf(d1) - K * _ndcdf(d1 - sst)


# Abramowitz & Stegun 26.2.17 coefficients — max error 7.5e-8, fully vectorised
_AS_P  = 0.2316419
_AS_A  = np.array([0.319381530, -0.356563782, 1.781477937, -1.821255978, 1.330274429])
_AS_C  = 1.0 / math.sqrt(2.0 * math.pi)

def _norm_cdf(x: np.ndarray) -> np.ndarray:
    """Standard normal CDF — pure numpy, no scipy."""
    t    = 1.0 / (1.0 + _AS_P * np.abs(x))
    poly = t * (_AS_A[0] + t * (_AS_A[1] + t * (_AS_A[2] + t * (_AS_A[3] + t * _AS_A[4]))))
    pdf  = _AS_C * np.exp(-0.5 * x * x)
    return np.where(x >= 0, 1.0 - pdf * poly, pdf * poly)


def _bs_call_vec(S_arr: np.ndarray, K: float, T_arr: np.ndarray, sigma: float = IV_FLAT) -> np.ndarray:
    """Vectorized BS call — pure numpy, no scipy dependency."""
    T_safe = np.maximum(T_arr, 1e-10)
    sst = sigma * np.sqrt(T_safe)
    d1  = (np.log(S_arr / K) + 0.5 * sigma * sigma * T_safe) / sst
    d2  = d1 - sst
    return np.maximum(S_arr * _norm_cdf(d1) - K * _norm_cdf(d2), 0.0)


# ===========================================================================
# VEV ORDER BOOK GENERATOR (Black-Scholes coupled to VFE mid)
# ===========================================================================

def vev_order_book(
    vfe_mid: float,
    strike: int,
    T_years: float,
    sigma: float = IV_FLAT,
    spread: float = 2.0,
    l1_vol: int = VEV_L1_VOL,
    rng: Optional[np.random.Generator] = None,
) -> OrderDepth:
    """Generate a VEV order book whose mid is BS(vfe_mid, K, T, sigma).

    This ensures option prices move correctly with the underlying: if VFE
    surges to 5400, VEV_5400 fair goes from ~16 → ~ATM, so our trader
    sees a realistic pricing environment.
    """
    fair = bs_call(vfe_mid, float(strike), T_years, sigma)
    fair = max(0.01, fair)  # floor at 1 cent to avoid zero-bid book

    # Add small noise to simulate book imprecision
    if rng is not None:
        noise = rng.normal(0.0, spread * 0.05)
        fair += noise

    half = spread / 2.0
    best_bid = max(0, int(math.floor(fair - half)))
    best_ask = int(math.ceil(fair + half))
    if best_ask <= best_bid:
        best_ask = best_bid + 1

    od = OrderDepth()
    bvol = int(max(1, l1_vol + (int(rng.integers(-4, 5)) if rng else 0)))
    avol = int(max(1, l1_vol + (int(rng.integers(-4, 5)) if rng else 0)))
    od.buy_orders[best_bid]  = bvol
    od.sell_orders[best_ask] = -avol

    # Second level
    if fair > 2.0:
        gap = max(1, int(spread))
        od.buy_orders[max(0, best_bid - gap)]  = bvol + 3
        od.sell_orders[best_ask + gap]          = -(avol + 3)

    return od


# ===========================================================================
# OPTIONS-AWARE SIMULATION ENGINE
# ===========================================================================

def _tte_years(tick_idx: int) -> float:
    ts = tick_idx * 100
    days = TTE_DAYS_T0 - ts / TS_PER_DAY
    return max(days, TTE_FLOOR_DAYS) / 365.0


class Day3SimEngine:
    """Simulation engine for Day 3 live session.

    Differences from montecarlo.SimulationEngine:
      - VEV order books are BS-coupled to VFE mid (not independent OU).
      - TTE decreases linearly from 5d at tick=0 to 0.25d at tick=9750.
      - HGP + VFE use standard OU / random-walk parametric models.
    """

    def __init__(
        self,
        trader_class,
        hgp_model: ProductModel,
        vfe_model: ProductModel,
        scenario: StressScenario,
        n_ticks: int = N_TICKS,
    ):
        self.trader_class = trader_class
        # Apply stress ONCE here, not on every run() call
        self.hgp      = apply_stress(copy.deepcopy(hgp_model), scenario)
        self.vfe      = apply_stress(copy.deepcopy(vfe_model), scenario)
        self.scenario = scenario
        self.n_ticks  = n_ticks

    def run(self, sim_seed: int) -> SimResult:
        rng         = np.random.default_rng(sim_seed)
        fill_engine = FillEngine(rng)
        n           = self.n_ticks

        # Use pre-stressed models stored on self (no deepcopy per sim)
        hgp = self.hgp
        vfe = self.vfe

        # ── Pre-generate all market data (vectorized, outside tick loop) ────────
        hgp_mids = _gen_ou_path(hgp, n, rng)
        vfe_mids = _gen_rw_path(vfe, n, rng)

        # TTE in years for every tick (numpy, no per-tick computation)
        T_arr = np.maximum(
            TTE_DAYS_T0 - np.arange(n) * 100.0 / TS_PER_DAY, TTE_FLOOR_DAYS
        ) / 365.0

        # VEV fair values: vectorized BS for each strike × all ticks
        # Replaces 100k Python bs_call() calls with 10 numpy operations
        vev_fair: Dict[int, np.ndarray] = {}
        for K in VEV_STRIKES:
            vev_fair[K] = np.maximum(_bs_call_vec(vfe_mids, float(K), T_arr), 0.01)

        # Pre-batch HGP / VFE order book parameters (removes per-tick rng.normal)
        hgp_sp   = np.maximum(2, rng.normal(hgp.spread_mean, max(0.01, hgp.spread_std), n).round()).astype(int)
        vfe_sp   = np.maximum(2, rng.normal(vfe.spread_mean, max(0.01, vfe.spread_std), n).round()).astype(int)
        hgp_bvol = np.maximum(1, rng.normal(hgp.vol_mean, max(0.01, hgp.vol_std), n).round()).astype(int)
        hgp_avol = np.maximum(1, rng.normal(hgp.vol_mean, max(0.01, hgp.vol_std), n).round()).astype(int)
        vfe_bvol = np.maximum(1, rng.normal(vfe.vol_mean, max(0.01, vfe.vol_std), n).round()).astype(int)
        vfe_avol = np.maximum(1, rng.normal(vfe.vol_mean, max(0.01, vfe.vol_std), n).round()).astype(int)
        # VEV L1 volumes (10 strikes × n ticks)
        vev_bvol = np.maximum(1, rng.integers(VEV_L1_VOL - 4, VEV_L1_VOL + 5, (n, len(VEV_STRIKES)))).astype(int)
        vev_avol = np.maximum(1, rng.integers(VEV_L1_VOL - 4, VEV_L1_VOL + 5, (n, len(VEV_STRIKES)))).astype(int)
        # ────────────────────────────────────────────────────────────────────────

        all_syms = ["HYDROGEL_PACK", "VELVETFRUIT_EXTRACT"] + [f"VEV_{k}" for k in VEV_STRIKES]
        pos_limits = {
            "HYDROGEL_PACK": HGP_LIMIT,
            "VELVETFRUIT_EXTRACT": VFE_LIMIT,
            **{f"VEV_{k}": VEV_LIMIT for k in VEV_STRIKES},
        }
        vev_fill_prob = VEV_FILL_PROB * self.scenario.fill_rate_multiplier

        result = SimResult()
        result.pnl_by_product   = {s: 0.0 for s in all_syms}
        result.fills_by_product = {s: 0   for s in all_syms}
        result.max_position     = {s: 0   for s in all_syms}
        result.avg_position     = {s: 0.0 for s in all_syms}

        positions: Dict[str, int]   = {s: 0 for s in all_syms}
        cash_pnl:  Dict[str, float] = {s: 0.0 for s in all_syms}
        pos_sums:  Dict[str, float] = {s: 0.0 for s in all_syms}
        last_mids: Dict[str, float] = {}
        trader_data = ""
        listings = {s: Listing(s, s, "XIRECS") for s in all_syms}

        cumulative_pnl = 0.0
        peak_pnl       = 0.0
        max_dd         = 0.0
        tick_pnls      = []

        try:
            trader = self.trader_class()

            for t_idx in range(n):
                ts      = t_idx * 100
                hgp_mid = float(hgp_mids[t_idx])
                vfe_mid = float(vfe_mids[t_idx])

                # ── Fast HGP order book (from pre-batched arrays) ──────────────
                hsp  = int(hgp_sp[t_idx])
                hbb  = int(hgp_mid) - hsp // 2
                hba  = hbb + hsp + (0 if hsp % 2 else 1)
                if hba <= hbb: hba = hbb + 1
                hgp_od = OrderDepth()
                hgp_od.buy_orders[hbb]  = int(hgp_bvol[t_idx])
                hgp_od.sell_orders[hba] = -int(hgp_avol[t_idx])

                # ── Fast VFE order book ────────────────────────────────────────
                vsp  = int(vfe_sp[t_idx])
                vbb  = int(vfe_mid) - vsp // 2
                vba  = vbb + vsp + (0 if vsp % 2 else 1)
                if vba <= vbb: vba = vbb + 1
                vfe_od = OrderDepth()
                vfe_od.buy_orders[vbb]  = int(vfe_bvol[t_idx])
                vfe_od.sell_orders[vba] = -int(vfe_avol[t_idx])

                order_depths: Dict[str, OrderDepth] = {
                    "HYDROGEL_PACK":       hgp_od,
                    "VELVETFRUIT_EXTRACT": vfe_od,
                }

                # ── Fast VEV order books (from pre-computed BS fairs) ──────────
                for ki, k in enumerate(VEV_STRIKES):
                    sym    = f"VEV_{k}"
                    fair   = float(vev_fair[k][t_idx])
                    spread = VEV_SPREADS[k]
                    half   = spread / 2.0
                    bb_v   = max(0, int(math.floor(fair - half)))
                    ba_v   = int(math.ceil(fair + half))
                    if ba_v <= bb_v: ba_v = bb_v + 1
                    vod = OrderDepth()
                    vod.buy_orders[bb_v]  = int(vev_bvol[t_idx, ki])
                    vod.sell_orders[ba_v] = -int(vev_avol[t_idx, ki])
                    order_depths[sym]     = vod
                    last_mids[sym]        = (bb_v + ba_v) * 0.5

                last_mids["HYDROGEL_PACK"]      = hgp_mid
                last_mids["VELVETFRUIT_EXTRACT"] = vfe_mid

                state = TradingState(
                    traderData   = trader_data,
                    timestamp    = ts,
                    listings     = listings,
                    order_depths = order_depths,
                    own_trades   = {},
                    market_trades= {},
                    position     = dict(positions),
                    observations = Observation(),
                )

                try:
                    all_orders, _, trader_data = trader.run(state)
                except Exception:
                    all_orders, trader_data = {}, trader_data

                # Fill orders for each symbol
                for sym in all_syms:
                    orders = all_orders.get(sym, [])
                    if not orders:
                        continue
                    limit = pos_limits[sym]
                    fill_prob = (hgp.make_fill_prob if sym == "HYDROGEL_PACK"
                                 else vfe.make_fill_prob if sym == "VELVETFRUIT_EXTRACT"
                                 else vev_fill_prob)
                    od = order_depths[sym]
                    book_copy = OrderDepth()
                    book_copy.buy_orders  = od.buy_orders.copy()
                    book_copy.sell_orders = od.sell_orders.copy()
                    fills, new_pos, delta_pnl = fill_engine.match_orders(
                        orders, book_copy, positions[sym], limit, fill_prob,
                    )
                    positions[sym]  = new_pos
                    cash_pnl[sym]  += delta_pnl
                    result.fills_by_product[sym] += len(fills)
                    result.n_fills += len(fills)
                    abs_pos = abs(new_pos)
                    if abs_pos > result.max_position[sym]:
                        result.max_position[sym] = abs_pos
                    pos_sums[sym] += abs_pos

                # MTM PnL
                mtm = sum(cash_pnl[s] + positions[s] * last_mids[s] for s in all_syms)
                tick_pnls.append(mtm - cumulative_pnl)
                cumulative_pnl = mtm
                # pnl_curve intentionally not populated — never read, saves 40KB/sim pickle

                if cumulative_pnl > peak_pnl:
                    peak_pnl = cumulative_pnl
                dd = peak_pnl - cumulative_pnl
                if dd > max_dd:
                    max_dd = dd
        finally:
            pass

        result.total_pnl    = cumulative_pnl
        result.terminal_pnl = cumulative_pnl
        result.max_drawdown = max_dd
        result.final_positions = dict(positions)

        for s in all_syms:
            result.pnl_by_product[s] = cash_pnl[s] + positions[s] * last_mids.get(s, 0.0)
            result.avg_position[s]   = pos_sums[s] / max(1, self.n_ticks)

        if len(tick_pnls) > 1:
            arr = np.array(tick_pnls)
            mu, sig = np.mean(arr), np.std(arr)
            if sig > 0:
                result.sharpe = (mu / sig) * math.sqrt(len(tick_pnls))

        return result


def _gen_ou_path(m: ProductModel, n: int, rng: np.random.Generator) -> np.ndarray:
    dW = rng.standard_normal(n)
    mids = np.empty(n)
    x = m.fair_value
    mu = m.mu
    for t in range(n):
        x += m.kappa * (mu - x) + m.sigma * dW[t]
        mids[t] = x
    return mids


def _gen_rw_path(m: ProductModel, n: int, rng: np.random.Generator) -> np.ndarray:
    dW = rng.standard_normal(n)
    mids = np.empty(n)
    x  = m.fair_value
    mu = m.mu
    for t in range(n):
        x  += m.kappa * (mu - x) + m.drift + m.sigma * dW[t]
        mu += m.drift * 0.5
        mids[t] = x
    return mids


# ===========================================================================
# MULTIPROCESSING WORKERS (module-level for Windows spawn compatibility)
# ===========================================================================

# Per-scenario worker (kept for run_scenario() single-scenario testing)
_worker_engine: Optional[Day3SimEngine] = None
_worker_base_hgp: Optional[ProductModel] = None
_worker_base_vfe: Optional[ProductModel] = None
_worker_trader_class = None


def _load_trader_silent(algo_path: str):
    """Load trader and monkey-patch logger.flush to a no-op for speed.

    The logger calls json.dumps on the full 12-symbol state every tick —
    patching to no-op removes ~1-2s of JSON serialization overhead per sim.
    """
    import importlib.util
    spec = importlib.util.spec_from_file_location("submission_module", algo_path)
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if hasattr(mod, "logger"):
        mod.logger.flush = lambda *a, **k: None
        mod.logger.print = lambda *a, **k: None
    return mod.Trader


def _worker_init(algo_path: str, hgp_model_dict: dict, vfe_model_dict: dict,
                 scenario_name: str, n_ticks: int):
    """Single-scenario pool initializer. Engine applies stress once in __init__."""
    global _worker_engine
    os.environ["IMC_TTE_DAYS"] = "5"
    TraderClass = _load_trader_silent(algo_path)
    _worker_engine = Day3SimEngine(
        TraderClass,
        ProductModel(**hgp_model_dict),
        ProductModel(**vfe_model_dict),
        STRESS_SCENARIOS[scenario_name],
        n_ticks,
    )


def _worker_run(sim_seed: int) -> SimResult:
    assert _worker_engine is not None
    return _worker_engine.run(sim_seed)


# Cross-scenario pool — ONE pool for all scenarios (eliminates per-scenario restarts)
_cross_engines: Dict[str, "Day3SimEngine"] = {}


def _cross_worker_init(algo_path: str, hgp_model_dict: dict, vfe_model_dict: dict):
    """Initialize cross-scenario worker: load trader + base models once."""
    global _worker_trader_class, _worker_base_hgp, _worker_base_vfe, _cross_engines
    os.environ["IMC_TTE_DAYS"] = "5"
    _worker_trader_class = _load_trader_silent(algo_path)
    _worker_base_hgp     = ProductModel(**hgp_model_dict)
    _worker_base_vfe     = ProductModel(**vfe_model_dict)
    _cross_engines       = {}   # cache: scenario_name → Day3SimEngine


def _cross_worker_run(args: Tuple[str, int]) -> Tuple[str, SimResult]:
    """Run one sim. Engine is cached per scenario — stress applied only once per
    worker×scenario (not per task), saving ~11k deepcopy+apply_stress calls."""
    scenario_name, sim_seed = args
    if scenario_name not in _cross_engines:
        scenario = STRESS_SCENARIOS[scenario_name]
        _cross_engines[scenario_name] = Day3SimEngine(
            _worker_trader_class, _worker_base_hgp, _worker_base_vfe,
            scenario, N_TICKS,
        )
    return scenario_name, _cross_engines[scenario_name].run(sim_seed)


# ===========================================================================
# BUILD PRODUCT MODELS FROM HISTORICAL DATA
# ===========================================================================

def build_models(workspace: str) -> Tuple[ProductModel, ProductModel]:
    """Calibrate HGP and VFE models from R3 historical data."""
    sys.stderr.write("  Calibrating product models from historical R3 data...\n")
    historical = load_all_historical(workspace)

    # HGP
    if "HYDROGEL_PACK" in historical and len(historical["HYDROGEL_PACK"]) > 100:
        stats = extract_stats(historical["HYDROGEL_PACK"], "HYDROGEL_PACK")
        hgp = ProductModel.from_stats(stats, "fixed_value", HGP_LIMIT)
        hgp.mu         = 10000.0
        hgp.kappa      = max(0.0005, min(hgp.kappa, 0.005))
        hgp.sigma      = max(1.5, min(hgp.sigma, 5.0))
        hgp.spread_mean = max(12.0, hgp.spread_mean)
        hgp.make_fill_prob = 0.015
        sys.stderr.write(f"    HGP calibrated: sigma={hgp.sigma:.3f} kappa={hgp.kappa:.5f} "
                         f"spread={hgp.spread_mean:.1f}\n")
    else:
        hgp = ProductModel.default_hydrogel_pack()
        hgp.position_limit = HGP_LIMIT
        sys.stderr.write("    HGP: using default model\n")

    # VFE
    if "VELVETFRUIT_EXTRACT" in historical and len(historical["VELVETFRUIT_EXTRACT"]) > 100:
        stats = extract_stats(historical["VELVETFRUIT_EXTRACT"], "VELVETFRUIT_EXTRACT")
        vfe = ProductModel.from_stats(stats, "random_walk", VFE_LIMIT)
        vfe.kappa      = max(0.0001, min(vfe.kappa, 0.003))
        vfe.sigma      = max(0.5, min(vfe.sigma, 4.0))
        if vfe.drift <= 0:
            vfe.drift  = 0.0015   # +15/day average (EDA-confirmed)
        vfe.make_fill_prob = 0.018
        sys.stderr.write(f"    VFE calibrated: sigma={vfe.sigma:.3f} kappa={vfe.kappa:.5f} "
                         f"drift={vfe.drift:.5f} spread={vfe.spread_mean:.1f}\n")
    else:
        vfe = ProductModel.default_velvetfruit_extract()
        vfe.position_limit = VFE_LIMIT
        sys.stderr.write("    VFE: using default model\n")

    return hgp, vfe


# ===========================================================================
# SCENARIO RUNNER
# ===========================================================================

def run_scenario(
    scenario_name: str,
    hgp: ProductModel,
    vfe: ProductModel,
    n_sims: int = N_SIMS,
    n_ticks: int = N_TICKS,
    n_workers: int = 1,
    base_seed: int = SEED,
) -> MonteCarloResult:
    """Run n_sims simulations for one scenario, using multiprocessing."""
    scenario = STRESS_SCENARIOS[scenario_name]
    seeds    = [base_seed + i * 7919 for i in range(n_sims)]
    t0       = time.time()

    # Serialise ProductModel as a plain dict for pickling (Windows compat)
    hgp_d = hgp.__dict__.copy()
    vfe_d = vfe.__dict__.copy()

    if n_workers > 1:
        with mp.Pool(
            processes=n_workers,
            initializer=_worker_init,
            initargs=(ALGO_PATH, hgp_d, vfe_d, scenario_name, n_ticks),
        ) as pool:
            results: List[SimResult] = []
            for i, res in enumerate(pool.imap_unordered(_worker_run, seeds)):
                results.append(res)
                if (i + 1) % max(1, n_sims // 10) == 0:
                    el = time.time() - t0
                    eta = (n_sims - i - 1) / ((i + 1) / el) if el > 0 else 0
                    pnls = [r.total_pnl for r in results]
                    sys.stderr.write(
                        f"\r    [{i+1:4d}/{n_sims}] "
                        f"mean={np.mean(pnls):>8,.0f}  "
                        f"ETA {eta:.0f}s    "
                    )
                    sys.stderr.flush()
    else:
        os.environ["IMC_TTE_DAYS"] = "5"
        TraderClass = _load_trader_silent(ALGO_PATH)
        engine = Day3SimEngine(TraderClass, hgp, vfe, scenario, n_ticks)
        results = []
        for i, seed in enumerate(seeds):
            results.append(engine.run(seed))
            if (i + 1) % max(1, n_sims // 10) == 0:
                el = time.time() - t0
                eta = (n_sims - i - 1) / ((i + 1) / el) if el > 0 else 0
                pnls = [r.total_pnl for r in results]
                sys.stderr.write(
                    f"\r    [{i+1:4d}/{n_sims}] "
                    f"mean={np.mean(pnls):>8,.0f}  "
                    f"ETA {eta:.0f}s    "
                )
                sys.stderr.flush()

    sys.stderr.write("\n")
    mc = MonteCarloResult(n_sims=n_sims, results=results, scenario_name=scenario_name)
    mc.compute()
    return mc


def run_all_scenarios(
    hgp: ProductModel,
    vfe: ProductModel,
    n_workers: int = mp.cpu_count(),
) -> Dict[str, MonteCarloResult]:
    """Run all scenarios with ONE shared process pool (no per-scenario startup cost).

    All 14 × 1000 = 14,000 tasks are submitted to a single pool. Workers each
    hold the trader + base models, applying stress fresh per task. This saves
    ~13 pool-startup cycles (~10s each on Windows) vs sequential per-scenario pools.
    """
    total_t0   = time.time()
    total_sims = len(SCENARIOS) * N_SIMS
    hgp_d      = hgp.__dict__.copy()
    vfe_d      = vfe.__dict__.copy()

    # Build task list: (scenario_name, seed) for every sim
    tasks: List[Tuple[str, int]] = []
    for sc in SCENARIOS:
        for i in range(N_SIMS):
            tasks.append((sc, SEED + i * 7919))

    raw: Dict[str, List[SimResult]] = {sc: [] for sc in SCENARIOS}
    done = 0

    sys.stderr.write(
        f"\n  Starting single pool: {n_workers} workers, "
        f"{total_sims:,} total tasks ({len(SCENARIOS)} scenarios × {N_SIMS} sims)\n"
    )
    sys.stderr.flush()

    # maxtasksperchild=None → no worker recycling (avoids startup overhead for small runs)
    with mp.Pool(
        processes=n_workers,
        initializer=_cross_worker_init,
        initargs=(ALGO_PATH, hgp_d, vfe_d),
        maxtasksperchild=None,
    ) as pool:
        for sc_name, result in pool.imap_unordered(_cross_worker_run, tasks):
            raw[sc_name].append(result)
            done += 1
            if done % max(1, total_sims // 50) == 0:
                el  = time.time() - total_t0
                eta = (total_sims - done) / (done / el) if el > 0 else 0
                # Show per-scenario completion counts
                counts = " | ".join(f"{s[:8]}:{len(raw[s])}" for s in SCENARIOS)
                sys.stderr.write(
                    f"\r  [{done:5d}/{total_sims}]  elapsed {el:.0f}s  ETA {eta:.0f}s"
                )
                sys.stderr.flush()

    sys.stderr.write("\n")
    results: Dict[str, MonteCarloResult] = {}
    for sc in SCENARIOS:
        mc = MonteCarloResult(n_sims=N_SIMS, results=raw[sc], scenario_name=sc)
        mc.compute()
        results[sc] = mc
        sys.stderr.write(
            f"  {sc:<22}: mean={mc.pnl_mean:>9,.0f}  "
            f"p5={mc.pnl_p5:>9,.0f}  p95={mc.pnl_p95:>9,.0f}  win={mc.win_rate:.0%}\n"
        )

    total_elapsed = time.time() - total_t0
    sys.stderr.write(f"\nAll scenarios done in {total_elapsed:.0f}s ({total_elapsed/60:.1f} min)\n")
    return results


# ===========================================================================
# TEXT REPORT
# ===========================================================================

def print_report(results: Dict[str, MonteCarloResult]):
    w = 100
    print("\n" + "=" * w)
    print(f"  MC Day 3 Simulation — {N_SIMS} sims × {N_TICKS:,} ticks — TTE=5d — v11")
    print("=" * w)
    hdr = (f"  {'Scenario':<22} {'Mean':>9} {'Std':>9} {'P5':>9} "
           f"{'P25':>9} {'P75':>9} {'P95':>9} {'WinRate':>8} {'Sharpe':>7} {'MaxDD p95':>10}")
    print(hdr)
    print("  " + "-" * (w - 2))
    for sc, mc in results.items():
        flag = " (**)" if any(x in sc for x in ["crash", "extreme", "no_rev", "full_"]) else ""
        print(
            f"  {sc:<22} {mc.pnl_mean:>9,.0f} {mc.pnl_std:>9,.0f} "
            f"{mc.pnl_p5:>9,.0f} {mc.pnl_p25:>9,.0f} {mc.pnl_p75:>9,.0f} "
            f"{mc.pnl_p95:>9,.0f} {mc.win_rate:>7.0%} {mc.sharpe_mean:>7.2f} "
            f"{mc.max_drawdown_p95:>10,.0f}{flag}"
        )
    print("=" * w)
    print("  (**) = high-severity scenario\n")

    # Per-product breakdown for baseline
    baseline = results.get("baseline")
    if baseline and baseline.results:
        prods  = list(baseline.results[0].pnl_by_product.keys())
        vev_syms = [p for p in prods if p.startswith("VEV_")]
        core_syms = ["HYDROGEL_PACK", "VELVETFRUIT_EXTRACT"]
        print("  BASELINE per-product breakdown:")
        for sym in core_syms + ["VEV_TOTAL"]:
            if sym == "VEV_TOTAL":
                pnls = [sum(r.pnl_by_product.get(v, 0) for v in vev_syms) for r in baseline.results]
            else:
                pnls = [r.pnl_by_product.get(sym, 0) for r in baseline.results]
            print(f"    {sym:<30}: mean={np.mean(pnls):>9,.0f}  "
                  f"p5={np.percentile(pnls, 5):>9,.0f}  "
                  f"p95={np.percentile(pnls, 95):>9,.0f}")
        print()


# ===========================================================================
# FIGURE
# ===========================================================================

def plot_results(results: Dict[str, MonteCarloResult], out_path: str):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.gridspec as gridspec
    from matplotlib.patches import Patch

    scenarios = list(results.keys())
    means  = [results[s].pnl_mean for s in scenarios]
    stds   = [results[s].pnl_std  for s in scenarios]
    p5s    = [results[s].pnl_p5   for s in scenarios]
    p95s   = [results[s].pnl_p95  for s in scenarios]
    wrs    = [results[s].win_rate  for s in scenarios]
    sharps = [results[s].sharpe_mean for s in scenarios]
    mxdds  = [results[s].max_drawdown_p95 for s in scenarios]

    COLORS = {
        "pos":    "#27ae60",
        "neg":    "#e74c3c",
        "neutral":"#3498db",
        "accent": "#f39c12",
        "bg":     "#1a1a2e",
        "panel":  "#16213e",
        "text":   "#ecf0f1",
        "grid":   "#2c3e50",
    }
    plt.rcParams.update({
        "figure.facecolor":  COLORS["bg"],
        "axes.facecolor":    COLORS["panel"],
        "axes.edgecolor":    COLORS["grid"],
        "axes.labelcolor":   COLORS["text"],
        "text.color":        COLORS["text"],
        "xtick.color":       COLORS["text"],
        "ytick.color":       COLORS["text"],
        "grid.color":        COLORS["grid"],
        "grid.alpha":        0.5,
        "font.family":       "monospace",
    })

    fig = plt.figure(figsize=(24, 18))
    gs  = gridspec.GridSpec(
        2, 2, figure=fig,
        hspace=0.38, wspace=0.30,
        left=0.07, right=0.97, top=0.93, bottom=0.07,
    )

    ax_dist  = fig.add_subplot(gs[0, 0])   # top-left:  baseline distribution
    ax_scen  = fig.add_subplot(gs[0, 1])   # top-right: scenario comparison bars
    ax_risk  = fig.add_subplot(gs[1, 0])   # bot-left:  risk metrics
    ax_prod  = fig.add_subplot(gs[1, 1])   # bot-right: per-product breakdown

    # ── PANEL 1: Baseline PnL distribution ─────────────────────────────────
    baseline = results.get("baseline")
    if baseline:
        pnls = np.array([r.total_pnl for r in baseline.results])
        ax_dist.hist(pnls, bins=60, color=COLORS["neutral"], alpha=0.75,
                     edgecolor="none", density=True, label="Sim PnL")

        # KDE overlay
        from scipy.stats import gaussian_kde
        kde = gaussian_kde(pnls, bw_method=0.3)
        xr  = np.linspace(pnls.min(), pnls.max(), 400)
        ax_dist.plot(xr, kde(xr), color=COLORS["accent"], lw=2, label="KDE")

        p5, p25, p50, p75, p95 = np.percentile(pnls, [5, 25, 50, 75, 95])
        for v, lbl, col in [
            (p5,   "P5",   COLORS["neg"]),
            (p50,  "P50",  COLORS["accent"]),
            (p95,  "P95",  COLORS["pos"]),
        ]:
            ax_dist.axvline(v, color=col, lw=1.5, ls="--", alpha=0.9)
            ax_dist.text(v, ax_dist.get_ylim()[1] * 0.05, f" {lbl}\n {v:,.0f}",
                         color=col, fontsize=8, va="bottom")

        # Shade loss region
        ax_dist.axvspan(pnls.min(), 0, color=COLORS["neg"], alpha=0.08)

        stats_text = (
            f"N = {baseline.n_sims:,}\n"
            f"Mean : {baseline.pnl_mean:>+9,.0f}\n"
            f"Std  : {baseline.pnl_std:>9,.0f}\n"
            f"P5   : {p5:>+9,.0f}\n"
            f"P25  : {p25:>+9,.0f}\n"
            f"P75  : {p75:>+9,.0f}\n"
            f"P95  : {p95:>+9,.0f}\n"
            f"WinR : {baseline.win_rate:.1%}\n"
            f"Sharpe: {baseline.sharpe_mean:.2f}\n"
            f"MaxDD p95: {baseline.max_drawdown_p95:,.0f}"
        )
        ax_dist.text(0.02, 0.97, stats_text, transform=ax_dist.transAxes,
                     fontsize=8, va="top", family="monospace",
                     bbox=dict(boxstyle="round,pad=0.5", facecolor=COLORS["bg"],
                               edgecolor=COLORS["grid"], alpha=0.85))
        ax_dist.set_title("Baseline PnL Distribution (1,000 sims)", fontsize=11, pad=8)
        ax_dist.set_xlabel("Total PnL (XIRECS)")
        ax_dist.set_ylabel("Density")
        ax_dist.legend(fontsize=8)
        ax_dist.grid(True, axis="x", alpha=0.3)

    # ── PANEL 2: Scenario comparison (horizontal bars) ─────────────────────
    # Sort by mean PnL descending
    order = sorted(range(len(scenarios)), key=lambda i: means[i], reverse=True)
    sc_sorted   = [scenarios[i] for i in order]
    mean_sorted = [means[i]     for i in order]
    p5_sorted   = [p5s[i]       for i in order]
    p95_sorted  = [p95s[i]      for i in order]
    wr_sorted   = [wrs[i]       for i in order]

    bar_colors = [COLORS["pos"] if m >= 0 else COLORS["neg"] for m in mean_sorted]
    y_pos      = np.arange(len(sc_sorted))

    bars = ax_scen.barh(y_pos, mean_sorted, color=bar_colors, alpha=0.82,
                        height=0.6, zorder=3)

    # P5–P95 error whiskers
    for i, (m, p5, p95) in enumerate(zip(mean_sorted, p5_sorted, p95_sorted)):
        ax_scen.plot([p5, p95], [i, i], color=COLORS["text"], lw=1.5, alpha=0.6, zorder=4)
        ax_scen.plot([p5, p5], [i - 0.15, i + 0.15], color=COLORS["neg"], lw=1.5, zorder=4)
        ax_scen.plot([p95, p95], [i - 0.15, i + 0.15], color=COLORS["pos"], lw=1.5, zorder=4)

    # Win rate annotation
    for i, (m, wr) in enumerate(zip(mean_sorted, wr_sorted)):
        x_off = 300
        ax_scen.text(max(m, 0) + x_off, i, f" {wr:.0%}", va="center",
                     fontsize=7, color=COLORS["text"], alpha=0.85)

    ax_scen.axvline(0, color=COLORS["text"], lw=0.8, alpha=0.5)
    ax_scen.set_yticks(y_pos)
    ax_scen.set_yticklabels(sc_sorted, fontsize=8)
    ax_scen.set_xlabel("Mean PnL (XIRECS)  [whiskers = P5–P95]")
    ax_scen.set_title("All Scenarios: Mean PnL + P5/P95 Interval", fontsize=11, pad=8)
    ax_scen.grid(True, axis="x", alpha=0.3, zorder=0)
    legend_elems = [
        Patch(color=COLORS["pos"], label="Mean ≥ 0"),
        Patch(color=COLORS["neg"], label="Mean < 0"),
    ]
    ax_scen.legend(handles=legend_elems, fontsize=8, loc="lower right")

    # ── PANEL 3: Risk metrics per scenario ─────────────────────────────────
    n = len(scenarios)
    x = np.arange(n)
    w = 0.28

    wr_arr  = np.array([results[s].win_rate for s in scenarios])
    sh_arr  = np.array([results[s].sharpe_mean for s in scenarios])
    # Normalise Sharpe to [0,1] for display on same axis
    sh_norm = np.clip(sh_arr / max(abs(sh_arr).max(), 1e-6), -1, 1) * 100
    mxdd_arr = np.array([results[s].max_drawdown_p95 for s in scenarios]) / 1000.0  # → k

    ax_risk.bar(x - w, wr_arr * 100, width=w, color=COLORS["pos"],
                alpha=0.75, label="Win Rate (%)")
    ax_risk.bar(x,     sh_norm,       width=w, color=COLORS["accent"],
                alpha=0.75, label="Sharpe (scaled ×100)")
    ax_risk.bar(x + w, -mxdd_arr,     width=w, color=COLORS["neg"],
                alpha=0.75, label="−MaxDD P95 (k XIRECS)")

    ax_risk.axhline(0,  color=COLORS["text"], lw=0.5, alpha=0.4)
    ax_risk.axhline(50, color=COLORS["pos"],  lw=0.5, ls=":", alpha=0.4)
    ax_risk.set_xticks(x)
    ax_risk.set_xticklabels(scenarios, rotation=45, ha="right", fontsize=7)
    ax_risk.set_ylabel("Metric value")
    ax_risk.set_title("Risk Metrics per Scenario", fontsize=11, pad=8)
    ax_risk.legend(fontsize=8, loc="upper right")
    ax_risk.grid(True, axis="y", alpha=0.3)

    # ── PANEL 4: Per-product PnL breakdown (baseline) ──────────────────────
    if baseline and baseline.results:
        syms = list(baseline.results[0].pnl_by_product.keys())
        vev_syms  = [s for s in syms if s.startswith("VEV_")]
        core_syms = ["HYDROGEL_PACK", "VELVETFRUIT_EXTRACT"]

        labels, means_prod, p5s_prod, p95s_prod = [], [], [], []
        for sym in core_syms:
            pnls_p = np.array([r.pnl_by_product.get(sym, 0) for r in baseline.results])
            labels.append(sym.replace("_", "\n"))
            means_prod.append(np.mean(pnls_p))
            p5s_prod.append(np.percentile(pnls_p, 5))
            p95s_prod.append(np.percentile(pnls_p, 95))

        # VEV aggregate
        vev_pnls = np.array([
            sum(r.pnl_by_product.get(v, 0) for v in vev_syms) for r in baseline.results
        ])
        labels.append("VEV\nTOTAL")
        means_prod.append(np.mean(vev_pnls))
        p5s_prod.append(np.percentile(vev_pnls, 5))
        p95s_prod.append(np.percentile(vev_pnls, 95))

        # Individual VEV strikes
        for v in vev_syms:
            pnls_v = np.array([r.pnl_by_product.get(v, 0) for r in baseline.results])
            labels.append(v.replace("VEV_", "K="))
            means_prod.append(np.mean(pnls_v))
            p5s_prod.append(np.percentile(pnls_v, 5))
            p95s_prod.append(np.percentile(pnls_v, 95))

        x_p = np.arange(len(labels))
        cols_p = [COLORS["pos"] if m >= 0 else COLORS["neg"] for m in means_prod]
        ax_prod.bar(x_p, means_prod, color=cols_p, alpha=0.8, zorder=3)

        for i, (m, p5, p95) in enumerate(zip(means_prod, p5s_prod, p95s_prod)):
            ax_prod.plot([i, i], [p5, p95], color=COLORS["text"], lw=1.5, alpha=0.6, zorder=4)
            ax_prod.plot([i - 0.15, i + 0.15], [p5, p5],   color=COLORS["neg"], lw=1.5, zorder=4)
            ax_prod.plot([i - 0.15, i + 0.15], [p95, p95], color=COLORS["pos"], lw=1.5, zorder=4)

        ax_prod.axhline(0, color=COLORS["text"], lw=0.5, alpha=0.4)
        ax_prod.set_xticks(x_p)
        ax_prod.set_xticklabels(labels, rotation=45, ha="right", fontsize=7)
        ax_prod.set_ylabel("Mean PnL (XIRECS)  [whiskers = P5–P95]")
        ax_prod.set_title("Per-Product PnL Breakdown (Baseline)", fontsize=11, pad=8)
        ax_prod.grid(True, axis="y", alpha=0.3, zorder=0)

    # ── Title ───────────────────────────────────────────────────────────────
    tte_end = max(TTE_DAYS_T0 - (N_TICKS - 1) * 100.0 / TS_PER_DAY, TTE_FLOOR_DAYS)
    fig.suptitle(
        f"Monte Carlo — Day 3 Live Session — submission_r3_v11.py\n"
        f"{N_SIMS:,} sims × {N_TICKS:,} ticks (TTE {TTE_DAYS_T0:.1f}→{tte_end:.2f}d) × {len(SCENARIOS)} scenarios  |  "
        f"VEV BS-coupled  |  {mp.cpu_count()} CPU parallel",
        fontsize=13, y=0.975, color=COLORS["text"],
    )

    plt.savefig(out_path, dpi=150, bbox_inches="tight",
                facecolor=COLORS["bg"], edgecolor="none")
    plt.close(fig)
    sys.stderr.write(f"\n  Figure saved → {out_path}\n")


# ===========================================================================
# JSON EXPORT
# ===========================================================================

def export_json(results: Dict[str, MonteCarloResult], out_path: str):
    data = {}
    for sc, mc in results.items():
        data[sc] = {
            "n_sims":              mc.n_sims,
            "pnl_mean":            round(mc.pnl_mean, 2),
            "pnl_std":             round(mc.pnl_std, 2),
            "pnl_median":          round(mc.pnl_median, 2),
            "pnl_p5":              round(mc.pnl_p5, 2),
            "pnl_p25":             round(mc.pnl_p25, 2),
            "pnl_p75":             round(mc.pnl_p75, 2),
            "pnl_p95":             round(mc.pnl_p95, 2),
            "win_rate":            round(mc.win_rate, 4),
            "sharpe_mean":         round(mc.sharpe_mean, 4),
            "sharpe_std":          round(mc.sharpe_std, 4),
            "max_drawdown_mean":   round(mc.max_drawdown_mean, 2),
            "max_drawdown_p95":    round(mc.max_drawdown_p95, 2),
            "avg_fills":           round(mc.avg_fills, 1),
        }
        # Per-product means for baseline
        if mc.results:
            prod_means = {}
            all_prods = list(mc.results[0].pnl_by_product.keys())
            for sym in all_prods:
                pnls = [r.pnl_by_product.get(sym, 0) for r in mc.results]
                prod_means[sym] = round(float(np.mean(pnls)), 2)
            data[sc]["product_means"] = prod_means
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    sys.stderr.write(f"  JSON saved → {out_path}\n")


# ===========================================================================
# MAIN
# ===========================================================================

def main():
    n_workers = N_WORKERS
    sys.stderr.write(
        f"\n{'='*70}\n"
        f"  MC Day 3 Simulation — submission_r3_v11.py\n"
        f"  {N_SIMS:,} sims × {N_TICKS:,} ticks × {len(SCENARIOS)} scenarios\n"
        f"  TTE=5d | VEV BS-coupled | {n_workers} CPU workers (memory-safe)\n"
        f"{'='*70}\n"
    )

    hgp, vfe = build_models(str(ROOT))
    results = run_all_scenarios(hgp, vfe, n_workers=n_workers)

    print_report(results)
    export_json(results, OUT_JSON)
    plot_results(results, OUT_PNG)

    sys.stderr.write(f"\nDone. Open {OUT_PNG} to view results.\n")


if __name__ == "__main__":
    mp.freeze_support()   # required for Windows with multiprocessing + frozen executables
    main()
