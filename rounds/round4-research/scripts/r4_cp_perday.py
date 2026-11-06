"""Per-day counterparty PnL audit across R4 backtest days + live day 487874.

For each (counterparty, symbol), compute mark-to-day-end-mid PnL per day.
A trader is a 'follow' candidate iff PnL is positive on ALL days (or all but one
with small magnitude). That filter rejects lucky 1-day fingerprints.
"""
import csv
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "backtester_data" / "round4"
LIVE = ROOT / "logs" / "487874" / "487874.log"


def end_mids(prices_csv: Path) -> dict:
    """Return {symbol: last mid_price} for the day."""
    last = {}
    last_ts = {}
    with open(prices_csv, newline="") as f:
        r = csv.DictReader(f, delimiter=";")
        for row in r:
            sym = row["product"]
            ts = int(row["timestamp"])
            try:
                mid = float(row["mid_price"])
            except Exception:
                continue
            if sym not in last_ts or ts > last_ts[sym]:
                last_ts[sym] = ts
                last[sym] = mid
    return last


def cp_pnl_from_trades(trades_csv: Path, end_mid: dict) -> dict:
    """{(cp, sym): pnl_marked_to_day_end} for each named counterparty."""
    pnl = defaultdict(float)
    with open(trades_csv, newline="") as f:
        r = csv.DictReader(f, delimiter=";")
        for row in r:
            sym = row["symbol"]
            try:
                px = float(row["price"]); qty = int(row["quantity"])
            except Exception:
                continue
            mid = end_mid.get(sym)
            if mid is None:
                continue
            buyer = row.get("buyer", "")
            seller = row.get("seller", "")
            # buyer made +qty at px → MTM = qty*(mid - px)
            # seller made -qty at px → MTM = qty*(px - mid)
            if buyer:
                pnl[(buyer, sym)] += qty * (mid - px)
            if seller:
                pnl[(seller, sym)] += qty * (px - mid)
    return pnl


def cp_pnl_from_live_log(log_path: Path) -> tuple:
    d = json.load(open(log_path, "r", encoding="utf-8", errors="replace"))
    # End mid per symbol from activitiesLog
    lines = d["activitiesLog"].strip().split("\n")
    hdr = lines[0].split(";")
    ip = hdr.index("product"); its = hdr.index("timestamp"); imid = hdr.index("mid_price")
    last_mid, last_ts = {}, {}
    for l in lines[1:]:
        parts = l.split(";")
        try: mid = float(parts[imid]); ts = int(parts[its])
        except Exception: continue
        sym = parts[ip]
        if sym not in last_ts or ts > last_ts[sym]:
            last_ts[sym] = ts; last_mid[sym] = mid
    pnl = defaultdict(float)
    for t in d["tradeHistory"]:
        sym = t["symbol"]; px = float(t["price"]); qty = int(t["quantity"])
        mid = last_mid.get(sym)
        if mid is None: continue
        b, s = t.get("buyer",""), t.get("seller","")
        if b and b != "SUBMISSION": pnl[(b, sym)] += qty * (mid - px)
        if s and s != "SUBMISSION": pnl[(s, sym)] += qty * (px - mid)
    return pnl


# Build per-day cp pnl
day_pnls = {}
for day in [1, 2, 3]:
    prices = DATA / f"prices_round_4_day_{day}.csv"
    trades = DATA / f"trades_round_4_day_{day}.csv"
    if not prices.exists() or not trades.exists():
        print(f"Missing data for day {day}: {prices.exists()} {trades.exists()}")
        continue
    em = end_mids(prices)
    day_pnls[f"d{day}"] = cp_pnl_from_trades(trades, em)

# Live (day 3 separate)
day_pnls["live3"] = cp_pnl_from_live_log(LIVE)

# Aggregate: list all (cp, sym) and their per-day pnls
all_keys = set()
for dp in day_pnls.values(): all_keys.update(dp.keys())

# Focus on Mark/Camilla/etc named counterparties, and on key symbols
KEY_SYMS = {"VELVETFRUIT_EXTRACT", "HYDROGEL_PACK"} | {f"VEV_{k}" for k in [4000, 4500, 5000, 5100, 5200, 5300, 5400, 5500]}

print(f"\n{'CP':>10} {'SYM':>22} {'D1':>9} {'D2':>9} {'D3':>9} {'LIVE3':>9} {'STAB':>5}")
rows = []
for cp, sym in sorted(all_keys):
    if sym not in KEY_SYMS: continue
    if not (cp and cp.startswith("Mark")): continue
    vals = [day_pnls[k].get((cp, sym), 0.0) for k in ["d1","d2","d3","live3"]]
    # Stability: how many days have PnL with same sign as mean
    if all(abs(v) < 50 for v in vals): continue   # noise
    mean = sum(vals)/4
    same_sign = sum(1 for v in vals if (v >= 0) == (mean >= 0))
    rows.append((cp, sym, vals, mean, same_sign))

rows.sort(key=lambda r: -abs(r[3]))
for cp, sym, vals, mean, ss in rows[:30]:
    print(f"{cp:>10} {sym:>22} {vals[0]:>9,.0f} {vals[1]:>9,.0f} {vals[2]:>9,.0f} {vals[3]:>9,.0f}  {ss}/4")
