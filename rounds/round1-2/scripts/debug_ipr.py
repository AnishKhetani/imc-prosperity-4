import pandas as pd
import numpy as np
# Quick diff check: run the OLD DynamicMMStrategy logic vs the new IPRStrategy on one day
# to see where they diverge

# Simulate manually for first 20 ticks of day 0
p = pd.read_csv('round_data/ROUND_2/prices_round_2_day_0.csv', sep=';')
ipr = p[p['product']=='INTARIAN_PEPPER_ROOT'].sort_values('timestamp').head(30)

# Old approach: limit=50, skew=0.1, take_edge=1, ema_window=5
# New approach: limit=80, inv_skew=0.1
# Compare fair values

ema_old = None
ema_new = None
alpha = 2.0 / 6  # EMA(5)

print(f"{'ts':>6} {'mid':>8} {'EMA_old':>8} {'EMA_new':>8} {'fair50':>7} {'fair80':>7} {'bb':>6} {'ba':>6} {'spread':>6}")
for _, row in ipr.iterrows():
    bb = row['bid_price_1']
    ba = row['ask_price_1']
    if pd.isna(bb) or pd.isna(ba):
        print(f"{int(row['timestamp']):>6} {'---':>8}")
        continue
    bb = int(bb)
    ba = int(ba)
    mid = (bb + ba) / 2.0
    bv = row['bid_volume_1']
    av = row['ask_volume_1']
    total = bv + av
    imb = (bv - av) / total if total > 0 else 0

    if ema_old is None:
        ema_old = mid
        ema_new = mid
    else:
        ema_old = alpha * mid + (1 - alpha) * ema_old
        ema_new = alpha * mid + (1 - alpha) * ema_new
    
    # Both use same EMA. The only difference is position evolution due to different limits
    # At position=0 they should be identical
    fair_50 = round(ema_old + imb * 0.5 - 0.1 * 0)  # position=0 initially
    fair_80 = round(ema_new + imb * 0.5 - 0.1 * 0)
    
    print(f"{int(row['timestamp']):>6} {mid:>8.1f} {ema_old:>8.2f} {ema_new:>8.2f} {fair_50:>7} {fair_80:>7} {bb:>6} {ba:>6} {ba-bb:>6}")
