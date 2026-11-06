import json
from collections import defaultdict

# Parse the log file (it's JSON)
with open('logs/42183/42183.log') as f:
    log = json.load(f)

print('Log keys:', list(log.keys()))

# Extract trades
trades = []
if 'tradeHistory' in log:
    trades = log['tradeHistory']
elif 'trades' in log:
    trades = log['trades']
else:
    # Search other keys
    for k, v in log.items():
        if isinstance(v, list) and len(v) > 0 and isinstance(v[0], dict):
            if 'buyer' in v[0] or 'seller' in v[0]:
                trades = v
                print(f'Found trades in key: {k}')
                break

print(f'Total trades: {len(trades)}')

# Separate OUR trades from market trades
our_buys = []
our_sells = []
market_trades = []

for t in trades:
    if t.get('buyer') == 'SUBMISSION':
        our_buys.append(t)
    elif t.get('seller') == 'SUBMISSION':
        our_sells.append(t)
    else:
        market_trades.append(t)

print(f'Our buys: {len(our_buys)}')
print(f'Our sells: {len(our_sells)}')
print(f'Market trades (no SUBMISSION): {len(market_trades)}')
print()

# Analyze by product
for product in ['EMERALDS', 'TOMATOES']:
    buys = [t for t in our_buys if t['symbol'] == product]
    sells = [t for t in our_sells if t['symbol'] == product]
    mkt = [t for t in market_trades if t['symbol'] == product]
    
    buy_qty = sum(t['quantity'] for t in buys)
    sell_qty = sum(t['quantity'] for t in sells)
    buy_vol = sum(t['price'] * t['quantity'] for t in buys)
    sell_vol = sum(t['price'] * t['quantity'] for t in sells)
    
    print(f'=== {product} ===')
    print(f'  Our fills: {len(buys)} buys ({buy_qty} units), {len(sells)} sells ({sell_qty} units)')
    print(f'  Net position change: {buy_qty - sell_qty}')
    if buy_qty > 0:
        print(f'  Avg buy price: {buy_vol/buy_qty:.2f}')
    if sell_qty > 0:
        print(f'  Avg sell price: {sell_vol/sell_qty:.2f}')
    if buy_qty > 0 and sell_qty > 0:
        matched = min(buy_qty, sell_qty)
        avg_buy = buy_vol / buy_qty
        avg_sell = sell_vol / sell_qty
        print(f'  Realized spread (avg sell - avg buy): {avg_sell - avg_buy:.2f}')
        print(f'  Approx realized PnL: {matched * (avg_sell - avg_buy):.2f}')
    print(f'  Market trades (not ours): {len(mkt)}')
    if mkt:
        mkt_qty = sum(t['quantity'] for t in mkt)
        print(f'  Market volume: {mkt_qty}')
    
    # Trade timing analysis
    if buys or sells:
        all_our = sorted(buys + sells, key=lambda t: t['timestamp'])
        ts_first = all_our[0]['timestamp']
        ts_last = all_our[-1]['timestamp']
        print(f'  First trade at: {ts_first}')
        print(f'  Last trade at: {ts_last}')
        
        # Bin by time quadrant
        for q, (lo, hi) in enumerate([(0, 50000), (50000, 100000), (100000, 150000), (150000, 200000)], 1):
            q_buys = [t for t in buys if lo <= t['timestamp'] < hi]
            q_sells = [t for t in sells if lo <= t['timestamp'] < hi]
            q_buy_qty = sum(t['quantity'] for t in q_buys)
            q_sell_qty = sum(t['quantity'] for t in q_sells)
            print(f'  Q{q} ({lo}-{hi}): buys={len(q_buys)}({q_buy_qty}), sells={len(q_sells)}({q_sell_qty})')
    
    # Buy/sell price distributions
    if buys:
        buy_prices = sorted(set(t['price'] for t in buys))
        print(f'  Buy prices: {buy_prices}')
        for p in buy_prices:
            qty = sum(t['quantity'] for t in buys if t['price'] == p)
            cnt = sum(1 for t in buys if t['price'] == p)
            print(f'    @{p}: {cnt} fills, {qty} units')
    if sells:
        sell_prices = sorted(set(t['price'] for t in sells))
        print(f'  Sell prices: {sell_prices}')
        for p in sell_prices:
            qty = sum(t['quantity'] for t in sells if t['price'] == p)
            cnt = sum(1 for t in sells if t['price'] == p)
            print(f'    @{p}: {cnt} fills, {qty} units')
    print()

