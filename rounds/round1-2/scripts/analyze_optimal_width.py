"""
Determine the maximum safe TOMATOES make width by analyzing the 66 make-fill ticks.

Key question: How deep do bot aggressive orders cross into the spread?
If bots cross to fair±6, WIDTH=6 is safe. If only fair±3, WIDTH=3 is max.

We know WIDTH=2 and WIDTH=3 had identical fill ticks (66 make fills).
The order book (bot side) is identical in both runs.
"""
import json, csv, io
from collections import Counter

def load(sid):
    with open(f'logs/{sid}/{sid}.json') as f:
        d = json.load(f)
    return list(csv.DictReader(io.StringIO(d['activitiesLog']), delimiter=';'))

rows = load(42260)  # Either sim works, market data is identical
tom = [r for r in rows if r['product'] == 'TOMATOES']
em = [r for r in rows if r['product'] == 'EMERALDS']

# Find the 66 make-fill ticks (where PnL differs between WIDTH=2 and WIDTH=3)
rows183 = load(42183)
tom183 = [r for r in rows183 if r['product'] == 'TOMATOES']

def get_fills(rows):
    d = {}; prev = 0.0
    for r in rows:
        ts = int(r['timestamp']); pnl = float(r['profit_and_loss'])
        delta = pnl - prev
        if abs(delta) > 0.001: d[ts] = delta
        prev = pnl
    return d

f260 = get_fills(tom)
f183 = get_fills(tom183)

# The 66 make-fill ticks are where PnL differs
make_fill_ticks = set()
for ts in f260:
    if ts in f183:
        diff = abs(f260[ts] - f183[ts])
        if diff > 0.001:
            make_fill_ticks.add(ts)

print(f"Make-fill ticks: {len(make_fill_ticks)}")

# Build tick lookup for TOMATOES
tom_by_ts = {}
for r in tom:
    tom_by_ts[int(r['timestamp'])] = r

# Also need the PREVIOUS tick's data to see our resting orders
sorted_ticks = sorted(tom_by_ts.keys())
tick_idx = {ts: i for i, ts in enumerate(sorted_ticks)}

print(f"\n{'='*80}")
print(f"MAKE-FILL TICK ANALYSIS")
print(f"{'='*80}")

# For each make-fill tick, show:
# 1. Current tick's order book (which includes our previous-tick resting orders)
# 2. The spread (bot spread, excluding our orders)
# 3. Inferred bot aggressive order price
# 4. Maximum width that would still get filled

# Columns for each make-fill tick:
results = []
for ts in sorted(make_fill_ticks):
    r = tom_by_ts[ts]
    bp1 = int(r['bid_price_1']) if r['bid_price_1'] else None
    ap1 = int(r['ask_price_1']) if r['ask_price_1'] else None
    bp2 = int(r['bid_price_2']) if r['bid_price_2'] else None
    ap2 = int(r['ask_price_2']) if r['ask_price_2'] else None
    bp3 = int(r['bid_price_3']) if r['bid_price_3'] else None
    ap3 = int(r['ask_price_3']) if r['ask_price_3'] else None
    mid = float(r['mid_price'])
    pnl_delta_260 = f260.get(ts, 0)
    pnl_delta_183 = f183.get(ts, 0)
    diff = pnl_delta_260 - pnl_delta_183
    
    # The spread shown in the activity log includes our previous-tick orders
    spread = (ap1 - bp1) if (ap1 and bp1) else None
    
    # Try to identify bot vs our levels
    # Bot levels are typically at regular intervals (symmetric around mid)
    # Our orders would be at fair±WIDTH
    
    results.append({
        'ts': ts,
        'bp1': bp1, 'bp2': bp2, 'bp3': bp3,
        'ap1': ap1, 'ap2': ap2, 'ap3': ap3,
        'mid': mid, 'spread': spread,
        'pnl_260': pnl_delta_260,
        'pnl_183': pnl_delta_183,
        'diff': diff,
        'fill_qty': round(-diff),  # diff = -N where N is units filled
    })

print(f"\n{'TS':>8} | {'Bid1':>5} {'Bid2':>5} {'Bid3':>5} | {'Ask1':>5} {'Ask2':>5} {'Ask3':>5} | {'Mid':>7} {'Sprd':>4} | {'PnL_3':>7} {'PnL_2':>7} {'Diff':>6} {'Qty':>3}")
print("-" * 100)
for r in results:
    print(f"{r['ts']:>8} | {r['bp1'] or '':>5} {r['bp2'] or '':>5} {r['bp3'] or '':>5} | "
          f"{r['ap1'] or '':>5} {r['ap2'] or '':>5} {r['ap3'] or '':>5} | "
          f"{r['mid']:>7.1f} {r['spread'] or '':>4} | "
          f"{r['pnl_183']:>7.2f} {r['pnl_260']:>7.2f} {r['diff']:>6.2f} {r['fill_qty']:>3}")

# Summary stats
print(f"\n{'='*80}")
print(f"SUMMARY")
print(f"{'='*80}")

spread_at_fill = [r['spread'] for r in results if r['spread']]
sp_dist = Counter(spread_at_fill)
print(f"\nSpread distribution at make-fill ticks:")
for s, c in sorted(sp_dist.items()):
    print(f"  Spread={s}: {c} ticks")

qty_dist = Counter(r['fill_qty'] for r in results)
print(f"\nFill quantity distribution:")
for q, c in sorted(qty_dist.items()):
    print(f"  Qty={q}: {c} ticks")

# Determine bot levels on make-fill ticks
# If spread is 13-14, the book shows pure bot levels (no our orders)
# If spread is 5-9, our orders are in the book
print(f"\nTicks with narrow spread (our orders in book): {sum(1 for s in spread_at_fill if s <= 10)}")
print(f"Ticks with wide spread (pure bot book): {sum(1 for s in spread_at_fill if s > 10)}")

