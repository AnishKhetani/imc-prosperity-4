import json

with open('logs/42183/42183.log') as f:
    log = json.load(f)

log_entries = log.get('logs', [])

# Look for WARN entries
warn_entries = []
for entry in log_entries:
    ll = entry.get('lambdaLog', '')
    if 'WARN' in ll:
        ts = entry.get('timestamp')
        # Find the WARN message
        warn_idx = ll.find('WARN')
        context = ll[max(0, warn_idx-20):warn_idx+200]
        warn_entries.append((ts, context))

print(f'Total WARN entries: {len(warn_entries)}')
print()

# Print first 20 warnings
for ts, ctx in warn_entries[:20]:
    print(f'  ts={ts}: ...{ctx[:150]}...')
print()

# Count warning types
buy_warns = sum(1 for _, c in warn_entries if 'buy' in c.lower())
sell_warns = sum(1 for _, c in warn_entries if 'sell' in c.lower())
emerald_warns = sum(1 for _, c in warn_entries if 'EMERALDS' in c)
tomato_warns = sum(1 for _, c in warn_entries if 'TOMATOES' in c)

print(f'Buy-side warnings: {buy_warns}')
print(f'Sell-side warnings: {sell_warns}')
print(f'EMERALDS warnings: {emerald_warns}')
print(f'TOMATOES warnings: {tomato_warns}')
print()

# Parse a few WARN entries to understand the numbers
for ts, ctx in warn_entries[:5]:
    print(f'\n--- ts={ts} ---')
    print(ctx[:300])
