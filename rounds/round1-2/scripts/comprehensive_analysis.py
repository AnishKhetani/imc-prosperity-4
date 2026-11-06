"""
Comprehensive single-player market analysis for EMERALDS + TOMATOES.
Since each bot runs independently on same dataset, this is a pure extraction problem.
"""
import json, csv, io, sys
from collections import defaultdict

def parse_activities(log_path):
    with open(log_path, 'r') as f:
        data = json.load(f)
    reader = csv.DictReader(io.StringIO(data['activitiesLog']), delimiter=';')
    rows = list(reader)
    return rows, data

def parse_training_data(price_path, trade_path):
    """Parse the raw training CSVs (semicolon-delimited)."""
    with open(price_path, 'r') as f:
        reader = csv.DictReader(f, delimiter=';')
        prices = list(reader)
    with open(trade_path, 'r') as f:
        reader = csv.DictReader(f, delimiter=';')
        trades = list(reader)
    return prices, trades

print("=" * 80)
print("COMPREHENSIVE MARKET ANALYSIS")
print("=" * 80)

# ── Parse both sims ──
rows_953, data_953 = parse_activities('logs/44953/44953.log')
rows_861, data_861 = parse_activities('logs/44861/44861.log')

# ── Parse training data ──
base = r'tutorial-round/data/TUTORIAL_ROUND_1'
prices_d1, trades_d1 = parse_training_data(f'{base}/prices_round_0_day_-1.csv', f'{base}/trades_round_0_day_-1.csv')
prices_d2, trades_d2 = parse_training_data(f'{base}/prices_round_0_day_-2.csv', f'{base}/trades_round_0_day_-2.csv')

print(f"\nTraining data: day_-1 has {len(prices_d1)} price rows, {len(trades_d1)} trade rows")
print(f"Training data: day_-2 has {len(prices_d2)} price rows, {len(trades_d2)} trade rows")

# ── Examine training data columns ──
print(f"\nPrice columns: {list(prices_d1[0].keys())}")
print(f"Trade columns: {list(trades_d1[0].keys())}")
print(f"Sample price row: {prices_d1[0]}")
print(f"Sample trade row: {trades_d1[0]}")

# ═══════════════════════════════════════════════════════════════
#  1. TRAINING DATA ANALYSIS - Bot behavior patterns
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("1. TRAINING DATA - BOT BEHAVIOR ANALYSIS (day_-1 and day_-2)")
print("=" * 80)

for day_label, prices, trades in [("day_-1", prices_d1, trades_d1), ("day_-2", prices_d2, trades_d2)]:
    print(f"\n--- {day_label} ---")
    for product in ['EMERALDS', 'TOMATOES']:
        prod_prices = [r for r in prices if r.get('product') == product]
        prod_trades = [r for r in trades if r.get('symbol') == product]
        
        if not prod_prices:
            continue
        
        spreads = []
        mids = []
        bid1_vols = []
        ask1_vols = []
        
        for r in prod_prices:
            try:
                b1 = float(r.get('bid_price_1', 0) or 0)
                a1 = float(r.get('ask_price_1', 0) or 0)
                if b1 > 0 and a1 > 0:
                    spreads.append(a1 - b1)
                    mids.append((b1 + a1) / 2)
                bv1 = float(r.get('bid_volume_1', 0) or 0)
                av1 = float(r.get('ask_volume_1', 0) or 0)
                bid1_vols.append(bv1)
                ask1_vols.append(av1)
            except (ValueError, TypeError):
                continue
        
        if spreads:
            # Spread distribution
            spread_counts = defaultdict(int)
            for s in spreads:
                spread_counts[int(s)] += 1
            
            print(f"\n  {product} ({len(prod_prices)} ticks, {len(prod_trades)} trades)")
            print(f"    Mid range: {min(mids):.1f} - {max(mids):.1f}")
            print(f"    Spread: mean={sum(spreads)/len(spreads):.2f}, min={min(spreads):.0f}, max={max(spreads):.0f}")
            print(f"    Spread distribution:")
            for s in sorted(spread_counts.keys()):
                pct = spread_counts[s] / len(spreads) * 100
                print(f"      {s:3d}: {spread_counts[s]:5d} ({pct:5.1f}%)")
            
            # L1 volume patterns
            print(f"    L1 bid vol: mean={sum(bid1_vols)/len(bid1_vols):.1f}, range=[{min(bid1_vols):.0f}, {max(bid1_vols):.0f}]")
            print(f"    L1 ask vol: mean={sum(ask1_vols)/len(ask1_vols):.1f}, range=[{min(ask1_vols):.0f}, {max(ask1_vols):.0f}]")
        
        # Trade analysis
        if prod_trades:
            trade_prices = [float(t.get('price', 0)) for t in prod_trades if t.get('price')]
            trade_qtys = [float(t.get('quantity', 0)) for t in prod_trades if t.get('quantity')]
            buyers = defaultdict(int)
            sellers = defaultdict(int)
            for t in prod_trades:
                buyers[t.get('buyer', '?')] += 1
                sellers[t.get('seller', '?')] += 1
            
            print(f"    Trades: {len(prod_trades)}, avg price={sum(trade_prices)/len(trade_prices):.1f}")
            print(f"    Trade price range: {min(trade_prices):.0f} - {max(trade_prices):.0f}")
            print(f"    Buyers: {dict(buyers)}")
            print(f"    Sellers: {dict(sellers)}")

