"""Analyze sim 44738 vs 44559 baseline — what changed with EM_NO_SKEW + WIND_DOWN?"""
import json
import re
from collections import defaultdict

LOG_44738 = r".\logs\44738\44738.log"
JSON_44738 = r".\logs\44738\44738.json"
JSON_44559 = r".\logs\44559\44559.json"

# ── Parse JSON for PnL timeseries ───────────────────
def parse_json(path):
    with open(path, "r") as f:
        data = json.load(f)
    
    total_pnl = data.get("profit", data.get("profitAndLoss", 0))
    print(f"  Total PnL: {total_pnl:.2f}")
    
    lines = data["activitiesLog"].strip().split("\n")
    header = lines[0].split(";")
    
    records = []
    for line in lines[1:]:
        parts = line.split(";")
        if len(parts) < len(header):
            continue
        rec = dict(zip(header, parts))
        records.append(rec)
    
    return total_pnl, records

# ── Parse log for fill details ──────────────────────
def parse_log(path):
    fills = []
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                if isinstance(data, list) and len(data) >= 5:
                    state_data = data[0]
                    orders_data = data[1]
                    ts = state_data[0]
                    own_trades = state_data[4]
                    positions = state_data[6]
                    
                    for sym, trades in own_trades.items():
                        for t in trades:
                            fills.append({
                                "symbol": t[0],
                                "price": t[1],
                                "qty": t[2],
                                "buyer": t[3],
                                "seller": t[4],
                                "fill_ts": t[5],
                                "reported_ts": ts,
                            })
            except (json.JSONDecodeError, IndexError, TypeError):
                continue
    return fills

print("=" * 80)
print("SIM 44738 ANALYSIS (EM_NO_SKEW + WIND_DOWN changes)")
print("=" * 80)

print("\n── 44738 (new) ──")
pnl_738, records_738 = parse_json(JSON_44738)

print("\n── 44559 (baseline) ──")
pnl_559, records_559 = parse_json(JSON_44559)

print(f"\n  DELTA: {pnl_738 - pnl_559:+.2f} ({pnl_738:.2f} vs {pnl_559:.2f})")

# ── PnL by product and day ──────────────────────────
print("\n" + "=" * 80)
print("PNL BY PRODUCT & DAY")
print("=" * 80)

def pnl_breakdown(records):
    """Get final PnL for each product on each day."""
    day_product = {}
    for rec in records:
        day = int(rec["day"])
        ts = int(rec["timestamp"])
        product = rec["product"]
        pnl = float(rec["profit_and_loss"])
        key = (day, product)
        if key not in day_product or ts > day_product[key][0]:
            day_product[key] = (ts, pnl)
    return {k: v[1] for k, v in day_product.items()}

bp738 = pnl_breakdown(records_738)
bp559 = pnl_breakdown(records_559)

print(f"\n{'':15s} {'44559':>10s} {'44738':>10s} {'Delta':>10s}")
print("-" * 50)
for key in sorted(set(list(bp738.keys()) + list(bp559.keys()))):
    old = bp559.get(key, 0)
    new = bp738.get(key, 0)
    label = f"Day {key[0]} {key[1]}"
    print(f"  {label:15s} {old:>10.2f} {new:>10.2f} {new-old:>+10.2f}")
    
em_old = sum(v for k, v in bp559.items() if k[1] == "EMERALDS")
em_new = sum(v for k, v in bp738.items() if k[1] == "EMERALDS")
tom_old = sum(v for k, v in bp559.items() if k[1] == "TOMATOES")
tom_new = sum(v for k, v in bp738.items() if k[1] == "TOMATOES")
print("-" * 50)
print(f"  {'EMERALDS total':15s} {em_old:>10.2f} {em_new:>10.2f} {em_new-em_old:>+10.2f}")
print(f"  {'TOMATOES total':15s} {tom_old:>10.2f} {tom_new:>10.2f} {tom_new-tom_old:>+10.2f}")
print(f"  {'GRAND TOTAL':15s} {pnl_559:>10.2f} {pnl_738:>10.2f} {pnl_738-pnl_559:>+10.2f}")

# ── Fill analysis ──────────────────────────────────────
print("\n" + "=" * 80)
print("FILL ANALYSIS (from log file)")  
print("=" * 80)

fills = parse_log(LOG_44738)

# Deduplicate: fills appear at reported_ts = fill_ts + 100
seen = set()
unique_fills = []
for f in fills:
    key = (f["symbol"], f["price"], f["qty"], f["fill_ts"])
    if key not in seen:
        seen.add(key)
        unique_fills.append(f)

by_sym = defaultdict(list)
for f in unique_fills:
    by_sym[f["symbol"]].append(f)

