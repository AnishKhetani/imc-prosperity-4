"""
Deep dive into:
1. TOMATOES mean-reversion (autocorr = -0.42) — can we exploit this?
2. EMERALDS narrow-spread (spread=8) ticks — what actually happens?
3. Optimal fair-value estimation for TOMATOES
4. Position management impact analysis
"""
import json, csv, io, math
from collections import defaultdict

def parse_training(price_path, trade_path):
    with open(price_path, 'r') as f:
        prices = list(csv.DictReader(f, delimiter=';'))
    with open(trade_path, 'r') as f:
        trades = list(csv.DictReader(f, delimiter=';'))
    return prices, trades

base = r'tutorial-round/data/TUTORIAL_ROUND_1'
prices_d1, trades_d1 = parse_training(f'{base}/prices_round_0_day_-1.csv', f'{base}/trades_round_0_day_-1.csv')
prices_d2, trades_d2 = parse_training(f'{base}/prices_round_0_day_-2.csv', f'{base}/trades_round_0_day_-2.csv')

# ═══════════════════════════════════════════════════════════════
#  1. TOMATOES MEAN REVERSION — BACKTEST DIFFERENT FAIR VALUES
# ═══════════════════════════════════════════════════════════════
print("=" * 80)
print("1. TOMATOES MEAN REVERSION BACKTEST")
print("   Autocorrelation = -0.42 means price overshoots then reverts")
print("   Question: Does a SLOWER EMA (more smoothing) beat a FASTER one?")
print("=" * 80)

for day_label, prices in [("day_-1", prices_d1), ("day_-2", prices_d2)]:
    tom = [r for r in prices if r.get('product') == 'TOMATOES']
    mids = []
    bids = []
    asks = []
    for r in tom:
        try:
            b1 = float(r.get('bid_price_1', 0) or 0)
            a1 = float(r.get('ask_price_1', 0) or 0)
            if b1 > 0 and a1 > 0:
                mids.append((b1 + a1) / 2)
                bids.append(b1)
                asks.append(a1)
            else:
                mids.append(mids[-1] if mids else 5000)
                bids.append(bids[-1] if bids else 4993)
                asks.append(asks[-1] if asks else 5007)
        except:
            mids.append(mids[-1] if mids else 5000)
            bids.append(bids[-1] if bids else 4993)
            asks.append(asks[-1] if asks else 5007)
    
    print(f"\n--- {day_label} ({len(mids)} ticks) ---")
    
    # Simulate market-making with different EMA windows
    # For each window, compute: if we quote at EMA ± WIDTH, how much do we earn?
    for ema_window in [1, 3, 5, 10, 20, 50]:
        for width in [4, 5, 6, 7]:
            ema = mids[0]
            alpha = 2.0 / (ema_window + 1)
            total_pnl = 0
            position = 0
            fills = 0
            
            for i in range(1, len(mids)):
                ema = alpha * mids[i] + (1 - alpha) * ema
                fair = round(ema)
                
                bid = fair - width
                ask = fair + width
                
                bot_ask = asks[i]  # bot's best ask (we can buy here if bid >= bot_ask)
                bot_bid = bids[i]  # bot's best bid (we can sell here if ask <= bot_bid)
                
                # Our bid gets filled if bot is willing to sell at or below our bid
                # i.e., bot's ask <= our bid
                if bot_ask <= bid and position < 80:
                    # We buy at bot_ask (in practice, our limit order at `bid` gets filled at bot_ask)
                    # Actually in this market, our resting order fills against bot's aggressive order
                    # Let's simulate: we place order at `bid`, bot hits it, we buy at `bid`
                    fill_price = bid  # We get filled at OUR price (limit order)
                    qty = min(12, 80 - position)  # approximate L1 volume
                    position += qty
                    total_pnl -= fill_price * qty
                    fills += 1
                
                if bot_bid >= ask and position > -80:
                    fill_price = ask
                    qty = min(12, 80 + position)
                    position -= qty
                    total_pnl += fill_price * qty
                    fills += 1
                
            # Liquidate at final mid
            total_pnl += position * mids[-1]
            
            if ema_window == 5:  # Only show width comparison for current EMA
                print(f"  EMA={ema_window:2d}, WIDTH={width}: fills={fills:5d}, PnL={total_pnl:8.1f}, final_pos={position:4d}")
            elif width == 5:  # Only show EMA comparison for current width
                print(f"  EMA={ema_window:2d}, WIDTH={width}: fills={fills:5d}, PnL={total_pnl:8.1f}, final_pos={position:4d}")

