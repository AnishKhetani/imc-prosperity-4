"""
IMC Prosperity 4 — Monte Carlo Simulator
=========================================
Generates synthetic market data calibrated to R3/R4 historical order book
statistics, runs the Trader algo against it, and aggregates PnL distributions
across N simulations.

Supports:
  - Parametric generation: VFE driven by OU; VEV vouchers BS-priced from VFE
    (Black-Scholes with per-strike IV calibrated from historical first prices)
  - Historical bootstrap (block-resample real R3/R4 CSVs with noise injection)
    — DEFAULT mode for rounds 3/4; produces the most realistic tick replay
  - Named counterparty injection: Mark 01 (buyer) / Mark 22 (seller) voucher
    trades appear in market_trades at R4-calibrated frequencies
  - Configurable TTE (--tte-days): day1=7, day2=6, day3=5 for backtester;
    live=4 for the platform session
  - Stress scenarios (hgp_crash_down, vfe_fast_drift, spread_shock, …)
  - Full PnL distribution analytics (VaR, Sharpe, drawdown, etc.)
  - Parameter sweep mode for hyper-parameter optimisation

Products simulated (rounds 3 & 4):
  HYDROGEL_PACK          (spot, pos-limit 200, OU, spread≈16)
  VELVETFRUIT_EXTRACT    (spot, pos-limit 200, weak MR + drift)
  VEV_4000 … VEV_6500   (call options on VFE, pos-limit 300, BS-priced)

Usage:
  python montecarlo.py                                # 200 sims, bootstrap, R4
  python montecarlo.py --mode parametric --sims 500
  python montecarlo.py --tte-days 5 --round 4        # day-3 TTE
  python montecarlo.py --stress spread_shock
  python montecarlo.py --stress-all --quiet
  python montecarlo.py --sweep ema_alpha 0.05 0.30 6
  python montecarlo.py --trader submissionr4.py --round 4 --mode bootstrap
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
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

# ---------------------------------------------------------------------------
# Lightweight datamodel replicas (no dependency on prosperity4bt at runtime)
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
    def __init__(
        self,
        traderData: str = "",
        timestamp: int = 0,
        listings: Optional[Dict] = None,
        order_depths: Optional[Dict] = None,
        own_trades: Optional[Dict] = None,
        market_trades: Optional[Dict] = None,
        position: Optional[Dict] = None,
        observations: Optional[Observation] = None,
    ):
        self.traderData = traderData
        self.timestamp = timestamp
        self.listings = listings or {}
        self.order_depths = order_depths or {}
        self.own_trades = own_trades or {}
        self.market_trades = market_trades or {}
        self.position = position or {}
        self.observations = observations or Observation()


# ---------------------------------------------------------------------------
# Patch the datamodel module so submission.py imports resolve to our replicas
# ---------------------------------------------------------------------------

import types

_dm = types.ModuleType("datamodel")
for _name in [
    "Listing", "Order", "OrderDepth", "Trade", "ConversionObservation",
    "Observation", "TradingState", "Symbol", "Product", "Position",
]:
    setattr(_dm, _name, globals().get(_name, str))
# Type aliases
_dm.Symbol = str
_dm.Product = str
_dm.Position = int
sys.modules["datamodel"] = _dm


# ---------------------------------------------------------------------------
# SECTION 1: Historical Data Loader & Statistics Extractor
# ---------------------------------------------------------------------------

@dataclass
class ProductStats:
    """Extracted statistics for one product from historical data."""
    symbol: str
    mid_prices: np.ndarray          # time series of mid prices
    spreads: np.ndarray             # L1 spread each tick
    bid_volumes: np.ndarray         # L1 bid volume each tick
    ask_volumes: np.ndarray         # L1 ask volume each tick
    # Derived
    returns: np.ndarray = field(default_factory=lambda: np.array([]))
    drift_per_tick: float = 0.0
    volatility: float = 0.0
    mean_reversion_speed: float = 0.0  # kappa for OU
    long_run_mean: float = 0.0
    spread_mean: float = 0.0
    spread_std: float = 0.0
    vol_mean: float = 0.0
    vol_std: float = 0.0
    autocorr_lag1: float = 0.0
    # Book depth distributions (for multi-level generation)
    depth_levels: int = 2           # typical number of price levels
    level_spacing_mean: float = 3.0
    level_spacing_std: float = 1.0
    # Trade arrival
    trade_arrival_rate: float = 0.01  # fraction of ticks with market trades
    trade_size_mean: float = 5.0
    trade_size_std: float = 2.0

    def __post_init__(self):
        if len(self.mid_prices) > 1:
            self.returns = np.diff(self.mid_prices)
            self.drift_per_tick = np.mean(self.returns)
            self.volatility = np.std(self.returns)
            if self.volatility > 0:
                self.autocorr_lag1 = np.corrcoef(
                    self.returns[:-1], self.returns[1:]
                )[0, 1] if len(self.returns) > 2 else 0.0
            # OU parameter estimation (discrete Vasicek)
            # dr = kappa*(mu - r)*dt + sigma*dW
            self.long_run_mean = np.mean(self.mid_prices)
            if len(self.returns) > 10:
                # Regress r_{t+1} - r_t = a + b*r_t
                y = self.returns
                x = self.mid_prices[:-1]
                x_mean = np.mean(x)
                y_mean = np.mean(y)
                cov_xy = np.mean((x - x_mean) * (y - y_mean))
                var_x = np.var(x)
                if var_x > 0:
                    b = cov_xy / var_x
                    a = y_mean - b * x_mean
                    self.mean_reversion_speed = max(0.0, -b)  # kappa = -b
                    if self.mean_reversion_speed > 0:
                        self.long_run_mean = a / self.mean_reversion_speed
            self.spread_mean = float(np.mean(self.spreads[self.spreads > 0])) if np.any(self.spreads > 0) else 14.0
            self.spread_std = float(np.std(self.spreads[self.spreads > 0])) if np.any(self.spreads > 0) else 3.0
            bv_valid = self.bid_volumes[self.bid_volumes > 0]
            av_valid = self.ask_volumes[self.ask_volumes > 0]
            self.vol_mean = float(np.mean(np.concatenate([bv_valid, av_valid]))) if len(bv_valid) > 0 else 15.0
            self.vol_std = float(np.std(np.concatenate([bv_valid, av_valid]))) if len(bv_valid) > 0 else 5.0


def load_prices_csv(filepath: str) -> Dict[str, List[dict]]:
    """Parse a prosperity prices CSV into per-product tick data."""
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
    """Parse a prosperity trades CSV."""
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
    """Extract statistical properties from parsed tick data."""
    mids, spreads, bvols, avols = [], [], [], []
    for t in product_ticks:
        bp1 = t["bid_price_1"]
        ap1 = t["ask_price_1"]
        if bp1 is not None and ap1 is not None and bp1 > 0 and ap1 > 0:
            mids.append((bp1 + ap1) / 2.0)
            spreads.append(ap1 - bp1)
            bvols.append(t["bid_volume_1"] or 0)
            avols.append(t["ask_volume_1"] or 0)
        elif t["mid_price"] is not None and t["mid_price"] > 0:
            mids.append(t["mid_price"])
            spreads.append(0)
            bvols.append(0)
            avols.append(0)
    return ProductStats(
        symbol=symbol,
        mid_prices=np.array(mids, dtype=np.float64),
        spreads=np.array(spreads, dtype=np.float64),
        bid_volumes=np.array(bvols, dtype=np.float64),
        ask_volumes=np.array(avols, dtype=np.float64),
    )


def _safe_float(s: str) -> Optional[float]:
    try:
        return float(s) if s.strip() else None
    except (ValueError, AttributeError):
        return None

def _safe_int(s: str) -> Optional[int]:
    try:
        return int(float(s)) if s.strip() else None
    except (ValueError, AttributeError):
        return None


# ---------------------------------------------------------------------------
# SECTION 1b: Black-Scholes helpers (VEV voucher pricing)
# ---------------------------------------------------------------------------

def _norm_cdf(x: float) -> float:
    """Standard normal CDF via erf approximation."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def bs_call(S: float, K: float, T: float, sigma: float, r: float = 0.0) -> float:
    """Black-Scholes European call price.

    Parameters
    ----------
    S     : underlying spot price (e.g. VFE mid)
    K     : strike price (e.g. 5300)
    T     : time to expiry in *years* (e.g. 7/252 = 0.02778)
    sigma : annualised implied volatility (e.g. 0.25 = 25%)
    r     : risk-free rate (0 for IMC context)
    """
    if T <= 1e-9 or sigma <= 1e-9 or S <= 0 or K <= 0:
        return max(0.0, S - K)
    sqT = math.sqrt(T)
    try:
        d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * sqT)
    except (ValueError, ZeroDivisionError):
        return max(0.0, S - K)
    d2 = d1 - sigma * sqT
    return S * _norm_cdf(d1) - K * math.exp(-r * T) * _norm_cdf(d2)


def bs_delta(S: float, K: float, T: float, sigma: float, r: float = 0.0) -> float:
    """Black-Scholes call delta N(d1)."""
    if T <= 1e-9 or sigma <= 1e-9 or S <= 0 or K <= 0:
        return 1.0 if S > K else 0.0
    sqT = math.sqrt(T)
    try:
        d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * sqT)
    except (ValueError, ZeroDivisionError):
        return 1.0 if S > K else 0.0
    return _norm_cdf(d1)


def bs_iv(
    C: float, S: float, K: float, T: float, r: float = 0.0,
    lo: float = 0.001, hi: float = 20.0, n_iter: int = 50,
) -> float:
    """Implied volatility via bisection.

    Returns the annualised IV such that bs_call(S,K,T,iv)==C.
    Falls back to lo if no solution found (e.g. deep intrinsic).
    """
    intrinsic = max(0.0, S - K)
    if T <= 1e-9 or C <= intrinsic + 1e-9:
        return lo
    for _ in range(n_iter):
        mid_iv = (lo + hi) * 0.5
        price = bs_call(S, K, T, mid_iv, r)
        if price >= C:
            hi = mid_iv
        else:
            lo = mid_iv
    return (lo + hi) * 0.5


# ---------------------------------------------------------------------------
# SECTION 2: Market Generative Models
# ---------------------------------------------------------------------------

