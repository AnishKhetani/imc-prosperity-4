"""
EDA for IMC Prosperity Round 3 Data
Products: VELVETFRUIT_EXTRACT, HYDROGEL_PACK, VEV_XXXX (options)
"""

import pandas as pd
import numpy as np
from scipy.stats import norm
from scipy.optimize import brentq
import warnings
warnings.filterwarnings("ignore")

DATA_DIR = r".\backtester_data\round3"

# ─── Load Data ───────────────────────────────────────────────────────────────

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

print("=" * 70)
print("ROUND 3 EDA — IMC Prosperity")
print("=" * 70)

print(f"\nTotal price rows: {len(prices)}")
print(f"Total trade rows: {len(trades)}")
print(f"\nAll products: {sorted(prices['product'].unique())}")
print(f"\nDays in data: {sorted(prices['day'].unique())}")

# ─── Separate underlyings from options ────────────────────────────────────────

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

# ─── Section 1: Underlying Price Analysis ─────────────────────────────────────

print("\n" + "=" * 70)
print("SECTION 1: UNDERLYING PRICES")
print("=" * 70)

for prod in UNDERLYINGS:
    df = px_under[px_under["product"] == prod].copy()
    df = df.sort_values(["day", "timestamp"])

    mids = df["mid_price"]
    spread = ((df["ask_price_1"] - df["bid_price_1"]).dropna())

    print(f"\n{'-'*50}")
    print(f"  {prod}")
    print(f"{'-'*50}")
    print(f"  Observations : {len(df)}")
    print(f"  Mid Price    : mean={mids.mean():.2f}, std={mids.std():.4f}, "
          f"min={mids.min():.2f}, max={mids.max():.2f}")
    print(f"  Bid-Ask Spd  : mean={spread.mean():.2f}, median={spread.median():.2f}")

    # Per-day breakdown
    for day in [0, 1, 2]:
        d = df[df["day"] == day]["mid_price"]
        if len(d) == 0:
            continue
        returns = d.pct_change().dropna()
        daily_vol = returns.std() * np.sqrt(len(d))
        print(f"  Day {day}: mean={d.mean():.2f}, std={d.std():.4f}, "
              f"range=[{d.min():.1f},{d.max():.1f}], vol_proxy={d.std():.4f}")

    # Autocorrelation of mid price returns
    all_mids = df["mid_price"].values
    if len(all_mids) > 2:
        rets = np.diff(all_mids) / all_mids[:-1]
        autocorr_1 = pd.Series(rets).autocorr(1)
        print(f"  Return autocorr(lag=1): {autocorr_1:.4f}")

# ─── Section 2: Order Book Quality ───────────────────────────────────────────

print("\n" + "=" * 70)
print("SECTION 2: ORDER BOOK DEPTH & QUALITY")
print("=" * 70)

for prod in UNDERLYINGS + list(OPTION_STRIKES.keys()):
    df = prices[prices["product"] == prod].copy()
    if df.empty:
        continue
    spread = (df["ask_price_1"] - df["bid_price_1"]).dropna()
    bv1 = df["bid_volume_1"].fillna(0).mean()
    av1 = df["ask_volume_1"].fillna(0).mean()
    print(f"  {prod:<25}: spread mean={spread.mean():.2f}, "
          f"bid_vol_avg={bv1:.1f}, ask_vol_avg={av1:.1f}, "
          f"rows={len(df)}")

# ─── Section 3: Black-Scholes Implied Volatility ──────────────────────────────

print("\n" + "=" * 70)
print("SECTION 3: OPTIONS — BLACK-SCHOLES ANALYSIS")
print("=" * 70)

def bs_call_price(S, K, T, r, sigma):
    if T <= 0 or sigma <= 0:
        return max(S - K, 0)
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    return S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)

def implied_vol(market_price, S, K, T, r=0.0):
    intrinsic = max(S - K, 0)
    if market_price <= intrinsic + 1e-6:
        return np.nan
    try:
        iv = brentq(lambda v: bs_call_price(S, K, T, r, v) - market_price,
                    1e-6, 20.0, xtol=1e-6, maxiter=200)
        return iv
    except:
        return np.nan

# Total timestamp span per day is ~1,000,000 ticks across 3 days
# Approximate T = (1 - fraction_elapsed) to expiry
# We assume options expire at end of day 2 (last timestamp ~999900 * 3)
TOTAL_TICKS = 999900 * 3  # approximate

