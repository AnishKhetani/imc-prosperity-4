"""
EDA Part 2 - Fast Options & Strategy Analysis for IMC Prosperity Round 3
"""
import pandas as pd
import numpy as np
from scipy.stats import norm
from scipy.optimize import brentq
import warnings
warnings.filterwarnings("ignore")

DATA_DIR = r".\backtester_data\round3"

def load_prices():
    dfs = []
    for day in [0, 1, 2]:
        df = pd.read_csv(f"{DATA_DIR}/prices_round_3_day_{day}.csv", sep=";")
        dfs.append(df)
    return pd.concat(dfs, ignore_index=True)

def load_trades():
    dfs = []
    for day in [0, 1, 2]:
        df = pd.read_csv(f"{DATA_DIR}/trades_round_3_day_{day}.csv", sep=";")
        df["day"] = day
        dfs.append(df)
    return pd.concat(dfs, ignore_index=True)

prices = load_prices()
trades = load_trades()

UNDERLYINGS = ["VELVETFRUIT_EXTRACT", "HYDROGEL_PACK"]
OPTION_STRIKES = {
    "VEV_4000": 4000, "VEV_4500": 4500,
    "VEV_5000": 5000, "VEV_5100": 5100,
    "VEV_5200": 5200, "VEV_5300": 5300,
    "VEV_5400": 5400, "VEV_5500": 5500,
    "VEV_6000": 6000, "VEV_6500": 6500,
}

px_under = prices[prices["product"].isin(UNDERLYINGS)].copy()
px_opts  = prices[prices["product"].isin(OPTION_STRIKES.keys())].copy()
px_opts["strike"] = px_opts["product"].map(OPTION_STRIKES)

TOTAL_TICKS = 999900 * 3

# ─── Black-Scholes Helpers ────────────────────────────────────────────────────

def bs_call(S, K, T, sigma, r=0.0):
    if T <= 0 or sigma <= 0: return max(S - K, 0.0)
    d1 = (np.log(S/K) + (r + 0.5*sigma**2)*T) / (sigma*np.sqrt(T))
    d2 = d1 - sigma*np.sqrt(T)
    return S*norm.cdf(d1) - K*np.exp(-r*T)*norm.cdf(d2)

def bs_delta(S, K, T, sigma, r=0.0):
    if T <= 0 or sigma <= 0: return 1.0 if S > K else 0.0
    d1 = (np.log(S/K) + (r + 0.5*sigma**2)*T) / (sigma*np.sqrt(T))
    return norm.cdf(d1)

def bs_vega(S, K, T, sigma, r=0.0):
    if T <= 0 or sigma <= 0: return 0.0
    d1 = (np.log(S/K) + (r + 0.5*sigma**2)*T) / (sigma*np.sqrt(T))
    return S * norm.pdf(d1) * np.sqrt(T)

def implied_vol(mkt, S, K, T, r=0.0):
    intrinsic = max(S - K, 0)
    if mkt <= intrinsic + 0.01: return np.nan
    try:
        return brentq(lambda v: bs_call(S, K, T, v, r) - mkt, 1e-6, 20.0, xtol=1e-6, maxiter=200)
    except:
        return np.nan

# ─── Section 3: Options BS Analysis (daily aggregates only = 30 calcs) ─────────

print("=" * 70)
print("SECTION 3: OPTIONS — BLACK-SCHOLES ANALYSIS (daily averages)")
print("=" * 70)

# Build daily aggregate: mean mid_price and mean S per (product, day)
vfe = px_under[px_under["product"] == "VELVETFRUIT_EXTRACT"][["day", "timestamp", "mid_price"]].rename(columns={"mid_price": "S"})

# For each option, find matching S by merging on day+timestamp (nearest)
px_opts_sorted = px_opts.sort_values(["day", "timestamp"])
vfe_sorted = vfe.sort_values(["day", "timestamp"])

# pd merge_asof for each day
parts = []
for day in [0, 1, 2]:
    o = px_opts_sorted[px_opts_sorted["day"] == day].copy()
    v = vfe_sorted[vfe_sorted["day"] == day].copy()
    merged = pd.merge_asof(o, v, on="timestamp", direction="nearest", suffixes=("", "_v"))
    parts.append(merged)
