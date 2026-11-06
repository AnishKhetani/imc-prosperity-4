"""Simulate adaptive pricing on 157104 platform data to estimate improvement."""
import json
from collections import Counter

with open('logs/157104/157104.log', 'r') as f:
    data = json.load(f)

logs = data['logs']
trades = data['tradeHistory']

# Parse ticks
ticks = []
for entry in logs:
    ts = entry['timestamp']
    ll = entry['lambdaLog']
    if not ll:
        continue
    try:
        parsed = json.loads(ll)
    except:
        continue
    if not isinstance(parsed, list) or len(parsed) < 2:
        continue
    state = parsed[0]
    ticks.append({
        'ts': state[0],
        'order_depths': state[3],
        'position': state[6],
    })

# === SIMULATE ADAPTIVE OSM ===
print("=" * 60)
print("SIMULATED ADAPTIVE vs ACTUAL FIXED OSM")
print("=" * 60)

osm_adaptive_bids = []
osm_adaptive_asks = []
osm_fixed_bids = []
osm_fixed_asks = []

FV = 10000
FIXED_WIDTH = 6

for tick in ticks:
    od = tick['order_depths'].get('ASH_COATED_OSMIUM')
    if not od:
        continue
    bids, asks = od[0], od[1]
    if not bids or not asks:
        continue
    
    # Integer keys
    bid_keys = [int(p) for p in bids.keys()]
    ask_keys = [int(p) for p in asks.keys()]
    
    # Remaining levels (not taken)
    remaining_bids = sorted([p for p in bid_keys if p < FV + 1], reverse=True)
    remaining_asks = sorted([p for p in ask_keys if p > FV - 1])
    
    # Adaptive pricing
    if remaining_bids:
        adaptive_bid = min(remaining_bids[0] + 1, FV - 1)
        osm_adaptive_bids.append(adaptive_bid)
    if remaining_asks:
        adaptive_ask = max(remaining_asks[0] - 1, FV + 1)
        osm_adaptive_asks.append(adaptive_ask)
    
    # Fixed pricing
    osm_fixed_bids.append(FV - FIXED_WIDTH)
    osm_fixed_asks.append(FV + FIXED_WIDTH)

# Compare
print(f"\nAdaptive bid distribution (n={len(osm_adaptive_bids)}):")
bc = Counter(osm_adaptive_bids)
for p in sorted(bc.keys()):
    print(f"  {p}: {bc[p]:4d} ({bc[p]/len(osm_adaptive_bids)*100:5.1f}%)")

print(f"\nAdaptive ask distribution (n={len(osm_adaptive_asks)}):")
ac = Counter(osm_adaptive_asks)
for p in sorted(ac.keys()):
    print(f"  {p}: {ac[p]:4d} ({ac[p]/len(osm_adaptive_asks)*100:5.1f}%)")

# Fixed pricing (always same)
print(f"\nFixed bid always: {FV - FIXED_WIDTH} ({len(osm_fixed_bids)} ticks)")
print(f"Fixed ask always: {FV + FIXED_WIDTH} ({len(osm_fixed_asks)} ticks)")

# Compare: how often is adaptive strictly better than fixed?
print("\n--- COMPARATIVE ANALYSIS ---")
better_bid = sum(1 for i in range(len(osm_adaptive_bids)) if osm_adaptive_bids[i] < osm_fixed_bids[i])
same_bid = sum(1 for i in range(len(osm_adaptive_bids)) if osm_adaptive_bids[i] == osm_fixed_bids[i])
worse_bid = sum(1 for i in range(len(osm_adaptive_bids)) if osm_adaptive_bids[i] > osm_fixed_bids[i])

print(f"Bid: adaptive < fixed (MORE edge): {better_bid} ({better_bid/len(osm_adaptive_bids)*100:.1f}%)")
print(f"Bid: adaptive = fixed (SAME): {same_bid} ({same_bid/len(osm_adaptive_bids)*100:.1f}%)")
print(f"Bid: adaptive > fixed (LESS edge): {worse_bid} ({worse_bid/len(osm_adaptive_bids)*100:.1f}%)")

