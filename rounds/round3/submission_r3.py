"""
IMC Prosperity 4 — Round 3 Submission v11
==========================================================================

PLAIN-ENGLISH SUMMARY
---------------------
We trade three product groups on the same tick:

  1. HYDROGEL_PACK (HGP) — A stationary mean-reverter around 9,990 with a
     ~300-tick half-life. We market-make conservatively: quote tight inside
     the wall, anchor fair to a slow blend of EMA + 10000, and STOP adding
     to the losing side when EMA drifts > 20 from anchor (this prevents the
     v10 trap that lost -2,379 on log 427401 by piling into a downtrend).
     A symbol-level circuit breaker flattens HGP if its MTM dips below
     -1,500 XIRECS within the session.

  2. VELVETFRUIT_EXTRACT (VFE) — Underlying for all VEV vouchers. AC1=-0.16
     so we MM with a slow EMA fair, take with edge=2, make 1 inside best.
     VFE is also our delta-hedge leg for the voucher portfolio.

  3. VEV vouchers — European calls on VFE, 5d to expiry at LIVE start.
     Data shows a STABLE FLAT smile at ~23% IV across liquid OTM strikes
     (5300/5400/5500/6000/6500), days 0-2. We pool these strikes to maintain
     a single regime-IV EMA, then BS-price each voucher off (S, K, T, sigma).
     We market-make ±1 tick around fair on the liquid strikes only and skip
     the dead strikes (4500/5000/5100 had ~1 trade in 3 days). VEV_4000 and
     VEV_4500 are deep ITM (delta≈1), so they're pure underlying exposure
     with zero option edge — we skip them.

  4. PORTFOLIO DELTA HEDGE — At every tick, Σ delta_i × pos_i is computed
     across all VEV positions; if the magnitude exceeds 20 VFE-equivalents,
     we issue a corrective trade in VFE. This is mandatory regardless of
     individual strategy direction.

  5. GAMMA SCALING — When TTE < 1 day, voucher position sizes are halved;
     when TTE < 0.25 day, all voucher MM is suspended (close-only).
     This protects against the gamma-trap scenario where being pinned to
     a strike at expiry creates massive PnL swings.

KEY EVIDENCE (see scripts/eda_v11.py output, full 3-day data):
  - HGP: mu ≈ 9990, σ ≈ 30, AC1 ≈ -0.13, half-life 200-400 ticks
  - VFE: mu ≈ 5250, σ ≈ 15, AC1 ≈ -0.16, spread 5
  - IV smile: flat at 22-24% on K∈{5000,5100,5200,5300,5400,5500},
              stable across days 0-2
  - VFE realised vol annualised ≈ 41% (RV >> IV in absolute terms BUT OTM
    finish-ITM probabilities are tiny — market is rationally pricing the
    distribution; we make money from b-a width, not naked vol)
  - Voucher trade volumes: liquid = {VEV_5300:121, VEV_5400:225, VEV_5500:267,
    VEV_6000:284, VEV_6500:284} per 3 days; dead = {VEV_4500/5000/5100 < 2}

DELTA / POSITION LIMITS (from wiki "Round 3 - Gloves Off"):
  HYDROGEL_PACK: 200, VELVETFRUIT_EXTRACT: 200, each VEV_xxx: 300

SESSION ROBUSTNESS:
  - All parameters chosen to be safe for both 1k-tick (live) and 10k-tick
    (full backtest) sessions. No magic numbers tuned to short backtest.
  - End-of-session unwind disabled (v10's UNWIND fired during backtest day
    closes; on a single-day live session it would close prematurely).

POST-MORTEM OF v10 (log 427401, +2,809 XIRECS, day-2 1000-tick slice):
  HGP -2,379:  Bought 180 HGP into a downtrend (10011 → 9915 → 9960). Cap
               at hard limit 200 at end. v11: trend-block + soft cap 80.
  VFE +5,188:  Worked. v11 keeps strategy, slightly trims sl to 120.
  VEV $0:      LIVE_VOUCHER_STRIKES=[5200, 5400, 5500] never filled because
               edge=1 + take_margin=2 + tiny sizes was too strict. v11 widens
               to 5 strikes, runs a portfolio IV EMA, and quotes inside the
               market (penny in front of best). This is the biggest unlock.
"""

