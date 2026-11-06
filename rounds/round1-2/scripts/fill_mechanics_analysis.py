"""
Precise fill mechanics analysis: HOW does the platform generate fills?
Compare what OUR strategy submits vs. what fills happen.
Parse the stdout log from 44861 to see submitted orders per tick.
"""
import json, csv, io
from collections import defaultdict

# Parse 44861 sim data
with open('logs/44861/44861.log', 'r') as f:
    data = json.load(f)

# The stdout field contains our compressed JSON output per tick
# Format: [[state], {orders}, conversions, traderData, logs]
# Let's parse the graphLog which has PnL per tick per product
graph_reader = csv.DictReader(io.StringIO(data['graphLog']), delimiter=';')
graph_rows = list(graph_reader)
print(f"graphLog: {len(graph_rows)} rows")
print(f"columns: {list(graph_rows[0].keys())}")
print(f"first: {graph_rows[0]}")
print(f"last: {graph_rows[-1]}")

# Parse activities to get per-tick book + PnL
act_reader = csv.DictReader(io.StringIO(data['activitiesLog']), delimiter=';')
rows = list(act_reader)

# ═══════════════════════════════════════════════════════════════
#  TOMATOES: Tick-by-tick position & PnL reconstruction
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("TOMATOES FILL MECHANICS — Reconstructing from PnL changes")
print("=" * 80)

tom_rows = [r for r in rows if r['product'] == 'TOMATOES']

# Track PnL changes. The PnL shown is mark-to-market: realized + unrealized
# PnL_change = (trade PnL from fill) + (position * mid_change)
# So PnL changes even without fills due to position mark-to-market

prev_pnl = 0
prev_mid = None
consecutive_fills = 0
max_consecutive = 0
fills_this_sequence = []
all_fill_sequences = []

for i, r in enumerate(tom_rows):
    pnl = float(r['profit_and_loss'])
    mid = float(r['mid_price'])
    b1 = float(r.get('bid_price_1', 0) or 0) 
    a1 = float(r.get('ask_price_1', 0) or 0)
    ts = int(r['timestamp'])
    spread = int(a1 - b1) if a1 > 0 and b1 > 0 else -1
    
    delta = pnl - prev_pnl
    
    if abs(delta) > 0.01:
        consecutive_fills += 1
        fills_this_sequence.append({
            'ts': ts, 'delta': delta, 'mid': mid, 'spread': spread,
            'b1': b1, 'a1': a1,
            'prev_mid': prev_mid
        })
    else:
        if consecutive_fills > 0:
            all_fill_sequences.append(fills_this_sequence.copy())
            max_consecutive = max(max_consecutive, consecutive_fills)
        consecutive_fills = 0
        fills_this_sequence = []
    
    prev_pnl = pnl
    prev_mid = mid

if consecutive_fills > 0:
    all_fill_sequences.append(fills_this_sequence.copy())

print(f"Total fill sequences: {len(all_fill_sequences)}")
print(f"Max consecutive fill ticks: {max_consecutive}")

# Distribution of sequence lengths
seq_lens = [len(s) for s in all_fill_sequences]
len_dist = defaultdict(int)
for l in seq_lens:
    len_dist[l] += 1
print(f"Sequence length distribution:")
for l in sorted(len_dist.keys()):
    print(f"  len={l}: {len_dist[l]} sequences")

# ═══════════════════════════════════════════════════════════════
#  MARK-TO-MARKET DECOMPOSITION
#  PnL_t = realized_cashflow + position_t * mid_t
#  Δ(PnL) = trade_cashflow + Δposition * mid_t + position_{t-1} * Δmid
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("MARK-TO-MARKET DECOMPOSITION")
print("PnL_t = cash + position * mid")
print("We need to separate fill events from MTM changes")
print("=" * 80)

# Since we know the FINAL position for 44861 is 7 (TOMATOES),
# we can backward-reconstruct position at each tick

