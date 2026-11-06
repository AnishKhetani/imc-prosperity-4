"""
IMC Prosperity 4 - Round 3 Submission
=====================================
Strategies based on EDA of Round 3 data:

1. HGP (HYDROGEL_PACK) Market Making:
   - Fixed fair value = 10000 (structural mean-reversion anchor)
   - Adaptive EMA to track short-term drift
   - OFI-adjusted quotes, spread ~16, position limit 200
   - Estimated PnL: ~16k/round

2. VFE (VELVETFRUIT_EXTRACT) Market Making:
   - EMA fair value tracker (mean-reverts within ~5250 range)
   - OFI skew (lag-1 corr 0.32), spread ~5, position limit 200
   - Estimated PnL: ~10k/round

3. VEV Options MM (strikes 5200-5500):
   - Real-time Black-Scholes pricing using VFE as underlying
   - sigma=0.05 calibrated from EDA, T decreasing over tournament
   - Quote +-1 around BS fair, delta-hedge with VFE
   - Position limit per option: 300

4. Deep OTM Options (VEV_6000, VEV_6500):
   - VFE historically maxes at ~5300, strikes 6000/6500 essentially worthless
   - Sell at best available price (0.5+), never buy
   - Near risk-free premium collection

5. Deep ITM Options (VEV_4000, VEV_4500):
   - delta ~ 1.0, acts as VFE forward
   - Buy when ask < (VFE - K) i.e. below intrinsic value
   - Hedge delta with VFE short

Position limits: VFE=200, HGP=200, VEV_*=300 each
"""

from __future__ import annotations

import json
import math
from typing import Any, Dict, List, Optional, Tuple

from datamodel import (
    Listing, Observation, Order, OrderDepth, ConversionObservation,
    Trade, TradingState, Symbol, Product, Position,
)

# ---------------------------------------------------------------------------
# Logger (visualizer-compatible compressed JSON)
# ---------------------------------------------------------------------------

MAX_LOG_LENGTH = 3750


class Logger:
    def __init__(self):
        self._logs = ""

    def print(self, *args: Any, **kwargs: Any) -> None:
        self._logs += " ".join(str(a) for a in args) + "\n"

    def flush(self, state: TradingState, orders: Dict[str, List[Order]],
              conversions: int, trader_data: str) -> None:
        output = json.dumps([
            self._compress_state(state),
            self._compress_orders(orders),
            conversions,
            trader_data[:500] if trader_data else "",
            self._logs.rstrip(),
        ], separators=(",", ":"))
        if len(output) > MAX_LOG_LENGTH:
            half = (MAX_LOG_LENGTH - 3) // 2
            output = output[:half] + "..." + output[-half:]
        print(output)
        self._logs = ""

    def _compress_state(self, state: TradingState) -> list:
        listings = {sym: [l.symbol, l.product, l.denomination]
                    for sym, l in state.listings.items()}
        order_depths = {sym: [od.buy_orders, od.sell_orders]
                        for sym, od in state.order_depths.items()}
        own_trades = {
            sym: [[t.symbol, t.price, t.quantity, t.buyer or "", t.seller or "", t.timestamp]
                  for t in trades]
            for sym, trades in state.own_trades.items()
        }
        market_trades = {
            sym: [[t.symbol, t.price, t.quantity, t.buyer or "", t.seller or "", t.timestamp]
                  for t in trades]
            for sym, trades in state.market_trades.items()
        }
        obs = {}
        if state.observations:
            obs["plain"] = state.observations.plainValueObservations
            obs["conv"] = {
                sym: {"bid": co.bidPrice, "ask": co.askPrice,
                      "transport": co.transportFees, "export": co.exportTariff,
                      "import": co.importTariff}
                for sym, co in state.observations.conversionObservations.items()
            }
        return [state.timestamp, state.traderData[:500] if state.traderData else "",
                listings, order_depths, own_trades, market_trades, state.position, obs]

    def _compress_orders(self, orders: Dict[str, List[Order]]) -> dict:
        return {sym: [[o.symbol, o.price, o.quantity] for o in ol]
                for sym, ol in orders.items()}