# ═══════════════════════════════════════════════════════════════
#  2. EMERALDS NARROW SPREAD — WHAT HAPPENS AT SPREAD=8?
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("2. EMERALDS NARROW SPREAD TICKS (spread=8)")
print("=" * 80)

for day_label, prices in [("day_-1", prices_d1), ("day_-2", prices_d2)]:
    em = [r for r in prices if r.get('product') == 'EMERALDS']
    
    narrow_ticks = []
    for i, r in enumerate(em):
        try:
            b1 = float(r.get('bid_price_1', 0) or 0)
            a1 = float(r.get('ask_price_1', 0) or 0)
            spread = a1 - b1
            if spread == 8:
                narrow_ticks.append({
                    'idx': i,
                    'ts': int(r.get('timestamp', 0)),
                    'b1': int(b1), 'a1': int(a1),
                    'b2': r.get('bid_price_2', ''),
                    'a2': r.get('ask_price_2', ''),
                    'bv1': r.get('bid_volume_1', ''),
                    'av1': r.get('ask_volume_1', ''),
                })
        except:
            pass
    
    print(f"\n  {day_label}: {len(narrow_ticks)} narrow-spread ticks")
    
    # What's the order book shape?
    patterns = defaultdict(int)
    for t in narrow_ticks:
        p = f"bid={t['b1']} bv={t['bv1']} b2={t['b2']} | ask={t['a1']} av={t['av1']} a2={t['a2']}"
        patterns[p] += 1
    
    for p, c in sorted(patterns.items(), key=lambda x: -x[1]):
        print(f"    {c:4d}x: {p}")
    
    # Are narrow spread ticks clustered?
    if narrow_ticks:
        gaps = [narrow_ticks[i+1]['ts'] - narrow_ticks[i]['ts'] for i in range(len(narrow_ticks)-1)]
        if gaps:
            print(f"    Gap between narrow ticks: min={min(gaps)}, max={max(gaps)}, mean={sum(gaps)/len(gaps):.0f}")
            consecutive = sum(1 for g in gaps if g == 100)
            print(f"    Consecutive (gap=100): {consecutive}/{len(gaps)}")

# ═══════════════════════════════════════════════════════════════
#  3. TOMATOES — OPTIMAL TAKE STRATEGY
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("3. TOMATOES — TAKE EDGE ANALYSIS")
print("   When we take at fair±edge, what's the expected PnL?")
print("=" * 80)

for day_label, prices in [("day_-1", prices_d1), ("day_-2", prices_d2)]:
    tom = [r for r in prices if r.get('product') == 'TOMATOES']
    mids = []
    bids = []
    asks = []
    bid_vols = []
    ask_vols = []
    for r in tom:
        try:
            b1 = float(r.get('bid_price_1', 0) or 0)
            a1 = float(r.get('ask_price_1', 0) or 0)
            bv1 = float(r.get('bid_volume_1', 0) or 0)
            av1 = float(r.get('ask_volume_1', 0) or 0)
            mids.append((b1 + a1) / 2 if b1 > 0 and a1 > 0 else mids[-1] if mids else 5000)
            bids.append(b1)
            asks.append(a1)
            bid_vols.append(bv1)
            ask_vols.append(av1)
        except:
            mids.append(mids[-1] if mids else 5000)
            bids.append(0)
            asks.append(0)
            bid_vols.append(0)
            ask_vols.append(0)
    
    print(f"\n--- {day_label} ---")
    
    # For each take_edge, simulate: buy at ask if ask <= fair - edge, sell at bid if bid >= fair + edge
    for ema_w in [5]:
        for take_edge in [-2, -1, 0, 1, 2, 3]:
            ema = mids[0]
            alpha = 2.0 / (ema_w + 1)
            take_pnl = 0
            take_count = 0
            position = 0
            
            for i in range(1, len(mids)):
                ema = alpha * mids[i] + (1 - alpha) * ema
                fair = round(ema)
                
                # Take buy: buy at ask if ask <= fair - take_edge
                if asks[i] > 0 and asks[i] <= fair - take_edge and position < 80:
                    qty = min(int(ask_vols[i]), 80 - position)
                    if qty > 0:
                        take_pnl -= asks[i] * qty
                        position += qty
                        take_count += 1
                
                # Take sell: sell at bid if bid >= fair + take_edge
                if bids[i] > 0 and bids[i] >= fair + take_edge and position > -80:
                    qty = min(int(bid_vols[i]), 80 + position)
                    if qty > 0:
                        take_pnl += bids[i] * qty
                        position -= qty
                        take_count += 1
            
            take_pnl += position * mids[-1]
            print(f"  EMA={ema_w}, TAKE_EDGE={take_edge:+d}: {take_count:5d} takes, PnL={take_pnl:8.1f}, final_pos={position}")