# ═══════════════════════════════════════════════════════════════
#  2. CROSS-DAY BOT CONSISTENCY - Is bot behavior identical?
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("2. CROSS-DAY BOT CONSISTENCY (Are bot spread patterns identical across days?)")
print("=" * 80)

for product in ['EMERALDS', 'TOMATOES']:
    d1_prices = [r for r in prices_d1 if r.get('product') == product]
    d2_prices = [r for r in prices_d2 if r.get('product') == product]
    
    # Compare spread distributions
    d1_spreads = defaultdict(int)
    d2_spreads = defaultdict(int)
    
    for r in d1_prices:
        try:
            b1 = float(r.get('bid_price_1', 0) or 0)
            a1 = float(r.get('ask_price_1', 0) or 0)
            if b1 > 0 and a1 > 0:
                d1_spreads[int(a1 - b1)] += 1
        except:
            pass
    
    for r in d2_prices:
        try:
            b1 = float(r.get('bid_price_1', 0) or 0)
            a1 = float(r.get('ask_price_1', 0) or 0)
            if b1 > 0 and a1 > 0:
                d2_spreads[int(a1 - b1)] += 1
        except:
            pass
    
    all_spreads = sorted(set(d1_spreads.keys()) | set(d2_spreads.keys()))
    print(f"\n  {product} spread comparison:")
    print(f"    {'Spread':>6} {'Day-1':>8} {'Day-2':>8} {'Day-1%':>8} {'Day-2%':>8}")
    total_d1 = sum(d1_spreads.values()) or 1
    total_d2 = sum(d2_spreads.values()) or 1
    for s in all_spreads:
        c1 = d1_spreads.get(s, 0)
        c2 = d2_spreads.get(s, 0)
        print(f"    {s:6d} {c1:8d} {c2:8d} {c1/total_d1*100:7.1f}% {c2/total_d2*100:7.1f}%")

# ═══════════════════════════════════════════════════════════════
#  3. SIM 44861 (BASELINE, PnL=2175) - Fill analysis
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("3. SIM 44861 FILL ANALYSIS (baseline PnL=2175, WIDTH=5)")
print("=" * 80)

# Parse the per-tick data from the sandbox stdout (the first field)
# Actually let's parse from the platform log differently
# The activities log has order book snapshots; let's look for trades in the graphLog

graph_861 = data_861.get('graphLog', '')
if graph_861:
    graph_reader = csv.DictReader(io.StringIO(graph_861), delimiter=';')
    graph_rows = list(graph_reader)
    print(f"\n  graphLog has {len(graph_rows)} rows")
    if graph_rows:
        print(f"  graphLog columns: {list(graph_rows[0].keys())}")
        print(f"  First: {graph_rows[0]}")
        print(f"  Last: {graph_rows[-1]}")

