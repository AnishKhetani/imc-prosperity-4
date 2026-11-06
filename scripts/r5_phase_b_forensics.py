"""
Round 5 Phase B — Full Data Forensics.

No priors. Let the data speak.

Outputs:
- Per-product baseline stats (mean, vol, skew, kurt, OU half-life, Hurst)
- Order-book anatomy (spread, depth, autocorr)
- Cross-product correlation matrix (lag 0); group-internal correlation summary
- Within-group basket / linear-combination tests (PEBBLES sizes, PANEL sizes)
- Anomaly register: >3sigma OB outliers, >0.7 cross-corr spikes, periodicity FFT peaks
- Trade-side analysis: aggressor classification via tick rule (Lee-Ready)

NOTE: trader-name analysis omitted — wiki + data confirm trader IDs not disclosed in P4 R5.
"""
from __future__ import annotations
import os, sys, math, json, warnings
from collections import defaultdict
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
np.set_printoptions(suppress=True, linewidth=160)
pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 60)

ROOT = os.path.join(os.path.dirname(__file__), "..", "round_data", "ROUND_5")
DAYS = [2, 3, 4]
OUT_DIR = os.path.join(os.path.dirname(__file__), "r5_forensic_output")
os.makedirs(OUT_DIR, exist_ok=True)


# ---------- helpers ----------

def hurst(ts: np.ndarray, max_lag: int = 50) -> float:
    """R/S Hurst exponent. H<0.5 mean-reverting, =0.5 random walk, >0.5 trending."""
    ts = np.asarray(ts, dtype=float)
    if len(ts) < max_lag * 4:
        return float("nan")
    lags = range(2, max_lag)
    tau = []
    for lag in lags:
        diff = ts[lag:] - ts[:-lag]
        if diff.std() <= 0:
            return float("nan")
        tau.append(np.std(diff))
    tau = np.array(tau)
    if (tau <= 0).any():
        return float("nan")
    p = np.polyfit(np.log(list(lags)), np.log(tau), 1)
    return float(p[0])


def ou_half_life(ts: np.ndarray) -> float:
    """OU half-life via AR(1) of dx_t = a + b*x_{t-1} + e -> half-life = -ln(2)/ln(1+b)."""
    ts = np.asarray(ts, dtype=float)
    x = ts[:-1]
    dx = np.diff(ts)
    if x.std() == 0:
        return float("nan")
    X = np.column_stack([np.ones_like(x), x])
    try:
        beta, *_ = np.linalg.lstsq(X, dx, rcond=None)
    except Exception:
        return float("nan")
    b = beta[1]
    if b >= 0:
        return float("inf")  # not mean reverting
    return float(-math.log(2) / math.log(1 + b))


def acf(x: np.ndarray, lags=range(1, 21)):
    x = np.asarray(x, dtype=float)
    x = x - x.mean()
    denom = (x * x).sum()
    if denom == 0:
        return [float("nan")] * len(list(lags))
    return [float((x[:-l] * x[l:]).sum() / denom) for l in lags]


def fft_peaks(ts: np.ndarray, top_k: int = 5):
    ts = np.asarray(ts, dtype=float)
    ts = ts - ts.mean()
    if len(ts) < 8:
        return []
    ft = np.fft.rfft(ts)
    power = np.abs(ft) ** 2
    freqs = np.fft.rfftfreq(len(ts))
    # ignore DC + the lowest few bins (long trends)
    mask = freqs > 0.0005
    idx = np.argsort(power[mask])[::-1][:top_k]
    real_idx = np.where(mask)[0][idx]
    return [(float(freqs[i]), int(round(1.0 / freqs[i])), float(power[i])) for i in real_idx]


# ---------- load ----------

print("=" * 90)
print("LOADING R5 DATA")
print("=" * 90)
prices_all, trades_all = [], []
for d in DAYS:
    p = pd.read_csv(os.path.join(ROOT, f"prices_round_5_day_{d}.csv"), sep=";")
    t = pd.read_csv(os.path.join(ROOT, f"trades_round_5_day_{d}.csv"), sep=";")
    print(f"  day {d}: prices rows={len(p):>7}  trades rows={len(t):>6}  "
          f"products={p['product'].nunique()}")
    prices_all.append(p)
    trades_all.append(t)