# ═══════════════════════════════════════════════════════════════
#  4. POSITION MANAGEMENT — How much does pos_fade help?
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("4. POSITION FADE IMPACT")
print("   adjusted_fair = ema + imb*W - pos*FADE")
print("   Higher FADE → more aggressive mean-reversion of position")
print("=" * 80)

for day_label, prices in [("day_-1", prices_d1), ("day_-2", prices_d2)]:
    tom = [r for r in prices if r.get('product') == 'TOMATOES']
    mids = []
    bids = []
    asks = []
    bid_vols = []
    ask_vols = []
    for r in tom:
        try:
            b1 = float(r.get('bid_price_1', 0) or 0)
            a1 = float(r.get('ask_price_1', 0) or 0)
            bv1 = float(r.get('bid_volume_1', 0) or 0)
            av1 = float(r.get('ask_volume_1', 0) or 0)
            mids.append((b1 + a1) / 2 if b1 > 0 and a1 > 0 else mids[-1] if mids else 5000)
            bids.append(b1)
            asks.append(a1)
            bid_vols.append(bv1)
            ask_vols.append(av1)
        except:
            mids.append(mids[-1] if mids else 5000)
            bids.append(0)
            asks.append(0)
            bid_vols.append(0)
            ask_vols.append(0)
    
    print(f"\n--- {day_label} ---")
    
    for pos_fade in [0, 0.02, 0.05, 0.1, 0.2, 0.5]:
        ema = mids[0]
        alpha = 2.0 / (5 + 1)
        width = 5
        total_pnl = 0
        position = 0
        fills = 0
        max_pos = 0
        
        for i in range(1, len(mids)):
            ema = alpha * mids[i] + (1 - alpha) * ema
            
            # Compute imbalance
            if bid_vols[i] + ask_vols[i] > 0:
                imb = (bid_vols[i] - ask_vols[i]) / (bid_vols[i] + ask_vols[i])
            else:
                imb = 0
            
            adjusted = ema + imb * 0.5 - position * pos_fade
            fair = round(adjusted)
            
            bid = fair - width
            ask = fair + width
            
            if asks[i] > 0 and asks[i] <= bid and position < 80:
                qty = min(int(ask_vols[i]), 80 - position)
                if qty > 0:
                    position += qty
                    total_pnl -= bid * qty
                    fills += 1
            
            if bids[i] > 0 and bids[i] >= ask and position > -80:
                qty = min(int(bid_vols[i]), 80 + position)
                if qty > 0:
                    position -= qty
                    total_pnl += ask * qty
                    fills += 1
            
            max_pos = max(max_pos, abs(position))
        
        total_pnl += position * mids[-1]
        print(f"  FADE={pos_fade:.2f}: fills={fills:5d}, PnL={total_pnl:8.1f}, max_pos={max_pos:3d}, final_pos={position:4d}")

# ═══════════════════════════════════════════════════════════════
#  5. MEAN-REVERSION SIGNAL — Direct exploitation
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("5. MEAN REVERSION DIRECT EXPLOIT")
print("   With autocorr=-0.42, price at t+1 tends to revert toward t-1")
print("   Strategy: shift fair value OPPOSITE to last move")
print("=" * 80)

