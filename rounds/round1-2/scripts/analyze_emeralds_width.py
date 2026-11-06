"""
EMERALDS width optimization analysis.
Determines maximum safe make width by analyzing bot aggressive behavior.

Key question: What is the bot aggressor's limit price on the 24 fill ticks?
If bot sell limit <= 9992 (proven by bot-to-bot trades at 9992),
then our bid can be at any price 9993-9999 and still get filled.
"""
import csv
import json
from collections import Counter

# Load all sims and compare EMERALDS behavior
sims = {}
for sim_id in ["42126", "42183", "42260", "42349"]:
    with open(f"logs/{sim_id}/{sim_id}.json") as f:
        data = json.load(f)
    rows = list(csv.DictReader(data["activitiesLog"].splitlines(), delimiter=";"))
    em = [r for r in rows if r["product"] == "EMERALDS"]
    sims[sim_id] = em

print("=" * 80)
print("PART 1: CROSS-SIM EMERALDS COMPARISON")
print("=" * 80)

# Compare PnL changes across all sims
for sim_id, em in sims.items():
    pnl_changes = []
    prev_pnl = 0.0
    position = 0
    for r in em:
        pnl = float(r["profit_and_loss"])
        if pnl != prev_pnl:
            delta = pnl - prev_pnl
            pnl_changes.append((int(r["timestamp"]), delta))
        prev_pnl = pnl
    
    fill_ts = [ts for ts, _ in pnl_changes]
    fill_sizes = [d for _, d in pnl_changes]
    
    ns = sum(1 for r in em if r["bid_price_1"] != "9992" or r["ask_price_1"] != "10008")
    
    print(f"\nSim {sim_id}:")
    print(f"  Fill events: {len(pnl_changes)}, total units: {sum(fill_sizes):.0f}")
    print(f"  Non-standard ticks: {ns}")
    print(f"  Fill timestamps: {fill_ts}")
    print(f"  Fill sizes: {[int(d) for d in fill_sizes]}")

# Verify all sims have identical fills (except 42126)
print("\n" + "=" * 80)
print("PART 2: VERIFY DETERMINISM")
print("=" * 80)

ref_sim = "42349"
ref_em = sims[ref_sim]
ref_pnl = []
prev = 0.0
for r in ref_em:
    pnl = float(r["profit_and_loss"])
    if pnl != prev:
        ref_pnl.append((int(r["timestamp"]), pnl - prev))
    prev = pnl

for sim_id in ["42183", "42260"]:
    em = sims[sim_id]
    sim_pnl = []
    prev = 0.0
    for r in em:
        pnl = float(r["profit_and_loss"])
        if pnl != prev:
            sim_pnl.append((int(r["timestamp"]), pnl - prev))
        prev = pnl
    
    ts_match = all(a[0] == b[0] for a, b in zip(ref_pnl, sim_pnl))
    size_match = all(abs(a[1] - b[1]) < 0.01 for a, b in zip(ref_pnl, sim_pnl))
    print(f"  {ref_sim} vs {sim_id}: timestamps match={ts_match}, sizes match={size_match}")

# Check 42126 differences
print("\n42126 vs 42349 differences:")
em126 = sims["42126"]
pnl126 = []
prev = 0.0
for r in em126:
    pnl = float(r["profit_and_loss"])
    if pnl != prev:
        pnl126.append((int(r["timestamp"]), pnl - prev))
    prev = pnl

ts_349 = set(ts for ts, _ in ref_pnl)
ts_126 = set(ts for ts, _ in pnl126)

extra_in_126 = ts_126 - ts_349
missing_in_126 = ts_349 - ts_126
common = ts_349 & ts_126

print(f"  Common fill ticks: {len(common)}")
print(f"  Extra fills in 42126: {sorted(extra_in_126)}")
print(f"  Missing fills in 42126: {sorted(missing_in_126)}")

# Show details of extra fills in 42126
print("\n  Extra fill details (42126):")
pnl126_dict = {ts: d for ts, d in pnl126}
em126_by_ts = {int(r["timestamp"]): r for r in em126}
for ts in sorted(extra_in_126):
    r = em126_by_ts[ts]
    b1 = r["bid_price_1"]
    a1 = r["ask_price_1"]
    delta = pnl126_dict[ts]
    print(f"    t={ts}: delta={delta:+.0f} | B1={b1} A1={a1}")

# Show details of fills at common ticks - do they match?
print("\n  Size comparison at common ticks:")
pnl349_dict = {ts: d for ts, d in ref_pnl}
mismatch = 0
for ts in sorted(common):
    s126 = pnl126_dict.get(ts, 0)
    s349 = pnl349_dict.get(ts, 0)
    if abs(s126 - s349) > 0.01:
        mismatch += 1
        print(f"    t={ts}: 42126={s126:+.0f} vs 42349={s349:+.0f}")