logger = Logger()

# ---------------------------------------------------------------------------
# Black-Scholes helpers
# ---------------------------------------------------------------------------

TOTAL_TICKS = 999_900 * 3   # 3 days total tournament duration


def _norm_cdf(x: float) -> float:
    """Standard normal CDF (Abramowitz & Stegun approximation)."""
    a1, a2, a3, a4, a5 = 0.319381530, -0.356563782, 1.781477937, -1.821255978, 1.330274429
    k = 1.0 / (1.0 + 0.2316419 * abs(x))
    poly = k * (a1 + k * (a2 + k * (a3 + k * (a4 + k * a5))))
    cdf = 1.0 - (1.0 / math.sqrt(2 * math.pi)) * math.exp(-0.5 * x * x) * poly
    return cdf if x >= 0 else 1.0 - cdf


def bs_call(S: float, K: float, T: float, sigma: float) -> float:
    """Black-Scholes European call price. Returns intrinsic if T<=0 or sigma<=0."""
    intrinsic = max(0.0, S - K)
    if T <= 1e-6 or sigma <= 1e-6:
        return intrinsic
    sqrt_T = math.sqrt(T)
    d1 = (math.log(S / K) + 0.5 * sigma * sigma * T) / (sigma * sqrt_T)
    d2 = d1 - sigma * sqrt_T
    return S * _norm_cdf(d1) - K * _norm_cdf(d2)


def bs_delta(S: float, K: float, T: float, sigma: float) -> float:
    """BS call delta in [0,1]."""
    if T <= 1e-6 or sigma <= 1e-6:
        return 1.0 if S > K else 0.0
    sqrt_T = math.sqrt(T)
    d1 = (math.log(S / K) + 0.5 * sigma * sigma * T) / (sigma * sqrt_T)
    return _norm_cdf(d1)


# ---------------------------------------------------------------------------
# Strategy base class
# ---------------------------------------------------------------------------


class Strategy:
    def __init__(self, symbol: str, position_limit: int, soft_limit: Optional[int] = None):
        self.symbol = symbol
        self.position_limit = position_limit
        self.soft_limit = soft_limit if soft_limit is not None else position_limit

    def act(self, state: TradingState) -> List[Order]:
        raise NotImplementedError

    def get_position(self, state: TradingState) -> int:
        return state.position.get(self.symbol, 0)

    def buy(self, price: int, qty: int, position: int) -> Optional[Order]:
        capacity = self.position_limit - position
        clipped = min(qty, capacity)
        return Order(self.symbol, price, clipped) if clipped > 0 else None

    def sell(self, price: int, qty: int, position: int) -> Optional[Order]:
        capacity = self.position_limit + position
        clipped = min(qty, capacity)
        return Order(self.symbol, price, -clipped) if clipped > 0 else None

    def soft_buy(self, price: int, qty: int, position: int) -> Optional[Order]:
        capacity = self.soft_limit - position
        clipped = min(qty, capacity)
        return Order(self.symbol, price, clipped) if clipped > 0 else None

    def soft_sell(self, price: int, qty: int, position: int) -> Optional[Order]:
        capacity = self.soft_limit + position
        clipped = min(qty, capacity)
        return Order(self.symbol, price, -clipped) if clipped > 0 else None

    def get_od(self, state: TradingState) -> OrderDepth:
        return state.order_depths.get(self.symbol, OrderDepth())

    @staticmethod
    def best_bid(od: OrderDepth) -> Optional[int]:
        return max(od.buy_orders) if od.buy_orders else None

    @staticmethod
    def best_ask(od: OrderDepth) -> Optional[int]:
        return min(od.sell_orders) if od.sell_orders else None

    def save(self) -> dict:
        return {}

    def load(self, data: dict) -> None:
        pass


# ---------------------------------------------------------------------------
# Strategy 1: HYDROGEL_PACK (HGP) Market Maker
# ---------------------------------------------------------------------------


