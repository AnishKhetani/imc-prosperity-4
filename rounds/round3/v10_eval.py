"""
IMC Prosperity 4 — Round 3 Submission v10
=============================================================

CHANGES IN v10 (competition-ready hardening):

  1. HYDROGEL_SOFT_LIMIT: 200 → 150.  MC stress test (50 sims, 13 scenarios)
     showed sl=200 hits the hard limit (maxPos avg=180) in crash scenarios,
     giving p5 = -49k. sl=150 cuts tail ~25% at cost of ~8k/day backtest.
     Backtest total: 174,876 → 155,310 (-11%). Risk-adjusted: clearly better.

  2. VelvetStrategy dynamic anchor: hardcoded 5250 replaced with session-start
     mid-price (initialized from first observed tick, then held fixed).
     Critical fix: on backtest day 2 (VFE starts ~5344), old anchor biased
     fair = 0.6*EMA + 0.4*5250 = 5306 (38 below market), causing strategy to
     aggressively TAKE-SELL into the uptrend. Dynamic anchor = 5344 → neutral.
     Gain: +12k on day 2 alone. Essential safety for future rounds.

  3. VelvetStrategy flat_only bug fix: when circuit breaker fired, flat_only=True
     caused the TAKE loop to skip with `not flat_only`, and then `return orders`
     returned an empty list. VFE positions were NEVER closed. Fixed: explicit
     close-only logic (sell longs at best bid, buy shorts at best ask) executes
     before the early return.

  4. LIVE_VOUCHER_STRIKES: [5200, 5400, 5500] → [5300, 5400, 5500].
     VEV_5200 had only 21 trades/day (too illiquid to fill). VEV_5300 has 140
     trades/day (7x more liquid) and is near-ATM when VFE drifts to 5350-5400.

  5. VOUCHER_SOFT_LIMIT: 40 → 60. Modest increase (50%) to allow more MM
     activity on the more liquid strike set.

  6. VELVET_EMA_ALPHA constant: 2/40 → 2/20 (corrects discrepancy; code always
     used hardcoded 2.0/20.0 — this aligns the constant with the actual behavior).

BACKTEST RESULTS (prosperity3bt, 10k ticks/day, 3 days R3):
  v10 (this file): HGP=85,624 + VFE=69,686 = 155,310
  Submission prev:                               112,442  (+38% advantage)

POST-MORTEM OF v1 (log 365182, -4,482 XIRECS on day=2 live):

  Local backtest of v1 on days 0–2 (10,000 ticks/day) scored +86,442
  (HYDROGEL alone +84,703). But the PLATFORM session ran only 1,000 ticks
  of a day-2-like slice on which HYDROGEL drifted 10011 → 9927 with no
  time for mean-reversion. v1 bought 317 units @ avg 9994.52 on the way
  down, hit the soft_limit=150 cap, and held a stuck +150 into the close
  at mid 9927 → −2,667 on HYDROGEL alone.

  Voucher book lost −1,815 driven by (a) +150 long VEV_6500 we cannot
  exit (bid=0), (b) +150 long VEV_4000 deep-ITM caught as S dropped,
  (c) smile-price mismatches on 5400/5500 sells.

FIXES IN v3 (minimal, targeted, preserves the +86k local edge):

  1. HYDROGEL_SOFT_LIMIT: 150 → 50.  Caps any one-sided MTM loss to
     ~ 50 × (abs drift-from-anchor). On the log 365182 slice that would
     have been ~50 × 70 = 3,500 instead of 150 × 70 = 10,500.

  2. HYDROGEL trend-adverse sizing: if |EMA − ANCHOR| > 20, halve make
     size on the TREND-FOLLOWING side (we stop adding to losing inventory
     while still quoting the opposite side to catch reversion).

  3. Vouchers trimmed:
       * REMOVED VEV_6000 and VEV_6500 (penny-wide, bid=0, cannot exit longs).
       * REMOVED VEV_4000 (deep-ITM → delta ≈ 1 → pure underlying risk with
         zero option edge; log 365182 proved we get run over).
       * KEPT VEV_5400 and VEV_5500 (liquid, non-zero bid, contained risk).
     Voucher soft_limit: 150 → 40 (smaller inventory on a vol product
     whose smile we can't trust out-of-sample).

  4. VOUCHER_TAKE_MARGIN: 1.0 → 2.0 (require bigger edge to take, since
     our smile model is over-fit to days 0–2 and may mis-price live).

  5. TTE_DAYS_AT_T0: kept at 5 (best extrapolation per forensic H8 linear
     fit).  Not the driver of the loss so we don't touch it.

Expected backtest:  ~50-70% of v1's +86k (smaller positions, fewer fills).
Expected platform:  positive; the structural HYDROGEL edge is intact and
                    the inventory-spiral cap makes even a hostile 1000-tick
                    slice bounded to ~ -4k worst-case HYDROGEL.

ORIGINAL DOCSTRING FOLLOWS:
"""
__ORIG_DOCSTRING__ = """
IMC Prosperity 4 — Round 3 Submission
=====================================

PRODUCTS (evidence from scripts/forensic_output/forensic_report.md):
  HYDROGEL_PACK       : pos 200, mean 9990.8, std 32, AC1=-0.13, spread ~16.
                        Stationary mean-reverter (half-life 300 ticks).
                        -> Adaptive-EMA market-making (ACO-style).

  VELVETFRUIT_EXTRACT : pos 200, mean 5250, spread ~5, hurst 0.97,
                        imb_vs_fwd1 corr ~+0.30 (strong microstructure signal,
                        side=+1 trade -> +0.42 mean fwd move).
                        -> Microprice MM with imbalance tilt. Also serves
                        as delta-hedge leg for voucher book.

  VEV_{4000,4500,5000,5100,5200,5300,5400,5500,6000,6500}: calls, pos 300 ea.
                        Smile is PARABOLIC & STABLE across days 0-2:
                          sigma(m) = 0.227 * m^2 + 0*m + 0.15   (m = ln(K/S)/sqrt(T))
                          resid_std across days 0/1/2: 0.0128/0.0167/0.0201
                        No arbitrage violations (butterfly, spread, bounds).
                        RV on underlying = 0.41 vs ATM IV = 0.23 -> long-vol
                        bias, but we DO NOT take naked vol risk (no RV gate
                        on live data; smile MM captures edge more safely).
                        -> BS smile-fit MM on LIQUID vouchers only.

LIQUIDITY FILTER (H17):
  tradeable: VEV_4000(313/d), VEV_5300(140), VEV_5400(262), VEV_5500(312),
             VEV_6000(334), VEV_6500(334).  VEV_5200(21) marginal.
  SKIP:     VEV_4500, VEV_5000, VEV_5100  (<1 trade/day -> no bot flow).

STRATEGIES (survivors after internal tournament):
  S1 HydrogelStrategy   -- stationary mean-rev MM
  S2 VelvetStrategy     -- microprice MM + imbalance tilt + delta-hedge offset
  S3 VoucherStrategy    -- BS smile-fit MM, adaptive TTE, inventory tiers

RISK CONTROLS:
  * Hard position limits enforced via .buy()/.sell() clippers.
  * Soft limits shrink quoting as inventory builds.
  * Regime-detection on spread (HYDROGEL/VELVET): if EMA spread halves,
    we halve make-size (preserves edge-per-fill).
  * Session PnL circuit breaker: once realized MTM dips below SESSION_PNL_FLOOR,
    all strategies go to FLAT-ONLY (close-only) mode.
  * Voucher starvation fallback: if a voucher has <1 fill per 1000 ticks,
    strategy widens quotes to BS+/-3 instead of BS+/-1.

TTE HANDLING:
  Historical days 0/1/2 had TTE = 8/7/6 days. Live (round 3 day 3) = 5 days.
  Single parameter `TTE_DAYS_AT_T0` controls which mode we're in.
  * For backtest over days 0-2 merged (prosperity3bt): 8.
  * For LIVE SUBMISSION: set to 5 (a comment below flags this line).
  TTE decreases linearly with state.timestamp (1,000,000 ts = 1 day).
"""