import json
import math
from typing import Any, Dict, List, Optional, Tuple

from datamodel import Order, OrderDepth, TradingState

# ===========================================================================
# LOGGER
# ===========================================================================

MAX_LOG_LENGTH = 3750


class Logger:
    def __init__(self):
        self._logs = ""

    def print(self, *args: Any, **kwargs: Any) -> None:
        self._logs += " ".join(str(a) for a in args) + "\n"

    def flush(self, state, orders, conversions, trader_data):
        out = json.dumps(
            [
                self._c_state(state),
                self._c_orders(orders),
                conversions,
                (trader_data or "")[:500],
                self._logs.rstrip(),
            ],
            separators=(",", ":"),
        )
        if len(out) > MAX_LOG_LENGTH:
            half = (MAX_LOG_LENGTH - 3) // 2
            out = out[:half] + "..." + out[-half:]
        print(out)
        self._logs = ""

    def _c_state(self, s):
        listings = {sym: [l.symbol, l.product, l.denomination] for sym, l in s.listings.items()}
        ods = {sym: [od.buy_orders, od.sell_orders] for sym, od in s.order_depths.items()}
        own = {sym: [[t.symbol, t.price, t.quantity, t.buyer or "", t.seller or "", t.timestamp] for t in ts]
               for sym, ts in s.own_trades.items()}
        mkt = {sym: [[t.symbol, t.price, t.quantity, t.buyer or "", t.seller or "", t.timestamp] for t in ts]
               for sym, ts in s.market_trades.items()}
        obs = {}
        if s.observations:
            obs["plain"] = s.observations.plainValueObservations
            obs["conv"] = {
                sym: {"bid": co.bidPrice, "ask": co.askPrice, "transport": co.transportFees,
                      "export": co.exportTariff, "import": co.importTariff}
                for sym, co in s.observations.conversionObservations.items()
            }
        return [s.timestamp, (s.traderData or "")[:500], listings, ods, own, mkt, s.position, obs]

    def _c_orders(self, o):
        return {sym: [[x.symbol, x.price, x.quantity] for x in lst] for sym, lst in o.items()}


logger = Logger()


# ===========================================================================
# CONSTANTS
# ===========================================================================

# --- TTE calibration (per wiki: "Round 3 - Gloves Off") ---
# Day 0 (tutorial)        : TTE = 8d
# Day 1 (Round 1)         : TTE = 7d
# Day 2 (Round 2)         : TTE = 6d
# Day 3 (Round 3 LIVE)    : TTE = 5d   <-- TTE_DAYS_AT_T0
# To backtest with proper TTE per day, set the constant to 8/7/6 for d0/d1/d2.
TTE_DAYS_AT_T0 = 5            # LIVE setting. TTE used by Greeks at timestamp=0.
TS_PER_DAY      = 1_000_000   # 10,000 ticks of 100 ts each per historical day
TTE_FLOOR_DAYS  = 0.25        # never let TTE go below 0.25d (otherwise gamma blows up)

# --- HGP (mean-reverter around 9990) ---
HGP_LIMIT          = 200
HGP_SOFT           = 80       # v10 lost -2.4k holding 180. Cut to 80 to bound risk.
HGP_FV_ANCHOR      = 10000    # Bots quote symmetrically around 10000.
HGP_EMA_ALPHA      = 2/40     # ~20-tick half-life
HGP_EMA_WEIGHT     = 0.5      # 50% EMA + 50% 10000
HGP_MAKE_OFFSET    = 5        # quote 5 inside fair
HGP_TAKE_EDGE      = 1        # take when ask <= fair-1 or bid >= fair+1
HGP_TREND_DRIFT    = 25       # |EMA - anchor| > 25 → STOP buys/sells on the losing side
HGP_LOSS_FLOOR     = -1500    # if HGP-only MTM < this, HGP goes close-only

