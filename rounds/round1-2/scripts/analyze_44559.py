"""
Comprehensive analysis of simulation 44559.
"""

import json
import csv
import io
from collections import defaultdict, Counter

LOG_PATH = "logs/44559/44559.log"

with open(LOG_PATH, "r") as f:
    data = json.load(f)

# ═══════════════════════════════════════════════════════════
# 1. PARSE ACTIVITIES LOG (order book + PnL per tick)
# ═══════════════════════════════════════════════════════════
activities_csv = data["activitiesLog"]
reader = csv.DictReader(io.StringIO(activities_csv), delimiter=";")
activities = list(reader)

print(f"Total activity rows: {len(activities)}")
print(f"Columns: {list(activities[0].keys()) if activities else 'N/A'}")

# Organize by product
product_ticks = defaultdict(list)
for row in activities:
    product_ticks[row["product"]].append(row)

print(f"\nProducts: {list(product_ticks.keys())}")
for prod, rows in product_ticks.items():
    print(f"  {prod}: {len(rows)} rows")

# ═══════════════════════════════════════════════════════════
# 2. FINAL PNL
# ═══════════════════════════════════════════════════════════
print("\n" + "="*60)
print("FINAL PNL")
print("="*60)

for prod, rows in product_ticks.items():
    last = rows[-1]
    pnl = float(last["profit_and_loss"])
    print(f"  {prod}: {pnl:.2f}")

total_pnl = sum(float(rows[-1]["profit_and_loss"]) for rows in product_ticks.values())
print(f"  TOTAL: {total_pnl:.2f}")

# ═══════════════════════════════════════════════════════════
# 3. TRADE HISTORY ANALYSIS
# ═══════════════════════════════════════════════════════════
print("\n" + "="*60)
print("TRADE HISTORY")
print("="*60)

trades = data["tradeHistory"]
print(f"Total trades: {len(trades)}")

# Separate by product
trades_by_product = defaultdict(list)
for t in trades:
    trades_by_product[t["symbol"]].append(t)

for prod, prod_trades in trades_by_product.items():
    buys = [t for t in prod_trades if t["buyer"] == "SUBMISSION"]
    sells = [t for t in prod_trades if t["seller"] == "SUBMISSION"]
    
    buy_qty = sum(t["quantity"] for t in buys)
    sell_qty = sum(t["quantity"] for t in sells)
    buy_value = sum(t["price"] * t["quantity"] for t in buys)
    sell_value = sum(t["price"] * t["quantity"] for t in sells)
    
    print(f"\n  {prod}:")
    print(f"    Total fills: {len(prod_trades)} ({len(buys)} buys, {len(sells)} sells)")
    print(f"    Buy qty: {buy_qty}, Sell qty: {sell_qty}, Net pos: {buy_qty - sell_qty}")
    print(f"    Buy value: {buy_value:.2f}, Sell value: {sell_value:.2f}")
    if buy_qty > 0:
        print(f"    Avg buy price: {buy_value/buy_qty:.2f}")
    if sell_qty > 0:
        print(f"    Avg sell price: {sell_value/sell_qty:.2f}")
    
    # Price distribution
    buy_prices = Counter()
    sell_prices = Counter()
    for t in buys:
        buy_prices[t["price"]] += t["quantity"]
    for t in sells:
        sell_prices[t["price"]] += t["quantity"]
    
    if buy_prices:
        print(f"    Buy price distribution: {dict(sorted(buy_prices.items()))}")
    if sell_prices:
        print(f"    Sell price distribution: {dict(sorted(sell_prices.items()))}")

# ═══════════════════════════════════════════════════════════
# 4. ORDER EXECUTION ANALYSIS
# ═══════════════════════════════════════════════════════════
print("\n" + "="*60)
print("ORDER EXECUTION ANALYSIS")
print("="*60)

# For each trade, determine if it was a TAKE or MAKE
# If our order crossed a resting order -> TAKE
# If a bot order crossed our resting order -> MAKE
# Heuristic: if we buy at ask_price_1 or sell at bid_price_1 from previous tick -> TAKE

