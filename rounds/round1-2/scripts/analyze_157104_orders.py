"""Parse lambdaLog to extract our orders per tick and the order book state."""
import json
from collections import Counter, defaultdict

with open('logs/157104/157104.log', 'r') as f:
    data = json.load(f)

logs = data['logs']
trades = data['tradeHistory']

# Parse each tick's lambdaLog
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
    
    # parsed = [state, orders, conversions, trader_data, log_text]
    if not isinstance(parsed, list) or len(parsed) < 2:
        continue
    
    state = parsed[0]
    our_orders = parsed[1]
    
    # state = [timestamp, traderData, listings, order_depths, own_trades, market_trades, position, observations]
    timestamp = state[0]
    order_depths = state[3]
    own_trades = state[4]
    market_trades = state[5]
    position = state[6]
    
    ticks.append({
        'ts': timestamp,
        'order_depths': order_depths,
        'own_trades': own_trades,
        'market_trades': market_trades,
        'position': position,
        'our_orders': our_orders,
    })

print(f"Parsed {len(ticks)} ticks")

# Track our orders for OSM and IPR
print("\n=== OSM ORDER ANALYSIS ===")
osm_bid_prices = []
osm_ask_prices = []
osm_bid_qtys = []
osm_ask_qtys = []

for tick in ticks:
    if 'ASH_COATED_OSMIUM' in tick['our_orders']:
        orders = tick['our_orders']['ASH_COATED_OSMIUM']
        for o in orders:
            price, qty = o[1], o[2]
            if qty > 0:
                osm_bid_prices.append(price)
                osm_bid_qtys.append(qty)
            else:
                osm_ask_prices.append(price)
                osm_ask_qtys.append(abs(qty))

print(f"Bid orders: {len(osm_bid_prices)}, unique prices: {set(osm_bid_prices)}")
print(f"Ask orders: {len(osm_ask_prices)}, unique prices: {set(osm_ask_prices)}")
print(f"Bid price counts: {Counter(osm_bid_prices).most_common()}")
print(f"Ask price counts: {Counter(osm_ask_prices).most_common()}")
print(f"Avg bid qty: {sum(osm_bid_qtys)/max(len(osm_bid_qtys),1):.1f}")
print(f"Avg ask qty: {sum(osm_ask_qtys)/max(len(osm_ask_qtys),1):.1f}")

# Count ticks where we send takes vs makes
osm_take_ticks = 0
osm_multi_order_ticks = 0
for tick in ticks:
    if 'ASH_COATED_OSMIUM' in tick['our_orders']:
        orders = tick['our_orders']['ASH_COATED_OSMIUM']
        if len(orders) > 2:
            osm_multi_order_ticks += 1
        # Check for takes (buy at ask or sell at bid)
        od = tick['order_depths'].get('ASH_COATED_OSMIUM', [None, None])
        if od[0] and od[1]:
            bids, asks = od[0], od[1]
            best_ask = min(int(p) for p in asks.keys()) if asks else None
            best_bid = max(int(p) for p in bids.keys()) if bids else None
            for o in orders:
                price, qty = o[1], o[2]
                if qty > 0 and best_ask and price >= best_ask:
                    osm_take_ticks += 1
                    break
                if qty < 0 and best_bid and price <= best_bid:
                    osm_take_ticks += 1
                    break

print(f"Ticks with takes: {osm_take_ticks}")
print(f"Ticks with >2 orders: {osm_multi_order_ticks}")

# Same for IPR
print("\n=== IPR ORDER ANALYSIS ===")
ipr_bid_prices = []
ipr_ask_prices = []
ipr_bid_qtys = []
ipr_ask_qtys = []

for tick in ticks:
    if 'INTARIAN_PEPPER_ROOT' in tick['our_orders']:
        orders = tick['our_orders']['INTARIAN_PEPPER_ROOT']
        for o in orders:
            price, qty = o[1], o[2]
            if qty > 0:
                ipr_bid_prices.append(price)
                ipr_bid_qtys.append(qty)
            else:
                ipr_ask_prices.append(price)
                ipr_ask_qtys.append(abs(qty))

