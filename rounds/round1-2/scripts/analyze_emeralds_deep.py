"""Deep analysis of EMERALDS microstructure from backtester + platform data."""
import csv
import json
from collections import Counter, defaultdict

# ========== PART 1: Backtester Tutorial Data ==========
print("=" * 70)
print("PART 1: BACKTESTER TUTORIAL DATA ANALYSIS")
print("=" * 70)

for day in [-2, -1]:
    fname = f"tutorial-round/data/TUTORIAL_ROUND_1/prices_round_0_day_{day}.csv"
    with open(fname) as f:
        rows = list(csv.DictReader(f, delimiter=";"))

    em = [r for r in rows if r["product"] == "EMERALDS"]
    print(f"\n--- Day {day}: {len(em)} EMERALDS ticks ---")

    bid1_dist = Counter()
    ask1_dist = Counter()
    spread_dist = Counter()
    bid_vol_dist = Counter()

    for r in em:
        b1 = r.get("bid_price_1", "")
        a1 = r.get("ask_price_1", "")
        bv1 = r.get("bid_volume_1", "")
        bid1_dist[b1] += 1
        ask1_dist[a1] += 1
        if bv1:
            bid_vol_dist[int(bv1)] += 1
        if b1 and a1:
            spread_dist[int(a1) - int(b1)] += 1

    print(f"Bid1 levels: {dict(sorted(bid1_dist.items()))}")
    print(f"Ask1 levels: {dict(sorted(ask1_dist.items()))}")
    print(f"Spread dist: {dict(sorted(spread_dist.items()))}")
    print(f"Bid1 vol range: {min(bid_vol_dist.keys())}-{max(bid_vol_dist.keys())}")

    # Check for non-standard ticks (not 9992/10008)
    non_std = [r for r in em if r.get("bid_price_1", "") not in ("9992", "9996", "9997", "9998") 
               or r.get("ask_price_1", "") not in ("10008", "10004", "10003", "10002")]


# ========== PART 2: Trade Data Analysis ==========
print("\n" + "=" * 70)
print("PART 2: TRADE DATA ANALYSIS")
print("=" * 70)

for day in [-2, -1]:
    fname = f"tutorial-round/data/TUTORIAL_ROUND_1/trades_round_0_day_{day}.csv"
    with open(fname) as f:
        rows = list(csv.DictReader(f, delimiter=";"))

    em = [r for r in rows if r["symbol"] == "EMERALDS"]
    print(f"\n--- Day {day}: {len(em)} EMERALDS trades ---")

    prices = Counter()
    buyers = Counter()
    sellers = Counter()
    for r in em:
        prices[int(float(r["price"]))] += 1
        buyers[r.get("buyer", "")] += 1
        sellers[r.get("seller", "")] += 1

    print(f"Price dist: {dict(sorted(prices.items()))}")
    print(f"Buyers: {dict(sorted(buyers.items()))}")
    print(f"Sellers: {dict(sorted(sellers.items()))}")

    # Show sample trades
    print("Sample trades:")
    for r in em[:15]:
        ts = r["timestamp"]
        p = r["price"]
        q = r["quantity"]
        buyer = r.get("buyer", "")
        seller = r.get("seller", "")
        print(f"  t={ts} p={p} q={q} buyer={buyer} seller={seller}")


# ========== PART 3: Platform Log Deep Analysis ==========
print("\n" + "=" * 70)
print("PART 3: PLATFORM LOG DEEP ANALYSIS (42349)")
print("=" * 70)

with open("logs/42349/42349.json") as f:
    data = json.load(f)

rows = list(csv.DictReader(data["activitiesLog"].splitlines(), delimiter=";"))
em = [r for r in rows if r["product"] == "EMERALDS"]

# Non-standard tick analysis - what are these 10000 levels?
non_std_bids = [r for r in em if r["bid_price_1"] == "10000"]
non_std_asks = [r for r in em if r["ask_price_1"] == "10000"]

print(f"\nTicks with bid at 10000: {len(non_std_bids)}")
print(f"Ticks with ask at 10000: {len(non_std_asks)}")

# Volume distribution on non-standard bid ticks
bid_10k_vols = Counter()
for r in non_std_bids:
    bid_10k_vols[int(r["bid_volume_1"])] += 1
print(f"Bid@10000 volume dist: {dict(sorted(bid_10k_vols.items()))}")

ask_10k_vols = Counter()
for r in non_std_asks:
    ask_10k_vols[int(r["ask_volume_1"])] += 1
print(f"Ask@10000 volume dist: {dict(sorted(ask_10k_vols.items()))}")

