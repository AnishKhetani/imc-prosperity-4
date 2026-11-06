"""Forensic analysis of live log 370648 (v6 submission)."""
import json, csv, io
from pathlib import Path
from collections import defaultdict

data = json.loads(Path('logs/370648/370648.json').read_text(encoding='utf-8'))
print(f"Round: {data['round']}, Status: {data['status']}, Total profit: {data['profit']:.2f}")

act_log = data.get('activitiesLog', '')
reader = csv.DictReader(io.StringIO(act_log), delimiter=';')

final_pnl = {}
mid_prices = defaultdict(list)
pnl_series = defaultdict(list)
for row in reader:
    prod = row['product']
    try:
        pnl = float(row['profit_and_loss'])
        ts  = int(row['timestamp'])
        mid = float(row['mid_price'])
        final_pnl[prod] = pnl
        pnl_series[prod].append((ts, pnl))
        mid_prices[prod].append((ts, mid))
    except:
        pass

print('\n=== FINAL PnL per product ===')
total = 0
for prod, pnl in sorted(final_pnl.items(), key=lambda x: -abs(x[1])):
    print(f'  {prod:<28}  {pnl:>10,.2f}')
    total += pnl
print(f'  {"TOTAL":<28}  {total:>10,.2f}')

# HYDROGEL detail
HYDRO = 'HYDROGEL_PACK'
if HYDRO in mid_prices:
    hm = mid_prices[HYDRO]
    hp = pnl_series[HYDRO]
    print(f'\n=== HYDROGEL mid (start={hm[0][1]:.0f}, end={hm[-1][1]:.0f}, '
          f'min={min(m for _,m in hm):.0f}, max={max(m for _,m in hm):.0f}) ===')
    for i in range(0, len(hp), max(1, len(hp)//10)):
        ts, pnl = hp[i]
        mid = hm[i][1]
        print(f'  ts={ts:>6}  pnl={pnl:>9,.1f}  mid={mid:.0f}')

# VELVET detail
VEL = 'VELVETFRUIT_EXTRACT'
if VEL in mid_prices:
    vm = mid_prices[VEL]
    vp = pnl_series[VEL]
    print(f'\n=== VELVET mid (start={vm[0][1]:.1f}, end={vm[-1][1]:.1f}, '
          f'min={min(m for _,m in vm):.1f}, max={max(m for _,m in vm):.1f}) ===')
    for i in range(0, len(vp), max(1, len(vp)//10)):
        ts, pnl = vp[i]
        mid = vm[i][1]
        print(f'  ts={ts:>6}  pnl={pnl:>9,.1f}  mid={mid:.1f}')

# Voucher detail
print('\n=== VOUCHER PnL ===')
for k in [4000,4500,5000,5100,5200,5300,5400,5500,6000,6500]:
    sym = f'VEV_{k}'
    if sym in final_pnl:
        print(f'  {sym}: {final_pnl[sym]:.2f}')

# Final positions
pos = data.get('positions', [])
print('\n=== FINAL POSITIONS ===')
for p in pos:
    sym, qty = p['symbol'], p['quantity']
    if qty != 0:
        print(f'  {sym:<28}  {qty:>8}')

# Own trades: parse market trades for SUBMISSION activity
market_trades = data.get('marketTrades', [])
if market_trades:
    sub_trades = [t for t in market_trades
                  if t.get('buyer') == 'SUBMISSION' or t.get('seller') == 'SUBMISSION']
    by_sym = defaultdict(list)
    for t in sub_trades:
        by_sym[t['symbol']].append(t)
    print('\n=== SUBMISSION TRADES BY SYMBOL ===')
    for sym, trades in sorted(by_sym.items()):
        buys  = sum(t['quantity'] for t in trades if t.get('buyer')  == 'SUBMISSION')
        sells = sum(t['quantity'] for t in trades if t.get('seller') == 'SUBMISSION')
        print(f'  {sym:<28}  bought={buys:>5}  sold={sells:>5}  net={buys-sells:>+6}')
else:
    print('\n(no marketTrades key in log)')

# graphLog last entries
graph = data.get('graphLog', '')
glines = [l for l in graph.strip().split('\n') if l.strip()]
print(f'\nGraph log lines: {len(glines)}')
print('Last 5 graph entries:')
for l in glines[-5:]:
    print(' ', l)