@dataclass
class ProductModel:
    """Generative model for one product's order book evolution."""
    symbol: str
    product_type: str               # "fixed_value" or "random_walk"
    fair_value: float               # initial or fixed FV
    position_limit: int = 80
    # OU parameters
    kappa: float = 0.0              # mean-reversion speed (0 = pure random walk)
    mu: float = 10000.0             # long-run mean
    sigma: float = 2.0              # volatility per tick
    drift: float = 0.0              # deterministic drift per tick
    # Spread / volume
    spread_mean: float = 14.0
    spread_std: float = 3.0
    vol_mean: float = 15.0
    vol_std: float = 5.0
    depth_levels: int = 2
    level_gap_mean: float = 3.0
    level_gap_std: float = 1.0
    # Trade generation
    trade_prob: float = 0.01        # prob of market trade each tick
    trade_size_mean: float = 5.0
    trade_size_std: float = 2.0
    # Fill model for make orders
    make_fill_prob: float = 0.03    # platform-calibrated fill probability
    price_floor: float = float("-inf")  # min allowed mid price (set to 0.0 for options)
    # Voucher / option fields (set is_voucher=True for VEV call options)
    is_voucher: bool = False         # True → price driven by BS on VFE underlying
    strike: float = 0.0             # option strike price (e.g. 5300)
    implied_vol_annual: float = 0.25 # annualised BS IV (25% ≈ R4 calibrated flat smile)

    @classmethod
    def from_stats(cls, stats: ProductStats, product_type: str = "random_walk",
                   position_limit: int = 80) -> "ProductModel":
        return cls(
            symbol=stats.symbol,
            product_type=product_type,
            fair_value=float(stats.mid_prices[0]) if len(stats.mid_prices) > 0 else 10000.0,
            position_limit=position_limit,
            kappa=stats.mean_reversion_speed,
            mu=stats.long_run_mean,
            sigma=stats.volatility if stats.volatility > 0 else 2.0,
            drift=stats.drift_per_tick,
            spread_mean=stats.spread_mean,
            spread_std=stats.spread_std,
            vol_mean=stats.vol_mean,
            vol_std=stats.vol_std,
            depth_levels=stats.depth_levels,
            level_gap_mean=stats.level_spacing_mean,
            level_gap_std=stats.level_spacing_std,
            trade_prob=stats.trade_arrival_rate,
            trade_size_mean=stats.trade_size_mean,
            trade_size_std=stats.trade_size_std,
        )

    @classmethod
    def default_aco(cls) -> "ProductModel":
        """ACO: mean-reverting around 10000, spread ~16, AC(1)=-0.50."""
        return cls(
            symbol="ASH_COATED_OSMIUM",
            product_type="fixed_value",
            fair_value=10000.0,
            position_limit=80,
            kappa=0.05,           # moderate mean-reversion
            mu=10000.0,
            sigma=3.5,
            drift=0.0,
            spread_mean=16.0,
            spread_std=4.0,
            vol_mean=15.0,
            vol_std=6.0,
            depth_levels=2,
            level_gap_mean=3.0,
            level_gap_std=1.0,
            trade_prob=0.008,
            trade_size_mean=5.0,
            trade_size_std=2.5,
            make_fill_prob=0.014,  # platform: ~1.4% fill rate
        )

    @classmethod
    def default_ipr(cls) -> "ProductModel":
        """IPR: drift +0.1/tick, spread ~14, AC(1)=-0.51."""
        return cls(
            symbol="INTARIAN_PEPPER_ROOT",
            product_type="random_walk",
            fair_value=12000.0,
            position_limit=80,
            kappa=0.02,           # weak mean-reversion (mostly drift)
            mu=12000.0,           # starting anchor (will drift away)
            sigma=3.0,
            drift=0.1,           # +0.1/tick = +1000/day (10K ticks)
            spread_mean=14.0,
            spread_std=3.0,
            vol_mean=13.0,
            vol_std=5.0,
            depth_levels=2,
            level_gap_mean=3.0,
            level_gap_std=1.0,
            trade_prob=0.01,
            trade_size_mean=4.0,
            trade_size_std=2.0,
            make_fill_prob=0.033,  # platform: ~3.3% fill rate
        )

    @classmethod
    def default_hydrogel_pack(cls) -> "ProductModel":
        """HYDROGEL_PACK: mean-reverts ~10000, spread=15.73, pos limit 200.
        R4 calibration: vol=2.169/tick, spread_mean=15.73, bv_mean=12.4.
        OU kappa calibrated from data; drift=0 (day-to-day drift varies so
        neutral default is used; stress scenarios cover both directions)."""
        return cls(
            symbol="HYDROGEL_PACK",
            product_type="fixed_value",
            fair_value=10000.0,
            position_limit=200,
            kappa=0.002,         # half-life ~300 ticks (stationary mean-reversion)
            mu=10000.0,          # structural anchor confirmed from R3/R4 data
            sigma=2.2,           # R4 actual: 2.169/tick rounded up slightly
            drift=0.0,
            spread_mean=15.7,    # R4 actual: 15.73
            spread_std=1.5,      # R4 actual: 1.45
            vol_mean=12.4,       # R4 actual bv_mean=12.4
            vol_std=4.0,
            depth_levels=2,
            level_gap_mean=8.0,
            level_gap_std=3.0,
            trade_prob=0.01,
            trade_size_mean=5.0,
            trade_size_std=2.0,
            make_fill_prob=0.015,  # platform ~1.5% fill rate for 16-wide spread
        )

    @classmethod
    def default_velvetfruit_extract(cls) -> "ProductModel":
        """VELVETFRUIT_EXTRACT: neutral drift (day-specific drift varies), spread=5.
        R4 calibration: vol=1.138/tick, spread_mean=4.98, bv_mean=37.8.
        Drift=0 is the neutral default; stress scenarios cover trending days."""
        return cls(
            symbol="VELVETFRUIT_EXTRACT",
            product_type="random_walk",
            fair_value=5245.0,
            position_limit=200,
            kappa=0.001,         # very weak MR — mostly random walk within day
            mu=5245.0,
            sigma=1.14,          # R4 actual: 1.138/tick
            drift=0.0,           # neutral default; use stress scenarios for trending days
            spread_mean=5.0,     # R4 actual: 4.98
            spread_std=0.9,      # R4 actual: 0.85
            vol_mean=37.8,       # R4 actual bv_mean=37.8
            vol_std=8.0,
            depth_levels=2,
            level_gap_mean=2.0,
            level_gap_std=1.0,
            trade_prob=0.012,
            trade_size_mean=5.0,
            trade_size_std=2.0,
            make_fill_prob=0.018,
        )

    @classmethod
    def default_vev(cls, strike: float, position_limit: int = 300) -> "ProductModel":
        """VEV voucher: European call on VFE, BS-priced in parametric mode.

        In parametric mode the fair value is recomputed each tick from
        bs_call(VFE_mid, strike, tte_remaining, implied_vol_annual).
        In bootstrap mode it uses block-resampled historical ticks.

        Spread calibrated from R4 data (wider for ITM/deep-OTM, narrower ATM):
          VEV_4000: spread≈20.75   VEV_5000: spread≈5.96   VEV_5300: spread≈1.97
          VEV_5400: spread≈1.30    VEV_5500: spread≈1.11   VEV_6000: spread≈1.0

        IV=0.25 (25% annual) fits R4 ATM/near-ATM prices well. Per-strike IV
        is re-calibrated automatically in main() when historical data is loaded.
        """
        # Spread table calibrated to R4 data
        _SPREAD = {
            4000: (20.8, 1.6), 4500: (15.8, 1.3), 5000: (6.0, 0.7),
            5100: (4.2, 0.6), 5200: (2.8, 0.5), 5300: (2.0, 0.4),
            5400: (1.3, 0.5), 5500: (1.1, 0.3), 6000: (1.0, 0.2),
            6500: (1.0, 0.2),
        }
        spread_mean, spread_std = _SPREAD.get(int(strike), (2.0, 0.5))
        # Initial fair value from BS at default VFE=5245, TTE=7/252 years
        initial_vfe = 5245.0
        initial_tte_years = 7.0 / 252.0
        initial_iv = 0.25
        fair = max(0.0, bs_call(initial_vfe, strike, initial_tte_years, initial_iv))
        return cls(
            symbol=f"VEV_{int(strike)}",
            product_type="fixed_value",
            fair_value=fair,
            position_limit=position_limit,
            kappa=0.08,          # Used only in bootstrap fallback; BS drives parametric
            mu=fair,
            sigma=max(0.1, fair * 0.04),   # Fallback OU noise (small)
            drift=0.0,
            spread_mean=spread_mean,
            spread_std=spread_std,
            vol_mean=15.0,       # typical L1 size for vouchers
            vol_std=5.0,
            depth_levels=1,      # Vouchers typically have shallow books
            level_gap_mean=2.0,
            level_gap_std=1.0,
            trade_prob=0.005,
            trade_size_mean=3.0,
            trade_size_std=1.0,
            make_fill_prob=0.015,
            price_floor=0.0,     # options cannot go negative
            is_voucher=True,
            strike=float(strike),
            implied_vol_annual=initial_iv,
        )


