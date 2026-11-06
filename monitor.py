"""
monitor.py — R5 Live Round Monitor
==================================
Single-command terminal dashboard that reads the live algorithm log files
(prosperity3bt-format `prices_*.csv` + `trades_*.csv`) and prints a
refreshing dashboard every 30 seconds.

USAGE
-----
    python monitor.py --prices live/prices.csv --trades live/trades.csv
    python monitor.py --dir live/                    # auto-pick newest CSVs
    python monitor.py --prices live/prices.csv --refresh 15

Options:
    --prices    PATH    activities CSV (semicolon-delimited)
    --trades    PATH    trades CSV (semicolon-delimited, optional)
    --dir       PATH    directory to auto-pick prices_*/trades_*.csv from
    --refresh   INT     refresh interval seconds (default 30)
    --once              render once and exit
    --no-color          disable ANSI colour output
    --my-team   STR     informational header

PANELS (top to bottom):
    1. PNL TRACKER         total + per-product + velocity + MC overlay
    2. STRATEGY HEALTH     P2 / S1+S2 / S2 / R2 / M1 / M3 health + trip-wires
    3. POSITION & RISK     per-product position vs limit, 1-sigma stress
    4. ORDER BOOK HEALTH   spread/depth vs historical median, OU residuals
    5. ANOMALY ALERT FEED  BLOCKER/WARNING events with severity colour

DESIGN
------
- Pure Python stdlib. No numpy / pandas / curses — pure ANSI.
- Never raises. Every panel either renders or shows "NO DATA".
- ASCII-only output (Windows cp1252 console safe).
- Polls files by mtime; re-reads only when mtime changes.

Exit: Ctrl-C.
"""

from __future__ import annotations

import argparse
import csv
import glob
import os
import sys
import time
from collections import defaultdict, deque
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Static reference data — derived from prior steps. Edit ONLY if Step-1 EDA
# baselines change. These are hard-coded by design (no live recompute).
# ---------------------------------------------------------------------------

# Strategy → product membership. Mirrors submission._strategy_of canonicalisation.
STRATEGY_PRODUCTS: Dict[str, List[str]] = {
    "P2": ["PEBBLES_XS", "PEBBLES_S", "PEBBLES_M", "PEBBLES_L", "PEBBLES_XL"],
    "S1S2": ["SNACKPACK_CHOCOLATE", "SNACKPACK_VANILLA"],
    "S2":   ["SNACKPACK_PISTACHIO", "SNACKPACK_RASPBERRY",
              "SNACKPACK_STRAWBERRY"],
    "R2":   ["ROBOT_DISHES", "ROBOT_IRONING"],
    "M1":   [
        "GALAXY_SOUNDS_BLACK_HOLES", "GALAXY_SOUNDS_DARK_MATTER",
        "GALAXY_SOUNDS_PLANETARY_RINGS", "GALAXY_SOUNDS_SOLAR_FLAMES",
        "GALAXY_SOUNDS_SOLAR_WINDS",
        "UV_VISOR_AMBER", "UV_VISOR_MAGENTA", "UV_VISOR_ORANGE",
        "UV_VISOR_RED", "UV_VISOR_YELLOW",
        "OXYGEN_SHAKE_CHOCOLATE", "OXYGEN_SHAKE_EVENING_BREATH",
        "OXYGEN_SHAKE_GARLIC", "OXYGEN_SHAKE_MINT",
        "OXYGEN_SHAKE_MORNING_BREATH",
        "PANEL_1X2", "PANEL_1X4", "PANEL_2X2", "PANEL_2X4", "PANEL_4X4",
    ],
    "M3":   [
        "MICROCHIP_CIRCLE", "MICROCHIP_OVAL", "MICROCHIP_RECTANGLE",
        "MICROCHIP_SQUARE", "MICROCHIP_TRIANGLE",
        "ROBOT_LAUNDRY", "ROBOT_MOPPING", "ROBOT_VACUUMING",
        "SLEEP_POD_COTTON", "SLEEP_POD_LAMB_WOOL", "SLEEP_POD_NYLON",
        "SLEEP_POD_POLYESTER", "SLEEP_POD_SUEDE",
        "TRANSLATOR_ASTRO_BLACK", "TRANSLATOR_ECLIPSE_CHARCOAL",
        "TRANSLATOR_GRAPHITE_MIST", "TRANSLATOR_SPACE_GRAY",
        "TRANSLATOR_VOID_BLUE",
    ],
}
PRODUCT_STRATEGY: Dict[str, str] = {
    p: s for s, ps in STRATEGY_PRODUCTS.items() for p in ps
}