# Build a mapping of timestamp -> order book state
book_at_tick = {}
for prod, rows in product_ticks.items():
    for row in rows:
        ts = int(row["timestamp"])
        bp1 = int(row["bid_price_1"]) if row.get("bid_price_1") else None
        ap1 = int(row["ask_price_1"]) if row.get("ask_price_1") else None
        bp2 = int(row["bid_price_2"]) if row.get("bid_price_2") else None
        ap2 = int(row["ask_price_2"]) if row.get("ask_price_2") else None
        mid = float(row["mid_price"]) if row.get("mid_price") else None
        book_at_tick[(prod, ts)] = {
            "bp1": bp1, "ap1": ap1, "bp2": bp2, "ap2": ap2, "mid": mid,
            "bv1": int(row["bid_volume_1"]) if row.get("bid_volume_1") else 0,
            "av1": int(row["ask_volume_1"]) if row.get("ask_volume_1") else 0,
        }

# Classify trades as TAKE vs MAKE
for prod, prod_trades in trades_by_product.items():
    takes = []
    makes = []
    unknown = []
    
    for t in prod_trades:
        ts = t["timestamp"]
        price = t["price"]
        is_buy = t["buyer"] == "SUBMISSION"
        
        # Get book at this tick (the state AFTER the trade)
        # The book at ts shows the resulting state
        # We need the book just BEFORE the trade to classify
        # Look at previous tick's book
        prev_ts = ts - 100
        book = book_at_tick.get((prod, prev_ts))
        
        if book is None:
            unknown.append(t)
            continue
        
        if is_buy:
            # If we bought at or below the ask -> TAKE
            if book["ap1"] and price <= book["ap1"]:
                takes.append(t)
            else:
                makes.append(t)
        else:
            # If we sold at or above the bid -> TAKE
            if book["bp1"] and price >= book["bp1"]:
                takes.append(t)
            else:
                makes.append(t)
    
    take_qty = sum(t["quantity"] for t in takes)
    make_qty = sum(t["quantity"] for t in makes)
    
    print(f"\n  {prod}:")
    print(f"    TAKES: {len(takes)} fills, {take_qty} units")
    print(f"    MAKES: {len(makes)} fills, {make_qty} units")
    print(f"    UNKNOWN: {len(unknown)} fills")
    
    if takes:
        print(f"    Take prices: {sorted(set(t['price'] for t in takes))}")
    if makes:
        print(f"    Make prices: {sorted(set(t['price'] for t in makes))}")

# ═══════════════════════════════════════════════════════════
# 5. SPREAD ANALYSIS
# ═══════════════════════════════════════════════════════════
print("\n" + "="*60)
print("SPREAD ANALYSIS")
print("="*60)

for prod, rows in product_ticks.items():
    spreads = []
    for row in rows:
        bp1 = int(row["bid_price_1"]) if row.get("bid_price_1") else None
        ap1 = int(row["ask_price_1"]) if row.get("ask_price_1") else None
        if bp1 and ap1:
            spreads.append(ap1 - bp1)
    
    if spreads:
        spread_dist = Counter(spreads)
        total = len(spreads)
        print(f"\n  {prod} (total ticks with spread: {total}):")
        for s in sorted(spread_dist.keys()):
            pct = spread_dist[s] / total * 100
            print(f"    Spread {s:3d}: {spread_dist[s]:5d} ticks ({pct:5.1f}%)")

# ═══════════════════════════════════════════════════════════
# 6. POSITION TRACKING (inferred from trades)
# ═══════════════════════════════════════════════════════════
print("\n" + "="*60)
print("POSITION TRACKING")
print("="*60)

for prod, prod_trades in trades_by_product.items():
    position = 0
    max_pos = 0
    min_pos = 0
    positions_over_time = []
    
    for t in sorted(prod_trades, key=lambda x: x["timestamp"]):
        if t["buyer"] == "SUBMISSION":
            position += t["quantity"]
        else:
            position -= t["quantity"]
        max_pos = max(max_pos, position)
        min_pos = min(min_pos, position)
        positions_over_time.append((t["timestamp"], position))
    
    print(f"\n  {prod}:")
    print(f"    Final position: {position}")
    print(f"    Max position: {max_pos}")
    print(f"    Min position: {min_pos}")
    print(f"    Position range: {max_pos - min_pos}")
    if positions_over_time:
        print(f"    First 10 position changes: {positions_over_time[:10]}")
        print(f"    Last 10 position changes: {positions_over_time[-10:]}")

