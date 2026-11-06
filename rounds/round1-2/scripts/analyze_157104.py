"""Comprehensive analysis of 157104 platform submission."""
import json
import csv
import io
import sys
from collections import defaultdict

with open('logs/157104/157104.json', 'r') as f:
    data = json.load(f)

print("=" * 60)
print("157104 SUBMISSION ANALYSIS")
print("=" * 60)

print(f"\nTotal Profit: {data['profit']}")
print(f"Round: {data['round']}")
print(f"Status: {data['status']}")

print("\n--- POSITIONS ---")
for p in data['positions']:
    print(p)

# Parse activities log
reader = csv.DictReader(io.StringIO(data['activitiesLog']), delimiter=';')
records = list(reader)
print(f"\nTotal activity records: {len(records)}")

products = sorted(set(r['product'] for r in records))
days = sorted(set(r['day'] for r in records))
print(f"Products: {products}")
print(f"Days: {days}")

# PnL by product at end of each day
print("\n--- PNL BY PRODUCT ---")
for prod in products:
    prod_records = [r for r in records if r['product'] == prod]
    last = prod_records[-1]
    print(f"  {prod}: final PnL = {last['profit_and_loss']}, final mid = {last['mid_price']}")

# Spread analysis
print("\n--- SPREAD ANALYSIS ---")
for prod in products:
    prod_records = [r for r in records if r['product'] == prod]
    spreads = []
    for r in prod_records:
        if r['bid_price_1'] and r['ask_price_1']:
            try:
                spread = float(r['ask_price_1']) - float(r['bid_price_1'])
                spreads.append(spread)
            except:
                pass
    if spreads:
        print(f"  {prod}:")
        print(f"    Spread - mean: {sum(spreads)/len(spreads):.1f}, min: {min(spreads)}, max: {max(spreads)}")
        print(f"    Spread distribution:")
        from collections import Counter
        spread_counts = Counter(spreads)
        for s in sorted(spread_counts.keys()):
            pct = spread_counts[s] / len(spreads) * 100
            if pct >= 1:
                print(f"      {s:.0f}: {spread_counts[s]} ({pct:.1f}%)")
    print(f"    Total ticks: {len(prod_records)}, with book: {len(spreads)}")

# Mid price analysis for IPR (drift)
print("\n--- MID PRICE ANALYSIS (IPR) ---")
ipr_records = [r for r in records if r['product'] == 'INTARIAN_PEPPER_ROOT']
if ipr_records:
    mids = []
    for r in ipr_records:
        if r['mid_price']:
            try:
                mids.append(float(r['mid_price']))
            except:
                pass
    if mids:
        print(f"  First mid: {mids[0]}, Last mid: {mids[-1]}")
        print(f"  Drift: {mids[-1] - mids[0]:.1f}")
        print(f"  Min: {min(mids):.1f}, Max: {max(mids):.1f}")

# Mid price analysis for OSM
print("\n--- MID PRICE ANALYSIS (OSM) ---")
osm_records = [r for r in records if r['product'] == 'ASH_COATED_OSMIUM']
if osm_records:
    mids = []
    for r in osm_records:
        if r['mid_price']:
            try:
                mids.append(float(r['mid_price']))
            except:
                pass
    if mids:
        print(f"  First mid: {mids[0]}, Last mid: {mids[-1]}")
        print(f"  Range: {min(mids):.1f} - {max(mids):.1f}")

# PnL curve from graphLog
graph_lines = data['graphLog'].strip().split('\n')
print(f"\n--- PNL CURVE ({len(graph_lines)-1} points) ---")
graph_data = []
for line in graph_lines[1:]:
    parts = line.split(';')
    if len(parts) == 2:
        graph_data.append((int(parts[0]), float(parts[1])))

# Print every 100th point
for ts, pnl in graph_data[::50]:
    print(f"  t={ts:6d}: PnL={pnl:.2f}")
if graph_data:
    print(f"  FINAL: t={graph_data[-1][0]}: PnL={graph_data[-1][1]:.2f}")

# Now parse the .log file for trade details
print("\n" + "=" * 60)
print("TRADE ANALYSIS FROM .LOG FILE")
print("=" * 60)