# Historical median spread (from Step 1 EDA). Per-product calibration is
# coarse — we only flag at >2x deviations. Default for unknown product = 4.
SPREAD_BASELINE: Dict[str, float] = defaultdict(lambda: 4.0)
SPREAD_BASELINE.update({
    # Wide MM (M1) — typical 12-16 ticks
    **{p: 14.0 for p in STRATEGY_PRODUCTS["M1"]},
    # Tight MM (M3) — typical 3-5 ticks
    **{p: 4.0 for p in STRATEGY_PRODUCTS["M3"]},
    # SNACK pair — typical 6 ticks
    "SNACKPACK_CHOC": 6.0, "SNACKPACK_VAN": 6.0,
    # SNACK wide MM (S2) — typical 12-14 ticks
    **{p: 13.0 for p in STRATEGY_PRODUCTS["S2"]},
    # ROBOT_DISHES/IRONING (R2) — typical 5 ticks
    **{p: 5.0 for p in STRATEGY_PRODUCTS["R2"]},
    # PEBBLES legs — typical 12 ticks
    **{p: 12.0 for p in STRATEGY_PRODUCTS["P2"]},
})

# Historical 5-pct top-of-book depth (Step 1 EDA, conservative).
DEPTH_BASELINE_P5: Dict[str, int] = defaultdict(lambda: 4)

# Monte Carlo BASELINE PnL reference (Step 4, parametric, 15 sims).
# Linear interpolation: at tick t, expected = MC_FINAL_MEAN * (t / 10000).
# Confidence band ±1 sigma uses MC_FINAL_STD pro-rated by sqrt(t/10000).
# Numbers from _harness_full.txt (15 sims x 1000 ticks): mean=+97, std=235.
# Scaled to 10000 ticks (R5 day length): mean ~+970, std ~+743.
MC_FINAL_MEAN = 970.0
MC_FINAL_STD = 743.0
ROUND_TICKS = 10_000          # 1,000,000 timestamps / 100

# Strategy trip-wire thresholds (Part B — calibrated from Step 4 MC scenario
# means; see R5_DECISION_COMMANDER.md §1).
TRIP_WIRES = {
    "P2":   {"warn_pnl": -50.0,  "block_pnl": -100.0, "trip_tick": 1500},
    "S1S2": {"warn_pnl": -50.0,  "block_pnl": -100.0, "trip_tick": 1500},
    "S2":   {"warn_pnl": -50.0,  "block_pnl": -100.0, "trip_tick": 2000},
    "R2":   {"warn_pnl": -50.0,  "block_pnl": -100.0, "trip_tick": 1500},
    "M1":   {"warn_pnl": -200.0, "block_pnl": -300.0, "trip_tick": 2000},
    "M3":   {"warn_pnl": -100.0, "block_pnl": -200.0, "trip_tick": 3000},
}
GLOBAL_WARN_PNL = -400.0
GLOBAL_BLOCK_PNL = -700.0
POSITION_LIMIT = 10

# ---------------------------------------------------------------------------
# ANSI colour helpers
# ---------------------------------------------------------------------------

