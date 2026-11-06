import json
from collections import defaultdict

with open(r'.\logs\372772\372772.json', encoding='utf-8') as f:
    d = json.load(f)

print('Round:', d.get('round'))
print('Status:', d.get('status'))
print('Total profit:', d.get('profit'))

print('\nFinal positions:')
for p in d.get('positions', []):
    if p['symbol'] != 'XIRECS':
        print('  %s: %d' % (p['symbol'], p['quantity']))

# Parse graphLog for PnL timeline
graph = d.get('graphLog', '')
lines = graph.strip().split('\n')[1:]  # skip header
pts = [(int(r.split(';')[0]), float(r.split(';')[1])) for r in lines if r]
print('\nTotal ticks: %d' % len(pts))
min_pnl, min_ts = min((v, t) for t, v in pts)
max_pnl, max_ts = max((v, t) for t, v in pts)
print('Min PnL: %.1f at ts=%d' % (min_pnl, min_ts))
print('Max PnL: %.1f at ts=%d' % (max_pnl, max_ts))
print('Final PnL: %.1f' % pts[-1][1])

# Find biggest drawdowns
print('\nLargest negative PnL points:')
negatives = sorted([(v, t) for t, v in pts if v < -500], key=lambda x: x[0])[:10]
for v, t in negatives:
    print('  ts=%d: %.1f' % (t, v))

# Find large drops (drawdown periods)
print('\nBig drop events (>500 in single tick):')
for i in range(1, len(pts)):
    drop = pts[i][1] - pts[i-1][1]
    if drop < -400:
        print('  ts=%d->%d: drop=%.1f (from %.1f to %.1f)' % (
            pts[i-1][0], pts[i][0], drop, pts[i-1][1], pts[i][1]))

# Parse activitiesLog for per-product PnL
acts = d.get('activitiesLog', '')
act_lines = acts.strip().split('\n')
# Format: day;ts;product;bid1;bid1v;...;mid;pnl
product_pnl = defaultdict(list)
for line in act_lines[1:]:
    parts = line.split(';')
    if len(parts) >= 17:
        try:
            ts = int(parts[1])
            prod = parts[2]
            pnl = float(parts[16])
            product_pnl[prod].append((ts, pnl))
        except Exception:
            pass

print('\nPer-product final PnL:')
for prod, data in sorted(product_pnl.items()):
    if data:
        final = data[-1][1]
        min_p = min(v for _, v in data)
        max_p = max(v for _, v in data)
        print('  %-30s  final=%8.1f  min=%8.1f  max=%8.1f' % (prod, final, min_p, max_p))

# Analyze worst period: ts 88000-92000 where PnL drops to -3352
print('\n=== WORST DRAWDOWN DETAIL (ts 88000-92000) ===')
worst_ts = [t for t, v in pts if 87000 <= t <= 93000]
for t, v in pts:
    if 87000 <= t <= 93000 and t % 1000 == 0:
        print('  ts=%d: cumulative_pnl=%.1f' % (t, v))

# For each product, show PnL delta during the worst period
print('\nPer-product PnL during worst period (ts 87000 to 93000):')
for prod, data in sorted(product_pnl.items()):
    before = [v for t, v in data if t <= 87000]
    after = [v for t, v in data if t <= 93000]
    if before and after:
        delta = after[-1] - before[-1]
        if abs(delta) > 10:
            print('  %-30s  delta=%.1f  (from %.1f to %.1f)' % (prod, delta, before[-1], after[-1]))

# Also check early drawdown ts 0-5000
print('\nPer-product PnL during early drawdown (ts 0 to 5000):')
for prod, data in sorted(product_pnl.items()):
    start = [v for t, v in data if t <= 100]
    end_5k = [v for t, v in data if t <= 5000]
    if start and end_5k:
        delta = end_5k[-1] - start[-1]
        if abs(delta) > 20:
            print('  %-30s  delta=%.1f  (from %.1f to %.1f)' % (prod, delta, start[-1], end_5k[-1]))
