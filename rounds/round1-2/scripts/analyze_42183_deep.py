import json
from collections import defaultdict

# Parse log to check for validation failures and order patterns
with open('logs/42183/42183.log') as f:
    log = json.load(f)

# Parse trade history
trades = log.get('tradeHistory', [])
our_buys = [t for t in trades if t.get('buyer') == 'SUBMISSION']
our_sells = [t for t in trades if t.get('seller') == 'SUBMISSION']

# Group by product
for product in ['EMERALDS', 'TOMATOES']:
    buys = sorted([t for t in our_buys if t['symbol'] == product], key=lambda t: t['timestamp'])
    sells = sorted([t for t in our_sells if t['symbol'] == product], key=lambda t: t['timestamp'])
    
    print(f'=== {product} TRADE TIMELINE ===')
    all_trades = sorted(buys + sells, key=lambda t: t['timestamp'])
    pos = 0
    for t in all_trades:
        if t.get('buyer') == 'SUBMISSION':
            pos += t['quantity']
            side = 'BUY '
        else:
            pos -= t['quantity']
            side = 'SELL'
        print(f'  ts={t["timestamp"]:>6} {side} {t["quantity"]:>3} @ {t["price"]:>8.1f}  pos={pos:>+4}')
    print()

# Analyze gaps between fills
print('=== FILL GAPS (ticks between fills) ===')
for product in ['EMERALDS', 'TOMATOES']:
    prod_trades = sorted([t for t in trades if t['symbol'] == product and 
                          (t.get('buyer') == 'SUBMISSION' or t.get('seller') == 'SUBMISSION')],
                         key=lambda t: t['timestamp'])
    if len(prod_trades) > 1:
        gaps = [(prod_trades[i+1]['timestamp'] - prod_trades[i]['timestamp']) 
                for i in range(len(prod_trades)-1)]
        avg_gap = sum(gaps) / len(gaps)
        print(f'{product}: avg gap={avg_gap:.0f} ticks ({avg_gap/100:.0f} timestamps)')
        print(f'  min gap={min(gaps)}, max gap={max(gaps)}')
        print(f'  fills per 10000 timestamps: {10000 / avg_gap * 100:.1f}')
    print()

# Check: how many ticks have tight spreads for TOMATOES?
with open('logs/42183/42183.json') as f:
    data = json.load(f)

lines = data['activitiesLog'].strip().split('\n')
header = lines[0].split(';')

tight_ticks = defaultdict(int)
for line in lines[1:]:
    parts = line.split(';')
    if len(parts) >= len(header):
        row = dict(zip(header, parts))
        if row['product'] == 'TOMATOES' and row['bid_price_1'] and row['ask_price_1']:
            spread = float(row['ask_price_1']) - float(row['bid_price_1'])
            if spread <= 6:
                tight_ticks['<= 6'] += 1
            elif spread <= 8:
                tight_ticks['<= 8'] += 1
            elif spread <= 10:
                tight_ticks['<= 10'] += 1
            elif spread <= 14:
                tight_ticks['<= 14'] += 1
            else:
                tight_ticks['> 14'] += 1

print('=== TOMATOES SPREAD DISTRIBUTION ===')
for k in sorted(tight_ticks.keys()):
    print(f'  {k}: {tight_ticks[k]} ticks ({tight_ticks[k]/20:.1f}%)')

# Check OUR order sizes in the log
log_entries = log.get('logs', [])
print(f'\n=== LOG ENTRIES: {len(log_entries)} total ===')

# Look for WARNING messages (from validation failures)
warn_count = 0
empty_count = 0
for entry in log_entries:
    ll = entry.get('lambdaLog', '')
    if 'WARN' in ll:
        warn_count += 1
    if 'no orders' in ll:
        empty_count += 1

print(f'Entries with WARN: {warn_count}')
print(f'Entries with "no orders": {empty_count}')

# Check the first few entries for order patterns
if log_entries:
    print(f'\nFirst log entry (truncated):')
    first = log_entries[0]
    ll = first.get('lambdaLog', '')
    print(f'  timestamp: {first.get("timestamp")}')
    print(f'  lambdaLog length: {len(ll)}')
    # Try to parse the inner JSON
    try:
        # The lambdaLog is a JSON array string: [[timestamp, traderData, ...], orders, conversions, newTraderData, logs]
        inner = json.loads(ll)
        if isinstance(inner, list) and len(inner) >= 2:
            orders = inner[1]
            print(f'  Orders: {json.dumps(orders)}')
    except:
        pass