class C:
    RESET = "\x1b[0m"
    BOLD = "\x1b[1m"
    DIM = "\x1b[2m"
    GREEN = "\x1b[32m"
    YELLOW = "\x1b[33m"
    RED = "\x1b[31m"
    CYAN = "\x1b[36m"
    GREY = "\x1b[90m"
    INV = "\x1b[7m"

    enabled = True

    @classmethod
    def w(cls, s: str, code: str) -> str:
        return f"{code}{s}{cls.RESET}" if cls.enabled else s


# ---------------------------------------------------------------------------
# Robust CSV parsing (never raises)
# ---------------------------------------------------------------------------

def _safe_int(v: Any, default: int = 0) -> int:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        if v is None or v == "":
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


def _read_prices_csv(path: str) -> List[dict]:
    if not path or not os.path.isfile(path):
        return []
    out: List[dict] = []
    try:
        with open(path, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f, delimiter=";")
            for row in reader:
                out.append(row)
    except Exception:
        return out
    return out


def _read_trades_csv(path: str) -> List[dict]:
    if not path or not os.path.isfile(path):
        return []
    out: List[dict] = []
    try:
        with open(path, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f, delimiter=";")
            for row in reader:
                out.append(row)
    except Exception:
        return out
    return out


# ---------------------------------------------------------------------------
# Snapshot model
# ---------------------------------------------------------------------------

class Snapshot:
    """Aggregated view of latest prices + trades."""

    def __init__(self, prices_rows: List[dict], trades_rows: List[dict]):
        self.prices = prices_rows
        self.trades = trades_rows
        self.timestamp = 0
        self.tick = 0
        self.pnl_per_product: Dict[str, float] = {}
        self.position_per_product: Dict[str, int] = {}   # estimated from trades
        self.spread_per_product: Dict[str, float] = {}
        self.depth_per_product: Dict[str, int] = {}
        self.mid_per_product: Dict[str, float] = {}
        self.trades_per_product: Dict[str, List[dict]] = defaultdict(list)
        self.last_update_per_product: Dict[str, int] = {}
        self.pnl_total: float = 0.0
        self._compute()

    def _compute(self) -> None:
        # latest row per product → spread/depth/mid/PnL
        per_prod: Dict[str, dict] = {}
        for row in self.prices:
            ts = _safe_int(row.get("timestamp"))
            sym = row.get("product") or ""
            if not sym:
                continue
            prev = per_prod.get(sym)
            if prev is None or _safe_int(prev.get("timestamp")) < ts:
                per_prod[sym] = row
            if ts > self.timestamp:
                self.timestamp = ts
        self.tick = self.timestamp // 100

        for sym, row in per_prod.items():
            self.last_update_per_product[sym] = _safe_int(row.get("timestamp"))
            bid1 = _safe_int(row.get("bid_price_1"))
            ask1 = _safe_int(row.get("ask_price_1"))
            bv1 = _safe_int(row.get("bid_volume_1"))
            av1 = _safe_int(row.get("ask_volume_1"))
            self.spread_per_product[sym] = float(ask1 - bid1) if (bid1 and ask1) else 0.0
            self.depth_per_product[sym] = max(bv1, av1)
            self.mid_per_product[sym] = _safe_float(row.get("mid_price"))
            pnl = _safe_float(row.get("profit_and_loss"))
            self.pnl_per_product[sym] = pnl

        self.pnl_total = sum(self.pnl_per_product.values())

        # estimate position from own trades (buyer="" or seller="" tags vary;
        # the live algo log marks own side with our team name, but at a
        # minimum we count net q as a sanity proxy if buyer/seller fields
        # contain "SUBMISSION" or are blank-on-our-side).
        for tr in self.trades:
            sym = tr.get("symbol") or ""
            if not sym:
                continue
            self.trades_per_product[sym].append(tr)
            buyer = (tr.get("buyer") or "").strip().upper()
            seller = (tr.get("seller") or "").strip().upper()
            qty = _safe_int(tr.get("quantity"))
            # Heuristic: in IMC algo log, our own trades have one of the
            # sides equal to "SUBMISSION" (or the team name). We treat
            # buyer=="SUBMISSION" → +qty, seller=="SUBMISSION" → -qty.
            if buyer == "SUBMISSION":
                self.position_per_product[sym] = self.position_per_product.get(sym, 0) + qty
            elif seller == "SUBMISSION":
                self.position_per_product[sym] = self.position_per_product.get(sym, 0) - qty

# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------

class AlertFeed:
    def __init__(self, max_lines: int = 30):
        self.lines: deque = deque(maxlen=max_lines)

    def push(self, severity: str, msg: str, ts: int) -> None:
        self.lines.append((severity, msg, ts))

    def render(self) -> List[str]:
        out = []
        for sev, msg, ts in list(self.lines)[-20:]:
            colour = C.RED if sev == "BLOCKER" else (C.YELLOW if sev == "WARNING" else C.GREY)
            tag = C.w(f"[{sev:7}]", colour + C.BOLD)
            out.append(f"  ts={ts:>7} {tag} {msg}")
        return out


# ---------------------------------------------------------------------------
# Velocity calculator (per-tick PnL series)
# ---------------------------------------------------------------------------

class VelocityHistory:
    def __init__(self):
        self.points: List[Tuple[int, float]] = []  # (timestamp, pnl_total)

    def add(self, ts: int, pnl: float):
        if not self.points or self.points[-1][0] < ts:
            self.points.append((ts, pnl))

    def velocity(self, lookback_ticks: int) -> Optional[float]:
        if len(self.points) < 2:
            return None
        target_ts = self.points[-1][0] - lookback_ticks * 100
        prev = None
        for ts, p in reversed(self.points):
            if ts <= target_ts:
                prev = (ts, p)
                break
        if prev is None:
            prev = self.points[0]
        dt = self.points[-1][0] - prev[0]
        if dt == 0:
            return 0.0
        return (self.points[-1][1] - prev[1]) / (dt / 100.0)


# ---------------------------------------------------------------------------
# Panels
# ---------------------------------------------------------------------------

def _bar(pct: float, width: int = 20) -> str:
    pct = max(0.0, min(1.0, pct))
    n = int(round(pct * width))
    return "[" + "#" * n + "-" * (width - n) + "]"


def _mc_expected(tick: int) -> Tuple[float, float, float]:
    """Return (expected_pnl, lower_1sigma, upper_1sigma) at this tick."""
    frac = max(0.0, min(1.0, tick / ROUND_TICKS))
    mean = MC_FINAL_MEAN * frac
    sigma = MC_FINAL_STD * (frac ** 0.5)  # variance grows linearly w/ time
    return mean, mean - sigma, mean + sigma


