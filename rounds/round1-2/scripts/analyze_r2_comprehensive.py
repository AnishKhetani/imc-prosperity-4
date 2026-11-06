"""Comprehensive R2 data analysis for ACO and IPR."""
import pandas as pd
import numpy as np
import json
import os

DATA_DIR = r".\round_data\ROUND_2"
LOG_DIR = r".\logs\277766"

# ─────────────────────── LOAD PRICES ───────────────────────
days = [-1, 0, 1]
all_prices = []
for d in days:
    fpath = os.path.join(DATA_DIR, f"prices_round_2_day_{d}.csv")
    if os.path.exists(fpath):
        df = pd.read_csv(fpath, sep=";")
        all_prices.append(df)
prices = pd.concat(all_prices, ignore_index=True)

# ─────────────────────── LOAD TRADES ───────────────────────
all_trades = []
for d in days:
    fpath = os.path.join(DATA_DIR, f"trades_round_2_day_{d}.csv")
    if os.path.exists(fpath):
        df = pd.read_csv(fpath, sep=";")
        df["day"] = d
        all_trades.append(df)
trades = pd.concat(all_trades, ignore_index=True)

print("=" * 70)
print("ROUND 2 DATA ANALYSIS")
print("=" * 70)

for product in ["ASH_COATED_OSMIUM", "INTARIAN_PEPPER_ROOT"]:
    pdf = prices[prices["product"] == product].copy()
    tdf = trades[trades["symbol"] == product].copy()
    
    print(f"\n{'='*70}")
    print(f"PRODUCT: {product}")
    print(f"{'='*70}")
    
    # ── Mid price stats ──
    mid = pdf["mid_price"].dropna()
    print(f"\nMid Price: min={mid.min():.1f}  max={mid.max():.1f}  mean={mid.mean():.1f}  std={mid.std():.2f}")
    
    # Per-day mid
    for d in days:
        day_mid = pdf[pdf["day"] == d]["mid_price"].dropna()
        if len(day_mid) > 0:
            print(f"  Day {d:>2}: min={day_mid.min():.1f}  max={day_mid.max():.1f}  mean={day_mid.mean():.1f}  std={day_mid.std():.2f}  n={len(day_mid)}")
    
    # ── Spread stats ──
    spread = (pdf["ask_price_1"] - pdf["bid_price_1"]).dropna()
    print(f"\nSpread: min={spread.min():.0f}  max={spread.max():.0f}  mean={spread.mean():.2f}  median={spread.median():.0f}")
    print(f"  Distribution: {dict(spread.value_counts().sort_index())}")
    
    # ── Return autocorrelation ──
    returns = mid.diff().dropna()
    if len(returns) > 10:
        ac1 = returns.autocorr(lag=1)
        ac2 = returns.autocorr(lag=2)
        ac5 = returns.autocorr(lag=5)
        print(f"\nReturn Autocorrelation: lag1={ac1:.4f}  lag2={ac2:.4f}  lag5={ac5:.4f}")
        print(f"  Mean return={returns.mean():.4f}  Std={returns.std():.4f}")
    
    # ── Order book depth ──
    for level in [1, 2, 3]:
        bv = pdf[f"bid_volume_{level}"].dropna()
        av = pdf[f"ask_volume_{level}"].dropna()
        if len(bv) > 0:
            print(f"\nL{level} Bid vol: mean={bv.mean():.1f}  Ask vol: mean={av.mean():.1f}")
    
    # ── Bid/Ask price distributions ──
    b1 = pdf["bid_price_1"].dropna()
    a1 = pdf["ask_price_1"].dropna()
    if len(b1) > 0:
        print(f"\nBid1: min={b1.min():.0f}  max={b1.max():.0f}")
        print(f"Ask1: min={a1.min():.0f}  max={a1.max():.0f}")
    
    # ── Trades ──
    if len(tdf) > 0:
        print(f"\nTrades: {len(tdf)} total")
        print(f"  Price: min={tdf['price'].min():.1f}  max={tdf['price'].max():.1f}  mean={tdf['price'].mean():.1f}")
        print(f"  Size: min={tdf['quantity'].min()}  max={tdf['quantity'].max()}  mean={tdf['quantity'].mean():.1f}")
        # Check buyer/seller patterns
        buyers = tdf["buyer"].value_counts()
        sellers = tdf["seller"].value_counts()
        print(f"  Unique buyers: {len(buyers)}")
        print(f"  Buyer counts: {dict(buyers.head(10))}")
        print(f"  Unique sellers: {len(sellers)}")
        print(f"  Seller counts: {dict(sellers.head(10))}")
        
        # Check for informed trader patterns (fixed size)
        size_dist = tdf["quantity"].value_counts().sort_index()
        print(f"  Size distribution: {dict(size_dist)}")