prices = pd.concat(prices_all, ignore_index=True)
trades = pd.concat(trades_all, ignore_index=True)
products = sorted(prices["product"].unique())
print(f"  total products: {len(products)}")

# Group taxonomy by prefix (first underscore-token, but PEBBLES_L is its own group ~PEBBLES)
def group_of(p):
    parts = p.split("_")
    # canonical groups
    for stem in ("GALAXY_SOUNDS", "MICROCHIP", "OXYGEN_SHAKE", "PANEL", "PEBBLES",
                 "ROBOT", "SLEEP_POD", "SNACKPACK", "TRANSLATOR", "UV_VISOR"):
        if p.startswith(stem):
            return stem
    return parts[0]

groups = defaultdict(list)
for p in products:
    groups[group_of(p)].append(p)
print("  groups:")
for g, items in groups.items():
    print(f"    {g:14} ({len(items)}): {items}")


# ---------- B4: baseline stats per product ----------

print("\n" + "=" * 90)
print("PHASE B4 — BASELINE STATISTICS")
print("=" * 90)

stats_rows = []
for prod in products:
    df = prices[prices["product"] == prod].sort_values(["day", "timestamp"])
    mids = df["mid_price"].astype(float).values
    rets = np.diff(mids)
    spreads = (df["ask_price_1"] - df["bid_price_1"]).astype(float).values
    spreads = spreads[~np.isnan(spreads)]
    bvol = df[["bid_volume_1", "bid_volume_2", "bid_volume_3"]].fillna(0).sum(axis=1).values
    avol = df[["ask_volume_1", "ask_volume_2", "ask_volume_3"]].fillna(0).sum(axis=1).values
    row = dict(
        product=prod,
        n=len(df),
        mid_mean=float(np.nanmean(mids)),
        mid_std=float(np.nanstd(mids)),
        ret_std=float(np.nanstd(rets)) if len(rets) else float("nan"),
        skew=float(pd.Series(rets).skew()) if len(rets) else float("nan"),
        kurt=float(pd.Series(rets).kurt()) if len(rets) else float("nan"),
        spread_mean=float(np.nanmean(spreads)) if len(spreads) else float("nan"),
        spread_med=float(np.nanmedian(spreads)) if len(spreads) else float("nan"),
        depth_b=float(np.nanmean(bvol)),
        depth_a=float(np.nanmean(avol)),
        ou_hl=ou_half_life(mids),
        hurst=hurst(mids, max_lag=80),
        acf1=acf(rets, [1])[0] if len(rets) > 1 else float("nan"),
    )
    stats_rows.append(row)

stats = pd.DataFrame(stats_rows).sort_values(["product"]).reset_index(drop=True)
stats.to_csv(os.path.join(OUT_DIR, "baseline_stats.csv"), index=False)
print(stats.to_string(index=False, float_format=lambda v: f"{v:9.3f}"))


# ---------- B2: order book anatomy + autocorr summary ----------

print("\n" + "=" * 90)
print("PHASE B2 — ORDER BOOK / RETURN AUTOCORRELATION (lag 1..10)")
print("=" * 90)

acf_rows = []
for prod in products:
    df = prices[prices["product"] == prod].sort_values(["day", "timestamp"])
    rets = np.diff(df["mid_price"].astype(float).values)
    if len(rets) < 50:
        continue
    a = acf(rets, range(1, 11))
    acf_rows.append([prod] + a)
acf_df = pd.DataFrame(acf_rows, columns=["product"] + [f"L{i}" for i in range(1, 11)])
acf_df.to_csv(os.path.join(OUT_DIR, "return_acf.csv"), index=False)
# print only ones with abs(L1) > 0.05
strong = acf_df[acf_df["L1"].abs() > 0.05]
print(f"Products with |ACF(1)| > 0.05: {len(strong)} / {len(acf_df)}")
print(strong.to_string(index=False, float_format=lambda v: f"{v:7.3f}"))


# ---------- Within-group cross-product correlations ----------

print("\n" + "=" * 90)
print("PHASE B2/B3 — CROSS-PRODUCT CORRELATIONS (mid returns, lag 0)")
print("=" * 90)

