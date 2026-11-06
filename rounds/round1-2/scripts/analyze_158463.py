"""Comprehensive analysis of 158463 platform submission — adaptive pricing."""
import json
import csv
import io
from collections import Counter, defaultdict

# ===== JSON LOG (activities, PnL) =====
with open('logs/158463/158463.json', 'r') as f:
    jdata = json.load(f)

print("=" * 60)
print("158463 SUBMISSION ANALYSIS")
print("=" * 60)
print(f"Total Profit: {jdata['profit']}")
print(f"Status: {jdata['status']}")

print("\n--- POSITIONS ---")
for p in jdata['positions']:
    print(f"  {p}")

# Activities
reader = csv.DictReader(io.StringIO(jdata['activitiesLog']), delimiter=';')
records = list(reader)
products = sorted(set(r['product'] for r in records))
days = sorted(set(r['day'] for r in records))
print(f"\nRecords: {len(records)}, Products: {products}, Days: {days}")

for prod in products:
    pr = [r for r in records if r['product'] == prod]
    last = pr[-1]
    print(f"  {prod}: PnL={last['profit_and_loss']}, final_mid={last['mid_price']}")

# Spread analysis
print("\n--- SPREAD ANALYSIS ---")
for prod in products:
    pr = [r for r in records if r['product'] == prod]
    spreads = []
    for r in pr:
        if r['bid_price_1'] and r['ask_price_1']:
            try:
                spreads.append(float(r['ask_price_1']) - float(r['bid_price_1']))
            except: pass
    if spreads:
        sc = Counter(spreads)
        print(f"  {prod}: mean={sum(spreads)/len(spreads):.1f}, n={len(spreads)}")
        for s in sorted(sc.keys()):
            pct = sc[s]/len(spreads)*100
            if pct >= 1:
                print(f"    {s:.0f}: {sc[s]} ({pct:.1f}%)")

# PnL curve
graph_lines = jdata['graphLog'].strip().split('\n')
graph_data = []
for line in graph_lines[1:]:
    parts = line.split(';')
    if len(parts) == 2:
        graph_data.append((int(parts[0]), float(parts[1])))
print(f"\n--- PNL CURVE ---")
for ts, pnl in graph_data[::50]:
    print(f"  t={ts:6d}: {pnl:.1f}")
if graph_data:
    print(f"  FINAL: t={graph_data[-1][0]}: {graph_data[-1][1]:.2f}")

# ===== LOG FILE (trades, per-tick data) =====
with open('logs/158463/158463.log', 'r') as f:
    ldata = json.load(f)

trades = ldata['tradeHistory']
logs = ldata['logs']
print(f"\n--- TRADES ---")
print(f"Total trades: {len(trades)}")

for prod in ['ASH_COATED_OSMIUM', 'INTARIAN_PEPPER_ROOT']:
    abbr = 'OSM' if 'OSMIUM' in prod else 'IPR'
    pt = [t for t in trades if t['symbol'] == prod]
    buys = [t for t in pt if t['buyer'] == 'SUBMISSION']
    sells = [t for t in pt if t['seller'] == 'SUBMISSION']
    print(f"\n  {abbr}: {len(pt)} trades")
    print(f"    Buys: {len(buys)}, qty={sum(t['quantity'] for t in buys)}")
    print(f"    Sells: {len(sells)}, qty={sum(t['quantity'] for t in sells)}")
    
    if buys:
        bp = Counter(t['price'] for t in buys)
        print(f"    Buy prices:")
        for p in sorted(bp.keys()):
            q = sum(t['quantity'] for t in buys if t['price'] == p)
            print(f"      {p}: {bp[p]} trades, qty={q}")
    if sells:
        sp = Counter(t['price'] for t in sells)
        print(f"    Sell prices:")
        for p in sorted(sp.keys()):
            q = sum(t['quantity'] for t in sells if t['price'] == p)
            print(f"      {p}: {sp[p]} trades, qty={q}")

# Parse per-tick lambdaLog
ticks = []
for entry in logs:
    ll = entry.get('lambdaLog', '')
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

print(f"\nParsed {len(ticks)} ticks")

