"""Compare 44861 (baseline WIDTH=5 + IMB + DEPTH) vs 45098 (WIDTH=5, no IMB/DEPTH)."""
import json

def load_our_trades(path, sym):
    with open(path) as f:
        d = json.load(f)
    return sorted(
        [t for t in d['tradeHistory']
         if t['symbol'] == sym and (t['buyer'] == 'SUBMISSION' or t['seller'] == 'SUBMISSION')],
        key=lambda x: x['timestamp']
    )

t861 = load_our_trades('logs/44861/44861.log', 'TOMATOES')
t098 = load_our_trades('logs/45098/45098.log', 'TOMATOES')

print(f"44861: {len(t861)} fills, 45098: {len(t098)} fills")

by_ts_861 = {t['timestamp']: t for t in t861}
by_ts_098 = {t['timestamp']: t for t in t098}
all_ts = sorted(set(by_ts_861.keys()) | set(by_ts_098.keys()))

lost = gained = matched = price_shifted = side_flip = 0
for ts in all_ts:
    in_861 = ts in by_ts_861
    in_098 = ts in by_ts_098
    
    def side(t):
        return 'BUY' if t['buyer'] == 'SUBMISSION' else 'SELL'
    
    if in_861 and not in_098:
        lost += 1
        t = by_ts_861[ts]
        print(f"  LOST:    t={ts:6d} {side(t)} {t['quantity']}x @ {t['price']:.0f}")
    elif not in_861 and in_098:
        gained += 1
        t = by_ts_098[ts]
        print(f"  GAINED:  t={ts:6d} {side(t)} {t['quantity']}x @ {t['price']:.0f}")
    else:
        matched += 1
        t1 = by_ts_861[ts]
        t2 = by_ts_098[ts]
        p861, p098 = t1['price'], t2['price']
        s861, s098 = side(t1), side(t2)
        if abs(p861 - p098) > 0.01 or s861 != s098:
            print(f"  CHANGED: t={ts:6d} {s861}@{p861:.0f} -> {s098}@{p098:.0f} (dp={p098 - p861:+.0f})")
            if s861 != s098:
                side_flip += 1
            else:
                price_shifted += 1

print(f"\nSummary: {matched} matched, {lost} lost, {gained} gained, {price_shifted} price-shifted, {side_flip} side-flips")

# PnL comparison
def calc_pnl(trades):
    buy_cost = sum(t['price'] * t['quantity'] for t in trades if t['buyer'] == 'SUBMISSION')
    sell_rev = sum(t['price'] * t['quantity'] for t in trades if t['seller'] == 'SUBMISSION')
    buy_qty = sum(t['quantity'] for t in trades if t['buyer'] == 'SUBMISSION')
    sell_qty = sum(t['quantity'] for t in trades if t['seller'] == 'SUBMISSION')
    net = buy_qty - sell_qty
    return sell_rev - buy_cost + net * 4996.5, buy_qty, sell_qty, net

pnl861, bq861, sq861, n861 = calc_pnl(t861)
pnl098, bq098, sq098, n098 = calc_pnl(t098)
print(f"\n44861: {bq861}b/{sq861}s, net={n861}, PnL={pnl861:.2f}")
print(f"45098: {bq098}b/{sq098}s, net={n098}, PnL={pnl098:.2f}")
print(f"Delta: {pnl098 - pnl861:+.2f}")