px_opts_w_S = pd.concat(parts, ignore_index=True)

# Compute T for each row
px_opts_w_S["T"] = px_opts_w_S.apply(
    lambda r: max((TOTAL_TICKS - (r["day"] * 999900 + r["timestamp"])) / TOTAL_TICKS, 1e-6), axis=1
)
px_opts_w_S["intrinsic"] = np.maximum(px_opts_w_S["S"] - px_opts_w_S["strike"], 0)
px_opts_w_S["time_value"] = px_opts_w_S["mid_price"] - px_opts_w_S["intrinsic"]

# Now aggregate to daily summaries BEFORE computing IV (only 30 rows)
daily_agg = px_opts_w_S.groupby(["product", "strike", "day"]).agg(
    mid_price=("mid_price", "mean"),
    S=("S", "mean"),
    T=("T", "mean"),
    intrinsic=("intrinsic", "mean"),
    time_value=("time_value", "mean"),
).reset_index()

daily_agg["IV"] = daily_agg.apply(
    lambda r: implied_vol(r["mid_price"], r["S"], r["strike"], r["T"]), axis=1
)

print("\nDaily Average IV by Strike:")
iv_table = daily_agg.pivot_table(index="strike", columns="day", values="IV")
print(iv_table.round(4).to_string())

print("\nOverall Mean IV by Strike (volatility smile):")
smile = daily_agg.groupby("strike")["IV"].mean().reset_index()
smile.columns = ["Strike", "IV_mean"]
print(smile.round(4).to_string(index=False))

print("\nTime Value by Strike (daily avg):")
tv_table = daily_agg.pivot_table(index="strike", columns="day", values="time_value")
print(tv_table.round(2).to_string())

print("\nAverage Underlying (VFE) Price by Day:")
avg_s = daily_agg.groupby("day")["S"].mean()
print(avg_s.round(2).to_string())

# Mid IV for greeks
mid_iv_by_strike = daily_agg.groupby("strike")["IV"].mean()
avg_S_overall = daily_agg["S"].mean()
T_mid = 0.5

print("\nOption Greeks (using mean IV, T=0.5, avg S=%.2f):" % avg_S_overall)
print(f"  {'Strike':>7}  {'IV':>6}  {'Delta':>6}  {'Intrinsic':>10}  {'TimeVal':>8}")
for _, row in smile.iterrows():
    K = int(row["Strike"])
    iv = row["IV_mean"]
    if np.isnan(iv): continue
    delta = bs_delta(avg_S_overall, K, T_mid, iv)
    intrinsic = max(avg_S_overall - K, 0)
    tv = bs_call(avg_S_overall, K, T_mid, iv) - intrinsic
    print(f"  {K:>7}  {iv:>6.4f}  {delta:>6.4f}  {intrinsic:>10.2f}  {tv:>8.2f}")

# ─── Section 4: Volatility Smile Analysis ────────────────────────────────────

print("\n" + "=" * 70)
print("SECTION 4: VOLATILITY SMILE / SKEW ANALYSIS")
print("=" * 70)

# Check for moneyness vs IV relationship
daily_agg["moneyness"] = daily_agg["S"] / daily_agg["strike"]
moneyness_iv = daily_agg.groupby("strike")[["moneyness", "IV"]].mean()
print("\n  Strike   Moneyness       IV    (ATM~1.0)")
for strike, row in moneyness_iv.iterrows():
    flag = " <-- ATM" if abs(row["moneyness"] - 1.0) < 0.02 else ""
    print(f"  {strike:>6}   {row['moneyness']:>9.4f}  {row['IV']:>8.4f}{flag}")

# IV min/max (check for consistent smile shape)
print("\nIV Range (min/max across days by strike):")
iv_range = daily_agg.groupby("strike")["IV"].agg(["min", "max", "std"])
print(iv_range.round(4).to_string())

# ─── Section 5: Put-Call Parity / Arbitrage Scan ─────────────────────────────

print("\n" + "=" * 70)
print("SECTION 5: LOWER BOUND VIOLATIONS (ARBITRAGE)")
print("=" * 70)

