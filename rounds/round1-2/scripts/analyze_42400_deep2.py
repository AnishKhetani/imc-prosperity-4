"""
Part 2: Deeper analysis of extra fills, adverse selection, and position skew effects.
"""
import csv
import io
import json
from collections import Counter

sims = {}
for sim_id in ["42126", "42183", "42349", "42400"]:
    with open(f"logs/{sim_id}/{sim_id}.json") as f:
        sims[sim_id] = json.load(f)

def parse_activities(data):
    rows = list(csv.DictReader(io.StringIO(data["activitiesLog"]), delimiter=";"))
    return {p: [r for r in rows if r["product"] == p] for p in ("EMERALDS", "TOMATOES")}

def get_pnl_changes(rows):
    changes = []
    prev = 0.0
    for r in rows:
        pnl = float(r["profit_and_loss"])
        if pnl != prev:
            changes.append((int(r["timestamp"]), pnl - prev, pnl, r))
        prev = pnl
    return changes

data400 = parse_activities(sims["42400"])
em400 = data400["EMERALDS"]
em400_fills = get_pnl_changes(em400)

# Index by timestamp for easy lookup
em400_by_ts = {}
for r in em400:
    em400_by_ts[int(r["timestamp"])] = r

print("=" * 80)
print("EXTRA FILL DEEP DIVE")
print("=" * 80)

extra_ts = [60400, 64800, 78600, 90200, 150000]
for ts in extra_ts:
    r = em400_by_ts.get(ts, {})
    b1, b1v = r.get("bid_price_1","?"), r.get("bid_volume_1","?")
    a1, a1v = r.get("ask_price_1","?"), r.get("ask_volume_1","?")
    pnl = r.get("profit_and_loss","?")
    
    # Look at surrounding ticks
    for delta in [-200, -100, 0, 100, 200]:
        t = ts + delta
        if t in em400_by_ts:
            rr = em400_by_ts[t]
            print(f"  t={t}: B1={rr['bid_price_1']}x{rr['bid_volume_1']} A1={rr['ask_price_1']}x{rr['ask_volume_1']} PnL={rr['profit_and_loss']}")
    print()

# Analysis: why do these extra fills appear?
print("=" * 80)
print("EXTRA FILL PATTERN ANALYSIS")
print("=" * 80)

# These extra fills also appeared in 42126 (penny-jumping). Why?
# 42183/42260/42349 all had WIDTH=1 make at exactly 9999/10001
# 42126 had penny-jumping (post inside the spread)
# 42400 has WIDTH=7 (post at 9993/10007)
# Common thread: wider quotes trigger extra bot aggression

# Count: 42126 had fills at 60400, 64800, 78600, 90200 (4 extra)
# 42400 has those same 4 PLUS 150000 (5 extra total)
# Bot taker's behavior depends on what's in the book

# Check the extra fill PnL deltas:
d400 = {ts: d for ts, d, _, _ in em400_fills}
for ts in extra_ts:
    delta = d400.get(ts, 0)
    units = delta / 7
    print(f"  t={ts}: PnL delta={delta:.0f} → {units:.1f} units")

total_extra = sum(d400.get(ts, 0) for ts in extra_ts)
print(f"  Total extra PnL: {total_extra:.0f}")
print(f"  Total extra units: {total_extra/7:.1f}")

# Compare: 42126 extra fill sizes (WIDTH=1)
data126 = parse_activities(sims["42126"])
em126_fills = get_pnl_changes(data126["EMERALDS"])
d126 = {ts: d for ts, d, _, _ in em126_fills}
print(f"\n42126 extra fills at those timestamps:")
for ts in [60400, 64800, 78600, 90200]:
    delta = d126.get(ts, 0)
    ratio = d400.get(ts, 0) / delta if delta != 0 else 0
    print(f"  t={ts}: WIDTH=1 delta={delta:.0f} | WIDTH=7 delta={d400.get(ts,0):.0f} | ratio={ratio:.1f}")