class HGPStrategy(Strategy):
    """
    HGP mean-reverts around 10000. EMA tracks short-term fair.
    OFI (order-flow imbalance) tilts quote skew.
    Inventory tiers control aggression.
    """
    FIXED_FAIR = 10000.0
    EMA_ALPHA = 2.0 / 16         # window ~15
    SPREAD_ALPHA = 2.0 / 20
    OFI_WEIGHT = 1.5             # OFI -> fair adjustment ticks
    SOFT_LIMIT = 150
    POSITION_LIMIT = 200

    def __init__(self):
        super().__init__("HYDROGEL_PACK", self.POSITION_LIMIT, self.SOFT_LIMIT)
        self.ema_fair: Optional[float] = None
        self.ema_spread: Optional[float] = None
        self._last_bid: Optional[int] = None
        self._last_ask: Optional[int] = None

    def act(self, state: TradingState) -> List[Order]:
        od = self.get_od(state)
        if not od.buy_orders or not od.sell_orders:
            return []
        position = self.get_position(state)

        bb = self.best_bid(od)
        ba = self.best_ask(od)
        mid = (bb + ba) / 2.0
        spread = ba - bb

        if self.ema_spread is None:
            self.ema_spread = float(spread)
        else:
            self.ema_spread = self.SPREAD_ALPHA * spread + (1 - self.SPREAD_ALPHA) * self.ema_spread

        if self.ema_fair is None:
            self.ema_fair = mid
        else:
            self.ema_fair = self.EMA_ALPHA * mid + (1 - self.EMA_ALPHA) * self.ema_fair

        # Pull EMA toward fixed fair 10000 to prevent long-run drift
        self.ema_fair = 0.02 * self.FIXED_FAIR + 0.98 * self.ema_fair

        bv = od.buy_orders[bb]
        av = abs(od.sell_orders[ba])
        total = bv + av
        ofi = (bv - av) / total if total > 0 else 0.0

        fair = self.ema_fair + self.OFI_WEIGHT * ofi

        orders: List[Order] = []

        # --- Phase 1: TAKE mispriced levels ---
        for ask_p in sorted(od.sell_orders):
            ask_v = abs(od.sell_orders[ask_p])
            if ask_p < fair - 1:
                o = self.soft_buy(ask_p, ask_v, position)
                if o:
                    orders.append(o)
                    position += o.quantity
            elif ask_p <= fair and position < -20:
                # close short even at fair
                o = self.soft_buy(ask_p, ask_v, position)
                if o:
                    orders.append(o)
                    position += o.quantity

        for bid_p in sorted(od.buy_orders, reverse=True):
            bid_v = od.buy_orders[bid_p]
            if bid_p > fair + 1:
                o = self.soft_sell(bid_p, bid_v, position)
                if o:
                    orders.append(o)
                    position -= o.quantity
            elif bid_p >= fair and position > 20:
                # close long even at fair
                o = self.soft_sell(bid_p, bid_v, position)
                if o:
                    orders.append(o)
                    position -= o.quantity

        # --- Phase 2: MAKE quotes inside book ---
        # Inventory skew: when long -> lower bid, when short -> raise ask
        inv_skew = position / self.position_limit  # [-1, 1]
        bid_skew = -round(inv_skew * 3)   # negative when long
        ask_skew = -round(inv_skew * 3)   # positive when long

        make_bid = int(fair) - 1 + bid_skew
        make_ask = int(fair) + 1 + ask_skew

        # Clamp inside bot book
        bot_bid = max(od.buy_orders)
        bot_ask = min(od.sell_orders)
        make_bid = max(make_bid, bot_bid + 1)
        make_ask = min(make_ask, bot_ask - 1)
        # Ensure spread > 0
        if make_bid >= make_ask:
            make_bid = int(fair) - 1
            make_ask = int(fair) + 1

        max_buy = self.soft_limit - position
        max_sell = self.soft_limit + position
        if max_buy > 0 and make_bid >= bot_bid + 1:
            orders.append(Order(self.symbol, make_bid, max_buy))
        if max_sell > 0 and make_ask <= bot_ask - 1:
            orders.append(Order(self.symbol, make_ask, -max_sell))

        self._last_bid = make_bid
        self._last_ask = make_ask
        return orders

    def save(self) -> dict:
        return {"ef": self.ema_fair, "es": self.ema_spread}

    def load(self, data: dict) -> None:
        self.ema_fair = data.get("ef")
        self.ema_spread = data.get("es")