better_ask = sum(1 for i in range(min(len(osm_adaptive_asks), len(osm_fixed_asks))) if osm_adaptive_asks[i] > osm_fixed_asks[i])
same_ask = sum(1 for i in range(min(len(osm_adaptive_asks), len(osm_fixed_asks))) if osm_adaptive_asks[i] == osm_fixed_asks[i])
worse_ask = sum(1 for i in range(min(len(osm_adaptive_asks), len(osm_fixed_asks))) if osm_adaptive_asks[i] < osm_fixed_asks[i])

print(f"Ask: adaptive > fixed (MORE edge): {better_ask} ({better_ask/len(osm_adaptive_asks)*100:.1f}%)")
print(f"Ask: adaptive = fixed (SAME): {same_ask} ({same_ask/len(osm_adaptive_asks)*100:.1f}%)")
print(f"Ask: adaptive < fixed (LESS edge): {worse_ask} ({worse_ask/len(osm_adaptive_asks)*100:.1f}%)")

# Estimate PnL improvement from edge differences
# For each tick where both strategies are best bid/ask, compare the edge
total_adaptive_bid_edge = sum(FV - b for b in osm_adaptive_bids)
total_fixed_bid_edge = sum(FV - b for b in osm_fixed_bids[:len(osm_adaptive_bids)])
print(f"\nTotal bid edge - adaptive: {total_adaptive_bid_edge}, fixed: {total_fixed_bid_edge}")
print(f"Avg bid edge - adaptive: {total_adaptive_bid_edge/len(osm_adaptive_bids):.1f}, fixed: {total_fixed_bid_edge/len(osm_fixed_bids):.1f}")

total_adaptive_ask_edge = sum(a - FV for a in osm_adaptive_asks)
total_fixed_ask_edge = sum(a - FV for a in osm_fixed_asks[:len(osm_adaptive_asks)])
print(f"Total ask edge - adaptive: {total_adaptive_ask_edge}, fixed: {total_fixed_ask_edge}")
print(f"Avg ask edge - adaptive: {total_adaptive_ask_edge/len(osm_adaptive_asks):.1f}, fixed: {total_fixed_ask_edge/len(osm_fixed_asks):.1f}")

# Check: how often is adaptive best bid (above all bot bids)?
adaptive_is_best_bid = 0
fixed_is_best_bid = 0
for i, tick in enumerate(ticks):
    od = tick['order_depths'].get('ASH_COATED_OSMIUM')
    if not od: continue
    bids = od[0]
    if not bids: continue
    bot_best_bid = max(int(p) for p in bids.keys())
    if i < len(osm_adaptive_bids) and osm_adaptive_bids[i] > bot_best_bid:
        adaptive_is_best_bid += 1
    if osm_fixed_bids[0] > bot_best_bid:
        fixed_is_best_bid += 1

print(f"\nAdaptive is best bid: {adaptive_is_best_bid}/{len(osm_adaptive_bids)} ({adaptive_is_best_bid/len(osm_adaptive_bids)*100:.1f}%)")
print(f"Fixed is best bid: {fixed_is_best_bid}/{len(osm_fixed_bids)} ({fixed_is_best_bid/len(osm_fixed_bids)*100:.1f}%)")

adaptive_is_best_ask = 0
fixed_is_best_ask = 0
for i, tick in enumerate(ticks):
    od = tick['order_depths'].get('ASH_COATED_OSMIUM')
    if not od: continue
    asks = od[1]
    if not asks: continue
    bot_best_ask = min(int(p) for p in asks.keys())
    if i < len(osm_adaptive_asks) and osm_adaptive_asks[i] < bot_best_ask:
        adaptive_is_best_ask += 1
    if osm_fixed_asks[0] < bot_best_ask:
        fixed_is_best_ask += 1

print(f"Adaptive is best ask: {adaptive_is_best_ask}/{len(osm_adaptive_asks)} ({adaptive_is_best_ask/len(osm_adaptive_asks)*100:.1f}%)")
print(f"Fixed is best ask: {fixed_is_best_ask}/{len(osm_fixed_asks)} ({fixed_is_best_ask/len(osm_fixed_asks)*100:.1f}%)")

# === SIMULATE ADAPTIVE IPR ===
print("\n\n" + "=" * 60)
print("SIMULATED ADAPTIVE vs FIXED WIDTH=3 IPR")
print("=" * 60)

