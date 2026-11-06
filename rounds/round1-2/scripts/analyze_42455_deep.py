import json, csv, io, statistics
from collections import defaultdict, Counter

with open(r'.\logs\42455\42455.log') as f:
    data = json.load(f)

print(f'=== PROFIT: {data.get("profit", "N/A")} (from .json) ===\n')

# Parse trade history 
trades = data['tradeHistory']
print(f'Total trades: {len(trades)}')

by_prod = defaultdict(list)
for t in trades:
    by_prod[t['symbol']].append(t)

for sym, tlist in by_prod.items():
    buys = [t for t in tlist if t['buyer'] == 'SUBMISSION']
    sells = [t for t in tlist if t['seller'] == 'SUBMISSION']
    
    buy_qty = sum(t['quantity'] for t in buys)
    sell_qty = sum(t['quantity'] for t in sells)
    buy_value = sum(t['price'] * t['quantity'] for t in buys)
    sell_value = sum(t['price'] * t['quantity'] for t in sells)
    
    avg_buy = buy_value / buy_qty if buy_qty else 0
    avg_sell = sell_value / sell_qty if sell_qty else 0
    
    print(f'\n=== {sym} ({len(tlist)} trades) ===')
    print(f'  Buys: {len(buys)} trades, {buy_qty} units, avg price {avg_buy:.2f}')
    print(f'  Sells: {len(sells)} trades, {sell_qty} units, avg price {avg_sell:.2f}')
    if buy_qty and sell_qty:
        print(f'  Avg edge/unit: {avg_sell - avg_buy:.2f}')
        net_pos = buy_qty - sell_qty
        realized_pnl = sell_value - buy_value  # only if balanced
        print(f'  Net position: {net_pos}')
        print(f'  Total bought value: {buy_value:.0f}, Total sold value: {sell_value:.0f}')
    
    # Trade timing
    timestamps = [t['timestamp'] for t in tlist]
    print(f'  First trade: t={min(timestamps)}, Last trade: t={max(timestamps)}')
    
    # Trade size distribution
    buy_sizes = Counter(t['quantity'] for t in buys)
    sell_sizes = Counter(t['quantity'] for t in sells)
    print(f'  Buy sizes: {dict(sorted(buy_sizes.items()))}')
    print(f'  Sell sizes: {dict(sorted(sell_sizes.items()))}')

# Parse sandbox logs for position tracking
print('\n=== POSITION & ORDER ANALYSIS ===')
logs = data['logs']

# Track positions over time from lambda logs
positions = {'EMERALDS': [], 'TOMATOES': []}
orders_placed = {'EMERALDS': [], 'TOMATOES': []}

for entry in logs:
    ts = entry['timestamp']
    ll = entry['lambdaLog']
    if not ll:
        continue
    try:
        parsed = json.loads(ll)
        if isinstance(parsed, list) and len(parsed) >= 7:
            state_data = parsed[0]  # [timestamp, traderData, listings, order_depths, ...]
            placed_orders = parsed[1]  # our orders
            
            # Extract position from state
            if isinstance(state_data, list) and len(state_data) >= 7:
                pos = state_data[6]  # position dict
                if isinstance(pos, dict):
                    for prod in ['EMERALDS', 'TOMATOES']:
                        if prod in pos:
                            positions[prod].append((ts, pos[prod]))
            
            # Extract our orders
            if isinstance(placed_orders, dict):
                for prod, ords in placed_orders.items():
                    for o in ords:
                        if isinstance(o, list) and len(o) >= 3:
                            orders_placed[prod].append({
                                'ts': ts,
                                'price': o[1],
                                'qty': o[2]
                            })
    except (json.JSONDecodeError, TypeError, IndexError):
        continue

for prod in ['EMERALDS', 'TOMATOES']:
    pos_list = positions[prod]
    ords = orders_placed[prod]
    
    if pos_list:
        pos_values = [p[1] for p in pos_list]
        print(f'\n--- {prod} ---')
        print(f'  Position range: {min(pos_values)} to {max(pos_values)}')
        print(f'  Final position: {pos_values[-1]}')
        extreme = sum(1 for p in pos_values if abs(p) > 60)
        print(f'  Ticks at |pos|>60: {extreme}/{len(pos_values)} ({100*extreme/len(pos_values):.1f}%)')
        
        # Position distribution
        hist = Counter()
        for p in pos_values:
            bucket = (p // 20) * 20
            hist[bucket] += 1
        print(f'  Position buckets: {dict(sorted(hist.items()))}')
    
    if ords:
        bid_orders = [o for o in ords if o['qty'] > 0]
        ask_orders = [o for o in ords if o['qty'] < 0]
        print(f'  Bid orders placed: {len(bid_orders)}, Ask orders placed: {len(ask_orders)}')
        
        if bid_orders:
            bid_prices = Counter(o['price'] for o in bid_orders)
            print(f'  Top bid prices: {dict(sorted(bid_prices.items(), key=lambda x: -x[1])[:5])}')
        if ask_orders:
            ask_prices = Counter(o['price'] for o in ask_orders)
            print(f'  Top ask prices: {dict(sorted(ask_prices.items(), key=lambda x: -x[1])[:5])}')

# Parse activities log for PnL curve
al = data['activitiesLog']
reader = csv.DictReader(io.StringIO(al), delimiter=';')
activities = list(reader)

# PnL at key timestamps
emerald_pnl = [(int(r['timestamp']), float(r['profit_and_loss'])) for r in activities if r['product'] == 'EMERALDS']
tomato_pnl = [(int(r['timestamp']), float(r['profit_and_loss'])) for r in activities if r['product'] == 'TOMATOES']

print(f'\n=== PNL PROGRESSION ===')
for prod, pnl_series in [('EMERALDS', emerald_pnl), ('TOMATOES', tomato_pnl)]:
    if pnl_series:
        # Sample at 25%, 50%, 75%, 100%
        n = len(pnl_series)
        for pct in [0.25, 0.5, 0.75, 1.0]:
            idx = min(int(n * pct), n - 1)
            ts, pnl = pnl_series[idx]
            print(f'  {prod} at {pct*100:.0f}% (t={ts}): PnL={pnl:.1f}')

# Spread analysis over time for TOMATOES  
print(f'\n=== TOMATOES SPREAD ANALYSIS ===')
tom_activities = [r for r in activities if r['product'] == 'TOMATOES']
narrow_spread = sum(1 for r in tom_activities if r['bid_price_1'] and r['ask_price_1'] and float(r['ask_price_1']) - float(r['bid_price_1']) < 10)
wide_spread = sum(1 for r in tom_activities if r['bid_price_1'] and r['ask_price_1'] and float(r['ask_price_1']) - float(r['bid_price_1']) >= 13)
print(f'  Narrow spread (<10): {narrow_spread}/{len(tom_activities)} ({100*narrow_spread/len(tom_activities):.1f}%)')
print(f'  Wide spread (>=13): {wide_spread}/{len(tom_activities)} ({100*wide_spread/len(tom_activities):.1f}%)')

# Check EMERALDS spread 
em_activities = [r for r in activities if r['product'] == 'EMERALDS']
em_spreads = []
for r in em_activities:
    if r['bid_price_1'] and r['ask_price_1']:
        s = float(r['ask_price_1']) - float(r['bid_price_1'])
        em_spreads.append(s)
em_spread_dist = Counter(int(s) for s in em_spreads)
print(f'\n=== EMERALDS SPREAD DISTRIBUTION ===')
print(f'  {dict(sorted(em_spread_dist.items()))}')