# ── Look at PnL trajectory ──
for sim_label, rows in [("44861 (baseline)", rows_861), ("44953 (current)", rows_953)]:
    print(f"\n--- {sim_label} ---")
    for product in ['EMERALDS', 'TOMATOES']:
        prod_rows = [r for r in rows if r['product'] == product]
        
        # PnL trajectory
        pnls = [float(r['profit_and_loss']) for r in prod_rows]
        
        # Detect PnL changes (= fills)
        fills = []
        prev_pnl = 0
        for i, r in enumerate(prod_rows):
            pnl = float(r['profit_and_loss'])
            if abs(pnl - prev_pnl) > 0.01:
                fills.append({
                    'tick': int(r['timestamp']),
                    'pnl_change': pnl - prev_pnl,
                    'total_pnl': pnl,
                    'mid': float(r['mid_price']),
                    'bid1': r.get('bid_price_1', ''),
                    'ask1': r.get('ask_price_1', ''),
                })
            prev_pnl = pnl
        
        print(f"\n  {product}: {len(fills)} PnL-change events, final PnL = {pnls[-1]:.2f}")
        if fills:
            changes = [f['pnl_change'] for f in fills]
            positive = [c for c in changes if c > 0]
            negative = [c for c in changes if c < 0]
            print(f"    Positive PnL changes: {len(positive)}, total = {sum(positive):.2f}")
            print(f"    Negative PnL changes: {len(negative)}, total = {sum(negative):.2f}")
            print(f"    Avg positive: {sum(positive)/len(positive):.2f}" if positive else "    No positive")
            print(f"    Avg negative: {sum(negative)/len(negative):.2f}" if negative else "    No negative")
            
            # Timing analysis: when do fills happen?
            fill_times = [f['tick'] for f in fills]
            early = len([t for t in fill_times if t < 50000])
            mid_t = len([t for t in fill_times if 50000 <= t < 150000])
            late = len([t for t in fill_times if t >= 150000])
            print(f"    Timing: early(<50k)={early}, mid(50k-150k)={mid_t}, late(>150k)={late}")
            
            # Show first 10 and last 5 fills
            print(f"    First 5 fills:")
            for f in fills[:5]:
                print(f"      t={f['tick']:6d}, Δpnl={f['pnl_change']:+8.2f}, total={f['total_pnl']:8.2f}, mid={f['mid']:.1f}")
            if len(fills) > 5:
                print(f"    Last 5 fills:")
                for f in fills[-5:]:
                    print(f"      t={f['tick']:6d}, Δpnl={f['pnl_change']:+8.2f}, total={f['total_pnl']:8.2f}, mid={f['mid']:.1f}")

# ═══════════════════════════════════════════════════════════════
#  4. SPREAD-REGIME FILL CORRELATION
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("4. SPREAD-REGIME FILL CORRELATION (when do fills happen relative to spread?)")
print("=" * 80)

for sim_label, rows in [("44861 (WIDTH=5)", rows_861), ("44953 (WIDTH=6)", rows_953)]:
    print(f"\n--- {sim_label} TOMATOES ---")
    tom_rows = [r for r in rows if r['product'] == 'TOMATOES']
    
    prev_pnl = 0
    spread_at_fill = defaultdict(int)
    spread_before_fill = defaultdict(int)
    total_by_spread = defaultdict(int)
    
    for i, r in enumerate(tom_rows):
        pnl = float(r['profit_and_loss'])
        b1 = float(r.get('bid_price_1', 0) or 0)
        a1 = float(r.get('ask_price_1', 0) or 0)
        spread = int(a1 - b1) if b1 > 0 and a1 > 0 else -1
        
        if spread >= 0:
            total_by_spread[spread] += 1
        
        if abs(pnl - prev_pnl) > 0.01:
            spread_at_fill[spread] += 1
            # Also check spread at previous tick
            if i > 0:
                pb1 = float(tom_rows[i-1].get('bid_price_1', 0) or 0)
                pa1 = float(tom_rows[i-1].get('ask_price_1', 0) or 0)
                prev_spread = int(pa1 - pb1) if pb1 > 0 and pa1 > 0 else -1
                spread_before_fill[prev_spread] += 1
        prev_pnl = pnl
    
    print(f"  Fills by spread AT fill tick:")
    for s in sorted(spread_at_fill.keys()):
        total = total_by_spread.get(s, 0)
        fill_rate = spread_at_fill[s] / total * 100 if total > 0 else 0
        print(f"    spread={s:2d}: {spread_at_fill[s]:3d} fills / {total:4d} ticks ({fill_rate:.1f}% fill rate)")
    
    print(f"  Fills by spread BEFORE fill tick:")
    for s in sorted(spread_before_fill.keys()):
        print(f"    spread={s:2d}: {spread_before_fill[s]:3d} fills")

# ═══════════════════════════════════════════════════════════════
#  5. EMERALDS - Theoretical max PnL analysis
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("5. EMERALDS - THEORETICAL MAX PnL")
print("=" * 80)
print("  Fair = 10000 always. Liquidation at fair = 0 cost.")
print("  Question: What is the maximum number of fills achievable?")

em_rows_861 = [r for r in rows_861 if r['product'] == 'EMERALDS']
prev_pnl = 0
em_fills = []
for r in em_rows_861:
    pnl = float(r['profit_and_loss'])
    if abs(pnl - prev_pnl) > 0.01:
        em_fills.append({
            'tick': int(r['timestamp']),
            'pnl_change': pnl - prev_pnl,
            'mid': float(r['mid_price']),
            'bid1': r.get('bid_price_1', ''),
            'ask1': r.get('ask_price_1', ''),
        })
    prev_pnl = pnl

