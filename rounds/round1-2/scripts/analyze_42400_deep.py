"""
Deep analysis of sim 42400 (EMERALDS WIDTH=7, TOMATOES WIDTH=5).
Goal: Find safe improvement opportunities without overfitting.
"""
import csv
import io
import json
import math
from collections import Counter, defaultdict

# Load all sims for comparison
sims = {}
for sim_id in ["42126", "42183", "42260", "42349", "42400"]:
    with open(f"logs/{sim_id}/{sim_id}.json") as f:
        sims[sim_id] = json.load(f)

def parse_activities(data):
    rows = list(csv.DictReader(io.StringIO(data["activitiesLog"]), delimiter=";"))
    em = [r for r in rows if r["product"] == "EMERALDS"]
    tom = [r for r in rows if r["product"] == "TOMATOES"]
    return em, tom

def get_pnl_changes(product_rows):
    changes = []
    prev = 0.0
    for r in product_rows:
        pnl = float(r["profit_and_loss"])
        if pnl != prev:
            changes.append((int(r["timestamp"]), pnl - prev, pnl))
        prev = pnl
    return changes

print("=" * 80)
print("PART 1: CROSS-SIM EMERALDS COMPARISON")
print("=" * 80)

for sim_id in ["42126", "42183", "42260", "42349", "42400"]:
    em, tom = parse_activities(sims[sim_id])
    em_fills = get_pnl_changes(em)
    tom_fills = get_pnl_changes(tom)
    
    em_total = sum(d for _, d, _ in em_fills)
    tom_total = sum(d for _, d, _ in tom_fills)
    em_units = em_total  # each fill $ = 1 unit at WIDTH=1... but not for wider widths
    
    print(f"\n  Sim {sim_id}: EM={em_total:.0f} ({len(em_fills)} fills) | TOM={tom_total:.1f} ({len(tom_fills)} fills) | Total={em_total+tom_total:.1f}")
    print(f"    EM fill timestamps: {[ts for ts, _, _ in em_fills]}")
    print(f"    EM fill sizes (PnL delta): {[round(d, 1) for _, d, _ in em_fills]}")

# PART 2: Detailed 42400 EMERALDS analysis
print("\n" + "=" * 80)
print("PART 2: 42400 EMERALDS FILL DETAIL")
print("=" * 80)

em400, tom400 = parse_activities(sims["42400"])
em400_fills = get_pnl_changes(em400)
em400_by_ts = {int(r["timestamp"]): r for r in em400}

print(f"\nTotal EMERALDS fills: {len(em400_fills)}")
print(f"Total EMERALDS PnL: {sum(d for _, d, _ in em400_fills):.0f}")

# At WIDTH=7, each unit earns 7 PnL. So units = PnL / 7
total_units = sum(d for _, d, _ in em400_fills) / 7
print(f"Estimated total units filled: {total_units:.1f}")

# Compare fill timestamps with 42349 (WIDTH=1)
em349, _ = parse_activities(sims["42349"])
em349_fills = get_pnl_changes(em349)
ts_349 = set(ts for ts, _, _ in em349_fills)
ts_400 = set(ts for ts, _, _ in em400_fills)

common = ts_349 & ts_400
extra_in_400 = ts_400 - ts_349
missing_in_400 = ts_349 - ts_400

print(f"\nFill timestamp comparison vs 42349 (WIDTH=1):")
print(f"  Common: {len(common)}")
print(f"  Extra in 42400: {sorted(extra_in_400)}")
print(f"  Missing in 42400: {sorted(missing_in_400)}")

# For common fills, compare PnL deltas
print(f"\nCommon fill PnL comparison (should be 7x at WIDTH=7 vs WIDTH=1):")
d349 = {ts: d for ts, d, _ in em349_fills}
d400 = {ts: d for ts, d, _ in em400_fills}
ratios = []
for ts in sorted(common):
    ratio = d400[ts] / d349[ts] if d349[ts] != 0 else 0
    ratios.append(ratio)
    if abs(ratio - 7.0) > 0.1:
        print(f"  t={ts}: WIDTH=1 delta={d349[ts]:.0f} | WIDTH=7 delta={d400[ts]:.0f} | ratio={ratio:.2f} *** MISMATCH")