# ═══════════════════════════════════════════════════════════
# 7. PNL OVER TIME
# ═══════════════════════════════════════════════════════════
print("\n" + "="*60)
print("PNL OVER TIME (quartiles)")
print("="*60)

for prod, rows in product_ticks.items():
    total = len(rows)
    q1 = total // 4
    q2 = total // 2
    q3 = (3 * total) // 4
    
    pnl_q1 = float(rows[q1]["profit_and_loss"])
    pnl_q2 = float(rows[q2]["profit_and_loss"])
    pnl_q3 = float(rows[q3]["profit_and_loss"])
    pnl_end = float(rows[-1]["profit_and_loss"])
    
    print(f"\n  {prod}:")
    print(f"    Q1 (t={rows[q1]['timestamp']}): {pnl_q1:.2f}")
    print(f"    Q2 (t={rows[q2]['timestamp']}): {pnl_q2:.2f}")
    print(f"    Q3 (t={rows[q3]['timestamp']}): {pnl_q3:.2f}")
    print(f"    End (t={rows[-1]['timestamp']}): {pnl_end:.2f}")

# ═══════════════════════════════════════════════════════════
# 8. FILL TIMING ANALYSIS
# ═══════════════════════════════════════════════════════════
print("\n" + "="*60)
print("FILL TIMING ANALYSIS")
print("="*60)

for prod, prod_trades in trades_by_product.items():
    timestamps = sorted(t["timestamp"] for t in prod_trades)
    if len(timestamps) < 2:
        continue
    
    gaps = [timestamps[i+1] - timestamps[i] for i in range(len(timestamps)-1)]
    avg_gap = sum(gaps) / len(gaps)
    max_gap = max(gaps)
    min_gap = min(gaps)
    
    # Quarter distribution
    max_ts = max(timestamps)
    q_boundary = max_ts / 4
    q_counts = [0, 0, 0, 0]
    for ts in timestamps:
        q = min(3, int(ts / q_boundary))
        q_counts[q] += 1
    
    print(f"\n  {prod}:")
    print(f"    Fill count: {len(timestamps)}")
    print(f"    First fill: t={timestamps[0]}, Last fill: t={timestamps[-1]}")
    print(f"    Avg gap: {avg_gap:.0f}, Min gap: {min_gap}, Max gap: {max_gap}")
    print(f"    Fills by quarter: Q1={q_counts[0]}, Q2={q_counts[1]}, Q3={q_counts[2]}, Q4={q_counts[3]}")

# ═══════════════════════════════════════════════════════════
# 9. EDGE PER FILL ANALYSIS
# ═══════════════════════════════════════════════════════════
print("\n" + "="*60)
print("EDGE PER FILL (vs mid price)")
print("="*60)

for prod, prod_trades in trades_by_product.items():
    edges = []
    for t in prod_trades:
        ts = t["timestamp"]
        book = book_at_tick.get((prod, ts))
        if book and book["mid"]:
            mid = book["mid"]
            if t["buyer"] == "SUBMISSION":
                # We bought — edge is mid - price (positive = good)
                edge = mid - t["price"]
            else:
                # We sold — edge is price - mid (positive = good)
                edge = t["price"] - mid
            edges.append((t["timestamp"], t["price"], mid, edge, t["quantity"],
                         "BUY" if t["buyer"] == "SUBMISSION" else "SELL"))
    
    if not edges:
        continue
    
    total_edge = sum(e[3] * e[4] for e in edges)
    avg_edge = sum(e[3] for e in edges) / len(edges)
    positive_edge = sum(1 for e in edges if e[3] > 0)
    negative_edge = sum(1 for e in edges if e[3] < 0)
    zero_edge = sum(1 for e in edges if e[3] == 0)
    
    print(f"\n  {prod}:")
    print(f"    Total weighted edge: {total_edge:.2f}")
    print(f"    Avg edge per fill: {avg_edge:.2f}")
    print(f"    Positive edge fills: {positive_edge}")
    print(f"    Negative edge fills: {negative_edge}")
    print(f"    Zero edge fills: {zero_edge}")
    
    # Show negative edge fills (these are bad)
    neg = [e for e in edges if e[3] < 0]
    if neg:
        print(f"    Negative edge fills detail:")
        for e in neg[:20]:
            print(f"      t={e[0]}: {e[5]} @ {e[1]}, mid={e[2]}, edge={e[3]:.1f}, qty={e[4]}")