# ─────────────────────── ACO SPECIFIC ANALYSIS ───────────────────────
print(f"\n{'='*70}")
print("ACO DETAILED MICROSTRUCTURE")
print("="*70)

aco = prices[prices["product"] == "ASH_COATED_OSMIUM"].copy()

# Check if FV is constant at 10000 or drifts
aco_mid = aco.groupby("day")["mid_price"].agg(["mean", "std", "min", "max", "count"])
print(f"\nACO Mid by Day:\n{aco_mid}")

# L1 spread analysis by day
for d in days:
    day_df = aco[aco["day"] == d]
    spread = (day_df["ask_price_1"] - day_df["bid_price_1"]).dropna()
    if len(spread) > 0:
        print(f"\n  Day {d}: Spread mean={spread.mean():.2f}  std={spread.std():.2f}")
        print(f"    Distribution: {dict(spread.value_counts().sort_index().head(20))}")

# Check for the bot's resting levels
print("\n\nACO L2 bid/ask (bot wall) distributions:")
b2 = aco["bid_price_2"].dropna()
a2 = aco["ask_price_2"].dropna()
if len(b2) > 0:
    print(f"  Bid L2: {dict(b2.value_counts().sort_index().head(20))}")
if len(a2) > 0:
    print(f"  Ask L2: {dict(a2.value_counts().sort_index().head(20))}")

# ─────────────────────── IPR SPECIFIC ANALYSIS ───────────────────────
print(f"\n{'='*70}")
print("IPR DETAILED MICROSTRUCTURE")
print("="*70)

ipr = prices[prices["product"] == "INTARIAN_PEPPER_ROOT"].copy()

ipr_mid = ipr.groupby("day")["mid_price"].agg(["mean", "std", "min", "max", "count"])
print(f"\nIPR Mid by Day:\n{ipr_mid}")