print(f"  Ratios: min={min(ratios):.2f}, max={max(ratios):.2f}, mean={sum(ratios)/len(ratios):.2f}")
if all(abs(r - 7.0) < 0.1 for r in ratios):
    print(f"  All {len(common)} common fills have exactly 7x PnL ratio ✓")

# Extra fills in 42400
if extra_in_400:
    print(f"\nExtra fill details (42400 only):")
    for ts in sorted(extra_in_400):
        delta = d400[ts]
        r = em400_by_ts.get(ts, {})
        b1 = r.get("bid_price_1", "?")
        a1 = r.get("ask_price_1", "?")
        print(f"  t={ts}: delta={delta:+.0f} units~{delta/7:.1f} | B1={b1} A1={a1}")

# Also compare with 42126 (which had 28 fills with penny-jumping strategy)
em126, _ = parse_activities(sims["42126"])
em126_fills = get_pnl_changes(em126)
ts_126 = set(ts for ts, _, _ in em126_fills)

print(f"\nFill timestamp comparison vs 42126 (28 fills, penny-jumping):")
common_126 = ts_126 & ts_400
extra_in_400_vs_126 = ts_400 - ts_126
extra_in_126_vs_400 = ts_126 - ts_400
print(f"  Common: {len(common_126)}")
print(f"  Extra in 42400: {sorted(extra_in_400_vs_126)}")
print(f"  Extra in 42126: {sorted(extra_in_126_vs_400)}")


# PART 3: Non-standard tick analysis
print("\n" + "=" * 80)
print("PART 3: NON-STANDARD TICK ANALYSIS (42400)")
print("=" * 80)

ns_bid = [r for r in em400 if r["bid_price_1"] == "10000"]
ns_ask = [r for r in em400 if r["ask_price_1"] == "10000"]
ns_other = [r for r in em400 if r["bid_price_1"] not in ("9992", "10000") or r["ask_price_1"] not in ("10008", "10000")]

print(f"Bot bid at 10000: {len(ns_bid)} ticks")
print(f"Bot ask at 10000: {len(ns_ask)} ticks")
print(f"Other non-standard: {len(ns_other)} ticks")

# Check if any non-standard ticks overlap with fills
fill_ts_set = set(ts for ts, _, _ in em400_fills)
ns_fill_overlap = [r for r in ns_bid + ns_ask if int(r["timestamp"]) in fill_ts_set]
print(f"Non-standard ticks that are also fill ticks: {len(ns_fill_overlap)}")

# Are our orders appearing in the book? Check for 9993 or 10007
for r in em400[:50]:
    b1 = r.get("bid_price_1", "")
    b2 = r.get("bid_price_2", "")
    b3 = r.get("bid_price_3", "")
    a1 = r.get("ask_price_1", "")
    a2 = r.get("ask_price_2", "")
    a3 = r.get("ask_price_3", "")
    prices = [b1, b2, b3, a1, a2, a3]
    if "9993" in prices or "10007" in prices:
        print(f"  OUR PRICE IN BOOK at t={r['timestamp']}: B=[{b1},{b2},{b3}] A=[{a1},{a2},{a3}]")


# PART 4: EMERALDS position dynamics
print("\n" + "=" * 80)
print("PART 4: POSITION DYNAMICS")
print("=" * 80)

# Reconstruct position from PnL changes
# Each fill at WIDTH=7: buy gives +units, sell gives +units 
# PnL delta > 0 always (we earn edge), but we need to know buy vs sell
# Can't directly determine from PnL alone. Need to look at the log.

# Instead, look at what the order book looked like on fill ticks
# If bot aggressors are selling (hitting our bid), we BUY
# If bot aggressors are buying (lifting our ask), we SELL
# At 42349 (WIDTH=1), all fills had delta = units * 1 = units
# position change = +units for buy, -units for sell
# But PnL is always positive for both. How to distinguish?

# Let's check the graphLog for position tracking
positions = sims["42400"].get("positions", [])
print(f"Positions data: {positions}")