# ═══════════════════════════════════════════════════════════
# 10. LOGGER OUTPUT ANALYSIS
# ═══════════════════════════════════════════════════════════
print("\n" + "="*60)
print("LOGGER OUTPUT ANALYSIS")
print("="*60)

logs = data["logs"]
print(f"Total log entries: {len(logs)}")

# Parse compressed logger output
# Each log is a string that JSON-decodes to [state, orders, conversions, traderData, logText]
error_count = 0
parsed_logs = []
for i, log_entry in enumerate(logs):
    try:
        parsed = json.loads(log_entry)
        parsed_logs.append(parsed)
        if len(parsed) >= 5 and "ERROR" in str(parsed[4]):
            error_count += 1
            print(f"  ERROR at tick {i}: {parsed[4][:200]}")
    except:
        error_count += 1
        
print(f"Parsed logs: {len(parsed_logs)}")
print(f"Error entries: {error_count}")

# Extract order submission patterns from logs
order_counts = defaultdict(lambda: {"buy": 0, "sell": 0, "total_buy_qty": 0, "total_sell_qty": 0})
for pl in parsed_logs:
    if len(pl) < 2:
        continue
    orders_dict = pl[1]
    for sym, order_list in orders_dict.items():
        for o in order_list:
            # [symbol, price, quantity]
            qty = o[2]
            if qty > 0:
                order_counts[sym]["buy"] += 1
                order_counts[sym]["total_buy_qty"] += qty
            else:
                order_counts[sym]["sell"] += 1
                order_counts[sym]["total_sell_qty"] += abs(qty)

print(f"\nOrder submission summary:")
for sym, counts in order_counts.items():
    print(f"  {sym}:")
    print(f"    Buy orders: {counts['buy']}, total qty: {counts['total_buy_qty']}")
    print(f"    Sell orders: {counts['sell']}, total qty: {counts['total_sell_qty']}")
    fill_count = len(trades_by_product.get(sym, []))
    total_orders = counts['buy'] + counts['sell']
    if total_orders > 0:
        fill_rate = fill_count / total_orders * 100
        print(f"    Fill rate: {fill_count}/{total_orders} = {fill_rate:.1f}%")

# ═══════════════════════════════════════════════════════════
# 11. DETAILED ORDER vs FILL MATCHING
# ═══════════════════════════════════════════════════════════
print("\n" + "="*60)
print("ORDER vs FILL MATCHING (sample)")
print("="*60)

# For ticks with fills, show what orders we submitted and what got filled
fill_ticks_by_prod = defaultdict(set)
for t in trades:
    fill_ticks_by_prod[t["symbol"]].add(t["timestamp"])

for prod in trades_by_product.keys():
    fill_ticks = sorted(fill_ticks_by_prod[prod])[:10]  # first 10 fill ticks
    print(f"\n  {prod} — first 10 fill ticks:")
    
    for ft in fill_ticks:
        # Find orders submitted at this tick
        tick_idx = ft // 100  # tick index
        if tick_idx < len(parsed_logs):
            pl = parsed_logs[tick_idx]
            if len(pl) >= 2:
                submitted_orders = pl[1].get(prod, [])
                fills_at_tick = [t for t in trades_by_product[prod] if t["timestamp"] == ft]
                book = book_at_tick.get((prod, ft), {})
                prev_book = book_at_tick.get((prod, ft - 100), {})
                
                print(f"    t={ft}:")
                print(f"      Book: bid={prev_book.get('bp1')}/{prev_book.get('bv1')} ask={prev_book.get('ap1')}/{prev_book.get('av1')}")
                print(f"      Orders: {[(o[1], o[2]) for o in submitted_orders]}")
                print(f"      Fills: {[(f['price'], f['quantity'], 'BUY' if f['buyer']=='SUBMISSION' else 'SELL') for f in fills_at_tick]}")

# ═══════════════════════════════════════════════════════════
# 12. MID PRICE STATISTICS
# ═══════════════════════════════════════════════════════════
print("\n" + "="*60)
print("MID PRICE STATISTICS")
print("="*60)

