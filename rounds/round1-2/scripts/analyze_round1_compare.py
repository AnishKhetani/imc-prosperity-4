"""Round 1 comparison analysis"""
import pandas as pd
import numpy as np

dfs = []
for fname in ['prices_round_1_day_-2.csv', 'prices_round_1_day_-1.csv', 'prices_round_1_day_0.csv']:
    df = pd.read_csv(f'round_data/ROUND1/{fname}', delimiter=';')
    dfs.append(df)
prices = pd.concat(dfs, ignore_index=True)

print('=== ASH_COATED_OSMIUM vs EMERALDS ===')
osm = prices[prices['product'] == 'ASH_COATED_OSMIUM']
osm_valid = osm[osm['bid_price_1'].notna() & osm['ask_price_1'].notna()]
spread_osm = osm_valid['ask_price_1'] - osm_valid['bid_price_1']
mid_osm = (osm_valid['bid_price_1'] + osm_valid['ask_price_1']) / 2

print(f'Fair value stability: mean={mid_osm.mean():.2f}, std={mid_osm.std():.2f}')
dev = (mid_osm - 10000).abs().max()
print(f'Max deviation from 10000: {dev:.1f}')
mode_osm = spread_osm.mode().values[0]
print(f'Spread: mean={spread_osm.mean():.2f}, mode={mode_osm}')

for w in [5, 6, 7, 8]:
    threshold = w * 2
    safe = (spread_osm >= threshold).sum()
    pct = 100 * safe / len(spread_osm)
    print(f'  WIDTH={w} safe (spread>={threshold}): {safe}/{len(spread_osm)} = {pct:.1f}%')
print()

# Narrow spread analysis
narrow = osm_valid[spread_osm < 14]
narrow_spread = narrow['ask_price_1'] - narrow['bid_price_1']
print(f'Narrow spread (<14) ticks: {len(narrow)} ({100*len(narrow)/len(osm_valid):.1f}%)')
ns_dist = dict(narrow_spread.value_counts().sort_index())
print(f'Narrow spread distribution: {ns_dist}')
print()

print('=== INTARIAN_PEPPER_ROOT vs TOMATOES ===')
ipr = prices[prices['product'] == 'INTARIAN_PEPPER_ROOT']
ipr_valid = ipr[ipr['bid_price_1'].notna() & ipr['ask_price_1'].notna()]
spread_ipr = ipr_valid['ask_price_1'] - ipr_valid['bid_price_1']
mid_ipr = (ipr_valid['bid_price_1'] + ipr_valid['ask_price_1']) / 2

print(f'Price range: {mid_ipr.min():.1f} to {mid_ipr.max():.1f}')
mode_ipr = spread_ipr.mode().values[0]
print(f'Spread: mean={spread_ipr.mean():.2f}, mode={mode_ipr}')

for w in [4, 5, 6]:
    threshold = w * 2
    safe = (spread_ipr >= threshold).sum()
    pct = 100 * safe / len(spread_ipr)
    print(f'  WIDTH={w} safe (spread>={threshold}): {safe}/{len(spread_ipr)} = {pct:.1f}%')
print()

# Daily drift for INTARIAN_PEPPER_ROOT
print('INTARIAN_PEPPER_ROOT daily drift:')
for d in sorted(ipr['day'].unique()):
    daydf = ipr[ipr['day'] == d]
    valid = daydf[daydf['mid_price'] > 0]
    start_mid = valid['mid_price'].iloc[0]
    end_mid = valid['mid_price'].iloc[-1]
    drift = end_mid - start_mid
    ticks = len(valid)
    print(f'  Day {d}: start={start_mid:.1f}, end={end_mid:.1f}, drift={drift:.1f}, drift/tick={drift/ticks:.4f}')
print()

# Check if EMERALDS/TOMATOES appear anywhere
print('=== All products in Round 1 ===')
print(prices['product'].unique())

# Key question: are IPR bid prices at integer levels? 
print()
print('=== INTARIAN_PEPPER_ROOT bid price modulo patterns ===')
bids = ipr_valid['bid_price_1']
asks = ipr_valid['ask_price_1']
print(f'Bid prices are integers: {(bids == bids.astype(int)).all()}')
print(f'Ask prices are integers: {(asks == asks.astype(int)).all()}')

# Check ASH_COATED_OSMIUM
print('=== ASH_COATED_OSMIUM price patterns ===')
osm_bids = osm_valid['bid_price_1']
osm_asks = osm_valid['ask_price_1']
print(f'Bid prices are integers: {(osm_bids == osm_bids.astype(int)).all()}')
print(f'Ask prices are integers: {(osm_asks == osm_asks.astype(int)).all()}')
