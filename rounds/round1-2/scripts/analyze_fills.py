import json
from collections import defaultdict

with open(r'.\logs\42126\42126.log', 'r') as f:
    log_data = json.load(f)

with open(r'.\logs\42126\42126.json', 'r') as f:
    json_data = json.load(f)

trades = log_data['tradeHistory']

# Parse activitiesLog for book state at each tick
lines = json_data['activitiesLog'].strip().split('\n')
header = lines[0].split(';')
# day;timestamp;product;bid_price_1;bid_volume_1;bid_price_2;bid_volume_2;bid_price_3;bid_volume_3;ask_price_1;ask_volume_1;ask_price_2;ask_volume_2;ask_price_3;ask_volume_3;mid_price;profit_and_loss

book_at = {}  # (timestamp, product) -> {bid1, ask1, mid, spread}
for line in lines[1:]:
    parts = line.split(';')
    ts = int(parts[1])
    prod = parts[2]
    bid1 = float(parts[3]) if parts[3] else None
    ask1 = float(parts[9]) if parts[9] else None
    mid = float(parts[15]) if parts[15] else None
    spread = (ask1 - bid1) if bid1 and ask1 else None
    book_at[(ts, prod)] = {'bid1': bid1, 'ask1': ask1, 'mid': mid, 'spread': spread}


def analyze_product(name, product_trades):
    buys = [t for t in product_trades if t['buyer'] == 'SUBMISSION']
    sells = [t for t in product_trades if t['seller'] == 'SUBMISSION']
    # Some trades have neither buyer nor seller as SUBMISSION (market trades we see)
    neither = [t for t in product_trades if t['buyer'] != 'SUBMISSION' and t['seller'] != 'SUBMISSION']

    print(f'{"=" * 55}')
    print(f'  {name} FILL ANALYSIS')
    print(f'{"=" * 55}')
    print(f'Total fills: {len(product_trades)} ({len(buys)} buys, {len(sells)} sells, {len(neither)} neither)')
    print()

    # Buy price distribution
    buy_prices = defaultdict(int)
    buy_edge = []
    for t in buys:
        p = int(t['price'])
        buy_prices[p] += t['quantity']
        book = book_at.get((t['timestamp'], name))
        if book and book['mid']:
            edge = book['mid'] - p
            buy_edge.append(edge)

    print('BUY fills (price distribution):')
    for p, q in sorted(buy_prices.items()):
        print(f'  @ {p}: {q} units')
    if buy_edge:
        avg_edge = sum(buy_edge) / len(buy_edge)
        print(f'  Avg edge (mid - buy_price): {avg_edge:.2f}')
    print()

    # Sell price distribution
    sell_prices = defaultdict(int)
    sell_edge = []
    for t in sells:
        p = int(t['price'])
        sell_prices[p] += t['quantity']
        book = book_at.get((t['timestamp'], name))
        if book and book['mid']:
            edge = p - book['mid']
            sell_edge.append(edge)

    print('SELL fills (price distribution):')
    for p, q in sorted(sell_prices.items()):
        print(f'  @ {p}: {q} units')
    if sell_edge:
        avg_edge = sum(sell_edge) / len(sell_edge)
        print(f'  Avg edge (sell_price - mid): {avg_edge:.2f}')
    print()

    # Fill rate
    total_ticks = 2000
    ticks_with_fill = len(set(t['timestamp'] for t in product_trades if t['buyer'] == 'SUBMISSION' or t['seller'] == 'SUBMISSION'))
    print(f'Fill rate: {ticks_with_fill}/{total_ticks} ticks had a fill ({ticks_with_fill/total_ticks*100:.1f}%)')
    
    # Time distribution (early vs late)
    our_trades = [t for t in product_trades if t['buyer'] == 'SUBMISSION' or t['seller'] == 'SUBMISSION']
    first_half = [t for t in our_trades if t['timestamp'] < 100000]
    second_half = [t for t in our_trades if t['timestamp'] >= 100000]
    print(f'First half fills: {len(first_half)}, Second half fills: {len(second_half)}')
    
    # Volume per fill
    our_vols = [t['quantity'] for t in our_trades]
    if our_vols:
        avg_vol = sum(our_vols) / len(our_vols)
        print(f'Avg fill size: {avg_vol:.1f} units, Max: {max(our_vols)}, Min: {min(our_vols)}')
    
    # Position walk through time
    print()
    print('Position evolution (sampled):')
    pos = 0
    milestone_times = [0, 25000, 50000, 75000, 100000, 125000, 150000, 175000, 199900]
    trade_idx = 0
    sorted_trades = sorted(our_trades, key=lambda x: x['timestamp'])
    for target_t in milestone_times:
        while trade_idx < len(sorted_trades) and sorted_trades[trade_idx]['timestamp'] <= target_t:
            t = sorted_trades[trade_idx]
            if t['buyer'] == 'SUBMISSION':
                pos += t['quantity']
            else:
                pos -= t['quantity']
            trade_idx += 1
        print(f'  t={target_t:>6}: pos={pos:>+4}')
    print()

    # Adverse selection: check PnL at trade points
    # For buys: did price go up after? For sells: did price go down after?
    if name == 'EMERALDS':
        fair = 10000
        print(f'Fills vs fair value ({fair}):')
        buy_above = sum(1 for t in buys if t['price'] > fair)
        buy_at = sum(1 for t in buys if t['price'] == fair)
        buy_below = sum(1 for t in buys if t['price'] < fair)
        sell_above = sum(1 for t in sells if t['price'] > fair)
        sell_at = sum(1 for t in sells if t['price'] == fair)
        sell_below = sum(1 for t in sells if t['price'] < fair)
        print(f'  Buys: {buy_below} below fair, {buy_at} at fair, {buy_above} above fair')
        print(f'  Sells: {sell_below} below fair, {sell_at} at fair, {sell_above} above fair')
        bad_buys = sum(t['quantity'] for t in buys if t['price'] > fair)
        bad_sells = sum(t['quantity'] for t in sells if t['price'] < fair)
        print(f'  BAD fills: {bad_buys} units bought above fair, {bad_sells} units sold below fair')

    return len(buys), len(sells)


print()
em_trades = [t for t in trades if t['symbol'] == 'EMERALDS']
tom_trades = [t for t in trades if t['symbol'] == 'TOMATOES']

analyze_product('EMERALDS', em_trades)
print()
analyze_product('TOMATOES', tom_trades)

# Spread analysis from book data
print()
print('=' * 55)
print('  BOOK SPREAD ANALYSIS')
print('=' * 55)
for prod in ['EMERALDS', 'TOMATOES']:
    spreads = [v['spread'] for k, v in book_at.items() if k[1] == prod and v['spread'] is not None]
    if spreads:
        avg_s = sum(spreads) / len(spreads)
        min_s = min(spreads)
        max_s = max(spreads)
        from collections import Counter
        spread_dist = Counter(int(s) for s in spreads)
        print(f'{prod}:')
        print(f'  Avg spread: {avg_s:.2f}, Min: {min_s:.0f}, Max: {max_s:.0f}')
        print(f'  Distribution: {dict(sorted(spread_dist.items()))}')
        print()
