"""Deep trade-level analysis for TOMATOES in 42260 vs 42183."""
import json, csv, io
from collections import Counter, defaultdict

def load_sim(sim_id):
    with open(f'logs/{sim_id}/{sim_id}.json', 'r') as f:
        data = json.load(f)
    activities = data['activitiesLog']
    reader = csv.DictReader(io.StringIO(activities), delimiter=';')
    rows = list(reader)
    return data, rows

# Load both sims
data_260, rows_260 = load_sim(42260)
data_183, rows_183 = load_sim(42183)

def analyze_tomatoes(rows, label):
    print(f"\n{'='*60}")
    print(f"TOMATOES ANALYSIS: {label}")
    print(f"{'='*60}")
    
    tom_rows = [r for r in rows if r['product'] == 'TOMATOES']
    
    # Track PnL changes between ticks to find fills
    fills = []
    prev_pnl = 0.0
    for i, r in enumerate(tom_rows):
        ts = int(r['timestamp'])
        pnl = float(r['profit_and_loss'])
        mid = float(r['mid_price'])
        bp1 = int(r['bid_price_1']) if r['bid_price_1'] else None
        ap1 = int(r['ask_price_1']) if r['ask_price_1'] else None
        spread = (ap1 - bp1) if (ap1 and bp1) else None
        
        delta = pnl - prev_pnl
        if abs(delta) > 0.01:  # PnL changed = fill happened
            fills.append({
                'tick': i,
                'ts': ts,
                'pnl_delta': delta,
                'pnl_total': pnl,
                'mid': mid,
                'bp1': bp1,
                'ap1': ap1,
                'spread': spread,
            })
        prev_pnl = pnl
    
    print(f"Total ticks: {len(tom_rows)}")
    print(f"Ticks with PnL change: {len(fills)}")
    
    # PnL delta distribution
    deltas = [f['pnl_delta'] for f in fills]
    positive = [d for d in deltas if d > 0]
    negative = [d for d in deltas if d < 0]
    
    print(f"\nPositive PnL changes: {len(positive)}")
    print(f"  Total: {sum(positive):.2f}")
    print(f"  Avg: {sum(positive)/len(positive):.2f}" if positive else "")
    print(f"  Max: {max(positive):.2f}" if positive else "")
    
    print(f"\nNegative PnL changes: {len(negative)}")
    print(f"  Total: {sum(negative):.2f}")
    print(f"  Avg: {sum(negative)/len(negative):.2f}" if negative else "")
    print(f"  Min: {min(negative):.2f}" if negative else "")
    
    # Spread at time of fill
    fill_spreads = [f['spread'] for f in fills if f['spread'] is not None]
    if fill_spreads:
        print(f"\nSpread at fill time:")
        spread_dist = Counter(fill_spreads)
        for s, c in sorted(spread_dist.items()):
            print(f"  Spread={s}: {c} fills")
    
    # Show the biggest losses
    biggest_losses = sorted(fills, key=lambda f: f['pnl_delta'])[:15]
    print(f"\nBiggest losses (PnL drops):")
    for f in biggest_losses:
        print(f"  t={f['ts']:6d}: delta={f['pnl_delta']:+.2f}  total={f['pnl_total']:.2f}  mid={f['mid']:.1f}  spread={f['spread']}")
    
    # When does PnL peak and trough?
    pnl_timeline = [(int(r['timestamp']), float(r['profit_and_loss'])) for r in tom_rows]
    peak = max(pnl_timeline, key=lambda x: x[1])
    trough = min(pnl_timeline, key=lambda x: x[1])
    print(f"\nPnL peak: {peak[1]:.2f} at t={peak[0]}")
    print(f"PnL trough: {trough[1]:.2f} at t={trough[0]}")
    
    # Compute max drawdown from peak
    running_max = 0
    max_drawdown = 0
    max_dd_time = 0
    for ts, pnl in pnl_timeline:
        if pnl > running_max:
            running_max = pnl
        dd = running_max - pnl
        if dd > max_drawdown:
            max_drawdown = dd
            max_dd_time = ts
    print(f"Max drawdown: {max_drawdown:.2f} at t={max_dd_time}")
    
    # Mid price movement
    mids = [float(r['mid_price']) for r in tom_rows]
    print(f"\nMid price range: {min(mids):.1f} - {max(mids):.1f}")
    print(f"Mid price std: {(sum((m - sum(mids)/len(mids))**2 for m in mids) / len(mids))**0.5:.2f}")
    
    return fills

