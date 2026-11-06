"""Precise analysis of bot bid/ask distribution and optimal WIDTH."""
import json
from collections import Counter, defaultdict

with open('logs/157104/157104.log', 'r') as f:
    data = json.load(f)

logs = data['logs']
trades = data['tradeHistory']

# Parse lambdaLog from each tick
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
    our_orders = parsed[1]
    ticks.append({
        'ts': state[0],
        'order_depths': state[3],
        'position': state[6],
        'our_orders': our_orders,
    })

print(f"Parsed {len(ticks)} ticks")

# ===== OSM BOT BID/ASK DISTRIBUTION =====
print("\n" + "="*60)
print("OSM BOT ORDER BOOK ANALYSIS")
print("="*60)

osm_bot_bids = []
osm_bot_asks = []
osm_spreads = []

for tick in ticks:
    od = tick['order_depths'].get('ASH_COATED_OSMIUM')
    if not od:
        continue
    bids, asks = od[0], od[1]
    if bids and asks:
        bb = max(int(p) for p in bids.keys())
        ba = min(int(p) for p in asks.keys())
        osm_bot_bids.append(bb)
        osm_bot_asks.append(ba)
        osm_spreads.append(ba - bb)

print(f"\nBot Best Bid distribution (n={len(osm_bot_bids)}):")
bid_counts = Counter(osm_bot_bids)
for p in sorted(bid_counts.keys()):
    pct = bid_counts[p] / len(osm_bot_bids) * 100
    print(f"  {p}: {bid_counts[p]:4d} ({pct:5.1f}%)")

print(f"\nBot Best Ask distribution (n={len(osm_bot_asks)}):")
ask_counts = Counter(osm_bot_asks)
for p in sorted(ask_counts.keys()):
    pct = ask_counts[p] / len(osm_bot_asks) * 100
    print(f"  {p}: {ask_counts[p]:4d} ({pct:5.1f}%)")

# Compute optimal WIDTH
print("\n--- WIDTH ANALYSIS FOR OSM ---")
for width in range(3, 10):
    bid_price = 10000 - width
    ask_price = 10000 + width
    
    # Count how often we'd be best bid/ask
    best_bid_pct = sum(1 for bb in osm_bot_bids if bb < bid_price) / len(osm_bot_bids)
    tied_bid_pct = sum(1 for bb in osm_bot_bids if bb == bid_price) / len(osm_bot_bids)
    best_ask_pct = sum(1 for ba in osm_bot_asks if ba > ask_price) / len(osm_bot_asks)
    tied_ask_pct = sum(1 for ba in osm_bot_asks if ba == ask_price) / len(osm_bot_asks)
    
    # Effective fill rate: best = full, tied = ~0% (bot priority), worse = 0%
    effective_bid = best_bid_pct
    effective_ask = best_ask_pct
    
    # Expected PnL per tick (relative, assumes same qty per fill)
    edge = 2 * width
    expected = (effective_bid + effective_ask) * edge
    
    print(f"  WIDTH={width}: bid={bid_price}, ask={ask_price}")
    print(f"    Best bid: {best_bid_pct*100:5.1f}%, tied: {tied_bid_pct*100:5.1f}%")
    print(f"    Best ask: {best_ask_pct*100:5.1f}%, tied: {tied_ask_pct*100:5.1f}%")
    print(f"    Expected score: {expected:.2f} (edge={edge} x activity={effective_bid+effective_ask:.3f})")

# ===== IPR BOT BID/ASK DISTRIBUTION =====
print("\n" + "="*60)
print("IPR BOT ORDER BOOK ANALYSIS")
print("="*60)

ipr_bot_bids = []
ipr_bot_asks = []
ipr_spreads = []
ipr_wmids = []

for tick in ticks:
    od = tick['order_depths'].get('INTARIAN_PEPPER_ROOT')
    if not od:
        continue
    bids, asks = od[0], od[1]
    if bids and asks:
        bb = max(int(p) for p in bids.keys())
        ba = min(int(p) for p in asks.keys())
        bv = bids[str(bb)]
        av = abs(asks[str(ba)])
        total = bv + av
        if total > 0:
            wmid = (bb * av + ba * bv) / total
        else:
            wmid = (bb + ba) / 2
        
        ipr_bot_bids.append(bb)
        ipr_bot_asks.append(ba)
        ipr_spreads.append(ba - bb)
        ipr_wmids.append(wmid)

print(f"\nIPR Spread distribution:")
spread_counts = Counter(ipr_spreads)
for s in sorted(spread_counts.keys()):
    pct = spread_counts[s] / len(ipr_spreads) * 100
    print(f"  {s}: {spread_counts[s]:4d} ({pct:5.1f}%)")