class MarketGenerator:
    """Generates synthetic order book sequences for a single product."""

    def __init__(self, model: ProductModel, rng: np.random.Generator):
        self.model = model
        self.rng = rng
        self.current_mid = model.fair_value

    def reset(self):
        self.current_mid = self.model.fair_value

    def step(self) -> float:
        """Advance mid-price by one tick using OU + drift."""
        m = self.model
        # OU step: dx = kappa*(mu - x)*dt + sigma*dW + drift*dt
        # For fixed_value: mu is the known FV, kappa is strong
        # For random_walk: kappa is weak, drift dominates
        dW = self.rng.standard_normal()
        if m.product_type == "fixed_value":
            # Strong mean-reversion to known FV
            self.current_mid += m.kappa * (m.mu - self.current_mid) + m.sigma * dW
        else:
            # Weak MR + drift
            self.current_mid += (
                m.kappa * (m.mu - self.current_mid)
                + m.drift
                + m.sigma * dW
            )
            # Slowly update OU target to follow drift
            m.mu += m.drift * 0.5
        if self.model.price_floor > float("-inf"):
            self.current_mid = max(self.model.price_floor, self.current_mid)
        return self.current_mid

    def generate_order_book(self, mid: float) -> OrderDepth:
        """Generate a synthetic order book around mid price."""
        od = OrderDepth()
        m = self.model

        # Sample spread (clamp to minimum of 2)
        spread = max(2, int(round(self.rng.normal(m.spread_mean, m.spread_std))))
        half = spread / 2.0

        # L1 prices
        best_bid = int(math.floor(mid - half))
        best_ask = int(math.ceil(mid + half))
        if best_bid >= best_ask:
            best_ask = best_bid + 1

        # L1 volumes
        bv1 = max(1, int(round(self.rng.normal(m.vol_mean, m.vol_std))))
        av1 = max(1, int(round(self.rng.normal(m.vol_mean, m.vol_std))))
        od.buy_orders[best_bid] = bv1
        od.sell_orders[best_ask] = -av1  # sells are NEGATIVE

        # Additional depth levels
        for lvl in range(1, m.depth_levels):
            gap = max(1, int(round(self.rng.normal(m.level_gap_mean, m.level_gap_std))))
            vol_decay = max(0.5, 1.0 + 0.3 * lvl)  # deeper levels have more volume
            bv = max(1, int(round(self.rng.normal(m.vol_mean * vol_decay, m.vol_std))))
            av = max(1, int(round(self.rng.normal(m.vol_mean * vol_decay, m.vol_std))))
            bid_p = best_bid - gap * lvl
            ask_p = best_ask + gap * lvl
            od.buy_orders[bid_p] = bv
            od.sell_orders[ask_p] = -av

        # Occasionally generate empty-side ticks (~3% of ticks, matching data)
        if self.rng.random() < 0.03:
            if self.rng.random() < 0.5:
                od.buy_orders = {}
            else:
                od.sell_orders = {}

        return od

    def generate_market_trades(self, mid: float, timestamp: int) -> List[Trade]:
        """Generate stochastic market trades for this tick."""
        trades = []
        m = self.model
        if self.rng.random() < m.trade_prob:
            size = max(1, int(round(self.rng.normal(m.trade_size_mean, m.trade_size_std))))
            # Price near mid with some noise
            price_offset = int(round(self.rng.normal(0, m.spread_mean * 0.3)))
            price = int(round(mid)) + price_offset
            trades.append(Trade(
                symbol=m.symbol,
                price=price,
                quantity=size,
                buyer="",
                seller="",
                timestamp=timestamp,
            ))
        return trades


# ---------------------------------------------------------------------------
# SECTION 3: Fill Model (Matching Engine)
# ---------------------------------------------------------------------------

class FillEngine:
    """Simulates order matching against the synthetic order book.
    
    Takes (crossing orders) are filled deterministically.
    Makes (passive orders) are filled probabilistically based on
    platform-calibrated fill rates.
    """

    def __init__(self, rng: np.random.Generator):
        self.rng = rng

    def match_orders(
        self,
        orders: List[Order],
        book: OrderDepth,
        position: int,
        position_limit: int,
        make_fill_prob: float,
    ) -> Tuple[List[Trade], int, float]:
        """
        Match orders against the book. Returns (fills, new_position, pnl_delta).
        
        Processing order matches platform behavior:
        1. Process orders in submission order
        2. Takes (crossing) fill deterministically at book price
        3. Makes (passive) fill probabilistically
        4. Each order checked against position limit after prior fills
        """
        fills: List[Trade] = []
        pnl = 0.0
        pos = position

        for order in orders:
            # Position limit check
            if order.quantity > 0:  # BUY
                max_qty = position_limit - pos
                if max_qty <= 0:
                    continue
                qty = min(order.quantity, max_qty)
            else:  # SELL
                max_qty = position_limit + pos
                if max_qty <= 0:
                    continue
                qty = max(-max_qty, order.quantity)  # qty is negative

            if qty == 0:
                continue

            if qty > 0:  # BUY
                # Check if this is a take (crosses the ask)
                is_take = False
                for ask_p in sorted(book.sell_orders.keys()):
                    if order.price >= ask_p:
                        is_take = True
                        fillable = min(qty, abs(book.sell_orders[ask_p]))
                        if fillable > 0:
                            fills.append(Trade(
                                symbol=order.symbol,
                                price=ask_p,
                                quantity=fillable,
                                buyer="SUBMISSION",
                                seller="BOT",
                                timestamp=0,
                            ))
                            pos += fillable
                            pnl -= ask_p * fillable
                            qty -= fillable
                            # Reduce book liquidity
                            book.sell_orders[ask_p] += fillable  # less negative
                            if abs(book.sell_orders[ask_p]) <= 0:
                                del book.sell_orders[ask_p]
                        if qty <= 0:
                            break

                if not is_take and qty > 0:
                    # Passive buy order — probabilistic fill
                    if self.rng.random() < make_fill_prob:
                        fill_qty = max(1, int(qty * self.rng.uniform(0.3, 1.0)))
                        fills.append(Trade(
                            symbol=order.symbol,
                            price=order.price,
                            quantity=fill_qty,
                            buyer="SUBMISSION",
                            seller="BOT",
                            timestamp=0,
                        ))
                        pos += fill_qty
                        pnl -= order.price * fill_qty

            else:  # SELL (qty < 0)
                abs_qty = abs(qty)
                is_take = False
                for bid_p in sorted(book.buy_orders.keys(), reverse=True):
                    if order.price <= bid_p:
                        is_take = True
                        fillable = min(abs_qty, book.buy_orders[bid_p])
                        if fillable > 0:
                            fills.append(Trade(
                                symbol=order.symbol,
                                price=bid_p,
                                quantity=fillable,
                                buyer="BOT",
                                seller="SUBMISSION",
                                timestamp=0,
                            ))
                            pos -= fillable
                            pnl += bid_p * fillable
                            abs_qty -= fillable
                            book.buy_orders[bid_p] -= fillable
                            if book.buy_orders[bid_p] <= 0:
                                del book.buy_orders[bid_p]
                        if abs_qty <= 0:
                            break

                if not is_take and abs_qty > 0:
                    if self.rng.random() < make_fill_prob:
                        fill_qty = max(1, int(abs_qty * self.rng.uniform(0.3, 1.0)))
                        fills.append(Trade(
                            symbol=order.symbol,
                            price=order.price,
                            quantity=fill_qty,
                            buyer="BOT",
                            seller="SUBMISSION",
                            timestamp=0,
                        ))
                        pos -= fill_qty
                        pnl += order.price * fill_qty

        return fills, pos, pnl


# ---------------------------------------------------------------------------
# SECTION 4: Bootstrap Data Generator
# ---------------------------------------------------------------------------

class BootstrapGenerator:
    """Generates synthetic data by block-resampling historical ticks with noise."""

    def __init__(
        self,
        historical_data: Dict[str, List[dict]],
        block_size: int = 50,
        noise_scale: float = 1.0,
        rng: Optional[np.random.Generator] = None,
    ):
        self.data = historical_data
        self.block_size = block_size
        self.noise_scale = noise_scale
        self.rng = rng or np.random.default_rng()

    def generate_sequence(self, symbol: str, n_ticks: int) -> List[dict]:
        """Generate n_ticks of data by block-resampling with noise."""
        src = self.data.get(symbol, [])
        if not src:
            raise ValueError(f"No historical data for {symbol}")

        result = []
        remaining = n_ticks
        while remaining > 0:
            # Pick random block start
            max_start = max(0, len(src) - self.block_size)
            start = self.rng.integers(0, max_start + 1)
            block = src[start:start + self.block_size]
            for tick in block:
                if remaining <= 0:
                    break
                noisy = dict(tick)
                # Add noise to prices
                if noisy["bid_price_1"] is not None:
                    noisy["bid_price_1"] += self.rng.normal(0, self.noise_scale)
                if noisy["ask_price_1"] is not None:
                    noisy["ask_price_1"] += self.rng.normal(0, self.noise_scale)
                if noisy["mid_price"] is not None:
                    noisy["mid_price"] += self.rng.normal(0, self.noise_scale)
                result.append(noisy)
                remaining -= 1
        return result

    def generate_order_book(self, tick: dict, symbol: str) -> OrderDepth:
        """Convert a tick dict into an OrderDepth."""
        od = OrderDepth()
        for level in range(1, 4):
            bp = tick.get(f"bid_price_{level}")
            bv = tick.get(f"bid_volume_{level}")
            if bp is not None and bv is not None and bp > 0 and bv > 0:
                od.buy_orders[int(round(bp))] = int(bv)
            ap = tick.get(f"ask_price_{level}")
            av = tick.get(f"ask_volume_{level}")
            if ap is not None and av is not None and ap > 0 and av > 0:
                od.sell_orders[int(round(ap))] = -int(av)
        return od


# ---------------------------------------------------------------------------
# SECTION 5: Stress Scenarios
# ---------------------------------------------------------------------------

@dataclass
class StressScenario:
    """Perturbation applied to base model parameters."""
    name: str
    spread_multiplier: float = 1.0    # multiply spread_mean
    vol_multiplier: float = 1.0       # multiply sigma
    drift_override: Optional[float] = None   # override drift (for random_walk products)
    fill_rate_multiplier: float = 1.0
    liquidity_multiplier: float = 1.0   # multiply volume means
    empty_book_prob: float = 0.03       # prob of empty book tick
    # R3-specific: shift HGP fair value anchor (to simulate trend-away-from-10000)
    hgp_mu_override: Optional[float] = None  # move HGP OU attractor to this price
    hgp_kappa_multiplier: float = 1.0        # weaken/strengthen HGP mean-reversion


