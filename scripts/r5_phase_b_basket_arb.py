"""SNACKPACK exhaustive subset & 3-day stability check; PEBBLES day-by-day basket exact check."""
import os, numpy as np, pandas as pd
from itertools import combinations

ROOT = os.path.join("round_data", "ROUND_5")
P = pd.concat([pd.read_csv(os.path.join(ROOT, f"prices_round_5_day_{d}.csv"), sep=";")
               for d in [2, 3, 4]], ignore_index=True)
piv = P.pivot_table(index=["day", "timestamp"], columns="product",
                    values="mid_price", aggfunc="first").sort_index()

SP = ["SNACKPACK_CHOCOLATE", "SNACKPACK_PISTACHIO", "SNACKPACK_RASPBERRY",
      "SNACKPACK_STRAWBERRY", "SNACKPACK_VANILLA"]
PEB = ["PEBBLES_XS", "PEBBLES_S", "PEBBLES_M", "PEBBLES_L", "PEBBLES_XL"]

def show(label, s):
    s = np.asarray(s, dtype=float); s = s[~np.isnan(s)]
    print(f"  {label:60s}  mean={s.mean():12.3f}  std={s.std():9.3f}  range={s.max()-s.min():9.2f}  p99-p1={np.percentile(s,99)-np.percentile(s,1):.2f}")

print("=== SNACKPACK: subset sums (k=2..5) ===")
mat = piv[SP].dropna().values
for k in range(2, 6):
    for combo in combinations(range(5), k):
        s = mat[:, list(combo)].sum(axis=1)
        names = "+".join([SP[c].split("_")[1] for c in combo])
        print(f"  k={k}  {names:35s}  mean={s.mean():9.2f}  std={s.std():7.2f}  range={s.max()-s.min():.1f}")

print("\n=== SNACKPACK: subset sums with mixed signs (k=3, +/-) ===")
# look for x+y-z=const
print("  trying (a+b-c) for all triples:")
for combo in combinations(range(5), 3):
    for sign_set in [(1,1,-1),(1,-1,1),(-1,1,1)]:
        s = sum(sg * mat[:, c] for sg, c in zip(sign_set, combo))
        names = "  ".join([("+" if sg>0 else "-") + SP[c].split("_")[1] for sg, c in zip(sign_set, combo)])
        if s.std() < 100:
            print(f"  {names:55s}  mean={s.mean():+9.2f}  std={s.std():7.2f}")

print("\n=== SNACKPACK: per-day basket constants? ===")
for d in [2, 3, 4]:
    sub = piv.xs(d, level="day")[SP].dropna()
    s = sub.sum(axis=1).values
    print(f"  day {d}  ALL_5 sum  mean={s.mean():.2f} std={s.std():.2f}  range={s.max()-s.min():.2f}")
    s = (sub["SNACKPACK_CHOCOLATE"] + sub["SNACKPACK_VANILLA"]).values
    print(f"  day {d}  CHOC+VAN   mean={s.mean():.2f} std={s.std():.2f}  range={s.max()-s.min():.2f}")
    s = (sub["SNACKPACK_PISTACHIO"] + sub["SNACKPACK_RASPBERRY"]).values
    print(f"  day {d}  PIST+RASP  mean={s.mean():.2f} std={s.std():.2f}  range={s.max()-s.min():.2f}")
    s = (sub["SNACKPACK_RASPBERRY"] + sub["SNACKPACK_STRAWBERRY"]).values
    print(f"  day {d}  RASP+STRA  mean={s.mean():.2f} std={s.std():.2f}  range={s.max()-s.min():.2f}")

print("\n=== PEBBLES: per-day exact basket sum ===")
mat2 = piv[PEB].dropna()
for d in [2, 3, 4]:
    sub = piv.xs(d, level="day")[PEB].dropna()
    s = sub.sum(axis=1).values
    print(f"  day {d}  PEBBLES sum_5  mean={s.mean():.4f}  std={s.std():.4f}  range={s.max()-s.min():.2f}  N={len(s)}")
    # how many ticks have sum != 50000?
    near = (np.abs(s - 50000) <= 2).mean()
    big = (np.abs(s - 50000) > 5).mean()
    print(f"            within ±2: {near*100:.2f}%   beyond ±5: {big*100:.4f}%")
    # max deviation
    dev = s - 50000
    print(f"            dev: mean={dev.mean():+.4f}  p1={np.percentile(dev,1):+.2f}  p99={np.percentile(dev,99):+.2f}  abs_max={np.abs(dev).max():.2f}")