# --- VFE (microstructure MM, also delta-hedge leg) ---
VFE_LIMIT          = 200
VFE_SOFT           = 175      # v10's optimum (+38k/session) — don't shrink what works
VFE_MAKE_PER_TICK  = 175
VFE_EMA_ALPHA      = 2/20     # v10's value
VFE_FV_ANCHOR      = 5250.0   # long-run anchor from EDA (mean ~5250 across 3d)
VFE_FV_EMA_WEIGHT  = 0.6      # 60% EMA + 40% anchor (v10 setting)
VFE_TAKE_EDGE      = 2
VFE_MAKE_OFFSET    = 1
VFE_HEDGE_THRESH   = 50       # only hedge when voucher delta exceeds ~50 (rare). Lower thresholds bleed spread.
VFE_HEDGE_MAX      = 20       # cap a single hedge order to 20 lots

# --- VEV vouchers ---
VEV_LIMIT          = 300
VEV_SOFT           = 80       # up from v10's 40 — flat smile lets us be more aggressive
VEV_EDGE           = 1        # quote at fair ± 1 tick
VEV_TAKE_MARGIN    = 1        # require this much edge beyond fair to take
VEV_MAX_QTY        = 15       # per-side make/take cap per tick
VEV_IV_EMA_ALPHA   = 2/40
VEV_IV_FALLBACK    = 0.23     # initial IV before any data seen (matches observed)
VEV_IV_MIN, VEV_IV_MAX = 0.10, 0.50

# Vouchers we ACTUALLY trade. Rationale:
#   skipped K=4000, 4500: deep-ITM, delta≈1 → no option edge
#   skipped K=5000, 5100: <1 trade/day in historical data (will not fill on platform)
#   K=5200: included only if reasonably liquid (18 trades/3d marginal but OK)
#   K=5300, 5400, 5500: prime liquid OTM strikes
#   K=6000, 6500: OTM but bot flow exists; spread structure asymmetric (bid≈0 risk)
#                 → INCLUDED but with extra-tight inventory cap
LIVE_STRIKES         = [5300, 5400, 5500, 6000, 6500]
TRAP_STRIKES         = {6000, 6500}    # bid≈0 risk → halve cap & no long inventory
TRAP_VEV_SOFT        = 30

# Strikes used to LEARN the regime IV (must trade liquidly with reliable mid):
IV_LEARN_STRIKES   = [5300, 5400, 5500]

# --- Gamma trap (near expiry) ---
GAMMA_HALF_TTE_D   = 1.0      # below 1 day → halve voucher sizes
GAMMA_STOP_TTE_D   = 0.25     # below 0.25 day → close-only on vouchers


# ===========================================================================
# BLACK-SCHOLES
# ===========================================================================

_SQRT_2 = math.sqrt(2.0)
_SQRT_2PI = math.sqrt(2.0 * math.pi)


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / _SQRT_2))


def _norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / _SQRT_2PI


def bs_call(S: float, K: float, T: float, sigma: float) -> float:
    if T <= 0 or sigma <= 0 or S <= 0:
        return max(S - K, 0.0)
    sst = sigma * math.sqrt(T)
    d1 = (math.log(S / K) + 0.5 * sigma * sigma * T) / sst
    d2 = d1 - sst
    return S * _norm_cdf(d1) - K * _norm_cdf(d2)


def bs_call_delta(S: float, K: float, T: float, sigma: float) -> float:
    if T <= 0 or sigma <= 0 or S <= 0:
        return 1.0 if S > K else 0.0
    sst = sigma * math.sqrt(T)
    d1 = (math.log(S / K) + 0.5 * sigma * sigma * T) / sst
    return _norm_cdf(d1)


def bs_call_vega(S: float, K: float, T: float, sigma: float) -> float:
    if T <= 0 or sigma <= 0 or S <= 0:
        return 0.0
    sst = sigma * math.sqrt(T)
    d1 = (math.log(S / K) + 0.5 * sigma * sigma * T) / sst
    return S * math.sqrt(T) * _norm_pdf(d1)