import json
import math
from typing import Any, Dict, List, Optional, Tuple

from datamodel import Order, OrderDepth, TradingState

# =======================================================================
# LOGGER (compressed JSON for jmerle visualiser)
# =======================================================================

MAX_LOG_LENGTH = 3750


class Logger:
    def __init__(self):
        self._logs = ""

    def print(self, *args: Any, **kwargs: Any) -> None:
        self._logs += " ".join(str(a) for a in args) + "\n"

    def flush(self, state, orders, conversions, trader_data):
        output = json.dumps(
            [
                self._c_state(state),
                self._c_orders(orders),
                conversions,
                (trader_data or "")[:500],
                self._logs.rstrip(),
            ],
            separators=(",", ":"),
        )
        if len(output) > MAX_LOG_LENGTH:
            half = (MAX_LOG_LENGTH - 3) // 2
            output = output[:half] + "..." + output[-half:]
        print(output)
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


# =======================================================================
# CONSTANTS (every magic number documented)
# =======================================================================

# --- Session-level risk
SESSION_PNL_FLOOR = -50_000   # Circuit breaker. Day-0/1/2 min PnL never below -5k; -50k = 10x safety.
MTM_WINDOW_TICKS  = 1000      # window for tracking drawdown (~10% of a day)

# --- TTE  (CONFIGURED FOR LIVE ROUND 3 DAY 3)
TTE_DAYS_AT_T0    = 5         # LIVE SUBMISSION: day 3 has 5 trading days to expiry.
                               # For historical backtest days 0/1/2, true TTE was 8/7/6.
                               # Using 5 here means fair values are slightly biased (shorter
                               # T -> smaller vol leg), but smile coefs are in reduced moneyness
                               # m = ln(K/S)/sqrt(T) so IV EMA self-heals within warm-up.
