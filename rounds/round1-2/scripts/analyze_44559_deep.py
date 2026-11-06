"""
Deep-dive analysis of 44559 — order execution, edge, negative fills, comparison with 42400.
"""

import json
import csv
import io
from collections import defaultdict, Counter

LOG_PATH = "logs/44559/44559.log"

with open(LOG_PATH, "r") as f:
    data = json.load(f)

activities_csv = data["activitiesLog"]
reader = csv.DictReader(io.StringIO(activities_csv), delimiter=";")
activities = list(reader)

product_ticks = defaultdict(list)
for row in activities:
    product_ticks[row["product"]].append(row)

trades = data["tradeHistory"]
trades_by_product = defaultdict(list)
for t in trades:
    trades_by_product[t["symbol"]].append(t)

book_at_tick = {}
for prod, rows in product_ticks.items():
    for row in rows:
        ts = int(row["timestamp"])
        bp1 = int(row["bid_price_1"]) if row.get("bid_price_1") and row["bid_price_1"] else None
        ap1 = int(row["ask_price_1"]) if row.get("ask_price_1") and row["ask_price_1"] else None
        bp2 = int(row["bid_price_2"]) if row.get("bid_price_2") and row["bid_price_2"] else None
        ap2 = int(row["ask_price_2"]) if row.get("ask_price_2") and row["ask_price_2"] else None
        bp3 = int(row["bid_price_3"]) if row.get("bid_price_3") and row["bid_price_3"] else None
        ap3 = int(row["ask_price_3"]) if row.get("ask_price_3") and row["ask_price_3"] else None
        bv1 = int(row["bid_volume_1"]) if row.get("bid_volume_1") and row["bid_volume_1"] else 0
        av1 = int(row["ask_volume_1"]) if row.get("ask_volume_1") and row["ask_volume_1"] else 0
        bv2 = int(row["bid_volume_2"]) if row.get("bid_volume_2") and row["bid_volume_2"] else 0
        av2 = int(row["ask_volume_2"]) if row.get("ask_volume_2") and row["ask_volume_2"] else 0
        bv3 = int(row["bid_volume_3"]) if row.get("bid_volume_3") and row["bid_volume_3"] else 0
        av3 = int(row["ask_volume_3"]) if row.get("ask_volume_3") and row["ask_volume_3"] else 0
        mid = float(row["mid_price"]) if row.get("mid_price") and row["mid_price"] else None
        pnl = float(row["profit_and_loss"]) if row.get("profit_and_loss") and row["profit_and_loss"] else 0.0
        book_at_tick[(prod, ts)] = {
            "bp1": bp1, "ap1": ap1, "bp2": bp2, "ap2": ap2, "bp3": bp3, "ap3": ap3,
            "bv1": bv1, "av1": av1, "bv2": bv2, "av2": av2, "bv3": bv3, "av3": av3,
            "mid": mid, "pnl": pnl,
        }

# ═══════════════════════════════════════════════════════════
# 1. DETAILED EMERALDS FILL ANALYSIS
# ═══════════════════════════════════════════════════════════
print("="*70)
print("EMERALDS — DETAILED FILL ANALYSIS")
print("="*70)

em_trades = sorted(trades_by_product["EMERALDS"], key=lambda t: t["timestamp"])
position = 0
cumulative_pnl = 0.0

for t in em_trades:
    ts = t["timestamp"]
    price = t["price"]
    qty = t["quantity"]
    is_buy = t["buyer"] == "SUBMISSION"
    
    prev_book = book_at_tick.get(("EMERALDS", ts - 100), {})
    curr_book = book_at_tick.get(("EMERALDS", ts), {})
    
    if is_buy:
        position += qty
        edge = 10000 - price
    else:
        position -= qty
        edge = price - 10000
    
    cumulative_pnl += edge * qty
    
    side = "BUY" if is_buy else "SELL"
    spread = (prev_book.get("ap1", 0) or 0) - (prev_book.get("bp1", 0) or 0)
    
    print(f"  t={ts:6d}: {side:4s} {qty:2d}@{price:.0f} edge={edge:+.0f} "
          f"pos={position:+3d} cum_pnl={cumulative_pnl:.0f} "
          f"prev_book=[{prev_book.get('bp1')}/{prev_book.get('bv1')} | "
          f"{prev_book.get('ap1')}/{prev_book.get('av1')}] spr={spread}")

