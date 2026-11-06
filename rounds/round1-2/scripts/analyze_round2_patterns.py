"""Analyze Round 2 data for exploitable patterns."""
import csv

def analyze_prices(day):
    fname = f"round_data/ROUND_2/prices_round_2_day_{day}.csv"
    aco_data = []
    ipr_data = []
    
    with open(fname) as f:
        reader = csv.DictReader(f, delimiter=';')
        for row in reader:
            ts = int(row['timestamp'])
            product = row['product']
            mid = float(row['mid_price'])
            bp1 = int(float(row['bid_price_1'])) if row['bid_price_1'] else None
            bv1 = int(float(row['bid_volume_1'])) if row['bid_volume_1'] else None
            ap1 = int(float(row['ask_price_1'])) if row['ask_price_1'] else None
            av1 = int(float(row['ask_volume_1'])) if row['ask_volume_1'] else None
            bp2 = int(float(row['bid_price_2'])) if row['bid_price_2'] else None
            bv2 = int(float(row['bid_volume_2'])) if row['bid_volume_2'] else None
            ap2 = int(float(row['ask_price_2'])) if row['ask_price_2'] else None
            av2 = int(float(row['ask_volume_2'])) if row['ask_volume_2'] else None
            
            entry = {
                'ts': ts, 'mid': mid, 
                'bp1': bp1, 'bv1': bv1, 'ap1': ap1, 'av1': av1,
                'bp2': bp2, 'bv2': bv2, 'ap2': ap2, 'av2': av2,
                'spread': ap1 - bp1 if ap1 and bp1 else None,
            }
            if product == 'ASH_COATED_OSMIUM':
                aco_data.append(entry)
            else:
                ipr_data.append(entry)
    
    return aco_data, ipr_data

def analyze_trades(day):
    fname = f"round_data/ROUND_2/trades_round_2_day_{day}.csv"
    aco_trades = []
    ipr_trades = []
    
    with open(fname) as f:
        reader = csv.DictReader(f, delimiter=';')
        for row in reader:
            ts = int(row['timestamp'])
            symbol = row['symbol']
            price = float(row['price'])
            qty = int(float(row['quantity']))
            
            entry = {'ts': ts, 'price': price, 'qty': qty}
            if symbol == 'ASH_COATED_OSMIUM':
                aco_trades.append(entry)
            else:
                ipr_trades.append(entry)
    
    return aco_trades, ipr_trades

print("=== ANALYZING DAY 0 ===")
aco_prices, ipr_prices = analyze_prices(0)
aco_trades, ipr_trades = analyze_trades(0)

# ACO analysis
print(f"\nACO: {len(aco_prices)} price snapshots, {len(aco_trades)} trades")
spreads = [d['spread'] for d in aco_prices if d['spread']]
from collections import Counter
spread_counts = Counter(spreads)
print(f"ACO spread distribution: {sorted(spread_counts.items())}")

# ACO: check if L1 volumes predict next tick direction
correct = 0
total = 0
for i in range(len(aco_prices)-1):
    d = aco_prices[i]
    d_next = aco_prices[i+1]
    if d['bv1'] and d['av1'] and d_next['mid']:
        imb = (d['bv1'] - d['av1']) / (d['bv1'] + d['av1'])
        mid_change = d_next['mid'] - d['mid']
        if imb > 0 and mid_change > 0:
            correct += 1
        elif imb < 0 and mid_change < 0:
            correct += 1
        if mid_change != 0:
            total += 1
if total > 0:
    print(f"ACO L1 imb predicts direction: {correct}/{total} = {correct/total:.3f}")

# ACO: check if L2 volumes add prediction value
correct_l2 = 0
total_l2 = 0
for i in range(len(aco_prices)-1):
    d = aco_prices[i]
    d_next = aco_prices[i+1]
    if d['bv1'] and d['av1'] and d_next['mid']:
        total_bv = d['bv1'] + (d['bv2'] or 0)
        total_av = d['av1'] + (d['av2'] or 0)
        imb = (total_bv - total_av) / (total_bv + total_av)
        mid_change = d_next['mid'] - d['mid']
        if imb > 0 and mid_change > 0:
            correct_l2 += 1
        elif imb < 0 and mid_change < 0:
            correct_l2 += 1
        if mid_change != 0:
            total_l2 += 1
if total_l2 > 0:
    print(f"ACO L2 imb predicts direction: {correct_l2}/{total_l2} = {correct_l2/total_l2:.3f}")

# ACO: check trade flow predicts direction
# Build trade flow per timestamp
trade_flow_by_ts = {}
for t in aco_trades:
    ts = t['ts']
    if ts not in trade_flow_by_ts:
        trade_flow_by_ts[ts] = 0
    trade_flow_by_ts[ts] += t['qty']  # total volume (can't determine direction from data)

# Check total trades per tick
trade_counts = [len([t for t in aco_trades if t['ts'] == d['ts']]) for d in aco_prices[:100]]
print(f"ACO trades per tick (first 100): avg={sum(trade_counts)/len(trade_counts):.1f}, max={max(trade_counts)}")