# ---------------------------------------------------------------------------
# Strategy 2: VELVETFRUIT_EXTRACT (VFE) Market Maker
# ---------------------------------------------------------------------------


class VFEStrategy(Strategy):
    """
    VFE: spread=5, drifts +20-28 per day.
    Use FAST EMA (window~6) to follow drift tightly.
    Only take very clear mispricings (>2 ticks), make inside bot spread.
    Inventory skew strongly to avoid being caught short in rising market.
    """
    EMA_ALPHA = 2.0 / 6          # window ~5: fast enough to follow drift
    OFI_WEIGHT = 0.5
    SOFT_LIMIT = 120
    POSITION_LIMIT = 200

    def __init__(self):
        super().__init__("VELVETFRUIT_EXTRACT", self.POSITION_LIMIT, self.SOFT_LIMIT)
        self.ema_fair: Optional[float] = None

    def act(self, state: TradingState) -> List[Order]:
        od = self.get_od(state)
        if not od.buy_orders or not od.sell_orders:
            return []
        position = self.get_position(state)

        bb = self.best_bid(od)
        ba = self.best_ask(od)
        bv = od.buy_orders[bb]
        av = abs(od.sell_orders[ba])
        total = bv + av
        wmid = (bb * av + ba * bv) / total if total > 0 else (bb + ba) / 2.0
        ofi = (bv - av) / total if total > 0 else 0.0

        if self.ema_fair is None:
            self.ema_fair = wmid
        else:
            self.ema_fair = self.EMA_ALPHA * wmid + (1 - self.EMA_ALPHA) * self.ema_fair

        fair = self.ema_fair + self.OFI_WEIGHT * ofi

        orders: List[Order] = []

        # --- Phase 1: TAKE only clear mispricings (>2 ticks) ---
        for ask_p in sorted(od.sell_orders):
            ask_v = abs(od.sell_orders[ask_p])
            if ask_p < fair - 2:
                o = self.soft_buy(ask_p, ask_v, position)
                if o:
                    orders.append(o)
                    position += o.quantity

        for bid_p in sorted(od.buy_orders, reverse=True):
            bid_v = od.buy_orders[bid_p]
            if bid_p > fair + 2:
                o = self.soft_sell(bid_p, bid_v, position)
                if o:
                    orders.append(o)
                    position -= o.quantity

        # --- Phase 2: MAKE 1 tick inside bot spread ---
        bot_bid = max(od.buy_orders)
        bot_ask = min(od.sell_orders)

        # Strong inventory skew: don't short into rising market
        inv_skew = position / self.position_limit  # [-1, 1]
        # bid skew: lower bids when long (don't accumulate more)
        # ask skew: raise asks when short (don't sell into drift)
        bid_adj = -round(inv_skew * 3)
        ask_adj = -round(inv_skew * 3)

        make_bid = int(bot_bid + 1) + bid_adj
        make_ask = int(bot_ask - 1) + ask_adj

        # Clamp to fair value bounds (never quote past fair)
        make_bid = min(make_bid, int(fair))
        make_ask = max(make_ask, int(fair) + 1)
        make_bid = max(make_bid, bot_bid + 1)
        make_ask = min(make_ask, bot_ask - 1)
        if make_bid >= make_ask:
            make_bid = bot_bid + 1
            make_ask = bot_ask - 1

        max_buy = self.soft_limit - position
        max_sell = self.soft_limit + position
        if max_buy > 0 and make_bid >= bot_bid + 1 and make_bid < make_ask:
            orders.append(Order(self.symbol, make_bid, max_buy))
        if max_sell > 0 and make_ask <= bot_ask - 1 and make_bid < make_ask:
            orders.append(Order(self.symbol, make_ask, -max_sell))

        return orders

    def save(self) -> dict:
        return {"ef": self.ema_fair}

    def load(self, data: dict) -> None:
        self.ema_fair = data.get("ef")