print(f"\n  EMERALDS Summary:")
print(f"    Total fills: {len(em_trades)}")
print(f"    Cumulative edge-based PnL: {cumulative_pnl:.0f}")
print(f"    Final position: {position}")
print(f"    Reported PnL: {float(product_ticks['EMERALDS'][-1]['profit_and_loss']):.2f}")

# ═══════════════════════════════════════════════════════════
# 2. DETAILED TOMATOES FILL ANALYSIS  
# ═══════════════════════════════════════════════════════════
print("\n" + "="*70)
print("TOMATOES — DETAILED FILL ANALYSIS")
print("="*70)

tom_trades = sorted(trades_by_product["TOMATOES"], key=lambda t: t["timestamp"])
position = 0

for t in tom_trades:
    ts = t["timestamp"]
    price = t["price"]
    qty = t["quantity"]
    is_buy = t["buyer"] == "SUBMISSION"
    
    prev_book = book_at_tick.get(("TOMATOES", ts - 100), {})
    curr_book = book_at_tick.get(("TOMATOES", ts), {})
    
    if is_buy:
        position += qty
    else:
        position -= qty
    
    side = "BUY" if is_buy else "SELL"
    mid = curr_book.get("mid", 0.0)
    prev_mid = prev_book.get("mid", 0.0)
    spread = (prev_book.get("ap1", 0) or 0) - (prev_book.get("bp1", 0) or 0)
    
    if is_buy:
        edge = mid - price if mid else 0
    else:
        edge = price - mid if mid else 0
    
    print(f"  t={ts:6d}: {side:4s} {qty:2d}@{price:.0f} mid={mid:.1f} edge={edge:+.1f} "
          f"pos={position:+3d} "
          f"prev=[{prev_book.get('bp1')}/{prev_book.get('bv1')}|{prev_book.get('ap1')}/{prev_book.get('av1')}] "
          f"spr={spread}")

# ═══════════════════════════════════════════════════════════
# 3. NEGATIVE EDGE FILLS — DEEP DIVE
# ═══════════════════════════════════════════════════════════
print("\n" + "="*70)
print("NEGATIVE EDGE FILLS — WHY?")
print("="*70)

for prod, prod_trades in trades_by_product.items():
    neg_edge_fills = []
    for t in prod_trades:
        ts = t["timestamp"]
        curr_book = book_at_tick.get((prod, ts), {})
        mid = curr_book.get("mid", 0.0)
        
        if t["buyer"] == "SUBMISSION":
            edge = mid - t["price"]
        else:
            edge = t["price"] - mid
        
        if edge < 0:
            prev_book = book_at_tick.get((prod, ts - 100), {})
            neg_edge_fills.append({
                "ts": ts, "price": t["price"], "qty": t["quantity"],
                "side": "BUY" if t["buyer"] == "SUBMISSION" else "SELL",
                "mid": mid, "edge": edge,
                "prev_bp1": prev_book.get("bp1"), "prev_ap1": prev_book.get("ap1"),
                "prev_mid": prev_book.get("mid"),
                "curr_bp1": curr_book.get("bp1"), "curr_ap1": curr_book.get("ap1"),
            })
    
    if neg_edge_fills:
        print(f"\n  {prod}: {len(neg_edge_fills)} negative-edge fills")
        for f in neg_edge_fills:
            print(f"    t={f['ts']}: {f['side']} {f['qty']}@{f['price']:.0f}")
            print(f"      curr_mid={f['mid']:.1f}, edge={f['edge']:.1f}")
            print(f"      prev_book=[{f['prev_bp1']}|{f['prev_ap1']}] prev_mid={f['prev_mid']}")
            print(f"      curr_book=[{f['curr_bp1']}|{f['curr_ap1']}]")
            # Is this a take or make?
            if f["side"] == "SELL" and f["prev_bp1"] and f["price"] >= f["prev_bp1"]:
                print(f"      Classification: TAKE (sold at {f['price']} >= prev_bid {f['prev_bp1']})")
            elif f["side"] == "BUY" and f["prev_ap1"] and f["price"] <= f["prev_ap1"]:
                print(f"      Classification: TAKE (bought at {f['price']} <= prev_ask {f['prev_ap1']})")
            else:
                print(f"      Classification: MAKE (resting order filled)")

