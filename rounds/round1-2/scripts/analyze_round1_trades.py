"""Round 1 trades analysis - check for informed traders"""
import pandas as pd
import numpy as np

# Load trades
dfs = []
for fname in ['trades_round_1_day_-2.csv', 'trades_round_1_day_-1.csv', 'trades_round_1_day_0.csv']:
    df = pd.read_csv(f'round_data/ROUND1/{fname}', delimiter=';')
    dfs.append(df)
trades = pd.concat(dfs, ignore_index=True)

print('Trade columns:', trades.columns.tolist())
print('Trade dtypes:')
print(trades.dtypes)
print()
print('First 20 trades:')
print(trades.head(20).to_string())
print()

# Check buyer/seller names
for col in ['buyer', 'seller']:
    if col in trades.columns:
        vals = trades[col].dropna().unique()
        print(f'{col} unique values: {vals[:20]}')
        val_counts = trades[col].value_counts()
        print(f'{col} value counts:')
        print(val_counts.head(20))
        print()

# Check trade patterns per product
for product in trades['symbol'].unique():
    tdf = trades[trades['symbol'] == product]
    qty_dist = dict(tdf['quantity'].value_counts().sort_index())
    print(f'=== {product} trades ===')
    print(f'  Count: {len(tdf)}')
    print(f'  Size distribution: {qty_dist}')
    pmin = tdf['price'].min()
    pmax = tdf['price'].max()
    print(f'  Price range: [{pmin}, {pmax}]')

    # Per-day breakdown
    for d in sorted(tdf['day'].unique()):
        dtdf = tdf[tdf['day'] == d]
        dpmin = dtdf['price'].min()
        dpmax = dtdf['price'].max()
        print(f'  Day {d}: {len(dtdf)} trades, price=[{dpmin}, {dpmax}]')
    print()

# Load prices to compare trade prices vs mid
dfs_p = []
for fname in ['prices_round_1_day_-2.csv', 'prices_round_1_day_-1.csv', 'prices_round_1_day_0.csv']:
    df = pd.read_csv(f'round_data/ROUND1/{fname}', delimiter=';')
    dfs_p.append(df)
prices = pd.concat(dfs_p, ignore_index=True)

# For INTARIAN_PEPPER_ROOT: check if trades happen near extremes
print("=== INTARIAN_PEPPER_ROOT trade timing ===")
ipr_trades = trades[trades['symbol'] == 'INTARIAN_PEPPER_ROOT']
ipr_prices = prices[prices['product'] == 'INTARIAN_PEPPER_ROOT']
for d in sorted(ipr_trades['day'].unique()):
    dtdf = ipr_trades[ipr_trades['day'] == d]
    dpdf = ipr_prices[ipr_prices['day'] == d]
    # Show trades in first/last 100 ticks
    early = dtdf[dtdf['timestamp'] < 10000]
    late = dtdf[dtdf['timestamp'] > 990000]
    mid_start = dpdf[dpdf['mid_price'] > 0]['mid_price'].iloc[0]
    mid_end = dpdf[dpdf['mid_price'] > 0]['mid_price'].iloc[-1]
    print(f"  Day {d}: {len(dtdf)} trades, early(<10k)={len(early)}, late(>990k)={len(late)}")
    print(f"    Price at start: {mid_start:.1f}, at end: {mid_end:.1f}")
    print(f"    Trade volume: buy_size avg={dtdf['quantity'].mean():.1f}")
print()

# Check for any patterns in trade timing
print("=== Trade timing distribution ===")
for product in trades['symbol'].unique():
    tdf = trades[trades['symbol'] == product]
    print(f"\n{product}:")
    # Divide day into 10 buckets
    for d in sorted(tdf['day'].unique()):
        dtdf = tdf[tdf['day'] == d]
        bins = pd.cut(dtdf['timestamp'], bins=10)
        counts = bins.value_counts().sort_index()
        print(f"  Day {d} trade count by period:")
        for interval, cnt in counts.items():
            print(f"    {interval}: {cnt}")