STRESS_SCENARIOS = {
    "baseline": StressScenario(name="baseline"),
    "wide_spread": StressScenario(name="wide_spread", spread_multiplier=1.5),
    "narrow_spread": StressScenario(name="narrow_spread", spread_multiplier=0.7),
    "high_vol": StressScenario(name="high_vol", vol_multiplier=2.0),
    "low_vol": StressScenario(name="low_vol", vol_multiplier=0.5),
    "no_drift": StressScenario(name="no_drift", drift_override=0.0),
    "double_drift": StressScenario(name="double_drift", drift_override=0.003),  # +30/day for VFE
    "negative_drift": StressScenario(name="negative_drift", drift_override=-0.002),  # VFE reverses
    "thin_liquidity": StressScenario(name="thin_liquidity", liquidity_multiplier=0.4, fill_rate_multiplier=0.5),
    "spread_shock": StressScenario(name="spread_shock", spread_multiplier=2.5, vol_multiplier=1.5),
    "crash": StressScenario(name="crash", vol_multiplier=3.0, drift_override=-0.005, fill_rate_multiplier=0.3),
    "low_fill": StressScenario(name="low_fill", fill_rate_multiplier=0.3),
    "platform_like": StressScenario(
        name="platform_like",
        spread_multiplier=1.2,      # platform spreads slightly wider
        fill_rate_multiplier=0.5,   # platform fills much lower (~1-2% vs backtester 15%)
        liquidity_multiplier=0.8,
    ),
    # -----------------------------------------------------------------------
    # R3-specific: HGP trending away from 10000 (the v1 live-session disaster)
    # On the live R3 day-2 session, HGP drifted 10011 → 9927 in ~1000 ticks.
    # Both scenarios set the OU attractor below/above 10000 AND weaken kappa,
    # so the price trends toward the target rather than reverting to 10000.
    # -----------------------------------------------------------------------
    "hgp_crash_down": StressScenario(
        name="hgp_crash_down",
        vol_multiplier=1.5,
        fill_rate_multiplier=0.6,
        hgp_mu_override=9920.0,     # attractor shifts to 9920 (v1 disaster endpoint)
        hgp_kappa_multiplier=0.5,   # half-speed reversion: price drifts down slowly
    ),
    "hgp_crash_up": StressScenario(
        name="hgp_crash_up",
        vol_multiplier=1.5,
        fill_rate_multiplier=0.6,
        hgp_mu_override=10080.0,    # attractor shifts +80 (symmetric upside scenario)
        hgp_kappa_multiplier=0.5,
    ),
    "hgp_extreme_down": StressScenario(
        name="hgp_extreme_down",
        vol_multiplier=2.0,
        fill_rate_multiplier=0.4,
        hgp_mu_override=9850.0,     # extreme: -150 from anchor (3× historical worst)
        hgp_kappa_multiplier=0.25,  # very slow reversion — does NOT recover quickly
    ),
    "hgp_no_reversion": StressScenario(
        name="hgp_no_reversion",
        vol_multiplier=2.0,
        fill_rate_multiplier=0.4,
        hgp_mu_override=9900.0,
        hgp_kappa_multiplier=0.0,   # zero kappa = pure random walk from starting point
    ),
    "vfe_no_drift": StressScenario(
        name="vfe_no_drift",
        drift_override=0.0,          # VFE drift disappears (tests if VFE MM still profits)
    ),
    "vfe_fast_drift": StressScenario(
        name="vfe_fast_drift",
        drift_override=0.004,         # +40/day (2.7x normal) — strong trending day
    ),
    "full_stress": StressScenario(
        name="full_stress",
        spread_multiplier=1.5,
        vol_multiplier=2.0,
        fill_rate_multiplier=0.4,
        liquidity_multiplier=0.6,
        hgp_mu_override=9920.0,
        hgp_kappa_multiplier=0.3,
        drift_override=-0.001,
    ),
}


def apply_stress(model: ProductModel, scenario: StressScenario) -> ProductModel:
    """Return a new model with stress perturbations applied."""
    import copy
    m = copy.deepcopy(model)
    m.spread_mean *= scenario.spread_multiplier
    m.spread_std *= scenario.spread_multiplier
    m.sigma *= scenario.vol_multiplier
    m.vol_mean *= scenario.liquidity_multiplier
    m.vol_std *= scenario.liquidity_multiplier
    m.make_fill_prob *= scenario.fill_rate_multiplier
    # Drift override only applies to non-voucher spot products
    if scenario.drift_override is not None and not m.is_voucher:
        m.drift = scenario.drift_override
    # HGP-specific: shift the OU attractor (simulates HGP trending away from 10000)
    if m.symbol == "HYDROGEL_PACK" and scenario.hgp_mu_override is not None:
        m.mu = scenario.hgp_mu_override
    if m.symbol == "HYDROGEL_PACK":
        m.kappa *= scenario.hgp_kappa_multiplier
    return m


# ---------------------------------------------------------------------------
# SECTION 5b: Manual Challenge — Celestial Gardeners' Guild (Round 3)
# ---------------------------------------------------------------------------
#
# Wiki rules (R3 — "Gloves Off"):
#   • N=51 counterparties, reserve prices uniform on {670, 675, …, 920} (step 5)
#   • Fair sell price the following day: 920 XIRECS (guaranteed)
#   • You submit TWO bids.  Sequential / exclusive model:
#       bid1: every counterparty with reserve < bid1 sells at bid1.
#             Profit per unit = 920 − bid1.
#       bid2: remaining counterparties (reserve ≥ bid1) with reserve < bid2:
#             - if bid2 ≥ avg_bid2 (mean of all players' second bids):
#                 trade at bid2.  Profit per unit = 920 − bid2.
#             - if bid2 < avg_bid2:
#                 trade with penalty multiplier = ((920 − avg_b2)/(920 − b2))^3
#                 Effective profit per unit = (920−b2) × penalty
#                                          = (920−avg_b2)^3 / (920−b2)^2
#   • Analytical optimum for bid1 (ignoring bid2): bid1 = 795 = midpoint(670,920)
#     → captures 25 units × 125 profit = 3,125 XIRECS.
#   • For bid2 (given avg competitor bid2 ≈ b2_nash):
#     bid just above b2_nash avoids penalty; b2_nash ≈ 857 when bid1=795.

_GUILD_SELL_PRICE = 920
_GUILD_RESERVES   = list(range(670, 925, 5))   # [670, 675, …, 920]  (51 values)


def manual_challenge_pnl(
    bid1: int,
    bid2: int,
    avg_bid2: float,
    sell_price: int = _GUILD_SELL_PRICE,
    reserves: Optional[List[int]] = None,
) -> Tuple[float, float, float]:
    """
    Compute expected PnL from the Celestial Gardeners' Guild manual challenge.

    Uses the *sequential / exclusive* model: bid2 only applies to counterparties
    whose reserve exceeds bid1 (i.e. those that did NOT trade at bid1).

    Parameters
    ----------
    bid1      : first bid price (integer, ideally multiple of 5)
    bid2      : second bid price (integer, ideally multiple of 5)
    avg_bid2  : assumed mean second bid of all competing players
    sell_price: fair sell price the next day (920 per wiki)
    reserves  : list of counterparty reserve prices (default: 670..920 step 5)

    Returns
    -------
    (total_pnl, pnl_from_bid1, pnl_from_bid2)
    """
    if reserves is None:
        reserves = _GUILD_RESERVES

    pnl_b1 = 0.0
    pnl_b2 = 0.0

    for r in reserves:
        if bid1 > r:
            # Captured by bid1
            pnl_b1 += sell_price - bid1
        elif bid2 > r:
            # Competed for via bid2
            profit_per_unit = float(sell_price - bid2)
            if bid2 >= avg_bid2:
                pnl_b2 += profit_per_unit
            else:
                # Penalty formula from wiki: PnL × ((920−avg_b2)/(920−b2))^3
                denom = sell_price - bid2
                if denom > 0:
                    penalty = ((sell_price - avg_bid2) / denom) ** 3
                    pnl_b2 += profit_per_unit * penalty

    return pnl_b1 + pnl_b2, pnl_b1, pnl_b2


def optimize_manual_bids(
    avg_bid2_estimate: float = 795.0,
    bid_grid_step: int = 5,
    sell_price: int = _GUILD_SELL_PRICE,
    reserves: Optional[List[int]] = None,
) -> Tuple[Tuple[int, int], float]:
    """
    Find (bid1, bid2) maximising expected PnL via exhaustive grid search.

    Parameters
    ----------
    avg_bid2_estimate : assumption about the mean competitor second bid
    bid_grid_step     : bid increment (must match reserve step = 5)
    sell_price        : fair sell price (920)
    reserves          : counterparty reserve prices

    Returns
    -------
    ((best_bid1, best_bid2), best_total_pnl)
    """
    if reserves is None:
        reserves = _GUILD_RESERVES
    min_r = min(reserves)
    max_r = max(reserves) + bid_grid_step  # include sell_price endpoint

    best_pnl  = -float("inf")
    best_bids = (min_r, max_r)

    for b1 in range(min_r, max_r + 1, bid_grid_step):
        for b2 in range(min_r, max_r + 1, bid_grid_step):
            pnl, _, _ = manual_challenge_pnl(b1, b2, avg_bid2_estimate, sell_price, reserves)
            if pnl > best_pnl:
                best_pnl  = pnl
                best_bids = (b1, b2)

    return best_bids, best_pnl


