import json
from collections import Counter, defaultdict

with open('logs/42183/42183.json') as f:
    data = json.load(f)

print('=== SUMMARY ===')
print(f'Round: {data["round"]}')
print(f'Status: {data["status"]}')
print(f'Total Profit: {data["profit"]}')
print()
print('=== FINAL POSITIONS ===')
for p in data['positions']:
    print(f'  {p}')
print()

# Parse activities log
lines = data['activitiesLog'].strip().split('\n')
print(f'Activities log: {len(lines)} lines')
header = lines[0]
print(f'Header: {header}')
fields = header.split(';')

products = set()
days = set()
rows = []
for line in lines[1:]:
    parts = line.split(';')
    if len(parts) >= len(fields):
        row = dict(zip(fields, parts))
        rows.append(row)
        days.add(row['day'])
        products.add(row['product'])

print(f'Days: {sorted(days)}')
print(f'Products: {sorted(products)}')
print()

# Count lines per product per day
day_prod = Counter()
for row in rows:
    day_prod[(row['day'], row['product'])] += 1
print('Lines per (day, product):')
for k in sorted(day_prod.keys()):
    print(f'  {k}: {day_prod[k]}')
print()

# PnL by product at end of each day
print('=== PnL OVER TIME (by product) ===')
pnl_by_product = defaultdict(list)
for row in rows:
    pnl = float(row['profit_and_loss'])
    ts = int(row['timestamp'])
    day = row['day']
    product = row['product']
    pnl_by_product[product].append((day, ts, pnl))

for product in sorted(pnl_by_product.keys()):
    entries = pnl_by_product[product]
    if entries:
        last = entries[-1]
        first_nonzero = None
        for e in entries:
            if e[2] != 0:
                first_nonzero = e
                break
        print(f'{product}:')
        print(f'  Final PnL: {last[2]}')
        print(f'  First non-zero: {first_nonzero}')
        # PnL at various checkpoints
        for frac in [0.25, 0.5, 0.75, 1.0]:
            idx = min(int(len(entries) * frac) - 1, len(entries) - 1)
            if idx >= 0:
                e = entries[idx]
                print(f'  At {frac*100:.0f}%: day={e[0]} ts={e[1]} pnl={e[2]}')
print()

# Order book analysis - spreads and mid prices
print('=== ORDER BOOK STATS (by product) ===')
for product in sorted(products):
    prod_rows = [r for r in rows if r['product'] == product]
    spreads = []
    mids = []
    for r in prod_rows:
        try:
            bid1 = float(r['bid_price_1']) if r['bid_price_1'] else None
            ask1 = float(r['ask_price_1']) if r['ask_price_1'] else None
            mid = float(r['mid_price']) if r['mid_price'] else None
            if bid1 and ask1:
                spreads.append(ask1 - bid1)
            if mid:
                mids.append(mid)
        except:
            pass
    if spreads:
        print(f'{product}:')
        print(f'  Spread: min={min(spreads)}, max={max(spreads)}, avg={sum(spreads)/len(spreads):.2f}')
        print(f'  Mid: min={min(mids):.1f}, max={max(mids):.1f}, avg={sum(mids)/len(mids):.1f}')
        print(f'  Ticks: {len(prod_rows)}')
print()

# Parse the log file for trade details
print('=== LOG FILE ANALYSIS ===')
with open('logs/42183/42183.log') as f:
    log_data = f.read()

# The log might be structured - let's see
print(f'Log file size: {len(log_data)} bytes')
# Try to find trade executions
trade_count = log_data.count('TRADE')
fill_count = log_data.count('fill')
buy_count = log_data.count('BUY')
sell_count = log_data.count('SELL')
print(f'Occurrences: TRADE={trade_count}, fill={fill_count}, BUY={buy_count}, SELL={sell_count}')

# Print first 2000 chars of log
print()
print('=== LOG (first 2000 chars) ===')
print(log_data[:2000])
print()
print('=== LOG (last 2000 chars) ===')
print(log_data[-2000:])