print(f"\n  44861 EMERALDS fills: {len(em_fills)}")
for f in em_fills:
    b1 = f['bid1']
    a1 = f['ask1']
    print(f"    t={f['tick']:6d}, Δpnl={f['pnl_change']:+8.2f}, mid={f['mid']}, bid1={b1}, ask1={a1}")

# Check what the bot's order book looks like at every tick for EMERALDS
print(f"\n  EMERALDS order book patterns (from training data day_-1):")
em_prices_d1 = [r for r in prices_d1 if r.get('product') == 'EMERALDS']
em_book_patterns = defaultdict(int)
for r in em_prices_d1:
    b1 = r.get('bid_price_1', '')
    a1 = r.get('ask_price_1', '')
    b2 = r.get('bid_price_2', '')
    a2 = r.get('ask_price_2', '')
    pattern = f"b1={b1} b2={b2} | a1={a1} a2={a2}"
    em_book_patterns[pattern] += 1

print(f"  Unique book patterns: {len(em_book_patterns)}")
for pattern, count in sorted(em_book_patterns.items(), key=lambda x: -x[1])[:20]:
    print(f"    {count:5d} ticks: {pattern}")

# ═══════════════════════════════════════════════════════════════
#  6. TOMATOES - Random walk properties & optimal strategy
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("6. TOMATOES - RANDOM WALK PROPERTIES")
print("=" * 80)

for day_label, prices in [("day_-1", prices_d1), ("day_-2", prices_d2)]:
    tom_prices = [r for r in prices if r.get('product') == 'TOMATOES']
    mids = []
    for r in tom_prices:
        try:
            b1 = float(r.get('bid_price_1', 0) or 0)
            a1 = float(r.get('ask_price_1', 0) or 0)
            if b1 > 0 and a1 > 0:
                mids.append((b1 + a1) / 2)
        except:
            pass
    
    if not mids:
        continue
    
    # Returns
    returns = [mids[i+1] - mids[i] for i in range(len(mids)-1)]
    
    # Autocorrelation
    mean_ret = sum(returns) / len(returns)
    var = sum((r - mean_ret)**2 for r in returns) / len(returns)
    if var > 0:
        autocorr1 = sum((returns[i] - mean_ret) * (returns[i+1] - mean_ret) for i in range(len(returns)-1)) / (len(returns)-1) / var
    else:
        autocorr1 = 0
    
    # Drift
    total_move = mids[-1] - mids[0]
    
    # Volatility (std of returns)
    import math
    std = math.sqrt(var) if var > 0 else 0
    
    print(f"\n  {day_label}: {len(mids)} mid prices")
    print(f"    Start: {mids[0]:.1f}, End: {mids[-1]:.1f}, Total drift: {total_move:+.1f}")
    print(f"    Return std: {std:.4f}")
    print(f"    Autocorrelation(1): {autocorr1:.4f}")
    print(f"    Max mid: {max(mids):.1f}, Min mid: {min(mids):.1f}, Range: {max(mids)-min(mids):.1f}")
    
    # Check if returns are mean-reverting or trending
    # Sign change frequency
    sign_changes = sum(1 for i in range(len(returns)-1) if returns[i] * returns[i+1] < 0)
    same_sign = sum(1 for i in range(len(returns)-1) if returns[i] * returns[i+1] > 0)
    zero_ret = sum(1 for r in returns if r == 0)
    print(f"    Sign changes: {sign_changes}, Same sign: {same_sign}, Zero returns: {zero_ret}")
    print(f"    Sign change rate: {sign_changes/(sign_changes+same_sign)*100:.1f}% (50% = pure random)")

# ═══════════════════════════════════════════════════════════════
#  7. TOMATOES - Can we detect narrow spread ticks in advance?
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("7. TOMATOES - NARROW SPREAD PREDICTABILITY")
print("=" * 80)