def get_T(day, ts):
    elapsed_ticks = day * 999900 + ts
    remaining = TOTAL_TICKS - elapsed_ticks
    T = remaining / TOTAL_TICKS  # fraction of total time remaining
    return max(T, 1e-6)

# Merge options with underlying mid price
vfe = px_under[px_under["product"] == "VELVETFRUIT_EXTRACT"][["day", "timestamp", "mid_price"]].copy()
vfe = vfe.rename(columns={"mid_price": "S"})

# Join nearest underlying price to option observations
# For simplicity, use per-day-timestamp merge (exact match first)
px_opts_iv = px_opts.merge(vfe, on=["day", "timestamp"], how="left")
# Fill remaining S values via forward fill per day
px_opts_iv = px_opts_iv.sort_values(["day", "timestamp"])
px_opts_iv["S"] = px_opts_iv["S"].fillna(method="ffill")

px_opts_iv["T"] = px_opts_iv.apply(lambda r: get_T(r["day"], r["timestamp"]), axis=1)
px_opts_iv["intrinsic"] = np.maximum(px_opts_iv["S"] - px_opts_iv["strike"], 0)
px_opts_iv["time_value"] = px_opts_iv["mid_price"] - px_opts_iv["intrinsic"]

# Compute IV for each row
# Fast IV: sample every 20th row then merge back via nearest-group
sample = px_opts_iv.iloc[::20].copy()
sample["IV"] = sample.apply(
    lambda r: implied_vol(r["mid_price"], r["S"], r["strike"], r["T"])
    if pd.notna(r["S"]) and r["mid_price"] > 0 else np.nan,
    axis=1
)
# Merge back to full frame via nearest-key groupby (use sampled only for summaries)
px_opts_iv = sample.copy()  # summaries use the sample

print("\nIV Summary by Strike (all days combined):")
iv_summary = px_opts_iv.groupby("product")["IV"].agg(["mean", "std", "min", "max", "count"])
iv_summary = iv_summary.sort_values("mean")
print(iv_summary.round(4).to_string())

# IV by day
print("\nIV by Strike and Day:")
iv_by_day = px_opts_iv.groupby(["product", "day"])["IV"].mean().unstack(level="day")
print(iv_by_day.round(4).to_string())

# Volatility smile
print("\nVolatility Smile (average IV by strike, all days):")
smile = px_opts_iv.groupby("strike")["IV"].mean().reset_index()
print(smile.round(4).to_string(index=False))

# ─── Section 4: Moneyness & Time Value Analysis ───────────────────────────────

print("\n" + "=" * 70)
print("SECTION 4: MONEYNESS & TIME VALUE")
print("=" * 70)

px_opts_iv["moneyness"] = px_opts_iv["S"] / px_opts_iv["strike"]

print("\nTime Value by Strike (mean across all days):")
tv_summary = px_opts_iv.groupby("strike")["time_value"].agg(["mean", "std", "min", "max"])
print(tv_summary.round(4).to_string())

print("\nMoneyness by Strike:")
m_summary = px_opts_iv.groupby("strike")["moneyness"].agg(["mean", "std"])
print(m_summary.round(4).to_string())

# ─── Section 5: Price Relationships ──────────────────────────────────────────

print("\n" + "=" * 70)
print("SECTION 5: PUT-CALL PARITY & ARBITRAGE CHECKS")
print("=" * 70)

# Check if option prices are consistent with put-call parity
# For call options: C = S - K*e^(-rT) + P (rearranged)
# We can check: C >= max(S-K, 0) (lower bound)
# and C <= S (upper bound)

print("\nOptions violating lower bound (C < intrinsic):")
violations = px_opts_iv[px_opts_iv["mid_price"] < px_opts_iv["intrinsic"] - 0.5]
if len(violations) == 0:
    print("  None found.")
else:
    print(violations[["day", "timestamp", "product", "strike", "S", "mid_price", "intrinsic"]].head(20).to_string())

print("\nOptions with zero or near-zero price (OTM, deep):")
zero_opts = px_opts_iv[px_opts_iv["mid_price"] < 1.0].groupby("product").size()
print(zero_opts.to_string())

# ─── Section 6: VELVETFRUIT_EXTRACT & HYDROGEL_PACK Spread ───────────────────

print("\n" + "=" * 70)
print("SECTION 6: VFE vs HYDROGEL RELATIONSHIP")
print("=" * 70)