# Actually, the PnL shown is the platform's mark-to-market:
# PnL = realized_trades_cashflow + position * mid_price
# When mid changes by dm and position is p: ΔPnL includes p * dm
# So even without a fill, PnL changes when mid moves while holding position

# Let's estimate: at ticks where mid DOESN'T change, ΔPnL must be from fills
# And at ticks where mid DOES change, ΔPnL = fill_pnl + position * Δmid

no_mid_change_fills = 0
mid_change_fills = 0
pure_mtm = 0

prev_pnl = 0
prev_mid = float(tom_rows[0]['mid_price'])

for i in range(1, len(tom_rows)):
    pnl = float(tom_rows[i]['profit_and_loss'])
    mid = float(tom_rows[i]['mid_price'])
    delta_pnl = pnl - prev_pnl
    delta_mid = mid - prev_mid
    
    if abs(delta_pnl) > 0.01:
        if abs(delta_mid) < 0.01:
            no_mid_change_fills += 1
        else:
            mid_change_fills += 1
    else:
        if abs(delta_mid) > 0.01:
            pure_mtm += 1  # mid moved but PnL didn't change (no position + no fill)
    
    prev_pnl = pnl
    prev_mid = mid

print(f"PnL changes with stable mid: {no_mid_change_fills} (pure fill events)")
print(f"PnL changes with mid change: {mid_change_fills} (fill + MTM mixed)")
print(f"No PnL change but mid moved: {pure_mtm} (MTM only, implies position=0)")

# ═══════════════════════════════════════════════════════════════
#  WHAT FAIR VALUE DOES THE STRATEGY COMPUTE?
#  Let's reconstruct the strategy's fair value at each tick
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("STRATEGY FAIR VALUE RECONSTRUCTION (EMA5 + IMB*0.5 - pos*0.05)")
print("=" * 80)

ema = None
alpha = 2.0 / (5 + 1)
position = 0  # unknown start, will estimate

# We know final position = 7, work forward
# For now, just compute what the strategy WOULD compute
fair_values = []
for i, r in enumerate(tom_rows):
    mid = float(r['mid_price'])
    b1 = float(r.get('bid_price_1', 0) or 0)
    a1 = float(r.get('ask_price_1', 0) or 0)
    bv1 = float(r.get('bid_volume_1', 0) or 0)
    av1 = float(r.get('ask_volume_1', 0) or 0)
    
    if ema is None:
        ema = mid
    else:
        ema = alpha * mid + (1 - alpha) * ema
    
    # L1 imbalance
    l1_total = bv1 + av1
    imb = (bv1 - av1) / l1_total if l1_total > 0 else 0
    
    # Without knowing exact position, show ema and adjusted
    adjusted_no_pos = ema + imb * 0.5
    fair_no_pos = round(adjusted_no_pos)
    
    fair_values.append({
        'ts': int(r['timestamp']),
        'mid': mid,
        'ema': ema,
        'fair_no_pos': fair_no_pos,
        'diff': fair_no_pos - mid,
        'imb': imb,
        'spread': int(a1 - b1) if a1 > 0 and b1 > 0 else -1,
    })

# How often does fair differ from mid?
diff_dist = defaultdict(int)
for fv in fair_values:
    diff_dist[fv['diff']] += 1
print("Fair value (no pos adj) vs mid distribution:")
for d in sorted(diff_dist.keys()):
    print(f"  diff={d:+.0f}: {diff_dist[d]} ticks ({diff_dist[d]/len(fair_values)*100:.1f}%)")

# ═══════════════════════════════════════════════════════════════
#  WHERE ARE OUR MAKE ORDERS RELATIVE TO BOT BOOK?
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("OUR MAKE ORDERS vs BOT BOOK (WIDTH=5)")
print("=" * 80)

inside_count = 0
at_bot_level = 0
outside_count = 0
our_bid_vs_bot = defaultdict(int)
our_ask_vs_bot = defaultdict(int)