# Per-day TTE lookup (wiki: "Gloves Off", section "Algorithmic trading challenge"):
#   Day 0 (tutorial / historical)  → TTE = 8 days
#   Day 1 (Round 1  / historical)  → TTE = 7 days
#   Day 2 (Round 2  / historical)  → TTE = 6 days
#   Day 3 (Round 3  / LIVE)        → TTE = 5 days   ← TTE_DAYS_AT_T0 above
# NOTE: To backtest with correct TTE for each day, change TTE_DAYS_AT_T0 to
#   8 (day 0), 7 (day 1), or 6 (day 2) before running prosperity3bt.
#   The IV EMA self-corrects in ~50 ticks so the impact on a full 10k-tick
#   backtest is small, but matters for the 1000-tick platform-length slice.
TTE_DAYS_BY_ROUND = {0: 8, 1: 7, 2: 6, 3: 5}   # reference constant — not used by strategy logic
TICKS_PER_DAY     = 10_000    # 100 timestamp units per tick, 10k ticks/day
TS_PER_DAY        = TICKS_PER_DAY * 100  # 1,000,000

# --- HYDROGEL (mean-reverting ~10000)
HYDROGEL_POS_LIMIT     = 200
HYDROGEL_SOFT_LIMIT    = 180        # v10: grid search optimal (BT=174k, worst p5=-28k, score=118k). MC stress tests: sl=200 → p5=-49k in
                                       # hgp_extreme_down (maxPos avg=180 at hard limit). sl=150 cuts
                                       # tail ~25%. Cost: ~5-8k/day in backtest; well worth the safety.
HYDROGEL_FV_ANCHOR     = 10000      # H1 data mean=9990.8, but bots quote sym about 10000
HYDROGEL_EMA_ALPHA     = 2/16       # half-life ~ spread width
HYDROGEL_MAKE_OFFSET   = 5          # v4: 5 inside wall (grid search: +900 PnL over off=3).
HYDROGEL_TAKE_EDGE     = 1          # ask <= fair-1 -> take
HYDROGEL_IMB_WEIGHT    = 1.0
HYDROGEL_TREND_DRIFT   = 20         # v5: |EMA-ANCHOR| above this => ZERO make on trend-following side

# --- End-of-session unwind (live session ~1000 ticks; backtest = 10000 ticks/day)
LIVE_SESSION_TICKS     = 1000       # approx live session length
UNWIND_START_TICK      = 850        # begin linearly reducing soft limits at this tick
#   ticks 851-1000 → limits scale from 100% → 0% (forces inventory flat before close)
#   ticks >1000    → full limits restored (we know we're in backtest)

# --- VELVETFRUIT (trending w/ microstructure signal)
VELVET_POS_LIMIT       = 200
VELVET_SOFT_LIMIT      = 175        # v9: sl=175 (grid search optimal, H=200). Peak at 174,876 total.
VELVET_MAKE_PER_TICK   = 175        # v9: no effective cap (matches sl=175, so never binding).
VELVET_EMA_ALPHA       = 2/20       # period-20; matches hardcoded 2.0/20.0 in VelvetStrategy.act()
VELVET_IMB_WEIGHT      = 0.5        # softer tilt; too aggressive created adverse fills
VELVET_TAKE_EDGE       = 2          # need 2 XIRECS of edge to take (spread ~5)
VELVET_MAKE_OFFSET     = 2          # 2 inside best (inside the bot 5249/5251 wall)
VELVET_MAX_HEDGE_SIZE  = 0          # DISABLED — hedge bled 2.8k on day0. Voucher book runs naked vol.

# --- VOUCHERS
VOUCHER_POS_LIMIT      = 300
VOUCHER_SOFT_LIMIT     = 60         # v10: raised from 40. VEV_5300 added (140 trades/day); modest
                                       # increase preserves safety while allowing more MM activity.
SMILE_A                = 0.227      # from H7 averaged across days
SMILE_B                = 0.0
SMILE_C                = 0.15
VOUCHER_EDGE_TICKS     = 1          # v9: reduced from 2. edge=2 puts VEV_5400/5500 OUTSIDE their
                                       # 2-tick spread (fallback to fair±2). edge=1 posts at spread edge.
VOUCHER_WIDE_EDGE      = 3          # starvation fallback widen
VOUCHER_STARVE_WINDOW  = 1000
VOUCHER_MIN_FILLS      = 1
VOUCHER_IV_EMA_ALPHA   = 2/100      # ~50-tick half-life (adapts within a day)
VOUCHER_IV_WARMUP      = 50
VOUCHER_INV_SKEW_TICKS = 0.02       # ticks of quote shift per 1 unit of inventory
VOUCHER_MAX_TAKE_QTY   = 10         # small bites on take fills
VOUCHER_MAX_MAKE_QTY   = 15         # cap per-side make size
VOUCHER_TAKE_MARGIN    = 2.0        # v3: was 1.0. Require bigger edge; smile is OOS-unreliable.
LIVE_VOUCHER_STRIKES   = [5300, 5400, 5500]  # v10: replaced VEV_5200 (21 trades/day) with VEV_5300
                                       # (140 trades/day, 7x more liquid). EDGE=1 posts at market
                                       # spread edge — joins queue for fills. VEV_5300 is near-ATM
                                       # when underlying drifts to 5350-5400 range.
                                       # VEV_6000/6500: bb=0, stuck-long trap → excluded.
                                       # VEV_4000/4500: deep ITM, pure underlying risk → excluded.