def panel_pnl(snap: Snapshot, vel: VelocityHistory) -> List[str]:
    out = ["", C.w("=== 1. PNL TRACKER ===", C.BOLD + C.CYAN)]
    if snap.timestamp == 0:
        out.append("  NO DATA")
        return out
    exp, lo, hi = _mc_expected(snap.tick)
    delta = snap.pnl_total - exp
    if snap.pnl_total < lo:
        verdict = C.w("BEHIND CI", C.RED + C.BOLD)
    elif snap.pnl_total > hi:
        verdict = C.w("AHEAD CI ", C.GREEN + C.BOLD)
    else:
        verdict = C.w("WITHIN CI", C.GREEN)

    out.append(f"  Total PnL:  {snap.pnl_total:>+10,.1f}    "
                f"MC expected: {exp:>+8,.1f}  CI=[{lo:>+8,.1f}, {hi:>+8,.1f}]  "
                f"{verdict}  d={delta:>+8,.1f}")

    v50 = vel.velocity(50)
    v200 = vel.velocity(200)
    v500 = vel.velocity(500)
    fmt = lambda v: "  N/A " if v is None else f"{v:>+6.2f}"
    out.append(f"  Velocity (PnL/tick):  50t={fmt(v50)}   "
                f"200t={fmt(v200)}   500t={fmt(v500)}")

    # per-strategy stacked
    per_strat: Dict[str, float] = defaultdict(float)
    for sym, p in snap.pnl_per_product.items():
        per_strat[PRODUCT_STRATEGY.get(sym, "OTHER")] += p
    out.append("  Per-strategy contribution:")
    for s in ["P2", "S1S2", "S2", "R2", "M1", "M3", "OTHER"]:
        if s in per_strat:
            v = per_strat[s]
            colour = C.GREEN if v >= 0 else C.RED
            out.append(f"    {s:<6} {C.w(f'{v:>+10,.1f}', colour)}")

    # top-3 winners and losers across all products
    tops = sorted(snap.pnl_per_product.items(), key=lambda kv: kv[1], reverse=True)
    if tops:
        out.append("  Top winners: " + "  ".join(
            f"{C.w(s, C.GREEN)}={v:+.0f}" for s, v in tops[:3]))
        out.append("  Top losers : " + "  ".join(
            f"{C.w(s, C.RED)}={v:+.0f}" for s, v in tops[-3:]))
    return out


def _strategy_pnl(snap: Snapshot) -> Dict[str, float]:
    per_strat: Dict[str, float] = defaultdict(float)
    for sym, p in snap.pnl_per_product.items():
        per_strat[PRODUCT_STRATEGY.get(sym, "OTHER")] += p
    return per_strat


def _strategy_last_trade_age(snap: Snapshot, strat: str) -> Optional[int]:
    """Return ticks since last trade on any product in this strategy."""
    products = STRATEGY_PRODUCTS.get(strat, [])
    last_ts = -1
    for sym in products:
        for tr in snap.trades_per_product.get(sym, []):
            ts = _safe_int(tr.get("timestamp"))
            if ts > last_ts:
                last_ts = ts
    if last_ts < 0:
        return None
    return (snap.timestamp - last_ts) // 100


def panel_strategy_health(snap: Snapshot, alerts: AlertFeed) -> List[str]:
    out = ["", C.w("=== 2. STRATEGY HEALTH ===", C.BOLD + C.CYAN)]
    if snap.timestamp == 0:
        out.append("  NO DATA")
        return out
    per_strat = _strategy_pnl(snap)

    out.append(f"  {'Component':<6} {'PnL':>10} {'Status':<10} "
                f"{'Trip Wire':<28} {'Last Fill':>12}")
    for s, tw in TRIP_WIRES.items():
        pnl = per_strat.get(s, 0.0)
        age = _strategy_last_trade_age(snap, s)
        age_s = "n/a" if age is None else f"{age}t ago"
        if snap.tick >= tw["trip_tick"] and pnl <= tw["block_pnl"]:
            status, sc = "TRIPPED", C.RED + C.BOLD
            alerts.push("BLOCKER",
                        f"{s} TRIP-WIRE: PnL={pnl:+.0f} <= {tw['block_pnl']:.0f} "
                        f"at tick {snap.tick} (limit tick {tw['trip_tick']})",
                        snap.timestamp)
        elif snap.tick >= tw["trip_tick"] and pnl <= tw["warn_pnl"]:
            status, sc = "DEGRADED", C.YELLOW
            alerts.push("WARNING",
                        f"{s} degraded: PnL={pnl:+.0f} <= {tw['warn_pnl']:.0f} "
                        f"at tick {snap.tick}", snap.timestamp)
        else:
            status, sc = "HEALTHY", C.GREEN
        wire = f"PnL<{tw['block_pnl']:.0f} by t{tw['trip_tick']}"
        out.append(f"  {s:<6} {pnl:>+10,.1f} {C.w(status, sc):<10} "
                    f"{wire:<28} {age_s:>12}")

    out.append(f"  {'GLOBAL':<6} {snap.pnl_total:>+10,.1f} "
                f"warn<{GLOBAL_WARN_PNL:.0f}  block<{GLOBAL_BLOCK_PNL:.0f}")
    if snap.pnl_total <= GLOBAL_BLOCK_PNL:
        alerts.push("BLOCKER", f"GLOBAL drawdown {snap.pnl_total:+.0f} "
                                f"<= {GLOBAL_BLOCK_PNL}; deploy V6_emergency_brake",
                    snap.timestamp)
    elif snap.pnl_total <= GLOBAL_WARN_PNL:
        alerts.push("WARNING", f"GLOBAL drawdown {snap.pnl_total:+.0f} "
                                f"<= {GLOBAL_WARN_PNL}", snap.timestamp)
    return out


