"""
Deep analysis of TOMATOES microstructure for strategy design.
Analyzes: spread distribution, price dynamics, bot behavior, fill opportunities,
order book depth patterns, and optimal market making parameters.
"""
import csv
import math
import os
from collections import defaultdict

DATA_DIR = r".\tutorial-round\data\TUTORIAL_ROUND_1"

def parse_prices(filepath):
    """Parse prices CSV into list of dicts per timestamp."""
    rows = []
    with open(filepath, 'r') as f:
        reader = csv.DictReader(f, delimiter=';')
        for row in reader:
            rows.append(row)
    return rows

def parse_trades(filepath):
    rows = []
    with open(filepath, 'r') as f:
        reader = csv.DictReader(f, delimiter=';')
        for row in reader:
            rows.append(row)
    return rows

def analyze_day(day_label, prices_file, trades_file):
    print(f"\n{'='*80}")
    print(f"  ANALYSIS: {day_label}")
    print(f"{'='*80}")
    
    prices = parse_prices(prices_file)
    trades = parse_trades(trades_file)
    
    # Filter TOMATOES
    tom_prices = [r for r in prices if r['product'] == 'TOMATOES']
    tom_trades = [r for r in trades if r['symbol'] == 'TOMATOES']
    
    print(f"\nTotal ticks: {len(tom_prices)}")
    print(f"Total trades: {len(tom_trades)}")
    
    # ========== PRICE ANALYSIS ==========
    mids = []
    spreads = []
    best_bids = []
    best_asks = []
    bid_sizes = []
    ask_sizes = []
    total_bid_depths = []
    total_ask_depths = []
    
    for row in tom_prices:
        # Parse order book
        bids = {}
        asks = {}
        for i in range(1, 4):
            bp = row.get(f'bid_price_{i}', '')
            bv = row.get(f'bid_volume_{i}', '')
            ap = row.get(f'ask_price_{i}', '')
            av = row.get(f'ask_volume_{i}', '')
            if bp and bv:
                bids[float(bp)] = int(bv)
            if ap and av:
                asks[float(ap)] = int(av)
        
        if bids and asks:
            bb = max(bids.keys())
            ba = min(asks.keys())
            mid = (bb + ba) / 2
            spread = ba - bb
            
            mids.append(mid)
            spreads.append(spread)
            best_bids.append(bb)
            best_asks.append(ba)
            bid_sizes.append(bids[bb])
            ask_sizes.append(asks[ba])
            total_bid_depths.append(sum(bids.values()))
            total_ask_depths.append(sum(asks.values()))
    
    print(f"\n--- SPREAD ANALYSIS ---")
    print(f"Mean spread: {sum(spreads)/len(spreads):.2f}")
    print(f"Median spread: {sorted(spreads)[len(spreads)//2]:.2f}")
    print(f"Min spread: {min(spreads):.2f}")
    print(f"Max spread: {max(spreads):.2f}")
    
    spread_dist = defaultdict(int)
    for s in spreads:
        spread_dist[int(s)] += 1
    print(f"\nSpread distribution:")
    for k in sorted(spread_dist.keys()):
        pct = spread_dist[k] / len(spreads) * 100
        print(f"  Spread={k}: {spread_dist[k]} ({pct:.1f}%)")
    
    print(f"\n--- PRICE DYNAMICS (Random Walk Check) ---")
    returns = [mids[i+1] - mids[i] for i in range(len(mids)-1)]
    mean_ret = sum(returns) / len(returns)
    var_ret = sum((r - mean_ret)**2 for r in returns) / len(returns)
    std_ret = var_ret**0.5
    print(f"Mean return: {mean_ret:.4f}")
    print(f"Std return: {std_ret:.4f}")
    print(f"Min return: {min(returns):.2f}")
    print(f"Max return: {max(returns):.2f}")
    
    # Autocorrelation
    n = len(returns)
    autocorrs = []
    for lag in [1, 2, 3, 5, 10, 20]:
        if lag < n:
            mean_r = sum(returns) / n
            num = sum((returns[i] - mean_r) * (returns[i-lag] - mean_r) for i in range(lag, n))
            den = sum((r - mean_r)**2 for r in returns)
            ac = num / den if den != 0 else 0
            autocorrs.append((lag, ac))
            print(f"  Autocorrelation lag={lag}: {ac:.4f}")
    
    # Price range
    print(f"\nPrice range: {min(mids):.0f} to {max(mids):.0f} (range={max(mids)-min(mids):.0f})")
    
    # Variance ratio test (random walk)
    for k in [5, 10, 20, 50]:
        if k < len(returns):
            k_returns = [sum(returns[i:i+k]) for i in range(0, len(returns)-k, k)]
            if len(k_returns) > 1:
                var_1 = var_ret
                var_k = sum((r - sum(k_returns)/len(k_returns))**2 for r in k_returns) / len(k_returns)
                vr = var_k / (k * var_1) if var_1 > 0 else 0
                print(f"  Variance ratio (k={k}): {vr:.4f} (1.0 = pure random walk)")
    
    print(f"\n--- ORDER BOOK DEPTH ---")
    print(f"Mean L1 bid size: {sum(bid_sizes)/len(bid_sizes):.1f}")
    print(f"Mean L1 ask size: {sum(ask_sizes)/len(ask_sizes):.1f}")
    print(f"Mean total bid depth: {sum(total_bid_depths)/len(total_bid_depths):.1f}")
    print(f"Mean total ask depth: {sum(total_ask_depths)/len(total_ask_depths):.1f}")
    
    # L1 size distribution
    l1_bid_dist = defaultdict(int)
    l1_ask_dist = defaultdict(int)
    for s in bid_sizes:
        l1_bid_dist[s] += 1
    for s in ask_sizes:
        l1_ask_dist[s] += 1
    print(f"\nL1 bid size distribution:")
    for k in sorted(l1_bid_dist.keys()):
        print(f"  Size={k}: {l1_bid_dist[k]} ({l1_bid_dist[k]/len(bid_sizes)*100:.1f}%)")
    print(f"\nL1 ask size distribution:")
    for k in sorted(l1_ask_dist.keys()):
        print(f"  Size={k}: {l1_ask_dist[k]} ({l1_ask_dist[k]/len(ask_sizes)*100:.1f}%)")
    
    # ========== TRADE ANALYSIS ==========
    print(f"\n--- TRADE ANALYSIS ---")
    trade_by_buyer = defaultdict(lambda: {'count': 0, 'volume': 0})
    trade_by_seller = defaultdict(lambda: {'count': 0, 'volume': 0})
    trade_prices_vs_mid = []
    
    trade_ts_set = defaultdict(list)
    for t in tom_trades:
        ts = int(t['timestamp'])
        qty = int(t['quantity'])
        price = float(t['price'])
        buyer = t.get('buyer', '')
        seller = t.get('seller', '')
        trade_by_buyer[buyer]['count'] += 1
        trade_by_buyer[buyer]['volume'] += qty
        trade_by_seller[seller]['count'] += 1
        trade_by_seller[seller]['volume'] += qty
        trade_ts_set[ts].append({'price': price, 'qty': qty, 'buyer': buyer, 'seller': seller})
    
    print(f"\nBuyers:")
    for b, v in sorted(trade_by_buyer.items(), key=lambda x: -x[1]['volume']):
        print(f"  {b}: {v['count']} trades, {v['volume']} volume")
    print(f"\nSellers:")
    for s, v in sorted(trade_by_seller.items(), key=lambda x: -x[1]['volume']):
        print(f"  {s}: {v['count']} trades, {v['volume']} volume")
    
    # Trade frequency
    trade_timestamps = sorted(set(int(t['timestamp']) for t in tom_trades))
    if len(trade_timestamps) > 1:
        gaps = [trade_timestamps[i+1] - trade_timestamps[i] for i in range(len(trade_timestamps)-1)]
        print(f"\nTrade timing:")
        print(f"  Ticks with trades: {len(trade_timestamps)} / {len(tom_prices)} ({len(trade_timestamps)/len(tom_prices)*100:.1f}%)")
        print(f"  Mean gap between trade ticks: {sum(gaps)/len(gaps):.1f}")
    
    # Trade size distribution
    trade_sizes = [int(t['quantity']) for t in tom_trades]
    size_dist = defaultdict(int)
    for s in trade_sizes:
        size_dist[s] += 1
    print(f"\nTrade size distribution:")
    for k in sorted(size_dist.keys()):
        print(f"  Size={k}: {size_dist[k]} ({size_dist[k]/len(trade_sizes)*100:.1f}%)")
    
    # ========== FILL OPPORTUNITY ANALYSIS ==========
    print(f"\n--- FILL OPPORTUNITY ANALYSIS (passive market making) ---")
    print(f"Simulating fills at various widths from mid-price:")
    
    # For each tick, check if a trade happened and at what price
    # Build mid-price lookup
    mid_by_ts = {}
    bb_by_ts = {}
    ba_by_ts = {}
    for row in tom_prices:
        ts = int(row['timestamp'])
        bids = {}
        asks = {}
        for i in range(1, 4):
            bp = row.get(f'bid_price_{i}', '')
            bv = row.get(f'bid_volume_{i}', '')
            ap = row.get(f'ask_price_{i}', '')
            av = row.get(f'ask_volume_{i}', '')
            if bp and bv:
                bids[float(bp)] = int(bv)
            if ap and av:
                asks[float(ap)] = int(av)
        if bids and asks:
            bb = max(bids.keys())
            ba = min(asks.keys())
            mid_by_ts[ts] = (bb + ba) / 2
            bb_by_ts[ts] = bb
            ba_by_ts[ts] = ba
    
    # For each width, simulate: our bid = round(mid) - width, our ask = round(mid) + width
    # Count fills where trade price <= our ask (we sell) or >= our bid (we buy)
    for width in range(1, 10):
        buy_fills = 0
        sell_fills = 0
        buy_pnl = 0
        sell_pnl = 0
        total_volume_bought = 0
        total_volume_sold = 0
        
        for ts, mid in mid_by_ts.items():
            fair = round(mid)
            our_bid = fair - width
            our_ask = fair + width
            
            if ts in trade_ts_set:
                for trade in trade_ts_set[ts]:
                    # If trade price <= our bid price, we could buy at our_bid level
                    # Actually: if there's a sell at price <= our_bid, we'd get filled buying
                    if trade['price'] <= our_bid:
                        buy_fills += 1
                        total_volume_bought += trade['qty']
                        buy_pnl += (mid - our_bid) * trade['qty']  # profit from buying below mid
                    # If there's a buy at price >= our_ask, we'd get filled selling
                    if trade['price'] >= our_ask:
                        sell_fills += 1
                        total_volume_sold += trade['qty']
                        sell_pnl += (our_ask - mid) * trade['qty']
        
        print(f"  WIDTH={width}: buy_fills={buy_fills}, sell_fills={sell_fills}, "
              f"total_fills={buy_fills+sell_fills}, "
              f"edge_per_fill={width:.0f}, "
              f"est_gross_pnl={buy_pnl+sell_pnl:.0f}")
    
    # ========== BOT QUOTE PATTERN ANALYSIS ==========
    print(f"\n--- BOT QUOTE PATTERNS ---")
    # Analyze how bot quotes change relative to mid
    bot_bid_offsets = []
    bot_ask_offsets = []
    for row in tom_prices:
        bids = {}
        asks = {}
        for i in range(1, 4):
            bp = row.get(f'bid_price_{i}', '')
            bv = row.get(f'bid_volume_{i}', '')
            ap = row.get(f'ask_price_{i}', '')
            av = row.get(f'ask_volume_{i}', '')
            if bp and bv:
                bids[float(bp)] = int(bv)
            if ap and av:
                asks[float(ap)] = int(av)
        if bids and asks:
            bb = max(bids.keys())
            ba = min(asks.keys())
            mid = (bb + ba) / 2
            bot_bid_offsets.append(mid - bb)
            bot_ask_offsets.append(ba - mid)
    
    print(f"Bot bid offset from mid: mean={sum(bot_bid_offsets)/len(bot_bid_offsets):.2f}, "
          f"min={min(bot_bid_offsets):.2f}, max={max(bot_bid_offsets):.2f}")
    print(f"Bot ask offset from mid: mean={sum(bot_ask_offsets)/len(bot_ask_offsets):.2f}, "
          f"min={min(bot_ask_offsets):.2f}, max={max(bot_ask_offsets):.2f}")
    
    # ========== KEY INSIGHT: Trade price vs L1 ==========
    print(f"\n--- TRADE PRICE vs ORDER BOOK ---")
    trades_at_bid = 0
    trades_at_ask = 0
    trades_between = 0
    trades_outside = 0
    
    for ts, trade_list in trade_ts_set.items():
        if ts in bb_by_ts:
            bb = bb_by_ts[ts]
            ba = ba_by_ts[ts]
            for trade in trade_list:
                p = trade['price']
                if p == bb:
                    trades_at_bid += 1
                elif p == ba:
                    trades_at_ask += 1
                elif bb < p < ba:
                    trades_between += 1
                else:
                    trades_outside += 1
    
    total_t = trades_at_bid + trades_at_ask + trades_between + trades_outside
    if total_t > 0:
        print(f"Trades at best bid: {trades_at_bid} ({trades_at_bid/total_t*100:.1f}%)")
        print(f"Trades at best ask: {trades_at_ask} ({trades_at_ask/total_t*100:.1f}%)")
        print(f"Trades between bid-ask: {trades_between} ({trades_between/total_t*100:.1f}%)")
        print(f"Trades outside bid-ask: {trades_outside} ({trades_outside/total_t*100:.1f}%)")
    
    # ========== CONSECUTIVE DIRECTION ANALYSIS ==========
    print(f"\n--- TRADE DIRECTION PATTERNS ---")
    # Classify trades as buy/sell relative to mid
    directions = []
    for ts in sorted(trade_ts_set.keys()):
        if ts in mid_by_ts:
            mid = mid_by_ts[ts]
            for trade in trade_ts_set[ts]:
                if trade['price'] >= mid:
                    directions.append(1)  # buy
                else:
                    directions.append(-1)  # sell
    
    if directions:
        runs = 1
        for i in range(1, len(directions)):
            if directions[i] != directions[i-1]:
                runs += 1
        expected_runs = 1 + 2 * sum(1 for d in directions if d == 1) * sum(1 for d in directions if d == -1) / len(directions)
        print(f"Number of direction changes: {runs}")
        print(f"Expected (random): {expected_runs:.0f}")
        print(f"Ratio: {runs/expected_runs:.3f} (< 1 means momentum, > 1 means mean-reversion)")
    
    # ========== EMA ANALYSIS ==========
    print(f"\n--- EMA FAIR VALUE QUALITY ---")
    for window in [3, 5, 10, 20]:
        alpha = 2 / (window + 1)
        ema = mids[0]
        errors = []
        for i in range(1, len(mids)):
            ema = alpha * mids[i] + (1 - alpha) * ema
            # Error = how far EMA is from actual next mid
            if i + 1 < len(mids):
                errors.append(abs(ema - mids[i+1]))
        mean_err = sum(errors) / len(errors)
        print(f"  EMA({window}) mean prediction error: {mean_err:.3f}")
    
    # Simple mid as predictor
    errors_mid = [abs(mids[i] - mids[i+1]) for i in range(len(mids)-1)]
    print(f"  Mid-price (no EMA) mean prediction error: {sum(errors_mid)/len(errors_mid):.3f}")
    
    # ========== INVENTORY RISK ==========
    print(f"\n--- INVENTORY RISK (max adverse move) ---")
    for horizon in [10, 50, 100, 200, 500]:
        if horizon < len(mids):
            max_moves = []
            for i in range(len(mids) - horizon):
                move = max(abs(mids[j] - mids[i]) for j in range(i, i + horizon))
                max_moves.append(move)
            mean_max = sum(max_moves) / len(max_moves)
            p95 = sorted(max_moves)[int(0.95 * len(max_moves))]
            p99 = sorted(max_moves)[int(0.99 * len(max_moves))]
            print(f"  Horizon={horizon} ticks: mean max move={mean_max:.1f}, P95={p95:.1f}, P99={p99:.1f}")
    
    return mids, spreads, trade_ts_set, mid_by_ts

# Run analysis on both days
for day_num, day_suffix in [(-2, '-2'), (-1, '-1')]:
    prices_file = os.path.join(DATA_DIR, f'prices_round_0_day_{day_suffix}.csv')
    trades_file = os.path.join(DATA_DIR, f'trades_round_0_day_{day_suffix}.csv')
    analyze_day(f"Day {day_suffix}", prices_file, trades_file)

print("\n\n" + "="*80)
print("CROSS-DAY COMPARISON COMPLETE")
print("="*80)