print(f"\n42400 fill at t=150000 is NEW (not in any previous sim)")
print(f"  This fill has A1=10000 (non-standard book)")
print(f"  Yet it produced PnL delta=49 ({49/7:.0f} units at WIDTH=7)")


# POSITION RECONSTRUCTION
print("\n" + "=" * 80)
print("POSITION RECONSTRUCTION & SKEW ANALYSIS")
print("=" * 80)

# Each fill at WIDTH=7 earns 7 per unit regardless of buy/sell direction:
# Buy at 9993 earns 10000-9993=7 per unit (mark to fair value)
# Sell at 10007 earns 10007-10000=7 per unit (mark to fair value)
# PnL delta = 7 * abs(units)
# But the DIRECTION matters for position tracking

# We know final position = -16 (short 16 EMERALDS)
# From PnL: 1028 / 7 = 146.857 ≈ 147 units total
# If all fills were on one side: position = ±147
# Final position = -16, so buys ≈ sells with slight sell excess
# buys - sells = -16; buys + sells = 147
# buys = (147-16)/2 = 65.5, sells = (147+16)/2 = 81.5

# Hmm, units should be integers. Let's verify.
print(f"Fill PnL deltas: {[d for _, d, _, _ in em400_fills]}")
print(f"All divisible by 7: {all(d % 7 == 0 for _, d, _, _ in em400_fills)}")
unit_sizes = [int(d/7) for _, d, _, _ in em400_fills]
print(f"Unit sizes: {unit_sizes}")
print(f"Total units: {sum(unit_sizes)}")

# We can't determine buy/sell from PnL alone, but we know:
# - Final position = -16 (net short)
# - If we assign direction randomly, we'd need sells - buys = 16
# - Total units = 147, so sells = (147+16)/2 = 81.5 ... not integer!

# Wait, 42400 says positions: EMERALDS=-16. 
# Maybe total units isn't exactly 147. Let me recount.
print(f"Sum of unit_sizes: {sum(unit_sizes)}")

# Actually 1028/7 = 146.857. But PnL should be exact multiples of 7.
# Let me check: 1028 % 7 = ?
print(f"1028 mod 7 = {1028 % 7}")
# 1028 / 7 = 146.857... so 1028 = 7*146 + 6. Not divisible!
# Something's off. Let me check each fill delta more carefully.

# Oh wait - the fill at t=150000 has A1=10000. This means the bot ask is at 10000.
# If we TAKE that ask at 10000, our cost is 10000 (fair value), edge = 0.
# But the delta is 49, which IS divisible by 7 (49/7=7 units).
# So maybe some takes happened at non-7-edge prices?
# Actually wait, 1028 = sum of deltas. Let me verify:
total_check = sum(d for _, d, _, _ in em400_fills)
print(f"Sum of deltas: {total_check}")
print(f"Each delta: {[d for _, d, _, _ in em400_fills]}")
print(f"Each delta mod 7: {[d % 7 for _, d, _, _ in em400_fills]}")

# Check: are these fills taking at 10000 or making at 9993/10007?
# All deltas are divisible by 7, so all fills are at edge=7
# This means the t=150000 fill (A1=10000) is NOT a take at 10000
# It's a MAKE fill at 9993/10007 that happened to coincide with a non-standard book
# The bot still crossed our resting order at 9993 or 10007

# So: total units = 1028/7 = 146.857... but each is integer?
print(f"\nActual individual check:")
for ts, d, _, _ in em400_fills:
    if d % 7 != 0:
        print(f"  NON-7 FILL at t={ts}: delta={d}")

# If all are divisible by 7, total should also be. Let me recalculate...


# ADVERSE SELECTION CHECK
print("\n" + "=" * 80)
print("ADVERSE SELECTION CHECK")
print("=" * 80)

# After each fill, does the fill look correct in hindsight?
# For EMERALDS with fair=10000, there IS no adverse selection since fair never moves.
# The only risk: position exposure if position gets extreme.
# Let's check max position excursion