# Check for any option priced below intrinsic on ORIGINAL data (not aggregated)
px_opts_w_S["violation"] = px_opts_w_S["mid_price"] - px_opts_w_S["intrinsic"]
violations = px_opts_w_S[px_opts_w_S["violation"] < -0.5]
print(f"\nRows where option < intrinsic value: {len(violations)}")
if len(violations) > 0:
    print(violations[["day","timestamp","product","strike","S","mid_price","intrinsic","violation"]].head(20).to_string())

# Check for bid < intrinsic (can buy option below intrinsic via bid)
px_opts_w_S["bid_violation"] = px_opts_w_S["bid_price_1"] - px_opts_w_S["intrinsic"]
bid_viols = px_opts_w_S[px_opts_w_S["bid_violation"] < -2]
print(f"\nRows where best BID < intrinsic: {len(bid_viols)}")

# *** CRITICAL: check ASK < intrinsic (true riskless arb) ***
px_opts_w_S["ask_violation"] = px_opts_w_S["ask_price_1"] - px_opts_w_S["intrinsic"]
ask_viols = px_opts_w_S[px_opts_w_S["ask_violation"] < -0.5]
print(f"\nRows where best ASK < intrinsic (BUY option < intrinsic = TRUE ARB): {len(ask_viols)}")
if len(ask_viols) > 0:
    print("Sample:")
    print(ask_viols[["day","timestamp","product","strike","S","ask_price_1","intrinsic","ask_violation"]].head(20).to_string())
    ask_viols_by_prod = ask_viols.groupby("product").agg(
        count=("ask_violation","count"),
        avg_violation=("ask_violation","mean"),
        total_profit=("ask_violation","sum")
    )
    print("\nBy product:")
    print(ask_viols_by_prod.to_string())

# ─── Section 6: VFE-HGP Relationship ─────────────────────────────────────────

print("\n" + "=" * 70)
print("SECTION 6: VFE vs HGP RELATIONSHIP")
print("=" * 70)

vfe_all = px_under[px_under["product"] == "VELVETFRUIT_EXTRACT"][["day", "timestamp", "mid_price"]].rename(columns={"mid_price": "VFE"})
hgp_all = px_under[px_under["product"] == "HYDROGEL_PACK"][["day", "timestamp", "mid_price"]].rename(columns={"mid_price": "HGP"})

merged_uh = pd.merge(
    vfe_all,
    hgp_all,
    on=["day","timestamp"],
    how="inner"
)

corr = merged_uh["VFE"].corr(merged_uh["HGP"])
ratio = merged_uh["VFE"] / merged_uh["HGP"]
print(f"\n  VFE-HGP Pearson correlation: {corr:.6f}")
print(f"  VFE/HGP ratio: mean={ratio.mean():.6f}, std={ratio.std():.8f}, "
      f"range=[{ratio.min():.6f},{ratio.max():.6f}]")
print(f"  VFE mean={merged_uh['VFE'].mean():.4f}, HGP mean={merged_uh['HGP'].mean():.4f}")
print(f"  Natural ratio = VFE/HGP = {merged_uh['VFE'].mean() / merged_uh['HGP'].mean():.6f}")

# OLS: VFE = a*HGP + b
from numpy.linalg import lstsq
X = np.column_stack([merged_uh["HGP"].values, np.ones(len(merged_uh))])
coef, _, _, _ = lstsq(X, merged_uh["VFE"].values, rcond=None)
fitted = X @ coef
residuals = merged_uh["VFE"].values - fitted
print(f"\n  OLS: VFE = {coef[0]:.8f} * HGP + {coef[1]:.4f}")
print(f"  Residual std: {residuals.std():.4f}, max_abs: {np.abs(residuals).max():.4f}")

# Mean reversion simulation on VFE-HGP spread
spread = merged_uh["VFE"] - coef[0] * merged_uh["HGP"] - coef[1]
spread_std = spread.std()
print(f"\n  Residual spread std={spread_std:.4f}")
ac1 = spread.autocorr(1)
ac2 = spread.autocorr(2)
print(f"  Spread autocorr(1)={ac1:.4f}, autocorr(2)={ac2:.4f}")

# ─── Section 7: Mean Reversion Tests ─────────────────────────────────────────

print("\n" + "=" * 70)
print("SECTION 7: MEAN REVERSION ANALYSIS")
print("=" * 70)