for day_label, prices in [("day_-1", prices_d1), ("day_-2", prices_d2)]:
    tom = [r for r in prices if r.get('product') == 'TOMATOES']
    mids = []
    bids = []
    asks = []
    for r in tom:
        try:
            b1 = float(r.get('bid_price_1', 0) or 0)
            a1 = float(r.get('ask_price_1', 0) or 0)
            mids.append((b1 + a1) / 2 if b1 > 0 and a1 > 0 else mids[-1] if mids else 5000)
            bids.append(b1)
            asks.append(a1)
        except:
            mids.append(mids[-1] if mids else 5000)
            bids.append(0)
            asks.append(0)
    
    print(f"\n--- {day_label} ---")
    
    # Test: shift fair by -beta * (mid_t - mid_{t-1})
    for beta in [0, 0.1, 0.2, 0.3, 0.5, 0.7, 1.0]:
        ema = mids[0]
        alpha = 2.0 / (5 + 1)
        width = 5
        total_pnl = 0
        position = 0
        fills = 0
        
        for i in range(2, len(mids)):
            ema = alpha * mids[i] + (1 - alpha) * ema
            last_move = mids[i] - mids[i-1]
            
            # Shift fair opposite to last move
            adjusted = ema - beta * last_move - position * 0.05
            fair = round(adjusted)
            
            bid = fair - width
            ask = fair + width
            
            if asks[i] > 0 and asks[i] <= bid and position < 80:
                qty = min(12, 80 - position)
                position += qty
                total_pnl -= bid * qty
                fills += 1
            
            if bids[i] > 0 and bids[i] >= ask and position > -80:
                qty = min(12, 80 + position)
                position -= qty
                total_pnl += ask * qty
                fills += 1
        
        total_pnl += position * mids[-1]
        print(f"  beta={beta:.1f}: fills={fills:5d}, PnL={total_pnl:8.1f}, final_pos={position}")

# ═══════════════════════════════════════════════════════════════
#  6. EMERALDS — Can we get MORE fills with dynamic width?
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("6. EMERALDS — ADAPTIVE WIDTH DURING NARROW SPREAD")
print("=" * 80)

for day_label, prices in [("day_-1", prices_d1), ("day_-2", prices_d2)]:
    em = [r for r in prices if r.get('product') == 'EMERALDS']
    
    for strategy in ["fixed_7", "fixed_3", "adaptive"]:
        total_pnl = 0
        position = 0
        fills = 0
        
        for i, r in enumerate(em):
            try:
                b1 = float(r.get('bid_price_1', 0) or 0)
                a1 = float(r.get('ask_price_1', 0) or 0)
                spread = a1 - b1 if a1 > 0 and b1 > 0 else 16
                bv1 = float(r.get('bid_volume_1', 0) or 0)
                av1 = float(r.get('ask_volume_1', 0) or 0)
            except:
                continue
            
            fair = 10000
            
            if strategy == "fixed_7":
                width = 7
            elif strategy == "fixed_3":
                width = 3
            elif strategy == "adaptive":
                # Use width=7 normally, but width=3 when spread is narrow
                if spread <= 8:
                    width = 3
                else:
                    width = 7
            
            bid = fair - width
            ask = fair + width
            
            # Take: buy at ask if ask <= fair - 1
            if a1 > 0 and a1 <= fair - 1 and position < 80:
                qty = min(int(av1), 80 - position)
                if qty > 0:
                    position += qty
                    total_pnl -= a1 * qty
                    fills += 1
            
            # Take: sell at bid if bid >= fair + 1
            if b1 > 0 and b1 >= fair + 1 and position > -80:
                qty = min(int(bv1), 80 + position)
                if qty > 0:
                    position -= qty
                    total_pnl += b1 * qty
                    fills += 1
            
            # Make: our bid gets hit if bot sells at our bid
            # This happens when bot_ask <= our_bid (bot crosses our bid)
            if a1 > 0 and a1 <= bid and position < 80:
                qty = min(int(av1), 80 - position)
                if qty > 0:
                    position += qty
                    total_pnl -= bid * qty  # filled at our price
                    fills += 1
            
            if b1 > 0 and b1 >= ask and position > -80:
                qty = min(int(bv1), 80 + position)
                if qty > 0:
                    position -= qty
                    total_pnl += ask * qty
                    fills += 1
        
        total_pnl += position * 10000  # liquidation at fair
        print(f"  {day_label} {strategy:12s}: fills={fills:5d}, PnL={total_pnl:8.1f}, final_pos={position}")