for prod, rows in product_ticks.items():
    mids = [float(r["mid_price"]) for r in rows if r.get("mid_price")]
    if mids:
        print(f"\n  {prod}:")
        print(f"    Min mid: {min(mids):.1f}")
        print(f"    Max mid: {max(mids):.1f}")
        print(f"    Mean mid: {sum(mids)/len(mids):.1f}")
        print(f"    Start mid: {mids[0]:.1f}")
        print(f"    End mid: {mids[-1]:.1f}")
        print(f"    Range: {max(mids) - min(mids):.1f}")
        
        # Price movement (drift)
        changes = [mids[i+1] - mids[i] for i in range(len(mids)-1)]
        up = sum(1 for c in changes if c > 0)
        down = sum(1 for c in changes if c < 0)
        flat = sum(1 for c in changes if c == 0)
        print(f"    Tick changes: {up} up, {down} down, {flat} flat")
        if changes:
            max_move = max(changes, key=abs)
            print(f"    Max single-tick move: {max_move:.1f}")

# ═══════════════════════════════════════════════════════════
# 13. COMPARISON WITH PREVIOUS SIMS
# ═══════════════════════════════════════════════════════════
print("\n" + "="*60)
print("COMPARISON WITH PREVIOUS SIMS")
print("="*60)

prev_sims = {
    42126: {"total": 920.58, "em": None, "tom": None},
    42183: {"total": 898.58, "em": 121.0, "tom": 777.58},
    42260: {"total": 672.58, "em": 121.0, "tom": 551.58},
    42349: {"total": 1225.57, "em": 121.0, "tom": 1104.57},
    42400: {"total": 2132.57, "em": 1028.0, "tom": 1104.57},
    42447: {"total": 1901.86, "em": None, "tom": None},
}

em_pnl = float(product_ticks["EMERALDS"][-1]["profit_and_loss"])
tom_pnl = float(product_ticks["TOMATOES"][-1]["profit_and_loss"])

print(f"\n  44559: EM={em_pnl:.2f} TOM={tom_pnl:.2f} TOTAL={total_pnl:.2f}")
print(f"\n  Previous results:")
for sim_id, vals in sorted(prev_sims.items()):
    em_str = f"EM={vals['em']}" if vals['em'] is not None else "EM=?"
    tom_str = f"TOM={vals['tom']}" if vals['tom'] is not None else "TOM=?"
    print(f"    {sim_id}: {em_str} {tom_str} TOTAL={vals['total']}")

best_prev = max(prev_sims.values(), key=lambda x: x["total"])
print(f"\n  Best previous: {max(prev_sims.items(), key=lambda x: x[1]['total'])[0]} @ {best_prev['total']}")
print(f"  Change vs best: {total_pnl - best_prev['total']:.2f} ({(total_pnl - best_prev['total'])/best_prev['total']*100:.1f}%)")

# ═══════════════════════════════════════════════════════════
# 14. BOOK DEPTH ANALYSIS AT FILL TICKS
# ═══════════════════════════════════════════════════════════
print("\n" + "="*60)
print("BOOK STATE AT FILL TICKS")
print("="*60)

for prod, prod_trades in trades_by_product.items():
    fill_books = []
    for t in prod_trades:
        ts = t["timestamp"]
        prev_book = book_at_tick.get((prod, ts - 100))
        curr_book = book_at_tick.get((prod, ts))
        if prev_book:
            fill_books.append({
                "ts": ts,
                "price": t["price"],
                "qty": t["quantity"],
                "side": "BUY" if t["buyer"] == "SUBMISSION" else "SELL",
                "prev_bp1": prev_book.get("bp1"),
                "prev_ap1": prev_book.get("ap1"),
                "prev_spread": (prev_book.get("ap1", 0) or 0) - (prev_book.get("bp1", 0) or 0),
                "curr_bp1": curr_book.get("bp1") if curr_book else None,
                "curr_ap1": curr_book.get("ap1") if curr_book else None,
            })
    
    if not fill_books:
        continue
    
    print(f"\n  {prod}:")
    # Spread at fill ticks
    fill_spreads = [fb["prev_spread"] for fb in fill_books if fb["prev_spread"] > 0]
    if fill_spreads:
        spread_dist = Counter(fill_spreads)
        print(f"    Spread distribution at fill ticks:")
        for s in sorted(spread_dist.keys()):
            print(f"      Spread {s}: {spread_dist[s]} fills")