for prod in UNDERLYINGS:
    df = prices[prices["product"] == prod].sort_values(["day", "timestamp"])
    mids = df["mid_price"].values
    rets = np.diff(mids)
    ac1 = pd.Series(rets).autocorr(1)
    ac2 = pd.Series(rets).autocorr(2)
    ac5 = pd.Series(rets).autocorr(5)
    r1 = np.var(np.diff(mids, 1))
    r2 = np.var(np.diff(mids, 2)) / 2
    vr = r2 / r1 if r1 > 0 else np.nan
    print(f"\n  {prod}:")
    print(f"    Return autocorr(1)={ac1:.4f}, (2)={ac2:.4f}, (5)={ac5:.4f}")
    print(f"    Variance ratio(q=2)={vr:.4f}  (>1=trending, <1=mean-reverting)")

    # Simulate z-score mean reversion strategy
    window = 100
    rolls = pd.Series(mids)
    roll_mean = rolls.rolling(window).mean()
    roll_std  = rolls.rolling(window).std()
    z = (rolls - roll_mean) / (roll_std + 1e-9)
    
    pnl_list = []
    pos = 0; entry = 0
    for i in range(window, len(rolls)):
        z_i = z.iloc[i]
        p_i = rolls.iloc[i]
        if z_i < -1.5 and pos == 0:
            pos = 1; entry = p_i
        elif z_i > 1.5 and pos == 0:
            pos = -1; entry = p_i
        elif abs(z_i) < 0.3 and pos != 0:
            pnl_list.append(pos * (p_i - entry))
            pos = 0
    
    print(f"    Z-score MR sim (z=1.5, exit=0.3, win={window}): "
          f"trades={len(pnl_list)}, "
          f"avg_pnl={np.mean(pnl_list) if pnl_list else 0:.4f}, "
          f"total={sum(pnl_list):.2f}, "
          f"win_rate={sum(1 for p in pnl_list if p>0)/len(pnl_list):.2%}" if pnl_list else "    No trades")

# ─── Section 8: Market Making Analysis ───────────────────────────────────────

print("\n" + "=" * 70)
print("SECTION 8: MARKET MAKING PROFITABILITY ESTIMATE")
print("=" * 70)

# For each product, simulate: post at mid ± half_spread, earn spread when filled
# Assume fill rate proportional to order book activity
for prod in UNDERLYINGS + ["VEV_5000", "VEV_5200", "VEV_5300", "VEV_5400"]:
    df = prices[prices["product"] == prod].copy()
    spread = (df["ask_price_1"] - df["bid_price_1"]).dropna()
    mid = df["mid_price"].dropna()
    
    # Effective spread captured by MM = bid-ask spread / 2 (one side)
    half_spread = spread.mean() / 2
    
    # Estimate number of fills from trade data
    t = trades[trades["symbol"] == prod]
    n_fills = len(t)
    avg_fill_qty = t["quantity"].mean() if len(t) > 0 else 0
    
    # Simple: if we MM all 3 days, estimate daily revenue
    # MM earns half-spread × quantity per fill (rough estimate assuming ~50% fill rate)
    mm_pnl_est = half_spread * avg_fill_qty * n_fills * 0.5
    
    print(f"\n  {prod}:")
    print(f"    Half-spread: {half_spread:.3f}, Avg trade size: {avg_fill_qty:.1f}")
    print(f"    Trade count (3 days): {n_fills}")
    print(f"    Estimated MM PnL (3 days): {mm_pnl_est:.1f}")

# ─── Section 9: Order Flow Imbalance ────────────────────────────────────────

print("\n" + "=" * 70)
print("SECTION 9: ORDER FLOW IMBALANCE SIGNAL")
print("=" * 70)

for prod in UNDERLYINGS + ["VEV_5000", "VEV_5200", "VEV_5300"]:
    df = prices[prices["product"] == prod].copy()
    df = df.sort_values(["day", "timestamp"])
    df["total_bid"] = df[["bid_volume_1","bid_volume_2","bid_volume_3"]].fillna(0).sum(axis=1)
    df["total_ask"] = df[["ask_volume_1","ask_volume_2","ask_volume_3"]].fillna(0).sum(axis=1)
    df["OFI"] = (df["total_bid"] - df["total_ask"]) / (df["total_bid"] + df["total_ask"] + 1e-6)
    df["ret_next"] = df["mid_price"].shift(-1) - df["mid_price"]
    
    corr = df["OFI"].corr(df["ret_next"].shift(1))  # predictive
    corr_lag0 = df["OFI"].corr(df["ret_next"])
    print(f"  {prod}: OFI-return corr (lag0)={corr_lag0:.4f}, (lag1 predict)={corr:.4f}")