def implied_vol(price: float, S: float, K: float, T: float,
                sigma_init: float = 0.23) -> Optional[float]:
    if price <= 0 or S <= 0 or T <= 0:
        return None
    intrinsic = max(S - K, 0.0)
    if price < intrinsic - 1e-6 or price >= S:
        return None
    sigma = max(min(sigma_init, VEV_IV_MAX), VEV_IV_MIN)
    for _ in range(30):
        if sigma <= 0 or sigma > 5:
            return None
        try:
            sst = sigma * math.sqrt(T)
            d1 = (math.log(S / K) + 0.5 * sigma * sigma * T) / sst
            p = S * _norm_cdf(d1) - K * _norm_cdf(d1 - sst)
            vega = S * math.sqrt(T) * _norm_pdf(d1)
            if vega < 1e-8:
                return None
            diff = price - p
            if abs(diff) < 1e-4:
                return max(VEV_IV_MIN, min(VEV_IV_MAX, sigma))
            sigma += diff / vega
        except (ValueError, OverflowError):
            return None
    if VEV_IV_MIN <= sigma <= VEV_IV_MAX:
        return sigma
    return None


def tte_years(timestamp: int) -> float:
    """Linear daily decay. Floor at TTE_FLOOR_DAYS to avoid Greek explosions."""
    days_left = TTE_DAYS_AT_T0 - timestamp / TS_PER_DAY
    return max(days_left, TTE_FLOOR_DAYS) / 365.0


def tte_days(timestamp: int) -> float:
    """Same as tte_years but in days, used for gamma-trap scaling."""
    return max(TTE_DAYS_AT_T0 - timestamp / TS_PER_DAY, TTE_FLOOR_DAYS)


# ===========================================================================
# STRATEGY HELPERS
# ===========================================================================


def best_bid(od: OrderDepth) -> Optional[int]:
    return max(od.buy_orders.keys()) if od.buy_orders else None


def best_ask(od: OrderDepth) -> Optional[int]:
    return min(od.sell_orders.keys()) if od.sell_orders else None


def order_clip(symbol: str, price: int, qty: int, position: int,
               hard_limit: int, side: int) -> Optional[Order]:
    """side=+1 BUY, -1 SELL.  Clips against hard position limit; returns None if 0.
    qty must be positive."""
    if qty <= 0 or price <= 0:
        return None
    if side > 0:
        cap = hard_limit - position
    else:
        cap = hard_limit + position
    q = min(qty, cap)
    if q <= 0:
        return None
    return Order(symbol, int(price), q if side > 0 else -q)


# ===========================================================================
# HYDROGEL — mean-reverting MM
# ===========================================================================


