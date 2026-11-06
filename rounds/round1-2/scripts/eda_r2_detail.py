import pandas as pd
import numpy as np

# Check the mid=0 ticks
for d in [-1, 0, 1]:
    p = pd.read_csv(f'round_data/ROUND_2/prices_round_2_day_{d}.csv', sep=';')
    zeros = p[p['mid_price'] == 0]
    print(f'Day {d}: {len(zeros)} zero-mid ticks out of {len(p)}')
    if len(zeros) > 0:
        print(zeros[['timestamp','product','bid_price_1','ask_price_1','mid_price']].head(3))

# Check ACO FV more carefully - exclude 0 mids
print()
for d in [-1, 0, 1]:
    p = pd.read_csv(f'round_data/ROUND_2/prices_round_2_day_{d}.csv', sep=';')
    aco = p[(p['product']=='ASH_COATED_OSMIUM') & (p['mid_price'] > 0)]
    med = aco['mid_price'].median()
    mn = aco['mid_price'].mean()
    lo = aco['mid_price'].min()
    hi = aco['mid_price'].max()
    print(f'Day {d} ACO: median={med:.1f}, mean={mn:.2f}, range={lo:.0f}-{hi:.0f}')
    first100 = aco['mid_price'].iloc[:100].mean()
    last100 = aco['mid_price'].iloc[-100:].mean()
    print(f'  First 100 avg: {first100:.1f}, Last 100 avg: {last100:.1f}, drift: {last100-first100:.1f}')

# Check IPR drift rate per tick
print()
for d in [-1, 0, 1]:
    p = pd.read_csv(f'round_data/ROUND_2/prices_round_2_day_{d}.csv', sep=';')
    ipr = p[(p['product']=='INTARIAN_PEPPER_ROOT') & (p['mid_price'] > 0)].sort_values('timestamp')
    if len(ipr) > 1:
        total_drift = ipr['mid_price'].iloc[-1] - ipr['mid_price'].iloc[0]
        ticks = len(ipr)
        print(f'Day {d} IPR: ticks={ticks}, total_drift={total_drift:.1f}, drift/tick={total_drift/ticks:.4f}')

# Spread distribution
print()
for d in [-1, 0, 1]:
    p = pd.read_csv(f'round_data/ROUND_2/prices_round_2_day_{d}.csv', sep=';')
    for prod in ['ASH_COATED_OSMIUM', 'INTARIAN_PEPPER_ROOT']:
        pp = p[(p['product']==prod) & (p['mid_price'] > 0)]
        sp = pp['ask_price_1'] - pp['bid_price_1']
        narrow = 100*(sp<=6).mean()
        print(f'Day {d} {prod[:3]}: spread mean={sp.mean():.1f}, min={sp.min()}, max={sp.max()}, narrow(<=6)={narrow:.1f}%')

# Check how many ticks have spread < width candidates
print()
print("--- Spread histogram for make width sizing ---")
for prod in ['ASH_COATED_OSMIUM', 'INTARIAN_PEPPER_ROOT']:
    all_sp = []
    for d in [-1, 0, 1]:
        p = pd.read_csv(f'round_data/ROUND_2/prices_round_2_day_{d}.csv', sep=';')
        pp = p[(p['product']==prod) & (p['mid_price'] > 0)]
        sp = pp['ask_price_1'] - pp['bid_price_1']
        all_sp.extend(sp.tolist())
    all_sp = np.array(all_sp)
    print(f'{prod[:3]}:')
    for w in [2, 3, 4, 5, 6, 7, 8]:
        # Can quote at fair+-w if half-spread > w (i.e. spread > 2w)
        pct = 100*(all_sp > 2*w).mean()
        print(f'  width={w}: {pct:.1f}% of ticks have spread>{2*w}')