# Check if non-standard ticks (bot at 10000) give clues about buy/sell direction
# Bot bid at 10000 = bot wants to buy = could lift our ask = we SELL
# Bot ask at 10000 = bot wants to sell = could hit our bid = we BUY
print(f"\nBot bid@10000 (potential SELL fills): {len(ns_bid)} ticks")
print(f"Bot ask@10000 (potential BUY fills): {len(ns_ask)} ticks")

# Check if non-standard ticks predict fills
ns_bid_ts = set(int(r["timestamp"]) for r in ns_bid)
ns_ask_ts = set(int(r["timestamp"]) for r in ns_ask)

# How many fills happen 1-3 ticks after a non-standard tick?
for label, ns_set in [("after bid@10000", ns_bid_ts), ("after ask@10000", ns_ask_ts)]:
    hits = 0
    for ts in fill_ts_set:
        for lookback in range(0, 500, 100):
            if (ts - lookback) in ns_set:
                hits += 1
                break
    print(f"  Fills within 5 ticks {label}: {hits}/{len(fill_ts_set)}")


# PART 5: TOMATOES analysis (verify unchanged)
print("\n" + "=" * 80)
print("PART 5: TOMATOES VERIFICATION")
print("=" * 80)

tom400_fills = get_pnl_changes(tom400)
_, tom349 = parse_activities(sims["42349"])
tom349_fills = get_pnl_changes(tom349)

print(f"42400 TOMATOES: {len(tom400_fills)} fills, PnL={sum(d for _, d, _ in tom400_fills):.2f}")
print(f"42349 TOMATOES: {len(tom349_fills)} fills, PnL={sum(d for _, d, _ in tom349_fills):.2f}")

ts_tom400 = [ts for ts, _, _ in tom400_fills]
ts_tom349 = [ts for ts, _, _ in tom349_fills]
print(f"Same timestamps: {ts_tom400 == ts_tom349}")

d_tom400 = {ts: d for ts, d, _ in tom400_fills}
d_tom349 = {ts: d for ts, d, _ in tom349_fills}
tom_mismatches = 0
for ts in ts_tom349:
    if ts in d_tom400 and abs(d_tom400[ts] - d_tom349[ts]) > 0.01:
        tom_mismatches += 1
print(f"PnL mismatches: {tom_mismatches}")


# PART 6: Can we safely widen EMERALDS further?
print("\n" + "=" * 80)
print("PART 6: EMERALDS WIDTH=8 FEASIBILITY")
print("=" * 80)

# At WIDTH=8, bid=9992 ask=10008 — AT the bot resting level
# Question: would any fills be lost?
# Evidence from bot-to-bot trades in backtester data
print("""
WIDTH=8 analysis:
- bid=9992, ask=10008 — exactly AT bot resting levels
- Bot maker posts at 9992/10008, then taker bot crosses
- Our order and bot order at same price: who gets priority?
- Platform matching: bot maker orders posted BEFORE ours (step 2 vs step 4)
- At same price, time priority means bot gets filled first
- If taker's full quantity is absorbed by bot maker, nothing left for us
- VERDICT: WIDTH=8 is UNSAFE — likely lose most/all fills

WIDTH=7 appears optimal:
- 1 tick inside bot levels
- Got MORE fills than expected (extra fills vs 42349)
- PnL = 1028 vs expected 847 = +181 bonus from extra fills
""")

# PART 7: EMERALDS — can we capture the non-standard 10000 ticks?
print("=" * 80)
print("PART 7: CAN WE PROFIT FROM BOT@10000 TICKS?")
print("=" * 80)

# Bot bid@10000: we could sell at 10000 (edge = 0 from fair 10000)
# Bot ask@10000: we could buy at 10000 (edge = 0)
# Currently we DON'T take these (strict edge: ≤9999/≥10001)
# Volume analysis
bid10k_vols = [int(r["bid_volume_1"]) for r in ns_bid]
ask10k_vols = [int(r["ask_volume_1"]) for r in ns_ask]
print(f"Bot bid@10000: {len(ns_bid)} ticks, total vol={sum(bid10k_vols)}, avg={sum(bid10k_vols)/len(bid10k_vols):.1f}")
print(f"Bot ask@10000: {len(ns_ask)} ticks, total vol={sum(ask10k_vols)}, avg={sum(ask10k_vols)/len(ask10k_vols):.1f}")