# ═══════════════════════════════════════════════════════════════
#  7. TOMATOES - IMB_WEIGHT and DEPTH_CONTRARIAN impact
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("7. IMB_WEIGHT AND DEPTH_CONTRARIAN GRID SEARCH")
print("=" * 80)

for day_label, prices in [("day_-1", prices_d1), ("day_-2", prices_d2)]:
    tom = [r for r in prices if r.get('product') == 'TOMATOES']
    
    # Pre-compute common data
    data_rows = []
    for r in tom:
        try:
            b1 = float(r.get('bid_price_1', 0) or 0)
            a1 = float(r.get('ask_price_1', 0) or 0)
            bv1 = float(r.get('bid_volume_1', 0) or 0)
            av1 = float(r.get('ask_volume_1', 0) or 0)
            b2 = float(r.get('bid_price_2', 0) or 0)
            a2 = float(r.get('ask_price_2', 0) or 0)
            bv2 = float(r.get('bid_volume_2', 0) or 0)
            av2 = float(r.get('ask_volume_2', 0) or 0)
            
            mid = (b1 + a1) / 2 if b1 > 0 and a1 > 0 else None
            
            if b1 > 0 and a1 > 0:
                l1_total = bv1 + av1
                l1_imb = (bv1 - av1) / l1_total if l1_total > 0 else 0
                bid_depth = bv1 + bv2
                ask_depth = av1 + av2
                depth_total = bid_depth + ask_depth
                depth_imb = (bid_depth - ask_depth) / depth_total if depth_total > 0 else 0
            else:
                l1_imb = 0
                depth_imb = 0
            
            data_rows.append({
                'mid': mid, 'b1': b1, 'a1': a1, 'bv1': bv1, 'av1': av1,
                'l1_imb': l1_imb, 'depth_imb': depth_imb
            })
        except:
            data_rows.append({'mid': None, 'b1': 0, 'a1': 0, 'bv1': 0, 'av1': 0,
                            'l1_imb': 0, 'depth_imb': 0})
    
    print(f"\n--- {day_label} ---")
    print(f"  {'IMB_W':>6} {'DEPTH':>6} {'fills':>6} {'PnL':>10} {'final_pos':>10}")
    
    for imb_w in [0, 0.25, 0.5, 0.75, 1.0]:
        for depth_c in [0, 0.5, 1, 2]:
            ema = data_rows[0]['mid'] or 5000
            alpha = 2.0 / (5 + 1)
            width = 5
            total_pnl = 0
            position = 0
            fills = 0
            
            for i in range(1, len(data_rows)):
                d = data_rows[i]
                if d['mid'] is None:
                    continue
                
                ema = alpha * d['mid'] + (1 - alpha) * ema
                adjusted = ema + d['l1_imb'] * imb_w - position * 0.05
                fair = round(adjusted)
                
                bid = fair - width
                ask = fair + width
                
                # Apply depth_contrarian
                if d['depth_imb'] > 0.1:
                    ask -= int(depth_c)
                elif d['depth_imb'] < -0.1:
                    bid += int(depth_c)
                
                if d['a1'] > 0 and d['a1'] <= bid and position < 80:
                    qty = min(int(d['av1']), 80 - position)
                    if qty > 0:
                        position += qty
                        total_pnl -= bid * qty
                        fills += 1
                
                if d['b1'] > 0 and d['b1'] >= ask and position > -80:
                    qty = min(int(d['bv1']), 80 + position)
                    if qty > 0:
                        position -= qty
                        total_pnl += ask * qty
                        fills += 1
            
            last_mid = data_rows[-1]['mid'] or 5000
            total_pnl += position * last_mid
            print(f"  {imb_w:6.2f} {depth_c:6.1f} {fills:6d} {total_pnl:10.1f} {position:10d}")

print("\n\nDONE.")