# ---------------------------------------------------------------------------
# Strategy 3: VEV Options Market Maker (strikes 5200-5500)
# ---------------------------------------------------------------------------

# IV by strike — calibrated from platform log 371903 (actual platform IVs)
# ATM strikes (5000-5500) consistently show ~3.1-3.2% IV on the platform
# Deep ITM (4000, 4500) are essentially at intrinsic (not quoted by BS here)
IV_BY_STRIKE: Dict[int, float] = {
    5000: 0.031,
    5100: 0.031,
    5200: 0.032,
    5300: 0.032,
    5400: 0.030,
    5500: 0.032,
}
BASE_IV = 0.032
IV_DRIFT_PER_TICK = 0.0  # IV is very stable across the day (confirmed from log)

# Day tracking constants
TICKS_PER_DAY = 999_900   # max timestamp per day on backtester
PLATFORM_TICKS_PER_DAY = 99_900  # on platform, day runs 0..99900
N_DAYS = 3


class VEVMMStrategy(Strategy):
    """
    ATM options market maker (VEV_5200 to VEV_5500).
    Uses EMA of market mid as fair value — avoids BS model risk.
    The market mid is the true signal; we just earn the spread.
    """
    EMA_ALPHA = 2 / 10           # moderate smoothing
    QUOTE_WIDTH = 1.5            # quote ±1.5 around fair (market spread is ~3-5)
    POSITION_LIMIT = 300
    SOFT_LIMIT = 100

    def __init__(self, strike: int, vfe_strategy: VFEStrategy):
        symbol = f"VEV_{strike}"
        super().__init__(symbol, self.POSITION_LIMIT, self.SOFT_LIMIT)
        self.strike = strike
        self.vfe = vfe_strategy
        self.fair: Optional[float] = None

    def act(self, state: TradingState) -> List[Order]:
        od = self.get_od(state)
        if not od.buy_orders or not od.sell_orders:
            return []

        position = self.get_position(state)
        bb = self.best_bid(od)
        ba = self.best_ask(od)
        mid = (bb + ba) / 2.0

        # EMA of market mid
        if self.fair is None:
            self.fair = mid
        else:
            self.fair = self.EMA_ALPHA * mid + (1 - self.EMA_ALPHA) * self.fair
        fair = self.fair

        # Inventory skew: push quotes away from our position
        inv_skew = position / self.soft_limit
        skew = round(inv_skew * 2)

        bid_p = int(math.floor(fair - self.QUOTE_WIDTH)) - skew
        ask_p = int(math.ceil(fair + self.QUOTE_WIDTH)) - skew
        bid_p = max(1, min(bid_p, bb + 1))
        ask_p = max(ask_p, ba - 1)
        if ask_p <= bid_p:
            ask_p = bid_p + 1

        orders: List[Order] = []

        # Take when market is clearly off our fair
        if ba < fair - 1.0:
            o = self.soft_buy(ba, abs(od.sell_orders[ba]), position)
            if o:
                orders.append(o)
                position += o.quantity

        if bb > fair + 1.0:
            o = self.soft_sell(bb, od.buy_orders[bb], position)
            if o:
                orders.append(o)
                position -= o.quantity

        # Make quotes
        max_buy = self.soft_limit - position
        max_sell = self.soft_limit + position
        if max_buy > 0 and bid_p > 0:
            orders.append(Order(self.symbol, bid_p, max_buy))
        if max_sell > 0:
            orders.append(Order(self.symbol, ask_p, -max_sell))

        return orders

    def save(self) -> dict:
        return {"fair": self.fair}

    def load(self, data: dict) -> None:
        if "fair" in data:
            self.fair = data["fair"]