print(f"Bid orders: {len(ipr_bid_prices)}")
print(f"Ask orders: {len(ipr_ask_prices)}")
print(f"Our bid prices - min: {min(ipr_bid_prices) if ipr_bid_prices else 'N/A'}, max: {max(ipr_bid_prices) if ipr_bid_prices else 'N/A'}")
print(f"Our ask prices - min: {min(ipr_ask_prices) if ipr_ask_prices else 'N/A'}, max: {max(ipr_ask_prices) if ipr_ask_prices else 'N/A'}")

# Compare our orders to book state
print("\n=== ORDER vs BOOK COMPARISON ===")
print("\nFirst 20 ticks detail:")
for tick in ticks[:20]:
    ts = tick['ts']
    pos = tick['position']
    
    for prod in ['ASH_COATED_OSMIUM', 'INTARIAN_PEPPER_ROOT']:
        abbr = 'OSM' if 'OSMIUM' in prod else 'IPR'
        od = tick['order_depths'].get(prod, [None, None])
        if od[0] and od[1]:
            bids, asks = od[0], od[1]
            bb = max(int(p) for p in bids.keys())
            ba = min(int(p) for p in asks.keys())
            spread = ba - bb
            
            # Our orders
            our = tick['our_orders'].get(prod, [])
            our_str = ', '.join(f"{o[1]}x{o[2]}" for o in our)
            
            p = pos.get(prod, 0)
            print(f"  t={ts:5d} {abbr}: book={bb}/{ba} sp={spread:2d} pos={p:3d} | orders: [{our_str}]")

# Analyze the relationship between spread and fills
print("\n\n=== SPREAD vs FILL ANALYSIS ===")
# For each tick, note the spread, and whether we got filled on the NEXT tick
osm_narrow_spread_ticks = 0
osm_wide_spread_ticks = 0

for i, tick in enumerate(ticks[:-1]):
    od = tick['order_depths'].get('ASH_COATED_OSMIUM', [None, None])
    if od[0] and od[1]:
        bids, asks = od[0], od[1]
        bb = max(int(p) for p in bids.keys())
        ba = min(int(p) for p in asks.keys())
        spread = ba - bb
        if spread <= 10:
            osm_narrow_spread_ticks += 1
        else:
            osm_wide_spread_ticks += 1

print(f"OSM narrow spread (<=10): {osm_narrow_spread_ticks} ticks")
print(f"OSM wide spread (>10): {osm_wide_spread_ticks} ticks")

# For OSM, what's the fill rate by spread?
# Build a map of tick -> whether we got filled
osm_filled = set()
for t in trades:
    if t['symbol'] == 'ASH_COATED_OSMIUM':
        osm_filled.add(t['timestamp'])

fill_by_spread = defaultdict(lambda: [0, 0])  # [filled, total]
for tick in ticks:
    od = tick['order_depths'].get('ASH_COATED_OSMIUM', [None, None])
    if od[0] and od[1]:
        bids, asks = od[0], od[1]
        bb = max(int(p) for p in bids.keys())
        ba = min(int(p) for p in asks.keys())
        spread = ba - bb
        # Check if fill happened this tick
        if tick['ts'] in osm_filled:
            fill_by_spread[spread][0] += 1
        fill_by_spread[spread][1] += 1

print("\nOSM fill rate by spread:")
for s in sorted(fill_by_spread.keys()):
    filled, total = fill_by_spread[s]
    print(f"  spread={s:2d}: {filled}/{total} = {100*filled/max(total,1):.1f}%")

# Same for IPR
ipr_filled = set()
for t in trades:
    if t['symbol'] == 'INTARIAN_PEPPER_ROOT':
        ipr_filled.add(t['timestamp'])

