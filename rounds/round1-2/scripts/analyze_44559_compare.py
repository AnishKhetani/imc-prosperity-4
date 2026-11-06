"""
Compare 44559 vs 42400 to understand the +20.44 PnL improvement.
Also: deep position bias analysis, and potential improvements.
"""

import json
import csv
import io
from collections import defaultdict, Counter

# Load 44559
with open("logs/44559/44559.log", "r") as f:
    data_44559 = json.load(f)

# Load 42400
with open("logs/42400/42400.log", "r") as f:
    data_42400 = json.load(f)

def parse_log(data):
    activities_csv = data["activitiesLog"]
    reader = csv.DictReader(io.StringIO(activities_csv), delimiter=";")
    activities = list(reader)
    
    product_ticks = defaultdict(list)
    for row in activities:
        product_ticks[row["product"]].append(row)
    
    trades_by_product = defaultdict(list)
    for t in data["tradeHistory"]:
        trades_by_product[t["symbol"]].append(t)
    
    return product_ticks, trades_by_product

pt_44559, tb_44559 = parse_log(data_44559)
pt_42400, tb_42400 = parse_log(data_42400)

# ═══════════════════════════════════════════════════════════
# 1. BASIC COMPARISON
# ═══════════════════════════════════════════════════════════
print("="*70)
print("44559 vs 42400 — COMPARISON")
print("="*70)

for prod in ["EMERALDS", "TOMATOES"]:
    pnl_44559 = float(pt_44559[prod][-1]["profit_and_loss"])
    pnl_42400 = float(pt_42400[prod][-1]["profit_and_loss"])
    
    fills_44559 = len(tb_44559[prod])
    fills_42400 = len(tb_42400[prod])
    
    qty_44559 = sum(t["quantity"] for t in tb_44559[prod])
    qty_42400 = sum(t["quantity"] for t in tb_42400[prod])
    
    print(f"\n  {prod}:")
    print(f"    PnL: {pnl_42400:.2f} -> {pnl_44559:.2f} ({pnl_44559-pnl_42400:+.2f})")
    print(f"    Fills: {fills_42400} -> {fills_44559} ({fills_44559-fills_42400:+d})")
    print(f"    Total qty: {qty_42400} -> {qty_44559} ({qty_44559-qty_42400:+d})")

# ═══════════════════════════════════════════════════════════
# 2. FILL TIMESTAMP COMPARISON (are fills the same?)
# ═══════════════════════════════════════════════════════════
print("\n" + "="*70)
print("FILL TIMESTAMPS — MATCH ANALYSIS")
print("="*70)

for prod in ["EMERALDS", "TOMATOES"]:
    ts_44559 = set(t["timestamp"] for t in tb_44559[prod])
    ts_42400 = set(t["timestamp"] for t in tb_42400[prod])
    
    common = ts_44559 & ts_42400
    only_44559 = ts_44559 - ts_42400
    only_42400 = ts_42400 - ts_44559
    
    print(f"\n  {prod}:")
    print(f"    Common fill ticks: {len(common)}")
    print(f"    Only in 44559: {len(only_44559)} — {sorted(only_44559)[:20]}")
    print(f"    Only in 42400: {len(only_42400)} — {sorted(only_42400)[:20]}")

# ═══════════════════════════════════════════════════════════
# 3. FILL PRICE COMPARISON (same ticks, different prices?)
# ═══════════════════════════════════════════════════════════
print("\n" + "="*70)
print("FILL PRICE COMPARISON (common ticks)")
print("="*70)

for prod in ["EMERALDS", "TOMATOES"]:
    fills_44559 = {t["timestamp"]: t for t in tb_44559[prod]}
    fills_42400 = {t["timestamp"]: t for t in tb_42400[prod]}
    
    common_ts = sorted(set(fills_44559.keys()) & set(fills_42400.keys()))
    
    price_diffs = 0
    qty_diffs = 0
    side_diffs = 0
    
    for ts in common_ts:
        f1 = fills_44559[ts]
        f2 = fills_42400[ts]
        
        if f1["price"] != f2["price"]:
            price_diffs += 1
            print(f"    {prod} t={ts}: price {f2['price']} -> {f1['price']}")
        if f1["quantity"] != f2["quantity"]:
            qty_diffs += 1
            print(f"    {prod} t={ts}: qty {f2['quantity']} -> {f1['quantity']}")
        if (f1["buyer"] == "SUBMISSION") != (f2["buyer"] == "SUBMISSION"):
            side_diffs += 1
            print(f"    {prod} t={ts}: SIDE CHANGED")
    
    print(f"  {prod}: {price_diffs} price diffs, {qty_diffs} qty diffs, {side_diffs} side diffs out of {len(common_ts)} common fills")

