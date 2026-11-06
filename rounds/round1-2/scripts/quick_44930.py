import json, csv, io
from collections import defaultdict

with open('logs/44930/44930.json','r') as f:
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
    print(f"\n{product}: Final PnL = {final_pnl:.2f}, Ticks = {len(prows)}")

    # PnL change analysis
    prev = 0
    changes = []
    for r in prows:
        p = float(r['profit_and_loss'])
        if abs(p - prev) > 0.001:
            changes.append((int(r['timestamp']), p - prev, p))
        prev = p
    gains = [c for _,c,_ in changes if c > 0]
    losses = [c for _,c,_ in changes if c < 0]
    print(f"  PnL changes: {len(changes)}, gains={len(gains)} (total={sum(gains):.1f}), losses={len(losses)} (total={sum(losses):.1f})")

with open('logs/44930/44930.log','r') as f:
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
    print(f"\n{sym}: {len(tlist)} trades")
    print(f"  Buys: {len(buys)} trades, {buy_vol} vol")
    print(f"  Sells: {len(sells)} trades, {sell_vol} vol")
    if buys:
        avg_buy = sum(t['price']*t['quantity'] for t in buys)/buy_vol
        print(f"  Avg buy: {avg_buy:.2f}")
    if sells:
        avg_sell = sum(t['price']*t['quantity'] for t in sells)/sell_vol
        print(f"  Avg sell: {avg_sell:.2f}")
    pos = 0
    for t in tlist:
        if t['buyer'] == 'SUBMISSION': pos += t['quantity']
        else: pos -= t['quantity']
    print(f"  Final pos: {pos}")

    # Show trade prices
    buy_prices = sorted(set(t['price'] for t in buys))
    sell_prices = sorted(set(t['price'] for t in sells))
    print(f"  Buy prices: {buy_prices[:20]}")
    print(f"  Sell prices: {sell_prices[:20]}")

    # First 20 trades
    print(f"  First 20 trades:")
    for t in tlist[:20]:
        side = 'BUY' if t['buyer'] == 'SUBMISSION' else 'SELL'
        print(f"    t={t['timestamp']:6d}: {side:4s} {t['quantity']}x @ {t['price']:.0f}")

    # Last 10 trades
    print(f"  Last 10 trades:")
    for t in tlist[-10:]:
        side = 'BUY' if t['buyer'] == 'SUBMISSION' else 'SELL'
        print(f"    t={t['timestamp']:6d}: {side:4s} {t['quantity']}x @ {t['price']:.0f}")