def print_manual_challenge_analysis(
    avg_bid2_estimates: Optional[List[float]] = None,
) -> None:
    """
    Print a full analysis: bid1 sweep, then optimal (bid1,bid2) for each
    assumed competitor avg_bid2.
    """
    if avg_bid2_estimates is None:
        avg_bid2_estimates = [750.0, 770.0, 790.0, 795.0, 800.0, 810.0,
                               830.0, 850.0, 860.0, 870.0, 880.0]

    print("\n" + "=" * 72)
    print("  MANUAL CHALLENGE — Celestial Gardeners' Guild (Round 3)")
    print(f"  Reserve prices: 670–920 step 5 ({len(_GUILD_RESERVES)} counterparties)")
    print(f"  Guaranteed sell price: {_GUILD_SELL_PRICE} XIRECS next day")
    print("=" * 72)

    # ---- Bid-1 sweep (no competition) ------------------------------------
    print("\n  --- Bid 1 optimum (independent of competition) ---")
    print(f"  {'bid1':>6}  {'units_b1':>8}  {'PnL/unit':>8}  {'PnL_b1':>10}")
    print(f"  {'-'*6}  {'-'*8}  {'-'*8}  {'-'*10}")
    best_b1_pnl  = -1.0
    for b1 in range(670, 925, 5):
        units = sum(1 for r in _GUILD_RESERVES if b1 > r)
        ppu   = _GUILD_SELL_PRICE - b1
        total = units * ppu
        marker = "  <-- optimal" if total > best_b1_pnl else ""
        if total > best_b1_pnl:
            best_b1_pnl = total
        if total >= 0:
            print(f"  {b1:>6}  {units:>8}  {ppu:>8}  {total:>10,}{marker}")

    # ---- Joint (bid1, bid2) optimum for each avg_bid2 assumption ---------
    print("\n  --- Optimal (bid1, bid2) vs assumed competitor avg_bid2 ---")
    print(f"  {'avg_b2':>8}  {'bid1':>6}  {'bid2':>6}  "
          f"{'PnL_b1':>9}  {'PnL_b2':>9}  {'Total':>10}")
    print(f"  {'-'*8}  {'-'*6}  {'-'*6}  {'-'*9}  {'-'*9}  {'-'*10}")
    for avg_b2 in avg_bid2_estimates:
        (b1, b2), pnl = optimize_manual_bids(avg_bid2_estimate=avg_b2)
        _, pb1, pb2 = manual_challenge_pnl(b1, b2, avg_b2)
        print(f"  {avg_b2:>8.0f}  {b1:>6}  {b2:>6}  "
              f"  {pb1:>8,.0f}  {pb2:>8,.0f}  {pnl:>10,.0f}")

    print("\n" + "=" * 72)
    print("  KEY RULES:")
    print("    • Single-bid optimum: bid1=795 → 25 units × 125 = 3,125 XIRECS")
    print("    • Two-bid optimum (grid search): bid1=750, bid2=835")
    print("      → 2,720 (bid1) + 1,445 (bid2) = 4,165 XIRECS")
    print("      Lower bid1 leaves a bigger pool for bid2's cheaper capture.")
    print("    • bid2 Nash: bid AT or just ABOVE expected competitor mean to")
    print("      avoid the ((920-avg_b2)/(920-b2))^3 penalty multiplier.")
    print("    • If competitors cluster near bid2≈835, you win with bid2=840+")
    print("      (gain 1 more unit but lose 5 profit/unit — monitor the table).")
    print("=" * 72)


# ---------------------------------------------------------------------------
# SECTION 5c: Named Counterparty Trader Simulator (R3/R4)
# ---------------------------------------------------------------------------

class NamedTraderSimulator:
    """Simulates Mark 01 (buyer) / Mark 22 (seller) voucher trading activity.

    In R4, the most significant named trader pattern is buyer='Mark 01',
    seller='Mark 22': Mark 22 dumps OTM VEV vouchers (often at 0 for deep-OTM
    strikes) and Mark 01 picks them up at market price.  The R4 submission's
    CP overlay detects these trades and adjusts quoting accordingly.

    Trade frequencies are calibrated to R4 data (3 days × 10 000 ticks/day):
      VEV_5300: ~44/day    VEV_5400: ~88/day    VEV_5500: ~100/day
      VEV_6000: ~106/day   VEV_6500: ~106/day   VEV_5200: ~11/day

    All voucher trades use buyer='Mark 01', seller='Mark 22'.
    Deep-OTM strikes (6000/6500) trade at price=0; others trade near fair mid.
    """

    # Per-tick probability of a named trade occurring, per strike.
    # Derived from R4 actual counts / (3 days × 10 000 ticks).
    _VOUCHER_PROBS: Dict[str, float] = {
        "VEV_5200": 0.00037,
        "VEV_5300": 0.00440,
        "VEV_5400": 0.00877,
        "VEV_5500": 0.00997,
        "VEV_6000": 0.01057,
        "VEV_6500": 0.01057,
    }
    # Strikes where Mark 22 dumps at price=0 regardless of fair value
    _ZERO_PRICE_STRIKES: set = {"VEV_6000", "VEV_6500"}

    def __init__(self, rng: np.random.Generator):
        self.rng = rng

    def generate_trades(
        self,
        active_symbols: List[str],
        last_mids: Dict[str, float],
        timestamp: int,
    ) -> Dict[str, List[Trade]]:
        """Return Mark 01/22 market trades to inject into TradingState."""
        result: Dict[str, List[Trade]] = {}
        for sym, prob in self._VOUCHER_PROBS.items():
            if sym not in active_symbols:
                continue
            if self.rng.random() > prob:
                continue
            mid = last_mids.get(sym, 0.0)
            if sym in self._ZERO_PRICE_STRIKES or mid < 1.0:
                price = 0
            else:
                # Trade near fair mid (±1 tick noise)
                price = max(0, int(round(mid)) + int(self.rng.integers(-1, 2)))
            size = int(self.rng.integers(2, 5))   # 2-4 units (R4 typical)
            result[sym] = [Trade(
                symbol=sym,
                price=price,
                quantity=size,
                buyer="Mark 01",
                seller="Mark 22",
                timestamp=timestamp,
            )]
        return result


# ---------------------------------------------------------------------------
# SECTION 6: Simulation Engine
# ---------------------------------------------------------------------------

@dataclass
class SimResult:
    """Result of a single simulation run."""
    total_pnl: float = 0.0
    pnl_by_product: Dict[str, float] = field(default_factory=dict)
    pnl_curve: List[float] = field(default_factory=list)  # cumulative PnL per tick
    max_drawdown: float = 0.0
    sharpe: float = 0.0
    n_fills: int = 0
    fills_by_product: Dict[str, int] = field(default_factory=dict)
    max_position: Dict[str, int] = field(default_factory=dict)
    avg_position: Dict[str, float] = field(default_factory=dict)
    final_positions: Dict[str, int] = field(default_factory=dict)
    # Terminal PnL includes mark-to-market of final position
    terminal_pnl: float = 0.0


