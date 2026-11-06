import json, csv, io
from collections import defaultdict

# === 44953 Analysis ===
with open('logs/44953/44953.json','r') as f:
    data = json.load(f)
print(f"Status: {data['status']}")
print(f"Total Profit: {data['profit']}")

reader = csv.DictReader(io.StringIO(data['activitiesLog']), delimiter=';')
rows = list(reader)
by_product = defaultdict(list)
for row in rows:
    by_product[row['product']].append(row)

for product in sorted(by_product.keys()):
    prows = by_product[product]
    final_pnl = float(prows[-1]['profit_and_loss'])
    print(f"\n{'='*60}")
    print(f"{product}: PnL={final_pnl:.2f}, Ticks={len(prows)}")

    # Spread stats
    spreads = []
    mids = []
    for r in prows:
        bp1 = float(r['bid_price_1']) if r.get('bid_price_1') else None
        ap1 = float(r['ask_price_1']) if r.get('ask_price_1') else None
        if bp1 and ap1:
            spreads.append(ap1 - bp1)
            mids.append((bp1 + ap1) / 2)
    if spreads:
        spread_dist = defaultdict(int)
        for s in spreads:
            spread_dist[s] += 1
        print(f"  Spread: mean={sum(spreads)/len(spreads):.2f}")
        for s in sorted(spread_dist.keys()):
            pct = spread_dist[s] / len(spreads) * 100
            if pct > 0.5:
                print(f"    {s:6.0f}: {spread_dist[s]:5d} ({pct:5.1f}%)")

    # PnL trajectory
    prev = 0
    changes = []
    for r in prows:
        p = float(r['profit_and_loss'])
        if abs(p - prev) > 0.001:
            changes.append((int(r['timestamp']), p - prev, p))
        prev = p
    gains = [c for _,c,_ in changes if c > 0]
    losses = [c for _,c,_ in changes if c < 0]
    print(f"  PnL events: {len(changes)}")
    if gains:
        print(f"  Gains: {len(gains)}, total={sum(gains):.1f}, avg={sum(gains)/len(gains):.2f}")
    if losses:
        print(f"  Losses: {len(losses)}, total={sum(losses):.1f}, avg={sum(losses)/len(losses):.2f}")
    if gains and losses:
        print(f"  Profit factor: {sum(gains)/abs(sum(losses)):.2f}")

# Trade history
with open('logs/44953/44953.log','r') as f:
    ldata = json.load(f)
trades = ldata['tradeHistory']
by_sym = defaultdict(list)
for t in trades:
    by_sym[t['symbol']].append(t)

for sym in sorted(by_sym.keys()):
    tlist = by_sym[sym]
    buys = [t for t in tlist if t['buyer'] == 'SUBMISSION']
    sells = [t for t in tlist if t['seller'] == 'SUBMISSION']
    buy_vol = sum(t['quantity'] for t in buys)
    sell_vol = sum(t['quantity'] for t in sells)
    print(f"\n{sym} Trades: {len(tlist)}")
    print(f"  Buys: {len(buys)} ({buy_vol} vol), Sells: {len(sells)} ({sell_vol} vol)")
    if buys:
        avg_buy = sum(t['price']*t['quantity'] for t in buys)/buy_vol
        print(f"  Avg buy: {avg_buy:.2f}")
    if sells:
        avg_sell = sum(t['price']*t['quantity'] for t in sells)/sell_vol
        print(f"  Avg sell: {avg_sell:.2f}")
    pos = 0
    max_pos = 0
    min_pos = 0
    for t in tlist:
        if t['buyer'] == 'SUBMISSION': pos += t['quantity']
        else: pos -= t['quantity']
        max_pos = max(max_pos, pos)
        min_pos = min(min_pos, pos)
    print(f"  Position: final={pos}, max={max_pos}, min={min_pos}")
    print(f"  Buy prices: {sorted(set(t['price'] for t in buys))}")
    print(f"  Sell prices: {sorted(set(t['price'] for t in sells))}")

    # First 10 and last 10
    print(f"  First 10:")
    for t in tlist[:10]:
        side = 'BUY' if t['buyer'] == 'SUBMISSION' else 'SELL'
        print(f"    t={t['timestamp']:6d}: {side:4s} {t['quantity']}x@{t['price']:.0f}")
    print(f"  Last 10:")
    for t in tlist[-10:]:
        side = 'BUY' if t['buyer'] == 'SUBMISSION' else 'SELL'
        print(f"    t={t['timestamp']:6d}: {side:4s} {t['quantity']}x@{t['price']:.0f}")

# === Compare with 44861 baseline ===
print(f"\n{'='*60}")
print("COMPARISON: 44861 vs 44953")
for sim in ['44861', '44953']:
    with open(f'logs/{sim}/{sim}.json','r') as f:
        d = json.load(f)
    reader = csv.DictReader(io.StringIO(d['activitiesLog']), delimiter=';')
    rows = list(reader)
    bp = defaultdict(list)
    for row in rows:
        bp[row['product']].append(row)
    parts = []
    for p in sorted(bp.keys()):
        parts.append(f"{p}={float(bp[p][-1]['profit_and_loss']):.0f}")
    print(f"  {sim}: total={d['profit']:.0f}, {', '.join(parts)}")