with open('logs/157104/157104.log', 'r') as f:
    log_content = f.read()

# Each line is a JSON array: [compressed_state, compressed_orders, conversions, trader_data, logs]
log_lines = log_content.strip().split('\n')
print(f"Total log entries: {len(log_lines)}")

# Parse all log entries
all_entries = []
for i, line in enumerate(log_lines):
    try:
        entry = json.loads(line)
        all_entries.append(entry)
    except:
        pass

print(f"Parsed entries: {len(all_entries)}")

# Analyze own trades
osm_trades = []
ipr_trades = []
osm_orders_sent = []
ipr_orders_sent = []

for entry in all_entries:
    state = entry[0]  # [timestamp, traderData, listings, order_depths, own_trades, market_trades, position, obs]
    orders = entry[1]  # {symbol: [[sym, price, qty], ...]}
    timestamp = state[0]
    own_trades = state[4]
    position = state[6]

    # Count orders sent
    if 'ASH_COATED_OSMIUM' in orders:
        osm_orders_sent.append((timestamp, orders['ASH_COATED_OSMIUM']))
    if 'INTARIAN_PEPPER_ROOT' in orders:
        ipr_orders_sent.append((timestamp, orders['INTARIAN_PEPPER_ROOT']))

    if 'ASH_COATED_OSMIUM' in own_trades:
        for t in own_trades['ASH_COATED_OSMIUM']:
            osm_trades.append({'ts': timestamp, 'price': t[1], 'qty': t[2], 'buyer': t[3], 'seller': t[4]})
    if 'INTARIAN_PEPPER_ROOT' in own_trades:
        for t in own_trades['INTARIAN_PEPPER_ROOT']:
            ipr_trades.append({'ts': timestamp, 'price': t[1], 'qty': t[2], 'buyer': t[3], 'seller': t[4]})

print(f"\nOSM trades: {len(osm_trades)}")
print(f"IPR trades: {len(ipr_trades)}")
print(f"OSM orders sent at ticks: {len(osm_orders_sent)}")
print(f"IPR orders sent at ticks: {len(ipr_orders_sent)}")

# Analyze OSM trades
print("\n--- OSM TRADES ---")
osm_buy_trades = [t for t in osm_trades if t['buyer'] == 'SUBMISSION']
osm_sell_trades = [t for t in osm_trades if t['seller'] == 'SUBMISSION']
print(f"  Buy trades: {len(osm_buy_trades)}, total qty: {sum(t['qty'] for t in osm_buy_trades)}")
print(f"  Sell trades: {len(osm_sell_trades)}, total qty: {sum(t['qty'] for t in osm_sell_trades)}")

if osm_buy_trades:
    buy_prices = [t['price'] for t in osm_buy_trades]
    print(f"  Buy prices: min={min(buy_prices)}, max={max(buy_prices)}, mean={sum(buy_prices)/len(buy_prices):.1f}")
    buy_price_counts = Counter(buy_prices)
    for p in sorted(buy_price_counts.keys()):
        print(f"    {p}: {buy_price_counts[p]}")

if osm_sell_trades:
    sell_prices = [t['price'] for t in osm_sell_trades]
    print(f"  Sell prices: min={min(sell_prices)}, max={max(sell_prices)}, mean={sum(sell_prices)/len(sell_prices):.1f}")
    sell_price_counts = Counter(sell_prices)
    for p in sorted(sell_price_counts.keys()):
        print(f"    {p}: {sell_price_counts[p]}")

# Analyze IPR trades  
print("\n--- IPR TRADES ---")
ipr_buy_trades = [t for t in ipr_trades if t['buyer'] == 'SUBMISSION']
ipr_sell_trades = [t for t in ipr_trades if t['seller'] == 'SUBMISSION']
print(f"  Buy trades: {len(ipr_buy_trades)}, total qty: {sum(t['qty'] for t in ipr_buy_trades)}")
print(f"  Sell trades: {len(ipr_sell_trades)}, total qty: {sum(t['qty'] for t in ipr_sell_trades)}")