def panel_position(snap: Snapshot, alerts: AlertFeed) -> List[str]:
    out = ["", C.w("=== 3. POSITION & RISK ===", C.BOLD + C.CYAN)]
    if not snap.position_per_product:
        out.append("  NO DATA  (own trades may not be tagged 'SUBMISSION'; "
                    "compute position from your variant's traderData if needed)")
        return out
    nonzero = [(s, p) for s, p in sorted(snap.position_per_product.items())
                if p != 0]
    if not nonzero:
        out.append("  All positions flat.")
        return out
    out.append(f"  {'Product':<28} {'Pos':>5} {'%':>5} {'Bar':<22}")
    sigma_impact = 0.0
    aggregate = 0
    for sym, pos in nonzero:
        pct = abs(pos) / float(POSITION_LIMIT)
        bar = _bar(pct)
        if pct < 0.7:
            colour = C.GREEN
        elif pct < 0.9:
            colour = C.YELLOW
        else:
            colour = C.RED + C.BOLD
            alerts.push("WARNING", f"{sym} position {pos} > 90% of limit",
                        snap.timestamp)
        out.append(f"  {sym:<28} {pos:>+5} "
                    f"{C.w(f'{pct*100:>4.0f}', colour)}% {C.w(bar, colour)}")
        # 1-sigma stress: assume 1-sigma move = SPREAD_BASELINE/2 ≈ 1 spread
        sig = SPREAD_BASELINE.get(sym, 4.0) / 2.0
        sigma_impact += abs(pos) * sig
        aggregate += pos
    out.append(f"  Aggregate directional exposure: {aggregate:+d} units")
    out.append(f"  1-sigma adverse-move PnL impact estimate: "
                f"{C.w(f'-{sigma_impact:,.0f}', C.YELLOW)}")
    return out


def panel_orderbook(snap: Snapshot, alerts: AlertFeed) -> List[str]:
    out = ["", C.w("=== 4. ORDER BOOK HEALTH ===", C.BOLD + C.CYAN)]
    if not snap.spread_per_product:
        out.append("  NO DATA")
        return out
    out.append(f"  {'Product':<28} {'Spread':>8} {'Median':>8} "
                f"{'Ratio':>7} {'Depth':>6} {'p5':>5} {'Mid':>10}")
    abnormal = 0
    for sym in sorted(snap.spread_per_product.keys()):
        sp = snap.spread_per_product[sym]
        med = SPREAD_BASELINE.get(sym, 4.0)
        ratio = sp / med if med > 0 else 0.0
        depth = snap.depth_per_product.get(sym, 0)
        p5 = DEPTH_BASELINE_P5.get(sym, 4)
        mid = snap.mid_per_product.get(sym, 0.0)
        if ratio > 2.0:
            abnormal += 1
            alerts.push("WARNING",
                        f"{sym} spread {sp:.0f} > 2x median ({med:.1f}); "
                        f"market regime may be shifting", snap.timestamp)
            colour = C.RED
        elif ratio > 1.5:
            colour = C.YELLOW
        else:
            colour = C.GREEN
        if depth < p5:
            d_colour = C.RED
        else:
            d_colour = C.GREEN
        out.append(f"  {sym:<28} {sp:>8.0f} {med:>8.1f} "
                    f"{C.w(f'{ratio:>6.2f}', colour)} "
                    f"{C.w(f'{depth:>6}', d_colour)} {p5:>5} {mid:>10.1f}")
    if abnormal:
        out.append(f"  {abnormal} product(s) with spread > 2x median.")
    return out


