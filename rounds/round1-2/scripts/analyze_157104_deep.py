"""Deep analysis of 157104 log file - trades, orders, fills."""
import json
from collections import Counter, defaultdict

with open('logs/157104/157104.log', 'r') as f:
    data = json.load(f)

print("=" * 60)
print("157104 DEEP LOG ANALYSIS")
print("=" * 60)

# Parse trade history
trades = data['tradeHistory']
print(f"\nTotal trades: {len(trades)}")

osm_trades = [t for t in trades if t['symbol'] == 'ASH_COATED_OSMIUM']
ipr_trades = [t for t in trades if t['symbol'] == 'INTARIAN_PEPPER_ROOT']
print(f"OSM trades: {len(osm_trades)}")
print(f"IPR trades: {len(ipr_trades)}")

# OSM trade analysis
print("\n--- OSM TRADES ---")
osm_buys = [t for t in osm_trades if t['buyer'] == 'SUBMISSION']
osm_sells = [t for t in osm_trades if t['seller'] == 'SUBMISSION']
print(f"  Buys: {len(osm_buys)}, qty={sum(t['quantity'] for t in osm_buys)}")
print(f"  Sells: {len(osm_sells)}, qty={sum(t['quantity'] for t in osm_sells)}")

if osm_buys:
    prices = Counter(t['price'] for t in osm_buys)
    print(f"  Buy price distribution:")
    for p in sorted(prices.keys()):
        print(f"    {p}: {prices[p]} trades, qty={sum(t['quantity'] for t in osm_buys if t['price']==p)}")

if osm_sells:
    prices = Counter(t['price'] for t in osm_sells)
    print(f"  Sell price distribution:")
    for p in sorted(prices.keys()):
        print(f"    {p}: {prices[p]} trades, qty={sum(t['quantity'] for t in osm_sells if t['price']==p)}")

# IPR trade analysis
print("\n--- IPR TRADES ---")
ipr_buys = [t for t in ipr_trades if t['buyer'] == 'SUBMISSION']
ipr_sells = [t for t in ipr_trades if t['seller'] == 'SUBMISSION']
print(f"  Buys: {len(ipr_buys)}, qty={sum(t['quantity'] for t in ipr_buys)}")
print(f"  Sells: {len(ipr_sells)}, qty={sum(t['quantity'] for t in ipr_sells)}")

if ipr_buys:
    prices = Counter(t['price'] for t in ipr_buys)
    print(f"  Buy price distribution:")
    for p in sorted(prices.keys()):
        print(f"    {p}: {prices[p]} trades, qty={sum(t['quantity'] for t in ipr_buys if t['price']==p)}")

if ipr_sells:
    prices = Counter(t['price'] for t in ipr_sells)
    print(f"  Sell price distribution:")
    for p in sorted(prices.keys()):
        print(f"    {p}: {prices[p]} trades, qty={sum(t['quantity'] for t in ipr_sells if t['price']==p)}")

# Parse logs entries
logs = data['logs']
print(f"\n\nTotal log entries: {len(logs)}")

# Each log entry is already structured
# Let's examine the first log entry
print("\n--- FIRST LOG ENTRY STRUCTURE ---")
first = logs[0]
print(f"Type: {type(first)}")
if isinstance(first, dict):
    print(f"Keys: {list(first.keys())}")
elif isinstance(first, list):
    print(f"Length: {len(first)}")
    for i, item in enumerate(first):
        if isinstance(item, str):
            print(f"  [{i}]: str len {len(item)}")
        elif isinstance(item, dict):
            print(f"  [{i}]: dict keys {list(item.keys())[:5]}")
        elif isinstance(item, list):
            print(f"  [{i}]: list len {len(item)}")
        else:
            print(f"  [{i}]: {type(item).__name__} = {str(item)[:100]}")
elif isinstance(first, str):
    # Try to parse as JSON
    try:
        parsed = json.loads(first)
        print(f"  Parsed: type={type(parsed).__name__}")
        if isinstance(parsed, list):
            print(f"  Len: {len(parsed)}")
            for i, item in enumerate(parsed):
                if isinstance(item, str):
                    print(f"    [{i}]: str len {len(item)}")
                elif isinstance(item, dict):
                    print(f"    [{i}]: dict keys {list(item.keys())[:5]}")
                elif isinstance(item, list):
                    print(f"    [{i}]: list len {len(item)}")
                else:
                    print(f"    [{i}]: {type(item).__name__} = {str(item)[:100]}")
    except:
        print(f"  Raw (first 300): {first[:300]}")