class SimulationEngine:
    """Runs the Trader against synthetic or bootstrapped market data."""

    def __init__(
        self,
        trader_class,
        models: List[ProductModel],
        n_ticks: int = 10000,
        seed: Optional[int] = None,
        scenario: StressScenario = STRESS_SCENARIOS["baseline"],
        bootstrap_gen: Optional[BootstrapGenerator] = None,
        mode: str = "parametric",  # "parametric" or "bootstrap"
        tte_start_days: float = 4.0,    # initial TTE for VEV options (trading days)
        ticks_per_day: int = 10000,     # backtester scale; 2000 for platform-like
        enable_named_traders: bool = True,  # inject Mark 01/22 voucher trades
    ):
        self.trader_class = trader_class
        self.base_models = models
        self.n_ticks = n_ticks
        self.seed = seed
        self.scenario = scenario
        self.bootstrap_gen = bootstrap_gen
        self.mode = mode
        self.tte_start_days = tte_start_days
        self.ticks_per_day = ticks_per_day
        self.enable_named_traders = enable_named_traders

    def run(self, sim_seed: int) -> SimResult:
        """Execute one full simulation."""
        rng = np.random.default_rng(sim_seed)
        fill_engine = FillEngine(rng)

        # Apply stress to models
        models = [apply_stress(m, self.scenario) for m in self.base_models]
        generators = {m.symbol: MarketGenerator(m, rng) for m in models}

        # Named trader simulator (R3/R4 only, when enabled)
        named_traders: Optional[NamedTraderSimulator] = None
        if self.enable_named_traders:
            named_traders = NamedTraderSimulator(rng)

        # Bootstrap sequences if needed
        bootstrap_sequences: Dict[str, List[dict]] = {}
        if self.mode == "bootstrap" and self.bootstrap_gen is not None:
            self.bootstrap_gen.rng = rng
            for m in models:
                try:
                    bootstrap_sequences[m.symbol] = self.bootstrap_gen.generate_sequence(
                        m.symbol, self.n_ticks
                    )
                except ValueError:
                    pass  # Fall back to parametric for this product

        # Initialize trader
        trader = self.trader_class()

        # Suppress print output from logger
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()

        try:
            return self._run_inner(
                trader, models, generators, fill_engine, rng,
                bootstrap_sequences, named_traders,
            )
        finally:
            sys.stdout = old_stdout

    def _run_inner(
        self,
        trader,
        models: List[ProductModel],
        generators: Dict[str, MarketGenerator],
        fill_engine: FillEngine,
        rng: np.random.Generator,
        bootstrap_sequences: Dict[str, List[dict]],
        named_traders: Optional[NamedTraderSimulator] = None,
    ) -> SimResult:
        result = SimResult()
        result.pnl_by_product = {m.symbol: 0.0 for m in models}
        result.fills_by_product = {m.symbol: 0 for m in models}
        result.max_position = {m.symbol: 0 for m in models}
        result.avg_position = {m.symbol: 0.0 for m in models}

        positions: Dict[str, int] = {m.symbol: 0 for m in models}
        cash_pnl: Dict[str, float] = {m.symbol: 0.0 for m in models}
        trader_data = ""
        cumulative_pnl = 0.0
        peak_pnl = 0.0
        max_dd = 0.0
        tick_pnls: List[float] = []
        position_sums: Dict[str, float] = {m.symbol: 0.0 for m in models}
        last_mids: Dict[str, float] = {}

        # ------------------------------------------------------------------
        # Pre-generate mid-price sequences for parametric mode (vectorised).
        # VEV vouchers are BS-priced from the VFE sequence; non-voucher
        # products use independent OU processes.
        # ------------------------------------------------------------------
        mid_sequences: Dict[str, np.ndarray] = {}
        vfe_mids: Optional[np.ndarray] = None

        # Pass 1: generate spot-product (non-voucher) sequences
        for m in models:
            if m.is_voucher:
                continue
            gen = generators[m.symbol]
            gen.reset()
            n = self.n_ticks
            dW = gen.rng.standard_normal(n)
            mids = np.empty(n)
            mid = gen.current_mid
            mu = m.mu
            if m.product_type == "fixed_value":
                for t in range(n):
                    mid += m.kappa * (mu - mid) + m.sigma * dW[t]
                    mids[t] = mid
            else:
                drift = m.drift
                kappa = m.kappa
                sigma = m.sigma
                for t in range(n):
                    mid += kappa * (mu - mid) + drift + sigma * dW[t]
                    mu += drift * 0.5
                    mids[t] = mid
            if m.price_floor > float("-inf"):
                mids = np.maximum(m.price_floor, mids)
            mid_sequences[m.symbol] = mids
            if m.symbol == "VELVETFRUIT_EXTRACT":
                vfe_mids = mids

        # Pass 2: BS-price vouchers from VFE sequence (parametric mode only)
        for m in models:
            if not m.is_voucher:
                continue
            if vfe_mids is not None and self.mode == "parametric":
                # TTE decreases by 1 trading day per `ticks_per_day` ticks
                tte_start_yrs = self.tte_start_days / 252.0
                tick_idx_arr = np.arange(self.n_ticks, dtype=np.float64)
                tte_yrs = np.maximum(
                    1e-6,
                    tte_start_yrs - tick_idx_arr / (self.ticks_per_day * 252.0),
                )
                _bs_call_vec = np.vectorize(bs_call)
                fairs = _bs_call_vec(vfe_mids, m.strike, tte_yrs, m.implied_vol_annual)
                mid_sequences[m.symbol] = np.maximum(0.0, fairs)
            else:
                # Fallback: simple OU centred on current fair value
                gen = generators[m.symbol]
                gen.reset()
                n = self.n_ticks
                dW = gen.rng.standard_normal(n)
                mids = np.empty(n)
                mid = gen.current_mid
                mu = m.mu
                for t in range(n):
                    mid += m.kappa * (mu - mid) + m.sigma * dW[t]
                    mid = max(0.0, mid)
                    mids[t] = mid
                mid_sequences[m.symbol] = mids

        listings = {
            m.symbol: Listing(m.symbol, m.symbol, "XIRECS") for m in models
        }

        for tick_idx in range(self.n_ticks):
            timestamp = tick_idx * 100
            order_depths: Dict[str, OrderDepth] = {}
            market_trades: Dict[str, List[Trade]] = {}

            for m in models:
                sym = m.symbol
                gen = generators[sym]

                if self.mode == "bootstrap" and sym in bootstrap_sequences:
                    # Bootstrap mode: use resampled historical tick
                    tick_data = bootstrap_sequences[sym][tick_idx]
                    if self.bootstrap_gen is not None:
                        od = self.bootstrap_gen.generate_order_book(tick_data, sym)
                    else:
                        od = OrderDepth()
                    mid = tick_data.get("mid_price", m.fair_value) or m.fair_value
                else:
                    # Parametric mode
                    mid = mid_sequences[sym][tick_idx]
                    od = gen.generate_order_book(mid)

                order_depths[sym] = od
                last_mids[sym] = mid

                # Generate market trades
                mt = gen.generate_market_trades(mid, timestamp)
                if mt:
                    market_trades[sym] = mt

            # Inject named trader (Mark 01 / Mark 22) voucher activity
            if named_traders is not None:
                active_syms = [m.symbol for m in models]
                nt_trades = named_traders.generate_trades(active_syms, last_mids, timestamp)
                for sym, tlist in nt_trades.items():
                    if sym in market_trades:
                        market_trades[sym].extend(tlist)
                    else:
                        market_trades[sym] = tlist

            # Build own_trades from previous tick's fills
            own_trades: Dict[str, List[Trade]] = {}

            # Construct TradingState
            state = TradingState(
                traderData=trader_data,
                timestamp=timestamp,
                listings=listings,
                order_depths=order_depths,
                own_trades=own_trades,
                market_trades=market_trades,
                position=dict(positions),
                observations=Observation(),
            )

            # Run trader
            try:
                all_orders, conversions, trader_data = trader.run(state)
            except Exception:
                all_orders, conversions, trader_data = {}, 0, trader_data

            # Process fills
            tick_fills: Dict[str, List[Trade]] = {}
            for m in models:
                sym = m.symbol
                orders = all_orders.get(sym, [])
                if not orders:
                    continue

                # Shallow-copy the book dicts for matching (int→int, so safe)
                book_copy = OrderDepth()
                book_copy.buy_orders = order_depths[sym].buy_orders.copy()
                book_copy.sell_orders = order_depths[sym].sell_orders.copy()

                fills, new_pos, delta_pnl = fill_engine.match_orders(
                    orders, book_copy, positions[sym], m.position_limit,
                    m.make_fill_prob,
                )

                positions[sym] = new_pos
                cash_pnl[sym] += delta_pnl
                result.fills_by_product[sym] += len(fills)
                result.n_fills += len(fills)

                if fills:
                    tick_fills[sym] = fills

                # Track position stats
                abs_pos = abs(positions[sym])
                if abs_pos > result.max_position[sym]:
                    result.max_position[sym] = abs_pos
                position_sums[sym] += abs_pos

            # Mark-to-market PnL
            mtm_pnl = sum(cash_pnl[m.symbol] + positions[m.symbol] * last_mids[m.symbol]
                          for m in models)
            tick_pnls.append(mtm_pnl - cumulative_pnl if tick_idx > 0 else mtm_pnl)
            cumulative_pnl = mtm_pnl
            result.pnl_curve.append(cumulative_pnl)

            if cumulative_pnl > peak_pnl:
                peak_pnl = cumulative_pnl
            dd = peak_pnl - cumulative_pnl
            if dd > max_dd:
                max_dd = dd

        # Final stats
        result.total_pnl = cumulative_pnl
        result.terminal_pnl = cumulative_pnl
        result.max_drawdown = max_dd
        result.final_positions = dict(positions)

        for m in models:
            sym = m.symbol
            result.pnl_by_product[sym] = cash_pnl[sym] + positions[sym] * last_mids[sym]
            result.avg_position[sym] = position_sums[sym] / max(1, self.n_ticks)

        # Sharpe (annualized-ish: per-tick Sharpe * sqrt(ticks))
        if len(tick_pnls) > 1:
            arr = np.array(tick_pnls)
            mean_ret = np.mean(arr)
            std_ret = np.std(arr)
            if std_ret > 0:
                result.sharpe = (mean_ret / std_ret) * math.sqrt(len(tick_pnls))

        return result


# ---------------------------------------------------------------------------
# SECTION 7: Monte Carlo Runner & Analytics
# ---------------------------------------------------------------------------

@dataclass
class MonteCarloResult:
    """Aggregated results across all simulations."""
    n_sims: int
    results: List[SimResult]
    # Distributions
    pnl_mean: float = 0.0
    pnl_std: float = 0.0
    pnl_median: float = 0.0
    pnl_p5: float = 0.0            # 5th percentile (VaR 95%)
    pnl_p25: float = 0.0
    pnl_p75: float = 0.0
    pnl_p95: float = 0.0
    max_drawdown_mean: float = 0.0
    max_drawdown_p95: float = 0.0
    sharpe_mean: float = 0.0
    sharpe_std: float = 0.0
    win_rate: float = 0.0           # fraction of sims with positive PnL
    avg_fills: float = 0.0
    scenario_name: str = "baseline"

    def compute(self):
        pnls = np.array([r.total_pnl for r in self.results])
        dds = np.array([r.max_drawdown for r in self.results])
        sharpes = np.array([r.sharpe for r in self.results])
        fills = np.array([r.n_fills for r in self.results])

        self.pnl_mean = float(np.mean(pnls))
        self.pnl_std = float(np.std(pnls))
        self.pnl_median = float(np.median(pnls))
        self.pnl_p5 = float(np.percentile(pnls, 5))
        self.pnl_p25 = float(np.percentile(pnls, 25))
        self.pnl_p75 = float(np.percentile(pnls, 75))
        self.pnl_p95 = float(np.percentile(pnls, 95))
        self.max_drawdown_mean = float(np.mean(dds))
        self.max_drawdown_p95 = float(np.percentile(dds, 95))
        self.sharpe_mean = float(np.mean(sharpes))
        self.sharpe_std = float(np.std(sharpes))
        self.win_rate = float(np.mean(pnls > 0))
        self.avg_fills = float(np.mean(fills))


# ---------------------------------------------------------------------------
# Multiprocessing worker
# ---------------------------------------------------------------------------
_worker_engine: Optional[SimulationEngine] = None


def _init_worker(trader_path: str, models: List[ProductModel], n_ticks: int,
                 scenario: StressScenario, mode: str,
                 tte_start_days: float = 4.0, ticks_per_day: int = 10000,
                 enable_named_traders: bool = True):
    """Initializer for pool workers — sets up a per-process engine."""
    global _worker_engine
    TraderClass = load_trader(trader_path)
    _worker_engine = SimulationEngine(
        trader_class=TraderClass,
        models=models,
        n_ticks=n_ticks,
        scenario=scenario,
        mode=mode,
        tte_start_days=tte_start_days,
        ticks_per_day=ticks_per_day,
        enable_named_traders=enable_named_traders,
    )


def _run_one_sim(sim_seed: int) -> SimResult:
    """Worker function — runs a single sim using the process-global engine."""
    assert _worker_engine is not None
    return _worker_engine.run(sim_seed)