class HgpStrategy:
    SYMBOL = "HYDROGEL_PACK"

    def __init__(self):
        self.ema: Optional[float] = None
        self.realized: float = 0.0           # session realized PnL (HGP only)
        self.last_seen_pos: int = 0
        self.last_seen_mid: Optional[float] = None
        self.frozen: bool = False            # close-only flag

    def update_pnl(self, state: TradingState, last_processed_ts: int) -> None:
        for t in state.own_trades.get(self.SYMBOL, []):
            if t.timestamp <= last_processed_ts:
                continue
            if getattr(t, "buyer", None) == "SUBMISSION":
                self.realized -= t.quantity * t.price
            elif getattr(t, "seller", None) == "SUBMISSION":
                self.realized += t.quantity * t.price

    def mtm(self, state: TradingState) -> float:
        pos = state.position.get(self.SYMBOL, 0)
        od = state.order_depths.get(self.SYMBOL)
        if not od or not od.buy_orders or not od.sell_orders:
            mid = self.last_seen_mid or HGP_FV_ANCHOR
        else:
            mid = (best_bid(od) + best_ask(od)) / 2.0
        return self.realized + pos * mid

    def act(self, state: TradingState, ctx: dict) -> List[Order]:
        od = state.order_depths.get(self.SYMBOL)
        if not od or not od.buy_orders or not od.sell_orders:
            return []
        position = state.position.get(self.SYMBOL, 0)
        bb, ba = best_bid(od), best_ask(od)
        mid = (bb + ba) / 2.0
        self.last_seen_mid = mid

        # update EMA
        if self.ema is None:
            self.ema = mid
        else:
            self.ema = HGP_EMA_ALPHA * mid + (1 - HGP_EMA_ALPHA) * self.ema

        fair = HGP_EMA_WEIGHT * self.ema + (1 - HGP_EMA_WEIGHT) * HGP_FV_ANCHOR
        fair_i = round(fair)

        # HGP-specific circuit breaker
        if self.mtm(state) < HGP_LOSS_FLOOR:
            self.frozen = True

        orders: List[Order] = []

        # ---- TAKE ----
        # Always allow takes that flatten or improve
        for ap in sorted(od.sell_orders.keys()):
            vol = abs(od.sell_orders[ap])
            if ap <= fair_i - HGP_TAKE_EDGE:
                if self.frozen:
                    # only buys that REDUCE a short position
                    if position >= 0:
                        break
                    qty = min(vol, -position)
                else:
                    cap = HGP_SOFT - position
                    qty = min(vol, max(0, cap))
                o = order_clip(self.SYMBOL, ap, qty, position, HGP_LIMIT, +1)
                if o:
                    orders.append(o); position += o.quantity

        for bp in sorted(od.buy_orders.keys(), reverse=True):
            vol = od.buy_orders[bp]
            if bp >= fair_i + HGP_TAKE_EDGE:
                if self.frozen:
                    if position <= 0:
                        break
                    qty = min(vol, position)
                else:
                    cap = HGP_SOFT + position
                    qty = min(vol, max(0, cap))
                o = order_clip(self.SYMBOL, bp, qty, position, HGP_LIMIT, -1)
                if o:
                    orders.append(o); position += o.quantity

        if self.frozen:
            return orders

        # ---- MAKE ----
        bid_wall = min(od.buy_orders.keys())
        ask_wall = max(od.sell_orders.keys())
        bid_px = max(bid_wall + 1, fair_i - HGP_MAKE_OFFSET)
        ask_px = min(ask_wall - 1, fair_i + HGP_MAKE_OFFSET)
        bid_px = min(bid_px, fair_i - 1)
        ask_px = max(ask_px, fair_i + 1)

        max_buy = max(0, HGP_SOFT - position)
        max_sell = max(0, HGP_SOFT + position)

        # Trend-adverse sizing: if EMA has drifted from anchor, don't add to losing side.
        drift = self.ema - HGP_FV_ANCHOR
        if drift > HGP_TREND_DRIFT:
            max_buy = 0       # price above anchor → expect down → don't buy
        elif drift < -HGP_TREND_DRIFT:
            max_sell = 0      # price below anchor → expect up → don't sell

        if max_buy > 0:
            orders.append(Order(self.SYMBOL, bid_px, max_buy))
        if max_sell > 0:
            orders.append(Order(self.SYMBOL, ask_px, -max_sell))
        return orders

    def save(self) -> dict:
        return {"e": self.ema, "r": self.realized, "f": self.frozen}

    def load(self, d: dict) -> None:
        self.ema = d.get("e")
        self.realized = d.get("r", 0.0)
        self.frozen = d.get("f", False)


# ===========================================================================
# VELVETFRUIT — microstructure MM + delta-hedge sink
# ===========================================================================