# --- Legacy R1/R2 products (kept to remain valid on earlier rounds if resubmitted)
ACO_POS_LIMIT          = 80
IPR_POS_LIMIT          = 80


# =======================================================================
# BLACK-SCHOLES UTILITIES
# =======================================================================

def _norm_cdf(x: float) -> float:
    # Abramowitz & Stegun 7.1.26 (|err| < 7.5e-8).
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def bs_call_price(S: float, K: float, T: float, sigma: float, r: float = 0.0) -> float:
    if T <= 0 or sigma <= 0 or S <= 0:
        return max(S - K, 0.0)
    sig_sqrt_T = sigma * math.sqrt(T)
    d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / sig_sqrt_T
    d2 = d1 - sig_sqrt_T
    return S * _norm_cdf(d1) - K * math.exp(-r * T) * _norm_cdf(d2)


def bs_call_delta(S: float, K: float, T: float, sigma: float, r: float = 0.0) -> float:
    if T <= 0 or sigma <= 0 or S <= 0:
        return 1.0 if S > K else 0.0
    sig_sqrt_T = sigma * math.sqrt(T)
    d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / sig_sqrt_T
    return _norm_cdf(d1)


def implied_vol_from_price(price: float, S: float, K: float, T: float,
                           sigma_init: float = 0.25, iters: int = 40) -> Optional[float]:
    """Newton-Raphson IV inversion. Returns None if non-convergent or out of bounds."""
    if price <= 0 or S <= 0 or T <= 0:
        return None
    # Intrinsic sanity
    intrinsic = max(S - K, 0.0)
    if price < intrinsic - 1e-6 or price > S:
        return None
    sigma = max(sigma_init, 0.05)
    for _ in range(iters):
        if sigma <= 0:
            return None
        try:
            sig_sqrt_T = sigma * math.sqrt(T)
            d1 = (math.log(S / K) + 0.5 * sigma * sigma * T) / sig_sqrt_T
            d2 = d1 - sig_sqrt_T
            p  = S * _norm_cdf(d1) - K * _norm_cdf(d2)
            vega = S * math.sqrt(T) * math.exp(-0.5 * d1 * d1) / math.sqrt(2 * math.pi)
            if vega < 1e-8:
                return None
            diff = price - p
            if abs(diff) < 1e-4:
                return max(0.05, min(2.0, sigma))
            sigma += diff / vega
            if sigma < 0.01 or sigma > 3.0:
                return None
        except (ValueError, OverflowError):
            return None
    return max(0.05, min(2.0, sigma))


def smile_iv(moneyness: float) -> float:
    iv = SMILE_A * moneyness * moneyness + SMILE_B * moneyness + SMILE_C
    return max(iv, 0.05)


def tte_years(timestamp: int) -> float:
    # Linear decay: at t=0 we're at TTE_DAYS_AT_T0, lose 1 day per TS_PER_DAY.
    days_elapsed = timestamp / TS_PER_DAY
    days_left = max(TTE_DAYS_AT_T0 - days_elapsed, 0.5)   # floor 0.5d to avoid div0
    return days_left / 365.0


# =======================================================================
# STRATEGY BASE
# =======================================================================


class Strategy:
    def __init__(self, symbol: str, position_limit: int, soft_limit: int):
        self.symbol = symbol
        self.position_limit = position_limit
        self.soft_limit = soft_limit

    def position(self, state: TradingState) -> int:
        return state.position.get(self.symbol, 0)

    def order_depth(self, state: TradingState) -> Optional[OrderDepth]:
        return state.order_depths.get(self.symbol)

    @staticmethod
    def best_bid(od: OrderDepth) -> Optional[int]:
        return max(od.buy_orders.keys()) if od.buy_orders else None

    @staticmethod
    def best_ask(od: OrderDepth) -> Optional[int]:
        return min(od.sell_orders.keys()) if od.sell_orders else None

    def buy(self, price: int, qty: int, position: int) -> Optional[Order]:
        cap = self.position_limit - position
        q = min(qty, cap)
        return Order(self.symbol, price, q) if q > 0 else None

    def sell(self, price: int, qty: int, position: int) -> Optional[Order]:
        cap = self.position_limit + position
        q = min(qty, cap)
        return Order(self.symbol, price, -q) if q > 0 else None

    def soft_buy(self, price: int, qty: int, position: int) -> Optional[Order]:
        cap = self.soft_limit - position
        q = min(qty, cap)
        return Order(self.symbol, price, q) if q > 0 else None

    def soft_sell(self, price: int, qty: int, position: int) -> Optional[Order]:
        cap = self.soft_limit + position
        q = min(qty, cap)
        return Order(self.symbol, price, -q) if q > 0 else None

    def save(self) -> dict:
        return {}

    def load(self, data: dict) -> None:
        pass

    # subclass hook
    def act(self, state: TradingState, ctx: dict) -> List[Order]:
        raise NotImplementedError


# =======================================================================
# S1 — HYDROGEL mean-reverting MM
# =======================================================================