# Build a wide matrix of mid-price returns indexed by (day, timestamp)
piv = prices.pivot_table(index=["day", "timestamp"], columns="product",
                          values="mid_price", aggfunc="first").sort_index()
ret_piv = piv.diff().dropna(how="all")

corr = ret_piv.corr()
corr.to_csv(os.path.join(OUT_DIR, "ret_corr_matrix.csv"))

print("\nTop 25 |corr| pairs (excluding self):")
pairs = []
arr = corr.values
cols = list(corr.columns)
for i in range(len(cols)):
    for j in range(i + 1, len(cols)):
        if not np.isnan(arr[i, j]):
            pairs.append((cols[i], cols[j], arr[i, j]))
pairs.sort(key=lambda x: abs(x[2]), reverse=True)
for a, b, c in pairs[:25]:
    same = "SAME" if group_of(a) == group_of(b) else "DIFF"
    print(f"  {c:+.3f}  [{same}]  {a:35} <-> {b}")

# Within-group correlation summary
print("\nWithin-group return correlation summary:")
for g, items in groups.items():
    sub = corr.loc[items, items]
    triu = sub.values[np.triu_indices_from(sub.values, k=1)]
    triu = triu[~np.isnan(triu)]
    if len(triu) == 0:
        continue
    print(f"  {g:14} mean={np.mean(triu):+.3f}  med={np.median(triu):+.3f}  "
          f"min={np.min(triu):+.3f}  max={np.max(triu):+.3f}")


# ---------- Within-group LINEAR COMBINATION tests (basket / size hierarchy) ----------

print("\n" + "=" * 90)
print("PHASE B3 — WITHIN-GROUP LINEAR COMBINATIONS (cointegration / basket arb)")
print("=" * 90)

# For groups where products may have a fixed price hierarchy (PEBBLES_XS<S<M<L<XL,
# PANEL_1X2<2X2<2X4<...), check (a) mean ordering, (b) ratios, (c) whether
# spread between adjacent levels is stationary (mean-reverting -> arb).
def stationarity_score(spread):
    s = np.asarray(spread, dtype=float)
    s = s[~np.isnan(s)]
    if len(s) < 100:
        return float("nan"), float("nan")
    hl = ou_half_life(s)
    h = hurst(s, max_lag=80)
    return hl, h

print("\n(A) PEBBLES — size hierarchy:")
peb = ["PEBBLES_XS", "PEBBLES_S", "PEBBLES_M", "PEBBLES_L", "PEBBLES_XL"]
peb_means = {p: stats.set_index("product").loc[p, "mid_mean"] for p in peb}
for p, m in peb_means.items():
    print(f"   {p:12} mid_mean={m:9.2f}")
# adjacent spreads
for a, b in zip(peb[:-1], peb[1:]):
    s = piv[b] - piv[a]
    hl, h = stationarity_score(s.dropna().values)
    print(f"   spread {b}-{a}: mean={s.mean():+.2f} std={s.std():.2f} OU_hl={hl:.1f}  hurst={h:.3f}")
# also test a / b ratios
print("\n   PEBBLES pairwise ratios (mean / std):")
for i in range(len(peb)):
    for j in range(i + 1, len(peb)):
        a, b = peb[i], peb[j]
        r = piv[b] / piv[a]
        print(f"     {b}/{a}: mean={r.mean():.4f} std={r.std():.4f}")

print("\n(B) PANEL — geometric size relationships (areas: 1x2=2, 1x4=4, 2x2=4, 2x4=8, 4x4=16):")
panel_areas = {"PANEL_1X2": 2, "PANEL_1X4": 4, "PANEL_2X2": 4,
               "PANEL_2X4": 8, "PANEL_4X4": 16}
for p, a in panel_areas.items():
    if p in stats["product"].values:
        m = stats.set_index("product").loc[p, "mid_mean"]
        print(f"   {p:10} area={a:2d}  mid_mean={m:9.2f}  per-area={m / a:.3f}")