if ipr_buy_trades:
    buy_prices = [t['price'] for t in ipr_buy_trades]
    print(f"  Buy prices: min={min(buy_prices)}, max={max(buy_prices)}, mean={sum(buy_prices)/len(buy_prices):.1f}")
    buy_price_counts = Counter(buy_prices)
    for p in sorted(buy_price_counts.keys()):
        print(f"    {p}: {buy_price_counts[p]}")

if ipr_sell_trades:
    sell_prices = [t['price'] for t in ipr_sell_trades]
    print(f"  Sell prices: min={min(sell_prices)}, max={max(sell_prices)}, mean={sum(sell_prices)/len(sell_prices):.1f}")
    sell_price_counts = Counter(sell_prices)
    for p in sorted(sell_price_counts.keys()):
        print(f"    {p}: {sell_price_counts[p]}")

# Analyze order depths to see what bots are offering
print("\n--- BOT ORDER BOOK ANALYSIS ---")
for prod in ['ASH_COATED_OSMIUM', 'INTARIAN_PEPPER_ROOT']:
    print(f"\n  {prod}:")
    best_bids = []
    best_asks = []
    bid_vols = []
    ask_vols = []
    total_bid_depth = []
    total_ask_depth = []
    
    for entry in all_entries:
        state = entry[0]
        order_depths = state[3]
        if prod in order_depths:
            od = order_depths[prod]
            bids = od[0]  # {price: vol}
            asks = od[1]  # {price: -vol}
            
            if bids:
                bb = max(int(p) for p in bids.keys())
                best_bids.append(bb)
                bid_vols.append(bids[str(bb)])
                total_bid_depth.append(sum(bids.values()))
            if asks:
                ba = min(int(p) for p in asks.keys())
                best_asks.append(ba)
                ask_vols.append(abs(asks[str(ba)]))
                total_ask_depth.append(sum(abs(v) for v in asks.values()))
    
    if best_bids:
        print(f"    Best bid: mean={sum(best_bids)/len(best_bids):.1f}, min={min(best_bids)}, max={max(best_bids)}")
    if best_asks:
        print(f"    Best ask: mean={sum(best_asks)/len(best_asks):.1f}, min={min(best_asks)}, max={max(best_asks)}")
    if bid_vols:
        print(f"    L1 bid vol: mean={sum(bid_vols)/len(bid_vols):.1f}, min={min(bid_vols)}, max={max(bid_vols)}")
    if ask_vols:
        print(f"    L1 ask vol: mean={sum(ask_vols)/len(ask_vols):.1f}, min={min(ask_vols)}, max={max(ask_vols)}")
    if total_bid_depth:
        print(f"    Total bid depth: mean={sum(total_bid_depth)/len(total_bid_depth):.1f}")
    if total_ask_depth:
        print(f"    Total ask depth: mean={sum(total_ask_depth)/len(total_ask_depth):.1f}")

# Position analysis
print("\n--- POSITION OVER TIME ---")
osm_positions = []
ipr_positions = []
for entry in all_entries:
    state = entry[0]
    ts = state[0]
    pos = state[6]
    osm_positions.append((ts, pos.get('ASH_COATED_OSMIUM', 0)))
    ipr_positions.append((ts, pos.get('INTARIAN_PEPPER_ROOT', 0)))

print(f"OSM positions: min={min(p for _,p in osm_positions)}, max={max(p for _,p in osm_positions)}")
print(f"IPR positions: min={min(p for _,p in ipr_positions)}, max={max(p for _,p in ipr_positions)}")

# Check how often positions hit limits
osm_at_limit = sum(1 for _,p in osm_positions if abs(p) >= 50)
ipr_at_limit = sum(1 for _,p in ipr_positions if abs(p) >= 50)
print(f"OSM at limit: {osm_at_limit}/{len(osm_positions)} ({100*osm_at_limit/len(osm_positions):.1f}%)")
print(f"IPR at limit: {ipr_at_limit}/{len(ipr_positions)} ({100*ipr_at_limit/len(ipr_positions):.1f}%)")

# Analyze our orders vs fills
print("\n--- ORDER ANALYSIS ---")
# Check what orders we sent and what got filled

