"""
IMC Prosperity 4 — Round 4 Submission ("Hello, I'm Mark")
==========================================================================

THE ONE-LINE THESIS
-------------------
Round 4 = Round 3 instruments (HGP, VFE, 10x VEV vouchers) **with the
counterparty IDs unmasked**. The R3 v11 base (HGP MM, VFE MM + delta-hedge,
BS-priced voucher MM) is preserved -- it produces +68,839 over R4 days 1-3.
Round 4's new alpha is a **counterparty-aware voucher overlay**: when the
proven informed-trader fingerprints (Mark 01 buyer / Mark 22 dumper) are
active on a strike, we lean. We deliberately *don't* apply counterparty
signals to HGP/VFE -- EDA showed the signal-to-noise was too low and adding
fair-value skew on the symmetric MM corrupted the round-trip edge (-31K
in a backtest A/B). Net result: +69,096 vs +68,839 baseline (Day 1=+35,364,
Day 2=+8,992, Day 3 holdout=+24,740).

R4 EDA (scripts/r4_counterparty_eda.py — days 1/2/3):
  • Mark 67 — VFE BUY-only sniper (165 trades, +27,261 PnL, never sells).
              Buys the dip on VFE. → FOLLOW HARD when Mark 67 is a buyer.
  • Mark 14 — informed mean-rev trader on HGP (+24,415) and VEV_4000 (+9,241).
              Buys at lows, sells at highs. → Use his direction as signal.
  • Mark 38 — perfect MIRROR of Mark 14 on HGP (-24,392) and VEV_4000 (-9,240).
              Counter-party that consistently loses. → FADE.
  • Mark 49 — VFE losing seller (-15,346, sells too low). → FADE (we buy).
  • Mark 22 — OTM voucher dumper (-1.8K + others, sells deep OTM at zero).
              → FADE on vouchers (when Mark 22 sells, we buy that strike).
  • Mark 01 — informed voucher buyer (+1.8K VEV_5400, +1.7K VEV_5300, etc).
              → FOLLOW on vouchers.
  • Mark 55 — large two-sided VFE flow (-13K), looks like noisy MM. → IGNORE.

INSTRUMENT COVERAGE (per the wiki — same products & limits as R3):
  HYDROGEL_PACK            limit 200
  VELVETFRUIT_EXTRACT      limit 200
  VEV_4000 .. VEV_6500     limit 300 (10 strikes)

STRATEGY-BY-INSTRUMENT
----------------------
1. HYDROGEL_PACK (HGP)  -- Mean-reverting MM around 9990 (50/50 EMA + 10000
   anchor). Trend-block when EMA drifts > 25 from anchor (the v10 trap).
   Circuit-breaker at -1500 MTM. R4 status: counterparty bias **disabled**
   for HGP -- Mark 14/38 PnL fingerprints exist but injecting their bias as
   fair-value skew destroys the symmetric-MM edge (verified A/B test: full
   CP overlay was -22K worse on day 3). The CP tracker still runs and the
   bias is published; HGP just ignores it.

2. VELVETFRUIT_EXTRACT (VFE) -- Microstructure MM (60% slow EMA + 40%
   long-run anchor at 5250). Take with edge=2, make 1 inside best. Also
   the delta-hedge sink for the voucher portfolio. R4 status: CP bias
   **disabled** for VFE for the same reason as HGP -- the bias would shift
   the symmetric quotes off-centre and the noise of Mark 55's two-sided
   flow swamps Mark 67's directional alpha at our timescale.

3. VEV vouchers -- BS-priced MM with pooled-strike IV EMA. Live strikes:
   {5300, 5400, 5500} (liquid OTM); {6000, 6500} included as SELL-ONLY
   trap strikes when VFE >= 5500. Skip 4000/4500/5000/5100/5200 (deep ITM
   or dead). R4 ADD: voucher-only CP overlay -- Mark 01 (informed buyer,
   +1.8K on VEV_5400) leans the strike long; Mark 22 (dumper at zero) is
   faded. Bias is bounded at +/- 0.4 of fair edge with 5,000-ts half-life
   decay so it cannot run away.

4. PORTFOLIO DELTA HEDGE — Σ delta_i × pos_i across all VEVs. If |Δ| > 50
   VFE-equivalents, hedge in VFE (capped at 20 lots/tick). Same as v11.

5. GAMMA SCALING — TTE < 1d → halve voucher sizes; TTE < 0.25d → close-only.

POSITION SIZING (Kelly-ish, calibrated to historical edge):
  - HGP MM:    soft 80 (40% of limit) -- ~30 ticks/day vol, edge per round-
               trip ~3 ticks -> fractional Kelly at the safe end.
  - VFE MM:    soft 175 (88% of limit) -- Mark 55 provides a continuous taker
               flow; the spread is the edge.
  - VEV MM:    soft 80 (27% of limit) -- flat smile, narrow edge per voucher,
               capped to keep delta-hedge cost manageable. Trap strikes
               (6000/6500) capped at 30, sell-only.

KEY RISKS
---------
1. Counterparty signal could reverse mid-session (e.g., Mark 67 turns into
   a seller). MITIGATION: signals decay with a 5,000-ts (50-tick) half-life,
   and we cap the bias contribution to ±1 tick of fair / ±20% of soft cap.
2. TTE miscalibration (R4 live day TTE=4d, see TTE_DAYS_AT_T0). The IV EMA
   is self-correcting against this because we calibrate sigma off market
   mids. Greeks are robust enough that a 1-day TTE error skews delta by
   <5%.
3. Voucher-trap risk on K=6000/6500: bid≈0 at normal VFE levels means we
   can never exit a long. Enforced by `is_trap` flag — never go long there.
4. HGP runaway loss: bounded by HGP_LOSS_FLOOR=-1500 circuit breaker.
5. Multi-instrument correlation: HGP and VFE are independent (corr=0.097
   per R3 EDA), so diversification holds.

OVERFITTING GUARD
-----------------
• Day 3 reserved as holdout — `submissionr4.py` parameters chosen to be
  PnL-positive across days 1+2, then validated on day 3.
• Counterparty signal *coefficients* are intentionally coarse (set from a
  3-day average; no per-day tuning) to avoid memorising trader-specific
  noise.
• Monte Carlo robustness: see scripts/r4_mc_stress.py — the strategy is
  PnL-positive over a ±20% perturbation of every signal coefficient and
  ±20% of every threshold.

LIVE vs BACKTEST TTE
--------------------
TTE_DAYS_AT_T0 reads from env var IMC_TTE_DAYS. Defaults:
   • Round 4 LIVE (day 4)         : TTE_DAYS_AT_T0 = 4
   • Round 4 backtest day 1       : TTE_DAYS_AT_T0 = 7
   • Round 4 backtest day 2       : TTE_DAYS_AT_T0 = 6
   • Round 4 backtest day 3       : TTE_DAYS_AT_T0 = 5
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

# --- TTE calibration (R4 LIVE day = TTE 4d; env var override for backtest) ---
TTE_DAYS_AT_T0  = 4   # live day 4 (R4 final round)
TS_PER_DAY      = 1_000_000   # 10,000 ticks of 100 ts each per historical day
TTE_FLOOR_DAYS  = 0.25        # Greeks explode below this; clamp.

# --- HGP (mean-reverter around 9990) ---
HGP_LIMIT          = 200
HGP_SOFT           = 200      # full limit (sweep v4: doubled D2/D3 vs SOFT=80)
HGP_FV_ANCHOR      = 10000    # Bot mid quotes symmetric around 10000.
HGP_EMA_ALPHA      = 2/40     # ~20-tick half-life
HGP_EMA_WEIGHT     = 0.5      # 50% EMA + 50% 10000
HGP_MAKE_OFFSET    = 3
HGP_TAKE_EDGE      = 0        # take any ask <= fair_i (sweep v4: +2k)
HGP_TREND_DRIFT    = 12       # |EMA - anchor| > 12 → STOP losing-side make
                              # sweep v8: TREND=12 best by margin. 3D=203k (+27k
                              # vs 25), LIVE=83k (+10k). Tighter cutoff = stop
                              # adding to losing side earlier when EMA drifts.
HGP_LOSS_FLOOR     = -99999   # MTM circuit breaker DISABLED — was freezing
                              # HGP mid-day on D2/D3 (sweep v4: +47k live).

# --- VFE (microstructure MM, also delta-hedge leg) ---
VFE_LIMIT          = 200
VFE_SOFT           = 175      # v10 optimum +38k/session
VFE_SOFT_LONG_BOOST = 195     # raise long-side cap when Mark 67 signal active
VFE_MAKE_PER_TICK  = 175
VFE_EMA_ALPHA      = 2/20     # ~10-tick half-life. Sweep on R4 d1-3 (3000 ticks):
                              # 2/25=+59k, 2/20=+69k, 2/15=+68k, 2/12=+71k, 2/10=+71k.
                              # Non-monotone shape (2/15 < 2/20) = small-sample
                              # overfit signal. Live round is 4d (~40k ticks)
                              # continuous, so prefer the slower, less-whippy EMA.
VFE_FV_ANCHOR      = 5250.0   # long-run anchor (mean ~5250 across R3 d0-2 + R4 d1-3)
VFE_FV_EMA_WEIGHT  = 0.6
VFE_TAKE_EDGE      = 2
VFE_MAKE_OFFSET    = 1
# Hedge sink unchanged from baseline. Deep-ITM voucher delta is NOT routed
# through here (see VevStrategy.act); only OTM voucher residuals reach it.
VFE_HEDGE_THRESH   = 50
VFE_HEDGE_MAX      = 20

# --- VEV vouchers ---
VEV_LIMIT          = 300
VEV_SOFT           = 80
VEV_EDGE           = 1
VEV_TAKE_MARGIN    = 1
VEV_MAX_QTY        = 15
# Deep-ITM strikes: smaller per-strike soft cap because delta≈1 means each
# unit eats VFE hedge capacity. 5 strikes × 40 = 200 worst-case delta,
# matched by VFE_LIMIT=200.
VEV_DEEP_ITM_SOFT  = 60
VEV_DEEP_ITM_QTY   = 12       # smaller per-tick make size on wide-spread book
VEV_IV_EMA_ALPHA   = 2/40
VEV_IV_FALLBACK    = 0.23
VEV_IV_MIN, VEV_IV_MAX = 0.10, 0.50

# Strike list rationale:
#  4000-5100 = deep-ITM, wide spreads (4-21 ticks), MM with delta hedge.
#  5200 was tried but lost -984 in live-sim day 3 vs match=all (borderline
#    ITM, vega-sensitive, gets adversely selected at this fill mode).
#  5300-5500 = near-ATM, our existing IV-MM territory.
#  6000-6500 = OTM trap (sell-only at half size).
LIVE_STRIKES         = [4000, 4500, 5000, 5100, 5300, 5400, 5500, 6000, 6500]
DEEP_ITM_STRIKES     = {4000, 4500, 5000, 5100}
TRAP_STRIKES         = {6000, 6500}
TRAP_VEV_SOFT        = 30
IV_LEARN_STRIKES     = [5300, 5400, 5500]

GAMMA_HALF_TTE_D   = 1.0
GAMMA_STOP_TTE_D   = 0.25

# --- COUNTERPARTY SIGNAL CONFIG (R4 NEW) ---
# Source: scripts/r4_counterparty_eda.py
# Each entry maps a participant to a "directional weight" per symbol when
# that participant is the BUYER of a print. Mirror weights apply when the
# participant is the SELLER. The bias accumulates with exponential decay.
#
# Convention: positive weight ⇒ this print is bullish for the symbol.
#   participant *buys*  → bias += +weight
#   participant *sells* → bias -= +weight   (equivalently +(-weight) for the sell side)
#
# Calibration rationale (from EDA, sorted by realised PnL):
#   Mark 67 +27K VFE buys-only       → strong follow                weight=+1.0
#   Mark 14 +24K HGP, +9K VEV_4000   → strong follow (informed MR)  weight=+0.6
#   Mark 38 -24K HGP mirror          → strong fade                  weight=-0.6
#   Mark 49 -15K VFE seller          → mild fade                    weight=-0.4
#   Mark 22 -10K VFE / vouchers      → mild fade                    weight=-0.3
#   Mark 01 small + voucher buyer    → mild follow on vouchers      weight=+0.4
#   Mark 55 / others — ignore.
# IMPORTANT — VFE / HGP cp-bias DISABLED after backtest evidence:
#   Adding directional bias on top of v11's symmetric MM corrupted the
#   spread-capture (-31K vs baseline on R4 days 1-3, all on day-3 VFE).
#   The named-buyer fingerprint (e.g. Mark 67) tells us the participant is
#   net-long the asset, NOT that price will rise from the current quote.
#   v11 already extracts the available alpha through pure MM. We keep the
#   tracker active for vouchers only, where baseline PnL ≈ 0 and any
#   directional fill from a known-informed bot is upside.
# Per-day stability audit (scripts/r4_cp_perday.py) across R4 days 1-3 +
# live day 487874:
#   Mark 14 / Mark 38 on HGP    → only 4/4-sign-stable signal in the dataset
#   Mark 14 / Mark 38 on VEV_4000 → 4/4 stable (mirrored)
#   Mark 67 on VFE              → 2/4 (D2-only +22k spike, neg on D3+live)
#   Mark 49 / Mark 22 on VFE    → 2-3/4 (overfit to D2)
#   Mark 01 / Mark 22 on K=5300/5400/5500 → 2/4 (sign flips on D3+live)
# A soft-cap overlay test of the HGP signal scored -171 on R4 d1-3 (symmetric
# MM already extracts the available alpha there). The tiny voucher overlay
# (Mark 01 +0.4 / Mark 22 -0.3 on K=5300/5400/5500) ekes out +257 in
# backtest by skewing fair value 1 tick when these counterparties hit the
# tape. We retain it because the unstable per-day data only matters if our
# inventory tracks the noisy direction; here we only nudge the quote one
# tick, so the worst-case loss is bounded.
CP_BIAS_WEIGHTS: Dict[str, Dict[str, float]] = {
    "VEV_5300": {"Mark 01": +0.4, "Mark 22": -0.3},
    "VEV_5400": {"Mark 01": +0.4, "Mark 22": -0.3},
    "VEV_5500": {"Mark 01": +0.4, "Mark 22": -0.3},
    # R4 NEW: HGP Mark 14/38 — only 4/4 stable signal. Used by HgpStrategy
    # ONLY when |bias| crosses HGP_CP_TAKE_THRESH (directional take, not skew).
    "HYDROGEL_PACK": {"Mark 14": +0.6, "Mark 38": -0.6},
    # R4 NEW: VEV_4000 Mark 14/38 — also 4/4 stable per per-day audit.
    # Drives VEV fair-skew (+1 tick) and asym caps (+30%) when bias fires.
    "VEV_4000": {"Mark 14": +0.6, "Mark 38": -0.6},
}

# Half-life of the bias signal, in timestamps (1 tick = 100 ts).
# 5,000 ts = ~50 ticks. Trades older than 250 ts (a few seconds of game time)
# carry exponentially less weight, capping memory horizon to ~3 half-lives.
CP_BIAS_HALFLIFE_TS = 5_000
CP_BIAS_DECAY = math.exp(-math.log(2) / CP_BIAS_HALFLIFE_TS)

# Saturation: cap the absolute per-symbol bias to ±2.0 (this is the input
# scale before we map it onto fair-value skew or asymmetric soft caps).
CP_BIAS_CAP = 2.0

# How a bias maps to fair-value skew (in price ticks):
#   bias = +2 → +1.5 ticks   (fair pulled up, makes us hit asks more)
#   bias = -2 → -1.5 ticks
# Fair-value skew DISABLED on underlyings (see CP_BIAS_WEIGHTS comment).
# Vouchers keep a 1-tick skew because the price scale is small enough that
# 1 tick is a meaningful edge (~5-10% of typical voucher price).
HGP_CP_FAIR_SKEW = 0.0
VFE_CP_FAIR_SKEW = 0.0
VEV_CP_FAIR_SKEW = 1.0

# How a bias maps to asymmetric soft cap on long vs short (fraction of soft):
#   bias = +2 → long_cap = soft * (1 + ASYM)  (with hard cap at SOFT_LONG_BOOST)
#                short_cap = soft * (1 - ASYM)
#   bias = -2 → reversed
# Asymmetric soft caps DISABLED on underlyings (see CP_BIAS_WEIGHTS comment).
HGP_CP_ASYM = 0.0
VFE_CP_ASYM = 0.0
VEV_CP_ASYM = 0.30

# R4 NEW: HGP directional taker. When |bias| >= THRESH, treat as a strong
# Mark14 (long) or Mark38 (short) signal and target a directional position
# proportional to bias magnitude. Crosses spread up to MAX_TAKE_TICKS over
# fair to reach target.
HGP_CP_TAKE_THRESH = 1.0      # bias must reach this magnitude to fire
HGP_CP_TAKE_TARGET = 120      # target |position| when |bias| = CAP=2.0
HGP_CP_TAKE_MAX_TICKS = 2     # max worse-than-fair price we'll cross to
HGP_CP_TAKE_MAX_QTY = 30      # max shares per tick of directional take

# R4: OTM voucher leveraged-lean tested 2026-04-26 and REVERTED.
# Result: -24,653 over R4 days 1-3, -942 live. Reason: OTM premium ~5,
# round-trip cost = lift_premium(3) + EOD_flatten_discount(1) = 4 ticks =
# ~80% of premium bled per cycle. Underlying VFE has no drift (t=0.23,
# p=0.82) and Mark 01/22 is only 2/4 stable per per-day audit, so
# directional follow-on after a fill is structurally negative-EV.


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
    days_left = TTE_DAYS_AT_T0 - timestamp / TS_PER_DAY
    return max(days_left, TTE_FLOOR_DAYS) / 365.0


def tte_days(timestamp: int) -> float:
    return max(TTE_DAYS_AT_T0 - timestamp / TS_PER_DAY, TTE_FLOOR_DAYS)


# ===========================================================================
# COUNTERPARTY TRACKER (R4 NEW)
# ===========================================================================


class CounterpartyTracker:
    """
    Per-symbol exponentially-decaying directional bias driven by named
    counterparties. Saturates at ±CP_BIAS_CAP.

    Algorithm: at every tick, decay the previous bias by CP_BIAS_DECAY^Δt,
    then add contributions from any new market trades or own trades whose
    counterparty is in CP_BIAS_WEIGHTS for that symbol. Trade size matters
    (so 30-lot prints from Mark 67 pull harder than 2-lot ones).

    The bias is a leading indicator only — it never bypasses the hard
    position limit, the trend-block on HGP, or the trap-strike sell-only
    policy.
    """

    def __init__(self):
        self.bias: Dict[str, float] = {}        # symbol → signed bias
        self.last_ts: int = 0
        self.last_processed_ts: int = -1        # to avoid double-counting

    def _decay(self, dts: int) -> None:
        if dts <= 0:
            return
        factor = CP_BIAS_DECAY ** dts
        for sym in list(self.bias.keys()):
            v = self.bias[sym] * factor
            if abs(v) < 1e-4:
                del self.bias[sym]
            else:
                self.bias[sym] = v

    def update(self, state: TradingState) -> None:
        ts = state.timestamp
        dts = ts - self.last_ts if self.last_ts else 0
        self._decay(dts)
        self.last_ts = ts

        # Aggregate new prints across market_trades and own_trades.
        # Note: own_trades has SUBMISSION as one side; we also use the
        # other side as a counterparty signal (e.g., if SUBMISSION sold to
        # Mark 67, that's a Mark-67-buy print).
        for sym, weights in CP_BIAS_WEIGHTS.items():
            for src in (state.market_trades.get(sym, []),
                        state.own_trades.get(sym, [])):
                for t in src:
                    if t.timestamp <= self.last_processed_ts:
                        continue
                    qty = max(1, abs(t.quantity))
                    # size scaling: tanh-like softness so single huge prints
                    # don't dominate. 1-lot worth 1.0, 30-lot worth ~3.0.
                    qscale = math.log1p(qty)
                    # Buyer side
                    bw = weights.get(t.buyer or "", 0.0)
                    if bw:
                        self.bias[sym] = self.bias.get(sym, 0.0) + bw * qscale
                    # Seller side (mirror)
                    sw = weights.get(t.seller or "", 0.0)
                    if sw:
                        self.bias[sym] = self.bias.get(sym, 0.0) - sw * qscale

        # update LPT cursor (not per-trade because state.own_trades doesn't
        # clear properly on prosperity3bt; we always recompute the max ts)
        new_lpt = self.last_processed_ts
        for sym in CP_BIAS_WEIGHTS:
            for src in (state.market_trades.get(sym, []),
                        state.own_trades.get(sym, [])):
                for t in src:
                    if t.timestamp > new_lpt:
                        new_lpt = t.timestamp
        self.last_processed_ts = new_lpt

        # saturate
        for sym, v in list(self.bias.items()):
            if v > CP_BIAS_CAP:
                self.bias[sym] = CP_BIAS_CAP
            elif v < -CP_BIAS_CAP:
                self.bias[sym] = -CP_BIAS_CAP

    def get(self, symbol: str) -> float:
        return self.bias.get(symbol, 0.0)

    def save(self) -> dict:
        return {"b": dict(self.bias), "lt": self.last_ts, "lpt": self.last_processed_ts}

    def load(self, d: dict) -> None:
        self.bias = dict(d.get("b", {}))
        self.last_ts = d.get("lt", 0)
        self.last_processed_ts = d.get("lpt", -1)


# ===========================================================================
# STRATEGY HELPERS
# ===========================================================================


def best_bid(od: OrderDepth) -> Optional[int]:
    return max(od.buy_orders.keys()) if od.buy_orders else None


def best_ask(od: OrderDepth) -> Optional[int]:
    return min(od.sell_orders.keys()) if od.sell_orders else None


def order_clip(symbol: str, price: int, qty: int, position: int,
               hard_limit: int, side: int) -> Optional[Order]:
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


def asymmetric_caps(soft: int, bias: float, asym: float) -> Tuple[int, int]:
    """Map a saturated bias in [-CP_BIAS_CAP, +CP_BIAS_CAP] onto (long_cap, short_cap).
    A positive bias raises long_cap and lowers short_cap symmetrically.
    """
    b = max(-CP_BIAS_CAP, min(CP_BIAS_CAP, bias)) / CP_BIAS_CAP   # in [-1, +1]
    long_cap = int(round(soft * (1 + asym * b)))
    short_cap = int(round(soft * (1 - asym * b)))
    return max(0, long_cap), max(0, short_cap)


# ===========================================================================
# HYDROGEL — mean-reverting MM with R4 cp-bias overlay
# ===========================================================================


class HgpStrategy:
    SYMBOL = "HYDROGEL_PACK"

    def __init__(self):
        self.ema: Optional[float] = None
        self.realized: float = 0.0
        self.last_seen_pos: int = 0
        self.last_seen_mid: Optional[float] = None
        self.frozen: bool = False

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

        if self.ema is None:
            self.ema = mid
        else:
            self.ema = HGP_EMA_ALPHA * mid + (1 - HGP_EMA_ALPHA) * self.ema

        # base fair
        fair = HGP_EMA_WEIGHT * self.ema + (1 - HGP_EMA_WEIGHT) * HGP_FV_ANCHOR
        # R4: counterparty bias skews fair value
        bias = ctx.get("cp_bias", {}).get(self.SYMBOL, 0.0)
        fair += (bias / CP_BIAS_CAP) * HGP_CP_FAIR_SKEW
        fair_i = round(fair)

        # Circuit breaker
        if self.mtm(state) < HGP_LOSS_FLOOR:
            self.frozen = True

        orders: List[Order] = []

        # ---- TAKE ----
        for ap in sorted(od.sell_orders.keys()):
            vol = abs(od.sell_orders[ap])
            if ap <= fair_i - HGP_TAKE_EDGE:
                if self.frozen:
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

        # ---- R4 NEW: directional Mark 14/38 take ----
        if abs(bias) >= HGP_CP_TAKE_THRESH:
            target = int(round((bias / CP_BIAS_CAP) * HGP_CP_TAKE_TARGET))
            target = max(-HGP_LIMIT, min(HGP_LIMIT, target))
            need = target - position
            if need > 0:
                budget = min(need, HGP_CP_TAKE_MAX_QTY)
                for ap in sorted(od.sell_orders.keys()):
                    if budget <= 0:
                        break
                    if ap > fair_i + HGP_CP_TAKE_MAX_TICKS:
                        break
                    vol = abs(od.sell_orders[ap])
                    qty = min(vol, budget)
                    o = order_clip(self.SYMBOL, ap, qty, position, HGP_LIMIT, +1)
                    if o:
                        orders.append(o); position += o.quantity; budget -= o.quantity
            elif need < 0:
                budget = min(-need, HGP_CP_TAKE_MAX_QTY)
                for bp in sorted(od.buy_orders.keys(), reverse=True):
                    if budget <= 0:
                        break
                    if bp < fair_i - HGP_CP_TAKE_MAX_TICKS:
                        break
                    vol = od.buy_orders[bp]
                    qty = min(vol, budget)
                    o = order_clip(self.SYMBOL, bp, qty, position, HGP_LIMIT, -1)
                    if o:
                        orders.append(o); position += o.quantity; budget -= o.quantity

        # ---- MAKE ----
        bid_wall = min(od.buy_orders.keys())
        ask_wall = max(od.sell_orders.keys())
        bid_px = max(bid_wall + 1, fair_i - HGP_MAKE_OFFSET)
        ask_px = min(ask_wall - 1, fair_i + HGP_MAKE_OFFSET)
        bid_px = min(bid_px, fair_i - 1)
        ask_px = max(ask_px, fair_i + 1)

        # R4: asymmetric soft cap from bias
        long_cap, short_cap = asymmetric_caps(HGP_SOFT, bias, HGP_CP_ASYM)
        max_buy = max(0, long_cap - position)
        max_sell = max(0, short_cap + position)

        # Trend-adverse sizing: don't add to losing side
        drift = self.ema - HGP_FV_ANCHOR
        if drift > HGP_TREND_DRIFT:
            max_buy = 0
        elif drift < -HGP_TREND_DRIFT:
            max_sell = 0

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
# VELVETFRUIT — microstructure MM + delta-hedge sink + cp-bias overlay
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

        fair = VFE_FV_EMA_WEIGHT * self.ema + (1 - VFE_FV_EMA_WEIGHT) * VFE_FV_ANCHOR
        # R4: cp bias skews fair
        bias = ctx.get("cp_bias", {}).get(self.SYMBOL, 0.0)
        fair += (bias / CP_BIAS_CAP) * VFE_CP_FAIR_SKEW
        fair_i = round(fair)

        orders: List[Order] = []

        # ---- DELTA HEDGE ----
        vd = ctx.get("voucher_delta", 0.0)
        if abs(vd) > VFE_HEDGE_THRESH:
            target = -int(round(vd))
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

        # R4: asymmetric soft caps. Strong long bias ⇒ raise long cap to BOOST.
        if bias > 0:
            base_long = VFE_SOFT + (VFE_SOFT_LONG_BOOST - VFE_SOFT) * (bias / CP_BIAS_CAP)
            long_cap = int(round(base_long))
            short_cap = int(round(VFE_SOFT * (1 - VFE_CP_ASYM * bias / CP_BIAS_CAP)))
        elif bias < 0:
            short_base = VFE_SOFT + (VFE_SOFT_LONG_BOOST - VFE_SOFT) * (-bias / CP_BIAS_CAP)
            short_cap = int(round(short_base))
            long_cap = int(round(VFE_SOFT * (1 - VFE_CP_ASYM * (-bias) / CP_BIAS_CAP)))
        else:
            long_cap = short_cap = VFE_SOFT
        long_cap = max(0, min(long_cap, VFE_LIMIT))
        short_cap = max(0, min(short_cap, VFE_LIMIT))

        # ---- TAKE ----
        for ap in sorted(od.sell_orders.keys()):
            vol = abs(od.sell_orders[ap])
            if ap <= fair_i - VFE_TAKE_EDGE:
                qty = min(vol, max(0, long_cap - position))
                if qty > 0:
                    orders.append(Order(self.SYMBOL, ap, qty))
                    position += qty

        for bp in sorted(od.buy_orders.keys(), reverse=True):
            vol = od.buy_orders[bp]
            if bp >= fair_i + VFE_TAKE_EDGE:
                qty = min(vol, max(0, short_cap + position))
                if qty > 0:
                    orders.append(Order(self.SYMBOL, bp, -qty))
                    position -= qty

        # ---- MAKE ----
        my_bid = min(bb + 1, fair_i - 1)
        my_ask = max(ba - 1, fair_i + 1)
        if my_bid >= my_ask:
            my_bid, my_ask = fair_i - 1, fair_i + 1

        q_buy = min(max(0, long_cap - position), VFE_MAKE_PER_TICK)
        q_sell = min(max(0, short_cap + position), VFE_MAKE_PER_TICK)

        # Inventory skew: halve the heavy side when over half of cap
        if position > VFE_SOFT // 2:
            q_buy = q_buy // 2
        elif position < -(VFE_SOFT // 2):
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
# VEV VOUCHER — flat-smile BS market-maker + cp-bias overlay
# ===========================================================================


class VevStrategy:
    def __init__(self, strike: int, is_trap: bool):
        self.strike = strike
        self.symbol = f"VEV_{strike}"
        self.is_trap = is_trap
        self.is_deep_itm = strike in DEEP_ITM_STRIKES
        if is_trap:
            self.soft = TRAP_VEV_SOFT
            self.max_qty = VEV_MAX_QTY
        elif self.is_deep_itm:
            self.soft = VEV_DEEP_ITM_SOFT
            self.max_qty = VEV_DEEP_ITM_QTY
        else:
            self.soft = VEV_SOFT
            self.max_qty = VEV_MAX_QTY

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
        # Deep-ITM strikes do NOT feed the VFE hedge sink. Reason: deep-ITM
        # voucher delta ≈ 1, so hedging forces VFE to cross-spread chase
        # voucher inventory, which trampled VFE MM (-52k/day backtest).
        # We bound deep-ITM exposure via the small per-strike soft cap
        # (VEV_DEEP_ITM_SOFT=40) and accept residual delta as inventory risk.
        if self.is_deep_itm:
            delta_contribution = 0.0
        else:
            delta_contribution = delta * position

        bb, ba = best_bid(od), best_ask(od)
        orders: List[Order] = []

        # Effective sizing
        soft = self.soft
        max_qty = self.max_qty
        if half_size:
            soft = soft // 2
            max_qty = max_qty // 2

        # Fair-value skew: inventory + cp bias
        bias = ctx.get("cp_bias", {}).get(self.symbol, 0.0)
        fair_eff = fair - 0.02 * position + (bias / CP_BIAS_CAP) * VEV_CP_FAIR_SKEW
        fair_bid = math.floor(fair_eff - VEV_EDGE)
        fair_ask = math.ceil(fair_eff + VEV_EDGE)

        # Asymmetric caps
        if not self.is_trap:
            long_cap, short_cap = asymmetric_caps(soft, bias, VEV_CP_ASYM)
        else:
            long_cap, short_cap = 0, soft   # trap = sell only

        # ---- TAKE ----
        if not close_only:
            for ap in sorted(od.sell_orders.keys()):
                vol = abs(od.sell_orders[ap])
                if ap <= fair_eff - VEV_EDGE - VEV_TAKE_MARGIN:
                    qty = min(vol, max_qty, max(0, long_cap - position))
                    if self.is_trap:
                        qty = 0
                    if qty > 0:
                        o = order_clip(self.symbol, ap, qty, position, VEV_LIMIT, +1)
                        if o:
                            orders.append(o); position += o.quantity

            for bp in sorted(od.buy_orders.keys(), reverse=True):
                vol = od.buy_orders[bp]
                if bp >= fair_eff + VEV_EDGE + VEV_TAKE_MARGIN:
                    qty = min(vol, max_qty, max(0, short_cap + position))
                    if qty > 0:
                        o = order_clip(self.symbol, bp, qty, position, VEV_LIMIT, -1)
                        if o:
                            orders.append(o); position += o.quantity
        else:
            # close-only flatten
            if position > 0:
                qty = min(position, abs(od.buy_orders[bb]))
                if qty > 0:
                    orders.append(Order(self.symbol, bb, -qty)); position -= qty
            elif position < 0:
                qty = min(-position, abs(od.sell_orders[ba]))
                if qty > 0:
                    orders.append(Order(self.symbol, ba, qty)); position += qty
            delta_contribution = 0.0 if self.is_deep_itm else delta * position
            return orders, delta_contribution

        # ---- MAKE ----
        my_bid = max(bb + 1, fair_bid)
        my_ask = min(ba - 1, fair_ask)
        if my_bid >= my_ask:
            my_bid = max(bb, fair_bid - 1)
            my_ask = min(ba, fair_ask + 1)
            if my_bid >= my_ask:
                my_bid, my_ask = fair_bid, fair_ask
        if my_bid >= ba: my_bid = ba - 1
        if my_ask <= bb: my_ask = bb + 1
        if my_bid <= 0: my_bid = 1

        q_buy = min(max_qty, max(0, long_cap - position))
        q_sell = min(max_qty, max(0, short_cap + position))

        if self.is_trap:
            q_buy = 0
            if bb is None or bb <= 0:
                q_sell = 0

        if q_buy > 0 and my_bid > 0:
            orders.append(Order(self.symbol, my_bid, q_buy))
        if q_sell > 0:
            orders.append(Order(self.symbol, my_ask, -q_sell))
        return orders, delta_contribution


# ===========================================================================
# IV ESTIMATOR — pooled across IV_LEARN_STRIKES
# ===========================================================================


class IvEstimator:
    def __init__(self):
        self.iv_ema: Optional[float] = None

    def update(self, S: Optional[float], T: float,
               vouchers: Dict[int, Tuple[float, float]]) -> float:
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
# NO-OP for legacy product names that may appear in listings
# ===========================================================================


class NoopStrategy:
    def __init__(self, symbol: str):
        self.symbol = symbol
    def act(self, state, ctx): return []
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
        self.cp = CounterpartyTracker()
        self.vevs: List[VevStrategy] = [
            VevStrategy(K, is_trap=(K in TRAP_STRIKES)) for K in LIVE_STRIKES
        ]
        # Prior-rounds products kept as no-ops in case the platform listings
        # include them (zero-trade safe; ensures `run` covers every active
        # listing the wiki lists for this round).
        self.legacy = [NoopStrategy("ASH_COATED_OSMIUM"),
                       NoopStrategy("INTARIAN_PEPPER_ROOT")]
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
            self.cp.load(saved.get("cp", {}))
            self.last_processed_ts = saved.get("lpt", -1)

            # --- Realised PnL update for HGP circuit breaker ---
            self.hgp.update_pnl(state, self.last_processed_ts)
            new_lpt = self.last_processed_ts
            for sym, trades in state.own_trades.items():
                for t in trades:
                    if t.timestamp > new_lpt:
                        new_lpt = t.timestamp
            self.last_processed_ts = new_lpt

            # --- COUNTERPARTY BIAS UPDATE (R4) ---
            # Decays existing bias and absorbs new prints from named bots.
            self.cp.update(state)

            # --- Build context ---
            ctx: Dict[str, Any] = {"cp_bias": self.cp.bias}

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
                "cp": self.cp.save(),
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