# ---------------------------------------------------------------------------
# Strategy 4: Deep OTM Options (VEV_6000, VEV_6500)
# ---------------------------------------------------------------------------


class DeepOTMStrategy(Strategy):
    """
    VEV_6000 and VEV_6500 are structurally worthless (VFE max ~5300 << 6000).
    Only SELL at whatever price the market offers (>= 0.5).
    Never buy.
    """
    POSITION_LIMIT = 300
    MIN_SELL_PRICE = 1           # at least 1 tick profit

    def __init__(self, strike: int):
        super().__init__(f"VEV_{strike}", self.POSITION_LIMIT, self.POSITION_LIMIT)
        self.strike = strike

    def act(self, state: TradingState) -> List[Order]:
        od = self.get_od(state)
        if not od.buy_orders:
            return []
        position = self.get_position(state)
        orders: List[Order] = []

        # Sell into all bids >= MIN_SELL_PRICE
        for bid_p in sorted(od.buy_orders, reverse=True):
            if bid_p < self.MIN_SELL_PRICE:
                break
            bid_v = od.buy_orders[bid_p]
            o = self.sell(bid_p, bid_v, position)
            if o:
                orders.append(o)
                position -= o.quantity

        # Also post passive sell at best bid (aggressive)
        if od.buy_orders:
            bb = max(od.buy_orders)
            if bb >= self.MIN_SELL_PRICE:
                remaining_sell = self.position_limit + position
                if remaining_sell > 0:
                    # only if not already added
                    already = sum(abs(o.quantity) for o in orders)
                    extra = remaining_sell - already
                    if extra > 0:
                        orders.append(Order(self.symbol, bb, -extra))

        return orders


# ---------------------------------------------------------------------------
# Strategy 5: Deep ITM Options (VEV_4000, VEV_4500) — Intrinsic Arb
# ---------------------------------------------------------------------------


