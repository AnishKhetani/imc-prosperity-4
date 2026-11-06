"""
EDA for Round 2 data: ASH_COATED_OSMIUM + INTARIAN_PEPPER_ROOT
Analyzes: spreads, volatility, mean-reversion, depth, cross-asset relationships
"""
import pandas as pd
import numpy as np
import os

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "round_data", "ROUND_2")

def load_prices(day):
    fp = os.path.join(DATA_DIR, f"prices_round_2_day_{day}.csv")
    return pd.read_csv(fp, sep=";")

def load_trades(day):
    fp = os.path.join(DATA_DIR, f"trades_round_2_day_{day}.csv")
    return pd.read_csv(fp, sep=";")

# ── Load all days ──────────────────────────────────────────────
days = [-1, 0, 1]
all_prices = []
all_trades = []
for d in days:
    p = load_prices(d)
    p["day_label"] = d
    all_prices.append(p)
    t = load_trades(d)
    t["day_label"] = d
    all_trades.append(t)

prices = pd.concat(all_prices, ignore_index=True)
trades = pd.concat(all_trades, ignore_index=True)

products = prices["product"].unique()
print(f"Products: {products}")
print(f"Days: {days}")
print(f"Total price rows: {len(prices)}, trade rows: {len(trades)}")
print()

# ── Per-product analysis ───────────────────────────────────────
for prod in sorted(products):
    print(f"\n{'='*70}")
    print(f"  {prod}")
    print(f"{'='*70}")
    
    pp = prices[prices["product"] == prod].copy()
    pp = pp.sort_values(["day_label", "timestamp"]).reset_index(drop=True)
    
    # Basic stats
    print(f"\n--- Price Stats ---")
    print(f"  Mid range: {pp['mid_price'].min():.1f} - {pp['mid_price'].max():.1f}")
    print(f"  Mid mean: {pp['mid_price'].mean():.2f}, std: {pp['mid_price'].std():.2f}")
    
    # Per-day stats
    for d in days:
        day_data = pp[pp["day_label"] == d]
        print(f"  Day {d:>2}: mid {day_data['mid_price'].min():.1f}-{day_data['mid_price'].max():.1f}, "
              f"mean={day_data['mid_price'].mean():.2f}, std={day_data['mid_price'].std():.2f}, "
              f"ticks={len(day_data)}")
    
    # Spread analysis
    print(f"\n--- Spread Distribution ---")
    pp["spread"] = pp["ask_price_1"] - pp["bid_price_1"]
    spread_desc = pp["spread"].describe()
    print(f"  Mean: {spread_desc['mean']:.2f}, Std: {spread_desc['std']:.2f}")
    print(f"  Min: {spread_desc['min']:.0f}, Median: {spread_desc['50%']:.0f}, Max: {spread_desc['max']:.0f}")
    spread_counts = pp["spread"].value_counts().sort_index()
    print(f"  Distribution (top 10):")
    for val, cnt in spread_counts.head(10).items():
        print(f"    spread={val:.0f}: {cnt} ticks ({100*cnt/len(pp):.1f}%)")
    
    # Volatility (returns)
    print(f"\n--- Volatility ---")
    pp["mid_return"] = pp.groupby("day_label")["mid_price"].diff()
    returns = pp["mid_return"].dropna()
    print(f"  Tick return mean: {returns.mean():.4f}, std: {returns.std():.4f}")
    print(f"  Tick return min: {returns.min():.1f}, max: {returns.max():.1f}")
    # Annualized vol (assuming 10000 ticks/day, 252 days)
    daily_vol = returns.std() * np.sqrt(10000)
    print(f"  Daily vol (σ√10000): {daily_vol:.2f}")
    
    # Mean-reversion: autocorrelation of returns
    print(f"\n--- Mean Reversion (Return Autocorrelation) ---")
    for lag in [1, 2, 5, 10]:
        ac = returns.autocorr(lag=lag)
        print(f"  AC(lag={lag}): {ac:.4f}")
    
    # Order book depth
    print(f"\n--- Order Book Depth ---")
    for side, cols in [("Bid", ["bid_volume_1", "bid_volume_2", "bid_volume_3"]),
                       ("Ask", ["ask_volume_1", "ask_volume_2", "ask_volume_3"])]:
        total_depth = pp[cols].sum(axis=1)
        l1_depth = pp[cols[0]]
        print(f"  {side} L1: mean={l1_depth.mean():.1f}, L1+L2+L3 mean={total_depth.mean():.1f}")
    
    # L1 imbalance
    print(f"\n--- L1 Imbalance ---")
    pp["l1_imb"] = (pp["bid_volume_1"] - pp["ask_volume_1"]) / (pp["bid_volume_1"] + pp["ask_volume_1"])
    print(f"  Mean: {pp['l1_imb'].mean():.4f}, Std: {pp['l1_imb'].std():.4f}")
    
    # Imbalance vs next return
    pp["next_return"] = pp.groupby("day_label")["mid_price"].diff().shift(-1)
    valid = pp.dropna(subset=["l1_imb", "next_return"])
    corr = valid["l1_imb"].corr(valid["next_return"])
    print(f"  Imbalance→Next_Return correlation: {corr:.4f}")
    
    # Depth imbalance
    bid_total = pp[["bid_volume_1", "bid_volume_2", "bid_volume_3"]].sum(axis=1)
    ask_total = pp[["ask_volume_1", "ask_volume_2", "ask_volume_3"]].sum(axis=1)
    pp["depth_imb"] = (bid_total - ask_total) / (bid_total + ask_total)
    depth_corr = valid["depth_imb"].corr(valid["next_return"]) if "depth_imb" in valid.columns else np.nan
    # Recalculate with valid rows
    pp2 = pp.dropna(subset=["depth_imb", "next_return"])
    depth_corr = pp2["depth_imb"].corr(pp2["next_return"])
    print(f"  Depth_Imbalance→Next_Return correlation: {depth_corr:.4f}")
    
    # Trades analysis
    pt = trades[trades["symbol"] == prod]
    if len(pt) > 0:
        print(f"\n--- Trades ---")
        print(f"  Total trades: {len(pt)}")
        print(f"  Avg quantity: {pt['quantity'].mean():.1f}")
        print(f"  Unique buyers: {pt['buyer'].nunique()}, sellers: {pt['seller'].nunique()}")
        if 'buyer' in pt.columns:
            print(f"  Top buyers: {pt['buyer'].value_counts().head(5).to_dict()}")
            print(f"  Top sellers: {pt['seller'].value_counts().head(5).to_dict()}")
    print()

