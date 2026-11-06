"""Analyze L2 order book for predictive signals."""
import json
import os

data_dir = os.path.join(os.path.dirname(__file__), '..', 'round_data', 'ROUND_2')

def load_round_data(day):
    fn = os.path.join(data_dir, f'prices_round_2_day_{day}.csv')
    rows = []
    with open(fn) as f:
        header = f.readline().strip().split(';')
        for line in f:
            parts = line.strip().split(';')
            row = dict(zip(header, parts))
            rows.append(row)
    return rows

def parse_book(row, product):
    """Parse full order book for a product."""
    bids = {}
    asks = {}
    for i in range(1, 4):
        bp_key = f'bid_price_{i}'
        bv_key = f'bid_volume_{i}'
        ap_key = f'ask_price_{i}'
        av_key = f'ask_volume_{i}'
        if row.get(bp_key) and row.get(bv_key):
            try:
                bids[int(row[bp_key])] = int(row[bv_key])
            except:
                pass
        if row.get(ap_key) and row.get(av_key):
            try:
                asks[int(row[ap_key])] = int(row[av_key])
            except:
                pass
    return bids, asks

# Check what product data looks like
for day in [0]:
    rows = load_round_data(day)
    aco_rows = [r for r in rows if r.get('product') == 'ASH_COATED_OSMIUM']
    
    # Look at L2 volumes and prices
    l2_imb_count = 0
    correct = 0
    total_pred = 0
    
    prev_mid = None
    
    for i, row in enumerate(aco_rows[:100]):
        bids, asks = parse_book(row, 'ASH_COATED_OSMIUM')
        
        if not bids or not asks:
            continue
            
        bb = max(bids.keys())
        ba = min(asks.keys())
        mid = (bb + ba) / 2.0
        
        # Calculate L1 and L2 volumes
        bid_prices = sorted(bids.keys(), reverse=True)
        ask_prices = sorted(asks.keys())
        
        l1_bv = bids[bid_prices[0]]
        l1_av = asks[ask_prices[0]]
        
        l2_bv = bids.get(bid_prices[1], 0) if len(bid_prices) > 1 else 0
        l2_av = asks.get(ask_prices[1], 0) if len(ask_prices) > 1 else 0
        
        # Total visible volume
        total_bv = sum(bids.values())
        total_av = sum(asks.values())
        
        spread = ba - bb
        
        if i < 10:
            print(f"Tick {row.get('timestamp','?')}: bb={bb} ba={ba} spread={spread}")
            print(f"  Bids: {dict(sorted(bids.items(), reverse=True))}")
            print(f"  Asks: {dict(sorted(asks.items()))}")
            print(f"  L1: bv={l1_bv} av={l1_av} | L2: bv={l2_bv} av={l2_av}")
            print(f"  Total: bv={total_bv} av={total_av}")
            print()
    
    # Now check: does the L2 total volume ratio predict mid price movement?
    print("\n--- L2 Total Volume Ratio vs Next Mid Move ---")
    mids = []
    ratios = []
    
    for row in aco_rows:
        bids, asks = parse_book(row, 'ASH_COATED_OSMIUM')
        if not bids or not asks:
            mids.append(None)
            ratios.append(None)
            continue
        bb = max(bids.keys())
        ba = min(asks.keys())
        mid = (bb + ba) / 2.0
        total_bv = sum(bids.values())
        total_av = sum(asks.values())
        ratio = (total_bv - total_av) / (total_bv + total_av) if (total_bv + total_av) > 0 else 0
        mids.append(mid)
        ratios.append(ratio)
    
    # Check prediction accuracy
    correct_l2 = 0
    total_l2 = 0
    for i in range(len(mids) - 1):
        if mids[i] is None or mids[i+1] is None or ratios[i] is None:
            continue
        move = mids[i+1] - mids[i]
        if move == 0:
            continue
        total_l2 += 1
        if (ratios[i] > 0 and move > 0) or (ratios[i] < 0 and move < 0):
            correct_l2 += 1
    
    print(f"L2 total volume imbalance prediction: {correct_l2}/{total_l2} = {correct_l2/total_l2*100:.1f}%")
    
    # Check L1 only for comparison
    correct_l1 = 0
    total_l1 = 0
    l1_ratios = []
    for row in aco_rows:
        bids, asks = parse_book(row, 'ASH_COATED_OSMIUM')
        if not bids or not asks:
            l1_ratios.append(None)
            continue
        bb = max(bids.keys())
        ba = min(asks.keys())
        l1_bv = bids[bb]
        l1_av = asks[ba]
        ratio = (l1_bv - l1_av) / (l1_bv + l1_av) if (l1_bv + l1_av) > 0 else 0
        l1_ratios.append(ratio)
    
    for i in range(len(mids) - 1):
        if mids[i] is None or mids[i+1] is None or l1_ratios[i] is None:
            continue
        move = mids[i+1] - mids[i]
        if move == 0:
            continue
        total_l1 += 1
        if (l1_ratios[i] > 0 and move > 0) or (l1_ratios[i] < 0 and move < 0):
            correct_l1 += 1
    
    print(f"L1 volume imbalance prediction: {correct_l1}/{total_l1} = {correct_l1/total_l1*100:.1f}%")
    
    # Check: L2 bid depth vs L2 ask depth
    print("\n--- L2-only (excluding L1) volume ---")
    correct_l2only = 0
    total_l2only = 0
    l2only_ratios = []
    for row in aco_rows:
        bids, asks = parse_book(row, 'ASH_COATED_OSMIUM')
        if not bids or not asks:
            l2only_ratios.append(None)
            continue
        bid_prices = sorted(bids.keys(), reverse=True)
        ask_prices = sorted(asks.keys())
        l2_bv = sum(bids[p] for p in bid_prices[1:]) if len(bid_prices) > 1 else 0
        l2_av = sum(asks[p] for p in ask_prices[1:]) if len(ask_prices) > 1 else 0
        ratio = (l2_bv - l2_av) / (l2_bv + l2_av) if (l2_bv + l2_av) > 0 else 0
        l2only_ratios.append(ratio)
    
    for i in range(len(mids) - 1):
        if mids[i] is None or mids[i+1] is None or l2only_ratios[i] is None:
            continue
        move = mids[i+1] - mids[i]
        if move == 0:
            continue
        total_l2only += 1
        if (l2only_ratios[i] > 0 and move > 0) or (l2only_ratios[i] < 0 and move < 0):
            correct_l2only += 1
    
    print(f"L2-only volume imbalance prediction: {correct_l2only}/{total_l2only} = {correct_l2only/total_l2only*100:.1f}%")
    
    # Spread as predictor
    print("\n--- Spread width as signal ---")
    spreads_when_move_up = []
    spreads_when_move_down = []
    for i, row in enumerate(aco_rows[:-1]):
        bids, asks = parse_book(row, 'ASH_COATED_OSMIUM')
        if not bids or not asks or mids[i] is None or mids[i+1] is None:
            continue
        bb = max(bids.keys())
        ba = min(asks.keys())
        spread = ba - bb
        move = mids[i+1] - mids[i]
        if move > 0:
            spreads_when_move_up.append(spread)
        elif move < 0:
            spreads_when_move_down.append(spread)
    
    if spreads_when_move_up:
        print(f"Avg spread before up move: {sum(spreads_when_move_up)/len(spreads_when_move_up):.2f}")
    if spreads_when_move_down:
        print(f"Avg spread before down move: {sum(spreads_when_move_down)/len(spreads_when_move_down):.2f}")