vfe_all = px_under[px_under["product"] == "VELVETFRUIT_EXTRACT"][["day", "timestamp", "mid_price"]].rename(columns={"mid_price": "VFE"})
hgp_all = px_under[px_under["product"] == "HYDROGEL_PACK"][["day", "timestamp", "mid_price"]].rename(columns={"mid_price": "HGP"})

merged = vfe_all.merge(hgp_all, on=["day", "timestamp"], how="inner")
if len(merged) > 0:
    corr = merged["VFE"].corr(merged["HGP"])
    ratio = merged["VFE"] / merged["HGP"]
    print(f"\n  VFE-HGP correlation: {corr:.4f}")
    print(f"  VFE/HGP ratio: mean={ratio.mean():.4f}, std={ratio.std():.6f}")
    print(f"  VFE mean: {merged['VFE'].mean():.2f}, HGP mean: {merged['HGP'].mean():.2f}")

    # Spread
    spread_stat = (merged["VFE"] - 0.5 * merged["HGP"])  # 2x VFE = HGP?
    print(f"\n  VFE - 0.5*HGP (should be constant if ratio is 2): mean={spread_stat.mean():.2f}, std={spread_stat.std():.4f}")

    # Try to find best linear combination
    from numpy.linalg import lstsq
    X = merged["HGP"].values.reshape(-1, 1)
    y = merged["VFE"].values
    coef, _, _, _ = lstsq(np.hstack([X, np.ones_like(X)]), y, rcond=None)
    print(f"\n  Best linear fit: VFE = {coef[0]:.6f} * HGP + {coef[1]:.2f}")
    fitted = coef[0] * merged["HGP"] + coef[1]
    residuals = merged["VFE"] - fitted
    print(f"  Residuals: std={residuals.std():.4f}, max_abs={residuals.abs().max():.4f}")
else:
    print("  Not enough matching timestamps to correlate.")

# ─── Section 7: Option Price Changes (Delta Analysis) ───────────────────────

print("\n" + "=" * 70)
print("SECTION 7: DELTA / OPTION SENSITIVITY ANALYSIS")
print("=" * 70)

# Compute BS delta for each option observation
def bs_delta(S, K, T, r=0.0, sigma=0.2):
    if T <= 0 or sigma <= 0:
        return 1.0 if S > K else 0.0
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    return norm.cdf(d1)

# Use mean IV per strike for delta calculation
mean_iv_by_strike = px_opts_iv.groupby("strike")["IV"].mean()
print("\nMean IV per strike:")
for k, iv in mean_iv_by_strike.items():
    print(f"  K={k}: IV={iv:.4f}")

# Compute implied delta using average underlying and average IV
avg_S = px_opts_iv["S"].mean()
print(f"\n  Average S (VFE): {avg_S:.2f}")
print("\nImplied Deltas (using average IV, T=0.5 as mid-life estimate):")
for strike, iv in mean_iv_by_strike.items():
    if pd.notna(iv):
        T = 0.5
        delta = bs_delta(avg_S, strike, T, sigma=iv)
        gamma_approx = norm.pdf((np.log(avg_S / strike) + 0.5 * iv**2 * T) / (iv * np.sqrt(T))) / (avg_S * iv * np.sqrt(T))
        vega_approx = avg_S * norm.pdf((np.log(avg_S / strike) + 0.5 * iv**2 * T) / (iv * np.sqrt(T))) * np.sqrt(T)
        print(f"  K={strike}: delta={delta:.4f}, gamma_approx={gamma_approx:.6f}, vega_approx={vega_approx:.2f}")

# ─── Section 8: Trade Pattern Analysis ──────────────────────────────────────

print("\n" + "=" * 70)
print("SECTION 8: TRADE ANALYSIS")
print("=" * 70)

print("\nTrade counts by symbol:")
trade_counts = trades.groupby("symbol").size().sort_values(ascending=False)
print(trade_counts.to_string())

print("\nTrade volumes by symbol:")
trade_vol = trades.groupby("symbol")["quantity"].sum().sort_values(ascending=False)
print(trade_vol.to_string())

print("\nAverage trade size by symbol:")
avg_trade = trades.groupby("symbol")["quantity"].mean().sort_values(ascending=False)
print(avg_trade.round(2).to_string())

print("\nPrice distribution of trades by symbol (mean price):")
trade_price_mean = trades.groupby("symbol")["price"].mean()
print(trade_price_mean.round(2).to_string())

# ─── Section 9: Market Making Spread Analysis ────────────────────────────────