print(f"""
Taking at 10000 analysis:
- Edge from take = 0 (buying at fair or selling at fair)
- BUT this creates position that needs to be unwound
- Unwinding happens via make fills at WIDTH=7 → expected edge = 7 per unit
- Net expected value: 0 (take edge) + 7 (unwind via make) = +7 per unit?
- BUT: make fills are rare (1.2% rate). Position from 10000 takes may persist
  until day end → exposure to mark-to-market at close
- Mark-to-market at close: position × (close_price - fair). Since fair=10000
  and mid is always 10000, closing P&L from position = 0 on average.
- So taking at 10000 is NEUTRAL in expectation (0 edge take, 0 close P&L)
  while adding position risk and potentially triggering skew adjustments
  that shift make prices away from optimal WIDTH=7 levels.
  
VERDICT: Keep strict edge thresholds. Taking at 10000 adds risk for zero 
expected benefit. The current approach (ignore 10000 ticks) is correct.
""")


# PART 8: TOMATOES optimization check
print("=" * 80)
print("PART 8: TOMATOES WIDTH=6 FEASIBILITY CHECK")
print("=" * 80)

# From section 0.7 of context: WIDTH=6 has all fills inside spread
# but is "very tight". Let's estimate the PnL gain.
tom_pnl_w5 = sum(d for _, d, _ in tom400_fills)
# Each unit at WIDTH=5 earns 5. At WIDTH=6, it would earn 6.
# Estimated units = total_pnl / 5 (approximately, since takes earn differently)
# Actually, has anyone checked if TOMATOES WIDTH=6 would lose fills?

print(f"Current TOMATOES PnL (WIDTH=5): {tom_pnl_w5:.2f}")
print(f"TOMATOES fills: {len(tom400_fills)}")

# To properly check WIDTH=6 feasibility, we need the bot spread on each fill tick
# We know from context: WIDTH=7 would lose 35 fills (outside spread)
# WIDTH=6: all fits but "very tight"
# Expected gain: (total_units) * 1 = +226 PnL
print(f"""
WIDTH=6 for TOMATOES:
- From context section 0.7: all 66 fills inside spread at WIDTH=6
- But "very tight" — gap 0-2 on many ticks
- Expected PnL: ~1,330 (vs current 1,105)
- Risk: if any bot limit price is < fair+6, that fill is lost
- Given platform determinism for TOMATOES, we could test this with a single sim
  and know definitively whether fills are preserved

RECOMMENDATION: Test WIDTH=6 on platform. If all fills preserved → +226 PnL.
If any fills lost → revert to WIDTH=5. Low risk since platform is deterministic.
""")


# PART 9: Mark-to-market analysis — do we leave money on the table at close?
print("=" * 80)
print("PART 9: END-OF-DAY POSITION ANALYSIS")
print("=" * 80)

# Last PnL row shows final state
print(f"EMERALDS final PnL: {em400[-1]['profit_and_loss']}")
print(f"TOMATOES final PnL: {tom400[-1]['profit_and_loss']}")

# We can estimate final position from the fill history
# But we don't know buy vs sell direction from PnL alone
# Let's check if the mark-to-market from the graphLog gives clues
graph_lines = sims["42400"]["graphLog"].strip().split("\n")[1:]  # skip header
graph_data = [(int(l.split(";")[0]), float(l.split(";")[1])) for l in graph_lines if l.strip()]
print(f"\nGraph log entries: {len(graph_data)}")
print(f"Final graph PnL: {graph_data[-1][1]:.2f}")
print(f"Max drawdown PnL: {min(v for _, v in graph_data):.2f}")
print(f"Max peak PnL: {max(v for _, v in graph_data):.2f}")

# PnL curve shape
quarter = len(graph_data) // 4
for q in range(4):
    start = q * quarter
    end = (q + 1) * quarter if q < 3 else len(graph_data)
    q_pnl = graph_data[end-1][1] - (graph_data[start][1] if start > 0 else 0)
    print(f"  Q{q+1} PnL: {q_pnl:.1f}")
