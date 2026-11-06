"""Forensic edge-hunt on R5 historical data.
Four passes:
  (1) per-product autocorrelation (lag 1,5,20) -> mean-reversion targets
  (2) cross-product lag-1 lead-lag correlation -> predictive pairs
  (3) basket sum-invariance scan (cluster-based, not brute force)
  (4) market_trades aggressor -> next-tick mid drift
"""
import os, sys, glob, itertools
import pandas as pd
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "round_data", "ROUND_5")

print("=" * 72)
print("LOADING R5 DATA")
print("=" * 72)

price_files = sorted(glob.glob(os.path.join(DATA, "prices_round_5_day_*.csv")))
trade_files = sorted(glob.glob(os.path.join(DATA, "trades_round_5_day_*.csv")))

prices_list = []
for f in price_files:
    df = pd.read_csv(f, sep=";")
    prices_list.append(df)
prices = pd.concat(prices_list, ignore_index=True)
print(f"  prices: {len(prices)} rows, days={sorted(prices.day.unique())}, products={prices['product'].nunique()}")

trades_list = []
for f in trade_files:
    df = pd.read_csv(f, sep=";")
    # day inferred from filename
    day = int(os.path.basename(f).split("day_")[1].split(".")[0])
    df["day"] = day
    trades_list.append(df)
trades = pd.concat(trades_list, ignore_index=True)
print(f"  trades: {len(trades)} rows, products={trades['symbol'].nunique()}")

# pivot mid-price wide: index=(day,timestamp), col=product
mids = prices.pivot_table(index=["day", "timestamp"], columns="product",
                         values="mid_price", aggfunc="mean").sort_index()
products = list(mids.columns)
print(f"  mid pivot: {mids.shape}")

# returns per day (avoid cross-day discontinuity)
ret_list = []
for d, g in mids.groupby(level=0):
    r = g.diff()
    ret_list.append(r)
returns = pd.concat(ret_list).dropna(how="all")

# -------------------------------------------------------------------------
print("\n" + "=" * 72)
print("PASS 1: PER-PRODUCT AUTOCORRELATION (mean-reversion / momentum)")
print("=" * 72)
ac_rows = []
for p in products:
    s = returns[p].dropna()
    if len(s) < 200:
        continue
    a1 = s.autocorr(lag=1)
    a5 = s.autocorr(lag=5)
    a20 = s.autocorr(lag=20)
    ac_rows.append((p, len(s), a1, a5, a20))
ac = pd.DataFrame(ac_rows, columns=["product", "n", "ac1", "ac5", "ac20"])
print("\nTop 10 |ac1| (most exploitable lag-1 structure):")
print(ac.reindex(ac.ac1.abs().sort_values(ascending=False).index).head(10).to_string(index=False))
print("\nTop 10 |ac5|:")
print(ac.reindex(ac.ac5.abs().sort_values(ascending=False).index).head(10).to_string(index=False))

# -------------------------------------------------------------------------
print("\n" + "=" * 72)
print("PASS 2: CROSS-PRODUCT LAG-1 LEAD-LAG (corr(ret_A_t-1, ret_B_t))")
print("=" * 72)
# Standardize columns
R = returns.copy()
R = R.loc[:, R.std() > 0]
prods = list(R.columns)
# build lagged ret matrix
R_lag1 = R.shift(1)
# correlation between R_lag1 (lead) and R (lag) -> column = current, row = past
# For efficiency: compute per pair with at least 1000 obs
print("\nTop 25 lead->lag pairs by |correlation| (n>=2000, |r|>=0.05):")
results = []
for i, a in enumerate(prods):
    la = R_lag1[a]
    for b in prods:
        if a == b:
            continue
        rb = R[b]
        # align
        valid = la.notna() & rb.notna()
        if valid.sum() < 2000:
            continue
        c = np.corrcoef(la[valid], rb[valid])[0, 1]
        if abs(c) >= 0.05:
            results.append((a, b, valid.sum(), c))
results.sort(key=lambda x: abs(x[3]), reverse=True)
print(f"  {'lead':<32} {'lag':<32} {'n':>6} {'corr':>7}")
for a, b, n, c in results[:25]:
    print(f"  {a:<32} {b:<32} {n:>6} {c:>+7.3f}")
if not results:
    print("  (no pairs cleared |r|>=0.05)")

