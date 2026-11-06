import json, csv, io
from collections import defaultdict, Counter

with open(r'.\logs\42455\42455.log') as f:
    data = json.load(f)

logs = data['logs']

positions_ts = []
our_orders_ts = []
book_ts = []
own_trades_ts = []

for entry in logs:
    ts = entry['timestamp']
    ll = entry['lambdaLog']
    if not ll:
        continue
    try:
        parsed = json.loads(ll)
        state = parsed[0]
        our_orders = parsed[1]
        
        pos = state[6] if len(state) > 6 else {}
        if isinstance(pos, dict):
            positions_ts.append((ts, dict(pos)))
        
        books = state[3] if len(state) > 3 else {}
        if isinstance(books, dict):
            book_entry = {}
            for prod, book in books.items():
                if isinstance(book, list) and len(book) == 2:
                    bids = {int(k): v for k, v in book[0].items()} if book[0] else {}
                    asks = {int(k): v for k, v in book[1].items()} if book[1] else {}
                    book_entry[prod] = {'bids': bids, 'asks': asks}
            book_ts.append((ts, book_entry))
        
        if isinstance(our_orders, dict):
            our_orders_ts.append((ts, our_orders))
        
        own_trades = state[4] if len(state) > 4 else {}
        if isinstance(own_trades, dict):
            for prod, trades in own_trades.items():
                for t in trades:
                    if isinstance(t, list) and len(t) >= 5:
                        own_trades_ts.append({
                            'ts': ts, 'prod': prod, 'price': t[1], 'qty': t[2],
                            'buyer': t[3], 'seller': t[4]
                        })
    except Exception:
        continue

print(f'Parsed {len(positions_ts)} pos, {len(book_ts)} book, {len(our_orders_ts)} order, {len(own_trades_ts)} own_trade entries')