print("\n" + "=" * 70)
print("SECTION 9: MARKET MAKING OPPORTUNITY ANALYSIS")
print("=" * 70)

print("\nBid-ask spread statistics (all products):")
for prod in sorted(prices["product"].unique()):
    df = prices[prices["product"] == prod].copy()
    spread = (df["ask_price_1"] - df["bid_price_1"]).dropna()
    mid = df["mid_price"].dropna()
    spread_pct = (spread / mid * 100).dropna()
    if len(spread) > 0:
        print(f"  {prod:<25}: raw={spread.mean():.2f} (σ={spread.std():.2f}), "
              f"pct={spread_pct.mean():.4f}%, mid≈{mid.mean():.2f}")

# ─── Section 10: Mean Reversion Tests ───────────────────────────────────────

print("\n" + "=" * 70)
print("SECTION 10: MEAN REVERSION TESTS (ADF-like)")
print("=" * 70)

# Simple heuristic: look at return autocorrelation
# Negative autocorrelation → mean-reverting; Positive → trending
for prod in UNDERLYINGS:
    df = prices[prices["product"] == prod].sort_values(["day", "timestamp"])
    mids = df["mid_price"].values
    if len(mids) < 10:
        continue
    rets = np.diff(mids)
    ac1 = pd.Series(rets).autocorr(1)
    ac2 = pd.Series(rets).autocorr(2)
    ac5 = pd.Series(rets).autocorr(5)
    print(f"\n  {prod}:")
    print(f"    Return autocorr(1)={ac1:.4f}, (2)={ac2:.4f}, (5)={ac5:.4f}")
    # Variance ratio test (VR > 1 → trending, VR < 1 → mean-reverting)
    r1 = np.var(np.diff(mids, 1))
    r2 = np.var(np.diff(mids, 2)) / 2
    vr = r2 / r1 if r1 > 0 else np.nan
    print(f"    Variance ratio (q=2): {vr:.4f} (>1=trending, <1=mean-reverting)")

# ─── Section 11: Option Spread Opportunities ────────────────────────────────

print("\n" + "=" * 70)
print("SECTION 11: OPTION SPREAD / STRATEGY SIGNALS")
print("=" * 70)

# For each timestamp, look at the full option chain
# Identify potential mispricing: options that are too cheap or too expensive relative to BS
# Sample at day midpoints