# Since we can't determine direction for EMERALDS fills from PnL alone,
# let's check: is the final position of -16 concerning?
print(f"Final EMERALDS position: -16")
print(f"Position limit: ±80")
print(f"Position utilization: {16/80*100:.0f}%")
print(f"""
Adverse selection analysis:
- EMERALDS fair value = 10,000 (constant, never moves)
- There IS no adverse selection by definition: 
  fair value doesn't change after fills
- Our edge is always WIDTH=7 per unit on every fill
- Position risk: 20% utilization at close, very manageable
- No risk of position squeeze (fair never moves)
""")


# SKEW ANALYSIS
print("=" * 80)
print("SKEW THRESHOLD ANALYSIS")
print("=" * 80)

# Current: SKEW_THRESHOLD=0.3 (24 units), HEAVY_THRESHOLD=0.6 (48 units)
# When position exceeds threshold, we skew our quotes:
# - Light skew: shift both bid/ask by 1 tick toward neutral
# - Heavy skew: shift by 2 ticks toward neutral
# This reduces our edge on the side that unwinds position (closer to fair)
# and increases edge on the side that adds position (further from fair)

# Question: does skew help or hurt?
# With 147 total units and final position -16, position rarely gets extreme
# Was skew ever triggered?
# Max position = ? Without knowing directions we can estimate:
# Random walk with 29 steps of varying sizes, final at -16
# Expected max excursion: sqrt(29) * avg_step ≈ 5.4 * 5 ≈ 27 units
print(f"Average fill size: {sum(unit_sizes)/len(unit_sizes):.1f} units")
print(f"SKEW_THRESHOLD: 24 units (0.3 * 80)")
print(f"HEAVY_THRESHOLD: 48 units (0.6 * 80)")
print(f"Estimated max excursion: ~27 units")
print(f"Skew would be triggered at moderate positions (~30% of limit)")
print(f"""
Skew impact:
- With avg fill ~5 units and 29 fills, position walks around 0
- Skew threshold at 24 units may be hit occasionally
- When triggered, shifts quotes by 1 tick → reduces edge from 7 to 6 on unwind side
- This is RARELY triggered and has minimal PnL impact
- Removing skew entirely is RISKY: position could grow unchecked
- Current thresholds seem reasonable

TO INVESTIGATE: Read the actual submission.py skew logic to verify.
""")


# SIZE+VOLUME RELATIONSHIP
print("=" * 80)
print("FILL SIZE DISTRIBUTION")
print("=" * 80)

size_counts = Counter(unit_sizes)
for size in sorted(size_counts):
    print(f"  {size} units: {size_counts[size]} fills")
print(f"  Total: {sum(unit_sizes)} units, {len(unit_sizes)} fills")
print(f"  Range: {min(unit_sizes)}-{max(unit_sizes)} units per fill")
print(f"  Median: {sorted(unit_sizes)[len(unit_sizes)//2]} units")

# Are bot aggressor quantities always the same across sims?
# We already know common fills have identical sizes (7x ratio with WIDTH=1 sims)
# Extra fills: sizes are 24/7≈3.4, 30/7≈4.3, 36/7≈5.1, 42/7=6, 49/7=7
# Wait: 24/7 is NOT integer. Let me check this.
print(f"\nExtra fill deltas and unit sizes:")
for ts in extra_ts:
    d = d400.get(ts, 0)
    print(f"  t={ts}: delta={d} → units={d/7:.4f} → exact? {d % 7 == 0}")

# Actually I miscounted delta for the extra at 60400
# Let me read the raw fill deltas again
print(f"\nRaw fill list:")
for ts, d, cum, _ in em400_fills:
    marker = " *** EXTRA" if ts in extra_ts else ""
    print(f"  t={ts:>6}: delta={d:>5.0f}  cum={cum:>6.0f}  units={d/7:>4.1f}{marker}")
