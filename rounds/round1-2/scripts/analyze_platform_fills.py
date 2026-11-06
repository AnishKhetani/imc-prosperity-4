"""
Analyze platform fill mechanics from actual JSON logs.
Compare 44861 (best, PnL=2175) vs 45133 (current, PnL=2047).
"""
import json
import os
from collections import defaultdict

LOG_DIR = r".\logs"

def analyze_log(sim_id):
    log_file = os.path.join(LOG_DIR, str(sim_id), f"{sim_id}.log")
    
    print(f"\n{'='*80}")
    print(f"  PLATFORM LOG ANALYSIS: {sim_id}")
    print(f"{'='*80}")
    
    with open(log_file, 'r') as f:
        content = f.read()
    
    # The log format: each line is a JSON array from the logger
    # [compressed_state, compressed_orders, conversions, trader_data, logs]
    lines = content.strip().split('\n')
    
    ticks = []
    for line in lines:
        try:
            data = json.loads(line)
            ticks.append(data)
        except json.JSONDecodeError:
            continue
    
    print(f"Total log lines: {len(ticks)}")
    
    # Analyze the compressed state format
    if ticks:
        # Show first tick to understand format
        first = ticks[0]
        print(f"\nFirst tick structure (types): {[type(x).__name__ for x in first]}")
        
        # State is first element: [timestamp, traderData, listings, depths, ownTrades, marketTrades, position, observations]
        state0 = first[0]
        print(f"State element count: {len(state0)}")
        print(f"State[0] (timestamp): {state0[0]}")
        
        # Depths format: {product: [buy_orders, sell_orders]}
        # where orders = {price: volume}
        if len(state0) > 3:
            depths = state0[3]
            print(f"Products in depths: {list(depths.keys()) if isinstance(depths, dict) else 'not a dict'}")
            if isinstance(depths, dict) and 'TOMATOES' in depths:
                tom_depth = depths['TOMATOES']
                print(f"TOMATOES depth sample: {tom_depth}")
    
    # Track TOMATOES fills and orders across ticks
    tom_fills_buy = []
    tom_fills_sell = []
    tom_mids = []
    tom_spreads = []
    our_orders_per_tick = []
    own_trade_ticks = 0
    
    prev_position = 0
    position_history = []
    pnl_history = []
    
    for i, tick in enumerate(ticks):
        state = tick[0]  # compressed state
        orders = tick[1]  # compressed orders
        
        ts = state[0]
        
        # Parse depths
        depths = state[3] if len(state) > 3 else {}
        if isinstance(depths, dict) and 'TOMATOES' in depths:
            tom_depth = depths['TOMATOES']
            if isinstance(tom_depth, list) and len(tom_depth) == 2:
                buy_orders = tom_depth[0]  # {price: vol}
                sell_orders = tom_depth[1]  # {price: vol}
                
                if buy_orders and sell_orders:
                    best_bid = max(int(k) for k in buy_orders.keys())
                    best_ask = min(int(k) for k in sell_orders.keys())
                    mid = (best_bid + best_ask) / 2
                    spread = best_ask - best_bid
                    tom_mids.append(mid)
                    tom_spreads.append(spread)
        
        # Parse own trades (fills)
        own_trades = state[4] if len(state) > 4 else {}
        if isinstance(own_trades, dict) and 'TOMATOES' in own_trades:
            for trade in own_trades['TOMATOES']:
                # trade format: [symbol, price, quantity, buyer, seller, timestamp]
                if isinstance(trade, list):
                    price = trade[1]
                    qty = trade[2]
                    buyer = trade[3]
                    seller = trade[4]
                    if buyer == 'SUBMISSION':
                        tom_fills_buy.append({'ts': ts, 'price': price, 'qty': qty, 'mid': tom_mids[-1] if tom_mids else 0})
                    elif seller == 'SUBMISSION':
                        tom_fills_sell.append({'ts': ts, 'price': price, 'qty': abs(qty), 'mid': tom_mids[-1] if tom_mids else 0})
                elif isinstance(trade, dict):
                    price = trade.get('price', 0)
                    qty = trade.get('quantity', 0)
                    buyer = trade.get('buyer', '')
                    seller = trade.get('seller', '')
                    if buyer == 'SUBMISSION':
                        tom_fills_buy.append({'ts': ts, 'price': price, 'qty': qty, 'mid': tom_mids[-1] if tom_mids else 0})
                    elif seller == 'SUBMISSION':
                        tom_fills_sell.append({'ts': ts, 'price': price, 'qty': abs(qty), 'mid': tom_mids[-1] if tom_mids else 0})
            own_trade_ticks += 1
        
        # Parse our orders
        if isinstance(orders, dict) and 'TOMATOES' in orders:
            our_orders_per_tick.append(orders['TOMATOES'])
        
        # Position tracking
        positions = state[6] if len(state) > 6 else {}
        if isinstance(positions, dict) and 'TOMATOES' in positions:
            pos = positions['TOMATOES']
            position_history.append(pos)
        else:
            position_history.append(prev_position)
        prev_position = position_history[-1]
    
    print(f"\n--- TOMATOES FILL ANALYSIS ---")
    print(f"Buy fills: {len(tom_fills_buy)}")
    print(f"Sell fills: {len(tom_fills_sell)}")
    print(f"Total fills: {len(tom_fills_buy) + len(tom_fills_sell)}")
    print(f"Ticks with own trades: {own_trade_ticks}")
    
    # Fill price analysis
    if tom_fills_buy:
        buy_edges = [f['mid'] - f['price'] for f in tom_fills_buy]
        buy_vols = [f['qty'] for f in tom_fills_buy]
        print(f"\nBuy fills:")
        print(f"  Mean buy price: {sum(f['price'] for f in tom_fills_buy)/len(tom_fills_buy):.2f}")
        print(f"  Mean edge (mid-buy): {sum(buy_edges)/len(buy_edges):.2f}")
        print(f"  Min edge: {min(buy_edges):.2f}")
        print(f"  Max edge: {max(buy_edges):.2f}")
        print(f"  Mean volume per fill: {sum(buy_vols)/len(buy_vols):.1f}")
        print(f"  Total volume bought: {sum(buy_vols)}")
    
    if tom_fills_sell:
        sell_edges = [f['price'] - f['mid'] for f in tom_fills_sell]
        sell_vols = [f['qty'] for f in tom_fills_sell]
        print(f"\nSell fills:")
        print(f"  Mean sell price: {sum(f['price'] for f in tom_fills_sell)/len(tom_fills_sell):.2f}")
        print(f"  Mean edge (sell-mid): {sum(sell_edges)/len(sell_edges):.2f}")
        print(f"  Min edge: {min(sell_edges):.2f}")
        print(f"  Max edge: {max(sell_edges):.2f}")
        print(f"  Mean volume per fill: {sum(sell_vols)/len(sell_vols):.1f}")
        print(f"  Total volume sold: {sum(sell_vols)}")
    
    # Spread analysis
    if tom_spreads:
        print(f"\n--- PLATFORM SPREAD ANALYSIS ---")
        spread_dist = defaultdict(int)
        for s in tom_spreads:
            spread_dist[int(s)] += 1
        for k in sorted(spread_dist.keys()):
            pct = spread_dist[k] / len(tom_spreads) * 100
            print(f"  Spread={k}: {spread_dist[k]} ({pct:.1f}%)")
        print(f"  Mean spread: {sum(tom_spreads)/len(tom_spreads):.2f}")
    
    # Position analysis
    if position_history:
        print(f"\n--- POSITION ANALYSIS ---")
        print(f"  Max long: {max(position_history)}")
        print(f"  Max short: {min(position_history)}")
        print(f"  Mean position: {sum(position_history)/len(position_history):.1f}")
        print(f"  Final position: {position_history[-1]}")
        
        # Time spent at various position levels
        pos_dist = defaultdict(int)
        for p in position_history:
            bucket = (p // 10) * 10
            pos_dist[bucket] += 1
        print(f"\n  Position distribution (buckets):")
        for k in sorted(pos_dist.keys()):
            print(f"    [{k},{k+10}): {pos_dist[k]} ticks ({pos_dist[k]/len(position_history)*100:.1f}%)")
    
    # Calculate realized PnL from fills
    total_buy_cost = sum(f['price'] * f['qty'] for f in tom_fills_buy)
    total_sell_rev = sum(f['price'] * f['qty'] for f in tom_fills_sell)
    total_bought = sum(f['qty'] for f in tom_fills_buy)
    total_sold = sum(f['qty'] for f in tom_fills_sell)
    net_pos = total_bought - total_sold
    
    print(f"\n--- PnL DECOMPOSITION ---")
    print(f"  Total bought: {total_bought} units @ avg {total_buy_cost/total_bought:.2f}" if total_bought else "  No buys")
    print(f"  Total sold: {total_sold} units @ avg {total_sell_rev/total_sold:.2f}" if total_sold else "  No sells")
    print(f"  Net position: {net_pos}")
    print(f"  Realized (sell-buy): {total_sell_rev - total_buy_cost:.2f}")
    if tom_mids:
        final_mid = tom_mids[-1]
        unrealized = net_pos * final_mid
        print(f"  Final mid: {final_mid}")
        print(f"  Unrealized (net_pos * final_mid): {unrealized:.2f}")
        print(f"  Estimated total PnL: {total_sell_rev - total_buy_cost + unrealized:.2f}")
    
    # Order analysis - what we're sending
    if our_orders_per_tick:
        print(f"\n--- OUR ORDER ANALYSIS ---")
        # Sample first few
        for i in range(min(3, len(our_orders_per_tick))):
            print(f"  Tick {i}: {our_orders_per_tick[i]}")
    
    return tom_fills_buy, tom_fills_sell, tom_mids, tom_spreads, position_history

# Analyze both logs
for sim_id in [44861, 45133]:
    try:
        analyze_log(sim_id)
    except Exception as e:
        print(f"Error analyzing {sim_id}: {e}")
        import traceback
        traceback.print_exc()