# ═══════════════════════════════════════════════════════════
# 4. TOMATOES: TAKE vs MAKE WITH EDGE BREAKDOWN
# ═══════════════════════════════════════════════════════════
print("\n" + "="*70)
print("TOMATOES — TAKE vs MAKE EDGE BREAKDOWN")
print("="*70)

takes_edge = 0.0
takes_weighted = 0.0
makes_edge = 0.0
makes_weighted = 0.0
take_count = 0
make_count = 0

for t in tom_trades:
    ts = t["timestamp"]
    price = t["price"]
    qty = t["quantity"]
    is_buy = t["buyer"] == "SUBMISSION"
    
    prev_book = book_at_tick.get(("TOMATOES", ts - 100), {})
    curr_book = book_at_tick.get(("TOMATOES", ts), {})
    mid = curr_book.get("mid", 0.0)
    
    if is_buy:
        edge = mid - price
        is_take = prev_book.get("ap1") and price <= prev_book["ap1"]
    else:
        edge = price - mid
        is_take = prev_book.get("bp1") and price >= prev_book["bp1"]
    
    if is_take:
        takes_edge += edge
        takes_weighted += edge * qty
        take_count += 1
    else:
        makes_edge += edge
        makes_weighted += edge * qty
        make_count += 1

print(f"  TAKES: {take_count} fills, total edge={takes_edge:.1f}, weighted edge={takes_weighted:.1f}")
print(f"  MAKES: {make_count} fills, total edge={makes_edge:.1f}, weighted edge={makes_weighted:.1f}")
if take_count > 0:
    print(f"  Avg take edge: {takes_edge/take_count:.2f}")
if make_count > 0:
    print(f"  Avg make edge: {makes_edge/make_count:.2f}")

# ═══════════════════════════════════════════════════════════
# 5. WHAT SPREADS DO FILLS HAPPEN ON?
# ═══════════════════════════════════════════════════════════
print("\n" + "="*70)
print("TOMATOES — FILLS BY SPREAD REGIME")
print("="*70)

spread_fills = defaultdict(lambda: {"count": 0, "edge_sum": 0.0, "qty_sum": 0})
for t in tom_trades:
    ts = t["timestamp"]
    prev_book = book_at_tick.get(("TOMATOES", ts - 100), {})
    curr_book = book_at_tick.get(("TOMATOES", ts), {})
    spread = (prev_book.get("ap1", 0) or 0) - (prev_book.get("bp1", 0) or 0)
    mid = curr_book.get("mid", 0.0)
    
    if t["buyer"] == "SUBMISSION":
        edge = mid - t["price"]
    else:
        edge = t["price"] - mid
    
    spread_fills[spread]["count"] += 1
    spread_fills[spread]["edge_sum"] += edge * t["quantity"]
    spread_fills[spread]["qty_sum"] += t["quantity"]

for s in sorted(spread_fills.keys()):
    sf = spread_fills[s]
    avg_edge = sf["edge_sum"] / sf["qty_sum"] if sf["qty_sum"] > 0 else 0
    print(f"  Spread {s:3d}: {sf['count']:3d} fills, {sf['qty_sum']:4d} units, "
          f"total_edge={sf['edge_sum']:+8.1f}, avg_edge/unit={avg_edge:+.2f}")

# ═══════════════════════════════════════════════════════════
# 6. EMERALDS: NON-STANDARD BOOK TICKS
# ═══════════════════════════════════════════════════════════
print("\n" + "="*70)
print("EMERALDS — NON-STANDARD BOOK TICKS (spread != 16)")
print("="*70)