# Our order prices
print("\n--- OUR ORDER PLACEMENT ---")
for prod in ['ASH_COATED_OSMIUM', 'INTARIAN_PEPPER_ROOT']:
    abbr = 'OSM' if 'OSMIUM' in prod else 'IPR'
    bid_prices = []
    ask_prices = []
    for tick in ticks:
        if prod in tick['our_orders']:
            for o in tick['our_orders'][prod]:
                if o[2] > 0:
                    bid_prices.append(o[1])
                else:
                    ask_prices.append(o[1])
    
    print(f"\n  {abbr}:")
    if bid_prices:
        bc = Counter(bid_prices)
        print(f"    Bid orders: {len(bid_prices)}, unique prices: {len(bc)}")
        print(f"    Bid distribution (top 10):")
        for p, c in sorted(bc.items()):
            if c >= 5:
                print(f"      {p}: {c} ({c/len(bid_prices)*100:.1f}%)")
    if ask_prices:
        ac = Counter(ask_prices)
        print(f"    Ask orders: {len(ask_prices)}, unique prices: {len(ac)}")
        print(f"    Ask distribution (top 10):")
        for p, c in sorted(ac.items()):
            if c >= 5:
                print(f"      {p}: {c} ({c/len(ask_prices)*100:.1f}%)")

# Position analysis
print("\n--- POSITION ANALYSIS ---")
for prod in ['ASH_COATED_OSMIUM', 'INTARIAN_PEPPER_ROOT']:
    abbr = 'OSM' if 'OSMIUM' in prod else 'IPR'
    positions = [tick['position'].get(prod, 0) for tick in ticks]
    if positions:
        print(f"  {abbr}: min={min(positions)}, max={max(positions)}, mean={sum(positions)/len(positions):.1f}")
        at_neg_limit = sum(1 for p in positions if p <= -50)
        at_pos_limit = sum(1 for p in positions if p >= 50)
        print(f"    At -50: {at_neg_limit} ({at_neg_limit/len(positions)*100:.1f}%)")
        print(f"    At +50: {at_pos_limit} ({at_pos_limit/len(positions)*100:.1f}%)")

# Compare with 157104
print("\n\n--- COMPARISON WITH 157104 ---")
print(f"  158463 profit: {jdata['profit']}")
try:
    with open('logs/157104/157104.json', 'r') as f:
        j157 = json.load(f)
    print(f"  157104 profit: {j157['profit']}")
    print(f"  Improvement: {jdata['profit'] - j157['profit']:.2f}")
except:
    print("  (157104 data not available)")

# Bot order book analysis for width insight
print("\n--- BOT ORDER BOOK ANALYSIS ---")
for prod in ['ASH_COATED_OSMIUM', 'INTARIAN_PEPPER_ROOT']:
    abbr = 'OSM' if 'OSMIUM' in prod else 'IPR'
    bot_bids = []
    bot_asks = []
    for tick in ticks:
        od = tick['order_depths'].get(prod)
        if not od:
            continue
        bids, asks = od[0], od[1]
        if bids and asks:
            bb = max(int(p) for p in bids.keys())
            ba = min(int(p) for p in asks.keys())
            bot_bids.append(bb)
            bot_asks.append(ba)
    if bot_bids:
        print(f"\n  {abbr} bot best bid: mean={sum(bot_bids)/len(bot_bids):.1f}")
        bc = Counter(bot_bids)
        for p in sorted(bc.keys()):
            if bc[p] >= 5:
                print(f"    {p}: {bc[p]} ({bc[p]/len(bot_bids)*100:.1f}%)")
    if bot_asks:
        print(f"  {abbr} bot best ask: mean={sum(bot_asks)/len(bot_asks):.1f}")
        ac = Counter(bot_asks)
        for p in sorted(ac.keys()):
            if ac[p] >= 5:
                print(f"    {p}: {ac[p]} ({ac[p]/len(bot_asks)*100:.1f}%)")