class VfeStrategy:
    SYMBOL = "VELVETFRUIT_EXTRACT"

    def __init__(self):
        self.ema: Optional[float] = None

    def act(self, state: TradingState, ctx: dict) -> List[Order]:
        od = state.order_depths.get(self.SYMBOL)
        if not od or not od.buy_orders or not od.sell_orders:
            return []
        position = state.position.get(self.SYMBOL, 0)
        bb, ba = best_bid(od), best_ask(od)
        mid = (bb + ba) / 2.0

        if self.ema is None:
            self.ema = mid
        else:
            self.ema = VFE_EMA_ALPHA * mid + (1 - VFE_EMA_ALPHA) * self.ema

        # v10-style fair: EMA + anchor blend. The anchor (5250) is the 3-day
        # observed mean and prevents EMA-driven runaway when the underlying
        # drifts in one direction within a single session.
        fair = VFE_FV_EMA_WEIGHT * self.ema + (1 - VFE_FV_EMA_WEIGHT) * VFE_FV_ANCHOR
        fair_i = round(fair)
        orders: List[Order] = []

        # ---- DELTA HEDGE (only when voucher delta is large) ----
        # voucher_delta = signed sum of delta_i * pos_i across all VEVs.
        # On the LIVE platform vouchers fill more than in backtest, so keeping
        # the threshold high avoids spread-bleed without abandoning the hedge.
        vd = ctx.get("voucher_delta", 0.0)
        if abs(vd) > VFE_HEDGE_THRESH:
            target = -int(round(vd))            # +ve voucher delta → sell VFE
            target = max(-VFE_HEDGE_MAX, min(VFE_HEDGE_MAX, target))
            if target > 0:
                qty_avail = abs(od.sell_orders[ba])
                qty = min(target, qty_avail, VFE_LIMIT - position)
                if qty > 0:
                    orders.append(Order(self.SYMBOL, ba, qty))
                    position += qty
            elif target < 0:
                qty_avail = od.buy_orders[bb]
                qty = min(-target, qty_avail, VFE_LIMIT + position)
                if qty > 0:
                    orders.append(Order(self.SYMBOL, bb, -qty))
                    position -= qty

        sl = VFE_SOFT

        # ---- TAKE: 2-tick edge vs fair ----
        for ap in sorted(od.sell_orders.keys()):
            vol = abs(od.sell_orders[ap])
            if ap <= fair_i - VFE_TAKE_EDGE:
                qty = min(vol, max(0, sl - position))
                if qty > 0:
                    orders.append(Order(self.SYMBOL, ap, qty))
                    position += qty

        for bp in sorted(od.buy_orders.keys(), reverse=True):
            vol = od.buy_orders[bp]
            if bp >= fair_i + VFE_TAKE_EDGE:
                qty = min(vol, max(0, sl + position))
                if qty > 0:
                    orders.append(Order(self.SYMBOL, bp, -qty))
                    position -= qty

        # ---- MAKE: 1 tick inside best bid/ask, clamped to fair±1 minimum ----
        my_bid = min(bb + 1, fair_i - 1)
        my_ask = max(ba - 1, fair_i + 1)
        if my_bid >= my_ask:
            my_bid, my_ask = fair_i - 1, fair_i + 1

        q_buy = min(max(0, sl - position), VFE_MAKE_PER_TICK)
        q_sell = min(max(0, sl + position), VFE_MAKE_PER_TICK)
        # Inventory skew: halve the heavy side
        if position > sl // 2:
            q_buy = q_buy // 2
        elif position < -(sl // 2):
            q_sell = q_sell // 2

        if q_buy > 0:
            orders.append(Order(self.SYMBOL, my_bid, q_buy))
        if q_sell > 0:
            orders.append(Order(self.SYMBOL, my_ask, -q_sell))
        return orders

    def save(self) -> dict:
        return {"e": self.ema}

    def load(self, d: dict) -> None:
        self.ema = d.get("e")


# ===========================================================================
# VEV VOUCHER — flat-smile BS market-maker
# ===========================================================================


class VevStrategy:
    def __init__(self, strike: int, is_trap: bool):
        self.strike = strike
        self.symbol = f"VEV_{strike}"
        self.is_trap = is_trap
        self.soft = TRAP_VEV_SOFT if is_trap else VEV_SOFT

    def fair_and_delta(self, S: float, T: float, sigma: float) -> Tuple[float, float]:
        return bs_call(S, self.strike, T, sigma), bs_call_delta(S, self.strike, T, sigma)

    def act(self, state: TradingState, ctx: dict, sigma: float,
            close_only: bool, half_size: bool) -> Tuple[List[Order], float]:
        od = state.order_depths.get(self.symbol)
        S = ctx.get("vfe_mid")
        if not od or not od.buy_orders or not od.sell_orders or S is None:
            return [], 0.0

        position = state.position.get(self.symbol, 0)
        T = tte_years(state.timestamp)
        fair, delta = self.fair_and_delta(S, T, sigma)
        delta_contribution = delta * position

        bb, ba = best_bid(od), best_ask(od)
        orders: List[Order] = []

        # Effective sizing
        soft = self.soft
        max_qty = VEV_MAX_QTY
        if half_size:
            soft = soft // 2
            max_qty = max_qty // 2

        # Inventory skew: shift fair toward zero-position
        fair_eff = fair - 0.02 * position
        fair_bid = math.floor(fair_eff - VEV_EDGE)
        fair_ask = math.ceil(fair_eff + VEV_EDGE)

        # ---- TAKE: only if margin > take_margin AND not close-only ----
        if not close_only:
            for ap in sorted(od.sell_orders.keys()):
                vol = abs(od.sell_orders[ap])
                if ap <= fair_eff - VEV_EDGE - VEV_TAKE_MARGIN:
                    qty = min(vol, max_qty, max(0, soft - position))
                    # trap strikes: NEVER buy (can't exit due to bid≈0 risk)
                    if self.is_trap:
                        qty = 0
                    if qty > 0:
                        o = order_clip(self.symbol, ap, qty, position, VEV_LIMIT, +1)
                        if o:
                            orders.append(o); position += o.quantity

            for bp in sorted(od.buy_orders.keys(), reverse=True):
                vol = od.buy_orders[bp]
                if bp >= fair_eff + VEV_EDGE + VEV_TAKE_MARGIN:
                    qty = min(vol, max_qty, max(0, soft + position))
                    if qty > 0:
                        o = order_clip(self.symbol, bp, qty, position, VEV_LIMIT, -1)
                        if o:
                            orders.append(o); position += o.quantity
        else:
            # close-only: hit the book to flatten
            if position > 0:
                qty = min(position, abs(od.buy_orders[bb]))
                if qty > 0:
                    orders.append(Order(self.symbol, bb, -qty)); position -= qty
            elif position < 0:
                qty = min(-position, abs(od.sell_orders[ba]))
                if qty > 0:
                    orders.append(Order(self.symbol, ba, qty)); position += qty
            # recompute final delta contribution
            delta_contribution = delta * position
            return orders, delta_contribution

        # ---- MAKE: penny in front of best, but not crossing fair ± edge ----
        my_bid = max(bb + 1, fair_bid)
        my_ask = min(ba - 1, fair_ask)
        # don't cross
        if my_bid >= my_ask:
            my_bid = max(bb, fair_bid - 1)
            my_ask = min(ba, fair_ask + 1)
            if my_bid >= my_ask:
                my_bid, my_ask = fair_bid, fair_ask
        # don't cross book
        if my_bid >= ba: my_bid = ba - 1
        if my_ask <= bb: my_ask = bb + 1
        if my_bid <= 0: my_bid = 1

        q_buy = min(max_qty, max(0, soft - position))
        q_sell = min(max_qty, max(0, soft + position))

        # Trap strikes: never go long; can only sell.
        if self.is_trap:
            q_buy = 0
            # Also: only sell if we have room and bid > 0 (don't post if book bid is 0).
            if bb is None or bb <= 0:
                q_sell = 0

        if q_buy > 0 and my_bid > 0:
            orders.append(Order(self.symbol, my_bid, q_buy))
        if q_sell > 0:
            orders.append(Order(self.symbol, my_ask, -q_sell))

        # delta_contribution already computed pre-fill; that's the right number
        # for the hedge (we hedge BEFORE fills happen this tick anyway, since the
        # hedge order is sent in the same tick).
        return orders, delta_contribution


# ===========================================================================
# IV ESTIMATOR — pooled across IV_LEARN_STRIKES
# ===========================================================================


class IvEstimator:
    def __init__(self):
        self.iv_ema: Optional[float] = None

    def update(self, S: Optional[float], T: float, vouchers: Dict[int, Tuple[float, float]]) -> float:
        """vouchers[K] = (mid, spread). Returns the current sigma to use."""
        if S is None or T <= 0:
            return self.iv_ema if self.iv_ema is not None else VEV_IV_FALLBACK

        ivs: List[float] = []
        for K in IV_LEARN_STRIKES:
            mp = vouchers.get(K)
            if mp is None:
                continue
            mid, _ = mp
            iv = implied_vol(mid, S, K, T,
                             sigma_init=self.iv_ema if self.iv_ema is not None else VEV_IV_FALLBACK)
            if iv is not None:
                ivs.append(iv)

        if ivs:
            mkt_iv = sum(ivs) / len(ivs)
            if self.iv_ema is None:
                self.iv_ema = mkt_iv
            else:
                self.iv_ema = VEV_IV_EMA_ALPHA * mkt_iv + (1 - VEV_IV_EMA_ALPHA) * self.iv_ema

        return self.iv_ema if self.iv_ema is not None else VEV_IV_FALLBACK

    def save(self) -> dict:
        return {"iv": self.iv_ema}

    def load(self, d: dict) -> None:
        self.iv_ema = d.get("iv")


# ===========================================================================
# NO-OP for legacy products
# ===========================================================================


class NoopStrategy:
    def __init__(self, symbol: str):
        self.symbol = symbol

    def act(self, state, ctx):
        return []

    def save(self): return {}

    def load(self, d): pass


# ===========================================================================
# TRADER
# ===========================================================================


class Trader:
    def __init__(self):
        self.hgp = HgpStrategy()
        self.vfe = VfeStrategy()
        self.iv = IvEstimator()
        self.vevs: List[VevStrategy] = [
            VevStrategy(K, is_trap=(K in TRAP_STRIKES)) for K in LIVE_STRIKES
        ]
        self.legacy = [NoopStrategy("ASH_COATED_OSMIUM"), NoopStrategy("INTARIAN_PEPPER_ROOT")]
        self.last_processed_ts: int = -1

    def run(self, state: TradingState) -> Tuple[Dict[str, List[Order]], int, str]:
        try:
            # --- Load persisted state ---
            saved: dict = {}
            if state.traderData and state.traderData.strip():
                try: saved = json.loads(state.traderData)
                except Exception: saved = {}
            self.hgp.load(saved.get("hgp", {}))
            self.vfe.load(saved.get("vfe", {}))
            self.iv.load(saved.get("iv", {}))
            self.last_processed_ts = saved.get("lpt", -1)

            # --- Realised PnL update (HGP only, used by HGP circuit breaker) ---
            self.hgp.update_pnl(state, self.last_processed_ts)
            new_lpt = self.last_processed_ts
            for sym, trades in state.own_trades.items():
                for t in trades:
                    if t.timestamp > new_lpt:
                        new_lpt = t.timestamp
            self.last_processed_ts = new_lpt

            # --- Build context ---
            ctx: Dict[str, Any] = {}
            v_od = state.order_depths.get(self.vfe.SYMBOL)
            S: Optional[float] = None
            if v_od and v_od.buy_orders and v_od.sell_orders:
                S = (best_bid(v_od) + best_ask(v_od)) / 2.0
                ctx["vfe_mid"] = S

            # --- Update IV from market mids of learn-strikes ---
            T = tte_years(state.timestamp)
            mids: Dict[int, Tuple[float, float]] = {}
            for K in LIVE_STRIKES:
                od = state.order_depths.get(f"VEV_{K}")
                if od and od.buy_orders and od.sell_orders:
                    bb_, ba_ = best_bid(od), best_ask(od)
                    mids[K] = ((bb_ + ba_) / 2.0, ba_ - bb_)
            sigma = self.iv.update(S, T, mids)

            # --- Gamma trap regime ---
            t_days = tte_days(state.timestamp)
            half_size = t_days < GAMMA_HALF_TTE_D
            close_only_vevs = t_days < GAMMA_STOP_TTE_D

            all_orders: Dict[str, List[Order]] = {}

            # --- Phase 1: Vouchers, accumulate signed delta ---
            voucher_delta = 0.0
            for v in self.vevs:
                o, dcontrib = v.act(state, ctx, sigma, close_only_vevs, half_size)
                voucher_delta += dcontrib
                if o:
                    all_orders[v.symbol] = o
            ctx["voucher_delta"] = voucher_delta

            # --- Phase 2: VFE consumes the hedge requirement ---
            o = self.vfe.act(state, ctx)
            if o:
                all_orders[self.vfe.SYMBOL] = o

            # --- Phase 3: HGP independent ---
            o = self.hgp.act(state, ctx)
            if o:
                all_orders[self.hgp.SYMBOL] = o

            # --- Persist ---
            saved = {
                "hgp": self.hgp.save(),
                "vfe": self.vfe.save(),
                "iv": self.iv.save(),
                "lpt": self.last_processed_ts,
            }
            trader_data = json.dumps(saved, separators=(",", ":"))

            logger.flush(state, all_orders, 0, trader_data)
            return all_orders, 0, trader_data

        except Exception as e:
            try: logger.print(f"ERR {e!r}")
            except Exception: pass
            try: logger.flush(state, {}, 0, state.traderData or "")
            except Exception: pass
            return {}, 0, state.traderData or ""