# Sample a few order book states to understand the market
print("\n--- SAMPLE ORDER BOOKS (first 5 ticks) ---")
for i, entry in enumerate(all_entries[:5]):
    state = entry[0]
    orders = entry[1]
    ts = state[0]
    print(f"\n  Tick t={ts}:")
    for prod in ['ASH_COATED_OSMIUM', 'INTARIAN_PEPPER_ROOT']:
        if prod in state[3]:
            od = state[3][prod]
            bids = od[0]
            asks = od[1]
            print(f"    {prod[:3]} book: bids={dict(sorted(bids.items(), key=lambda x: -int(x[0])))} | asks={dict(sorted(asks.items(), key=lambda x: int(x[0])))}")
        if prod in orders:
            print(f"    {prod[:3]} orders: {orders[prod]}")
    pos = state[6]
    print(f"    Position: {pos}")

# Analyze take opportunities
print("\n--- TAKE OPPORTUNITY ANALYSIS ---")
for prod, fv in [('ASH_COATED_OSMIUM', 10000), ('INTARIAN_PEPPER_ROOT', None)]:
    print(f"\n  {prod}:")
    take_buy_opps = 0  # ask < fair
    take_sell_opps = 0  # bid > fair
    total_ticks = 0
    
    for entry in all_entries:
        state = entry[0]
        if prod in state[3]:
            total_ticks += 1
            od = state[3][prod]
            bids = od[0]
            asks = od[1]
            
            if prod == 'ASH_COATED_OSMIUM':
                fair = 10000
            else:
                # Compute wmid
                if bids and asks:
                    bb = max(int(p) for p in bids.keys())
                    ba = min(int(p) for p in asks.keys())
                    bv = bids[str(bb)]
                    av = abs(asks[str(ba)])
                    total = bv + av
                    if total > 0:
                        fair = (bb * av + ba * bv) / total
                    else:
                        fair = (bb + ba) / 2
                else:
                    continue
            
            if asks:
                ba = min(int(p) for p in asks.keys())
                if ba < fair - 0.5:
                    take_buy_opps += 1
            if bids:
                bb = max(int(p) for p in bids.keys())
                if bb > fair + 0.5:
                    take_sell_opps += 1
    
    print(f"    Total ticks: {total_ticks}")
    print(f"    Take buy opps (ask < fair-0.5): {take_buy_opps} ({100*take_buy_opps/max(total_ticks,1):.1f}%)")
    print(f"    Take sell opps (bid > fair+0.5): {take_sell_opps} ({100*take_sell_opps/max(total_ticks,1):.1f}%)")

# Check how many ticks have empty/incomplete books
print("\n--- BOOK COMPLETENESS ---")
for prod in ['ASH_COATED_OSMIUM', 'INTARIAN_PEPPER_ROOT']:
    no_book = 0
    one_sided = 0  
    full_book = 0
    for entry in all_entries:
        state = entry[0]
        if prod in state[3]:
            od = state[3][prod]
            has_bids = bool(od[0])
            has_asks = bool(od[1])
            if has_bids and has_asks:
                full_book += 1
            elif has_bids or has_asks:
                one_sided += 1
            else:
                no_book += 1
        else:
            no_book += 1
    print(f"  {prod}: full={full_book}, one-sided={one_sided}, no_book={no_book}")

# Analyze market trades (bot-to-bot trades)
print("\n--- MARKET TRADES (bot activity) ---")
for prod in ['ASH_COATED_OSMIUM', 'INTARIAN_PEPPER_ROOT']:
    all_market_trades = []
    for entry in all_entries:
        state = entry[0]
        market_trades = state[5]
        if prod in market_trades:
            for t in market_trades[prod]:
                all_market_trades.append({'price': t[1], 'qty': t[2], 'buyer': t[3], 'seller': t[4]})
    print(f"\n  {prod}: {len(all_market_trades)} market trades")
    if all_market_trades:
        prices = [t['price'] for t in all_market_trades]
        print(f"    Prices: min={min(prices)}, max={max(prices)}, mean={sum(prices)/len(prices):.1f}")
        buyers = Counter(t['buyer'] for t in all_market_trades)
        sellers = Counter(t['seller'] for t in all_market_trades)
        print(f"    Top buyers: {buyers.most_common(5)}")
        print(f"    Top sellers: {sellers.most_common(5)}")
