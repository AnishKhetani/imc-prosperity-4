"""
Critical analysis: Why did 42260 (2-level TOMATOES) perform WORSE than 42183 (1-level)?
Hypothesis: Platform is deterministic — bots trade same qty regardless of our orders.
Our quoting width only determines FILL PRICE, not FILL COUNT.
"""
import json, csv, io
from collections import Counter

def load_activities(sim_id):
    with open(f'logs/{sim_id}/{sim_id}.json', 'r') as f:
        data = json.load(f)
    activities = data['activitiesLog']
    reader = csv.DictReader(io.StringIO(activities), delimiter=';')
    return list(reader), data

rows260, data260 = load_activities(42260)
rows183, data183 = load_activities(42183)

# Extract TOMATOES data
def get_tomatoes(rows):
    return [r for r in rows if r['product'] == 'TOMATOES']

tom260 = get_tomatoes(rows260)
tom183 = get_tomatoes(rows183)

# === TEST: Are the order books identical? ===
print("=== MARKET DATA COMPARISON (first 50 ticks) ===")
mismatch = 0
for i in range(min(len(tom260), len(tom183))):
    r260 = tom260[i]
    r183 = tom183[i]
    
    # Compare mid prices
    if r260['mid_price'] != r183['mid_price']:
        mismatch += 1
        if mismatch <= 5:
            print(f"MID MISMATCH at tick {i}: {r260['mid_price']} vs {r183['mid_price']}")
    
    # Compare non-standard levels (ignoring our orders, compare L2+ which are bot-generated)
    # Actually bot levels might shift due to our fills. Let's check timestamps
    if r260['timestamp'] != r183['timestamp']:
        print(f"TIMESTAMP MISMATCH at tick {i}: {r260['timestamp']} vs {r183['timestamp']}")
        break

print(f"Mid price mismatches: {mismatch}/{len(tom260)}")

# === Check: are the SAME ticks seeing PnL changes? ===
print(f"\n=== FILL TICK COMPARISON ===")
def get_fill_ticks(tom_rows):
    fills = {}
    prev_pnl = 0.0
    for r in tom_rows:
        ts = int(r['timestamp'])
        pnl = float(r['profit_and_loss'])
        delta = pnl - prev_pnl
        if abs(delta) > 0.001:
            fills[ts] = delta
        prev_pnl = pnl
    return fills

fills260 = get_fill_ticks(tom260)
fills183 = get_fill_ticks(tom183)

common = set(fills260.keys()) & set(fills183.keys())
only260 = set(fills260.keys()) - set(fills183.keys())
only183 = set(fills183.keys()) - set(fills260.keys())

print(f"Fill ticks in 42260: {len(fills260)}")
print(f"Fill ticks in 42183: {len(fills183)}")
print(f"Common fill ticks: {len(common)}")
print(f"Only in 42260: {len(only260)}")
print(f"Only in 42183: {len(only183)}")

if only260:
    print(f"  42260-only ticks: {sorted(only260)[:20]}")
if only183:
    print(f"  42183-only ticks: {sorted(only183)[:20]}")

# === Compare per-fill PnL at common ticks ===
print(f"\n=== PER-FILL PNL COMPARISON (common ticks) ===")
diff_total = 0
diff_count = 0
same_count = 0
bigger260 = 0
bigger183 = 0

fill_diffs = []
for ts in sorted(common):
    d260 = fills260[ts]
    d183 = fills183[ts]
    diff = d260 - d183
    fill_diffs.append((ts, d260, d183, diff))
    if abs(diff) > 0.001:
        diff_count += 1
        diff_total += diff
        if d260 > d183:
            bigger260 += 1
        else:
            bigger183 += 1
    else:
        same_count += 1

print(f"Same PnL at fill: {same_count}")
print(f"Different PnL at fill: {diff_count}")
print(f"  42260 better: {bigger260}")
print(f"  42183 better: {bigger183}")
print(f"Net difference: {diff_total:.2f}")

# Show biggest differences
fill_diffs.sort(key=lambda x: x[3])
print(f"\nBiggest differences (42260 worse):")
for ts, d260, d183, diff in fill_diffs[:10]:
    print(f"  t={ts:6d}: 42260={d260:+.2f}  42183={d183:+.2f}  diff={diff:+.2f}")

print(f"\nBiggest differences (42260 better):")
for ts, d260, d183, diff in fill_diffs[-10:]:
    print(f"  t={ts:6d}: 42260={d260:+.2f}  42183={d183:+.2f}  diff={diff:+.2f}")

# === Classify the differences ===
print(f"\n=== DIFFERENCE ANALYSIS ===")
# Group differences by sign and magnitude
small_diff = sum(1 for _, _, _, d in fill_diffs if 0.001 < abs(d) <= 1)
med_diff = sum(1 for _, _, _, d in fill_diffs if 1 < abs(d) <= 5)
large_diff = sum(1 for _, _, _, d in fill_diffs if abs(d) > 5)
print(f"Small diff (±0-1): {small_diff}")
print(f"Med diff (±1-5): {med_diff}")
print(f"Large diff (±5+): {large_diff}")

# === What's the cumulative effect? ===
print(f"\n=== CUMULATIVE EFFECT ===")
cum_diff = 0
for ts, d260, d183, diff in sorted(fill_diffs, key=lambda x: x[0]):
    cum_diff += diff
# Final cumulative
print(f"Cumulative PnL difference (42260 - 42183): {cum_diff:.2f}")
print(f"Expected from profit: {551.578125 - 777.578125:.2f}")

# === EMERALDS comparison ===
print(f"\n=== EMERALDS COMPARISON ===")
em260 = [r for r in rows260 if r['product'] == 'EMERALDS']
em183 = [r for r in rows183 if r['product'] == 'EMERALDS']

em_fills260 = get_fill_ticks(em260)
em_fills183 = get_fill_ticks(em183)
print(f"EMERALDS fill ticks: 42260={len(em_fills260)}, 42183={len(em_fills183)}")
em_common = set(em_fills260.keys()) & set(em_fills183.keys())
em_only260 = set(em_fills260.keys()) - set(em_fills183.keys())
em_only183 = set(em_fills183.keys()) - set(em_fills260.keys())
print(f"Common: {len(em_common)}, Only 42260: {len(em_only260)}, Only 42183: {len(em_only183)}")

# Check if EMERALDS fills are identical
em_mismatch = 0
for ts in em_common:
    if abs(em_fills260[ts] - em_fills183[ts]) > 0.001:
        em_mismatch += 1
print(f"EMERALDS fill PnL mismatches: {em_mismatch}")