# -------------------------------------------------------------------------
print("\n" + "=" * 72)
print("PASS 3: BASKET SUM-INVARIANCE (cluster-based)")
print("=" * 72)
# Strategy: find products whose mids are highly cross-correlated (>0.9)
# in *levels*, then check if a sum/diff has stationary residual.
# First: compute correlation matrix on returns.
M = returns.dropna(how="any", axis=1)  # full panel only
print(f"  full-panel returns shape: {M.shape}")
if M.shape[1] >= 2:
    C = M.corr()
    # find pairs with |corr|>=0.5 on returns
    pairs = []
    cols = list(C.columns)
    for i in range(len(cols)):
        for j in range(i+1, len(cols)):
            r = C.iloc[i, j]
            if abs(r) >= 0.5:
                pairs.append((cols[i], cols[j], r))
    pairs.sort(key=lambda x: abs(x[2]), reverse=True)
    print(f"\nReturn-corr pairs |r|>=0.5: {len(pairs)} pairs")
    for a, b, r in pairs[:15]:
        print(f"  {a:<32} {b:<32} r={r:+.3f}")
    # now for top 30 pairs, fit best ratio and check residual std
    print(f"\nCointegration check on top {min(30,len(pairs))} pairs (regress B on A, residual std vs A std):")
    print(f"  {'A':<32} {'B':<32} {'beta':>8} {'res_std':>9} {'A_std':>9} {'ratio':>7}")
    for a, b, _ in pairs[:30]:
        a_levels = mids[a].dropna()
        b_levels = mids[b].dropna()
        common = a_levels.index.intersection(b_levels.index)
        if len(common) < 1000:
            continue
        x = a_levels.loc[common].values
        y = b_levels.loc[common].values
        beta = np.cov(x, y)[0, 1] / np.var(x)
        alpha = y.mean() - beta * x.mean()
        resid = y - (alpha + beta * x)
        rs = resid.std()
        as_ = x.std()
        ratio = rs / (beta * as_) if beta != 0 else float("nan")
        if ratio < 0.5:  # residual notably tighter than scaled A
            print(f"  {a:<32} {b:<32} {beta:>8.3f} {rs:>9.2f} {as_:>9.2f} {ratio:>7.3f}")

# -------------------------------------------------------------------------
print("\n" + "=" * 72)
print("PASS 4: MARKET-TRADE AGGRESSOR -> NEXT-TICK MID DRIFT")
print("=" * 72)
# For each market trade at time t for product p:
#   classify aggressor: price >= mid(t) -> BUY aggressor (+1), else SELL (-1)
#   compute drift = mid(t+100) - mid(t)
# If aggressor signal is informative, mean(drift * sign) > 0 with low p-value.
# We need mid at each timestamp per product per day.
mid_lookup = mids  # MultiIndex (day, timestamp) -> product
# trades: timestamp, buyer, seller, symbol, currency, price, quantity, day
print(f"\nProcessing {len(trades)} trades...")
agg_rows = []
# group by day for fast lookup
for d, td in trades.groupby("day"):
    if d not in mids.index.get_level_values(0):
        continue
    day_mids = mids.loc[d]  # index=timestamp, col=product
    ts_arr = day_mids.index.values
    for sym, sd in td.groupby("symbol"):
        if sym not in day_mids.columns:
            continue
        col = day_mids[sym]
        for ts, price, qty in zip(sd["timestamp"].values, sd["price"].values, sd["quantity"].values):
            # find mid at ts and ts+100 (next tick)
            if ts not in col.index:
                continue
            m_now = col.loc[ts]
            # next tick
            future_ts = ts + 100
            if future_ts not in col.index:
                continue
            m_next = col.loc[future_ts]
            if pd.isna(m_now) or pd.isna(m_next):
                continue
            agg = 1 if price >= m_now else -1
            drift = m_next - m_now
            agg_rows.append((sym, agg, drift, qty))
print(f"  classified {len(agg_rows)} trades")
if agg_rows:
    adf = pd.DataFrame(agg_rows, columns=["sym", "agg", "drift", "qty"])
    adf["signed_drift"] = adf["agg"] * adf["drift"]
    print("\nPer-product aggressor signal (mean signed drift over next 100 ticks):")
    summary = adf.groupby("sym").agg(
        n=("agg", "size"),
        mean_signed_drift=("signed_drift", "mean"),
        std_signed_drift=("signed_drift", "std"),
    )
    summary["t_stat"] = summary["mean_signed_drift"] / (summary["std_signed_drift"] / np.sqrt(summary["n"]))
    summary = summary.sort_values("t_stat", ascending=False)
    print(summary.head(20).to_string())
    print("\nWorst 10 (potentially adverse):")
    print(summary.tail(10).to_string())
    overall = adf["signed_drift"].mean()
    overall_se = adf["signed_drift"].std() / np.sqrt(len(adf))
    print(f"\nOVERALL aggressor signal: {overall:+.4f} ± {overall_se:.4f} (t={overall/overall_se:+.2f}, n={len(adf)})")

print("\n" + "=" * 72)
print("DONE")
print("=" * 72)