em_nonstandard = []
for row in product_ticks["EMERALDS"]:
    bp1 = int(row["bid_price_1"]) if row.get("bid_price_1") and row["bid_price_1"] else 0
    ap1 = int(row["ask_price_1"]) if row.get("ask_price_1") and row["ask_price_1"] else 0
    spread = ap1 - bp1
    if spread != 16:
        ts = int(row["timestamp"])
        em_nonstandard.append((ts, bp1, ap1, spread))

print(f"  Non-standard ticks: {len(em_nonstandard)}/{len(product_ticks['EMERALDS'])}")
for ts, bp, ap, spr in em_nonstandard[:30]:
    # Check if there was a fill near this tick
    nearby_fills = [t for t in em_trades if abs(t["timestamp"] - ts) <= 200]
    fill_str = ""
    if nearby_fills:
        fill_str = f" << NEARBY FILLS: {[(t['price'], t['quantity'], 'B' if t['buyer']=='SUBMISSION' else 'S') for t in nearby_fills]}"
    print(f"  t={ts}: bid={bp} ask={ap} spread={spr}{fill_str}")

# ═══════════════════════════════════════════════════════════
# 7. TOMATOES: NARROW SPREAD TICKS (potential lost fills)
# ═══════════════════════════════════════════════════════════
print("\n" + "="*70)
print("TOMATOES — NARROW SPREAD TICKS (spread <= 10)")
print("="*70)

narrow_ticks = 0
narrow_with_fills = 0
for row in product_ticks["TOMATOES"]:
    bp1 = int(row["bid_price_1"]) if row.get("bid_price_1") and row["bid_price_1"] else 0
    ap1 = int(row["ask_price_1"]) if row.get("ask_price_1") and row["ask_price_1"] else 0
    spread = ap1 - bp1
    if spread <= 10:
        narrow_ticks += 1
        ts = int(row["timestamp"])
        fills_at = [t for t in tom_trades if t["timestamp"] == ts]
        if fills_at:
            narrow_with_fills += 1

print(f"  Narrow spread ticks: {narrow_ticks}/{len(product_ticks['TOMATOES'])}")
print(f"  Narrow spread ticks with fills: {narrow_with_fills}")

# ═══════════════════════════════════════════════════════════
# 8. EMERALDS: FILL PRICE vs SKEW POSITION
# ═══════════════════════════════════════════════════════════
print("\n" + "="*70)
print("EMERALDS — FILL PRICE & POSITION AT FILL TIME")
print("="*70)

print("  (showing how position skew affects bid/ask placement)")
position = 0
for t in em_trades:
    ts = t["timestamp"]
    price = t["price"]
    qty = t["quantity"]
    is_buy = t["buyer"] == "SUBMISSION"
    
    pos_ratio = position / 80
    
    # Reconstruct expected bid/ask from strategy
    bid_price = 10000 - 7
    ask_price = 10000 + 7
    
    SKEW = 0.3
    HEAVY = 0.6
    if pos_ratio > HEAVY:
        bid_price -= 1; ask_price -= 1
    elif pos_ratio > SKEW:
        ask_price -= 1
    elif pos_ratio < -HEAVY:
        bid_price += 1; ask_price += 1
    elif pos_ratio < -SKEW:
        bid_price += 1
        
    side = "BUY" if is_buy else "SELL"
    
    if is_buy:
        position += qty
    else:
        position -= qty
    
    match = ""
    if is_buy and price == bid_price:
        match = " (@ our bid - MAKE)"
    elif not is_buy and price == ask_price:
        match = " (@ our ask - MAKE)"
    elif is_buy and price == 9993:
        match = " (@ 9993 - TAKE at bot bid)"
    elif not is_buy and price == 10007:
        match = " (@ 10007 - TAKE at bot ask)" 
        
    print(f"  t={ts:6d}: {side:4s} {qty:2d}@{price:.0f} pos_before={position - (qty if is_buy else -qty):+3d} "
          f"pos_after={position:+3d} ratio={pos_ratio:+.2f} "
          f"expected_bid={bid_price} expected_ask={ask_price}{match}")