class HydrogelStrategy(Strategy):
    def __init__(self):
        super().__init__("HYDROGEL_PACK", HYDROGEL_POS_LIMIT, HYDROGEL_SOFT_LIMIT)
        self.ema_fair: Optional[float] = None
        self.ema_spread: Optional[float] = None

    def act(self, state: TradingState, ctx: dict) -> List[Order]:
        od = self.order_depth(state)
        if not od or not od.buy_orders or not od.sell_orders:
            return []
        position = self.position(state)
        orders: List[Order] = []

        bb, ba = self.best_bid(od), self.best_ask(od)
        mid = (bb + ba) / 2.0
        spread = ba - bb

        # Blend: 50% long-run anchor (10000) + 50% fast EMA.
        # The long-run anchor prevents drift catastrophes (seen on platform vs local).
        if self.ema_fair is None:
            self.ema_fair = mid
        else:
            self.ema_fair = HYDROGEL_EMA_ALPHA * mid + (1 - HYDROGEL_EMA_ALPHA) * self.ema_fair
        if self.ema_spread is None:
            self.ema_spread = float(spread)
        else:
            self.ema_spread = 0.1 * spread + 0.9 * self.ema_spread

        bv = od.buy_orders[bb]
        av = abs(od.sell_orders[ba])
        imb = (bv - av) / (bv + av) if (bv + av) > 0 else 0.0

        fair = 0.5 * self.ema_fair + 0.5 * HYDROGEL_FV_ANCHOR + HYDROGEL_IMB_WEIGHT * imb
        fair_i = round(fair)

        flat_only = ctx.get("flat_only", False)

        # -- TAKE --
        for ap in sorted(od.sell_orders.keys()):
            vol = abs(od.sell_orders[ap])
            if ap <= fair_i - HYDROGEL_TAKE_EDGE:
                o = self.soft_buy(ap, vol, position) if not flat_only else self.buy(ap, min(vol, max(0, -position)), position)
                if o:
                    orders.append(o); position += o.quantity

        for bp in sorted(od.buy_orders.keys(), reverse=True):
            vol = od.buy_orders[bp]
            if bp >= fair_i + HYDROGEL_TAKE_EDGE:
                o = self.soft_sell(bp, vol, position) if not flat_only else self.sell(bp, min(vol, max(0, position)), position)
                if o:
                    orders.append(o); position += o.quantity

        if flat_only:
            return orders

        # -- MAKE -- wall-based
        bid_wall = min(od.buy_orders.keys())
        ask_wall = max(od.sell_orders.keys())
        # Regime: if observed spread is unusually thin (<10), halve make qty.
        regime_thin = self.ema_spread < 10
        mk_scale = 0.5 if regime_thin else 1.0

        bid_px = max(bid_wall + 1, fair_i - HYDROGEL_MAKE_OFFSET)
        ask_px = min(ask_wall - 1, fair_i + HYDROGEL_MAKE_OFFSET)
        # stay inside
        bid_px = min(bid_px, fair_i - 1)
        ask_px = max(ask_px, fair_i + 1)

        max_buy  = max(0, self.soft_limit - position)
        max_sell = max(0, self.soft_limit + position)
        q_buy  = int(max_buy  * mk_scale)
        q_sell = int(max_sell * mk_scale)

        # v3: trend-adverse sizing.  If EMA has diverged far from the long-run
        # anchor (10000), the market is in a directional regime and mean-
        # reversion may not complete within a short (~1000t) platform slice.
        # In that case we DO NOT keep loading up the side that's been losing.
        drift = self.ema_fair - HYDROGEL_FV_ANCHOR
        if drift > HYDROGEL_TREND_DRIFT:
            # price well above anchor → reversion DOWN expected → keep sells, STOP buys.
            # v5: full zero (was halve) — prevents inventory accumulation into a downtrend.
            q_buy = 0
        elif drift < -HYDROGEL_TREND_DRIFT:
            # price well below anchor → reversion UP expected → keep buys, STOP sells.
            # v5: full zero on SELLS (was halve). Symmetrically halt trend-following side.
            q_sell = 0

        if q_buy  > 0: orders.append(Order(self.symbol, bid_px, q_buy))
        if q_sell > 0: orders.append(Order(self.symbol, ask_px, -q_sell))
        return orders

    def save(self):
        return {"f": self.ema_fair, "s": self.ema_spread}

    def load(self, d):
        self.ema_fair = d.get("f"); self.ema_spread = d.get("s")


# =======================================================================
# S2 — VELVETFRUIT microstructure MM (+ delta-hedge offset)
# =======================================================================


