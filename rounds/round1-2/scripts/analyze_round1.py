"""Round 1 data analysis - classify new products"""
import pandas as pd
import numpy as np

# Load all 3 days of prices
dfs = []
for fname in ['prices_round_1_day_-2.csv', 'prices_round_1_day_-1.csv', 'prices_round_1_day_0.csv']:
    df = pd.read_csv(f'round_data/ROUND1/{fname}', delimiter=';')
    dfs.append(df)
prices = pd.concat(dfs, ignore_index=True)

# Load trades
tdfs = []
for fname in ['trades_round_1_day_-2.csv', 'trades_round_1_day_-1.csv', 'trades_round_1_day_0.csv']:
    df = pd.read_csv(f'round_data/ROUND1/{fname}', delimiter=';')
    tdfs.append(df)
trades = pd.concat(tdfs, ignore_index=True)

print("Products:", prices['product'].unique())
print("Total price rows:", len(prices))
print("Total trade rows:", len(trades))
print()

for product in prices['product'].unique():
    pdf = prices[prices['product'] == product].copy()
    tdf = trades[trades['symbol'] == product] if 'symbol' in trades.columns else pd.DataFrame()
    
    print(f"{'='*60}")
    print(f"  {product}")
    print(f"{'='*60}")
    print(f"  Rows: {len(pdf)}")
    days = sorted(pdf['day'].unique())
    print(f"  Days: {days}")
    
    for d in days:
        daydf = pdf[pdf['day'] == d]
        print(f"  Day {d}: {len(daydf)} ticks, ts [{daydf['timestamp'].min()}, {daydf['timestamp'].max()}]")
    
    print(f"  Mid price range: [{pdf['mid_price'].min():.1f}, {pdf['mid_price'].max():.1f}]")
    print(f"  Mid price mean: {pdf['mid_price'].mean():.1f}")
    
    # Spread
    spread = pdf['ask_price_1'] - pdf['bid_price_1']
    valid_spread = spread.dropna()
    if len(valid_spread) > 0:
        print(f"  Spread: mean={valid_spread.mean():.2f}, min={valid_spread.min():.0f}, max={valid_spread.max():.0f}, median={valid_spread.median():.0f}")
        print(f"  Spread distribution:")
        for s in sorted(valid_spread.unique()):
            cnt = (valid_spread == s).sum()
            pct = 100 * cnt / len(valid_spread)
            if pct > 0.5:
                print(f"    spread={s:.0f}: {cnt} ({pct:.1f}%)")
    else:
        print("  Spread: N/A (missing bids or asks)")
    
    # Has bid/ask counts
    has_bid = pdf['bid_price_1'].notna().sum()
    has_ask = pdf['ask_price_1'].notna().sum()
    print(f"  Has bid: {has_bid}/{len(pdf)} ({100*has_bid/len(pdf):.1f}%)")
    print(f"  Has ask: {has_ask}/{len(pdf)} ({100*has_ask/len(pdf):.1f}%)")
    
    # Bid/ask volumes
    if has_bid > 0:
        bv = pdf['bid_volume_1'].dropna()
        print(f"  Bid vol L1: mean={bv.mean():.1f}, min={bv.min():.0f}, max={bv.max():.0f}")
    if has_ask > 0:
        av = pdf['ask_volume_1'].dropna()
        print(f"  Ask vol L1: mean={av.mean():.1f}, min={av.min():.0f}, max={av.max():.0f}")
    
    # L2/L3 presence
    has_l2_bid = pdf['bid_price_2'].notna().sum()
    has_l2_ask = pdf['ask_price_2'].notna().sum()
    has_l3_bid = pdf['bid_price_3'].notna().sum()
    has_l3_ask = pdf['ask_price_3'].notna().sum()
    print(f"  L2 bid: {has_l2_bid}, L2 ask: {has_l2_ask}, L3 bid: {has_l3_bid}, L3 ask: {has_l3_ask}")
    
    # Return autocorrelation per day and combined
    for d in days:
        daydf = pdf[pdf['day'] == d]
        mid = daydf['mid_price']
        mid_returns = mid.diff().dropna()
        if len(mid_returns) > 20:
            acf1 = mid_returns.autocorr(lag=1)
            acf2 = mid_returns.autocorr(lag=2)
            acf5 = mid_returns.autocorr(lag=5)
            print(f"  Day {d} ACF: lag1={acf1:.3f}, lag2={acf2:.3f}, lag5={acf5:.3f}")
    
    # Price trajectory per day
    for d in days:
        daydf = pdf[pdf['day'] == d]
        mid = daydf['mid_price']
        print(f"  Day {d}: start={mid.iloc[0]:.1f}, end={mid.iloc[-1]:.1f}, chg={mid.iloc[-1]-mid.iloc[0]:.1f}, std={mid.std():.2f}")
    
    # Trades analysis
    if len(tdf) > 0:
        print(f"\n  --- Trades ---")
        print(f"  Total trades: {len(tdf)}")
        if 'buyer' in tdf.columns:
            buyers = tdf['buyer'].dropna().unique()
            sellers = tdf['seller'].dropna().unique()
            print(f"  Buyers: {buyers[:10]}")
            print(f"  Sellers: {sellers[:10]}")
            
            # Check for named bots with fixed sizes
            for col in ['buyer', 'seller']:
                named = tdf[tdf[col].notna() & (tdf[col] != '')]
                if len(named) > 0:
                    for name in named[col].unique():
                        bot_trades = named[named[col] == name]
                        sizes = bot_trades['quantity'].unique()
                        count = len(bot_trades)
                        print(f"  Bot '{name}' as {col}: {count} trades, sizes={sorted(sizes)}, price range=[{bot_trades['price'].min()}, {bot_trades['price'].max()}]")
        
        # Trade size distribution
        print(f"  Trade sizes: {sorted(tdf['quantity'].unique())}")
        print(f"  Trade price range: [{tdf['price'].min()}, {tdf['price'].max()}]")
    
    print()

# Compare to tutorial data
print("\n" + "="*60)
print("COMPARISON WITH TUTORIAL DATA")
print("="*60)
print()

# Load tutorial data
for tut_fname in ['prices_round_0_day_-2.csv', 'prices_round_0_day_-1.csv']:
    import os
    for search_dir in ['round_data/ROUND1', 'tutorial-round/data']:
        candidate = os.path.join(search_dir, tut_fname)
        if os.path.exists(candidate):
            print(f"Found tutorial data at: {candidate}")
            break