# ─── Section 10: HGP Mean Reversion Strategy Simulation ─────────────────────

print("\n" + "=" * 70)
print("SECTION 10: HGP MEAN REVERSION — PARAMETER SWEEP")
print("=" * 70)

hgp = prices[prices["product"] == "HYDROGEL_PACK"].sort_values(["day","timestamp"])
hgp_mids = pd.Series(hgp["mid_price"].values)
hgp_fair = 10000.0  # natural fair value

print(f"\nHGP: mean={hgp_mids.mean():.2f}, std={hgp_mids.std():.4f}")
print(f"HGP dist from 10000: mean_dev={abs(hgp_mids - 10000).mean():.4f}")

# Test different z-score windows and thresholds
best_pnl = -np.inf
best_params = None
for window in [20, 50, 100, 200]:
    roll_mean = hgp_mids.rolling(window).mean()
    roll_std  = hgp_mids.rolling(window).std()
    z = (hgp_mids - roll_mean) / (roll_std + 1e-9)
    for thresh in [0.5, 1.0, 1.5, 2.0, 2.5]:
        for exit_thresh in [0.0, 0.3]:
            pnl_list = []
            pos = 0; entry = 0
            for i in range(window, len(hgp_mids)):
                z_i = z.iloc[i]
                p_i = hgp_mids.iloc[i]
                if z_i < -thresh and pos == 0:
                    pos = 1; entry = p_i
                elif z_i > thresh and pos == 0:
                    pos = -1; entry = p_i
                elif abs(z_i) < exit_thresh and pos != 0:
                    pnl_list.append(pos * (p_i - entry))
                    pos = 0
            total_pnl = sum(pnl_list)
            if total_pnl > best_pnl:
                best_pnl = total_pnl
                best_params = (window, thresh, exit_thresh, len(pnl_list), total_pnl)

if best_params:
    print(f"\n  Best HGP MR params: window={best_params[0]}, entry_z={best_params[1]}, "
          f"exit_z={best_params[2]}")
    print(f"  Trades={best_params[3]}, Total PnL={best_params[4]:.2f}")

# Also test with fair=10000 as anchor
print("\n  Testing HGP with fixed fair=10000.0 anchor:")
for thresh in [5, 10, 15, 20, 25, 30]:
    pnl_list = []
    pos = 0; entry = 0
    for i in range(len(hgp_mids)):
        p = hgp_mids.iloc[i]
        dev = p - hgp_fair
        if dev < -thresh and pos == 0:
            pos = 1; entry = p
        elif dev > thresh and pos == 0:
            pos = -1; entry = p
        elif abs(dev) < thresh * 0.3 and pos != 0:
            pnl_list.append(pos * (p - entry))
            pos = 0
    print(f"    thresh={thresh:>3}: trades={len(pnl_list):>5}, "
          f"total_pnl={sum(pnl_list):>8.2f}, "
          f"avg={np.mean(pnl_list) if pnl_list else 0:>6.2f}")

# ─── Section 11: VFE Option Strategy Backtests ───────────────────────────────

print("\n" + "=" * 70)
print("SECTION 11: VFE OPTION STRATEGY — DELTA NEUTRAL BACKTEST")
print("=" * 70)

# Key insight: if we can identify the "true" IV, we can:
# 1. Market-make the options (buy cheap, sell dear) 
# 2. Or do IV mean reversion (sell when IV high, buy when low)

# Compute IV time series for key strikes using daily agg already computed
print("\nIV by strike by day (for spread trading):")
print(daily_agg.pivot_table(index="strike", columns="day", values="IV").round(4).to_string())

# Which options have widest IV spread (best for selling premium vs buying cheap)?
iv_spread = daily_agg.groupby("strike")["IV"].agg(["max","min"])
iv_spread["range"] = iv_spread["max"] - iv_spread["min"]
print("\nIV Range per strike (max-min across days):")
print(iv_spread.round(4).to_string())