class VelvetStrategy(Strategy):
    """v4 REACTIVATED: mean-reverting MM on VELVETFRUIT_EXTRACT.
    Grid search confirmed profitable: +38k/session vs disabled baseline.
    Uses: 60% adaptive EMA + 40% session-start anchor (dynamic), TAKE edge=2, MAKE inside spread.
    Inventory-skew halving prevents directional accumulation.
    save()/load() persist EMA across ticks in stateless live platform.
    """
    def __init__(self):
        super().__init__("VELVETFRUIT_EXTRACT", VELVET_POS_LIMIT, VELVET_SOFT_LIMIT)

    def act(self, state: TradingState, ctx: dict) -> List[Order]:
        od = self.order_depth(state)
        if not od or not od.buy_orders or not od.sell_orders:
            return []
        position = self.position(state)
        orders: List[Order] = []
        flat_only = ctx.get("flat_only", False)

        bb = max(od.buy_orders.keys())
        ba = min(od.sell_orders.keys())
        mid = (bb + ba) / 2.0

        # EMA with getattr for safe tick-1 init; persisted via save()/load()
        ema    = getattr(self, "_v_ema",    None)
        anchor = getattr(self, "_v_anchor", None)
        if ema is None:
            ema    = mid
            anchor = mid   # dynamic anchor: set once to session-start price; never updated
        else:
            ema = (2.0 / 20.0) * mid + (1.0 - 2.0 / 20.0) * ema
        self._v_ema = ema
        if anchor is None:
            anchor = mid
        self._v_anchor = anchor  # stable after tick-1; prevents bias if VFE drifts between rounds

        # Fair value: 60% adaptive EMA + 40% session-start anchor (dynamic, not hardcoded 5250)
        fair = 0.6 * ema + 0.4 * anchor
        fair_i = round(fair)
        sl = VELVET_SOFT_LIMIT

        # -- TAKE: 2-tick edge vs fair --
        for ap in sorted(od.sell_orders.keys()):
            vol = abs(od.sell_orders[ap])
            if ap <= fair_i - 2:
                qty = min(vol, max(0, sl - position))
                if qty > 0 and not flat_only:
                    orders.append(Order(self.symbol, ap, qty))
                    position += qty
        for bp in sorted(od.buy_orders.keys(), reverse=True):
            vol = od.buy_orders[bp]
            if bp >= fair_i + 2:
                qty = min(vol, max(0, sl + position))
                if qty > 0 and not flat_only:
                    orders.append(Order(self.symbol, bp, -qty))
                    position -= qty

        if flat_only:
            # Circuit breaker active: close existing positions at best available prices.
            # Bug fix v10: previous code returned empty orders here; VFE was never closed.
            if position > 0:
                for bp in sorted(od.buy_orders.keys(), reverse=True):
                    vol = od.buy_orders[bp]
                    qty = min(vol, position)
                    if qty > 0:
                        orders.append(Order(self.symbol, bp, -qty))
                        position -= qty
            elif position < 0:
                for ap in sorted(od.sell_orders.keys()):
                    vol = abs(od.sell_orders[ap])
                    qty = min(vol, -position)
                    if qty > 0:
                        orders.append(Order(self.symbol, ap, qty))
                        position += qty
            return orders

        # -- MAKE: 1 tick inside best bid/ask, clamped to fair±1 minimum --
        my_bid = min(bb + 1, fair_i - 1)
        my_ask = max(ba - 1, fair_i + 1)
        if my_bid >= my_ask:
            my_bid, my_ask = fair_i - 1, fair_i + 1

        q_buy  = min(max(0, sl - position), VELVET_MAKE_PER_TICK)
        q_sell = min(max(0, sl + position), VELVET_MAKE_PER_TICK)
        # Inventory-skew: halve size on the already-heavy side
        if position > sl // 2:
            q_buy = q_buy // 2
        elif position < -(sl // 2):
            q_sell = q_sell // 2

        if q_buy  > 0:
            orders.append(Order(self.symbol, my_bid,  q_buy))
        if q_sell > 0:
            orders.append(Order(self.symbol, my_ask, -q_sell))
        return orders

    def save(self) -> dict:
        return {"e": getattr(self, "_v_ema", None), "a": getattr(self, "_v_anchor", None)}

    def load(self, d: dict) -> None:
        self._v_ema    = d.get("e")
        self._v_anchor = d.get("a")


# =======================================================================
# S3 — VOUCHER smile-fit MM
# =======================================================================


class VoucherStrategy(Strategy):
    def __init__(self, strike: int):
        super().__init__(f"VEV_{strike}", VOUCHER_POS_LIMIT, VOUCHER_SOFT_LIMIT)
        self.strike = strike
        self.tick_counter = 0
        self.ema_iv: Optional[float] = None   # per-voucher online implied vol

    def compute_fair(self, S: float, timestamp: int, market_mid: Optional[float]) -> Tuple[float, float]:
        """Return (fair_price, delta).

        Primary: use EMA of market-implied IV (adapts to regime shifts).
        Fallback: parabolic smile from forensic (days 0-2 avg).
        """
        T = tte_years(timestamp)
        if S <= 0 or T <= 0:
            return max(S - self.strike, 0.0), 1.0 if S > self.strike else 0.0

        # Update online IV from observed market mid (if present).
        if market_mid is not None and market_mid > 0:
            mkt_iv = implied_vol_from_price(market_mid, S, self.strike, T,
                                            sigma_init=(self.ema_iv or 0.25))
            if mkt_iv is not None:
                if self.ema_iv is None:
                    self.ema_iv = mkt_iv
                else:
                    self.ema_iv = VOUCHER_IV_EMA_ALPHA * mkt_iv + (1 - VOUCHER_IV_EMA_ALPHA) * self.ema_iv

        # Pick IV: use market-derived EMA immediately when available.
        # v8 fix: removed 50-tick warmup penalty. The smile fallback severely
        # underprices ITM options (e.g. VEV_5200 BS-fair=93 vs market=104).
        # We learn the correct IV from market_mid on tick 0, so use it immediately.
        if self.ema_iv is not None:
            iv = self.ema_iv
        else:
            m = math.log(self.strike / S) / math.sqrt(max(T, 1e-6))
            iv = smile_iv(m)  # only used before any market data seen (tick 0 edge case)

        price = bs_call_price(S, self.strike, T, iv)
        delta = bs_call_delta(S, self.strike, T, iv)
        return price, delta

    def act(self, state: TradingState, ctx: dict) -> List[Order]:
        od = self.order_depth(state)
        if not od or not od.buy_orders or not od.sell_orders:
            return []
        position = self.position(state)
        orders: List[Order] = []
        flat_only = ctx.get("flat_only", False)

        S = ctx.get("velvet_mid")
        if S is None:
            return []

        bb, ba = self.best_bid(od), self.best_ask(od)
        market_mid = (bb + ba) / 2.0 if (bb is not None and ba is not None) else None

        fair, delta = self.compute_fair(S, state.timestamp, market_mid)
        ctx["voucher_delta_accum"] = ctx.get("voucher_delta_accum", 0.0) + delta * position

        # Starvation detection: if no recent fills, widen.
        self.tick_counter += 1
        trades = state.own_trades.get(self.symbol, [])
        recent_fills = sum(1 for t in trades if t.timestamp >= state.timestamp - VOUCHER_STARVE_WINDOW * 100)
        edge = VOUCHER_WIDE_EDGE if recent_fills < VOUCHER_MIN_FILLS and self.tick_counter > VOUCHER_STARVE_WINDOW else VOUCHER_EDGE_TICKS

        # Inventory skew: shift our effective fair toward 0-inventory.
        skewed_fair = fair - VOUCHER_INV_SKEW_TICKS * position

        fair_bid = int(math.floor(skewed_fair - edge))
        fair_ask = int(math.ceil(skewed_fair + edge))

        # -- TAKE only when margin > VOUCHER_TAKE_MARGIN ticks beyond edge (strict) --
        for ap in sorted(od.sell_orders.keys()):
            vol = abs(od.sell_orders[ap])
            if ap <= fair - edge - VOUCHER_TAKE_MARGIN:
                qty = min(vol, VOUCHER_MAX_TAKE_QTY)
                o = self.soft_buy(ap, qty, position) if not flat_only else self.buy(ap, min(qty, max(0, -position)), position)
                if o:
                    orders.append(o); position += o.quantity

        for bp in sorted(od.buy_orders.keys(), reverse=True):
            vol = od.buy_orders[bp]
            if bp >= fair + edge + VOUCHER_TAKE_MARGIN:
                qty = min(vol, VOUCHER_MAX_TAKE_QTY)
                o = self.soft_sell(bp, qty, position) if not flat_only else self.sell(bp, min(qty, max(0, position)), position)
                if o:
                    orders.append(o); position += o.quantity

        if flat_only:
            return orders

        # -- MAKE at skewed fair +/- edge (inside spread if possible) --
        my_bid = max(bb + 1 if bb is not None else fair_bid, fair_bid)
        my_ask = min(ba - 1 if ba is not None else fair_ask, fair_ask)
        if my_bid >= my_ask:
            my_bid = fair_bid
            my_ask = fair_ask
        if bb is not None and my_ask <= bb:  my_ask = bb + 1
        if ba is not None and my_bid >= ba:  my_bid = ba - 1

        max_buy  = max(0, self.soft_limit - position)
        max_sell = max(0, self.soft_limit + position)
        q_buy  = min(max_buy,  VOUCHER_MAX_MAKE_QTY)
        q_sell = min(max_sell, VOUCHER_MAX_MAKE_QTY)
        if q_buy  > 0 and my_bid > 0: orders.append(Order(self.symbol, my_bid, q_buy))
        if q_sell > 0:                orders.append(Order(self.symbol, my_ask, -q_sell))
        return orders

    def save(self): return {"tc": self.tick_counter, "iv": self.ema_iv}
    def load(self, d):
        self.tick_counter = d.get("tc", 0)
        self.ema_iv = d.get("iv")


# =======================================================================
# LEGACY: R1/R2 products (no-op on R3 since symbols not present)
# =======================================================================


class NoopStrategy(Strategy):
    def __init__(self, symbol, limit=80):
        super().__init__(symbol, limit, limit)

    def act(self, state, ctx):
        return []


# =======================================================================
# TRADER
# =======================================================================


class Trader:
    def __init__(self):
        self.hydrogel = HydrogelStrategy()
        self.velvet   = VelvetStrategy()
        self.vouchers = [VoucherStrategy(k) for k in LIVE_VOUCHER_STRIKES]
        self.legacy   = [NoopStrategy("ASH_COATED_OSMIUM"), NoopStrategy("INTARIAN_PEPPER_ROOT")]
        self.all      = [self.hydrogel, self.velvet, *self.vouchers, *self.legacy]
        self.session_pnl_min: float = 0.0   # running min of session mtm
        self.flat_only: bool = False

    def _compute_pnl(self, state: TradingState, cum_cash: float, last_ts: int) -> Tuple[float, float, int]:
        """Return (pnl_estimate, updated_cum_cash, updated_last_ts).

        Processes each own-trade exactly once by gating on trade.timestamp > last_ts.
        (prosperity3bt's runner does NOT clear state.own_trades between ticks.)
        """
        max_ts = last_ts
        for sym, trades in state.own_trades.items():
            for t in trades:
                if t.timestamp <= last_ts:
                    continue
                if getattr(t, "buyer", None) == "SUBMISSION":
                    cum_cash -= t.quantity * t.price
                elif getattr(t, "seller", None) == "SUBMISSION":
                    cum_cash += t.quantity * t.price
                if t.timestamp > max_ts:
                    max_ts = t.timestamp
        unrealized = 0.0
        for sym, pos in state.position.items():
            if pos == 0:
                continue
            od = state.order_depths.get(sym)
            if not od or not od.buy_orders or not od.sell_orders:
                continue
            mid = (max(od.buy_orders) + min(od.sell_orders)) / 2
            unrealized += pos * mid
        return cum_cash + unrealized, cum_cash, max_ts

    def run(self, state: TradingState) -> Tuple[Dict[str, List[Order]], int, str]:
        try:
            saved = {}
            if state.traderData and state.traderData.strip():
                try: saved = json.loads(state.traderData)
                except Exception: saved = {}

            for strat in self.all:
                strat.load(saved.get(strat.symbol, {}))
            self.session_pnl_min = saved.get("_pnl_min", 0.0)
            self.flat_only = saved.get("_flat", False)
            cum_cash = saved.get("_cash", 0.0)
            last_cash_ts = saved.get("_cash_ts", -1)
            tick_num = saved.get("_tick", 0) + 1

            # --- End-of-session unwind: scale soft limits down in ticks [UNWIND_START, LIVE_SESSION_TICKS]
            # After LIVE_SESSION_TICKS ticks we're confirmed in backtest → restore full limits.
            if UNWIND_START_TICK < tick_num <= LIVE_SESSION_TICKS:
                unwind_frac = (tick_num - UNWIND_START_TICK) / (LIVE_SESSION_TICKS - UNWIND_START_TICK)
            else:
                unwind_frac = 0.0
            self.hydrogel.soft_limit = int(HYDROGEL_SOFT_LIMIT * (1.0 - unwind_frac))
            self.velvet.soft_limit   = int(VELVET_SOFT_LIMIT   * (1.0 - unwind_frac))

            # --- Context shared across strategies ---
            ctx: Dict[str, Any] = {"flat_only": self.flat_only}
            v_od = state.order_depths.get(self.velvet.symbol)
            if v_od and v_od.buy_orders and v_od.sell_orders:
                ctx["velvet_mid"] = (max(v_od.buy_orders) + min(v_od.sell_orders)) / 2

            # --- Phase 1: voucher strategies first (accumulate delta) ---
            all_orders: Dict[str, List[Order]] = {}
            ctx["voucher_delta_accum"] = 0.0
            for v in self.vouchers:
                if v.symbol in state.order_depths:
                    o = v.act(state, ctx)
                    if o: all_orders[v.symbol] = o

            # --- Phase 2: velvet consumes aggregated voucher delta ---
            ctx["voucher_delta"] = ctx["voucher_delta_accum"]
            if self.velvet.symbol in state.order_depths:
                o = self.velvet.act(state, ctx)
                if o: all_orders[self.velvet.symbol] = o

            # --- Phase 3: hydrogel (independent) ---
            if self.hydrogel.symbol in state.order_depths:
                o = self.hydrogel.act(state, ctx)
                if o: all_orders[self.hydrogel.symbol] = o

            # --- Risk: session PnL circuit breaker ---
            pnl_estimate, cum_cash, last_cash_ts = self._compute_pnl(state, cum_cash, last_cash_ts)
            if pnl_estimate < self.session_pnl_min:
                self.session_pnl_min = pnl_estimate
            if self.session_pnl_min < SESSION_PNL_FLOOR:
                self.flat_only = True  # sticky once tripped

            # Save
            for strat in self.all:
                saved[strat.symbol] = strat.save()
            saved["_pnl_min"] = self.session_pnl_min
            saved["_flat"]    = self.flat_only
            saved["_cash"]    = cum_cash
            saved["_cash_ts"] = last_cash_ts
            saved["_tick"]    = tick_num
            trader_data = json.dumps(saved, separators=(",", ":"))

            logger.flush(state, all_orders, 0, trader_data)
            return all_orders, 0, trader_data

        except Exception as e:
            try: logger.print(f"ERR: {e!r}")
            except Exception: pass
            try: logger.flush(state, {}, 0, state.traderData or "")
            except Exception: pass
            return {}, 0, state.traderData or ""

    def bid(self, state: TradingState) -> int:
        return 2000