# For IPR, compute how often our bid/ask is inside bot spread
# Our bid = round(wmid) - width, our ask = round(wmid) + width
print("\n--- WIDTH ANALYSIS FOR IPR ---")
for width in range(2, 8):
    inside_bid = 0
    inside_ask = 0
    tied_bid = 0
    tied_ask = 0
    total = len(ipr_wmids)
    
    for i in range(total):
        fair = round(ipr_wmids[i])
        our_bid = fair - width
        our_ask = fair + width
        bb = ipr_bot_bids[i]
        ba = ipr_bot_asks[i]
        
        if our_bid > bb:
            inside_bid += 1
        elif our_bid == bb:
            tied_bid += 1
            
        if our_ask < ba:
            inside_ask += 1
        elif our_ask == ba:
            tied_ask += 1
    
    edge = 2 * width
    effective_bid = inside_bid / total
    effective_ask = inside_ask / total
    expected = (effective_bid + effective_ask) * edge
    
    print(f"  WIDTH={width}: spread=2*{width}={2*width}")
    print(f"    Best bid: {inside_bid/total*100:5.1f}%, tied: {tied_bid/total*100:5.1f}%")
    print(f"    Best ask: {inside_ask/total*100:5.1f}%, tied: {tied_ask/total*100:5.1f}%")
    print(f"    Expected score: {expected:.2f}")

# ===== COMPARE OSM WIDTH=6 vs actual fills =====
print("\n" + "="*60)
print("VALIDATION: OSM WIDTH=6 PREDICTIONS vs ACTUAL")
print("="*60)

# Our current WIDTH=6: bid at 9994, ask at 10006
# We should fill when our bid is best (bot bid < 9994) AND a taker sells
osm_our_best_bid = sum(1 for bb in osm_bot_bids if bb < 9994)
osm_tied_bid = sum(1 for bb in osm_bot_bids if bb == 9994)
print(f"Our bid at 9994 is best: {osm_our_best_bid} ticks ({osm_our_best_bid/len(osm_bot_bids)*100:.1f}%)")
print(f"Our bid at 9994 is tied: {osm_tied_bid} ticks ({osm_tied_bid/len(osm_bot_bids)*100:.1f}%)")

osm_our_best_ask = sum(1 for ba in osm_bot_asks if ba > 10006)
osm_tied_ask = sum(1 for ba in osm_bot_asks if ba == 10006)
print(f"Our ask at 10006 is best: {osm_our_best_ask} ticks ({osm_our_best_ask/len(osm_bot_asks)*100:.1f}%)")
print(f"Our ask at 10006 is tied: {osm_tied_ask} ticks ({osm_tied_ask/len(osm_bot_asks)*100:.1f}%)")

# Count actual make fills at 9994 and 10006
make_buys_9994 = [t for t in trades if t['symbol']=='ASH_COATED_OSMIUM' and t['buyer']=='SUBMISSION' and t['price']==9994]
make_sells_10006 = [t for t in trades if t['symbol']=='ASH_COATED_OSMIUM' and t['seller']=='SUBMISSION' and t['price']==10006]
print(f"\nActual make fills at 9994: {len(make_buys_9994)} trades, qty={sum(t['quantity'] for t in make_buys_9994)}")
print(f"Actual make fills at 10006: {len(make_sells_10006)} trades, qty={sum(t['quantity'] for t in make_sells_10006)}")

print(f"\nTotal OSM our best or tied bid ticks: {osm_our_best_bid + osm_tied_bid}")
print(f"Total OSM fills: {len([t for t in trades if t['symbol']=='ASH_COATED_OSMIUM'])}")

# What about take fills?
osm_take_buys = [t for t in trades if t['symbol']=='ASH_COATED_OSMIUM' and t['buyer']=='SUBMISSION' and t['price']>9994]
osm_take_sells = [t for t in trades if t['symbol']=='ASH_COATED_OSMIUM' and t['seller']=='SUBMISSION' and t['price']<10006]
print(f"\nTake fills (buy > 9994): {len(osm_take_buys)} trades at prices {set(t['price'] for t in osm_take_buys)}")
print(f"Take fills (sell < 10006): {len(osm_take_sells)} trades at prices {set(t['price'] for t in osm_take_sells)}")

# ===== KEY INSIGHT: How do bot bids relate to bot asks? =====
print("\n" + "="*60)
print("OSM BOOK PLACEMENT ANALYSIS")
print("="*60)
# Show bot bid + ask together
bid_ask_pairs = Counter(zip(osm_bot_bids, osm_bot_asks))
print("\nBot (bid, ask) pair frequencies:")
for (b, a), count in sorted(bid_ask_pairs.items(), key=lambda x: -x[1])[:20]:
    print(f"  bid={b}, ask={a}, spread={a-b}: {count} ({count/len(osm_bot_bids)*100:.1f}%)")