# Parse all logs to extract order book states and our orders
print("\n\n--- PARSING ALL LOG ENTRIES ---")
parsed_logs = []
for i, entry in enumerate(logs):
    if isinstance(entry, str):
        try:
            parsed = json.loads(entry)
            parsed_logs.append(parsed)
        except:
            pass
    elif isinstance(entry, list):
        parsed_logs.append(entry)
    elif isinstance(entry, dict):
        parsed_logs.append(entry)

print(f"Parsed {len(parsed_logs)} entries")

if parsed_logs:
    # Show structure
    first_parsed = parsed_logs[0]
    print(f"First parsed type: {type(first_parsed)}")
    if isinstance(first_parsed, list) and len(first_parsed) >= 5:
        # Format: [state, orders, conversions, trader_data, logs]
        state = first_parsed[0]
        orders = first_parsed[1]
        conversions = first_parsed[2]
        trader_data = first_parsed[3]
        log_text = first_parsed[4]
        
        print(f"\nState: {type(state)}")
        if isinstance(state, list):
            print(f"  Timestamp: {state[0]}")
            print(f"  Trader data: {str(state[1])[:100]}")
            print(f"  Listings: {type(state[2])}")
            print(f"  Order depths: {type(state[3])}")
            if isinstance(state[3], dict):
                for prod, od in state[3].items():
                    print(f"    {prod}: bids={od[0]}, asks={od[1]}")
            print(f"  Own trades: {state[4]}")
            print(f"  Market trades: {state[5]}")
            print(f"  Position: {state[6]}")
        
        print(f"\nOrders sent: {orders}")
        print(f"Log text: {log_text[:200] if isinstance(log_text, str) else log_text}")
    
    # Now do full analysis across all ticks
    print("\n\n--- FULL TICK-BY-TICK ANALYSIS ---")
    
    osm_fill_analysis = {'takes': 0, 'makes': 0, 'take_qty': 0, 'make_qty': 0}
    ipr_fill_analysis = {'takes': 0, 'makes': 0, 'take_qty': 0, 'make_qty': 0}
    
    position_history = {'ASH_COATED_OSMIUM': [], 'INTARIAN_PEPPER_ROOT': []}
    
    osm_our_bid_prices = []
    osm_our_ask_prices = []
    ipr_our_bid_prices = []
    ipr_our_ask_prices = []
    
    ipr_fair_values = []
    
    for entry in parsed_logs:
        if not isinstance(entry, list) or len(entry) < 5:
            continue
        state = entry[0]
        orders = entry[1]
        
        if not isinstance(state, list) or len(state) < 7:
            continue
            
        ts = state[0]
        pos = state[6]
        
        position_history['ASH_COATED_OSMIUM'].append((ts, pos.get('ASH_COATED_OSMIUM', 0)))
        position_history['INTARIAN_PEPPER_ROOT'].append((ts, pos.get('INTARIAN_PEPPER_ROOT', 0)))
        
        # Track our orders
        for prod in ['ASH_COATED_OSMIUM', 'INTARIAN_PEPPER_ROOT']:
            if prod in orders:
                for order in orders[prod]:
                    price = order[1]
                    qty = order[2]
                    if prod == 'ASH_COATED_OSMIUM':
                        if qty > 0:
                            osm_our_bid_prices.append(price)
                        else:
                            osm_our_ask_prices.append(price)
                    else:
                        if qty > 0:
                            ipr_our_bid_prices.append(price)
                        else:
                            ipr_our_ask_prices.append(price)
        
        # Track IPR fair values
        if 'INTARIAN_PEPPER_ROOT' in state[3]:
            od = state[3]['INTARIAN_PEPPER_ROOT']
            bids, asks = od[0], od[1]
            if bids and asks:
                bb = max(int(p) for p in bids.keys())
                ba = min(int(p) for p in asks.keys())
                bv = bids[str(bb)]
                av = abs(asks[str(ba)])
                total = bv + av
                if total > 0:
                    wmid = (bb * av + ba * bv) / total
                else:
                    wmid = (bb + ba) / 2
                ipr_fair_values.append((ts, wmid))
    
    # Position analysis
    for prod in ['ASH_COATED_OSMIUM', 'INTARIAN_PEPPER_ROOT']:
        ph = position_history[prod]
        if ph:
            positions = [p for _, p in ph]
            print(f"\n{prod} position:")
            print(f"  Min={min(positions)}, Max={max(positions)}, Mean={sum(positions)/len(positions):.1f}")
            print(f"  At limit (-50): {sum(1 for p in positions if p <= -50)}")
            print(f"  At limit (+50): {sum(1 for p in positions if p >= 50)}")
            # Position distribution
            pos_counts = Counter(positions)
            print(f"  Distribution (top 10):")
            for p, c in pos_counts.most_common(10):
                print(f"    pos={p}: {c} ticks ({100*c/len(positions):.1f}%)")
    
    # Our order prices
    print(f"\nOur OSM bid prices: mean={sum(osm_our_bid_prices)/max(len(osm_our_bid_prices),1):.0f}, unique={len(set(osm_our_bid_prices))}, n={len(osm_our_bid_prices)}")
    if osm_our_bid_prices:
        print(f"  Distribution: {Counter(osm_our_bid_prices).most_common(5)}")
    print(f"Our OSM ask prices: mean={sum(osm_our_ask_prices)/max(len(osm_our_ask_prices),1):.0f}, unique={len(set(osm_our_ask_prices))}, n={len(osm_our_ask_prices)}")
    if osm_our_ask_prices:
        print(f"  Distribution: {Counter(osm_our_ask_prices).most_common(5)}")
    
    print(f"\nOur IPR bid prices: mean={sum(ipr_our_bid_prices)/max(len(ipr_our_bid_prices),1):.0f}, unique={len(set(ipr_our_bid_prices))}, n={len(ipr_our_bid_prices)}")
    if ipr_our_bid_prices:
        print(f"  Distribution (top 10): {Counter(ipr_our_bid_prices).most_common(10)}")
    print(f"Our IPR ask prices: mean={sum(ipr_our_ask_prices)/max(len(ipr_our_ask_prices),1):.0f}, unique={len(set(ipr_our_ask_prices))}, n={len(ipr_our_ask_prices)}")
    if ipr_our_ask_prices:
        print(f"  Distribution (top 10): {Counter(ipr_our_ask_prices).most_common(10)}")
    
    # IPR fair value tracking
    if ipr_fair_values:
        print(f"\nIPR fair value (wmid):")
        print(f"  First: {ipr_fair_values[0][1]:.1f}, Last: {ipr_fair_values[-1][1]:.1f}")
        print(f"  Range: {min(v for _,v in ipr_fair_values):.1f} - {max(v for _,v in ipr_fair_values):.1f}")