# Check order book tightness over time for EMERALDS
print('=== EMERALDS ORDER BOOK DETAILS ===')
with open('logs/42183/42183.json') as f:
    data = json.load(f)

lines = data['activitiesLog'].strip().split('\n')
header = lines[0].split(';')
emerald_rows = []
for line in lines[1:]:
    parts = line.split(';')
    if len(parts) >= len(header):
        row = dict(zip(header, parts))
        if row['product'] == 'EMERALDS':
            emerald_rows.append(row)

# Find ticks where bid1 or ask1 is NOT the standard 9992/10008
interesting = []
for r in emerald_rows:
    b1 = float(r['bid_price_1']) if r['bid_price_1'] else None
    a1 = float(r['ask_price_1']) if r['ask_price_1'] else None
    if b1 and b1 != 9992:
        interesting.append(('bid', int(r['timestamp']), b1, r['bid_volume_1']))
    if a1 and a1 != 10008:
        interesting.append(('ask', int(r['timestamp']), a1, r['ask_volume_1']))

print(f'Ticks with non-standard L1: {len(interesting)} out of {len(emerald_rows)}')
for i in interesting[:30]:
    print(f'  {i}')
if len(interesting) > 30:
    print(f'  ... and {len(interesting) - 30} more')

# Count standard vs non-standard
bid_counts = defaultdict(int)
ask_counts = defaultdict(int)
for r in emerald_rows:
    b1 = r['bid_price_1']
    a1 = r['ask_price_1']
    if b1:
        bid_counts[b1] += 1
    if a1:
        ask_counts[a1] += 1

print(f'\nEMERALDS bid_price_1 distribution:')
for p, c in sorted(bid_counts.items(), key=lambda x: -x[1]):
    print(f'  {p}: {c} ticks ({c/len(emerald_rows)*100:.1f}%)')
print(f'EMERALDS ask_price_1 distribution:')
for p, c in sorted(ask_counts.items(), key=lambda x: -x[1]):
    print(f'  {p}: {c} ticks ({c/len(emerald_rows)*100:.1f}%)')

# Same for TOMATOES
print('\n=== TOMATOES ORDER BOOK DETAILS ===')
tomato_rows = []
for line in lines[1:]:
    parts = line.split(';')
    if len(parts) >= len(header):
        row = dict(zip(header, parts))
        if row['product'] == 'TOMATOES':
            tomato_rows.append(row)

bid_counts_t = defaultdict(int)
ask_counts_t = defaultdict(int)
for r in tomato_rows:
    b1 = r['bid_price_1']
    a1 = r['ask_price_1']
    if b1:
        bid_counts_t[b1] += 1
    if a1:
        ask_counts_t[a1] += 1

print(f'TOMATOES bid_price_1 distribution (top 15):')
for p, c in sorted(bid_counts_t.items(), key=lambda x: -x[1])[:15]:
    print(f'  {p}: {c} ticks ({c/len(tomato_rows)*100:.1f}%)')
print(f'TOMATOES ask_price_1 distribution (top 15):')
for p, c in sorted(ask_counts_t.items(), key=lambda x: -x[1])[:15]:
    print(f'  {p}: {c} ticks ({c/len(tomato_rows)*100:.1f}%)')

# Check TOMATOES mid price range
mids_t = [float(r['mid_price']) for r in tomato_rows if r['mid_price']]
print(f'\nTOMATOES mid price: min={min(mids_t):.1f}, max={max(mids_t):.1f}')
print(f'  Range: {max(mids_t) - min(mids_t):.1f}')
# Divide into quartiles
n = len(mids_t)
for q in [0, 0.25, 0.5, 0.75, 1.0]:
    idx = min(int(n * q), n - 1)
    print(f'  {q*100:.0f}th percentile (by time): mid={mids_t[idx]:.1f}')