# POSITION ANALYSIS
print('\n=== POSITION ANALYSIS ===')
for prod in ['EMERALDS', 'TOMATOES']:
    pos_vals = [(ts, p.get(prod, 0)) for ts, p in positions_ts]
    vals = [p for _, p in pos_vals]
    extreme = sum(1 for v in vals if abs(v) > 60)
    at_limit = sum(1 for v in vals if abs(v) >= 80)
    
    print(f'\n{prod}:')
    print(f'  Range: {min(vals)} to {max(vals)}')
    print(f'  |pos|>60: {extreme}/{len(vals)} ({100*extreme/len(vals):.1f}%)')
    print(f'  At limit: {at_limit}/{len(vals)} ({100*at_limit/len(vals):.1f}%)')
    
    hist = Counter()
    for v in vals:
        bucket = (v // 10) * 10
        hist[bucket] += 1
    print(f'  Buckets: {dict(sorted(hist.items()))}')

# ORDER PLACEMENT vs BOOK
print('\n=== OUR ORDERS vs MARKET ===')
for prod in ['EMERALDS', 'TOMATOES']:
    bid_edges = []
    ask_edges = []
    our_spreads = []
    
    for i in range(min(len(our_orders_ts), len(book_ts))):
        ts1, orders = our_orders_ts[i]
        ts2, books = book_ts[i]
        if ts1 != ts2 or prod not in orders or prod not in books:
            continue
        
        bids_in_book = books[prod]['bids']
        asks_in_book = books[prod]['asks']
        if not bids_in_book or not asks_in_book:
            continue
        
        best_bid = max(bids_in_book.keys())
        best_ask = min(asks_in_book.keys())
        
        prod_orders = orders[prod]
        our_bids = [o for o in prod_orders if isinstance(o, list) and o[2] > 0]
        our_asks = [o for o in prod_orders if isinstance(o, list) and o[2] < 0]
        
        if our_bids:
            our_best_bid = max(o[1] for o in our_bids)
            bid_edges.append(our_best_bid - best_bid)
        if our_asks:
            our_best_ask = min(o[1] for o in our_asks)
            ask_edges.append(best_ask - our_best_ask)
        if our_bids and our_asks:
            our_spreads.append(min(o[1] for o in our_asks) - max(o[1] for o in our_bids))
    
    print(f'\n{prod}:')
    if bid_edges:
        print(f'  Bid edge (>0=inside spread): {dict(sorted(Counter(bid_edges).items()))}')
    if ask_edges:
        print(f'  Ask edge (>0=inside spread): {dict(sorted(Counter(ask_edges).items()))}')
    if our_spreads:
        print(f'  Our spread widths: {dict(sorted(Counter(our_spreads).items()))}')

# MARKET SPREAD
print('\n=== MARKET SPREAD ===')
for prod in ['EMERALDS', 'TOMATOES']:
    spreads = []
    for ts, books in book_ts:
        if prod in books and books[prod]['bids'] and books[prod]['asks']:
            spread = min(books[prod]['asks'].keys()) - max(books[prod]['bids'].keys())
            spreads.append(spread)
    print(f'{prod}: {dict(sorted(Counter(spreads).items()))}')

# FILL RATE
print('\n=== FILL RATE ===')
trades_by_ts = defaultdict(list)
for t in own_trades_ts:
    trades_by_ts[(t['ts'], t['prod'])].append(t)

for prod in ['EMERALDS', 'TOMATOES']:
    fill_ticks = sum(1 for (ts, p) in trades_by_ts if p == prod)
    total = len(book_ts)
    total_qty = sum(t['qty'] for t in own_trades_ts if t['prod'] == prod)
    print(f'{prod}: filled on {fill_ticks}/{total} ticks ({100*fill_ticks/total:.1f}%), total qty {total_qty}')

# TOMATOES ORDER SIZES - are we quoting full 80 when we could get partially filled?
print('\n=== ORDER SIZES ===')
for prod in ['EMERALDS', 'TOMATOES']:
    bid_qtys = []
    ask_qtys = []
    for ts, orders in our_orders_ts:
        if prod not in orders:
            continue
        for o in orders[prod]:
            if isinstance(o, list):
                if o[2] > 0:
                    bid_qtys.append(o[2])
                else:
                    ask_qtys.append(abs(o[2]))
    print(f'\n{prod}:')
    print(f'  Bid sizes: {dict(sorted(Counter(bid_qtys).items()))}')
    print(f'  Ask sizes: {dict(sorted(Counter(ask_qtys).items()))}')

# EMERALDS: check if we're always quoting at 9993/10007
print('\n=== EMERALDS ORDER PRICES ===')
em_bid_prices = []
em_ask_prices = []
for ts, orders in our_orders_ts:
    if 'EMERALDS' not in orders:
        continue
    for o in orders['EMERALDS']:
        if isinstance(o, list):
            if o[2] > 0:
                em_bid_prices.append(o[1])
            else:
                em_ask_prices.append(o[1])
print(f'Bid prices: {dict(sorted(Counter(em_bid_prices).items()))}')
print(f'Ask prices: {dict(sorted(Counter(em_ask_prices).items()))}')

# TOMATOES prices
print('\n=== TOMATOES ORDER PRICES (sample) ===')
tom_bid_prices = []
tom_ask_prices = []
tom_bid_spreads = []  # our bid minus mid
for i in range(min(len(our_orders_ts), len(book_ts))):
    ts, orders = our_orders_ts[i]
    _, books = book_ts[i]
    if 'TOMATOES' not in orders or 'TOMATOES' not in books:
        continue
    bids = books['TOMATOES']['bids']
    asks = books['TOMATOES']['asks']
    if not bids or not asks:
        continue
    mid = (max(bids.keys()) + min(asks.keys())) / 2
    for o in orders['TOMATOES']:
        if isinstance(o, list):
            if o[2] > 0:
                tom_bid_prices.append(o[1])
                tom_bid_spreads.append(round(o[1] - mid, 1))
            else:
                tom_ask_prices.append(o[1])

print(f'Bid distance from mid: {dict(sorted(Counter(tom_bid_spreads).items()))}')