for day_label, prices in [("day_-1", prices_d1), ("day_-2", prices_d2)]:
    tom_prices = [r for r in prices if r.get('product') == 'TOMATOES']
    spreads = []
    for r in tom_prices:
        try:
            b1 = float(r.get('bid_price_1', 0) or 0)
            a1 = float(r.get('ask_price_1', 0) or 0)
            if b1 > 0 and a1 > 0:
                spreads.append(int(a1 - b1))
            else:
                spreads.append(-1)
        except:
            spreads.append(-1)
    
    # For each narrow spread tick, what was the spread at prior ticks?
    narrow_threshold = 10
    narrow_indices = [i for i, s in enumerate(spreads) if 0 < s <= narrow_threshold]
    
    print(f"\n  {day_label}: {len(narrow_indices)} ticks with spread <= {narrow_threshold}")
    
    # Transition matrix: P(spread_t | spread_{t-1})
    transitions = defaultdict(lambda: defaultdict(int))
    for i in range(1, len(spreads)):
        if spreads[i] > 0 and spreads[i-1] > 0:
            s_prev = min(spreads[i-1], 20)
            s_curr = min(spreads[i], 20)
            transitions[s_prev][s_curr] += 1
    
    # Show transition probabilities for narrow spreads
    print(f"  Transition: if spread_t-1 = X, probability of spread_t <= 10:")
    for prev_s in sorted(transitions.keys()):
        total = sum(transitions[prev_s].values())
        narrow_next = sum(v for k, v in transitions[prev_s].items() if k <= narrow_threshold)
        print(f"    spread={prev_s:2d}: P(narrow_next)={narrow_next/total*100:5.1f}% (n={total})")

# ═══════════════════════════════════════════════════════════════
#  8. TOMATOES - Aggressive take opportunities
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("8. TOMATOES - AGGRESSIVE TAKE ANALYSIS (from training data)")
print("=" * 80)

for day_label, prices, trades in [("day_-1", prices_d1, trades_d1), ("day_-2", prices_d2, trades_d2)]:
    tom_prices = [r for r in prices if r.get('product') == 'TOMATOES']
    tom_trades = [r for r in trades if r.get('symbol') == 'TOMATOES']
    
    print(f"\n  {day_label}:")
    
    # Build mid-price series
    mids = {}
    for r in tom_prices:
        try:
            ts = int(r.get('timestamp', 0))
            b1 = float(r.get('bid_price_1', 0) or 0)
            a1 = float(r.get('ask_price_1', 0) or 0)
            if b1 > 0 and a1 > 0:
                mids[ts] = (b1 + a1) / 2
        except:
            pass
    
    # Check trade frequency and who's trading
    buyer_counts = defaultdict(int)
    seller_counts = defaultdict(int)
    for t in tom_trades:
        buyer_counts[t.get('buyer', '')] += 1
        seller_counts[t.get('seller', '')] += 1
    
    print(f"    Total trades: {len(tom_trades)}")
    print(f"    Buyers: {dict(sorted(buyer_counts.items(), key=lambda x: -x[1]))}")
    print(f"    Sellers: {dict(sorted(seller_counts.items(), key=lambda x: -x[1]))}")
    
    # For each trade, check: was the trade at bid, ask, or mid?
    trade_at = defaultdict(int)
    for t in tom_trades:
        try:
            ts = int(t.get('timestamp', 0))
            price = float(t.get('price', 0))
            if ts in mids:
                mid = mids[ts]
                if price < mid - 0.5:
                    trade_at['below_mid'] += 1
                elif price > mid + 0.5:
                    trade_at['above_mid'] += 1
                else:
                    trade_at['at_mid'] += 1
        except:
            pass
    print(f"    Trade location: {dict(trade_at)}")

# ═══════════════════════════════════════════════════════════════
#  9. PnL SENSITIVITY - What is position @ end worth?
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("9. END-OF-DAY LIQUIDATION IMPACT")
print("=" * 80)

# EMERALDS is always 10000, so position * 0 = no impact
# TOMATOES: position * (final_mid - fair) = impact
for sim_label, rows in [("44861", rows_861), ("44953", rows_953)]:
    tom_rows = [r for r in rows if r['product'] == 'TOMATOES']
    if tom_rows:
        final_mid = float(tom_rows[-1]['mid_price'])
        final_pnl = float(tom_rows[-1]['profit_and_loss'])
        print(f"  {sim_label}: TOMATOES final mid = {final_mid}, final PnL = {final_pnl:.2f}")

# ═══════════════════════════════════════════════════════════════
#  10. VOLUME - What's the total possible extraction?
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("10. TOTAL BOT VOLUME AVAILABLE")
print("=" * 80)

for day_label, prices in [("day_-1", prices_d1), ("day_-2", prices_d2)]:
    for product in ['EMERALDS', 'TOMATOES']:
        prod_prices = [r for r in prices if r.get('product') == product]
        total_bid_vol = 0
        total_ask_vol = 0
        for r in prod_prices:
            for level in ['1', '2', '3']:
                bv = float(r.get(f'bid_volume_{level}', 0) or 0)
                av = float(r.get(f'ask_volume_{level}', 0) or 0)
                total_bid_vol += bv
                total_ask_vol += av
        print(f"  {day_label} {product}: total bid volume = {total_bid_vol:.0f}, total ask volume = {total_ask_vol:.0f}")

print("\n\nDONE.")