# Categorize trades as takes vs makes
print("\n\n--- TAKE vs MAKE TRADE CLASSIFICATION ---")
# A trade is a TAKE when we cross the spread (we buy at the ask or sell at the bid)
# A trade is a MAKE when our resting order gets filled

# For each trade, check if our order price was at/near the bot's best bid/ask
# Actually simpler: in the platform, if SUBMISSION is buyer and the price is at/near ask, it's a take
# If SUBMISSION is buyer and the price is at our bid, it's a make (bot crossed to us)

# Look at trade prices relative to the book at that time
# Using trade history from the log
for prod, prod_trades, label in [('ASH_COATED_OSMIUM', osm_trades, 'OSM'), 
                                   ('INTARIAN_PEPPER_ROOT', ipr_trades, 'IPR')]:
    print(f"\n{label} ({len(prod_trades)} trades):")
    
    my_buys = [t for t in prod_trades if t['buyer'] == 'SUBMISSION']
    my_sells = [t for t in prod_trades if t['seller'] == 'SUBMISSION']
    
    if my_buys:
        print(f"  My buys ({len(my_buys)}):")
        for t in my_buys[:20]:
            print(f"    t={t['timestamp']}: price={t['price']}, qty={t['quantity']}")
    
    if my_sells:
        print(f"  My sells ({len(my_sells)}):")
        for t in my_sells[:20]:
            print(f"    t={t['timestamp']}: price={t['price']}, qty={t['quantity']}")

# Who fills our orders?
print("\n\n--- COUNTERPARTIES ---")
for prod_trades, label in [(osm_trades, 'OSM'), (ipr_trades, 'IPR')]:
    print(f"\n{label}:")
    counterparties_buy = Counter()
    counterparties_sell = Counter()
    for t in prod_trades:
        if t['buyer'] == 'SUBMISSION':
            counterparties_buy[t['seller']] += t['quantity']
        elif t['seller'] == 'SUBMISSION':
            counterparties_sell[t['buyer']] += t['quantity']
    print(f"  When we buy, sellers: {counterparties_buy.most_common(10)}")
    print(f"  When we sell, buyers: {counterparties_sell.most_common(10)}")