for sym in sorted(by_sym):
    sym_fills = by_sym[sym]
    buys = [f for f in sym_fills if f["qty"] > 0]
    sells = [f for f in sym_fills if f["qty"] < 0]
    
    total_buy_qty = sum(f["qty"] for f in buys)
    total_sell_qty = sum(abs(f["qty"]) for f in sells)
    total_buy_val = sum(f["qty"] * f["price"] for f in buys)
    total_sell_val = sum(abs(f["qty"]) * f["price"] for f in sells)
    
    # categorize: take vs make
    # For EMERALDS: takes are at 9999/10001, makes are at 9993/10007
    # For TOMATOES: takes are near mid, makes are at mid ± 5
    takes = []
    makes = []
    for f in sym_fills:
        if sym == "EMERALDS":
            if abs(f["price"] - 10000) <= 1:
                takes.append(f)
            else:
                makes.append(f)
        else:
            makes.append(f)  # all tomatoes are effectively makes with TAKE_EDGE=0
    
    print(f"\n  {sym}:")
    print(f"    Total fills: {len(sym_fills)} ({len(buys)} buys, {len(sells)} sells)")
    print(f"    Buy qty: {total_buy_qty}, Sell qty: {total_sell_qty}")
    if total_buy_qty > 0:
        print(f"    Avg buy price:  {total_buy_val/total_buy_qty:.2f}")
    if total_sell_qty > 0:
        print(f"    Avg sell price: {total_sell_val/total_sell_qty:.2f}")
    if takes:
        print(f"    Take fills: {len(takes)}")
    if makes:
        make_buys = [f for f in makes if f["qty"] > 0]
        make_sells = [f for f in makes if f["qty"] < 0]
        print(f"    Make fills: {len(makes)} ({len(make_buys)} buy, {len(make_sells)} sell)")
        if make_buys:
            prices = [f["price"] for f in make_buys]
            print(f"    Make buy prices: {sorted(set(prices))}")
        if make_sells:
            prices = [f["price"] for f in make_sells]
            print(f"    Make sell prices: {sorted(set(prices))}")

# ── Position trajectory ─────────────────────────────
print("\n" + "=" * 80)
print("POSITION TRAJECTORY (from log)")
print("=" * 80)

positions_by_ts = defaultdict(dict)
with open(LOG_44738, "r") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
            if isinstance(data, list) and len(data) >= 5:
                ts = data[0][0]
                pos = data[0][6]
                for sym, p in pos.items():
                    positions_by_ts[ts][sym] = p
        except:
            continue

# Find end-of-day positions and wind-down period
print("\n  End-of-day positions:")
all_ts = sorted(positions_by_ts.keys())
if all_ts:
    # Day -1 data
    day1_ts = [t for t in all_ts if t <= 200000]  # approximate
    if day1_ts:
        last_ts = day1_ts[-1]
        print(f"    Last recorded ts: {last_ts}")
        print(f"    Positions: {positions_by_ts[last_ts]}")
    
    # Show wind-down period positions
    wind_ts = [t for t in all_ts if t >= 180000]
    if wind_ts:
        print(f"\n  Wind-down period (ts >= 180000):")
        print(f"    {'Timestamp':>10s}  {'EMERALDS':>10s}  {'TOMATOES':>10s}")
        for ts in wind_ts[:20]:
            em = positions_by_ts[ts].get("EMERALDS", 0)
            tom = positions_by_ts[ts].get("TOMATOES", 0)
            print(f"    {ts:>10d}  {em:>10d}  {tom:>10d}")

# ── Compare fill timestamps vs 44559 ────────────────
print("\n" + "=" * 80)
print("FILL COMPARISON vs 44559")
print("=" * 80)

LOG_44559 = r".\logs\44559\44559.log"
fills_559 = parse_log(LOG_44559)
seen559 = set()
unique_559 = []
for f in fills_559:
    key = (f["symbol"], f["price"], f["qty"], f["fill_ts"])
    if key not in seen559:
        seen559.add(key)
        unique_559.append(f)

by_sym_559 = defaultdict(list)
for f in unique_559:
    by_sym_559[f["symbol"]].append(f)

for sym in sorted(set(list(by_sym.keys()) + list(by_sym_559.keys()))):
    n_old = len(by_sym_559.get(sym, []))
    n_new = len(by_sym.get(sym, []))
    print(f"  {sym}: {n_old} fills (old) → {n_new} fills (new), delta={n_new - n_old:+d}")
    
    # Check if fill timestamps differ
    old_ts = set((f["fill_ts"], f["price"], f["qty"]) for f in by_sym_559.get(sym, []))
    new_ts = set((f["fill_ts"], f["price"], f["qty"]) for f in by_sym.get(sym, []))
    
    only_old = old_ts - new_ts
    only_new = new_ts - old_ts
    
    if only_old:
        print(f"    Fills in 44559 but NOT in 44738: {len(only_old)}")
        for ts, p, q in sorted(only_old)[:5]:
            print(f"      ts={ts} price={p} qty={q}")
    if only_new:
        print(f"    Fills in 44738 but NOT in 44559: {len(only_new)}")
        for ts, p, q in sorted(only_new)[:5]:
            print(f"      ts={ts} price={p} qty={q}")
    if not only_old and not only_new:
        print(f"    All fill timestamps identical")

print("\nDone.")