# ═══════════════════════════════════════════════════════════
# 4. TOMATOES POSITION BIAS ANALYSIS
# ═══════════════════════════════════════════════════════════
print("\n" + "="*70)
print("TOMATOES — POSITION BIAS DEEP DIVE")
print("="*70)

for label, data_trades in [("42400", tb_42400["TOMATOES"]), ("44559", tb_44559["TOMATOES"])]:
    position = 0
    buy_side_qty = 0
    sell_side_qty = 0
    time_short = 0
    time_long = 0
    time_neutral = 0
    last_ts = 0
    
    pos_snapshots = []
    for t in sorted(data_trades, key=lambda x: x["timestamp"]):
        # Time at previous position
        gap = t["timestamp"] - last_ts if last_ts > 0 else 0
        if position > 0:
            time_long += gap
        elif position < 0:
            time_short += gap
        else:
            time_neutral += gap
        
        if t["buyer"] == "SUBMISSION":
            position += t["quantity"]
            buy_side_qty += t["quantity"]
        else:
            position -= t["quantity"]
            sell_side_qty += t["quantity"]
        
        last_ts = t["timestamp"]
        pos_snapshots.append((t["timestamp"], position))
    
    print(f"\n  {label}:")
    print(f"    Buy qty: {buy_side_qty}, Sell qty: {sell_side_qty}")
    print(f"    Net: {buy_side_qty - sell_side_qty}")
    print(f"    Time long: {time_long/200000*100:.1f}%, short: {time_short/200000*100:.1f}%, neutral: {time_neutral/200000*100:.1f}%")

# ═══════════════════════════════════════════════════════════
# 5. TOMATOES — WHERE DOES EDGE COME FROM?
# ═══════════════════════════════════════════════════════════
print("\n" + "="*70)
print("TOMATOES — EDGE SOURCE: TAKING AT BID vs ASK")
print("="*70)

for label, data_trades, product_ticks_data in [
    ("44559", tb_44559["TOMATOES"], pt_44559),
]:
    book_at = {}
    for row in product_ticks_data["TOMATOES"]:
        ts = int(row["timestamp"])
        bp1 = int(row["bid_price_1"]) if row.get("bid_price_1") and row["bid_price_1"] else None
        ap1 = int(row["ask_price_1"]) if row.get("ask_price_1") and row["ask_price_1"] else None
        mid = float(row["mid_price"]) if row.get("mid_price") and row["mid_price"] else None
        book_at[ts] = {"bp1": bp1, "ap1": ap1, "mid": mid}
    
    take_bid_edge = 0.0
    take_ask_edge = 0.0
    take_bid_count = 0
    take_ask_count = 0
    
    for t in data_trades:
        ts = t["timestamp"]
        prev = book_at.get(ts - 100, {})
        curr = book_at.get(ts, {})
        mid = curr.get("mid")
        if mid is None:
            continue
        
        is_buy = t["buyer"] == "SUBMISSION"
        
        if is_buy:
            edge = mid - t["price"]
            # Taking at ask = buying the ask
            is_at_bid = prev.get("bp1") and t["price"] == prev["bp1"]
            take_ask_count += 1
            take_ask_edge += edge * t["quantity"]
        else:
            edge = t["price"] - mid
            # Taking at bid = selling the bid
            is_at_ask = prev.get("ap1") and t["price"] == prev["ap1"]
            take_bid_count += 1
            take_bid_edge += edge * t["quantity"]
    
    print(f"\n  {label}:")
    print(f"    Buy fills (taking asks): {take_ask_count}, weighted edge: {take_ask_edge:.1f}")
    print(f"    Sell fills (taking bids): {take_bid_count}, weighted edge: {take_bid_edge:.1f}")
    if take_ask_count > 0:
        print(f"    Avg buy edge/unit: {take_ask_edge/sum(t['quantity'] for t in data_trades if t['buyer']=='SUBMISSION'):.2f}")
    if take_bid_count > 0:
        print(f"    Avg sell edge/unit: {take_bid_edge/sum(t['quantity'] for t in data_trades if t['seller']=='SUBMISSION'):.2f}")

# ═══════════════════════════════════════════════════════════
# 6. TOMATOES — TAKING vs BOT SPREAD: WHERE IN SPREAD ARE WE?
# ═══════════════════════════════════════════════════════════
print("\n" + "="*70)
print("TOMATOES — TAKE POSITION IN SPREAD")
print("="*70)