for day in [0, 1, 2]:
    day_data = px_opts_iv[px_opts_iv["day"] == day].copy()
    day_data = day_data.sort_values("timestamp")
    
    # Take a sample in the middle
    mid_ts = day_data["timestamp"].median()
    snap = day_data[day_data["timestamp"] == day_data["timestamp"].unique()[len(day_data["timestamp"].unique())//2]]
    
    print(f"\n--- Day {day} Option Chain Snapshot ---")
    snap_sorted = snap[["strike", "S", "mid_price", "intrinsic", "time_value", "IV", "T"]].sort_values("strike")
    print(snap_sorted.round(4).to_string(index=False))

# ─── Section 12: HYDROGEL_PACK — Mean Reversion / Fair Value ────────────────

print("\n" + "=" * 70)
print("SECTION 12: HYDROGEL_PACK DETAILED ANALYSIS")
print("=" * 70)

hgp = px_under[px_under["product"] == "HYDROGEL_PACK"].sort_values(["day", "timestamp"])
hgp_mids = hgp["mid_price"]

print(f"\nHGP price stats: mean={hgp_mids.mean():.2f}, std={hgp_mids.std():.4f}, "
      f"min={hgp_mids.min():.2f}, max={hgp_mids.max():.2f}")

for day in [0, 1, 2]:
    d = hgp[hgp["day"] == day]["mid_price"]
    if len(d) == 0:
        continue
    print(f"  Day {day}: mean={d.mean():.2f}, std={d.std():.4f}, "
          f"range=[{d.min():.1f},{d.max():.1f}]")

# Rolling z-score to check mean reversion signal quality
hgp_all = hgp["mid_price"].values
window = 50
if len(hgp_all) > window:
    rolls = pd.Series(hgp_all)
    roll_mean = rolls.rolling(window).mean()
    roll_std = rolls.rolling(window).std()
    z_scores = (rolls - roll_mean) / roll_std
    # Count profitable reversals
    trades_sim = []
    pos = 0
    entry = 0
    for i in range(window, len(rolls)):
        if z_scores.iloc[i] < -1.5 and pos == 0:
            pos = 1; entry = rolls.iloc[i]
        elif z_scores.iloc[i] > 1.5 and pos == 0:
            pos = -1; entry = rolls.iloc[i]
        elif abs(z_scores.iloc[i]) < 0.3 and pos != 0:
            pnl = pos * (rolls.iloc[i] - entry)
            trades_sim.append(pnl)
            pos = 0
    
    print(f"\n  HGP Mean Reversion Simulation (z-score ±1.5, window={window}):")
    print(f"    Trades: {len(trades_sim)}")
    if trades_sim:
        print(f"    Avg PnL per trade: {np.mean(trades_sim):.4f}")
        print(f"    Total PnL: {sum(trades_sim):.4f}")
        print(f"    Win rate: {sum(1 for p in trades_sim if p > 0) / len(trades_sim):.2%}")

# ─── Section 13: VFE Dynamics & Market-Making ────────────────────────────────

print("\n" + "=" * 70)
print("SECTION 13: VELVETFRUIT_EXTRACT DYNAMICS")
print("=" * 70)

vfe_all_sorted = vfe_all.sort_values(["day", "timestamp"])
vfe_prices = vfe_all_sorted["VFE"].values
rets = np.diff(vfe_prices)
print(f"\nVFE returns: mean={rets.mean():.6f}, std={rets.std():.4f}")
print(f"VFE annualized vol (if 1 tick = ~0.1s): {rets.std() * np.sqrt(9999 * 3):.2f}")

# Check if VFE follows a random walk or has drift
from scipy.stats import ttest_1samp
t_stat, p_val = ttest_1samp(rets, 0)
print(f"\nVFE return t-test (H0: mean=0): t={t_stat:.4f}, p={p_val:.4f}")
if p_val < 0.05:
    print("  → Significant drift detected!")
else:
    print("  → No significant drift (consistent with random walk)")

# ─── Section 14: Position Limit Analysis ────────────────────────────────────

print("\n" + "=" * 70)
print("SECTION 14: POSITION LIMITS & TRADE SIZE CONTEXT")
print("=" * 70)

# From IMC Prosperity typically: VELVETFRUIT_EXTRACT=??, HYDROGEL_PACK=??
# Option position limits vary by contract
print("\nTrade size distribution:")
for sym in sorted(trades["symbol"].unique()):
    t = trades[trades["symbol"] == sym]["quantity"]
    print(f"  {sym:<25}: max={t.max()}, mean={t.mean():.2f}, "
          f"p50={t.median():.1f}, p95={t.quantile(0.95):.1f}")

# ─── Section 15: Market Microstructure — Bid Volume vs Ask Volume ─────────────

print("\n" + "=" * 70)
print("SECTION 15: BID/ASK VOLUME IMBALANCE (ORDER FLOW SIGNALS)")
print("=" * 70)

for prod in UNDERLYINGS + ["VEV_5000", "VEV_5200", "VEV_5300"]:
    df = prices[prices["product"] == prod].copy()
    df["total_bid"] = df[["bid_volume_1","bid_volume_2","bid_volume_3"]].fillna(0).sum(axis=1)
    df["total_ask"] = df[["ask_volume_1","ask_volume_2","ask_volume_3"]].fillna(0).sum(axis=1)
    df["imbalance"] = (df["total_bid"] - df["total_ask"]) / (df["total_bid"] + df["total_ask"] + 1e-6)
    print(f"\n  {prod}: bid_vol={df['total_bid'].mean():.1f}, "
          f"ask_vol={df['total_ask'].mean():.1f}, "
          f"imbalance={df['imbalance'].mean():.4f}")

    # Predict next price move from imbalance
    df = df.sort_values(["day", "timestamp"])
    df["next_mid"] = df["mid_price"].shift(-1)
    df["price_chg"] = df["next_mid"] - df["mid_price"]
    corr = df["imbalance"].corr(df["price_chg"])
    print(f"    Imbalance → next price change correlation: {corr:.4f}")

# ─── SUMMARY ────────────────────────────────────────────────────────────────

print("\n" + "=" * 70)
print("SUMMARY: KEY FINDINGS")
print("=" * 70)
print("""
Run complete. Key items to investigate in findings above:
  1. VFE drift test result
  2. IV smile shape (skew/smirk across strikes)
  3. HGP mean-reversion signal PnL
  4. Order flow imbalance predictive power
  5. Option mispricing relative to BS
  6. VFE-HGP linear relationship residuals
""")