fills_260 = analyze_tomatoes(rows_260, "42260 (new, 2-level)")
fills_183 = analyze_tomatoes(rows_183, "42183 (old, 1-level)")

# === CRITICAL: Compare the order book around fills ===
print(f"\n{'='*60}")
print(f"KEY DIFFERENCES")
print(f"{'='*60}")

# Look at 42260 for ticks where our orders show in the book
# Our L1 bids at fair-2, L2 at fair-5 will show up as higher bids
# Our L1 asks at fair+2, L2 at fair+5 will show up as lower asks
tom260 = [r for r in rows_260 if r['product'] == 'TOMATOES']
tom183 = [r for r in rows_183 if r['product'] == 'TOMATOES']

# Check if our orders are tightening the book
def check_our_orders_in_book(tom_rows, label):
    print(f"\n{label}:")
    tight_count = 0
    our_bid_visible = 0
    our_ask_visible = 0
    
    # Bot default: spread ~13 (varies between 12-14)
    # If spread is notably smaller, our orders are in the book
    sp_dist = Counter()
    bp1_changes = Counter()
    
    for r in tom_rows:
        bp1 = int(r['bid_price_1']) if r['bid_price_1'] else None
        ap1 = int(r['ask_price_1']) if r['ask_price_1'] else None
        bp2 = int(r['bid_price_2']) if r['bid_price_2'] else None
        ap2 = int(r['ask_price_2']) if r['ask_price_2'] else None
        
        if bp1 and ap1:
            sp = ap1 - bp1
            sp_dist[sp] += 1
            
            # If there are 3 levels on a side, one is likely ours
            if r['bid_price_3']:
                our_bid_visible += 1
            if r['ask_price_3']:
                our_ask_visible += 1
    
    print(f"  Spread distribution:")
    for s, c in sorted(sp_dist.items()):
        print(f"    Spread={s}: {c} ({100*c/len(tom_rows):.1f}%)")
    print(f"  Ticks with 3+ bid levels (our orders visible): {our_bid_visible}")
    print(f"  Ticks with 3+ ask levels (our orders visible): {our_ask_visible}")

check_our_orders_in_book(tom260, "42260 (2-level)")
check_our_orders_in_book(tom183, "42183 (1-level)")

# === DETAILED: Look at the log to see which orders we're placing ===
# Parse the log file to extract our actual orders
def parse_log_orders(sim_id):
    try:
        with open(f'logs/{sim_id}/{sim_id}.log', 'r') as f:
            content = f.read()
    except FileNotFoundError:
        print(f"No log file for {sim_id}")
        return []
    
    # Log might be all on one line or multiple lines
    # Try to find JSON arrays in the content
    all_orders = []
    
    # Split by newline first
    for line in content.strip().split('\n'):
        line = line.strip()
        if not line:
            continue
        try:
            parsed = json.loads(line)
            if isinstance(parsed, list) and len(parsed) >= 5:
                state_info, orders_info, conversions, trader_data, logs = parsed
                if isinstance(orders_info, dict):
                    ts = state_info[0] if isinstance(state_info, list) else 0
                    for sym, olist in orders_info.items():
                        for o in olist:
                            all_orders.append({
                                'ts': ts,
                                'sym': o[0],
                                'price': o[1],
                                'qty': o[2],
                            })
        except (json.JSONDecodeError, ValueError, IndexError):
            pass
    
    return all_orders

print(f"\n=== ORDER PLACEMENT ANALYSIS ===")
orders_260 = parse_log_orders(42260)
orders_183 = parse_log_orders(42183)

for label, orders in [("42260", orders_260), ("42183", orders_183)]:
    tom_orders = [o for o in orders if o['sym'] == 'TOMATOES']
    print(f"\n{label} TOMATOES orders: {len(tom_orders)}")
    if tom_orders:
        buy_orders = [o for o in tom_orders if o['qty'] > 0]
        sell_orders = [o for o in tom_orders if o['qty'] < 0]
        print(f"  Buy orders: {len(buy_orders)}")
        print(f"  Sell orders: {len(sell_orders)}")
        
        # Price distribution relative to mid
        buy_prices = Counter(o['price'] for o in buy_orders)
        sell_prices = Counter(o['price'] for o in sell_orders)
        print(f"  Buy price range: {min(buy_prices)}-{max(buy_prices)}" if buy_prices else "")
        print(f"  Sell price range: {min(sell_prices)}-{max(sell_prices)}" if sell_prices else "")