# ── Cross-asset analysis ───────────────────────────────────────
print(f"\n{'='*70}")
print(f"  CROSS-ASSET ANALYSIS")
print(f"{'='*70}")

# Merge on timestamp+day for synchronized analysis
aco = prices[prices["product"] == "ASH_COATED_OSMIUM"][["day_label", "timestamp", "mid_price"]].rename(columns={"mid_price": "ACO_mid"})
ipr = prices[prices["product"] == "INTARIAN_PEPPER_ROOT"][["day_label", "timestamp", "mid_price"]].rename(columns={"mid_price": "IPR_mid"})
merged = pd.merge(aco, ipr, on=["day_label", "timestamp"], how="inner")
print(f"Synchronized ticks: {len(merged)}")

# Correlation of mids
corr_mid = merged["ACO_mid"].corr(merged["IPR_mid"])
print(f"Mid price correlation: {corr_mid:.4f}")

# Correlation of returns  
merged["ACO_ret"] = merged.groupby("day_label")["ACO_mid"].diff()
merged["IPR_ret"] = merged.groupby("day_label")["IPR_mid"].diff()
valid_m = merged.dropna(subset=["ACO_ret", "IPR_ret"])
corr_ret = valid_m["ACO_ret"].corr(valid_m["IPR_ret"])
print(f"Return correlation: {corr_ret:.4f}")

# Lead-lag: does ACO return predict IPR next return, or vice versa?
merged["ACO_ret_lag1"] = merged.groupby("day_label")["ACO_ret"].shift(1)
merged["IPR_ret_lag1"] = merged.groupby("day_label")["IPR_ret"].shift(1)
valid_lag = merged.dropna(subset=["ACO_ret", "IPR_ret", "ACO_ret_lag1", "IPR_ret_lag1"])