position = 0
for t in sorted(tb_44559["TOMATOES"], key=lambda x: x["timestamp"]):
    ts = t["timestamp"]
    is_buy = t["buyer"] == "SUBMISSION"
    
    book_at_data = {}
    for row in pt_44559["TOMATOES"]:
        rts = int(row["timestamp"])
        if rts == ts - 100:
            bp1 = int(row["bid_price_1"]) if row.get("bid_price_1") and row["bid_price_1"] else 0
            ap1 = int(row["ask_price_1"]) if row.get("ask_price_1") and row["ask_price_1"] else 0
            book_at_data = {"bp1": bp1, "ap1": ap1}
            break
    
    if is_buy:
        position += t["quantity"]
    else:
        position -= t["quantity"]

# More efficient version
print("  (see detailed fill analysis above)")

# ═══════════════════════════════════════════════════════════
# 7. EMERALDS — IS SKEW COSTING US EDGE?
# ═══════════════════════════════════════════════════════════
print("\n" + "="*70)
print("EMERALDS — SKEW IMPACT ON PNL")
print("="*70)

# Count fills at 10006 vs 10007
em_trades = tb_44559["EMERALDS"]
sells_at_10006 = sum(t["quantity"] for t in em_trades if t["seller"] == "SUBMISSION" and t["price"] == 10006)
sells_at_10007 = sum(t["quantity"] for t in em_trades if t["seller"] == "SUBMISSION" and t["price"] == 10007)
buys_at_9993 = sum(t["quantity"] for t in em_trades if t["buyer"] == "SUBMISSION" and t["price"] == 9993)
buys_at_9994 = sum(t["quantity"] for t in em_trades if t["buyer"] == "SUBMISSION" and t["price"] == 9994)

print(f"  Sells @ 10007 (full edge=7): {sells_at_10007} units")
print(f"  Sells @ 10006 (edge=6, skewed): {sells_at_10006} units")
print(f"  Buys @ 9993 (full edge=7): {buys_at_9993} units")
print(f"  Buys @ 9994 (edge=6, skewed): {buys_at_9994} units")

# PnL cost of skew
skew_cost = sells_at_10006 * 1  # lost 1 tick on each
print(f"  PnL cost of ask skew (10006 instead of 10007): -{skew_cost}")
print(f"  If ALL sells were at 10007: +{skew_cost} additional PnL")

# ═══════════════════════════════════════════════════════════
# 8. TOMATOES — ADVERSE SELECTION FROM TAKING
# ═══════════════════════════════════════════════════════════
print("\n" + "="*70)
print("TOMATOES — ADVERSE SELECTION CHECK")
print("="*70)
print("  (does the mid move against us after we take?)")

tom_trades_sorted = sorted(tb_44559["TOMATOES"], key=lambda x: x["timestamp"])
book_lookup = {}
for row in pt_44559["TOMATOES"]:
    ts = int(row["timestamp"])
    mid = float(row["mid_price"]) if row.get("mid_price") and row["mid_price"] else None
    book_lookup[ts] = mid

results = []
for t in tom_trades_sorted:
    ts = t["timestamp"]
    is_buy = t["buyer"] == "SUBMISSION"
    
    mid_at_fill = book_lookup.get(ts)
    # Check mid 5, 10, 20 ticks later
    mid_5 = book_lookup.get(ts + 500)
    mid_10 = book_lookup.get(ts + 1000)
    mid_20 = book_lookup.get(ts + 2000)
    
    if mid_at_fill is None:
        continue
    
    results.append({
        "ts": ts, "is_buy": is_buy,
        "mid_0": mid_at_fill,
        "mid_5": mid_5, "mid_10": mid_10, "mid_20": mid_20,
    })

# Calculate average adverse selection
buy_adverse_5 = []
buy_adverse_10 = []
buy_adverse_20 = []
sell_adverse_5 = []
sell_adverse_10 = []
sell_adverse_20 = []

for r in results:
    if r["is_buy"]:
        if r["mid_5"] is not None:
            buy_adverse_5.append(r["mid_5"] - r["mid_0"])
        if r["mid_10"] is not None:
            buy_adverse_10.append(r["mid_10"] - r["mid_0"])
        if r["mid_20"] is not None:
            buy_adverse_20.append(r["mid_20"] - r["mid_0"])
    else:
        if r["mid_5"] is not None:
            sell_adverse_5.append(r["mid_0"] - r["mid_5"])
        if r["mid_10"] is not None:
            sell_adverse_10.append(r["mid_0"] - r["mid_10"])
        if r["mid_20"] is not None:
            sell_adverse_20.append(r["mid_0"] - r["mid_20"])

def avg(lst):
    return sum(lst) / len(lst) if lst else 0

