"""Analyze live submission log 369364."""
import json, csv, io
from pathlib import Path
from collections import defaultdict

data = json.loads(Path('logs/369364/369364.json').read_text(encoding='utf-8'))
print(f"Round: {data['round']}, Status: {data['status']}, Total profit: {data['profit']:.2f}")

act_log = data.get('activitiesLog', '')
reader = csv.DictReader(io.StringIO(act_log), delimiter=';')

final_pnl = {}
all_pnl = defaultdict(list)
mid_prices = defaultdict(list)
for row in reader:
    prod = row['product']
    try:
        pnl = float(row['profit_and_loss'])
        final_pnl[prod] = pnl
        all_pnl[prod].append(pnl)
        mid_prices[prod].append((int(row['timestamp']), float(row['mid_price'])))
    except:
        pass

print('\n=== FINAL PnL per product ===')
total = 0
for prod, pnl in sorted(final_pnl.items(), key=lambda x: -abs(x[1])):
    print(f'  {prod:<25}  {pnl:>10,.2f}')
    total += pnl
print(f'  {"TOTAL":<25}  {total:>10,.2f}')

# HYDROGEL mid-price evolution
print('\n=== HYDROGEL mid_price (every 10k ts) ===')
hydrogel_mids = mid_prices.get('HYDROGEL_PACK', [])
for ts, mp in hydrogel_mids[::100]:
    print(f'  ts={ts:>6}  mid={mp:.1f}')
if hydrogel_mids:
    print(f'  start: {hydrogel_mids[0][1]:.1f}, end: {hydrogel_mids[-1][1]:.1f}')
    print(f'  min: {min(m for _,m in hydrogel_mids):.1f}, max: {max(m for _,m in hydrogel_mids):.1f}')

# VELVET mid price evolution
print('\n=== VELVET mid_price at start/end ===')
velvet_mids = mid_prices.get('VELVETFRUIT_EXTRACT', [])
if velvet_mids:
    print(f'  start: ts={velvet_mids[0][0]} mid={velvet_mids[0][1]:.1f}')
    print(f'  end:   ts={velvet_mids[-1][0]} mid={velvet_mids[-1][1]:.1f}')
    print(f'  min={min(m for _,m in velvet_mids):.1f}, max={max(m for _,m in velvet_mids):.1f}')

# Parse graphLog for position data
graph = data.get('graphLog', '')
glines = [l for l in graph.strip().split('\n') if l.strip()]
print(f'\nGraph log lines: {len(glines)}')
if glines:
    print('Header:', glines[0])
    print('Last 15 entries:')
    for l in glines[-15:]:
        print(' ', l)

# Positions at end
positions = data.get('positions', {})
print('\n=== FINAL POSITIONS ===')
for k, v in sorted(positions.items()):
    if v != 0:
        print(f'  {k:<25}  {v:>6}')