print("\n=== Sample 5 ticks where PEBBLES sum deviates most from 50000 ===")
mat2 = piv[PEB].dropna().copy()
mat2["sum5"] = mat2.sum(axis=1)
mat2["dev"] = mat2["sum5"] - 50000
mat2 = mat2.assign(absdev=mat2["dev"].abs()).sort_values("absdev", ascending=False).head(5)
print(mat2.to_string())

print("\n=== Top 25 PEBBLES dislocations and corresponding bid/ask spreads ===")
# verify: are dislocations real (i.e., crossing tradable bid/ask in the basket sense)?
print("  Computing tradable basket bid/ask: best bids of each leg sum vs best asks.")
# Need bid_price_1 and ask_price_1 per product
prices_long = P[["day","timestamp","product","bid_price_1","ask_price_1"]]
piv_b = prices_long.pivot_table(index=["day","timestamp"], columns="product",
                                 values="bid_price_1", aggfunc="first").sort_index()
piv_a = prices_long.pivot_table(index=["day","timestamp"], columns="product",
                                 values="ask_price_1", aggfunc="first").sort_index()
basket_bid = piv_b[PEB].sum(axis=1)   # if you SELL all 5, you collect this
basket_ask = piv_a[PEB].sum(axis=1)   # if you BUY all 5, you pay this
# Arb: if basket_bid > 50000 → sell all 5 for guaranteed profit (bid_sum - 50000)
# Arb: if basket_ask < 50000 → buy all 5 for guaranteed profit (50000 - ask_sum)
sell_arb = basket_bid - 50000
buy_arb = 50000 - basket_ask
sell_pos = sell_arb[sell_arb > 0]
buy_pos = buy_arb[buy_arb > 0]
print(f"  ticks with positive sell-basket arb (basket_bid > 50000): {len(sell_pos)}/{len(basket_bid)} "
      f"  mean_edge={sell_pos.mean() if len(sell_pos)>0 else 0:.2f}  max={sell_pos.max() if len(sell_pos)>0 else 0:.2f}")
print(f"  ticks with positive buy-basket arb (basket_ask < 50000): {len(buy_pos)}/{len(basket_ask)} "
      f"  mean_edge={buy_pos.mean() if len(buy_pos)>0 else 0:.2f}  max={buy_pos.max() if len(buy_pos)>0 else 0:.2f}")
# distribution of total edge available
both = pd.DataFrame({"sell_edge": sell_arb.clip(lower=0), "buy_edge": buy_arb.clip(lower=0)})
print(f"  total positive edge ticks (either side): {((sell_arb>0)|(buy_arb>0)).sum()}")
print(f"  pct of ticks with arb available: {((sell_arb>0)|(buy_arb>0)).mean()*100:.2f}%")
print(f"  total integrated edge if traded once per opportunity (sum of positive edges):")
print(f"    sell side: {sell_pos.sum():.0f}   buy side: {buy_pos.sum():.0f}")

# Same arb on SNACKPACK CHOC+VAN if it has tight constraint
print("\n=== SNACKPACK CHOC+VAN basket arb test (target=19940 approx) ===")
SP_pair = ["SNACKPACK_CHOCOLATE","SNACKPACK_VANILLA"]
basket_bid2 = piv_b[SP_pair].sum(axis=1)
basket_ask2 = piv_a[SP_pair].sum(axis=1)
# Use rolling per-day fair (it's not exactly constant but std=76 within range 19767..20109)
# Instead, test: is (mid+mid) mean revert? Compute z-score relative to 19940 with std 76
target = 19940.67
sigma = 76.20
# If basket_bid > target+1*sigma -> sell. If basket_ask < target-1*sigma -> buy.
sell_signal = basket_bid2 - (target + 0.5 * sigma)
buy_signal = (target - 0.5 * sigma) - basket_ask2
sp = sell_signal[sell_signal > 0]
bp = buy_signal[buy_signal > 0]
print(f"  sell signals (>{target+0.5*sigma:.0f}): {len(sp)} mean_edge={sp.mean() if len(sp)>0 else 0:.2f} max={sp.max() if len(sp)>0 else 0:.2f}")
print(f"  buy signals (<{target-0.5*sigma:.0f}): {len(bp)} mean_edge={bp.mean() if len(bp)>0 else 0:.2f} max={bp.max() if len(bp)>0 else 0:.2f}")
