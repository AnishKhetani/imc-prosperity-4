"""
Complete IPR fill execution analysis.
Compares our orders placed vs actual fills.
"""
import json
from collections import Counter, defaultdict

with open(r'.\logs\155873\155873.log') as f:
    raw = json.loads(f.read())
with open(r'.\logs\155873\155873.json') as f:
    d = json.load(f)

# ── 1. Parse our orders every tick ──
our_ipr_orders = []  # (ts, bid_price, bid_qty, ask_price, ask_qty)
our_osm_orders = []

for entry in raw['logs']:
    ts = entry['timestamp']
    try:
        parsed = json.loads(entry['lambdaLog'])
        orders = parsed[1]
        
        # IPR orders
        ipr_ords = orders.get('INTARIAN_PEPPER_ROOT', [])
        if ipr_ords:
            bids = [(o[1], o[2]) for o in ipr_ords if o[2] > 0]
            asks = [(o[1], -o[2]) for o in ipr_ords if o[2] < 0]
            bid_p = bids[0][0] if bids else None
            bid_q = bids[0][1] if bids else 0
            ask_p = asks[0][0] if asks else None
            ask_q = asks[0][1] if asks else 0
            our_ipr_orders.append((ts, bid_p, bid_q, ask_p, ask_q))
        else:
            our_ipr_orders.append((ts, None, 0, None, 0))
            
        # OSM orders
        osm_ords = orders.get('ASH_COATED_OSMIUM', [])
        if osm_ords:
            bids = [(o[1], o[2]) for o in osm_ords if o[2] > 0]
            asks = [(o[1], -o[2]) for o in osm_ords if o[2] < 0]
            our_osm_orders.append((ts, bids, asks))
    except:
        our_ipr_orders.append((ts, None, 0, None, 0))

# ── 2. Parse book from activities log ──
lines = d['activitiesLog'].strip().split('\n')
ipr_book = {}  # ts -> (bid1, bv1, ask1, av1)
for line in lines[1:]:
    parts = line.split(';')
    if len(parts) > 15 and parts[2] == 'INTARIAN_PEPPER_ROOT':
        ts = int(parts[1])
        bid1 = float(parts[3]) if parts[3] else None
        bv1 = int(parts[4]) if parts[4] else 0
        ask1 = float(parts[9]) if parts[9] else None
        av1 = int(parts[10]) if parts[10] else 0
        mid = float(parts[15]) if parts[15] else None
        ipr_book[ts] = (bid1, bv1, ask1, av1, mid)

# ── 3. Parse actual trades ──
ipr_trades = []
for trade in raw['tradeHistory']:
    if trade['symbol'] == 'INTARIAN_PEPPER_ROOT':
        is_buy = trade['buyer'] == 'SUBMISSION'
        is_sell = trade['seller'] == 'SUBMISSION'
        if is_buy or is_sell:
            ipr_trades.append({
                'ts': trade['timestamp'],
                'side': 'BUY' if is_buy else 'SELL',
                'price': trade['price'],
                'qty': trade['quantity'],
            })

trades_by_ts = defaultdict(list)
for t in ipr_trades:
    trades_by_ts[t['ts']].append(t)

# ── 4. Full tick-by-tick analysis around fills ──
print("=" * 90)
print("TICK-BY-TICK AROUND EACH IPR FILL")
print("=" * 90)
print(f"{'ts':>6s}  {'BotBid':>8s}  {'BotAsk':>8s}  {'Spread':>6s}  {'OurBid':>8s}  {'OurAsk':>8s}  {'Fill':>20s}")
print("-" * 90)