# Drift analysis
for d in days:
    day_df = ipr[ipr["day"] == d].copy()
    day_mid = day_df["mid_price"].dropna()
    if len(day_mid) > 5:
        first_half = day_mid.iloc[:len(day_mid)//2].mean()
        second_half = day_mid.iloc[len(day_mid)//2:].mean()
        total_drift = day_mid.iloc[-1] - day_mid.iloc[0] if len(day_mid) > 0 else 0
        print(f"\n  Day {d}: first_half_mean={first_half:.1f}  second_half_mean={second_half:.1f}  total_drift={total_drift:.1f}")

# Spread analysis by day
for d in days:
    day_df = ipr[ipr["day"] == d]
    spread = (day_df["ask_price_1"] - day_df["bid_price_1"]).dropna()
    if len(spread) > 0:
        print(f"\n  Day {d}: Spread mean={spread.mean():.2f}  std={spread.std():.2f}")
        print(f"    Distribution: {dict(spread.value_counts().sort_index().head(20))}")

# ─────────────────────── LOG ANALYSIS ───────────────────────
print(f"\n{'='*70}")
print("LOG 277766 — PERFORMANCE ANALYSIS")
print("="*70)

log_path = os.path.join(LOG_DIR, "277766.json")
with open(log_path, "r") as f:
    log_data = json.load(f)

print(f"\nStatus: {log_data.get('status')}")
print(f"Round: {log_data.get('round')}")
print(f"Total Profit: {log_data.get('profit')}")

# Parse activities log for fill analysis
activities = log_data.get("activitiesLog", "")
if isinstance(activities, str):
    lines = activities.strip().split("\n")
    print(f"\nActivities log: {len(lines)} lines")
    
    # Parse fills
    aco_fills = []
    ipr_fills = []
    aco_pnl_series = []
    ipr_pnl_series = []
    
    for line in lines:
        if not line.strip():
            continue
        parts = line.split(";")
        if len(parts) < 7:
            continue
        try:
            day = int(parts[0])
            ts = int(parts[1])
            product = parts[2]
            bid1 = float(parts[3]) if parts[3] else None
            bv1 = int(parts[4]) if parts[4] else None
            ask1 = float(parts[9]) if len(parts) > 9 and parts[9] else None
            av1 = int(parts[10]) if len(parts) > 10 and parts[10] else None
            mid = float(parts[15]) if len(parts) > 15 and parts[15] else None
            pnl = float(parts[16]) if len(parts) > 16 and parts[16] else None
        except (ValueError, IndexError):
            continue
        
        if product == "ASH_COATED_OSMIUM" and pnl is not None:
            aco_pnl_series.append((ts, pnl))
        elif product == "INTARIAN_PEPPER_ROOT" and pnl is not None:
            ipr_pnl_series.append((ts, pnl))
    
    if aco_pnl_series:
        aco_final = aco_pnl_series[-1][1]
        print(f"\nACO PnL trajectory: start={aco_pnl_series[0][1]:.2f}  end={aco_final:.2f}")
    if ipr_pnl_series:
        ipr_final = ipr_pnl_series[-1][1]
        print(f"IPR PnL trajectory: start={ipr_pnl_series[0][1]:.2f}  end={ipr_final:.2f}")
    if aco_pnl_series and ipr_pnl_series:
        print(f"Combined: {aco_final + ipr_final:.2f}")

# Parse graphLog for PnL curve
graph_log = log_data.get("graphLog", "")
if isinstance(graph_log, str):
    graph_lines = graph_log.strip().split("\n")
    if len(graph_lines) > 1:
        pnl_values = []
        for gl in graph_lines[1:]:  # skip header
            try:
                ts, val = gl.split(";")
                pnl_values.append((int(ts), float(val)))
            except:
                pass
        if pnl_values:
            max_pnl = max(v for _, v in pnl_values)
            min_pnl = min(v for _, v in pnl_values)
            final_pnl = pnl_values[-1][1]
            max_dd = 0
            peak = pnl_values[0][1]
            for _, v in pnl_values:
                peak = max(peak, v)
                max_dd = max(max_dd, peak - v)
            print(f"\nPnL Curve: min={min_pnl:.2f}  max={max_pnl:.2f}  final={final_pnl:.2f}")
            print(f"Max Drawdown: {max_dd:.2f}")
            print(f"Sharpe (rough): {np.mean([pnl_values[i][1] - pnl_values[i-1][1] for i in range(1, len(pnl_values))]) / max(np.std([pnl_values[i][1] - pnl_values[i-1][1] for i in range(1, len(pnl_values))]), 0.001):.4f}")

# ─────────────────────── TICKS ANALYSIS ───────────────────────
print(f"\n{'='*70}")
print("TICK-COUNT AND EMPTY-BOOK ANALYSIS")
print("="*70)
for product in ["ASH_COATED_OSMIUM", "INTARIAN_PEPPER_ROOT"]:
    pdf = prices[prices["product"] == product]
    for d in days:
        ddf = pdf[pdf["day"] == d]
        total = len(ddf)
        empty_bid = ddf["bid_price_1"].isna().sum()
        empty_ask = ddf["ask_price_1"].isna().sum()
        both_empty = ((ddf["bid_price_1"].isna()) & (ddf["ask_price_1"].isna())).sum()
        print(f"\n{product} Day {d}: {total} ticks, empty_bid={empty_bid} ({100*empty_bid/max(total,1):.1f}%), empty_ask={empty_ask} ({100*empty_ask/max(total,1):.1f}%), both_empty={both_empty}")

# ─────────────────────── OPTIMAL WIDTH ANALYSIS ───────────────────────
print(f"\n{'='*70}")
print("OPTIMAL WIDTH ANALYSIS")
print("="*70)

for product in ["ASH_COATED_OSMIUM", "INTARIAN_PEPPER_ROOT"]:
    pdf = prices[prices["product"] == product].copy()
    spread = (pdf["ask_price_1"] - pdf["bid_price_1"]).dropna()
    half_spread = spread / 2.0
    
    print(f"\n{product}:")
    print(f"  Half-spread stats: mean={half_spread.mean():.2f}  min={half_spread.min():.1f}  p5={half_spread.quantile(0.05):.1f}  p25={half_spread.quantile(0.25):.1f}  median={half_spread.median():.1f}")
    
    # For each candidate width, what fraction of ticks would our make orders be inside the spread?
    for w in range(1, 12):
        pct_inside = (half_spread >= w).mean() * 100
        print(f"  WIDTH={w}: {pct_inside:.1f}% ticks inside spread")
