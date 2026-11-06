"""
Deep analysis of platform simulation data for generalizable edge signals.
NOT looking for dataset-specific patterns — looking for structural/microstructure patterns.
"""
import json, csv
from collections import defaultdict, Counter

with open(r'.\logs\42126\42126.log', 'r') as f:
    log_data = json.load(f)

with open(r'.\logs\42126\42126.json', 'r') as f:
    json_data = json.load(f)

trades = log_data['tradeHistory']

# Parse activitiesLog
lines = json_data['activitiesLog'].strip().split('\n')
header = lines[0].split(';')

ticks = []  # list of dicts per tick
for line in lines[1:]:
    parts = line.split(';')
    row = {}
    row['day'] = int(parts[0])
    row['timestamp'] = int(parts[1])
    row['product'] = parts[2]
    row['bid1'] = float(parts[3]) if parts[3] else None
    row['bid1_vol'] = int(parts[4]) if parts[4] else 0
    row['bid2'] = float(parts[5]) if parts[5] else None
    row['bid2_vol'] = int(parts[6]) if parts[6] else 0
    row['bid3'] = float(parts[7]) if parts[7] else None
    row['bid3_vol'] = int(parts[8]) if parts[8] else 0
    row['ask1'] = float(parts[9]) if parts[9] else None
    row['ask1_vol'] = int(parts[10]) if parts[10] else 0
    row['ask2'] = float(parts[11]) if parts[11] else None
    row['ask2_vol'] = int(parts[12]) if parts[12] else 0
    row['ask3'] = float(parts[13]) if parts[13] else None
    row['ask3_vol'] = int(parts[14]) if parts[14] else 0
    row['mid'] = float(parts[15]) if parts[15] else None
    row['pnl'] = float(parts[16]) if parts[16] else 0
    ticks.append(row)

em_ticks = [t for t in ticks if t['product'] == 'EMERALDS']
tom_ticks = [t for t in ticks if t['product'] == 'TOMATOES']

# ═══════════════════════════════════════════════════════
# 1. SPREAD REGIME ANALYSIS — when does spread tighten?
# ═══════════════════════════════════════════════════════
print('=' * 60)
print('  1. SPREAD REGIME ANALYSIS')
print('=' * 60)

for name, product_ticks in [('EMERALDS', em_ticks), ('TOMATOES', tom_ticks)]:
    spreads = []
    for t in product_ticks:
        if t['bid1'] and t['ask1']:
            s = t['ask1'] - t['bid1']
            spreads.append((t['timestamp'], s))
    
    if not spreads:
        continue
    
    print(f'\n{name}:')
    # When does spread tighten? 
    tight_ts = [ts for ts, s in spreads if s <= 8]
    normal_ts = [ts for ts, s in spreads if s > 8]
    print(f'  Tight spread (<=8): {len(tight_ts)} ticks ({len(tight_ts)/len(spreads)*100:.1f}%)')
    print(f'  Normal spread (>8): {len(normal_ts)} ticks')
    
    # Are tight spreads clustered in time?
    if tight_ts:
        print(f'  Tight spread timestamps (first 20): {tight_ts[:20]}')
        # Check if tight follows tight
        prev_spread = {}
        tight_after_tight = 0
        tight_after_normal = 0
        for i in range(1, len(spreads)):
            if spreads[i][1] <= 8:
                if spreads[i-1][1] <= 8:
                    tight_after_tight += 1
                else:
                    tight_after_normal += 1
        if tight_after_tight + tight_after_normal > 0:
            print(f'  Tight after tight: {tight_after_tight}, Tight after normal: {tight_after_normal}')
            print(f'  Spread regime persistence: {tight_after_tight/(tight_after_tight+tight_after_normal)*100:.1f}%')

# ═══════════════════════════════════════════════════════
# 2. ORDER BOOK IMBALANCE — does it predict price moves?
# ═══════════════════════════════════════════════════════
print('\n' + '=' * 60)
print('  2. ORDER BOOK IMBALANCE → PRICE PREDICTION')
print('=' * 60)