# Test price ~ area linearity:
xs = np.array([panel_areas[p] for p in panel_areas])
ys = np.array([stats.set_index("product").loc[p, "mid_mean"] for p in panel_areas])
slope, intercept = np.polyfit(xs, ys, 1)
print(f"   linear fit: price ~= {slope:.2f} * area + {intercept:.2f}")
# Test area-weighted spread stationarity for the obvious basket:
# 2 x PANEL_1X4 vs PANEL_2X4 (both area 8)
if "PANEL_2X4" in piv and "PANEL_1X4" in piv:
    s = piv["PANEL_2X4"] - 2 * piv["PANEL_1X4"]
    hl, h = stationarity_score(s.dropna().values)
    print(f"   basket  PANEL_2X4 - 2*PANEL_1X4: mean={s.mean():+.2f} std={s.std():.2f} OU_hl={hl:.1f} hurst={h:.3f}")
# 4x4 (area 16) vs 2*2x4 (area 16)
if "PANEL_4X4" in piv and "PANEL_2X4" in piv:
    s = piv["PANEL_4X4"] - 2 * piv["PANEL_2X4"]
    hl, h = stationarity_score(s.dropna().values)
    print(f"   basket  PANEL_4X4 - 2*PANEL_2X4: mean={s.mean():+.2f} std={s.std():.2f} OU_hl={hl:.1f} hurst={h:.3f}")
# 4x4 (16) vs 4*2x2 (16)
if "PANEL_4X4" in piv and "PANEL_2X2" in piv:
    s = piv["PANEL_4X4"] - 4 * piv["PANEL_2X2"]
    hl, h = stationarity_score(s.dropna().values)
    print(f"   basket  PANEL_4X4 - 4*PANEL_2X2: mean={s.mean():+.2f} std={s.std():.2f} OU_hl={hl:.1f} hurst={h:.3f}")
# 2x2 (4) vs 2*1x2 (4)
if "PANEL_2X2" in piv and "PANEL_1X2" in piv:
    s = piv["PANEL_2X2"] - 2 * piv["PANEL_1X2"]
    hl, h = stationarity_score(s.dropna().values)
    print(f"   basket  PANEL_2X2 - 2*PANEL_1X2: mean={s.mean():+.2f} std={s.std():.2f} OU_hl={hl:.1f} hurst={h:.3f}")
# 1x4 (4) vs 2*1x2 (4)
if "PANEL_1X4" in piv and "PANEL_1X2" in piv:
    s = piv["PANEL_1X4"] - 2 * piv["PANEL_1X2"]
    hl, h = stationarity_score(s.dropna().values)
    print(f"   basket  PANEL_1X4 - 2*PANEL_1X2: mean={s.mean():+.2f} std={s.std():.2f} OU_hl={hl:.1f} hurst={h:.3f}")
# 1x4 vs 2x2 (both area 4) — pure substitutes
if "PANEL_1X4" in piv and "PANEL_2X2" in piv:
    s = piv["PANEL_1X4"] - piv["PANEL_2X2"]
    hl, h = stationarity_score(s.dropna().values)
    print(f"   substitute  PANEL_1X4 - PANEL_2X2 (both area 4): mean={s.mean():+.2f} std={s.std():.2f} OU_hl={hl:.1f} hurst={h:.3f}")


# ---------- B1: trade aggressor / impact ----------

print("\n" + "=" * 90)
print("PHASE B1 — TRADE-LEVEL ANALYSIS (no trader IDs available — using aggregate)")
print("=" * 90)

# Compute aggressor side via tick rule: trade.price >= last_mid -> buyer aggressor
trade_summary = []
for prod in products:
    tr = trades[trades["symbol"] == prod].copy()
    pr = prices[prices["product"] == prod][["day", "timestamp", "mid_price",
                                              "bid_price_1", "ask_price_1"]]
    if tr.empty:
        continue
    # join nearest by timestamp (within day)
    # Simplification: trades have (timestamp) but not day; we infer day by file.
    # Using forward-merge per day
    daily = []
    for d, ttr in tr.groupby(tr.get("day", pd.Series(np.nan, index=tr.index)).fillna(0)):
        # day field might not exist; fallback: assign by row index split (~equal size per day)
        pass
    # The trades csvs lack a `day` col, but we concat'd them so we lost the per-day mapping.
    # Re-load with day flag.
    daily_dfs = []
    for d in DAYS:
        ttd = pd.read_csv(os.path.join(ROOT, f"trades_round_5_day_{d}.csv"), sep=";")
        ttd = ttd[ttd["symbol"] == prod].copy()
        ttd["day"] = d
        daily_dfs.append(ttd)
    tr = pd.concat(daily_dfs, ignore_index=True)
    if tr.empty:
        continue
    pr = pr.sort_values(["day", "timestamp"]).reset_index(drop=True)
    tr = tr.sort_values(["day", "timestamp"]).reset_index(drop=True)
    merged = pd.merge_asof(tr, pr, on="timestamp", by="day", direction="backward")
    merged["aggressor_buy"] = merged["price"] >= merged["mid_price"]
    bucks = merged["price"] * merged["quantity"]
    trade_summary.append(dict(
        product=prod,
        n_trades=len(merged),
        total_qty=int(merged["quantity"].sum()),
        notional=float(bucks.sum()),
        med_size=float(merged["quantity"].median()),
        max_size=int(merged["quantity"].max()),
        agg_buy_ratio=float(merged["aggressor_buy"].mean()),
        n_at_mid=int((merged["price"] == merged["mid_price"]).sum()),
    ))