for fv in fair_values:
    if fv['spread'] < 0:
        continue
    
    mid = fv['mid']
    fair = fv['fair_no_pos']  # approximate
    our_bid = fair - 5  # WIDTH=5
    our_ask = fair + 5
    
    # Bot levels from mid ± spread/2
    # For spread=14: bot bid = mid - 7, bot ask = mid + 7
    # For spread=13: bot bid = mid - 6.5, bot ask = mid + 6.5
    # Actually, we know exact levels from data
    
    b1 = fair_values[fair_values.index(fv)]['mid'] - fv['spread']/2  # approximate
    a1 = fair_values[fair_values.index(fv)]['mid'] + fv['spread']/2
    
    # How far is our bid from bot's best bid?
    # Our bid should be ABOVE bot's best bid (inside the spread)
    bid_gap = our_bid - (mid - fv['spread']/2)  # positive = inside spread
    ask_gap = (mid + fv['spread']/2) - our_ask  # positive = inside spread
    
    our_bid_vs_bot[round(bid_gap)] += 1
    our_ask_vs_bot[round(ask_gap)] += 1

print("Our bid gap from bot bid (positive = inside spread, gets filled):")
for g in sorted(our_bid_vs_bot.keys()):
    print(f"  gap={g:+d}: {our_bid_vs_bot[g]} ticks ({our_bid_vs_bot[g]/len(fair_values)*100:.1f}%)")

print("\nOur ask gap from bot ask (positive = inside spread, gets filled):")
for g in sorted(our_ask_vs_bot.keys()):
    print(f"  gap={g:+d}: {our_ask_vs_bot[g]} ticks ({our_ask_vs_bot[g]/len(fair_values)*100:.1f}%)")

# ═══════════════════════════════════════════════════════════════
#  EMERALDS: Check if we can extract MORE by changing take threshold
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("EMERALDS DETAILED FILLS — Can we improve?")
print("=" * 80)

em_rows = [r for r in rows if r['product'] == 'EMERALDS']
prev_pnl = 0
for r in em_rows:
    pnl = float(r['profit_and_loss'])
    delta = pnl - prev_pnl
    if abs(delta) > 0.01:
        ts = int(r['timestamp'])
        mid = float(r['mid_price'])
        b1 = float(r.get('bid_price_1', 0) or 0)
        a1 = float(r.get('ask_price_1', 0) or 0)
        bv1 = float(r.get('bid_volume_1', 0) or 0)
        av1 = float(r.get('ask_volume_1', 0) or 0)
        spread = a1 - b1
        
        # Decompose PnL change: at fair=10000 with width=7
        # Make buy at 9993: earn 7 per unit
        # Make sell at 10007: earn 7 per unit
        # Take buy at 9999: earn 1 per unit
        # Take sell at 10001: earn 1 per unit
        # But all deltas are multiples of 7, so these are all MAKE fills
        
        units = delta / 7  # should be integer
        print(f"  t={ts:6d}: ΔPnL={delta:+.0f} ({units:+.0f} units @ edge=7), mid={mid}, spread={spread:.0f}, bv1={bv1:.0f}, av1={av1:.0f}")
    prev_pnl = pnl

# Count EMERALDS ticks where bot narrows spread to 8
em_narrow = [r for r in em_rows if float(r.get('ask_price_1', 0) or 0) - float(r.get('bid_price_1', 0) or 0) == 8]
print(f"\nEMERALDS narrow spread (=8) ticks: {len(em_narrow)} / {len(em_rows)}")
for r in em_narrow[:10]:
    ts = int(r['timestamp'])
    b1 = float(r.get('bid_price_1', 0) or 0)
    a1 = float(r.get('ask_price_1', 0) or 0)
    bv1 = float(r.get('bid_volume_1', 0) or 0)
    av1 = float(r.get('ask_volume_1', 0) or 0)
    pnl = float(r['profit_and_loss'])
    print(f"  t={ts}: bid={b1:.0f}({bv1:.0f}) ask={a1:.0f}({av1:.0f}) PnL={pnl:.2f}")

print("\n\nDONE.")