# Fill rate analysis - at which spreads do we fill?
print("\n--- FILL RATE BY SPREAD ---")
for prod in ['ASH_COATED_OSMIUM', 'INTARIAN_PEPPER_ROOT']:
    abbr = 'OSM' if 'OSMIUM' in prod else 'IPR'
    filled_ts = set(t['timestamp'] for t in trades if t['symbol'] == prod)
    fill_by_spread = defaultdict(lambda: [0, 0])
    for tick in ticks:
        od = tick['order_depths'].get(prod)
        if not od:
            continue
        bids, asks = od[0], od[1]
        if bids and asks:
            bb = max(int(p) for p in bids.keys())
            ba = min(int(p) for p in asks.keys())
            spread = ba - bb
            if tick['ts'] in filled_ts:
                fill_by_spread[spread][0] += 1
            fill_by_spread[spread][1] += 1
    
    print(f"\n  {abbr}:")
    for s in sorted(fill_by_spread.keys()):
        filled, total = fill_by_spread[s]
        print(f"    spread={s:2d}: {filled}/{total} = {filled/max(total,1)*100:.1f}%")

# Adaptive pricing - are we always best quote?
print("\n--- BEST QUOTE STATUS ---")
for prod in ['ASH_COATED_OSMIUM', 'INTARIAN_PEPPER_ROOT']:
    abbr = 'OSM' if 'OSMIUM' in prod else 'IPR'
    best_bid = 0
    tied_bid = 0
    worse_bid = 0
    best_ask = 0
    tied_ask = 0
    worse_ask = 0
    total = 0
    
    for tick in ticks:
        od = tick['order_depths'].get(prod)
        if not od:
            continue
        bids, asks = od[0], od[1]
        if not bids or not asks:
            continue
        
        bb = max(int(p) for p in bids.keys())
        ba = min(int(p) for p in asks.keys())
        
        if prod not in tick['our_orders']:
            continue
        
        our_bid = None
        our_ask = None
        for o in tick['our_orders'][prod]:
            if o[2] > 0:
                our_bid = o[1]
            else:
                our_ask = o[1]
        
        total += 1
        if our_bid is not None:
            if our_bid > bb: best_bid += 1
            elif our_bid == bb: tied_bid += 1
            else: worse_bid += 1
        if our_ask is not None:
            if our_ask < ba: best_ask += 1
            elif our_ask == ba: tied_ask += 1
            else: worse_ask += 1
    
    print(f"\n  {abbr} (n={total}):")
    print(f"    Bid - best: {best_bid} ({best_bid/max(total,1)*100:.1f}%), tied: {tied_bid} ({tied_bid/max(total,1)*100:.1f}%), worse: {worse_bid} ({worse_bid/max(total,1)*100:.1f}%)")
    print(f"    Ask - best: {best_ask} ({best_ask/max(total,1)*100:.1f}%), tied: {tied_ask} ({tied_ask/max(total,1)*100:.1f}%), worse: {worse_ask} ({worse_ask/max(total,1)*100:.1f}%)")

# Edge analysis - what's the actual edge per fill?
print("\n--- EDGE PER FILL ---")
for prod in ['ASH_COATED_OSMIUM', 'INTARIAN_PEPPER_ROOT']:
    abbr = 'OSM' if 'OSMIUM' in prod else 'IPR'
    pt = [t for t in trades if t['symbol'] == prod]
    buys = [t for t in pt if t['buyer'] == 'SUBMISSION']
    sells = [t for t in pt if t['seller'] == 'SUBMISSION']
    
    if prod == 'ASH_COATED_OSMIUM':
        fv = 10000
        buy_edge = sum((fv - t['price']) * t['quantity'] for t in buys)
        sell_edge = sum((t['price'] - fv) * t['quantity'] for t in sells)
        buy_qty = sum(t['quantity'] for t in buys)
        sell_qty = sum(t['quantity'] for t in sells)
        print(f"\n  {abbr}:")
        print(f"    Buy edge (FV-price)*qty: {buy_edge:.0f} from {buy_qty} qty")
        print(f"    Sell edge (price-FV)*qty: {sell_edge:.0f} from {sell_qty} qty")
        print(f"    Total edge: {buy_edge + sell_edge:.0f}")
        if buy_qty: print(f"    Avg buy edge/unit: {buy_edge/buy_qty:.1f}")
        if sell_qty: print(f"    Avg sell edge/unit: {sell_edge/sell_qty:.1f}")