trade_df = pd.DataFrame(trade_summary)
trade_df.to_csv(os.path.join(OUT_DIR, "trade_summary.csv"), index=False)
print(trade_df.to_string(index=False, float_format=lambda v: f"{v:9.3f}"))


# ---------- B3: anomaly register ----------

print("\n" + "=" * 90)
print("PHASE B3 — ANOMALY REGISTER")
print("=" * 90)

anomalies = []

# (1) products whose mid is essentially constant (FIXED VALUE archetype)
const_thresh = 0.01  # ret_std < 1% of mid
for _, row in stats.iterrows():
    if row["ret_std"] < 1.0 and row["mid_std"] < 5:
        anomalies.append(("FIXED_VALUE_CANDIDATE", row["product"],
                          f"ret_std={row['ret_std']:.3f} mid_std={row['mid_std']:.3f}"))

# (2) extreme mean-reversion (Hurst < 0.4 or fast OU half-life)
for _, row in stats.iterrows():
    if row["hurst"] < 0.4 and row["ret_std"] > 0:
        anomalies.append(("STRONG_MEAN_REVERT", row["product"],
                          f"hurst={row['hurst']:.3f} OU_hl={row['ou_hl']:.1f}"))
    elif row["hurst"] > 0.6:
        anomalies.append(("STRONG_TREND", row["product"],
                          f"hurst={row['hurst']:.3f}"))

# (3) extreme negative ACF(1) → strong tick-level mean reversion (MM-friendly)
for _, row in acf_df.iterrows():
    if row["L1"] < -0.15:
        anomalies.append(("STRONG_NEG_ACF1", row["product"], f"acf1={row['L1']:.3f}"))

# (4) cross-product correlation > 0.7
for a, b, c in pairs:
    if abs(c) > 0.7:
        anomalies.append(("HIGH_CORR", f"{a}|{b}",
                          f"corr={c:+.3f} {'SAME' if group_of(a) == group_of(b) else 'DIFF'}"))

# (5) FFT periodicity for products with strong cycles
print("\nFFT top-3 periods (only printed where dominant period <= 5000 ticks):")
for prod in products:
    df = prices[prices["product"] == prod].sort_values(["day", "timestamp"])
    mids = df["mid_price"].astype(float).values
    pks = fft_peaks(mids, top_k=3)
    pks_short = [(p, t, w) for (p, t, w) in pks if t <= 5000 and t >= 5]
    if pks_short:
        # sort by power
        pks_short.sort(key=lambda x: -x[2])
        first = pks_short[0]
        if first[2] > 1e6:  # arbitrary power threshold
            anomalies.append(("PERIODIC", prod, f"period={first[1]}ticks power={first[2]:.2e}"))

print(f"\nTotal anomalies flagged: {len(anomalies)}")
print(f"{'TAG':<28} {'PRODUCT(S)':<55} DETAIL")
print("-" * 130)
for tag, prod, detail in anomalies:
    print(f"{tag:<28} {prod:<55} {detail}")

# Save anomalies
with open(os.path.join(OUT_DIR, "anomaly_register.txt"), "w") as f:
    for tag, prod, detail in anomalies:
        f.write(f"{tag}\t{prod}\t{detail}\n")

print("\n" + "=" * 90)
print(f"Outputs written to {OUT_DIR}")
print("=" * 90)