# IPR analysis
print(f"\nIPR: {len(ipr_prices)} price snapshots, {len(ipr_trades)} trades")
ipr_spreads = [d['spread'] for d in ipr_prices if d['spread']]
ipr_spread_counts = Counter(ipr_spreads)
print(f"IPR spread distribution: {sorted(ipr_spread_counts.items())}")

# IPR: avg L1 bid vs ask volumes
ipr_bv1s = [d['bv1'] for d in ipr_prices if d['bv1']]
ipr_av1s = [d['av1'] for d in ipr_prices if d['av1']]
print(f"IPR avg L1 bid vol: {sum(ipr_bv1s)/len(ipr_bv1s):.1f}, avg L1 ask vol: {sum(ipr_av1s)/len(ipr_av1s):.1f}")

# IPR: drift rate
if len(ipr_prices) > 1:
    first_mid = ipr_prices[0]['mid']
    last_mid = ipr_prices[-1]['mid']
    n_ticks = len(ipr_prices) - 1
    print(f"IPR drift: {first_mid} -> {last_mid}, change={last_mid-first_mid:.1f}, per tick={((last_mid-first_mid)/n_ticks):.4f}")

# IPR: check if volume imbalance predicts direction
correct_ipr = 0
total_ipr = 0
for i in range(len(ipr_prices)-1):
    d = ipr_prices[i]
    d_next = ipr_prices[i+1]
    if d['bv1'] and d['av1'] and d_next['mid']:
        imb = (d['bv1'] - d['av1']) / (d['bv1'] + d['av1'])
        mid_change = d_next['mid'] - d['mid']
        if imb > 0 and mid_change > 0:
            correct_ipr += 1
        elif imb < 0 and mid_change < 0:
            correct_ipr += 1
        if mid_change != 0:
            total_ipr += 1
if total_ipr > 0:
    print(f"IPR L1 imb predicts direction: {correct_ipr}/{total_ipr} = {correct_ipr/total_ipr:.3f}")

# IPR trade analysis
ipr_trade_counts = [len([t for t in ipr_trades if t['ts'] == d['ts']]) for d in ipr_prices[:100]]
print(f"IPR trades per tick (first 100): avg={sum(ipr_trade_counts)/len(ipr_trade_counts):.1f}, max={max(ipr_trade_counts)}")

# IPR: trade prices relative to mid
if ipr_trades:
    # Match trades to closest price snapshot
    above_mid = 0
    below_mid = 0
    at_mid = 0
    for t in ipr_trades[:500]:
        # Find closest price
        closest = min(ipr_prices, key=lambda d: abs(d['ts'] - t['ts']))
        if t['price'] > closest['mid']:
            above_mid += 1
        elif t['price'] < closest['mid']:
            below_mid += 1
        else:
            at_mid += 1
    print(f"IPR trades (first 500): above_mid={above_mid}, below_mid={below_mid}, at_mid={at_mid}")

# ACO: serial autocorrelation of mid changes
mid_changes = []
for i in range(len(aco_prices)-1):
    mc = aco_prices[i+1]['mid'] - aco_prices[i]['mid']
    mid_changes.append(mc)

if len(mid_changes) > 2:
    n = len(mid_changes)
    mean = sum(mid_changes) / n
    var = sum((x - mean)**2 for x in mid_changes) / n
    if var > 0:
        cov1 = sum((mid_changes[i] - mean) * (mid_changes[i+1] - mean) for i in range(n-1)) / (n-1)
        ac1 = cov1 / var
        print(f"\nACO mid-change AC(1): {ac1:.3f}")

# IPR: serial autocorrelation
ipr_mid_changes = []
for i in range(len(ipr_prices)-1):
    mc = ipr_prices[i+1]['mid'] - ipr_prices[i]['mid']
    ipr_mid_changes.append(mc)

if len(ipr_mid_changes) > 2:
    n = len(ipr_mid_changes)
    mean = sum(ipr_mid_changes) / n
    var = sum((x - mean)**2 for x in ipr_mid_changes) / n
    if var > 0:
        cov1 = sum((ipr_mid_changes[i] - mean) * (ipr_mid_changes[i+1] - mean) for i in range(n-1)) / (n-1)
        ac1 = cov1 / var
        print(f"IPR mid-change AC(1): {ac1:.3f}")

# Check for ACO price patterns around trades
print("\n=== ACO TRADE ANALYSIS ===")
# When trades happen at certain prices, what happens next?
trade_tss = set(t['ts'] for t in aco_trades)
price_by_ts = {d['ts']: d for d in aco_prices}
big_moves = [(d['ts'], aco_prices[i+1]['mid'] - d['mid']) for i, d in enumerate(aco_prices[:-1]) if abs(aco_prices[i+1]['mid'] - d['mid']) >= 4]
print(f"ACO big moves (>=4): {len(big_moves)} out of {len(aco_prices)-1} ticks")
if big_moves:
    print(f"  Example big moves: {big_moves[:10]}")