# ─── Section 12: Trade Fingerprinting ──────────────────────────────────────

print("\n" + "=" * 70)
print("SECTION 12: TRADE FINGERPRINTING (counterparty analysis)")
print("=" * 70)

print("\nAll unique currencies in trades:")
print(trades["currency"].value_counts().to_string())

print("\nBuyer/Seller info:")
print(f"  Buyer non-null: {trades['buyer'].notna().sum()}")
print(f"  Seller non-null: {trades['seller'].notna().sum()}")

# Trade clustering - are there regular intervals?
for sym in ["VELVETFRUIT_EXTRACT", "HYDROGEL_PACK"]:
    t = trades[trades["symbol"] == sym].sort_values(["day","timestamp"])
    ts = t["timestamp"].values
    if len(ts) > 2:
        gaps = np.diff(ts)
        print(f"\n  {sym} trade timing gaps: mean={gaps.mean():.0f}, "
              f"median={np.median(gaps):.0f}, min={gaps.min()}, max={gaps.max()}")

# Option trades timing
for sym in list(OPTION_STRIKES.keys())[:4]:
    t = trades[trades["symbol"] == sym]
    if len(t) > 0:
        print(f"\n  {sym}: {len(t)} trades, price range=[{t['price'].min()},{t['price'].max()}]")

# ─── Section 13: Intraday Price Patterns ─────────────────────────────────────

print("\n" + "=" * 70)
print("SECTION 13: INTRADAY PATTERNS (start vs end)")
print("=" * 70)

