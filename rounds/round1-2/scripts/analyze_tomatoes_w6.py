"""TOMATOES WIDTH=6 feasibility: check spread at fill ticks"""
import csv, io, json
from collections import Counter

with open('logs/42400/42400.json') as f:
    data = json.load(f)
rows = list(csv.DictReader(io.StringIO(data['activitiesLog']), delimiter=';'))
tom = [r for r in rows if r['product'] == 'TOMATOES']

prev_pnl = 0
fills = []
for r in tom:
    pnl = float(r['profit_and_loss'])
    if pnl != prev_pnl:
        b1 = int(r['bid_price_1'])
        a1 = int(r['ask_price_1'])
        spread = a1 - b1
        fills.append({'ts': int(r['timestamp']), 'delta': pnl - prev_pnl,
                       'b1': b1, 'a1': a1, 'spread': spread})
    prev_pnl = pnl

print(f'TOMATOES PnL-change events: {len(fills)}')
unique_ts = set(f['ts'] for f in fills)
print(f'Unique timestamps: {len(unique_ts)}')

spread_dist = Counter(f['spread'] for f in fills)
print(f'Spread distribution at fill ticks: {dict(sorted(spread_dist.items()))}')

# For WIDTH=6: our bid=fair-6, ask=fair+6
# Bot spread must be > 12 (strictly) for our orders to be inside bot quotes
# If bot spread = 12: our bid might be AT bot bid, ask AT bot ask → priority issue
# If bot spread > 12: safe

thin = [f for f in fills if f['spread'] < 12]
at_12 = [f for f in fills if f['spread'] == 12]
safe = [f for f in fills if f['spread'] > 12]

print(f'\nSpread < 12 (unsafe for WIDTH=6): {len(thin)} fills')
print(f'Spread == 12 (borderline): {len(at_12)} fills')
print(f'Spread > 12 (safe for WIDTH=6): {len(safe)} fills')

# But actually TOMATOES spread is bot_ask - bot_bid
# Our fair value is EMA-based, not necessarily mid
# At WIDTH=6 our quotes: fair-6 and fair+6
# For our BID=fair-6 to be inside (above bot bid): fair-6 > bot_bid → fair > bot_bid+6
# For our ASK=fair+6 to be inside (below bot ask): fair+6 < bot_ask → fair < bot_ask-6
# So we need: bot_bid+6 < fair < bot_ask-6
# i.e., bot_ask - bot_bid > 12 AND fair is NOT too close to either edge

# Check margin per fill
margins = []
for f in fills:
    mid = (f['b1'] + f['a1']) / 2  # approximate fair
    bid_margin = mid - 6 - f['b1']  # how far our bid is above bot bid
    ask_margin = f['a1'] - (mid + 6)  # how far our ask is below bot ask
    min_margin = min(bid_margin, ask_margin)
    margins.append(min_margin)

print(f'\nMargin analysis (how far inside bot quotes, in ticks):')
margin_dist = Counter(m for m in margins)
for m in sorted(margin_dist):
    print(f'  margin={m:.1f}: {margin_dist[m]} fills')

tight_fills = [f for f, m in zip(fills, margins) if m <= 0]
print(f'\nFills with margin <= 0 (AT or OUTSIDE bot quotes): {len(tight_fills)}')
for f in tight_fills[:10]:
    mid = (f['b1'] + f['a1']) / 2
    our_bid = mid - 6
    our_ask = mid + 6
    print(f'  t={f["ts"]} spread={f["spread"]} b1={f["b1"]} a1={f["a1"]} mid={mid} our_bid={our_bid} our_ask={our_ask}')

# But actually, fair != mid. Fair = EMA + imbalance adjustment
# This makes the margin even more uncertain. We'd need to reconstruct EMA values.
# For a rough estimate, this is good enough.

# Also check: PnL per fill at WIDTH=5 vs what WIDTH=6 would give
total_pnl_w5 = sum(f['delta'] for f in fills)
print(f'\nTotal TOMATOES PnL at WIDTH=5: {total_pnl_w5:.2f}')
print(f'If same fills at WIDTH=6: ~{total_pnl_w5 * 6/5:.2f} (rough estimate)')
print(f'Improvement: ~+{total_pnl_w5 * 1/5:.0f} PnL')

# BUT: this only holds if no fills are lost
# The risk is that at WIDTH=6, some fills become impossible because our quote
# lands at or outside the bot's quote level, and we lose to time priority
# This is why platform testing is needed
