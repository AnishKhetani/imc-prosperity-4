"""
Analyze platform fills from the actual JSON log format.
The log is a single JSON with activitiesLog (CSV) and trade data.
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
        data = json.load(f)
    
    print(f"Top-level keys: {list(data.keys())}")
    
    # Parse activitiesLog CSV
    activities = data.get('activitiesLog', '')
    lines = activities.strip().split('\n')
    header = lines[0].split(';')
    print(f"Activities header: {header}")
    print(f"Total activity rows: {len(lines)-1}")
    
    # Parse into records
    tom_records = []
    em_records = []
    for line in lines[1:]:
        parts = line.split(';')
        rec = dict(zip(header, parts))
        if rec.get('product') == 'TOMATOES':
            tom_records.append(rec)
        elif rec.get('product') == 'EMERALDS':
            em_records.append(rec)
    
    print(f"TOMATOES ticks: {len(tom_records)}")
    print(f"EMERALDS ticks: {len(em_records)}")
    
    # TOMATOES spread analysis
    spreads = []
    mids = []
    for r in tom_records:
        try:
            bid1 = float(r.get('bid_price_1', '0') or '0')
            ask1 = float(r.get('ask_price_1', '0') or '0')
            if bid1 > 0 and ask1 > 0:
                spreads.append(ask1 - bid1)
                mids.append((bid1 + ask1) / 2)
        except ValueError:
            pass
    
    print(f"\n--- PLATFORM SPREAD (including our orders) ---")
    spread_dist = defaultdict(int)
    for s in spreads:
        spread_dist[int(s)] += 1
    for k in sorted(spread_dist.keys()):
        pct = spread_dist[k] / len(spreads) * 100
        print(f"  Spread={k}: {spread_dist[k]} ({pct:.1f}%)")
    print(f"  Mean spread: {sum(spreads)/len(spreads):.2f}")
    
    # PnL progression
    pnls = []
    for r in tom_records:
        try:
            pnl = float(r.get('profit_and_loss', '0') or '0')
            pnls.append(pnl)
        except ValueError:
            pass
    
    if pnls:
        print(f"\n--- TOMATOES PnL PROGRESSION ---")
        print(f"  Final PnL: {pnls[-1]:.2f}")
        print(f"  Max PnL: {max(pnls):.2f}")
        print(f"  Min PnL: {min(pnls):.2f}")
        # PnL at 25%, 50%, 75%
        n = len(pnls)
        print(f"  PnL at 25%: {pnls[n//4]:.2f}")
        print(f"  PnL at 50%: {pnls[n//2]:.2f}")
        print(f"  PnL at 75%: {pnls[3*n//4]:.2f}")
    
    # Parse trades
    trades = data.get('tradeLogs', data.get('trades', []))
    if not trades:
        # Maybe the trades are embedded differently
        for key in data.keys():
            if 'trade' in key.lower():
                print(f"  Found trade key: {key}")
                trades = data[key]
    
    # Filter TOMATOES trades where SUBMISSION is involved
    our_tom_trades = []
    if isinstance(trades, list):
        for t in trades:
            if isinstance(t, dict) and t.get('symbol') == 'TOMATOES':
                if t.get('buyer') == 'SUBMISSION' or t.get('seller') == 'SUBMISSION':
                    our_tom_trades.append(t)
    
    print(f"\n--- OUR TOMATOES TRADES ---")
    print(f"Total trades with SUBMISSION: {len(our_tom_trades)}")
    
    if our_tom_trades:
        buys = [t for t in our_tom_trades if t.get('buyer') == 'SUBMISSION']
        sells = [t for t in our_tom_trades if t.get('seller') == 'SUBMISSION']
        
        print(f"Buy fills: {len(buys)}")
        print(f"Sell fills: {len(sells)}")
        
        # Build mid lookup from activities
        mid_by_ts = {}
        bid_by_ts = {}
        ask_by_ts = {}
        for r in tom_records:
            try:
                ts = int(r['timestamp'])
                bid1 = float(r.get('bid_price_1', '0') or '0')
                ask1 = float(r.get('ask_price_1', '0') or '0')
                if bid1 > 0 and ask1 > 0:
                    mid_by_ts[ts] = (bid1 + ask1) / 2
                    bid_by_ts[ts] = bid1
                    ask_by_ts[ts] = ask1
            except ValueError:
                pass
        
        # Analyze buy fills
        if buys:
            print(f"\n  Buy fills analysis:")
            buy_edges = []
            buy_prices = []
            buy_vols = []
            for t in buys:
                ts = t['timestamp']
                price = t['price']
                qty = t['quantity']
                mid = mid_by_ts.get(ts, 0)
                edge = mid - price if mid else 0
                buy_edges.append(edge)
                buy_prices.append(price)
                buy_vols.append(qty)
            
            print(f"    Total volume: {sum(buy_vols)}")
            print(f"    Avg price: {sum(buy_prices)/len(buy_prices):.2f}")
            print(f"    Avg volume/fill: {sum(buy_vols)/len(buy_vols):.1f}")
            print(f"    Avg edge (mid-price): {sum(buy_edges)/len(buy_edges):.2f}")
            
            # Edge distribution
            edge_dist = defaultdict(int)
            for e in buy_edges:
                edge_dist[round(e, 1)] += 1
            print(f"    Edge distribution:")
            for k in sorted(edge_dist.keys()):
                print(f"      Edge={k}: {edge_dist[k]}")
        
        if sells:
            print(f"\n  Sell fills analysis:")
            sell_edges = []
            sell_prices = []
            sell_vols = []
            for t in sells:
                ts = t['timestamp']
                price = t['price']
                qty = t['quantity']
                mid = mid_by_ts.get(ts, 0)
                edge = price - mid if mid else 0
                sell_edges.append(edge)
                sell_prices.append(price)
                sell_vols.append(qty)
            
            print(f"    Total volume: {sum(sell_vols)}")
            print(f"    Avg price: {sum(sell_prices)/len(sell_prices):.2f}")
            print(f"    Avg volume/fill: {sum(sell_vols)/len(sell_vols):.1f}")
            print(f"    Avg edge (price-mid): {sum(sell_edges)/len(sell_edges):.2f}")
            
            edge_dist = defaultdict(int)
            for e in sell_edges:
                edge_dist[round(e, 1)] += 1
            print(f"    Edge distribution:")
            for k in sorted(edge_dist.keys()):
                print(f"      Edge={k}: {edge_dist[k]}")
        
        # PnL from trades
        total_buy_cost = sum(t['price'] * t['quantity'] for t in buys)
        total_sell_rev = sum(t['price'] * t['quantity'] for t in sells)
        total_bought = sum(t['quantity'] for t in buys)
        total_sold = sum(t['quantity'] for t in sells)
        net_pos = total_bought - total_sold
        
        print(f"\n  Trade PnL:")
        print(f"    Total bought: {total_bought} units")
        print(f"    Total sold: {total_sold} units")
        print(f"    Net position: {net_pos}")
        print(f"    Realized cash: {total_sell_rev - total_buy_cost:.2f}")
        if mids:
            final_mid = mids[-1]
            unrealized = net_pos * final_mid
            print(f"    Final mid: {final_mid}")
            print(f"    Unrealized: {unrealized:.2f}")
            print(f"    Estimated total: {total_sell_rev - total_buy_cost + unrealized:.2f}")
        
        # Timing analysis
        trade_timestamps = sorted(set(t['timestamp'] for t in our_tom_trades))
        if len(trade_timestamps) > 1:
            gaps = [trade_timestamps[i+1] - trade_timestamps[i] for i in range(len(trade_timestamps)-1)]
            print(f"\n  Timing:")
            print(f"    Ticks with fills: {len(trade_timestamps)} / {len(tom_records)}")
            print(f"    Fill rate: {len(trade_timestamps)/len(tom_records)*100:.1f}%")
            print(f"    Mean gap: {sum(gaps)/len(gaps):.0f}")
            print(f"    Min gap: {min(gaps)}")
            print(f"    Max gap: {max(gaps)}")
        
        # Position path reconstruction
        position = 0
        positions = [0]
        max_pos = 0
        min_pos = 0
        for t in sorted(our_tom_trades, key=lambda x: x['timestamp']):
            if t.get('buyer') == 'SUBMISSION':
                position += t['quantity']
            else:
                position -= t['quantity']
            positions.append(position)
            max_pos = max(max_pos, position)
            min_pos = min(min_pos, position)
        
        print(f"\n  Position path:")
        print(f"    Max long: {max_pos}")
        print(f"    Max short: {min_pos}")
        print(f"    Final: {position}")
        
        # Trade counterparties
        counterparties = defaultdict(int)
        for t in our_tom_trades:
            if t.get('buyer') == 'SUBMISSION':
                cp = t.get('seller', 'unknown')
            else:
                cp = t.get('buyer', 'unknown')
            counterparties[cp] += 1
        print(f"\n  Counterparties:")
        for cp, count in sorted(counterparties.items(), key=lambda x: -x[1]):
            print(f"    {cp}: {count}")
        
        # Are our fills takes or makes?
        takes = 0
        makes = 0
        for t in our_tom_trades:
            ts = t['timestamp']
            price = t['price']
            bid = bid_by_ts.get(ts, 0)
            ask = ask_by_ts.get(ts, 0)
            
            if t.get('buyer') == 'SUBMISSION':
                # We bought - if price <= our bid (L1 = our bid level), it's a make
                # If price >= ask (we crossed), it's a take
                if ask > 0 and price >= ask:
                    takes += 1
                else:
                    makes += 1
            else:
                # We sold - if price >= our ask (L1 = our ask level), it's a make
                # If price <= bid, it's a take
                if bid > 0 and price <= bid:
                    takes += 1
                else:
                    makes += 1
        
        print(f"\n  Fill type (approx):")
        print(f"    Takes (aggressive): {takes}")
        print(f"    Makes (passive): {makes}")
        
        # Show sample trades
        print(f"\n  Sample trades (first 10):")
        for t in sorted(our_tom_trades, key=lambda x: x['timestamp'])[:10]:
            ts = t['timestamp']
            side = 'BUY' if t.get('buyer') == 'SUBMISSION' else 'SELL'
            mid = mid_by_ts.get(ts, 0)
            bid = bid_by_ts.get(ts, 0)
            ask = ask_by_ts.get(ts, 0)
            print(f"    ts={ts} {side} {t['quantity']}@{t['price']} mid={mid:.1f} spread={ask-bid:.0f} cp={t.get('buyer','') if side=='SELL' else t.get('seller','')}")
    
    return our_tom_trades, mids, pnls

for sim_id in [44861, 45133]:
    try:
        analyze_log(sim_id)
    except Exception as e:
        print(f"Error analyzing {sim_id}: {e}")
        import traceback
        traceback.print_exc()