# ═══════════════════════════════════════════════════════════
# 15. MARKET TRADES (BOT-TO-BOT)
# ═══════════════════════════════════════════════════════════
print("\n" + "="*60)
print("MARKET TRADES (bot-to-bot, from logger state)")
print("="*60)

# Extract market trades from the compressed state in logs
market_trades_count = defaultdict(int)
market_trade_prices = defaultdict(list)

for pl in parsed_logs:
    if len(pl) < 1:
        continue
    state_data = pl[0]
    if len(state_data) < 6:
        continue
    # state = [timestamp, traderData, listings, orderDepths, ownTrades, marketTrades, position, obs]
    market_trades_dict = state_data[5]
    for sym, mt_list in market_trades_dict.items():
        market_trades_count[sym] += len(mt_list)
        for mt in mt_list:
            # [symbol, price, quantity, buyer, seller, timestamp]
            market_trade_prices[sym].append(mt[1])

for sym in market_trades_count:
    prices = market_trade_prices[sym]
    print(f"\n  {sym}:")
    print(f"    Total bot-to-bot trades: {market_trades_count[sym]}")
    if prices:
        print(f"    Price range: {min(prices)} - {max(prices)}")
        price_dist = Counter(prices)
        print(f"    Top 10 prices: {dict(sorted(price_dist.items(), key=lambda x: -x[1])[:10])}")

# ═══════════════════════════════════════════════════════════
# 16. OWN TRADES FROM LOGGER (cross-check)
# ═══════════════════════════════════════════════════════════
print("\n" + "="*60)
print("OWN TRADES FROM LOGGER (cross-check)")
print("="*60)

own_trades_count = defaultdict(int)
for pl in parsed_logs:
    if len(pl) < 1:
        continue
    state_data = pl[0]
    if len(state_data) < 5:
        continue
    own_trades_dict = state_data[4]
    for sym, ot_list in own_trades_dict.items():
        own_trades_count[sym] += len(ot_list)

for sym in own_trades_count:
    print(f"  {sym}: {own_trades_count[sym]} own trades in logger")

# ═══════════════════════════════════════════════════════════
# 17. POSITION FROM LOGGER STATE
# ═══════════════════════════════════════════════════════════
print("\n" + "="*60)
print("POSITION FROM LOGGER STATE (sampled)")
print("="*60)

positions_over_time = defaultdict(list)
for pl in parsed_logs:
    if len(pl) < 1:
        continue
    state_data = pl[0]
    if len(state_data) < 7:
        continue
    ts = state_data[0]
    pos_dict = state_data[6]
    for sym, pos in pos_dict.items():
        positions_over_time[sym].append((ts, pos))

for sym in positions_over_time:
    pts = positions_over_time[sym]
    if not pts:
        continue
    positions = [p[1] for p in pts]
    non_zero = [p for p in positions if p != 0]
    
    print(f"\n  {sym}:")
    print(f"    Ticks with position != 0: {len(non_zero)}/{len(positions)}")
    if positions:
        print(f"    Max: {max(positions)}, Min: {min(positions)}")
        print(f"    Avg: {sum(positions)/len(positions):.1f}")
        # Position at quartiles
        n = len(positions)
        print(f"    Q1: {positions[n//4]}, Q2: {positions[n//2]}, Q3: {positions[3*n//4]}, End: {positions[-1]}")
    
    # Time spent at each position level
    pos_time = Counter(positions)
    # Group by ranges
    at_limit = sum(v for k, v in pos_time.items() if abs(k) >= 75)
    at_heavy = sum(v for k, v in pos_time.items() if 40 <= abs(k) < 75)
    at_moderate = sum(v for k, v in pos_time.items() if 10 <= abs(k) < 40)
    at_low = sum(v for k, v in pos_time.items() if abs(k) < 10)
    
    print(f"    Position magnitude: |pos|<10: {at_low}, 10-39: {at_moderate}, 40-74: {at_heavy}, ≥75: {at_limit}")

print("\n\nDone.")
