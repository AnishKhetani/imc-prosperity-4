"""
Deep dive into 370648: voucher spreads, mid prices, and own-trade activity.
Compares with 369364 to isolate why VELVET dropped from +2334 to +164.
"""
import json, csv, io
from pathlib import Path
from collections import defaultdict

def parse_log(path):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    act_log = data.get('activitiesLog', '')
    reader = csv.DictReader(io.StringIO(act_log), delimiter=';')
    rows = defaultdict(list)
    for row in reader:
        prod = row['product']
        try:
            ts = int(row['timestamp'])
            mid = float(row['mid_price'])
            pnl = float(row['profit_and_loss'])
            bb1 = float(row['bid_price_1']) if row['bid_price_1'] else None
            ba1 = float(row['ask_price_1']) if row['ask_price_1'] else None
            bv1 = int(row['bid_volume_1']) if row['bid_volume_1'] else 0
            av1 = int(row['ask_volume_1']) if row['ask_volume_1'] else 0
            rows[prod].append({'ts': ts, 'mid': mid, 'pnl': pnl,
                                'bb': bb1, 'ba': ba1, 'bv': bv1, 'av': av1})
        except:
            pass
    return data, rows

data4, rows4 = parse_log('logs/369364/369364.json')
data6, rows6 = parse_log('logs/370648/370648.json')

# -- Compare VELVET tick-by-tick mid prices between v4 and v6 --
print('=== VELVET mid price comparison ===')
print(f'{"ts":>8}  {"v4 mid":>10}  {"v6 mid":>10}  {"v4 pnl":>10}  {"v6 pnl":>10}')
v4v = rows4.get('VELVETFRUIT_EXTRACT', [])
v6v = rows6.get('VELVETFRUIT_EXTRACT', [])
v4d = {r['ts']: r for r in v4v}
v6d = {r['ts']: r for r in v6v}
all_ts = sorted(set(v4d.keys()) | set(v6d.keys()))
for ts in all_ts[::100]:
    r4 = v4d.get(ts, {})
    r6 = v6d.get(ts, {})
    m4 = r4.get('mid', '-')
    m6 = r6.get('mid', '-')
    p4 = r4.get('pnl', '-')
    p6 = r6.get('pnl', '-')
    print(f'{ts:>8}  {str(m4):>10}  {str(m6):>10}  {str(p4):>10}  {str(p6):>10}')

# -- Show all voucher spreads at selected timestamps (v6) --
print('\n=== VOUCHER market data in v6 (370648) at selected timestamps ===')
strikes = [4000,4500,5000,5100,5200,5300,5400,5500,6000,6500]
velvet_mids = {r['ts']: r['mid'] for r in rows6.get('VELVETFRUIT_EXTRACT', [])}
for ts_sel in [0, 10000, 30000, 50000, 70000, 90000, 99900]:
    S = velvet_mids.get(ts_sel, None)
    print(f'\n  ts={ts_sel}  VELVET_mid={S}')
    for k in strikes:
        sym = f'VEV_{k}'
        rd = {r['ts']: r for r in rows6.get(sym, [])}
        r = rd.get(ts_sel, None)
        if r:
            spread = (r['ba'] - r['bb']) if (r['bb'] and r['ba']) else None
            print(f'    {sym}: bb={r["bb"]}({r["bv"]}) ba={r["ba"]}({r["av"]}) '
                  f'mid={r["mid"]:.2f} spread={spread}  pnl={r["pnl"]:.2f}')
        else:
            print(f'    {sym}: no data at this ts')

# -- Show VELVET bid/ask in both logs at the critical ts~58000-60000 window --
print('\n=== VELVET order book at ts 55000-62000 ===')
print(f'{"ts":>8}  {"v4 bb":>7}  {"v4 ba":>7}  {"v4 mid":>8}  {"v6 bb":>7}  {"v6 ba":>7}  {"v6 mid":>8}')
for ts in range(55000, 62100, 100):
    r4 = v4d.get(ts, {})
    r6 = v6d.get(ts, {})
    if r4 or r6:
        print(f'{ts:>8}  {str(r4.get("bb","-")):>7}  {str(r4.get("ba","-")):>7}  '
              f'{str(r4.get("mid","-")):>8}  '
              f'{str(r6.get("bb","-")):>7}  {str(r6.get("ba","-")):>7}  '
              f'{str(r6.get("mid","-")):>8}')