ll_aco_to_ipr = valid_lag["ACO_ret_lag1"].corr(valid_lag["IPR_ret"])
ll_ipr_to_aco = valid_lag["IPR_ret_lag1"].corr(valid_lag["ACO_ret"])
print(f"Lead-lag ACO(t-1)→IPR(t): {ll_aco_to_ipr:.4f}")
print(f"Lead-lag IPR(t-1)→ACO(t): {ll_ipr_to_aco:.4f}")

# Spread (price ratio) analysis for cointegration-like check
merged["ratio"] = merged["ACO_mid"] / merged["IPR_mid"]
merged["spread_pair"] = merged["ACO_mid"] - merged["IPR_mid"]
print(f"\nPrice ratio (ACO/IPR): mean={merged['ratio'].mean():.6f}, std={merged['ratio'].std():.6f}")
print(f"Price spread (ACO-IPR): mean={merged['spread_pair'].mean():.2f}, std={merged['spread_pair'].std():.2f}")

# Check if spread is mean-reverting: autocorrelation of spread changes
merged["spread_change"] = merged.groupby("day_label")["spread_pair"].diff()
sc = merged["spread_change"].dropna()
for lag in [1, 2, 5, 10]:
    ac = sc.autocorr(lag=lag)
    print(f"  Spread_change AC(lag={lag}): {ac:.4f}")

# Quick cointegration test: regress ACO = a + b*IPR + resid, check if resid is stationary
# Using simple OLS (no scipy needed)
X = merged["IPR_mid"].values
Y = merged["ACO_mid"].values
n = len(X)
x_mean = X.mean()
y_mean = Y.mean()
beta = np.sum((X - x_mean) * (Y - y_mean)) / np.sum((X - x_mean)**2)
alpha = y_mean - beta * x_mean
resid = Y - alpha - beta * X
print(f"\nOLS regression: ACO = {alpha:.2f} + {beta:.4f} * IPR")
print(f"Residual mean: {resid.mean():.4f}, std: {resid.std():.4f}")
resid_ac1 = np.corrcoef(resid[:-1], resid[1:])[0, 1]
print(f"Residual AC(1): {resid_ac1:.4f}")
# If resid AC(1) is close to 1, not cointegrated. If significantly < 1, may be cointegrated.

# Check for level changes between days
print(f"\n--- Per-Day Levels ---")
for d in days:
    dm = merged[merged["day_label"] == d]
    print(f"  Day {d}: ACO mean={dm['ACO_mid'].mean():.2f}, IPR mean={dm['IPR_mid'].mean():.2f}, "
          f"spread={dm['spread_pair'].mean():.2f}, ratio={dm['ratio'].mean():.6f}")

# Check if ASH_COATED_OSMIUM has a fixed fair value like in R1
print(f"\n--- ASH_COATED_OSMIUM: Is FV still fixed? ---")
aco_p = prices[prices["product"] == "ASH_COATED_OSMIUM"]
for d in days:
    day_data = aco_p[aco_p["day_label"] == d]
    mid_mode = day_data["mid_price"].mode().values[0] if len(day_data) > 0 else np.nan
    mid_vals = day_data["mid_price"].value_counts().head(5)
    print(f"  Day {d}: mode={mid_mode}, top mids: {mid_vals.to_dict()}")

print("\n--- INTARIAN_PEPPER_ROOT: Price drift check ---")
ipr_p = prices[prices["product"] == "INTARIAN_PEPPER_ROOT"]
for d in days:
    day_data = ipr_p[ipr_p["day_label"] == d]
    first_mid = day_data["mid_price"].iloc[0] if len(day_data) > 0 else np.nan
    last_mid = day_data["mid_price"].iloc[-1] if len(day_data) > 0 else np.nan
    print(f"  Day {d}: open={first_mid:.1f}, close={last_mid:.1f}, drift={last_mid-first_mid:.1f}")

print("\nDone.")