for name, product_ticks in [('EMERALDS', em_ticks), ('TOMATOES', tom_ticks)]:
    imbalance_returns = []
    for i in range(len(product_ticks) - 1):
        t = product_ticks[i]
        t_next = product_ticks[i + 1]
        if t['bid1_vol'] and t['ask1_vol'] and t['mid'] and t_next['mid']:
            total_vol = t['bid1_vol'] + t['ask1_vol']
            imb = (t['bid1_vol'] - t['ask1_vol']) / total_vol  # +1 = all bids, -1 = all asks
            ret = t_next['mid'] - t['mid']
            imbalance_returns.append((imb, ret))
    
    if not imbalance_returns:
        continue
    
    print(f'\n{name}:')
    # Bucket imbalance into quintiles
    sorted_ir = sorted(imbalance_returns, key=lambda x: x[0])
    n = len(sorted_ir)
    bucket_size = n // 5
    for i in range(5):
        start = i * bucket_size
        end = (i + 1) * bucket_size if i < 4 else n
        bucket = sorted_ir[start:end]
        avg_imb = sum(x[0] for x in bucket) / len(bucket)
        avg_ret = sum(x[1] for x in bucket) / len(bucket)
        print(f'  Imb quintile {i+1} (avg imb={avg_imb:+.3f}): avg next return = {avg_ret:+.4f}')

# ═══════════════════════════════════════════════════════
# 3. VOLUME-WEIGHTED MID vs SIMPLE MID
# ═══════════════════════════════════════════════════════
print('\n' + '=' * 60)
print('  3. VOLUME-WEIGHTED MID vs SIMPLE MID (predictive accuracy)')
print('=' * 60)

for name, product_ticks in [('TOMATOES', tom_ticks)]:
    simple_err = []
    wmid_err = []
    for i in range(len(product_ticks) - 1):
        t = product_ticks[i]
        t_next = product_ticks[i + 1]
        if t['bid1'] and t['ask1'] and t['bid1_vol'] and t['ask1_vol'] and t_next['mid']:
            simple_mid = (t['bid1'] + t['ask1']) / 2
            total_v = t['bid1_vol'] + t['ask1_vol']
            wmid = (t['bid1'] * t['ask1_vol'] + t['ask1'] * t['bid1_vol']) / total_v
            
            actual = t_next['mid']
            simple_err.append(abs(simple_mid - actual))
            wmid_err.append(abs(wmid - actual))
    
    if simple_err:
        print(f'\n{name}:')
        print(f'  Simple mid MAE: {sum(simple_err)/len(simple_err):.4f}')
        print(f'  Weighted mid MAE: {sum(wmid_err)/len(wmid_err):.4f}')
        wmid_wins = sum(1 for s, w in zip(simple_err, wmid_err) if w < s)
        print(f'  Weighted mid better: {wmid_wins}/{len(simple_err)} ({wmid_wins/len(simple_err)*100:.1f}%)')

# ═══════════════════════════════════════════════════════
# 4. DEPTH LEVELS — does L2/L3 depth signal upcoming moves?
# ═══════════════════════════════════════════════════════
print('\n' + '=' * 60)
print('  4. DEPTH PRESSURE (L1+L2+L3 total volume imbalance)')
print('=' * 60)

for name, product_ticks in [('EMERALDS', em_ticks), ('TOMATOES', tom_ticks)]:
    depth_returns = []
    for i in range(len(product_ticks) - 1):
        t = product_ticks[i]
        t_next = product_ticks[i + 1]
        if t['mid'] and t_next['mid']:
            bid_depth = t['bid1_vol'] + t['bid2_vol'] + t['bid3_vol']
            ask_depth = t['ask1_vol'] + t['ask2_vol'] + t['ask3_vol']
            total = bid_depth + ask_depth
            if total > 0:
                depth_imb = (bid_depth - ask_depth) / total
                ret = t_next['mid'] - t['mid']
                depth_returns.append((depth_imb, ret))
    
    if not depth_returns:
        continue
    
    print(f'\n{name}:')
    sorted_dr = sorted(depth_returns, key=lambda x: x[0])
    n = len(sorted_dr)
    bucket_size = n // 5
    for i in range(5):
        start = i * bucket_size
        end = (i + 1) * bucket_size if i < 4 else n
        bucket = sorted_dr[start:end]
        avg_imb = sum(x[0] for x in bucket) / len(bucket)
        avg_ret = sum(x[1] for x in bucket) / len(bucket)
        print(f'  Depth quintile {i+1} (avg imb={avg_imb:+.3f}): avg next return = {avg_ret:+.4f}')