print(f"  After BUY fills (positive = price went up = GOOD):")
print(f"    +5 ticks: {avg(buy_adverse_5):+.2f} ({len(buy_adverse_5)} samples)")
print(f"    +10 ticks: {avg(buy_adverse_10):+.2f} ({len(buy_adverse_10)} samples)")
print(f"    +20 ticks: {avg(buy_adverse_20):+.2f} ({len(buy_adverse_20)} samples)")
print(f"  After SELL fills (positive = price went down = GOOD):")
print(f"    +5 ticks: {avg(sell_adverse_5):+.2f} ({len(sell_adverse_5)} samples)")
print(f"    +10 ticks: {avg(sell_adverse_10):+.2f} ({len(sell_adverse_10)} samples)")
print(f"    +20 ticks: {avg(sell_adverse_20):+.2f} ({len(sell_adverse_20)} samples)")

# ═══════════════════════════════════════════════════════════
# 9. TOMATOES — WHAT IF WE DIDN'T TAKE? (make-only PnL)
# ═══════════════════════════════════════════════════════════
print("\n" + "="*70)
print("TOMATOES — TAKE EDGE BREAKDOWN")
print("="*70)

book_at_full = {}
for row in pt_44559["TOMATOES"]:
    ts = int(row["timestamp"])
    bp1 = int(row["bid_price_1"]) if row.get("bid_price_1") and row["bid_price_1"] else None
    ap1 = int(row["ask_price_1"]) if row.get("ask_price_1") and row["ask_price_1"] else None
    mid = float(row["mid_price"]) if row.get("mid_price") and row["mid_price"] else None
    book_at_full[ts] = {"bp1": bp1, "ap1": ap1, "mid": mid}

# For each take, what's the distance from fill price to the OPPOSITE side of book?
# If we BUY (take ask), the "true" edge is distance to the opposite bid
# If we SELL (take bid), edge is distance to opposite ask
for t in tom_trades_sorted:
    ts = t["timestamp"]
    prev = book_at_full.get(ts - 100, {})
    is_buy = t["buyer"] == "SUBMISSION"
    
    if is_buy:
        # We're buying. Taking the ask (or near it). 
        # Our fair estimate = EMA (unknown), but let's check where in the spread we take
        if prev.get("bp1") and prev.get("ap1"):
            spread = prev["ap1"] - prev["bp1"]
            distance_from_ask = prev["ap1"] - t["price"]
            distance_from_bid = t["price"] - prev["bp1"]
            # Edge = how much inside spread we captured from ask side
    # This is getting complex; the detailed fill table above has all this info already

# Instead: how much of our edge comes from takes vs how much from inventory MTM?
total_take_pnl = 0.0
for t in tom_trades_sorted:
    ts = t["timestamp"]
    curr = book_at_full.get(ts, {})
    mid = curr.get("mid")
    if mid is None:
        continue
    
    if t["buyer"] == "SUBMISSION":
        total_take_pnl += (mid - t["price"]) * t["quantity"]
    else:
        total_take_pnl += (t["price"] - mid) * t["quantity"]

reported_pnl = float(pt_44559["TOMATOES"][-1]["profit_and_loss"])
inventory_pnl = reported_pnl - total_take_pnl  # rough approximation

print(f"  Total edge from takes: {total_take_pnl:.1f}")
print(f"  Reported PnL: {reported_pnl:.2f}")
print(f"  Difference (inventory drift + MTM): {inventory_pnl:.2f}")

# ═══════════════════════════════════════════════════════════
# 10. TOMATOES — SELL BIAS: ARE WE SELLING MORE?
# ═══════════════════════════════════════════════════════════
print("\n" + "="*70)
print("TOMATOES — BUY/SELL BIAS BY TIME QUARTER")
print("="*70)

for label, data_trades in [("44559", tb_44559["TOMATOES"]), ("42400", tb_42400["TOMATOES"])]:
    total_ts = max(t["timestamp"] for t in data_trades)
    q_boundary = total_ts / 4
    quarters = {1: {"buys": 0, "sells": 0, "buy_qty": 0, "sell_qty": 0},
                2: {"buys": 0, "sells": 0, "buy_qty": 0, "sell_qty": 0},
                3: {"buys": 0, "sells": 0, "buy_qty": 0, "sell_qty": 0},
                4: {"buys": 0, "sells": 0, "buy_qty": 0, "sell_qty": 0}}
    
    for t in data_trades:
        q = min(4, int(t["timestamp"] / q_boundary) + 1)
        if t["buyer"] == "SUBMISSION":
            quarters[q]["buys"] += 1
            quarters[q]["buy_qty"] += t["quantity"]
        else:
            quarters[q]["sells"] += 1
            quarters[q]["sell_qty"] += t["quantity"]
    
    print(f"\n  {label}:")
    for q in range(1, 5):
        d = quarters[q]
        net = d["buy_qty"] - d["sell_qty"]
        print(f"    Q{q}: {d['buys']} buys ({d['buy_qty']}q), {d['sells']} sells ({d['sell_qty']}q), net={net:+d}")

print("\n\nDone.")