def panel_alerts(alerts: AlertFeed) -> List[str]:
    out = ["", C.w("=== 5. ANOMALY ALERT FEED ===", C.BOLD + C.CYAN)]
    rendered = alerts.render()
    if not rendered:
        out.append(C.w("  no alerts.", C.GREY))
    else:
        out.extend(rendered)
    return out


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def _autopick(directory: str) -> Tuple[Optional[str], Optional[str]]:
    if not directory or not os.path.isdir(directory):
        return None, None
    prices = sorted(glob.glob(os.path.join(directory, "prices_*.csv")),
                    key=os.path.getmtime, reverse=True)
    trades = sorted(glob.glob(os.path.join(directory, "trades_*.csv")),
                    key=os.path.getmtime, reverse=True)
    return (prices[0] if prices else None), (trades[0] if trades else None)


def _clear_screen() -> None:
    if os.name == "nt":
        # ANSI clear; works on Win10+ console with VT enabled
        sys.stdout.write("\x1b[2J\x1b[H")
    else:
        sys.stdout.write("\x1b[2J\x1b[H")


def render_once(prices_path: str, trades_path: str, vel: VelocityHistory,
                alerts: AlertFeed, my_team: str) -> None:
    prices = _read_prices_csv(prices_path)
    trades = _read_trades_csv(trades_path) if trades_path else []
    snap = Snapshot(prices, trades)
    vel.add(snap.timestamp, snap.pnl_total)

    # Header
    pct = snap.tick * 100.0 / ROUND_TICKS if ROUND_TICKS else 0.0
    bar = _bar(pct / 100.0, 30)
    header = (
        f"{C.w('R5 LIVE MONITOR', C.BOLD + C.INV)}  "
        f"team={my_team}  ts={snap.timestamp}  tick={snap.tick}/{ROUND_TICKS}  "
        f"({pct:.1f}%)  {bar}"
    )
    print(header)
    print(C.w(f"  prices={prices_path or '<none>'}  "
              f"trades={trades_path or '<none>'}", C.DIM))

    for line in panel_pnl(snap, vel):              print(line)
    for line in panel_strategy_health(snap, alerts): print(line)
    for line in panel_position(snap, alerts):      print(line)
    for line in panel_orderbook(snap, alerts):     print(line)
    for line in panel_alerts(alerts):              print(line)
    print()


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--prices", default="")
    p.add_argument("--trades", default="")
    p.add_argument("--dir", default="")
    p.add_argument("--refresh", type=int, default=30)
    p.add_argument("--once", action="store_true")
    p.add_argument("--no-color", action="store_true")
    p.add_argument("--my-team", default="MyTeam")
    args = p.parse_args()

    if args.no_color or os.environ.get("NO_COLOR"):
        C.enabled = False

    # Enable VT mode on Windows so ANSI colours render
    if os.name == "nt" and C.enabled:
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
        except Exception:
            pass

    prices_path = args.prices
    trades_path = args.trades
    if args.dir:
        ap, at = _autopick(args.dir)
        prices_path = prices_path or ap or ""
        trades_path = trades_path or at or ""

    vel = VelocityHistory()
    alerts = AlertFeed()

    try:
        while True:
            _clear_screen()
            try:
                render_once(prices_path, trades_path, vel, alerts, args.my_team)
            except Exception as e:  # never crash the dashboard
                print(C.w(f"render error: {e!r}  (continuing)", C.RED))
            if args.once:
                return 0
            time.sleep(max(1, args.refresh))
    except KeyboardInterrupt:
        print("\nbye.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