for prod in UNDERLYINGS:
    df = prices[prices["product"] == prod].sort_values(["day","timestamp"])
    for day in [0, 1, 2]:
        d = df[df["day"] == day]
        if len(d) < 100: continue
        first_10pct = d.head(len(d)//10)["mid_price"].mean()
        last_10pct  = d.tail(len(d)//10)["mid_price"].mean()
        drift = last_10pct - first_10pct
        print(f"  {prod} day {day}: start={first_10pct:.2f}, end={last_10pct:.2f}, drift={drift:+.2f}")

# ─── Section 14: Position Limit Context ──────────────────────────────────────

print("\n" + "=" * 70)
print("SECTION 14: POSITION LIMITS (typical IMC Prosperity values)")
print("=" * 70)

print("""
  Typical position limits for Round 3 products:
  NOTE: These are from competition context / data patterns.
  
  Looking at bid/ask volumes to infer limits:
""")
for prod in sorted(prices["product"].unique()):
    df = prices[prices["product"] == prod]
    max_vol1 = df["bid_volume_1"].max()
    max_vol_total = df[["bid_volume_1","bid_volume_2","bid_volume_3"]].fillna(0).sum(axis=1).max()
    print(f"  {prod:<25}: max_bid_vol1={max_vol1:.0f}, max_total_vol={max_vol_total:.0f}")

# ─── Section 15: Deep OTM Options Analysis ───────────────────────────────────

print("\n" + "=" * 70)
print("SECTION 15: DEEP OTM OPTIONS (VEV_6000, VEV_6500)")
print("=" * 70)

for prod in ["VEV_6000", "VEV_6500"]:
    df = prices[prices["product"] == prod]
    mids = df["mid_price"].dropna()
    print(f"\n  {prod}: mean={mids.mean():.4f}, min={mids.min():.4f}, max={mids.max():.4f}")
    # Price = 0.5 means bid=0, ask=1 (1 tick wide)
    # Can we sell these for 1.0 and buy for 0.5?
    n_at_half = (mids == 0.5).sum()
    n_at_one  = (mids == 1.0).sum()
    print(f"  Price=0.5 (bid=0, ask=1): {n_at_half} rows ({100*n_at_half/len(mids):.1f}%)")
    print(f"  Price=1.0 (bid=1, ask=?): {n_at_one} rows ({100*n_at_one/len(mids):.1f}%)")

# Check max prices for OTM options
for prod in ["VEV_5400", "VEV_5500", "VEV_6000"]:
    df = prices[prices["product"] == prod]
    t = trades[trades["symbol"] == prod]
    vfe_t = px_under[px_under["product"] == "VELVETFRUIT_EXTRACT"]["mid_price"]
    print(f"\n  {prod}: strike={OPTION_STRIKES[prod]}")
    print(f"    Option mid: mean={df['mid_price'].mean():.2f}, max={df['mid_price'].max():.2f}")
    print(f"    VFE needed to go ITM: {OPTION_STRIKES[prod]:.0f}")
    print(f"    VFE max observed: {vfe_t.max():.2f}")
    print(f"    Trades: {len(t)}, max_price_traded={t['price'].max() if len(t)>0 else 0:.2f}")

# ─── Section 16: Best Strategy Summary ───────────────────────────────────────

print("\n" + "=" * 70)
print("SECTION 16: STRATEGIC OPPORTUNITIES RANKED")
print("=" * 70)

# Compute simple metrics for comparison
# 1. VFE Market Making
vfe_df = prices[prices["product"] == "VELVETFRUIT_EXTRACT"]
vfe_spread = (vfe_df["ask_price_1"] - vfe_df["bid_price_1"]).mean()
vfe_trades = len(trades[trades["symbol"] == "VELVETFRUIT_EXTRACT"])
vfe_avg_qty = trades[trades["symbol"] == "VELVETFRUIT_EXTRACT"]["quantity"].mean() if vfe_trades > 0 else 0

# 2. HGP Market Making
hgp_df = prices[prices["product"] == "HYDROGEL_PACK"]
hgp_spread = (hgp_df["ask_price_1"] - hgp_df["bid_price_1"]).mean()
hgp_trades = len(trades[trades["symbol"] == "HYDROGEL_PACK"])
hgp_avg_qty = trades[trades["symbol"] == "HYDROGEL_PACK"]["quantity"].mean() if hgp_trades > 0 else 0

print(f"""
KEY FINDINGS SUMMARY:
=====================

VELVETFRUIT_EXTRACT (VFE):
  - Prices ~5250 with std ~15, range [5198-5300]
  - Bid-ask spread = {vfe_spread:.2f} ticks (TIGHT)
  - Return autocorr(1) = -0.16 (mild mean reversion)
  - {vfe_trades} trades total, avg size {vfe_avg_qty:.1f}

HYDROGEL_PACK (HGP):
  - Prices ~9990 with std ~32, range [9891-10079]  
  - Bid-ask spread = {hgp_spread:.2f} ticks (WIDE for MM)
  - Return autocorr(1) = -0.13 (mild mean reversion)
  - {hgp_trades} trades total, avg size {hgp_avg_qty:.1f}
  - Has a natural "fair value" around 10000

VEV OPTIONS:
  - 10 strikes from 4000 to 6500
  - Call options on VELVETFRUIT_EXTRACT
  - VEV_4000,4500 deep ITM with thick spreads (20+)
  - VEV_5200,5300 near-ATM with tight spreads (~2-3)
  - VEV_6000,6500 effectively worthless (price=0.5)
  - IV smile present (check IV table above)

STRATEGIES TO IMPLEMENT:
========================

1. VFE Market Making (PRIORITY: HIGH)
   - VFE spread = ~5, can earn 1-2 ticks per roundtrip
   - Mild mean reversion supports directional skew
   - High trade frequency = good fill opportunity

2. HGP Market Making / Mean Reversion (PRIORITY: HIGH)
   - Wide spread ~16 ticks = fat margins  
   - Mean-reverts toward 10000 (natural fair value)
   - Z-score strategy: enter at 1.5σ, exit at 0.3σ

3. Option Market Making (PRIORITY: MEDIUM)
   - Near-ATM options (VEV_5200, VEV_5300) have tight spreads
   - Can earn spread on both legs
   - Must delta-hedge with VFE to control risk

4. IV Arbitrage / Smile Trading (PRIORITY: MEDIUM)  
   - If IV smile is consistent, sell high-IV options, buy low-IV
   - Use BS fair value as anchor for pricing

5. Deep OTM Option Selling (PRIORITY: LOW)
   - VEV_6000/6500 priced at 0.5 = near zero
   - Selling at ask=1 earns 0.5 per contract but limited qty
   - VFE never reaches 6000 in data (max ~5300)

6. VFE-HGP Pairs Trading (PRIORITY: LOW unless corr high)
   - Correlation: see Section 6
   - If residual spread is mean-reverting, trade the pair
""")