for trade in ipr_trades:
    ts = trade['ts']
    # Find our order at this tick or the tick before
    our_order = None
    for o in our_ipr_orders:
        if o[0] == ts:
            our_order = o
            break
    # Also check tick before (our order is from previous tick)
    if our_order is None or our_order[1] is None:
        for o in our_ipr_orders:
            if o[0] == ts - 100:
                our_order = o
                break
    
    book = ipr_book.get(ts, (None, 0, None, 0, None))
    
    ob_str = f"{book[0] or '':>8}" 
    oa_str = f"{book[2] or '':>8}"
    sp_str = f"{book[2] - book[0]:.0f}" if book[0] and book[2] else "?"
    ob_our = f"{our_order[1] or '':>8}" if our_order else "?"
    oa_our = f"{our_order[3] or '':>8}" if our_order else "?"
    fill_str = f"{trade['side']} {trade['qty']}@{trade['price']:.0f}"
    
    print(f"{ts:6d}  {ob_str}  {oa_str}  {sp_str:>6s}  {ob_our}  {oa_our}  {fill_str:>20s}")

# ── 5. Analyze: on which ticks do we NOT place orders and why? ──
print()
print("=" * 90)
print("TICK ANALYSIS: How many ticks do we place IPR orders?")
print("=" * 90)
no_order_ticks = sum(1 for o in our_ipr_orders if o[1] is None and o[3] is None)
bid_only = sum(1 for o in our_ipr_orders if o[1] is not None and o[3] is None)
ask_only = sum(1 for o in our_ipr_orders if o[1] is None and o[3] is not None)
both = sum(1 for o in our_ipr_orders if o[1] is not None and o[3] is not None)
print(f"Total ticks: {len(our_ipr_orders)}")
print(f"  Both bid+ask: {both}")
print(f"  Bid only: {bid_only}")
print(f"  Ask only: {ask_only}")
print(f"  No orders: {no_order_ticks}")

# ── 6. Order placement stats ──
print()
print("=" * 90)
print("IPR ORDER PLACEMENT vs BOOK")
print("=" * 90)

# For each tick we place orders, compare our price to bot's L1
edge_to_bid = []  # how far our bid is from bot's best bid
edge_to_ask = []  # how far our ask is from bot's best ask
inside_spread_bid = 0
inside_spread_ask = 0

for o in our_ipr_orders:
    ts = o[0]
    book = ipr_book.get(ts)
    if not book or not book[0] or not book[2]:
        continue
    bot_bid, _, bot_ask, _, mid = book
    
    if o[1] is not None:  # We placed a bid
        dist_from_bot_bid = o[1] - bot_bid  # positive = our bid above bot's
        edge_to_bid.append(dist_from_bot_bid)
        if o[1] > bot_bid and o[1] < bot_ask:
            inside_spread_bid += 1
    
    if o[3] is not None:  # We placed an ask
        dist_from_bot_ask = bot_ask - o[3]  # positive = our ask below bot's
        edge_to_ask.append(dist_from_bot_ask)
        if o[3] < bot_ask and o[3] > bot_bid:
            inside_spread_ask += 1

if edge_to_bid:
    print(f"Our bid vs bot's bid (positive = we're higher/tighter):")
    c = Counter(round(x) for x in edge_to_bid)
    for delta, count in sorted(c.items()):
        bar = '#' * min(count, 50)
        print(f"  {delta:+3.0f}: {count:4d} {bar}")
    print(f"  Inside spread: {inside_spread_bid}/{len(edge_to_bid)}")

print()
if edge_to_ask:
    print(f"Our ask vs bot's ask (positive = we're lower/tighter):")
    c = Counter(round(x) for x in edge_to_ask)
    for delta, count in sorted(c.items()):
        bar = '#' * min(count, 50)
        print(f"  {delta:+3.0f}: {count:4d} {bar}")
    print(f"  Inside spread: {inside_spread_ask}/{len(edge_to_ask)}")