class DeepITMStrategy(Strategy):
    """
    Deep ITM calls (VEV_4000, VEV_4500) priced near intrinsic = VFE - K.
    Market makers both sides: buy at intrinsic-spread/2, sell at intrinsic+spread/2.
    The platform spread for VEV_4000 is ~22, VEV_4500 ~16, so we earn half-spread.
    Delta ~1.0 so VFE MM naturally hedges us.
    """
    POSITION_LIMIT = 300
    SOFT_LIMIT = 60   # smaller soft limit — deep ITM has large notional risk

    def __init__(self, strike: int, vfe_strategy: VFEStrategy):
        super().__init__(f"VEV_{strike}", self.POSITION_LIMIT, self.SOFT_LIMIT)
        self.strike = strike
        self.vfe = vfe_strategy

    def act(self, state: TradingState) -> List[Order]:
        od = self.get_od(state)
        if not od.buy_orders or not od.sell_orders:
            return []

        position = self.get_position(state)

        # Get VFE mid
        vfe_od = state.order_depths.get("VELVETFRUIT_EXTRACT", OrderDepth())
        if not vfe_od.buy_orders or not vfe_od.sell_orders:
            return []
        vfe_bb = max(vfe_od.buy_orders)
        vfe_ba = min(vfe_od.sell_orders)
        vfe_mid = (vfe_bb + vfe_ba) / 2.0
        intrinsic = max(0.0, vfe_mid - self.strike)

        bb = self.best_bid(od)
        ba = self.best_ask(od)
        mkt_spread = ba - bb

        orders: List[Order] = []

        # --- TAKE: buy if ask below intrinsic-2, sell if bid above intrinsic+2 ---
        for ask_p in sorted(od.sell_orders):
            ask_v = abs(od.sell_orders[ask_p])
            if ask_p < intrinsic - 2:
                o = self.soft_buy(ask_p, ask_v, position)
                if o:
                    orders.append(o)
                    position += o.quantity

        for bid_p in sorted(od.buy_orders, reverse=True):
            bid_v = od.buy_orders[bid_p]
            if bid_p > intrinsic + 2 and position > 0:
                o = self.soft_sell(bid_p, bid_v, position)
                if o:
                    orders.append(o)
                    position -= o.quantity

        # --- MAKE: quote inside bot spread at intrinsic ± half-spread ---
        if intrinsic > 1:
            half = max(2, mkt_spread // 4)
            inv_skew = position / self.soft_limit
            make_bid = int(intrinsic) - half - round(inv_skew * 3)
            make_ask = int(intrinsic) + half - round(inv_skew * 3)

            make_bid = max(1, min(make_bid, bb + 1))
            make_ask = max(make_ask, ba - 1)
            if make_bid < make_ask:
                max_buy = self.soft_limit - position
                max_sell = self.soft_limit + position
                if max_buy > 0 and make_bid > 0:
                    orders.append(Order(self.symbol, make_bid, max_buy))
                if max_sell > 0:
                    orders.append(Order(self.symbol, make_ask, -max_sell))

        return orders


# ---------------------------------------------------------------------------
# Trader
# ---------------------------------------------------------------------------


class Trader:
    def __init__(self):
        # Underlying MM strategies (instantiated first so options can ref VFE)
        self.hgp = HGPStrategy()
        self.vfe = VFEStrategy()

        # ATM options (5200-5500: best spread/volume, avoids adverse selection on 5000/5100)
        self.vev_mm: List[VEVMMStrategy] = [
            VEVMMStrategy(5200, self.vfe),
            VEVMMStrategy(5300, self.vfe),
            VEVMMStrategy(5400, self.vfe),
            VEVMMStrategy(5500, self.vfe),
        ]

        # Deep OTM: sell only
        self.vev_otm: List[DeepOTMStrategy] = [
            DeepOTMStrategy(6000),
            DeepOTMStrategy(6500),
        ]

        # Deep ITM: arb only
        self.vev_itm: List[DeepITMStrategy] = [
            DeepITMStrategy(4000, self.vfe),
            DeepITMStrategy(4500, self.vfe),
        ]

        # VEV_5000, VEV_5100: moderate ITM, skip for now (low volume)
        # Future: add them to vev_mm if liquidity improves

        self.all_strategies: List[Strategy] = (
            [self.hgp, self.vfe]
            + self.vev_mm
            + self.vev_otm
            + self.vev_itm
        )

    def run(self, state: TradingState) -> Tuple[Dict[str, List[Order]], int, str]:
        try:
            saved: dict = {}
            if state.traderData and state.traderData.strip():
                try:
                    saved = json.loads(state.traderData)
                except (json.JSONDecodeError, ValueError):
                    saved = {}

            # --- Day tracking ---
            # Detect day changes: when ts < last_ts, a new day started
            ts = state.timestamp
            last_ts = saved.get("_last_ts", -1)
            day_offset = saved.get("_day", 0)
            if last_ts >= 0 and ts < last_ts:
                day_offset += 1  # new day detected
            saved["_last_ts"] = ts
            saved["_day"] = day_offset

            all_orders: Dict[str, List[Order]] = {}
            conversions = 0

            # Inject day_offset into VEV MM strategies
            for s in self.vev_mm:
                s._day_offset = day_offset

            # Run VFE first so options can use its updated EMA
            for strategy in self.all_strategies:
                sym = strategy.symbol
                strategy.load(saved.get(sym, {}))
                if sym in state.order_depths:
                    orders = strategy.act(state)
                    if orders:
                        all_orders[sym] = orders
                saved[sym] = strategy.save()

            trader_data = json.dumps(saved, separators=(",", ":"))
            logger.flush(state, all_orders, conversions, trader_data)
            return all_orders, conversions, trader_data

        except Exception:
            try:
                logger.flush(state, {}, 0, state.traderData or "")
            except Exception:
                pass
            return {}, 0, state.traderData or ""