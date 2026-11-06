"""
IMC Prosperity 4 — Round 5 Monte Carlo Simulator
=================================================
Calibrated to Round 5 data (3 days × 10,000 ticks × 50 products).

R5 STRUCTURAL FACTS (from Step 1 Intelligence Report):
  - 50 NEW products in 10 themed groups of 5 (R3/R4 products decommissioned)
  - POSITION LIMIT = 10 for every product (vs 50-400 in prior rounds)
  - NO trader IDs disclosed (buyer/seller fields are empty unless SUBMISSION) —
    therefore NO named participant agents exist to model
  - Two structurally significant groups:
      * PEBBLES: 5-leg basket sum ≡ 50,000 (R²=1.0000, residual std 2.8)
      * SNACKPACK: CHOC+VAN ≈ 19,940 (std 76, daily drift ±150)
  - Three tick-level mean-reverting products (post-Roll-bounce caveat):
      ROBOT_DISHES (ACF1=-0.232), ROBOT_IRONING (-0.125),
      OXYGEN_SHAKE_EVENING_BREATH (-0.123), OXYGEN_SHAKE_CHOCOLATE (-0.089)
  - Two heavy-tailed products: OXYGEN_SHAKE_{CHOCOLATE, EVENING_BREATH}
    (kurt 14-16, max_jump ~100)
  - All other 41 products are near-Gaussian random walks (Hurst≈0.50)

ARCHITECTURE PRESERVED FROM R3/R4 (archive/r3/montecarlo.py):
  - datamodel replicas + sys.modules patch
  - ProductStats / ProductModel + OU-from-stats calibration
  - MarketGenerator (orderbook synthesis, multi-level, empty-side ticks)
  - FillEngine (deterministic takes, probabilistic makes; per-order limit check)
  - BootstrapGenerator (block-resample R5 CSVs with noise)
  - StressScenario framework + per-scenario perturbation
  - SimulationEngine + MonteCarloResult + parallel MC runner
  - Parameter sweep, reporting, JSON output

R5-SPECIFIC CHANGES (search "# NEW" and "# MODIFIED"):
  - All 50 R5 products with empirical OU/spread/depth from Phase B CSVs
  - PEBBLES basket constraint enforced exactly in parametric mode
  - SNACKPACK CHOC+VAN soft-cointegration enforced in parametric mode
  - Heavy-tail jump generator for OXYGEN_SHAKE products (Student-t innovations)
  - Negative-ACF tick-fade dynamics for ROBOT_DISHES / IRONING
  - Named-trader subsystem REMOVED (R5 has no trader IDs)
  - NoiseTraderSimulator adds anonymous market-trade flow
  - Five new stress scenarios required by user spec:
      regime_shift, no_insider, crowded_trade, limit_stress, correlation_break
  - Per-strategy attribution (S2, P2, S1, R2, R3, M1, …) tracked separately
  - Shadow benchmark: passive mid-price follower PnL computed each sim
  - All position limits = 10 (was 80-400)

Usage (R5):
  python montecarlo.py                              # 200 sims, baseline, R5
  python montecarlo.py --stress regime_shift
  python montecarlo.py --stress crowded_trade --strategy P2
  python montecarlo.py --stress limit_stress
  python montecarlo.py --workers 8 --sims 1000
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import math
import multiprocessing
import os
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

import numpy as np

# ---------------------------------------------------------------------------
# Datamodel replicas (UNCHANGED from R3/R4 simulator) — keep contract identical
# so existing trader code (submission*.py) imports resolve correctly.
# ---------------------------------------------------------------------------

class Listing:
    __slots__ = ("symbol", "product", "denomination")
    def __init__(self, symbol: str, product: str, denomination: str):
        self.symbol = symbol
        self.product = product
        self.denomination = denomination

class Order:
    __slots__ = ("symbol", "price", "quantity")
    def __init__(self, symbol: str, price: int, quantity: int):
        self.symbol = symbol
        self.price = price
        self.quantity = quantity
    def __repr__(self):
        return f"Order({self.symbol}, {self.price}, {self.quantity})"

class OrderDepth:
    __slots__ = ("buy_orders", "sell_orders")
    def __init__(self):
        self.buy_orders: Dict[int, int] = {}
        self.sell_orders: Dict[int, int] = {}

class Trade:
    __slots__ = ("symbol", "price", "quantity", "buyer", "seller", "timestamp")
    def __init__(self, symbol="", price=0, quantity=0, buyer="", seller="", timestamp=0):
        self.symbol = symbol
        self.price = price
        self.quantity = quantity
        self.buyer = buyer
        self.seller = seller
        self.timestamp = timestamp

class ConversionObservation:
    def __init__(self, **kwargs):
        self.bidPrice = kwargs.get("bidPrice", 0.0)
        self.askPrice = kwargs.get("askPrice", 0.0)
        self.transportFees = kwargs.get("transportFees", 0.0)
        self.exportTariff = kwargs.get("exportTariff", 0.0)
        self.importTariff = kwargs.get("importTariff", 0.0)

class Observation:
    __slots__ = ("plainValueObservations", "conversionObservations")
    def __init__(self):
        self.plainValueObservations: Dict[str, int] = {}
        self.conversionObservations: Dict[str, ConversionObservation] = {}

class TradingState:
    __slots__ = (
        "traderData", "timestamp", "listings", "order_depths",
        "own_trades", "market_trades", "position", "observations",
    )
    def __init__(self, traderData="", timestamp=0, listings=None, order_depths=None,
                 own_trades=None, market_trades=None, position=None, observations=None):
        self.traderData = traderData
        self.timestamp = timestamp
        self.listings = listings or {}
        self.order_depths = order_depths or {}
        self.own_trades = own_trades or {}
        self.market_trades = market_trades or {}
        self.position = position or {}
        self.observations = observations or Observation()

import types
_dm = types.ModuleType("datamodel")
for _name in ["Listing","Order","OrderDepth","Trade","ConversionObservation",
              "Observation","TradingState","Symbol","Product","Position"]:
    setattr(_dm, _name, globals().get(_name, str))
_dm.Symbol = str; _dm.Product = str; _dm.Position = int
sys.modules["datamodel"] = _dm


# ---------------------------------------------------------------------------
# NEW: Round 5 product taxonomy and position limits
# ---------------------------------------------------------------------------
# All 50 R5 products. Position limit = 10 for ALL of them per the wiki
# ("All products have a position limit of 10"). No conversions, no
# observations, no settlement penalty visible — products mark to last mid.

R5_POSITION_LIMIT = 10  # NEW: universal R5 position limit (was 80-400 in R3/R4)

R5_GROUPS: Dict[str, List[str]] = {  # NEW: full taxonomy
    "GALAXY_SOUNDS": [
        "GALAXY_SOUNDS_BLACK_HOLES", "GALAXY_SOUNDS_DARK_MATTER",
        "GALAXY_SOUNDS_PLANETARY_RINGS", "GALAXY_SOUNDS_SOLAR_FLAMES",
        "GALAXY_SOUNDS_SOLAR_WINDS",
    ],
    "MICROCHIP": [
        "MICROCHIP_CIRCLE", "MICROCHIP_OVAL", "MICROCHIP_RECTANGLE",
        "MICROCHIP_SQUARE", "MICROCHIP_TRIANGLE",
    ],
    "OXYGEN_SHAKE": [
        "OXYGEN_SHAKE_CHOCOLATE", "OXYGEN_SHAKE_EVENING_BREATH",
        "OXYGEN_SHAKE_GARLIC", "OXYGEN_SHAKE_MINT",
        "OXYGEN_SHAKE_MORNING_BREATH",
    ],
    "PANEL": [
        "PANEL_1X2", "PANEL_1X4", "PANEL_2X2", "PANEL_2X4", "PANEL_4X4",
    ],
    "PEBBLES": [
        "PEBBLES_XS", "PEBBLES_S", "PEBBLES_M", "PEBBLES_L", "PEBBLES_XL",
    ],
    "ROBOT": [
        "ROBOT_DISHES", "ROBOT_IRONING", "ROBOT_LAUNDRY",
        "ROBOT_MOPPING", "ROBOT_VACUUMING",
    ],
    "SLEEP_POD": [
        "SLEEP_POD_COTTON", "SLEEP_POD_LAMB_WOOL", "SLEEP_POD_NYLON",
        "SLEEP_POD_POLYESTER", "SLEEP_POD_SUEDE",
    ],
    "SNACKPACK": [
        "SNACKPACK_CHOCOLATE", "SNACKPACK_PISTACHIO", "SNACKPACK_RASPBERRY",
        "SNACKPACK_STRAWBERRY", "SNACKPACK_VANILLA",
    ],
    "TRANSLATOR": [
        "TRANSLATOR_ASTRO_BLACK", "TRANSLATOR_ECLIPSE_CHARCOAL",
        "TRANSLATOR_GRAPHITE_MIST", "TRANSLATOR_SPACE_GRAY",
        "TRANSLATOR_VOID_BLUE",
    ],
    "UV_VISOR": [
        "UV_VISOR_AMBER", "UV_VISOR_MAGENTA", "UV_VISOR_ORANGE",
        "UV_VISOR_RED", "UV_VISOR_YELLOW",
    ],
}
R5_ALL_PRODUCTS: List[str] = [s for syms in R5_GROUPS.values() for s in syms]
R5_GROUP_OF: Dict[str, str] = {s: g for g, syms in R5_GROUPS.items() for s in syms}

# NEW: PEBBLES basket constraint (sum of 5 mids ≡ 50,000 ± 2.8 mid-noise)
R5_PEBBLES_BASKET_SUM = 50000.0
R5_PEBBLES_BASKET_NOISE_STD = 2.8

# NEW: SNACKPACK CHOC+VAN soft cointegration target (mean of full sample)
R5_SNACKPACK_CHOCVAN_TARGET = 19940.67
R5_SNACKPACK_CHOCVAN_STD = 76.20  # cross-day std; intraday is 32-48
R5_SNACKPACK_CHOCVAN_DAILY_DRIFT_STD = 80.0  # absorbs day-to-day mean shift

# NEW: products with statistically significant tick-level negative ACF.
# CAVEAT: Per Step 3 adversarial review (Roll 1984 critique), some/all of
# this is bid-ask bounce. The simulator faithfully reproduces what the data
# shows; the trader is responsible for not being fooled by it.
R5_NEG_ACF_PRODUCTS: Dict[str, float] = {
    "ROBOT_DISHES": -0.232,
    "OXYGEN_SHAKE_EVENING_BREATH": -0.123,
    "ROBOT_IRONING": -0.125,
    "OXYGEN_SHAKE_CHOCOLATE": -0.089,
}

# NEW: heavy-tail products (Student-t innovations instead of Gaussian)
R5_HEAVY_TAIL_PRODUCTS: Dict[str, float] = {
    # df=4 gives kurt=6 raw; combined with regime mixture we get observed kurt~15
    "OXYGEN_SHAKE_CHOCOLATE": 4.0,
    "OXYGEN_SHAKE_EVENING_BREATH": 4.0,
    "ROBOT_DISHES": 4.0,
    "ROBOT_IRONING": 4.0,
}


# ---------------------------------------------------------------------------
# Historical loader (UNCHANGED interface; reads R5 day_2/3/4 CSVs)
# ---------------------------------------------------------------------------

@dataclass
class ProductStats:
    """Extracted statistics for one product from historical data."""
    symbol: str
    mid_prices: np.ndarray
    spreads: np.ndarray
    bid_volumes: np.ndarray
    ask_volumes: np.ndarray
    returns: np.ndarray = field(default_factory=lambda: np.array([]))
    drift_per_tick: float = 0.0
    volatility: float = 0.0
    mean_reversion_speed: float = 0.0
    long_run_mean: float = 0.0
    spread_mean: float = 0.0
    spread_std: float = 0.0
    vol_mean: float = 0.0
    vol_std: float = 0.0
    autocorr_lag1: float = 0.0
    hurst: float = 0.5                # NEW: Hurst exponent from R/S analysis
    kurtosis: float = 0.0             # NEW: excess kurtosis for heavy-tail flag
    depth_levels: int = 2
    level_spacing_mean: float = 3.0
    level_spacing_std: float = 1.0
    trade_arrival_rate: float = 0.01
    trade_size_mean: float = 5.0
    trade_size_std: float = 2.0

    def __post_init__(self):
        if len(self.mid_prices) > 1:
            self.returns = np.diff(self.mid_prices)
            self.drift_per_tick = float(np.mean(self.returns))
            self.volatility = float(np.std(self.returns))
            if self.volatility > 0 and len(self.returns) > 2:
                self.autocorr_lag1 = float(np.corrcoef(
                    self.returns[:-1], self.returns[1:]
                )[0, 1])
                # NEW: kurtosis (excess; Gaussian = 0)
                m4 = float(np.mean((self.returns - self.returns.mean()) ** 4))
                self.kurtosis = m4 / (self.volatility ** 4) - 3.0
            self.long_run_mean = float(np.mean(self.mid_prices))
            if len(self.returns) > 10:
                y = self.returns
                x = self.mid_prices[:-1]
                xm, ym = float(np.mean(x)), float(np.mean(y))
                cov_xy = float(np.mean((x - xm) * (y - ym)))
                var_x = float(np.var(x))
                if var_x > 0:
                    b = cov_xy / var_x
                    a = ym - b * xm
                    self.mean_reversion_speed = max(0.0, -b)
                    if self.mean_reversion_speed > 0:
                        self.long_run_mean = a / self.mean_reversion_speed
            self.spread_mean = float(np.mean(self.spreads[self.spreads > 0])) if np.any(self.spreads > 0) else 14.0
            self.spread_std = float(np.std(self.spreads[self.spreads > 0])) if np.any(self.spreads > 0) else 3.0
            bv = self.bid_volumes[self.bid_volumes > 0]
            av = self.ask_volumes[self.ask_volumes > 0]
            self.vol_mean = float(np.mean(np.concatenate([bv, av]))) if len(bv) > 0 else 15.0
            self.vol_std = float(np.std(np.concatenate([bv, av]))) if len(bv) > 0 else 5.0
            self.hurst = _hurst_rs(self.mid_prices)  # NEW

def _hurst_rs(series: np.ndarray, max_lag: int = 200) -> float:  # NEW
    """R/S Hurst exponent (truncated for speed)."""
    n = len(series)
    if n < 100:
        return 0.5
    lags = [10, 20, 50, 100, min(max_lag, n // 4)]
    rs = []
    for lag in lags:
        if lag >= n:
            continue
        chunks = n // lag
        rs_vals = []
        for i in range(chunks):
            seg = series[i*lag:(i+1)*lag]
            mean_seg = seg.mean()
            dev = np.cumsum(seg - mean_seg)
            R = float(dev.max() - dev.min())
            S = float(seg.std())
            if S > 0:
                rs_vals.append(R / S)
        if rs_vals:
            rs.append((lag, float(np.mean(rs_vals))))
    if len(rs) < 2:
        return 0.5
    xs = np.log([x[0] for x in rs])
    ys = np.log([x[1] for x in rs])
    slope = float(np.polyfit(xs, ys, 1)[0])
    return max(0.1, min(0.95, slope))


def load_prices_csv(filepath: str) -> Dict[str, List[dict]]:
    products: Dict[str, List[dict]] = defaultdict(list)
    with open(filepath, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            product = row["product"]
            tick = {
                "timestamp": int(row["timestamp"]),
                "bid_price_1": _safe_float(row.get("bid_price_1", "")),
                "bid_volume_1": _safe_int(row.get("bid_volume_1", "")),
                "bid_price_2": _safe_float(row.get("bid_price_2", "")),
                "bid_volume_2": _safe_int(row.get("bid_volume_2", "")),
                "bid_price_3": _safe_float(row.get("bid_price_3", "")),
                "bid_volume_3": _safe_int(row.get("bid_volume_3", "")),
                "ask_price_1": _safe_float(row.get("ask_price_1", "")),
                "ask_volume_1": _safe_int(row.get("ask_volume_1", "")),
                "ask_price_2": _safe_float(row.get("ask_price_2", "")),
                "ask_volume_2": _safe_int(row.get("ask_volume_2", "")),
                "ask_price_3": _safe_float(row.get("ask_price_3", "")),
                "ask_volume_3": _safe_int(row.get("ask_volume_3", "")),
                "mid_price": _safe_float(row.get("mid_price", "")),
            }
            products[product].append(tick)
    return dict(products)


def load_trades_csv(filepath: str) -> Dict[str, List[dict]]:
    trades: Dict[str, List[dict]] = defaultdict(list)
    if not os.path.exists(filepath):
        return dict(trades)
    with open(filepath, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            symbol = row.get("symbol", "")
            trades[symbol].append({
                "timestamp": int(row.get("timestamp", 0)),
                "buyer": row.get("buyer", ""),
                "seller": row.get("seller", ""),
                "price": _safe_float(row.get("price", "")),
                "quantity": _safe_int(row.get("quantity", "")),
            })
    return dict(trades)


def extract_stats(product_ticks: List[dict], symbol: str) -> ProductStats:
    mids, spreads, bvols, avols = [], [], [], []
    for t in product_ticks:
        bp1 = t["bid_price_1"]; ap1 = t["ask_price_1"]
        if bp1 is not None and ap1 is not None and bp1 > 0 and ap1 > 0:
            mids.append((bp1 + ap1) / 2.0)
            spreads.append(ap1 - bp1)
            bvols.append(t["bid_volume_1"] or 0)
            avols.append(t["ask_volume_1"] or 0)
        elif t["mid_price"] is not None and t["mid_price"] > 0:
            mids.append(t["mid_price"]); spreads.append(0); bvols.append(0); avols.append(0)
    return ProductStats(
        symbol=symbol,
        mid_prices=np.array(mids, dtype=np.float64),
        spreads=np.array(spreads, dtype=np.float64),
        bid_volumes=np.array(bvols, dtype=np.float64),
        ask_volumes=np.array(avols, dtype=np.float64),
    )


def _safe_float(s):
    try: return float(s) if s.strip() else None
    except (ValueError, AttributeError): return None
def _safe_int(s):
    try: return int(float(s)) if s.strip() else None
    except (ValueError, AttributeError): return None


# ---------------------------------------------------------------------------
# Generative model (MODIFIED: R5 fields added; R3/R4 BS-voucher path removed)
# ---------------------------------------------------------------------------

@dataclass
class ProductModel:
    symbol: str
    product_type: str               # "fixed_value" or "random_walk"
    fair_value: float
    position_limit: int = R5_POSITION_LIMIT  # MODIFIED: default 10 (was 80)
    kappa: float = 0.0
    mu: float = 10000.0
    sigma: float = 2.0
    drift: float = 0.0
    spread_mean: float = 14.0
    spread_std: float = 3.0
    vol_mean: float = 15.0
    vol_std: float = 5.0
    depth_levels: int = 2
    level_gap_mean: float = 3.0
    level_gap_std: float = 1.0
    trade_prob: float = 0.01
    trade_size_mean: float = 5.0
    trade_size_std: float = 2.0
    make_fill_prob: float = 0.03
    price_floor: float = float("-inf")
    # NEW R5 fields
    group: str = ""                 # NEW: e.g. "PEBBLES"
    ar1_coef: float = 0.0           # NEW: AR(1) coefficient on returns (neg-ACF)
    student_t_df: float = 0.0       # NEW: 0=Gaussian, >2=Student-t innovations
    hurst: float = 0.5              # NEW: empirical Hurst (informational)

    @classmethod
    def from_stats(cls, stats: ProductStats, position_limit: int = R5_POSITION_LIMIT,  # MODIFIED
                   product_type: str = "random_walk") -> "ProductModel":
        sym = stats.symbol
        m = cls(
            symbol=sym,
            product_type=product_type,
            fair_value=float(stats.mid_prices[0]) if len(stats.mid_prices) > 0 else 10000.0,
            position_limit=position_limit,
            kappa=float(stats.mean_reversion_speed),
            mu=float(stats.long_run_mean),
            sigma=float(stats.volatility) if stats.volatility > 0 else 2.0,
            drift=float(stats.drift_per_tick),
            spread_mean=float(stats.spread_mean),
            spread_std=float(stats.spread_std),
            vol_mean=float(stats.vol_mean),
            vol_std=float(stats.vol_std),
            hurst=float(stats.hurst),
        )
        m.group = R5_GROUP_OF.get(sym, "")
        # AR(1) on returns for tick-fade products. Use empirical estimate when
        # |acf1| > 0.05; else 0.
        if abs(stats.autocorr_lag1) > 0.05:
            m.ar1_coef = float(stats.autocorr_lag1)
        # Student-t for heavy-tail products
        if sym in R5_HEAVY_TAIL_PRODUCTS:
            m.student_t_df = R5_HEAVY_TAIL_PRODUCTS[sym]
        # Make fill probability scales with spread (wider spread = lower fill rate)
        m.make_fill_prob = max(0.005, min(0.04, 0.30 / max(1.0, m.spread_mean)))
        return m


class MarketGenerator:
    """Per-product orderbook synthesis. Supports AR(1)-on-returns and
    Student-t innovations (NEW for R5)."""

    def __init__(self, model: ProductModel, rng: np.random.Generator):
        self.model = model
        self.rng = rng
        self.current_mid = model.fair_value
        self._last_return = 0.0  # NEW: for AR(1) dynamics

    def reset(self):
        self.current_mid = self.model.fair_value
        self._last_return = 0.0

    def _innovation(self) -> float:  # NEW
        m = self.model
        if m.student_t_df > 2.0:
            # Standardised Student-t (var=1) so sigma still applies
            df = m.student_t_df
            t = self.rng.standard_t(df)
            scale = math.sqrt((df - 2.0) / df)
            return float(t * scale)
        return float(self.rng.standard_normal())

    def step(self) -> float:
        m = self.model
        eps = self._innovation() * m.sigma
        if m.product_type == "fixed_value":
            base_ret = m.kappa * (m.mu - self.current_mid) + eps
        else:
            base_ret = m.kappa * (m.mu - self.current_mid) + m.drift + eps
            m.mu += m.drift * 0.5
        if m.ar1_coef != 0.0:  # NEW: AR(1) on returns
            ret = base_ret + m.ar1_coef * self._last_return
        else:
            ret = base_ret
        self._last_return = ret
        self.current_mid += ret
        if m.price_floor > float("-inf"):
            self.current_mid = max(m.price_floor, self.current_mid)
        return self.current_mid

    def generate_order_book(self, mid: float) -> OrderDepth:
        od = OrderDepth()
        m = self.model
        spread = max(2, int(round(self.rng.normal(m.spread_mean, m.spread_std))))
        half = spread / 2.0
        best_bid = int(math.floor(mid - half))
        best_ask = int(math.ceil(mid + half))
        if best_bid >= best_ask:
            best_ask = best_bid + 1
        bv1 = max(1, int(round(self.rng.normal(m.vol_mean, m.vol_std))))
        av1 = max(1, int(round(self.rng.normal(m.vol_mean, m.vol_std))))
        od.buy_orders[best_bid] = bv1
        od.sell_orders[best_ask] = -av1
        for lvl in range(1, m.depth_levels):
            gap = max(1, int(round(self.rng.normal(m.level_gap_mean, m.level_gap_std))))
            vol_decay = max(0.5, 1.0 + 0.3 * lvl)
            bv = max(1, int(round(self.rng.normal(m.vol_mean * vol_decay, m.vol_std))))
            av = max(1, int(round(self.rng.normal(m.vol_mean * vol_decay, m.vol_std))))
            od.buy_orders[best_bid - gap*lvl] = bv
            od.sell_orders[best_ask + gap*lvl] = -av
        if self.rng.random() < 0.03:
            if self.rng.random() < 0.5:
                od.buy_orders = {}
            else:
                od.sell_orders = {}
        return od

    def generate_market_trades(self, mid: float, timestamp: int) -> List[Trade]:
        trades = []
        m = self.model
        if self.rng.random() < m.trade_prob:
            size = max(1, int(round(self.rng.normal(m.trade_size_mean, m.trade_size_std))))
            price_offset = int(round(self.rng.normal(0, m.spread_mean * 0.3)))
            price = int(round(mid)) + price_offset
            # NOTE (R5): buyer/seller fields are EMPTY — wiki is explicit.
            trades.append(Trade(symbol=m.symbol, price=price, quantity=size,
                                buyer="", seller="", timestamp=timestamp))
        return trades


# ---------------------------------------------------------------------------
# Fill engine (UNCHANGED logic; processes orders in submission order with
# per-order limit check, takes deterministic, makes probabilistic). The
# wiki's "all-or-nothing" rule [Phase A item A2] is NOT enforced here — we
# keep the empirically-observed R1-R4 per-order behaviour. Trader code
# should remain defensive (never over-quote) which is safe under both
# rule interpretations.
# ---------------------------------------------------------------------------

class FillEngine:
    def __init__(self, rng: np.random.Generator):
        self.rng = rng
        self.limit_breach_count = 0  # NEW: count attempted breaches per sim

    def match_orders(self, orders, book, position, position_limit, make_fill_prob):
        fills: List[Trade] = []
        pnl = 0.0
        pos = position
        for order in orders:
            if order.quantity > 0:
                max_qty = position_limit - pos
                if max_qty <= 0:
                    if order.quantity > 0:
                        self.limit_breach_count += 1  # NEW
                    continue
                qty = min(order.quantity, max_qty)
            else:
                max_qty = position_limit + pos
                if max_qty <= 0:
                    if order.quantity < 0:
                        self.limit_breach_count += 1  # NEW
                    continue
                qty = max(-max_qty, order.quantity)
            if qty == 0: continue
            if qty > 0:
                is_take = False
                for ask_p in sorted(book.sell_orders.keys()):
                    if order.price >= ask_p:
                        is_take = True
                        fillable = min(qty, abs(book.sell_orders[ask_p]))
                        if fillable > 0:
                            fills.append(Trade(order.symbol, ask_p, fillable, "SUBMISSION", "BOT", 0))
                            pos += fillable; pnl -= ask_p * fillable; qty -= fillable
                            book.sell_orders[ask_p] += fillable
                            if abs(book.sell_orders[ask_p]) <= 0:
                                del book.sell_orders[ask_p]
                        if qty <= 0: break
                if not is_take and qty > 0:
                    if self.rng.random() < make_fill_prob:
                        fill_qty = max(1, int(qty * self.rng.uniform(0.3, 1.0)))
                        fills.append(Trade(order.symbol, order.price, fill_qty, "SUBMISSION", "BOT", 0))
                        pos += fill_qty; pnl -= order.price * fill_qty
            else:
                abs_qty = abs(qty); is_take = False
                for bid_p in sorted(book.buy_orders.keys(), reverse=True):
                    if order.price <= bid_p:
                        is_take = True
                        fillable = min(abs_qty, book.buy_orders[bid_p])
                        if fillable > 0:
                            fills.append(Trade(order.symbol, bid_p, fillable, "BOT", "SUBMISSION", 0))
                            pos -= fillable; pnl += bid_p * fillable; abs_qty -= fillable
                            book.buy_orders[bid_p] -= fillable
                            if book.buy_orders[bid_p] <= 0:
                                del book.buy_orders[bid_p]
                        if abs_qty <= 0: break
                if not is_take and abs_qty > 0:
                    if self.rng.random() < make_fill_prob:
                        fill_qty = max(1, int(abs_qty * self.rng.uniform(0.3, 1.0)))
                        fills.append(Trade(order.symbol, order.price, fill_qty, "BOT", "SUBMISSION", 0))
                        pos -= fill_qty; pnl += order.price * fill_qty
        return fills, pos, pnl


# ---------------------------------------------------------------------------
# Bootstrap generator (UNCHANGED — block-resamples R5 CSVs)
# ---------------------------------------------------------------------------

class BootstrapGenerator:
    def __init__(self, historical_data, block_size=50, noise_scale=1.0, rng=None):
        self.data = historical_data
        self.block_size = block_size
        self.noise_scale = noise_scale
        self.rng = rng or np.random.default_rng()

    def generate_sequence(self, symbol, n_ticks):
        src = self.data.get(symbol, [])
        if not src:
            raise ValueError(f"No historical data for {symbol}")
        result = []
        remaining = n_ticks
        while remaining > 0:
            max_start = max(0, len(src) - self.block_size)
            start = int(self.rng.integers(0, max_start + 1))
            block = src[start:start + self.block_size]
            for tick in block:
                if remaining <= 0: break
                noisy = dict(tick)
                if noisy["bid_price_1"] is not None: noisy["bid_price_1"] += self.rng.normal(0, self.noise_scale)
                if noisy["ask_price_1"] is not None: noisy["ask_price_1"] += self.rng.normal(0, self.noise_scale)
                if noisy["mid_price"] is not None: noisy["mid_price"] += self.rng.normal(0, self.noise_scale)
                result.append(noisy)
                remaining -= 1
        return result

    def generate_synced_sequences(self, symbols, n_ticks):
        """Bootstrap N symbols using SHARED block start indices.

        BUG FIX: the original `generate_sequence` was called independently per
        symbol, which destroyed cross-product invariants such as the PEBBLES
        5-leg basket sum (≡ 50,000) and the SNACKPACK CHOC+VAN cointegration.
        That made the basket-arb edge invisible to the MC tool — the
        strategy's MC PnL collapsed to passive-MM noise on each leg.

        This method picks ONE block-start per block boundary and uses it for
        every symbol in `symbols`, preserving real-data cross-leg structure
        from the historical CSVs. Per-symbol noise is still applied
        independently (matches per-leg observation noise).
        """
        srcs = {s: self.data.get(s, []) for s in symbols}
        for s, src in srcs.items():
            if not src:
                raise ValueError(f"No historical data for {s}")
        # All R5 product histories have the same length (per-day CSVs were
        # zipped tick-by-tick during load). Use the shortest as safety bound.
        common_len = min(len(src) for src in srcs.values())
        max_start = max(0, common_len - self.block_size)
        results = {s: [] for s in symbols}
        remaining = n_ticks
        while remaining > 0:
            start = int(self.rng.integers(0, max_start + 1))
            take = min(self.block_size, remaining)
            for s in symbols:
                block = srcs[s][start:start + take]
                for tick in block:
                    noisy = dict(tick)
                    if noisy.get("bid_price_1") is not None:
                        noisy["bid_price_1"] += self.rng.normal(0, self.noise_scale)
                    if noisy.get("ask_price_1") is not None:
                        noisy["ask_price_1"] += self.rng.normal(0, self.noise_scale)
                    if noisy.get("mid_price") is not None:
                        noisy["mid_price"] += self.rng.normal(0, self.noise_scale)
                    results[s].append(noisy)
            remaining -= take
        return results

    def generate_order_book(self, tick, symbol):
        od = OrderDepth()
        for level in range(1, 4):
            bp = tick.get(f"bid_price_{level}"); bv = tick.get(f"bid_volume_{level}")
            if bp and bv and bp > 0 and bv > 0:
                od.buy_orders[int(round(bp))] = int(bv)
            ap = tick.get(f"ask_price_{level}"); av = tick.get(f"ask_volume_{level}")
            if ap and av and ap > 0 and av > 0:
                od.sell_orders[int(round(ap))] = -int(av)
        return od


# ---------------------------------------------------------------------------
# NEW: NoiseTraderSimulator — replaces R3/R4 NamedTraderSimulator
# ---------------------------------------------------------------------------
# In R5 there are NO trader IDs (wiki: "self.buyer and self.seller will only
# be non-empty strings if the algorithm itself is the buyer/seller"), and
# Phase B confirmed 0/35,385 trades carry names. There are NO statistically
# significant participant outliers to model. Therefore named-trader injection
# is removed.
#
# We retain a generic anonymous noise-trader that injects market_trades at
# the empirical per-product trade arrival rate. Trade aggressor direction
# is sampled with uniform 50/50 (the "no informed flow" null hypothesis).
# An optional INFORMED_FLOW mode injects directional flow correlated with
# the next-tick mid move — used by the no_insider stress scenario as the
# "control" against which the strategy is tested.

class NoiseTraderSimulator:  # NEW
    def __init__(self, rng: np.random.Generator, informed_flow: bool = False):
        self.rng = rng
        self.informed_flow = informed_flow

    def generate_trades(self, model: ProductModel, mid: float, next_mid: float,
                         timestamp: int) -> List[Trade]:
        if self.rng.random() > model.trade_prob:
            return []
        size = max(1, int(round(self.rng.normal(model.trade_size_mean, model.trade_size_std))))
        if self.informed_flow:
            # Aggressor direction biased toward next-tick movement (60/40)
            up = (next_mid > mid)
            biased = self.rng.random() < 0.60
            buyer_aggressor = up if biased else (self.rng.random() < 0.5)
        else:
            buyer_aggressor = (self.rng.random() < 0.5)
        spread_offset = int(round(model.spread_mean * 0.5))
        price = int(round(mid)) + (spread_offset if buyer_aggressor else -spread_offset)
        return [Trade(symbol=model.symbol, price=price, quantity=size,
                      buyer="", seller="", timestamp=timestamp)]


# ---------------------------------------------------------------------------
# NEW: CrowdedTradeAgent — second-team competitor for the CROWDED_TRADE stress
# ---------------------------------------------------------------------------
# Implements a crude version of the user's primary strategy as a separate
# market participant whose orders compete for the same fills. Drains liquidity
# at the same price levels, reducing our fill rate.

class CrowdedTradeAgent:  # NEW
    """Lightweight competitor that quotes the same price level as our trader.
    Effect: each tick, with probability `crowd_share`, half of our intended
    passive fill is captured by the competitor (modelled by halving make_fill_prob).
    """
    def __init__(self, strategy: str, crowd_share: float = 0.5):
        self.strategy = strategy
        self.crowd_share = crowd_share

    def affected_products(self) -> Set[str]:
        if self.strategy == "P2":
            return set(R5_GROUPS["PEBBLES"])
        if self.strategy == "S2":
            return set(R5_GROUPS["SNACKPACK"])
        if self.strategy == "S1":
            return {"SNACKPACK_CHOCOLATE", "SNACKPACK_VANILLA"}
        if self.strategy == "M1":
            # Wide-spread MM target list
            return (set(R5_GROUPS["GALAXY_SOUNDS"]) | set(R5_GROUPS["UV_VISOR"])
                    | set(R5_GROUPS["OXYGEN_SHAKE"]) | set(R5_GROUPS["PANEL"]))
        if self.strategy == "all":
            return set(R5_ALL_PRODUCTS)
        return set()


# ---------------------------------------------------------------------------
# Stress scenarios (MODIFIED: R3/R4 HGP/VFE-specific scenarios removed;
# user-spec R5 scenarios added)
# ---------------------------------------------------------------------------

@dataclass
class StressScenario:
    name: str
    spread_multiplier: float = 1.0
    vol_multiplier: float = 1.0
    drift_override: Optional[float] = None
    fill_rate_multiplier: float = 1.0
    liquidity_multiplier: float = 1.0
    empty_book_prob: float = 0.03
    # NEW R5 fields
    regime_shift: bool = False               # NEW: 2x vol jump at random tick
    no_insider: bool = False                 # NEW: disable informed flow agent
    crowded_strategy: Optional[str] = None   # NEW: name of competing strategy
    crowded_share: float = 0.5               # NEW: fraction of fills lost
    limit_stress: bool = False               # NEW: pre-load positions to ±limit
    correlation_break: bool = False          # NEW: zero out PEBBLES/SNACKPACK constraints


STRESS_SCENARIOS: Dict[str, StressScenario] = {
    "baseline": StressScenario(name="baseline"),
    # R5-generic stresses
    "wide_spread": StressScenario(name="wide_spread", spread_multiplier=1.5),
    "narrow_spread": StressScenario(name="narrow_spread", spread_multiplier=0.7),
    "high_vol": StressScenario(name="high_vol", vol_multiplier=2.0),
    "low_vol": StressScenario(name="low_vol", vol_multiplier=0.5),
    "thin_liquidity": StressScenario(name="thin_liquidity",
                                      liquidity_multiplier=0.4, fill_rate_multiplier=0.5),
    "low_fill": StressScenario(name="low_fill", fill_rate_multiplier=0.3),
    "platform_like": StressScenario(name="platform_like", spread_multiplier=1.2,
                                     fill_rate_multiplier=0.5, liquidity_multiplier=0.8),
    # NEW: Five user-spec R5 scenarios
    "regime_shift": StressScenario(name="regime_shift", regime_shift=True,
                                    vol_multiplier=2.0),
    "no_insider": StressScenario(name="no_insider", no_insider=True),
    "crowded_trade": StressScenario(name="crowded_trade", crowded_strategy="P2",
                                     crowded_share=0.5),
    "crowded_S2": StressScenario(name="crowded_S2", crowded_strategy="S2", crowded_share=0.5),
    "crowded_M1": StressScenario(name="crowded_M1", crowded_strategy="M1", crowded_share=0.5),
    "limit_stress": StressScenario(name="limit_stress", limit_stress=True),
    "correlation_break": StressScenario(name="correlation_break", correlation_break=True),
    # Combined worst-case
    "full_stress": StressScenario(name="full_stress", spread_multiplier=1.5,
                                   vol_multiplier=2.0, fill_rate_multiplier=0.4,
                                   liquidity_multiplier=0.6, regime_shift=True,
                                   crowded_strategy="all", crowded_share=0.4),
}


def apply_stress(model: ProductModel, scenario: StressScenario) -> ProductModel:
    import copy
    m = copy.deepcopy(model)
    m.spread_mean *= scenario.spread_multiplier
    m.spread_std *= scenario.spread_multiplier
    m.sigma *= scenario.vol_multiplier
    m.vol_mean *= scenario.liquidity_multiplier
    m.vol_std *= scenario.liquidity_multiplier
    m.make_fill_prob *= scenario.fill_rate_multiplier
    if scenario.drift_override is not None:
        m.drift = scenario.drift_override
    # NEW: crowded trade halves make_fill_prob on affected products
    if scenario.crowded_strategy is not None:
        agent = CrowdedTradeAgent(scenario.crowded_strategy, scenario.crowded_share)
        if m.symbol in agent.affected_products():
            m.make_fill_prob *= (1.0 - scenario.crowded_share)
    return m


# ---------------------------------------------------------------------------
# Simulation engine (MODIFIED: R5 product set; PEBBLES/SNACKPACK constraints;
# regime_shift mid-sim; correlation_break; limit_stress preload; per-strategy
# attribution; shadow benchmark)
# ---------------------------------------------------------------------------

@dataclass
class SimResult:
    total_pnl: float = 0.0
    pnl_by_product: Dict[str, float] = field(default_factory=dict)
    pnl_by_group: Dict[str, float] = field(default_factory=dict)        # NEW
    pnl_by_strategy: Dict[str, float] = field(default_factory=dict)     # NEW
    pnl_curve: List[float] = field(default_factory=list)
    max_drawdown: float = 0.0
    drawdown_duration: int = 0                                          # NEW
    sharpe: float = 0.0
    n_fills: int = 0
    fills_by_product: Dict[str, int] = field(default_factory=dict)
    max_position: Dict[str, int] = field(default_factory=dict)
    avg_position: Dict[str, float] = field(default_factory=dict)
    final_positions: Dict[str, int] = field(default_factory=dict)
    terminal_pnl: float = 0.0
    limit_breach_count: int = 0                                         # NEW
    shadow_pnl: float = 0.0                                             # NEW: passive mid follower

# NEW: product → strategy mapping for attribution.
# This is the canonical mapping derived from Step 3 final portfolio.
def _strategy_of(symbol: str) -> str:
    g = R5_GROUP_OF.get(symbol, "")
    if g == "PEBBLES":
        return "P2"  # PEBBLES synthetic-fair MM (anomaly tier)
    if symbol in ("SNACKPACK_CHOCOLATE", "SNACKPACK_VANILLA"):
        return "S1+S2"  # CHOC+VAN pair stat-arb + MM overlap
    if g == "SNACKPACK":
        return "S2"  # wide-spread MM on remaining 3 SNACKPACK legs
    if symbol in ("ROBOT_DISHES", "ROBOT_IRONING"):
        return "R2"  # tick-fade MM (CONDITIONAL on bounce-stripped ACF test)
    if g in ("GALAXY_SOUNDS", "UV_VISOR", "OXYGEN_SHAKE", "PANEL"):
        return "M1"  # wide-deep baseline MM
    if g in ("MICROCHIP", "ROBOT", "SLEEP_POD", "TRANSLATOR"):
        return "M3"  # thin-book tight MM (likely partly excluded by X5)
    return "OTHER"


class SimulationEngine:
    def __init__(self, trader_class, models, n_ticks=10000, seed=None,
                 scenario=None, bootstrap_gen=None, mode="parametric",
                 enable_noise_traders=True,                     # MODIFIED rename
                 informed_flow_default=True):                   # NEW
        self.trader_class = trader_class
        self.base_models = models
        self.n_ticks = n_ticks
        self.seed = seed
        self.scenario = scenario or STRESS_SCENARIOS["baseline"]
        self.bootstrap_gen = bootstrap_gen
        self.mode = mode
        self.enable_noise_traders = enable_noise_traders
        self.informed_flow_default = informed_flow_default

    def run(self, sim_seed: int) -> SimResult:
        rng = np.random.default_rng(sim_seed)
        fill_engine = FillEngine(rng)
        models = [apply_stress(m, self.scenario) for m in self.base_models]
        generators = {m.symbol: MarketGenerator(m, rng) for m in models}
        # NEW: noise-trader subsystem (replaces named-trader subsystem)
        noise_trader: Optional[NoiseTraderSimulator] = None
        if self.enable_noise_traders:
            informed = self.informed_flow_default and not self.scenario.no_insider  # NEW
            noise_trader = NoiseTraderSimulator(rng, informed_flow=informed)

        bootstrap_sequences: Dict[str, List[dict]] = {}
        if self.mode == "bootstrap" and self.bootstrap_gen is not None:
            self.bootstrap_gen.rng = rng
            # FIX: bootstrap PEBBLES legs together so the basket sum constraint
            # (5 mids ≡ 50,000) is preserved from real history. Same for
            # SNACKPACK CHOC+VAN cointegration. Without this, independent
            # block sampling destroys cross-product structure and the
            # basket-arb edge becomes invisible to MC.
            synced_groups: List[List[str]] = []
            try:
                peb = [s for s in R5_GROUPS["PEBBLES"] if s in self.bootstrap_gen.data]
                if len(peb) >= 2:
                    synced_groups.append(peb)
            except Exception:
                pass
            if not self.scenario.correlation_break:
                # All 5 SNACKPACK legs share a tight 5-leg sum constraint
                # (sum ≈ 50,221, rel_std=0.377% in R5 history). Sync all 5
                # rather than only CHOC+VAN to preserve the full structure
                # (any pair/triple cointegration is implied by the joint sync).
                snack = [s for s in R5_GROUPS["SNACKPACK"]
                         if s in self.bootstrap_gen.data]
                if len(snack) >= 2:
                    synced_groups.append(snack)
            # Skip PEBBLES sync entirely under correlation_break (the scenario
            # is meant to model the basket constraint failing).
            if self.scenario.correlation_break:
                synced_groups = [g for g in synced_groups
                                 if not any(s.startswith("PEBBLES_") or s.startswith("SNACKPACK_")
                                            for s in g)]
            already: set = set()
            for group in synced_groups:
                try:
                    seqs = self.bootstrap_gen.generate_synced_sequences(
                        group, self.n_ticks)
                    for s, ticks in seqs.items():
                        bootstrap_sequences[s] = ticks
                        already.add(s)
                except ValueError:
                    pass
            for m in models:
                if m.symbol in already:
                    continue
                try:
                    bootstrap_sequences[m.symbol] = self.bootstrap_gen.generate_sequence(
                        m.symbol, self.n_ticks)
                except ValueError:
                    pass

        trader = self.trader_class()
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            return self._run_inner(trader, models, generators, fill_engine, rng,
                                    bootstrap_sequences, noise_trader)
        finally:
            sys.stdout = old_stdout

    # NEW: parametric mid generation with PEBBLES/SNACKPACK constraints
    def _generate_parametric_mids(self, models, generators) -> Dict[str, np.ndarray]:
        n = self.n_ticks
        seqs: Dict[str, np.ndarray] = {}

        # Pass 1: independent OU sequences for each product
        for m in models:
            gen = generators[m.symbol]
            gen.reset()
            arr = np.empty(n)
            for t in range(n):
                arr[t] = gen.step()
            seqs[m.symbol] = arr

        # NEW: enforce PEBBLES basket sum constraint (skip if correlation_break)
        if (not self.scenario.correlation_break
                and all(s in seqs for s in R5_GROUPS["PEBBLES"])):
            peb = R5_GROUPS["PEBBLES"]
            stack = np.column_stack([seqs[s] for s in peb])  # (n, 5)
            cur_sum = stack.sum(axis=1)
            # Force sum to target plus small noise (matches empirical std=2.8)
            rng_b = np.random.default_rng(self.seed or 0)
            target = R5_PEBBLES_BASKET_SUM + rng_b.normal(
                0.0, R5_PEBBLES_BASKET_NOISE_STD, size=n)
            adjustment = (target - cur_sum) / 5.0  # distribute equally
            for s in peb:
                seqs[s] = seqs[s] + adjustment

        # NEW: enforce SNACKPACK CHOC+VAN soft cointegration
        if (not self.scenario.correlation_break
                and "SNACKPACK_CHOCOLATE" in seqs and "SNACKPACK_VANILLA" in seqs):
            choc = seqs["SNACKPACK_CHOCOLATE"]
            van = seqs["SNACKPACK_VANILLA"]
            cur = choc + van
            rng_c = np.random.default_rng((self.seed or 0) + 1)
            # Daily drift + intraday noise
            target = (R5_SNACKPACK_CHOCVAN_TARGET
                      + rng_c.normal(0.0, R5_SNACKPACK_CHOCVAN_DAILY_DRIFT_STD)
                      + rng_c.normal(0.0, R5_SNACKPACK_CHOCVAN_STD * 0.5, size=n))
            adj = (target - cur) / 2.0
            seqs["SNACKPACK_CHOCOLATE"] = choc + adj
            seqs["SNACKPACK_VANILLA"] = van + adj

        # NEW: regime_shift — at random tick, double sigma for remainder
        if self.scenario.regime_shift:
            rng_r = np.random.default_rng((self.seed or 0) + 2)
            shift_t = int(rng_r.integers(n // 4, 3 * n // 4))
            for sym, arr in seqs.items():
                # Re-inflate post-shift returns by sqrt(2) factor
                base = arr[shift_t]
                rets = np.diff(arr[shift_t:])
                seqs[sym][shift_t+1:] = base + np.cumsum(rets * math.sqrt(2.0))

        return seqs

    def _run_inner(self, trader, models, generators, fill_engine, rng,
                    bootstrap_sequences, noise_trader):
        result = SimResult()
        result.pnl_by_product = {m.symbol: 0.0 for m in models}
        result.pnl_by_group = defaultdict(float)         # NEW
        result.pnl_by_strategy = defaultdict(float)      # NEW
        result.fills_by_product = {m.symbol: 0 for m in models}
        result.max_position = {m.symbol: 0 for m in models}
        result.avg_position = {m.symbol: 0.0 for m in models}

        positions: Dict[str, int] = {m.symbol: 0 for m in models}
        cash_pnl: Dict[str, float] = {m.symbol: 0.0 for m in models}
        trader_data = ""
        cumulative_pnl = 0.0
        peak_pnl = 0.0
        peak_tick = 0                                    # NEW
        max_dd = 0.0
        max_dd_duration = 0                              # NEW
        tick_pnls: List[float] = []
        position_sums: Dict[str, float] = {m.symbol: 0.0 for m in models}
        last_mids: Dict[str, float] = {}
        first_mids: Dict[str, float] = {}                # NEW: shadow benchmark

        # NEW: limit_stress — preload positions to ±limit to test recovery
        if self.scenario.limit_stress:
            for m in models:
                # Alternate sign by hash so half are +limit, half -limit
                sign = 1 if (hash(m.symbol) % 2 == 0) else -1
                positions[m.symbol] = sign * m.position_limit

        # Generate parametric mid sequences (with constraints) up front
        mid_sequences: Dict[str, np.ndarray] = {}
        if self.mode == "parametric":
            mid_sequences = self._generate_parametric_mids(models, generators)

        listings = {m.symbol: Listing(m.symbol, m.symbol, "XIRECS") for m in models}

        for tick_idx in range(self.n_ticks):
            timestamp = tick_idx * 100
            order_depths: Dict[str, OrderDepth] = {}
            market_trades: Dict[str, List[Trade]] = {}

            for m in models:
                sym = m.symbol
                gen = generators[sym]
                if self.mode == "bootstrap" and sym in bootstrap_sequences:
                    tick_data = bootstrap_sequences[sym][tick_idx]
                    od = self.bootstrap_gen.generate_order_book(tick_data, sym) if self.bootstrap_gen else OrderDepth()
                    mid = tick_data.get("mid_price", m.fair_value) or m.fair_value
                else:
                    mid = float(mid_sequences[sym][tick_idx])
                    od = gen.generate_order_book(mid)
                order_depths[sym] = od
                last_mids[sym] = mid
                if sym not in first_mids:
                    first_mids[sym] = mid                # NEW

                if noise_trader is not None:
                    # next-mid for informed flow signal
                    if self.mode == "parametric" and tick_idx + 1 < self.n_ticks:
                        next_mid = float(mid_sequences[sym][tick_idx + 1])
                    else:
                        next_mid = mid
                    nt = noise_trader.generate_trades(m, mid, next_mid, timestamp)
                    if nt:
                        market_trades[sym] = nt

            own_trades: Dict[str, List[Trade]] = {}
            state = TradingState(traderData=trader_data, timestamp=timestamp,
                                  listings=listings, order_depths=order_depths,
                                  own_trades=own_trades, market_trades=market_trades,
                                  position=dict(positions), observations=Observation())
            try:
                all_orders, conversions, trader_data = trader.run(state)
            except Exception:
                all_orders, conversions, trader_data = {}, 0, trader_data

            for m in models:
                sym = m.symbol
                orders = all_orders.get(sym, [])
                if not orders: continue
                book_copy = OrderDepth()
                book_copy.buy_orders = order_depths[sym].buy_orders.copy()
                book_copy.sell_orders = order_depths[sym].sell_orders.copy()
                fills, new_pos, delta_pnl = fill_engine.match_orders(
                    orders, book_copy, positions[sym], m.position_limit, m.make_fill_prob)
                positions[sym] = new_pos
                cash_pnl[sym] += delta_pnl
                result.fills_by_product[sym] += len(fills)
                result.n_fills += len(fills)
                abs_pos = abs(positions[sym])
                if abs_pos > result.max_position[sym]:
                    result.max_position[sym] = abs_pos
                position_sums[sym] += abs_pos

            mtm_pnl = sum(cash_pnl[m.symbol] + positions[m.symbol] * last_mids[m.symbol]
                           for m in models)
            tick_pnls.append(mtm_pnl - cumulative_pnl if tick_idx > 0 else mtm_pnl)
            cumulative_pnl = mtm_pnl
            result.pnl_curve.append(cumulative_pnl)
            if cumulative_pnl > peak_pnl:
                peak_pnl = cumulative_pnl
                peak_tick = tick_idx
            dd = peak_pnl - cumulative_pnl
            if dd > max_dd:
                max_dd = dd
                max_dd_duration = tick_idx - peak_tick   # NEW

        # Final stats
        result.total_pnl = cumulative_pnl
        result.terminal_pnl = cumulative_pnl
        result.max_drawdown = max_dd
        result.drawdown_duration = max_dd_duration       # NEW
        result.final_positions = dict(positions)
        result.limit_breach_count = fill_engine.limit_breach_count  # NEW

        for m in models:
            sym = m.symbol
            prod_pnl = cash_pnl[sym] + positions[sym] * last_mids[sym]
            result.pnl_by_product[sym] = prod_pnl
            result.avg_position[sym] = position_sums[sym] / max(1, self.n_ticks)
            result.pnl_by_group[R5_GROUP_OF.get(sym, "OTHER")] += prod_pnl  # NEW
            result.pnl_by_strategy[_strategy_of(sym)] += prod_pnl           # NEW

        # NEW: shadow benchmark — passive mid follower with constant +1 lot
        # per product (capped at limit). Captures pure beta. Useful as floor.
        shadow = 0.0
        for m in models:
            sym = m.symbol
            if sym in first_mids and sym in last_mids:
                shadow += last_mids[sym] - first_mids[sym]  # 1 unit long whole sim
        result.shadow_pnl = shadow

        if len(tick_pnls) > 1:
            arr = np.array(tick_pnls)
            mean_ret = float(np.mean(arr)); std_ret = float(np.std(arr))
            if std_ret > 0:
                result.sharpe = (mean_ret / std_ret) * math.sqrt(len(tick_pnls))

        # Convert defaultdicts to regular dicts so they can be pickled cleanly
        result.pnl_by_group = dict(result.pnl_by_group)
        result.pnl_by_strategy = dict(result.pnl_by_strategy)
        return result


# ---------------------------------------------------------------------------
# Monte Carlo runner (UNCHANGED)
# ---------------------------------------------------------------------------

@dataclass
class MonteCarloResult:
    n_sims: int
    results: List[SimResult]
    pnl_mean: float = 0.0
    pnl_std: float = 0.0
    pnl_median: float = 0.0
    pnl_p5: float = 0.0
    pnl_p25: float = 0.0
    pnl_p75: float = 0.0
    pnl_p95: float = 0.0
    max_drawdown_mean: float = 0.0
    max_drawdown_p95: float = 0.0
    drawdown_duration_mean: float = 0.0     # NEW
    sharpe_mean: float = 0.0
    sharpe_std: float = 0.0
    win_rate: float = 0.0
    avg_fills: float = 0.0
    limit_breach_total: int = 0             # NEW
    shadow_pnl_mean: float = 0.0            # NEW
    scenario_name: str = "baseline"

    def compute(self):
        pnls = np.array([r.total_pnl for r in self.results])
        dds = np.array([r.max_drawdown for r in self.results])
        sharpes = np.array([r.sharpe for r in self.results])
        fills = np.array([r.n_fills for r in self.results])
        durs = np.array([r.drawdown_duration for r in self.results])  # NEW
        breaches = np.array([r.limit_breach_count for r in self.results])  # NEW
        shadows = np.array([r.shadow_pnl for r in self.results])  # NEW
        self.pnl_mean = float(np.mean(pnls)); self.pnl_std = float(np.std(pnls))
        self.pnl_median = float(np.median(pnls))
        self.pnl_p5 = float(np.percentile(pnls, 5))
        self.pnl_p25 = float(np.percentile(pnls, 25))
        self.pnl_p75 = float(np.percentile(pnls, 75))
        self.pnl_p95 = float(np.percentile(pnls, 95))
        self.max_drawdown_mean = float(np.mean(dds))
        self.max_drawdown_p95 = float(np.percentile(dds, 95))
        self.drawdown_duration_mean = float(np.mean(durs))     # NEW
        self.sharpe_mean = float(np.mean(sharpes)); self.sharpe_std = float(np.std(sharpes))
        self.win_rate = float(np.mean(pnls > 0))
        self.avg_fills = float(np.mean(fills))
        self.limit_breach_total = int(np.sum(breaches))         # NEW
        self.shadow_pnl_mean = float(np.mean(shadows))          # NEW


_worker_engine: Optional[SimulationEngine] = None
def _init_worker(trader_path, models, n_ticks, scenario, mode,
                 enable_noise_traders=True, informed_flow_default=True):
    global _worker_engine
    TraderClass = load_trader(trader_path)
    _worker_engine = SimulationEngine(trader_class=TraderClass, models=models,
        n_ticks=n_ticks, scenario=scenario, mode=mode,
        enable_noise_traders=enable_noise_traders,
        informed_flow_default=informed_flow_default)

def _run_one_sim(sim_seed):
    assert _worker_engine is not None
    return _worker_engine.run(sim_seed)


def run_montecarlo(trader_class, models, n_sims=200, n_ticks=10000, base_seed=42,
                    scenario=None, bootstrap_gen=None, mode="parametric",
                    progress=True, workers=1, trader_path="",
                    enable_noise_traders=True,
                    informed_flow_default=True) -> MonteCarloResult:
    scenario = scenario or STRESS_SCENARIOS["baseline"]
    sim_seeds = [base_seed + i * 7919 for i in range(n_sims)]
    t0 = time.time()
    if workers > 1 and mode == "parametric":
        sys.stderr.write(f"  Using {workers} worker processes\n"); sys.stderr.flush()
        with multiprocessing.Pool(processes=workers, initializer=_init_worker,
                initargs=(trader_path, models, n_ticks, scenario, mode,
                           enable_noise_traders, informed_flow_default)) as pool:
            results = []
            for i, res in enumerate(pool.imap_unordered(_run_one_sim, sim_seeds)):
                results.append(res)
                if progress and (i + 1) % max(1, n_sims // 20) == 0:
                    elapsed = time.time() - t0; rate = (i + 1) / elapsed
                    eta = (n_sims - i - 1) / rate if rate > 0 else 0
                    sys.stderr.write(f"\r  [{i+1}/{n_sims}] mean={np.mean([r.total_pnl for r in results]):,.0f} ETA {eta:.0f}s")
                    sys.stderr.flush()
    else:
        engine = SimulationEngine(trader_class=trader_class, models=models,
            n_ticks=n_ticks, scenario=scenario, bootstrap_gen=bootstrap_gen,
            mode=mode, enable_noise_traders=enable_noise_traders,
            informed_flow_default=informed_flow_default)
        results = []
        for i in range(n_sims):
            res = engine.run(sim_seeds[i]); results.append(res)
            if progress and (i + 1) % max(1, n_sims // 20) == 0:
                elapsed = time.time() - t0; rate = (i + 1) / elapsed
                eta = (n_sims - i - 1) / rate if rate > 0 else 0
                sys.stderr.write(f"\r  [{i+1}/{n_sims}] mean={np.mean([r.total_pnl for r in results]):,.0f} ETA {eta:.0f}s")
                sys.stderr.flush()
    if progress:
        sys.stderr.write("\n"); sys.stderr.flush()
    mc = MonteCarloResult(n_sims=n_sims, results=results, scenario_name=scenario.name)
    mc.compute()
    return mc


# ---------------------------------------------------------------------------
# Reporting (MODIFIED: per-strategy attribution + shadow benchmark + breach)
# ---------------------------------------------------------------------------

def print_report(mc: MonteCarloResult, header: str = ""):
    print("\n" + "=" * 78)
    if header:
        print(f"  {header}")
    print(f"  Scenario: {mc.scenario_name}  |  Sims: {mc.n_sims}")
    print("=" * 78)
    print(f"  {'PnL Mean':>22}: {mc.pnl_mean:>14,.1f}")
    print(f"  {'PnL Std':>22}: {mc.pnl_std:>14,.1f}")
    print(f"  {'PnL Median':>22}: {mc.pnl_median:>14,.1f}")
    print(f"  {'VaR 95% (P5)':>22}: {mc.pnl_p5:>14,.1f}")
    print(f"  {'P25 / P75':>22}: {mc.pnl_p25:>7,.0f} / {mc.pnl_p75:>7,.0f}")
    print(f"  {'P95':>22}: {mc.pnl_p95:>14,.1f}")
    print(f"  {'Win Rate':>22}: {mc.win_rate:>13.1%}")
    print(f"  {'Sharpe (mean / std)':>22}: {mc.sharpe_mean:>7.2f} / {mc.sharpe_std:>4.2f}")
    print(f"  {'MaxDD (mean / P95)':>22}: {mc.max_drawdown_mean:>7,.0f} / {mc.max_drawdown_p95:>5,.0f}")
    print(f"  {'DD duration (mean)':>22}: {mc.drawdown_duration_mean:>14,.0f} ticks")  # NEW
    print(f"  {'Avg Fills':>22}: {mc.avg_fills:>14,.0f}")
    print(f"  {'Limit Breach Total':>22}: {mc.limit_breach_total:>14,d}"           # NEW
          f"   {'(MUST be 0 in prod)' if mc.limit_breach_total > 0 else 'OK'}")
    print(f"  {'Shadow PnL (passive)':>22}: {mc.shadow_pnl_mean:>14,.1f}"          # NEW
          f"   vs Strategy: {mc.pnl_mean - mc.shadow_pnl_mean:+,.0f}")

    if mc.results:
        # NEW: per-strategy breakdown
        print("\n  --- Per-strategy attribution ---")
        strat_keys: Set[str] = set()
        for r in mc.results:
            strat_keys.update(r.pnl_by_strategy.keys())
        for k in sorted(strat_keys):
            vals = [r.pnl_by_strategy.get(k, 0.0) for r in mc.results]
            print(f"    {k:>10}: mean={np.mean(vals):>10,.0f}  "
                  f"std={np.std(vals):>9,.0f}  "
                  f"p5={np.percentile(vals,5):>10,.0f}  "
                  f"p95={np.percentile(vals,95):>10,.0f}")

        # NEW: per-group breakdown
        print("\n  --- Per-group PnL ---")
        group_keys: Set[str] = set()
        for r in mc.results:
            group_keys.update(r.pnl_by_group.keys())
        for k in sorted(group_keys):
            vals = [r.pnl_by_group.get(k, 0.0) for r in mc.results]
            print(f"    {k:>16}: mean={np.mean(vals):>10,.0f}  "
                  f"p5={np.percentile(vals,5):>10,.0f}  "
                  f"p95={np.percentile(vals,95):>10,.0f}")
    print("=" * 78)


def print_sweep_report(sweep_results, param_name):
    print(f"\n{'='*72}")
    print(f"  PARAMETER SWEEP: {param_name}")
    print(f"{'='*72}")
    print(f"  {'Value':>10} {'Mean PnL':>12} {'Std':>10} {'VaR95':>10} "
          f"{'Sharpe':>8} {'WinRate':>8} {'Fills':>8}")
    print(f"  {'-'*10} {'-'*12} {'-'*10} {'-'*10} {'-'*8} {'-'*8} {'-'*8}")
    for val, mc in sweep_results:
        print(f"  {val:>10.4f} {mc.pnl_mean:>12,.0f} {mc.pnl_std:>10,.0f} "
              f"{mc.pnl_p5:>10,.0f} {mc.sharpe_mean:>8.2f} "
              f"{mc.win_rate:>7.1%} {mc.avg_fills:>8.0f}")
    print(f"{'='*72}")


# ---------------------------------------------------------------------------
# Parameter sweep (UNCHANGED)
# ---------------------------------------------------------------------------

def parameter_sweep(trader_module_path, param_name, param_values, models,
                     n_sims=50, n_ticks=5000, scenario=None):
    import importlib.util, re, tempfile
    scenario = scenario or STRESS_SCENARIOS["baseline"]
    source_path = Path(trader_module_path)
    original_source = source_path.read_text(encoding="utf-8")
    sweep_results = []
    for val in param_values:
        patched = re.sub(rf"({re.escape(param_name)}\s*[=:]\s*)[\d.]+",
                          rf"\g<1>{val}", original_source)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as tmp:
            tmp.write(patched); tmp_path = tmp.name
        try:
            spec = importlib.util.spec_from_file_location("trader_tmp", tmp_path)
            mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
            trader_cls = mod.Trader
            sys.stderr.write(f"\n--- {param_name} = {val} ---\n")
            mc = run_montecarlo(trader_cls, models, n_sims=n_sims, n_ticks=n_ticks,
                                 scenario=scenario, progress=True)
            sweep_results.append((val, mc))
        except Exception as e:
            sys.stderr.write(f"  ERROR at {param_name}={val}: {e}\n")
        finally:
            os.unlink(tmp_path)
    return sweep_results


# ---------------------------------------------------------------------------
# Data discovery (MODIFIED: prioritises round_data/ROUND_5)
# ---------------------------------------------------------------------------

def find_r5_data_files(workspace_root: str) -> Dict[int, str]:  # NEW
    """Find R5 prices CSVs by day. Returns {day: filepath}."""
    candidates = [
        os.path.join(workspace_root, "round_data", "ROUND_5"),
        os.path.join(workspace_root, "round_data", "round_5"),
    ]
    found: Dict[int, str] = {}
    for cdir in candidates:
        if not os.path.isdir(cdir): continue
        for f in os.listdir(cdir):
            if f.startswith("prices_round_5_day_") and f.endswith(".csv"):
                try:
                    day = int(f.replace(".csv", "").split("_")[-1])
                    found[day] = os.path.join(cdir, f)
                except (IndexError, ValueError):
                    pass
    return found


def load_r5_historical(workspace_root: str) -> Dict[str, List[dict]]:  # NEW
    files = find_r5_data_files(workspace_root)
    merged: Dict[str, List[dict]] = defaultdict(list)
    for day in sorted(files.keys()):
        try:
            products = load_prices_csv(files[day])
            for sym, ticks in products.items():
                merged[sym].extend(ticks)
        except Exception as e:
            sys.stderr.write(f"Warning: failed to load {files[day]}: {e}\n")
    return dict(merged)


# ---------------------------------------------------------------------------
# Trader loader (UNCHANGED)
# ---------------------------------------------------------------------------

def load_trader(trader_path: str):
    import importlib.util
    spec = importlib.util.spec_from_file_location("submission_module", trader_path)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod.Trader


# ---------------------------------------------------------------------------
# NEW: build R5 product models from empirical data
# ---------------------------------------------------------------------------

def build_r5_models(historical: Dict[str, List[dict]]) -> List[ProductModel]:
    """Construct ProductModels for all 50 R5 products, calibrated from R5 data."""
    models: List[ProductModel] = []
    for sym in R5_ALL_PRODUCTS:
        ticks = historical.get(sym, [])
        if len(ticks) < 100:
            sys.stderr.write(f"  WARNING: no historical data for {sym}, using fallback\n")
            m = ProductModel(symbol=sym, product_type="random_walk",
                              fair_value=10000.0, position_limit=R5_POSITION_LIMIT,
                              kappa=0.0, mu=10000.0, sigma=10.0,
                              spread_mean=10.0, spread_std=2.0,
                              vol_mean=20.0, vol_std=5.0,
                              group=R5_GROUP_OF.get(sym, ""))
        else:
            stats = extract_stats(ticks, sym)
            # Random_walk for all R5 products (Hurst≈0.5 in data); the
            # PEBBLES/SNACKPACK constraints are enforced post-hoc.
            m = ProductModel.from_stats(stats, position_limit=R5_POSITION_LIMIT,
                                          product_type="random_walk")
        models.append(m)
    return models


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="IMC Prosperity 4 — Round 5 Monte Carlo Simulator")
    parser.add_argument("--trader", type=str, default="submission.py",
                         help="Path to trader .py (default: submission.py)")
    parser.add_argument("--sims", type=int, default=200)
    parser.add_argument("--ticks", type=int, default=10000,
                         help="Ticks per simulation (10000 = full backtester day)")
    parser.add_argument("--mode", choices=["parametric", "bootstrap"], default="bootstrap",
                         help="Default: bootstrap (replays R5 ticks); parametric is OU+constraints")
    parser.add_argument("--stress", type=str, default=None,
                         help=f"Scenario: {', '.join(STRESS_SCENARIOS.keys())}")
    parser.add_argument("--stress-all", action="store_true")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--sweep", nargs=4, metavar=("PARAM","MIN","MAX","N"))
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--workers", "-j", type=int, default=1)
    parser.add_argument("--no-noise-traders", action="store_true",
                         help="Disable anonymous noise-trader market_trade injection")
    parser.add_argument("--no-informed", action="store_true",
                         help="Force no_insider mode (uniform aggressor direction)")
    parser.add_argument("--strategy", type=str, default=None,
                         help="Override crowded-trade competitor strategy (P2|S2|S1|M1|all)")
    args = parser.parse_args()

    workspace = os.path.dirname(os.path.abspath(__file__))
    trader_path = os.path.join(workspace, args.trader) if not os.path.isabs(args.trader) else args.trader

    sys.stderr.write(f"Loading trader from {trader_path}...\n")
    TraderClass = load_trader(trader_path)

    # Load R5 historical data and build models
    sys.stderr.write("Loading R5 historical data...\n")
    historical = load_r5_historical(workspace)
    if not historical:
        sys.stderr.write("ERROR: no R5 data found in round_data/ROUND_5/\n")
        return
    sys.stderr.write(f"  Loaded {len(historical)} products from R5 data\n")
    models = build_r5_models(historical)
    sys.stderr.write(f"  Built {len(models)} product models (limit={R5_POSITION_LIMIT} each)\n")

    # Bootstrap generator (R5 default mode)
    bootstrap_gen = BootstrapGenerator(historical, block_size=50, noise_scale=0.5)

    # Stress override for crowded-trade strategy choice
    if args.strategy and args.stress and "crowded" in args.stress:
        STRESS_SCENARIOS[args.stress].crowded_strategy = args.strategy

    informed_flow_default = not args.no_informed
    enable_noise_traders = not args.no_noise_traders

    # Sweep mode
    if args.sweep:
        param_name = args.sweep[0]
        pv = list(np.linspace(float(args.sweep[1]), float(args.sweep[2]), int(args.sweep[3])))
        scen = STRESS_SCENARIOS.get(args.stress, STRESS_SCENARIOS["baseline"])
        sweep_results = parameter_sweep(trader_path, param_name, pv, models,
                                          n_sims=min(50, args.sims),
                                          n_ticks=min(5000, args.ticks), scenario=scen)
        print_sweep_report(sweep_results, param_name)
        return

    # Stress-all
    if args.stress_all:
        for sn, sc in STRESS_SCENARIOS.items():
            sys.stderr.write(f"\n>>> Scenario: {sn}\n")
            mc = run_montecarlo(TraderClass, models, n_sims=args.sims, n_ticks=args.ticks,
                                 base_seed=args.seed, scenario=sc, bootstrap_gen=bootstrap_gen,
                                 mode=args.mode, progress=not args.quiet, workers=args.workers,
                                 trader_path=trader_path,
                                 enable_noise_traders=enable_noise_traders,
                                 informed_flow_default=informed_flow_default)
            print_report(mc, f"R5 MONTE CARLO — {sn.upper()}")
        return

    scenario = STRESS_SCENARIOS.get(args.stress, STRESS_SCENARIOS["baseline"])
    sys.stderr.write(f"Running {args.sims} sims × {args.ticks} ticks "
                     f"[{args.mode}, {scenario.name}, R5 {len(models)} products]...\n")

    mc = run_montecarlo(TraderClass, models, n_sims=args.sims, n_ticks=args.ticks,
                         base_seed=args.seed, scenario=scenario,
                         bootstrap_gen=bootstrap_gen, mode=args.mode,
                         progress=not args.quiet, workers=args.workers,
                         trader_path=trader_path,
                         enable_noise_traders=enable_noise_traders,
                         informed_flow_default=informed_flow_default)
    print_report(mc, "R5 MONTE CARLO SIMULATION RESULTS")

    out_path = os.path.join(workspace, "montecarlo_results.json")
    summary = {
        "n_sims": mc.n_sims, "scenario": mc.scenario_name, "mode": args.mode,
        "round": 5, "n_ticks": args.ticks, "n_products": len(models),
        "position_limit": R5_POSITION_LIMIT,
        "pnl_mean": mc.pnl_mean, "pnl_std": mc.pnl_std,
        "pnl_median": mc.pnl_median, "pnl_p5": mc.pnl_p5,
        "pnl_p25": mc.pnl_p25, "pnl_p75": mc.pnl_p75, "pnl_p95": mc.pnl_p95,
        "sharpe_mean": mc.sharpe_mean, "sharpe_std": mc.sharpe_std,
        "win_rate": mc.win_rate,
        "max_drawdown_mean": mc.max_drawdown_mean, "max_drawdown_p95": mc.max_drawdown_p95,
        "drawdown_duration_mean": mc.drawdown_duration_mean,
        "avg_fills": mc.avg_fills,
        "limit_breach_total": mc.limit_breach_total,
        "shadow_pnl_mean": mc.shadow_pnl_mean,
        "per_sim_pnl": [r.total_pnl for r in mc.results],
        "per_strategy_mean": {k: float(np.mean([r.pnl_by_strategy.get(k, 0.0) for r in mc.results]))
                              for k in {kk for r in mc.results for kk in r.pnl_by_strategy}},
        "per_group_mean": {k: float(np.mean([r.pnl_by_group.get(k, 0.0) for r in mc.results]))
                           for k in {kk for r in mc.results for kk in r.pnl_by_group}},
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    sys.stderr.write(f"Results saved to {out_path}\n")


if __name__ == "__main__":
    main()
