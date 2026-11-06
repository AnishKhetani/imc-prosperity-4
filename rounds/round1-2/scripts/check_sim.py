import json, csv, io
with open('logs/42447/42447.json') as f:
    data = json.load(f)
print(f'Total PnL: {data["profit"]:.2f}')
print(f'Status: {data["status"]}')

rows = list(csv.DictReader(io.StringIO(data['activitiesLog']), delimiter=';'))
products = set(r['product'] for r in rows)
for p in sorted(products):
    pr = [r for r in rows if r['product'] == p]
    final_pnl = float(pr[-1]['profit_and_loss'])
    print(f'  {p}: {final_pnl:.2f}')

tom = [r for r in rows if r['product'] == 'TOMATOES']
prev = 0
tom_fills = 0
for r in tom:
    pnl = float(r['profit_and_loss'])
    if pnl != prev:
        tom_fills += 1
    prev = pnl
print(f'  TOMATOES fills: {tom_fills}')

em = [r for r in rows if r['product'] == 'EMERALDS']
prev = 0
em_fills = 0
for r in em:
    pnl = float(r['profit_and_loss'])
    if pnl != prev:
        em_fills += 1
    prev = pnl
print(f'  EMERALDS fills: {em_fills}')