# PnL change analysis with position tracking
pnl_changes = []
prev_pnl = 0.0
for r in em:
    pnl = float(r["profit_and_loss"])
    if pnl != prev_pnl:
        pnl_changes.append((int(r["timestamp"]), pnl - prev_pnl, pnl))
    prev_pnl = pnl

print(f"\n--- Fill Events: {len(pnl_changes)} ---")
print(f"Total PnL: {sum(d for _, d, _ in pnl_changes):.0f}")
print(f"Fill sizes: {[int(d) for _, d, _ in pnl_changes]}")
print(f"Min fill: {min(d for _, d, _ in pnl_changes):.0f}")
print(f"Max fill: {max(d for _, d, _ in pnl_changes):.0f}")
print(f"Avg fill: {sum(d for _, d, _ in pnl_changes)/len(pnl_changes):.1f}")

# Timing analysis between fills
fill_timestamps = [ts for ts, _, _ in pnl_changes]
gaps = [fill_timestamps[i+1] - fill_timestamps[i] for i in range(len(fill_timestamps)-1)]
print(f"\nGap between fills (ticks):")
print(f"  Min: {min(gaps)/100:.0f}")
print(f"  Max: {max(gaps)/100:.0f}")
print(f"  Mean: {sum(gaps)/len(gaps)/100:.0f}")
print(f"  Median: {sorted(gaps)[len(gaps)//2]/100:.0f}")

# Check bot volume at 9992/9990 on fill ticks vs non-fill ticks
fill_ts_set = set(ts for ts, _, _ in pnl_changes)
fill_vols = []
nonfill_vols = []
for r in em:
    ts = int(r["timestamp"])
    bv1 = int(r["bid_volume_1"]) if r["bid_volume_1"] else 0
    av1 = int(r["ask_volume_1"]) if r["ask_volume_1"] else 0
    if ts in fill_ts_set:
        fill_vols.append((bv1, av1))
    else:
        nonfill_vols.append((bv1, av1))

print(f"\nBot L1 volume on fill ticks vs non-fill ticks:")
fill_bv = [v[0] for v in fill_vols]
fill_av = [v[1] for v in fill_vols]
nf_bv = [v[0] for v in nonfill_vols]
nf_av = [v[1] for v in nonfill_vols]
print(f"  Fill ticks - bid vol: min={min(fill_bv)} max={max(fill_bv)} avg={sum(fill_bv)/len(fill_bv):.1f}")
print(f"  Fill ticks - ask vol: min={min(fill_av)} max={max(fill_av)} avg={sum(fill_av)/len(fill_av):.1f}")
print(f"  Non-fill ticks - bid vol: avg={sum(nf_bv)/len(nf_bv):.1f}")
print(f"  Non-fill ticks - ask vol: avg={sum(nf_av)/len(nf_av):.1f}")


# ========== PART 4: Cross-sim comparison ==========
print("\n" + "=" * 70)
print("PART 4: IS THERE AN EARLIER SIM WITH DIFFERENT STRATEGY?")
print("=" * 70)

# Check if we have other sim logs
import os
log_dirs = [d for d in os.listdir("logs") if os.path.isdir(f"logs/{d}")]
print(f"Available sims: {sorted(log_dirs)}")

# Compare fill patterns across sims
for sim_dir in sorted(log_dirs):
    json_path = f"logs/{sim_dir}/{sim_dir}.json"
    if not os.path.exists(json_path):
        continue
    with open(json_path) as f:
        sdata = json.load(f)
    
    srows = list(csv.DictReader(sdata["activitiesLog"].splitlines(), delimiter=";"))
    sem = [r for r in srows if r["product"] == "EMERALDS"]
    
    s_pnl_changes = []
    s_prev = 0.0
    for r in sem:
        pnl = float(r["profit_and_loss"])
        if pnl != s_prev:
            s_pnl_changes.append((int(r["timestamp"]), pnl - s_prev))
        s_prev = pnl
    
    fill_ts = [ts for ts, _ in s_pnl_changes]
    fill_sizes = [int(d) for _, d in s_pnl_changes]
    total = sum(fill_sizes)
    
    # Count non-standard ticks
    ns_count = sum(1 for r in sem if r["bid_price_1"] != "9992" or r["ask_price_1"] != "10008")
    
    print(f"  Sim {sim_dir}: {len(s_pnl_changes)} fills, total={total}, NS ticks={ns_count}")
    print(f"    Fill ticks: {fill_ts[:10]}...")
    print(f"    Fill sizes: {fill_sizes[:10]}...")