# ── 7. Key metric: fill rate ──
print()
print("=" * 90)
print("FILL RATE")
print("=" * 90)
total_bid_ticks = sum(1 for o in our_ipr_orders if o[1] is not None)
total_ask_ticks = sum(1 for o in our_ipr_orders if o[3] is not None)
buy_fills = sum(1 for t in ipr_trades if t['side'] == 'BUY')
sell_fills = sum(1 for t in ipr_trades if t['side'] == 'SELL')
print(f"Bid orders placed on {total_bid_ticks} ticks, filled {buy_fills} times ({100*buy_fills/max(total_bid_ticks,1):.1f}%)")
print(f"Ask orders placed on {total_ask_ticks} ticks, filled {sell_fills} times ({100*sell_fills/max(total_ask_ticks,1):.1f}%)")
print(f"Average IPR spread: {sum(book[2]-book[0] for book in ipr_book.values() if book[0] and book[2])/sum(1 for book in ipr_book.values() if book[0] and book[2]):.1f}")
print(f"Our WIDTH=4 means total spread = 8")

# ── 8. What portion of PnL is spread capture vs directional? ──
print()
print("=" * 90)
print("PnL DECOMPOSITION: spread capture vs directional")
print("=" * 90)
pos = 0
spread_pnl = 0
for t in sorted(ipr_trades, key=lambda x: x['ts']):
    mid = ipr_book.get(t['ts'], (None,None,None,None,None))[4]
    if mid is None:
        # Find closest
        closest_ts = min(ipr_book.keys(), key=lambda k: abs(k - t['ts']))
        mid = ipr_book[closest_ts][4]
    
    if t['side'] == 'BUY':
        # We bought: spread capture = mid - buy_price
        spread_pnl += (mid - t['price']) * t['qty']
        pos += t['qty']
    else:
        # We sold: spread capture = sell_price - mid
        spread_pnl += (t['price'] - mid) * t['qty']
        pos -= t['qty']

final_mid = ipr_book[max(ipr_book.keys())][4]
total_pnl = d['profit'] - 2133.375  # total - OSM PnL = IPR PnL (~557.5)
directional_pnl = total_pnl - spread_pnl

print(f"Total IPR PnL: ~557.5")
print(f"Spread capture PnL (fill edge * qty): {spread_pnl:.1f}")
print(f"Directional PnL (inventory * price move): {total_pnl - spread_pnl:.1f}")
print(f"Final position: {pos}, final mid: {final_mid}")

# ── 9. Compare: what if WIDTH was different? ──
print()
print("=" * 90)
print("HYPOTHETICAL: DIFFERENT STRATEGIES")
print("=" * 90)
# For each tick, check if the bot's best ask crosses our bid level
# (which means we'd get filled on our bid)
# The activities log shows post-matching book, but our orders get
# matched AGAINST the bot's quotes shown there.
# No -- the activities log is pre-matching. Our orders are submitted
# and then matched against the existing book.
# Actually, the "mid_price" column shows pre-our-order state.
# When we place bid at 11998 and bot ask is 12006, no match.
# We only get filled when the bot reprices to cross our level.

# Let me count: on NEXT tick after we place a bid, does the bot's ask
# cross our bid? That's our fill mechanism.
print("Fill mechanism: our resting order gets hit by bot on subsequent tick")
print()
for test_width in [3, 4, 5, 6, 7]:
    fills_bid = 0
    fills_ask = 0
    for i, o in enumerate(our_ipr_orders[:-1]):
        ts = o[0]
        next_ts = our_ipr_orders[i+1][0]
        next_book = ipr_book.get(next_ts)
        if not next_book or not next_book[0] or not next_book[2]:
            continue
        
        book_now = ipr_book.get(ts)
        if not book_now or not book_now[4]:
            continue
        mid = book_now[4]
        our_bid = round(mid) - test_width
        our_ask = round(mid) + test_width
        
        # Bot's next-tick ask <= our bid = fill
        if next_book[2] <= our_bid:
            fills_bid += 1
        # Bot's next-tick bid >= our ask = fill  
        if next_book[0] >= our_ask:
            fills_ask += 1
    
    total = fills_bid + fills_ask
    print(f"  WIDTH={test_width}: bid_fills~{fills_bid:3d}, ask_fills~{fills_ask:3d}, total~{total:3d}")