ipr_fill_by_spread = defaultdict(lambda: [0, 0])
for tick in ticks:
    od = tick['order_depths'].get('INTARIAN_PEPPER_ROOT', [None, None])
    if od[0] and od[1]:
        bids, asks = od[0], od[1]
        bb = max(int(p) for p in bids.keys())
        ba = min(int(p) for p in asks.keys())
        spread = ba - bb
        if tick['ts'] in ipr_filled:
            ipr_fill_by_spread[spread][0] += 1
        ipr_fill_by_spread[spread][1] += 1

print("\nIPR fill rate by spread:")
for s in sorted(ipr_fill_by_spread.keys()):
    filled, total = ipr_fill_by_spread[s]
    print(f"  spread={s:2d}: {filled}/{total} = {100*filled/max(total,1):.1f}%")

# OSM: analyze where our fills actually come from
print("\n\n=== OSM FILL MECHANICS ===")
# At what spread values do our OSM makes get filled?
osm_make_fills_at_9994 = 0
osm_make_fills_at_10006 = 0
osm_take_fills = 0

# Track all own_trades from next tick
for i, tick in enumerate(ticks):
    ot = tick['own_trades']
    if 'ASH_COATED_OSMIUM' in ot:
        for t in ot['ASH_COATED_OSMIUM']:
            price = t[1]
            qty = t[2]
            buyer = t[3]
            seller = t[4]
            if buyer == 'SUBMISSION':
                if price == 9994:
                    osm_make_fills_at_9994 += 1
                elif price >= 9999:
                    osm_take_fills += 1
            elif seller == 'SUBMISSION':
                if price == 10006:
                    osm_make_fills_at_10006 += 1
                elif price <= 10002:
                    osm_take_fills += 1

print(f"Make fills at 9994 (buy): {osm_make_fills_at_9994}")
print(f"Make fills at 10006 (sell): {osm_make_fills_at_10006}")
print(f"Take fills: {osm_take_fills}")

# Check if there are narrow-spread opportunities we're missing
print("\n\n=== MISSED OPPORTUNITIES ANALYSIS ===")
# For OSM at FV=10000: when ask <= 9999, we should take. When bid >= 10001, we should take.
osm_buy_opps = 0
osm_sell_opps = 0
osm_buy_edge_sum = 0
osm_sell_edge_sum = 0

for tick in ticks:
    od = tick['order_depths'].get('ASH_COATED_OSMIUM', [None, None])
    if od[0] and od[1]:
        asks = od[1]
        bids = od[0]
        for p_str, vol in asks.items():
            p = int(p_str)
            if p <= 9999:
                osm_buy_opps += 1
                osm_buy_edge_sum += (10000 - p) * abs(vol)
        for p_str, vol in bids.items():
            p = int(p_str)
            if p >= 10001:
                osm_sell_opps += 1
                osm_sell_edge_sum += (p - 10000) * vol

print(f"OSM take-buy opportunities (ask<=9999): {osm_buy_opps} ticks")
print(f"OSM take-sell opportunities (bid>=10001): {osm_sell_opps} ticks")
print(f"OSM theoretical buy edge: {osm_buy_edge_sum}")
print(f"OSM theoretical sell edge: {osm_sell_edge_sum}")

# For IPR: when are there narrow spreads?
ipr_narrow = 0
for tick in ticks:
    od = tick['order_depths'].get('INTARIAN_PEPPER_ROOT', [None, None])
    if od[0] and od[1]:
        bids, asks = od[0], od[1]
        bb = max(int(p) for p in bids.keys())
        ba = min(int(p) for p in asks.keys())
        if ba - bb <= 6:  # Within our make width*2
            ipr_narrow += 1

print(f"\nIPR narrow spread (<=6): {ipr_narrow} ticks")

# Position-PnL correlation
print("\n\n=== POSITION EVOLUTION ===")
for i in range(0, len(ticks), 100):
    tick = ticks[i]
    osm_pos = tick['position'].get('ASH_COATED_OSMIUM', 0)
    ipr_pos = tick['position'].get('INTARIAN_PEPPER_ROOT', 0)
    print(f"  t={tick['ts']:5d}: OSM_pos={osm_pos:3d}, IPR_pos={ipr_pos:3d}")