# ═══════════════════════════════════════════════════════
# 5. MARKET TRADE FLOW — do other bots' trades predict moves?
# ═══════════════════════════════════════════════════════
print('\n' + '=' * 60)
print('  5. MARKET TRADE FLOW — do fills predict next-tick direction?')
print('=' * 60)

# Build a lookup of our fills per timestamp
our_buy_ts = set()
our_sell_ts = set()
for t in trades:
    if t['buyer'] == 'SUBMISSION':
        our_buy_ts.add(t['timestamp'])
    elif t['seller'] == 'SUBMISSION':
        our_sell_ts.add(t['timestamp'])

# For each product, look at ticks where we had a fill and check the next tick
for name, product_ticks in [('EMERALDS', em_ticks), ('TOMATOES', tom_ticks)]:
    buy_next = []
    sell_next = []
    no_fill_next = []
    for i in range(len(product_ticks) - 1):
        t = product_ticks[i]
        t_next = product_ticks[i + 1]
        if t['mid'] and t_next['mid']:
            ret = t_next['mid'] - t['mid']
            if t['timestamp'] in our_buy_ts:
                buy_next.append(ret)
            elif t['timestamp'] in our_sell_ts:
                sell_next.append(ret)
            else:
                no_fill_next.append(ret)
    
    print(f'\n{name}:')
    if buy_next:
        print(f'  After our BUY: avg next return = {sum(buy_next)/len(buy_next):+.4f} ({len(buy_next)} samples)')
    if sell_next:
        print(f'  After our SELL: avg next return = {sum(sell_next)/len(sell_next):+.4f} ({len(sell_next)} samples)')
    if no_fill_next:
        print(f'  After no fill: avg next return = {sum(no_fill_next)/len(no_fill_next):+.4f} ({len(no_fill_next)} samples)')

# ═══════════════════════════════════════════════════════
# 6. SPREAD TIGHTENING → fill opportunity
# ═══════════════════════════════════════════════════════
print('\n' + '=' * 60)
print('  6. TIGHT SPREAD = FILL OPPORTUNITY?')
print('=' * 60)

our_fill_ts = set()
for t in trades:
    if t['buyer'] == 'SUBMISSION' or t['seller'] == 'SUBMISSION':
        our_fill_ts.add((t['timestamp'], t['symbol']))

for name, product_ticks in [('EMERALDS', em_ticks), ('TOMATOES', tom_ticks)]:
    tight_fills = 0
    tight_total = 0
    wide_fills = 0
    wide_total = 0
    for t in product_ticks:
        if t['bid1'] and t['ask1']:
            s = t['ask1'] - t['bid1']
            is_fill = (t['timestamp'], name) in our_fill_ts
            if s <= 8:
                tight_total += 1
                if is_fill: tight_fills += 1
            else:
                wide_total += 1
                if is_fill: wide_fills += 1
    
    print(f'\n{name}:')
    if tight_total > 0:
        print(f'  Tight spread (<=8): filled {tight_fills}/{tight_total} ({tight_fills/tight_total*100:.1f}%)')
    if wide_total > 0:
        print(f'  Wide spread (>8): filled {wide_fills}/{wide_total} ({wide_fills/wide_total*100:.1f}%)')

# ═══════════════════════════════════════════════════════
# 7. BOT BEHAVIOR — are bot quotes predictable/patterned?
# ═══════════════════════════════════════════════════════
print('\n' + '=' * 60)
print('  7. BOT QUOTE LEVEL ANALYSIS')
print('=' * 60)