# For wide-spread ticks, the bot levels are clearly visible
# The aggressive order came from the bot side
wide_spread_fills = [r for r in results if r['spread'] and r['spread'] > 10]
narrow_spread_fills = [r for r in results if r['spread'] and r['spread'] <= 10]

print(f"\n--- Wide spread make fills ({len(wide_spread_fills)}) ---")
if wide_spread_fills:
    print("These are fills where bots crossed from their levels to ours")
    print("Bot bid is at ~mid-6.5, bot ask is at ~mid+6.5")
    for r in wide_spread_fills[:5]:
        half_spread = r['spread'] / 2
        print(f"  ts={r['ts']:>6}: spread={r['spread']}, mid={r['mid']:.1f}, "
              f"bot_bid~={r['mid']-half_spread:.0f}, bot_ask~={r['mid']+half_spread:.0f}, "
              f"qty={r['fill_qty']}")

print(f"\n--- Narrow spread make fills ({len(narrow_spread_fills)}) ---")
if narrow_spread_fills:
    print("These are fills where our orders tightened the spread")
    for r in narrow_spread_fills:
        print(f"  ts={r['ts']:>6}: bp1={r['bp1']} bp2={r['bp2']} bp3={r['bp3']} | "
              f"ap1={r['ap1']} ap2={r['ap2']} ap3={r['ap3']} | "
              f"spread={r['spread']}, mid={r['mid']:.1f}, qty={r['fill_qty']}")

# === CRITICAL: Look at the PREVIOUS tick for each make-fill to see what was in the book ===
print(f"\n{'='*80}")
print(f"PREVIOUS-TICK ANALYSIS (what the book looked like BEFORE the fill)")
print(f"{'='*80}")

# On the tick BEFORE a make fill, our orders from 2 ticks ago should be in the book
# The make fill tick shows our CURRENT tick's result
# Let's look at the tick before each make fill
for r in results[:10]:  # First 10
    ts = r['ts']
    idx = tick_idx.get(ts)
    if idx and idx > 0:
        prev_ts = sorted_ticks[idx - 1]
        prev_r = tom_by_ts[prev_ts]
        prev_bp1 = int(prev_r['bid_price_1']) if prev_r['bid_price_1'] else None
        prev_ap1 = int(prev_r['ask_price_1']) if prev_r['ask_price_1'] else None
        prev_bp2 = int(prev_r['bid_price_2']) if prev_r['bid_price_2'] else None
        prev_ap2 = int(prev_r['ask_price_2']) if prev_r['ask_price_2'] else None
        prev_bp3 = int(prev_r['bid_price_3']) if prev_r['bid_price_3'] else None
        prev_ap3 = int(prev_r['ask_price_3']) if prev_r['ask_price_3'] else None
        prev_mid = float(prev_r['mid_price'])
        
        # Our fair value would have been based on prev_mid (EMA)
        # At WIDTH=3, our bid = fair-3, ask = fair+3
        # The fill happened because a bot crossed to our level
        
        print(f"\n  t={ts} (fill_qty={r['fill_qty']}):")
        print(f"    PREV tick book: {prev_bp3 or ''} {prev_bp2 or ''} [{prev_bp1}] ... [{prev_ap1}] {prev_ap2 or ''} {prev_ap3 or ''} (mid={prev_mid:.1f})")
        print(f"    FILL tick book: {r['bp3'] or ''} {r['bp2'] or ''} [{r['bp1']}] ... [{r['ap1']}] {r['ap2'] or ''} {r['ap3'] or ''} (mid={r['mid']:.1f})")
        print(f"    Our fair ≈ {round(prev_mid)} → bid={round(prev_mid)-3}, ask={round(prev_mid)+3}")
        
        # The fill could be on bid (bot sold to us) or ask (bot bought from us)
        # We can tell by looking at the PnL change direction
        # If PnL increased significantly, we probably bought below fair (bid fill)
        # or sold above fair (ask fill)

# === MAXIMUM WIDTH ANALYSIS ===
print(f"\n{'='*80}")
print(f"MAXIMUM WIDTH ANALYSIS")
print(f"{'='*80}")

print("""
Given:
- Bot spread ~13 (fair±6.5)
- Bot aggressive orders cross to at least fair±3 (proved by WIDTH=2,3 having same fills)
- All 66 make fills are preserved going from WIDTH=2→3

Key insight: the bot's aggressive order must be priced at LEAST at our make price.
At WIDTH=3, fills happened, so bot orders reached at least fair±3.

Conservative estimate: bots cross to fair±5 (well within their own spread range)
Aggressive estimate: bots cross to fair±6 (edge of their spread)

WIDTH analysis (assuming all 66 fills preserved):
  WIDTH=3: baseline 777.58 PnL
  WIDTH=4: +226 → ~1003.58
  WIDTH=5: +452 → ~1229.58
  WIDTH=6: +678 → ~1455.58

Risk: if some fills are lost at wider width, each lost fill costs:
  lost_PnL = fill_qty × WIDTH (total edge from that fill is gone)
  
For WIDTH=5, losing a 5-unit fill costs 25 PnL.
We'd need to lose >18 fills (>2/3) to be worse than WIDTH=3.
""")

# Final recommendation
print("RECOMMENDATION: Try WIDTH=5 (moderate-aggressive)")
print("  - Well within bot spread of 13 (fair±6.5)")
print("  - Even if we lose 30% of fills, net PnL gain is positive")
print("  - Expected PnL: ~1000-1230 TOMATOES + 121 EMERALDS = ~1120-1350 total")