# ═══════════════════════════════════════════════════════════
# 9. TOMATOES: PNL DECOMPOSITION
# ═══════════════════════════════════════════════════════════
print("\n" + "="*70)
print("TOMATOES — PNL DECOMPOSITION")
print("="*70)

# Track realized PnL from round-trip trades
position = 0
cost_basis = 0.0
realized_pnl = 0.0

for t in sorted(tom_trades, key=lambda x: x["timestamp"]):
    is_buy = t["buyer"] == "SUBMISSION"
    price = t["price"]
    qty = t["quantity"]
    
    if is_buy:
        cost_basis += price * qty
        position += qty
    else:
        cost_basis -= price * qty
        position -= qty

# Unrealized PnL = position * last_mid - remaining cost basis
last_mid = float(product_ticks["TOMATOES"][-1]["mid_price"])
total_buy_value = sum(t["price"] * t["quantity"] for t in tom_trades if t["buyer"] == "SUBMISSION")
total_sell_value = sum(t["price"] * t["quantity"] for t in tom_trades if t["seller"] == "SUBMISSION")
trading_pnl = total_sell_value - total_buy_value
inventory_value = position * last_mid  # mark-to-market of remaining position

print(f"  Total buy value: {total_buy_value:.2f}")
print(f"  Total sell value: {total_sell_value:.2f}")
print(f"  Trading PnL (sells - buys): {trading_pnl:.2f}")
print(f"  Final position: {position}")
print(f"  Last mid: {last_mid}")
print(f"  Mark-to-market of position: {inventory_value:.2f}")
print(f"  Estimated total PnL: {trading_pnl + inventory_value:.2f}")
print(f"  Reported PnL: {float(product_ticks['TOMATOES'][-1]['profit_and_loss']):.2f}")

# ═══════════════════════════════════════════════════════════
# 10. TOMATOES: HOW MUCH PNL FROM TAKES vs POSITION?
# ═══════════════════════════════════════════════════════════
print("\n" + "="*70)
print("TOMATOES — TAKE FILL DETAILS")
print("="*70)

position = 0
for t in tom_trades:
    ts = t["timestamp"]
    price = t["price"]
    qty = t["quantity"]
    is_buy = t["buyer"] == "SUBMISSION"
    
    prev_book = book_at_tick.get(("TOMATOES", ts - 100), {})
    curr_book = book_at_tick.get(("TOMATOES", ts), {})
    
    if is_buy:
        position += qty
        is_take = prev_book.get("ap1") and price <= prev_book["ap1"]
        which_level = ""
        if is_take and price == prev_book.get("ap1"):
            which_level = "L1-ask"
        elif is_take and price == prev_book.get("ap2"):
            which_level = "L2-ask"
        elif is_take and price == prev_book.get("ap3"):
            which_level = "L3-ask"
    else:
        position -= qty
        is_take = prev_book.get("bp1") and price >= prev_book["bp1"]
        which_level = ""
        if is_take and price == prev_book.get("bp1"):
            which_level = "L1-bid"
        elif is_take and price == prev_book.get("bp2"):
            which_level = "L2-bid"
        elif is_take and price == prev_book.get("bp3"):
            which_level = "L3-bid"
    
    side = "BUY" if is_buy else "SELL"
    type_str = "TAKE" if is_take else "MAKE"
    
    fair_str = ""
    # What was our fair value estimate? EMA + imbalance - pos*0.05
    # We can't reconstruct EMA without full state, but mid_price is a proxy
    mid = curr_book.get("mid", 0)
    if mid:
        if is_buy:
            vs_mid = mid - price
        else:
            vs_mid = price - mid
        fair_str = f" vs_mid={vs_mid:+.1f}"
    
    print(f"  t={ts:6d}: {type_str:4s} {side:4s} {qty:2d}@{price:.0f} {which_level:8s} "
          f"pos={position:+3d} prev=[{prev_book.get('bp1')}|{prev_book.get('ap1')}]{fair_str}")

print("\n\nDone.")