for name, product_ticks in [('EMERALDS', em_ticks), ('TOMATOES', tom_ticks)]:
    bid1_levels = Counter()
    ask1_levels = Counter()
    bid1_vol_dist = Counter()
    ask1_vol_dist = Counter()
    
    for t in product_ticks:
        if t['bid1']: bid1_levels[int(t['bid1'])] += 1
        if t['ask1']: ask1_levels[int(t['ask1'])] += 1
        bid1_vol_dist[t['bid1_vol']] += 1
        ask1_vol_dist[t['ask1_vol']] += 1
    
    print(f'\n{name}:')
    print(f'  Top bid levels: {bid1_levels.most_common(5)}')
    print(f'  Top ask levels: {ask1_levels.most_common(5)}')
    print(f'  Top bid volumes: {bid1_vol_dist.most_common(5)}')
    print(f'  Top ask volumes: {ask1_vol_dist.most_common(5)}')
    
    # Check if volume is symmetric (same on bid and ask)
    sym_count = 0
    for t in product_ticks:
        if t['bid1_vol'] == t['ask1_vol']:
            sym_count += 1
    print(f'  Symmetric L1 volume: {sym_count}/{len(product_ticks)} ({sym_count/len(product_ticks)*100:.1f}%)')

# ═══════════════════════════════════════════════════════
# 8. CROSS-PRODUCT CORRELATION
# ═══════════════════════════════════════════════════════
print('\n' + '=' * 60)
print('  8. CROSS-PRODUCT CORRELATION')
print('=' * 60)

em_returns = {}
tom_returns = {}
for i in range(1, len(em_ticks)):
    if em_ticks[i]['mid'] and em_ticks[i-1]['mid']:
        em_returns[em_ticks[i]['timestamp']] = em_ticks[i]['mid'] - em_ticks[i-1]['mid']
for i in range(1, len(tom_ticks)):
    if tom_ticks[i]['mid'] and tom_ticks[i-1]['mid']:
        tom_returns[tom_ticks[i]['timestamp']] = tom_ticks[i]['mid'] - tom_ticks[i-1]['mid']

common_ts = sorted(set(em_returns.keys()) & set(tom_returns.keys()))
if common_ts:
    er = [em_returns[ts] for ts in common_ts]
    tr = [tom_returns[ts] for ts in common_ts]
    n = len(er)
    mean_e = sum(er) / n
    mean_t = sum(tr) / n
    cov = sum((er[i] - mean_e) * (tr[i] - mean_t) for i in range(n)) / n
    std_e = (sum((x - mean_e)**2 for x in er) / n) ** 0.5
    std_t = (sum((x - mean_t)**2 for x in tr) / n) ** 0.5
    corr = cov / (std_e * std_t) if std_e > 0 and std_t > 0 else 0
    print(f'  Contemporaneous return correlation: {corr:.4f}')
    
    # Lead-lag: does EMERALDS predict TOMATOES or vice versa?
    common_sorted = common_ts
    if len(common_sorted) > 2:
        # EM(t) → TOM(t+1)?
        em_lead = [em_returns.get(common_sorted[i], 0) for i in range(len(common_sorted)-1)]
        tom_lag = [tom_returns.get(common_sorted[i+1], 0) for i in range(len(common_sorted)-1)]
        n2 = len(em_lead)
        mean_el = sum(em_lead)/n2
        mean_tl = sum(tom_lag)/n2
        cov2 = sum((em_lead[i]-mean_el)*(tom_lag[i]-mean_tl) for i in range(n2))/n2
        std_el = (sum((x-mean_el)**2 for x in em_lead)/n2)**0.5
        std_tl = (sum((x-mean_tl)**2 for x in tom_lag)/n2)**0.5
        corr2 = cov2/(std_el*std_tl) if std_el>0 and std_tl>0 else 0
        print(f'  Lead: EM(t) → TOM(t+1) correlation: {corr2:.4f}')
        
        # TOM(t) → EM(t+1)?
        tom_lead = [tom_returns.get(common_sorted[i], 0) for i in range(len(common_sorted)-1)]
        em_lag = [em_returns.get(common_sorted[i+1], 0) for i in range(len(common_sorted)-1)]
        mean_tl2 = sum(tom_lead)/n2
        mean_el2 = sum(em_lag)/n2
        cov3 = sum((tom_lead[i]-mean_tl2)*(em_lag[i]-mean_el2) for i in range(n2))/n2
        std_tl2 = (sum((x-mean_tl2)**2 for x in tom_lead)/n2)**0.5
        std_el2 = (sum((x-mean_el2)**2 for x in em_lag)/n2)**0.5
        corr3 = cov3/(std_tl2*std_el2) if std_tl2>0 and std_el2>0 else 0
        print(f'  Lead: TOM(t) → EM(t+1) correlation: {corr3:.4f}')