ipr_adaptive_bids = []
ipr_adaptive_asks = []
ipr_fixed_bids = []
ipr_fixed_asks = []
ipr_fairs = []

SKEW = 0.2
TAKE_EDGE = 1
FIXED_IPR_WIDTH = 3

for tick in ticks:
    od = tick['order_depths'].get('INTARIAN_PEPPER_ROOT')
    if not od: continue
    bids, asks = od[0], od[1]
    if not bids or not asks: continue
    
    bid_keys = {int(p): v for p, v in bids.items()}
    ask_keys = {int(p): v for p, v in asks.items()}
    
    bb = max(bid_keys.keys())
    ba = min(ask_keys.keys())
    bv = bid_keys[bb]
    av = abs(ask_keys[ba])
    total = bv + av
    wmid = (bb * av + ba * bv) / total if total > 0 else (bb + ba) / 2
    
    pos = tick['position'].get('INTARIAN_PEPPER_ROOT', 0)
    fair = round(wmid - SKEW * pos)
    ipr_fairs.append(fair)
    
    # Remaining levels
    remaining_bids = sorted([p for p in bid_keys if p < fair + TAKE_EDGE], reverse=True)
    remaining_asks = sorted([p for p in ask_keys if p > fair - TAKE_EDGE])
    
    if remaining_bids:
        adaptive_bid = min(remaining_bids[0] + 1, fair - 1)
        ipr_adaptive_bids.append(adaptive_bid)
    if remaining_asks:
        adaptive_ask = max(remaining_asks[0] - 1, fair + 1)
        ipr_adaptive_asks.append(adaptive_ask)
    
    ipr_fixed_bids.append(fair - FIXED_IPR_WIDTH)
    ipr_fixed_asks.append(fair + FIXED_IPR_WIDTH)

if ipr_adaptive_bids:
    avg_adaptive_bid_edge = sum(ipr_fairs[i] - ipr_adaptive_bids[i] for i in range(min(len(ipr_fairs), len(ipr_adaptive_bids)))) / len(ipr_adaptive_bids)
    avg_fixed_bid_edge = sum(ipr_fairs[i] - ipr_fixed_bids[i] for i in range(min(len(ipr_fairs), len(ipr_fixed_bids)))) / len(ipr_fixed_bids)
    
    avg_adaptive_ask_edge = sum(ipr_adaptive_asks[i] - ipr_fairs[i] for i in range(min(len(ipr_fairs), len(ipr_adaptive_asks)))) / len(ipr_adaptive_asks)
    avg_fixed_ask_edge = FIXED_IPR_WIDTH
    
    print(f"Avg IPR adaptive bid edge from fair: {avg_adaptive_bid_edge:.1f} (fixed: {avg_fixed_bid_edge:.1f})")
    print(f"Avg IPR adaptive ask edge from fair: {avg_adaptive_ask_edge:.1f} (fixed: {avg_fixed_ask_edge:.1f})")
    print(f"Avg IPR round-trip edge: adaptive={avg_adaptive_bid_edge+avg_adaptive_ask_edge:.1f}, fixed={avg_fixed_bid_edge+avg_fixed_ask_edge:.1f}")

# Check best-quote status for IPR
ipr_adaptive_best_bid = 0
ipr_fixed_best_bid = 0
idx = 0
for tick in ticks:
    od = tick['order_depths'].get('INTARIAN_PEPPER_ROOT')
    if not od: continue
    bids = od[0]
    if not bids: continue
    bot_best_bid = max(int(p) for p in bids.keys())
    if idx < len(ipr_adaptive_bids) and ipr_adaptive_bids[idx] > bot_best_bid:
        ipr_adaptive_best_bid += 1
    if idx < len(ipr_fixed_bids) and ipr_fixed_bids[idx] > bot_best_bid:
        ipr_fixed_best_bid += 1
    idx += 1

print(f"\nIPR adaptive is best bid: {ipr_adaptive_best_bid}/{len(ipr_adaptive_bids)} ({ipr_adaptive_best_bid/max(len(ipr_adaptive_bids),1)*100:.1f}%)")
print(f"IPR fixed is best bid: {ipr_fixed_best_bid}/{len(ipr_fixed_bids)} ({ipr_fixed_best_bid/max(len(ipr_fixed_bids),1)*100:.1f}%)")