def run_montecarlo(
    trader_class,
    models: List[ProductModel],
    n_sims: int = 200,
    n_ticks: int = 10000,
    base_seed: int = 42,
    scenario: StressScenario = STRESS_SCENARIOS["baseline"],
    bootstrap_gen: Optional[BootstrapGenerator] = None,
    mode: str = "parametric",
    progress: bool = True,
    workers: int = 1,
    trader_path: str = "",
    tte_start_days: float = 4.0,
    ticks_per_day: int = 10000,
    enable_named_traders: bool = True,
) -> MonteCarloResult:
    """Run N simulations and aggregate results."""
    sim_seeds = [base_seed + i * 7919 for i in range(n_sims)]
    t0 = time.time()

    if workers > 1 and mode == "parametric":
        # Parallel execution via multiprocessing
        sys.stderr.write(f"  Using {workers} worker processes\n")
        sys.stderr.flush()
        with multiprocessing.Pool(
            processes=workers,
            initializer=_init_worker,
            initargs=(trader_path, models, n_ticks, scenario, mode,
                      tte_start_days, ticks_per_day, enable_named_traders),
        ) as pool:
            results: List[SimResult] = []
            for i, res in enumerate(pool.imap_unordered(_run_one_sim, sim_seeds)):
                results.append(res)
                if progress and (i + 1) % max(1, n_sims // 20) == 0:
                    elapsed = time.time() - t0
                    rate = (i + 1) / elapsed
                    eta = (n_sims - i - 1) / rate if rate > 0 else 0
                    sys.stderr.write(
                        f"\r  [{i+1}/{n_sims}] "
                        f"mean PnL={np.mean([r.total_pnl for r in results]):,.0f}  "
                        f"ETA {eta:.0f}s"
                    )
                    sys.stderr.flush()
    else:
        # Sequential execution
        engine = SimulationEngine(
            trader_class=trader_class,
            models=models,
            n_ticks=n_ticks,
            scenario=scenario,
            bootstrap_gen=bootstrap_gen,
            mode=mode,
            tte_start_days=tte_start_days,
            ticks_per_day=ticks_per_day,
            enable_named_traders=enable_named_traders,
        )
        results = []
        for i in range(n_sims):
            res = engine.run(sim_seeds[i])
            results.append(res)
            if progress and (i + 1) % max(1, n_sims // 20) == 0:
                elapsed = time.time() - t0
                rate = (i + 1) / elapsed
                eta = (n_sims - i - 1) / rate if rate > 0 else 0
                sys.stderr.write(
                    f"\r  [{i+1}/{n_sims}] "
                    f"mean PnL={np.mean([r.total_pnl for r in results]):,.0f}  "
                    f"ETA {eta:.0f}s"
                )
                sys.stderr.flush()

    if progress:
        sys.stderr.write("\n")
        sys.stderr.flush()

    mc = MonteCarloResult(n_sims=n_sims, results=results, scenario_name=scenario.name)
    mc.compute()
    return mc


# ---------------------------------------------------------------------------
# SECTION 8: Parameter Sweep
# ---------------------------------------------------------------------------

def parameter_sweep(
    trader_module_path: str,
    param_name: str,
    param_values: List[float],
    models: List[ProductModel],
    n_sims: int = 50,
    n_ticks: int = 5000,
    scenario: StressScenario = STRESS_SCENARIOS["baseline"],
) -> List[Tuple[float, MonteCarloResult]]:
    """Sweep a parameter by patching the trader source and re-running MC."""
    import importlib.util
    import re
    import tempfile

    source_path = Path(trader_module_path)
    original_source = source_path.read_text(encoding="utf-8")

    sweep_results = []

    for val in param_values:
        # Patch the source
        patched = re.sub(
            rf"({re.escape(param_name)}\s*[=:]\s*)[\d.]+",
            rf"\g<1>{val}",
            original_source,
        )

        # Write to temp file and load
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as tmp:
            tmp.write(patched)
            tmp_path = tmp.name

        try:
            spec = importlib.util.spec_from_file_location("trader_tmp", tmp_path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            trader_cls = mod.Trader

            sys.stderr.write(f"\n--- {param_name} = {val} ---\n")
            mc = run_montecarlo(
                trader_cls, models, n_sims=n_sims, n_ticks=n_ticks,
                scenario=scenario, progress=True,
            )
            sweep_results.append((val, mc))
        except Exception as e:
            sys.stderr.write(f"  ERROR at {param_name}={val}: {e}\n")
        finally:
            os.unlink(tmp_path)

    return sweep_results


# ---------------------------------------------------------------------------
# SECTION 9: Reporting
# ---------------------------------------------------------------------------

def print_report(mc: MonteCarloResult, header: str = ""):
    """Print a formatted MC report."""
    print("\n" + "=" * 72)
    if header:
        print(f"  {header}")
    print(f"  Scenario: {mc.scenario_name}  |  Sims: {mc.n_sims}")
    print("=" * 72)
    print(f"  {'PnL Mean':>18}: {mc.pnl_mean:>12,.1f}")
    print(f"  {'PnL Std':>18}: {mc.pnl_std:>12,.1f}")
    print(f"  {'PnL Median':>18}: {mc.pnl_median:>12,.1f}")
    print(f"  {'VaR 95% (P5)':>18}: {mc.pnl_p5:>12,.1f}")
    print(f"  {'P25':>18}: {mc.pnl_p25:>12,.1f}")
    print(f"  {'P75':>18}: {mc.pnl_p75:>12,.1f}")
    print(f"  {'P95':>18}: {mc.pnl_p95:>12,.1f}")
    print(f"  {'Win Rate':>18}: {mc.win_rate:>11.1%}")
    print(f"  {'Sharpe (mean)':>18}: {mc.sharpe_mean:>12.2f}")
    print(f"  {'Sharpe (std)':>18}: {mc.sharpe_std:>12.2f}")
    print(f"  {'MaxDD (mean)':>18}: {mc.max_drawdown_mean:>12,.1f}")
    print(f"  {'MaxDD (P95)':>18}: {mc.max_drawdown_p95:>12,.1f}")
    print(f"  {'Avg Fills':>18}: {mc.avg_fills:>12,.0f}")

    # Per-product breakdown
    if mc.results:
        products = mc.results[0].pnl_by_product.keys()
        for prod in products:
            pnls = [r.pnl_by_product.get(prod, 0) for r in mc.results]
            fills = [r.fills_by_product.get(prod, 0) for r in mc.results]
            avg_pos = [r.avg_position.get(prod, 0) for r in mc.results]
            max_pos = [r.max_position.get(prod, 0) for r in mc.results]
            print(f"\n  --- {prod} ---")
            print(f"    PnL:  mean={np.mean(pnls):,.0f}  std={np.std(pnls):,.0f}  "
                  f"p5={np.percentile(pnls, 5):,.0f}  p95={np.percentile(pnls, 95):,.0f}")
            print(f"    Fills: mean={np.mean(fills):.0f}  |  "
                  f"AvgPos: {np.mean(avg_pos):.1f}  MaxPos: {np.mean(max_pos):.0f}")

    print("=" * 72)


def print_sweep_report(sweep_results: List[Tuple[float, MonteCarloResult]], param_name: str):
    """Print parameter sweep summary."""
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
# SECTION 10: Data auto-discovery
# ---------------------------------------------------------------------------

def find_data_files(workspace_root: str) -> Dict[int, Dict[int, str]]:
    """Find all prices CSVs organized by round/day."""
    data_dirs = [
        os.path.join(workspace_root, "archive_r1r2", "round_data"),
        os.path.join(workspace_root, "round_data"),
        os.path.join(workspace_root, "backtester_data"),  # R3 data lives here
    ]
    found: Dict[int, Dict[int, str]] = {}  # {round: {day: filepath}}
    for data_dir in data_dirs:
        if not os.path.isdir(data_dir):
            continue
        for root, dirs, files in os.walk(data_dir):
            for f in files:
                if f.startswith("prices_round_") and f.endswith(".csv"):
                    # Parse round and day from filename
                    parts = f.replace(".csv", "").split("_")
                    try:
                        round_num = int(parts[2])
                        day_num = int(parts[4])
                        if round_num not in found:
                            found[round_num] = {}
                        found[round_num][day_num] = os.path.join(root, f)
                    except (IndexError, ValueError):
                        pass
    return found


def load_all_historical(workspace_root: str) -> Dict[str, List[dict]]:
    """Load and merge all available historical price data."""
    data_files = find_data_files(workspace_root)
    merged: Dict[str, List[dict]] = defaultdict(list)
    for round_num in sorted(data_files.keys()):
        for day_num in sorted(data_files[round_num].keys()):
            filepath = data_files[round_num][day_num]
            try:
                products = load_prices_csv(filepath)
                for sym, ticks in products.items():
                    merged[sym].extend(ticks)
            except Exception as e:
                sys.stderr.write(f"Warning: failed to load {filepath}: {e}\n")
    return dict(merged)


# ---------------------------------------------------------------------------
# SECTION 11: Import the actual Trader class
# ---------------------------------------------------------------------------

def load_trader(trader_path: str):
    """Dynamically load a Trader class from a .py file."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("submission_module", trader_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.Trader


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="IMC Prosperity 4 Monte Carlo Simulator")
    parser.add_argument("--trader", type=str, default="submissionr4.py",
                        help="Path to trader .py file (default: submissionr4.py)")
    parser.add_argument("--sims", type=int, default=200,
                        help="Number of simulations")
    parser.add_argument("--ticks", type=int, default=10000,
                        help=(
                            "Ticks per simulation. "
                            "10000 = full backtester day; 2000 = platform-realistic."
                        ))
    parser.add_argument("--mode", choices=["parametric", "bootstrap"], default=None,
                        help=(
                            "Data generation mode. Default: bootstrap for R3/R4 "
                            "(uses real ticks), parametric for R1/R2."
                        ))
    parser.add_argument("--stress", type=str, default=None,
                        help=f"Stress scenario: {', '.join(STRESS_SCENARIOS.keys())}")
    parser.add_argument("--stress-all", action="store_true",
                        help="Run all stress scenarios")
    parser.add_argument("--seed", type=int, default=42,
                        help="Base random seed")
    parser.add_argument("--sweep", nargs=4, metavar=("PARAM", "MIN", "MAX", "N"),
                        help="Parameter sweep: PARAM MIN MAX N_STEPS")
    parser.add_argument("--quiet", action="store_true",
                        help="Suppress progress output")
    parser.add_argument("--workers", "-j", type=int, default=1,
                        help="Number of parallel worker processes (default: 1)")
    parser.add_argument("--round", type=int, default=4, choices=[1, 2, 3, 4],
                        help="Competition round (default: 4). Rounds 3 and 4 share the same instruments.")
    parser.add_argument("--tte-days", type=float, default=4.0,
                        help=(
                            "Initial time-to-expiry for VEV vouchers in trading days "
                            "(default: 4.0 ≈ R4 live; backtester: day1=7, day2=6, day3=5)."
                        ))
    parser.add_argument("--no-named-traders", action="store_true",
                        help="Disable Mark 01/22 named trader injection in parametric mode.")
    parser.add_argument("--manual", action="store_true",
                        help=(
                            "Print Celestial Gardeners' Guild manual challenge analysis "
                            "(optimal bid1/bid2 for various avg-competitor assumptions). "
                            "Can be combined with --sims to also run the MC."
                        ))
    args = parser.parse_args()

    # --manual: print Celestial Gardeners' Guild analysis (standalone or combined)
    if args.manual:
        print_manual_challenge_analysis()
        trader_path_default = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), args.trader
        ) if not os.path.isabs(args.trader) else args.trader
        if not os.path.exists(trader_path_default):
            return   # manual-only mode; trader not available

    # Resolve paths
    workspace = os.path.dirname(os.path.abspath(__file__))
    trader_path = os.path.join(workspace, args.trader) if not os.path.isabs(args.trader) else args.trader

    # Determine mode: bootstrap by default for R3/R4, parametric for R1/R2
    if args.mode is not None:
        mode = args.mode
    elif args.round in (3, 4):
        mode = "bootstrap"
    else:
        mode = "parametric"

    # Load trader
    sys.stderr.write(f"Loading trader from {trader_path}...\n")
    TraderClass = load_trader(trader_path)

    # Build product models — calibrate from historical data when available
    historical = load_all_historical(workspace)
    models = []

    enable_named_traders = (args.round in (3, 4)) and not args.no_named_traders

    if args.round in (3, 4):
        # -------------------------------------------------------------------
        # Rounds 3 and 4: HYDROGEL_PACK + VELVETFRUIT_EXTRACT + 10 VEV vouchers
        # -------------------------------------------------------------------
        _SPOT_PRODUCTS = [
            ("HYDROGEL_PACK",       "fixed_value", 200, 0.015),
            ("VELVETFRUIT_EXTRACT", "random_walk", 200, 0.018),
        ]
        _VEV_STRIKES = [4000, 4500, 5000, 5100, 5200, 5300, 5400, 5500, 6000, 6500]

        # --- Spot products (HGP, VFE) ---
        for sym, ptype, pos_lim, fill_prob in _SPOT_PRODUCTS:
            if sym in historical and len(historical[sym]) > 100:
                stats = extract_stats(historical[sym], sym)
                m = ProductModel.from_stats(stats, product_type=ptype, position_limit=pos_lim)
                m.make_fill_prob = fill_prob
                if ptype == "fixed_value":
                    m.mu = float(np.mean(stats.mid_prices))
                    m.fair_value = m.mu
                    m.drift = 0.0  # HGP: keep drift-neutral for generality
                else:
                    m.drift = 0.0  # VFE: neutral drift default
                sys.stderr.write(
                    f"  {sym}: calibrated from {len(stats.mid_prices)} ticks "
                    f"(sigma={m.sigma:.3f}, spread={m.spread_mean:.2f}, "
                    f"drift={m.drift:.5f})\n"
                )
            else:
                m = (ProductModel.default_hydrogel_pack() if sym == "HYDROGEL_PACK"
                     else ProductModel.default_velvetfruit_extract())
                sys.stderr.write(f"  {sym}: using default R4-calibrated model\n")
            models.append(m)

        # --- VFE reference price and TTE for IV calibration ---
        vfe_hist = historical.get("VELVETFRUIT_EXTRACT", [])
        vfe_first_mid = 5245.0  # R4/R3 starting price
        if vfe_hist:
            t0 = vfe_hist[0]
            bp = t0.get("bid_price_1") or 0.0
            ap = t0.get("ask_price_1") or 0.0
            if bp and ap:
                vfe_first_mid = (bp + ap) / 2.0
            elif t0.get("mid_price"):
                vfe_first_mid = float(t0["mid_price"])
        tte_years_calib = args.tte_days / 252.0

        # --- VEV vouchers (BS-priced in parametric mode) ---
        for strike in _VEV_STRIKES:
            sym = f"VEV_{strike}"
            m = ProductModel.default_vev(float(strike), position_limit=300)

            if sym in historical and len(historical[sym]) > 100:
                # Calibrate spread and volume from empirical data
                stats = extract_stats(historical[sym], sym)
                m.spread_mean = stats.spread_mean if stats.spread_mean > 0 else m.spread_mean
                m.spread_std = stats.spread_std if stats.spread_std > 0 else m.spread_std
                m.vol_mean = stats.vol_mean if stats.vol_mean > 0 else m.vol_mean
                m.vol_std = stats.vol_std if stats.vol_std > 0 else m.vol_std

                # Calibrate per-strike implied vol from the first observed price
                t0_tick = historical[sym][0]
                bp0 = t0_tick.get("bid_price_1") or 0.0
                ap0 = t0_tick.get("ask_price_1") or 0.0
                first_price = (bp0 + ap0) / 2.0 if bp0 and ap0 else (t0_tick.get("mid_price") or 0.0)
                if first_price and first_price > 0 and vfe_first_mid > 0 and tte_years_calib > 0:
                    calib_iv = bs_iv(float(first_price), vfe_first_mid, float(strike), tte_years_calib)
                    m.implied_vol_annual = max(0.05, min(5.0, calib_iv))
                # Also update sigma for OU fallback (proportional to first price)
                first_ret_std = stats.volatility if stats.volatility > 0 else 0.5
                m.sigma = max(0.05, first_ret_std)
                # Reset fair_value to empirical BS
                m.fair_value = max(0.0, bs_call(vfe_first_mid, float(strike), tte_years_calib, m.implied_vol_annual))
                m.mu = m.fair_value

                sys.stderr.write(
                    f"  {sym}: IV={m.implied_vol_annual:.3f}  fv={m.fair_value:.2f}  "
                    f"spread={m.spread_mean:.2f}  (from {len(stats.mid_prices)} ticks)\n"
                )
            else:
                sys.stderr.write(
                    f"  {sym}: default_vev  IV={m.implied_vol_annual:.3f}  fv={m.fair_value:.2f}\n"
                )
            models.append(m)

    else:
        # -------------------------------------------------------------------
        # Rounds 1 / 2: ASH_COATED_OSMIUM + INTARIAN_PEPPER_ROOT
        # -------------------------------------------------------------------
        if "ASH_COATED_OSMIUM" in historical and len(historical["ASH_COATED_OSMIUM"]) > 100:
            stats = extract_stats(historical["ASH_COATED_OSMIUM"], "ASH_COATED_OSMIUM")
            m = ProductModel.from_stats(stats, product_type="fixed_value", position_limit=80)
            m.mu = 10000.0
            m.fair_value = 10000.0
            m.make_fill_prob = 0.014
            sys.stderr.write(f"  ACO: calibrated from {len(stats.mid_prices)} ticks "
                             f"(sigma={m.sigma:.2f}, spread={m.spread_mean:.1f})\n")
            models.append(m)
        else:
            sys.stderr.write("  ACO: using default model\n")
            models.append(ProductModel.default_aco())

        if "INTARIAN_PEPPER_ROOT" in historical and len(historical["INTARIAN_PEPPER_ROOT"]) > 100:
            stats = extract_stats(historical["INTARIAN_PEPPER_ROOT"], "INTARIAN_PEPPER_ROOT")
            m = ProductModel.from_stats(stats, product_type="random_walk", position_limit=80)
            m.make_fill_prob = 0.033
            sys.stderr.write(f"  IPR: calibrated from {len(stats.mid_prices)} ticks "
                             f"(sigma={m.sigma:.2f}, drift={m.drift:.4f}, spread={m.spread_mean:.1f})\n")
            models.append(m)
        else:
            sys.stderr.write("  IPR: using default model\n")
            models.append(ProductModel.default_ipr())

    # Bootstrap generator
    bootstrap_gen = None
    if mode == "bootstrap" and historical:
        bootstrap_gen = BootstrapGenerator(
            historical_data=historical,
            block_size=50,
            noise_scale=0.5,
        )
        # Verify bootstrap has data for all requested products
        missing = [m.symbol for m in models if m.symbol not in historical]
        if missing:
            sys.stderr.write(
                f"  WARNING: bootstrap missing data for {missing}; "
                f"these will fall back to parametric.\n"
            )

    sys.stderr.write(
        f"Mode: {mode}  |  Round: {args.round}  |  TTE: {args.tte_days:.1f}d  |  "
        f"Named traders: {enable_named_traders}\n"
    )

    # Parameter sweep mode
    if args.sweep:
        param_name = args.sweep[0]
        param_min = float(args.sweep[1])
        param_max = float(args.sweep[2])
        n_steps = int(args.sweep[3])
        param_values = list(np.linspace(param_min, param_max, n_steps))
        scenario = STRESS_SCENARIOS.get(args.stress, STRESS_SCENARIOS["baseline"])
        sweep_results = parameter_sweep(
            trader_path, param_name, param_values, models,
            n_sims=min(50, args.sims), n_ticks=min(5000, args.ticks),
            scenario=scenario,
        )
        print_sweep_report(sweep_results, param_name)
        return

    # Stress-all mode
    if args.stress_all:
        for scenario_name, scenario in STRESS_SCENARIOS.items():
            sys.stderr.write(f"\n>>> Scenario: {scenario_name}\n")
            mc = run_montecarlo(
                TraderClass, models, n_sims=args.sims, n_ticks=args.ticks,
                base_seed=args.seed, scenario=scenario,
                bootstrap_gen=bootstrap_gen, mode=mode,
                progress=not args.quiet,
                workers=args.workers, trader_path=trader_path,
                tte_start_days=args.tte_days,
                enable_named_traders=enable_named_traders,
            )
            print_report(mc, f"MONTE CARLO — {scenario_name.upper()}")
        return

    # Single scenario
    scenario = STRESS_SCENARIOS.get(args.stress, STRESS_SCENARIOS["baseline"])
    sys.stderr.write(f"Running {args.sims} sims × {args.ticks} ticks "
                     f"[{mode}, {scenario.name}]...\n")

    mc = run_montecarlo(
        TraderClass, models, n_sims=args.sims, n_ticks=args.ticks,
        base_seed=args.seed, scenario=scenario,
        bootstrap_gen=bootstrap_gen, mode=mode,
        progress=not args.quiet,
        workers=args.workers, trader_path=trader_path,
        tte_start_days=args.tte_days,
        enable_named_traders=enable_named_traders,
    )
    print_report(mc, "MONTE CARLO SIMULATION RESULTS")

    # Save raw results to JSON
    out_path = os.path.join(workspace, "montecarlo_results.json")
    summary = {
        "n_sims": mc.n_sims,
        "scenario": mc.scenario_name,
        "mode": mode,
        "round": args.round,
        "n_ticks": args.ticks,
        "tte_start_days": args.tte_days,
        "enable_named_traders": enable_named_traders,
        "pnl_mean": mc.pnl_mean,
        "pnl_std": mc.pnl_std,
        "pnl_median": mc.pnl_median,
        "pnl_p5": mc.pnl_p5,
        "pnl_p25": mc.pnl_p25,
        "pnl_p75": mc.pnl_p75,
        "pnl_p95": mc.pnl_p95,
        "sharpe_mean": mc.sharpe_mean,
        "sharpe_std": mc.sharpe_std,
        "win_rate": mc.win_rate,
        "max_drawdown_mean": mc.max_drawdown_mean,
        "max_drawdown_p95": mc.max_drawdown_p95,
        "avg_fills": mc.avg_fills,
        "per_sim_pnl": [r.total_pnl for r in mc.results],
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    sys.stderr.write(f"Results saved to {out_path}\n")


if __name__ == "__main__":
    main()