if mismatch == 0:
    print(f"    All {len(common)} common fills have identical sizes!")

# PART 3: Analyze non-standard ticks + fill interaction
print("\n" + "=" * 80)
print("PART 3: NON-STANDARD TICK DEEP DIVE (42349)")
print("=" * 80)

ref_em_by_ts = {int(r["timestamp"]): r for r in ref_em}
fill_ts_set = set(ts for ts, _ in ref_pnl)

# Categorize non-standard ticks
ns_bid10k = []  # Bot bid at 10000
ns_ask10k = []  # Bot ask at 10000
for r in ref_em:
    ts = int(r["timestamp"])
    b1 = r["bid_price_1"]
    a1 = r["ask_price_1"]
    if b1 == "10000":
        ns_bid10k.append(r)
    elif a1 == "10000":
        ns_ask10k.append(r)

print(f"\nBot bid at 10000: {len(ns_bid10k)} ticks")
print(f"Bot ask at 10000: {len(ns_ask10k)} ticks")

# What volumes do these have?
for label, ns_list in [("Bot bid@10000", ns_bid10k), ("Bot ask@10000", ns_ask10k)]:
    vols = [int(r["bid_volume_1"] if r["bid_price_1"] == "10000" else r["ask_volume_1"]) for r in ns_list]
    print(f"\n  {label}:")
    print(f"    Volume range: {min(vols)}-{max(vols)}")
    print(f"    Volume dist: {Counter(vols)}")
    total_vol = sum(vols)
    print(f"    Total volume: {total_vol}")

# For each non-standard tick, check what happens on surrounding ticks
print("\n  Non-standard tick neighborhoods:")
for r in ns_bid10k[:5]:
    ts = int(r["timestamp"])
    prev = ref_em_by_ts.get(ts - 100, {})
    next_ = ref_em_by_ts.get(ts + 100, {})
    print(f"    t={ts}: Bid@10000 vol={r['bid_volume_1']}")
    if prev:
        print(f"      prev (t-100): B1={prev.get('bid_price_1', '?')} A1={prev.get('ask_price_1', '?')}")
    if next_:
        print(f"      next (t+100): B1={next_.get('bid_price_1', '?')} A1={next_.get('ask_price_1', '?')}")

# PART 4: Width feasibility analysis
print("\n" + "=" * 80)
print("PART 4: WIDTH FEASIBILITY FOR EMERALDS")
print("=" * 80)

print("""
LOGICAL ARGUMENT:
- Bot resting book: bid=9992, ask=10008 (spread=16)
- Bot-to-bot trades happen at 9992 and 10008 (from backtester data)
- This means taker bots have sell limit <= 9992 and buy limit >= 10008
- Our make bid at 9993 (WIDTH=7) is ABOVE 9992 → taker sell still fills us
- Our make ask at 10007 (WIDTH=7) is BELOW 10008 → taker buy still fills us
- Therefore WIDTH=7 should preserve all 24 fills

EXPECTED PnL AT VARIOUS WIDTHS:
""")

for width in range(1, 9):
    bid = 10000 - width
    ask = 10000 + width
    expected_pnl = 121 * width
    inside = bid > 9992 and ask < 10008
    status = "SAFE (inside bot spread)" if inside else "AT/OUTSIDE bot level"
    print(f"  WIDTH={width}: bid={bid} ask={ask} → {expected_pnl} PnL | {status}")

print("""
RISK ANALYSIS:
- WIDTH=7 (9993/10007): 1 tick inside bot resting levels. Should be safe.
- WIDTH=8 (9992/10008): AT bot level. Priority goes to bot (they post first). RISKY.
- Recommendation: WIDTH=7 (maximum safe width). PnL: 121 * 7 = 847.

ADDITIONAL CONSIDERATIONS:
1. Currently taking at 10000 (zero edge) on ~59 non-standard ticks.
   → These are harmless (0 PnL) but affect position.
   → At WIDTH=7, position skew from zero-edge takes could shift make prices.
   → Recommend: stop taking at 10000 (use strict inequality FAIR-1/FAIR+1).
   This prevents position drift that could trigger skew adjustments.

2. The 24 fill events are MAKES, not takes:
   → All PnL changes occur on standard-book ticks (9992/10008)
   → No orders near fair to take on those ticks
   → Our resting make orders get filled by bot aggressors after our tick
   → The context file's claim "all fills are takes" was WRONG
""")
