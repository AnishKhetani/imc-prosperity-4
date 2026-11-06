"""
Round 3 Forensic Research Suite
================================
First-principles interrogation of Prosperity 4 Round 3 data.

Products (live TTE=5d):
  - HYDROGEL_PACK              (delta-1, pos limit 200)
  - VELVETFRUIT_EXTRACT        (delta-1 underlying, pos limit 200)
  - VEV_{4000,4500,5000,5100,5200,5300,5400,5500,6000,6500}  (calls, limit 300 ea.)

Historic days:
  day 0 -> TTE=8d
  day 1 -> TTE=7d
  day 2 -> TTE=6d

Output:
  scripts/forensic_output/
    plots/*.png
    forensic_summary.json       machine-readable summary of every test
    forensic_report.md          human-readable rollup with VERDICTs

Usage:
  python scripts/r3_forensic_suite.py
  python scripts/r3_forensic_suite.py --section H1   # run one hypothesis only
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# ------------------------------------------------------------------
# Config
# ------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "round_data" / "ROUND_3"
OUT_DIR = Path(__file__).resolve().parent / "forensic_output"
PLOT_DIR = OUT_DIR / "plots"
OUT_DIR.mkdir(parents=True, exist_ok=True)
PLOT_DIR.mkdir(parents=True, exist_ok=True)

HYDROGEL = "HYDROGEL_PACK"
VELVET = "VELVETFRUIT_EXTRACT"
STRIKES = [4000, 4500, 5000, 5100, 5200, 5300, 5400, 5500, 6000, 6500]
VOUCHERS = [f"VEV_{k}" for k in STRIKES]
UNDERLYINGS = [HYDROGEL, VELVET]
ALL_PRODUCTS = UNDERLYINGS + VOUCHERS

# Day -> TTE in *years* (1 day = 1/365). We'll also report in days.
HIST_TTE_DAYS = {0: 8, 1: 7, 2: 6}
LIVE_TTE_DAYS = 5
TICK_PER_DAY = 10_000  # 100ms ticks in a "day"

SUMMARY: Dict[str, dict] = {}
REPORT_LINES: List[str] = []


def say(msg: str):
    print(msg)
    REPORT_LINES.append(msg)


def verdict(tag: str, msg: str):
    line = f"[VERDICT::{tag}] {msg}"
    print(line)
    REPORT_LINES.append(line)


# ------------------------------------------------------------------
# Loading
# ------------------------------------------------------------------
def load_prices() -> pd.DataFrame:
    frames = []
    for d in sorted(HIST_TTE_DAYS):
        p = DATA_DIR / f"prices_round_3_day_{d}.csv"
        df = pd.read_csv(p, sep=";")
        df["day"] = d
        frames.append(df)
    out = pd.concat(frames, ignore_index=True)
    out["t"] = out["day"] * TICK_PER_DAY + out["timestamp"] // 100
    return out


def load_trades() -> pd.DataFrame:
    frames = []
    for d in sorted(HIST_TTE_DAYS):
        p = DATA_DIR / f"trades_round_3_day_{d}.csv"
        df = pd.read_csv(p, sep=";")
        df["day"] = d
        frames.append(df)
    out = pd.concat(frames, ignore_index=True)
    out["t"] = out["day"] * TICK_PER_DAY + out["timestamp"] // 100
    return out


def pivot_mid(prices: pd.DataFrame, product: str) -> pd.Series:
    s = prices[prices["product"] == product].set_index("t")["mid_price"].sort_index()
    return s[~s.index.duplicated(keep="first")]


def best_bid_ask(prices: pd.DataFrame, product: str) -> pd.DataFrame:
    d = prices[prices["product"] == product].sort_values("t").copy()
    return d.set_index("t")[
        ["bid_price_1", "bid_volume_1", "ask_price_1", "ask_volume_1", "mid_price", "day"]
    ]


def full_book(prices: pd.DataFrame, product: str) -> pd.DataFrame:
    cols = ["t", "day"] + [f"{s}_price_{i}" for s in ("bid", "ask") for i in (1, 2, 3)] \
        + [f"{s}_volume_{i}" for s in ("bid", "ask") for i in (1, 2, 3)] + ["mid_price"]
    d = prices[prices["product"] == product][cols].sort_values("t").copy()
    return d.set_index("t")


# ------------------------------------------------------------------
# Black-Scholes utilities
# ------------------------------------------------------------------
def _norm_cdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_pdf(x):
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def bs_call(S, K, T, sigma, r=0.0):
    if T <= 0 or sigma <= 0:
        return max(S - K, 0.0)
    d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    return S * _norm_cdf(d1) - K * math.exp(-r * T) * _norm_cdf(d2)


def bs_vega(S, K, T, sigma, r=0.0):
    if T <= 0 or sigma <= 0:
        return 0.0
    d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * math.sqrt(T))
    return S * _norm_pdf(d1) * math.sqrt(T)


def bs_delta(S, K, T, sigma, r=0.0):
    if T <= 0 or sigma <= 0:
        return 1.0 if S > K else 0.0
    d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * math.sqrt(T))
    return _norm_cdf(d1)


def implied_vol(price, S, K, T, r=0.0, tol=1e-6, maxiter=100):
    """Newton with safeguarded bisection."""
    if price <= max(S - K * math.exp(-r * T), 0.0) + 1e-9:
        return np.nan
    if price >= S - 1e-9:
        return np.nan
    lo, hi = 1e-4, 5.0
    # Bisection for robustness.
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        p = bs_call(S, K, T, mid, r)
        if p > price:
            hi = mid
        else:
            lo = mid
        if hi - lo < tol:
            break
    return 0.5 * (lo + hi)


# ------------------------------------------------------------------
# Plot helper (matplotlib import isolated)
# ------------------------------------------------------------------
def _plt():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    return plt


# ==================================================================
# SECTION H0 — Sanity / Schema
# ==================================================================
def H0_schema(prices: pd.DataFrame, trades: pd.DataFrame):
    say("\n===== H0 :: SCHEMA & SANITY =====")
    summary = {}
    summary["prices_rows"] = int(len(prices))
    summary["trades_rows"] = int(len(trades))
    summary["days"] = sorted(prices["day"].unique().tolist())
    summary["products_in_prices"] = sorted(prices["product"].unique().tolist())
    summary["products_in_trades"] = sorted(trades["symbol"].unique().tolist())
    missing_in_trades = sorted(set(ALL_PRODUCTS) - set(summary["products_in_trades"]))
    summary["products_never_traded"] = missing_in_trades

    # Per-product per-day bar coverage
    cov = (prices.groupby(["day", "product"])["timestamp"].nunique()
           .unstack(fill_value=0))
    summary["timestamps_per_day_product"] = cov.to_dict()
    say(f"Prices rows={len(prices)}, Trades rows={len(trades)}, days={summary['days']}")
    say(f"Products missing from trades (i.e. NEVER traded historically): {missing_in_trades}")
    nan_cp = trades["buyer"].isna().all() and trades["seller"].isna().all()
    summary["counterparty_fully_anonymized"] = bool(nan_cp)
    verdict("H0", f"Counterparty columns anonymized={nan_cp}. "
                   f"Products never traded: {missing_in_trades or 'none'}.")
    SUMMARY["H0"] = summary


# ==================================================================
# SECTION H1 — HYDROGEL_PACK stationarity & fair value
# ==================================================================
def H1_hydrogel_stationarity(prices: pd.DataFrame):
    say("\n===== H1 :: HYDROGEL stationarity & fair-value =====")
    mid = pivot_mid(prices, HYDROGEL).dropna()
    r = mid.diff().dropna()
    summary = dict(
        mean=float(mid.mean()), median=float(mid.median()),
        std=float(mid.std()), min=float(mid.min()), max=float(mid.max()),
        mode=float(mid.round().mode().iloc[0]) if len(mid) else None,
        ret_mean=float(r.mean()), ret_std=float(r.std()),
        ret_skew=float(pd.Series(r).skew()), ret_kurt=float(pd.Series(r).kurt()),
        ac1=float(pd.Series(r).autocorr(1)) if len(r) > 2 else None,
        hurst=_hurst(mid.values),
        pct_at_mode=float((mid.round() == mid.round().mode().iloc[0]).mean()),
    )
    # Half-life via AR(1)
    x = mid.values - mid.mean()
    if len(x) > 10:
        phi = np.corrcoef(x[:-1], x[1:])[0, 1]
        summary["ar1_phi"] = float(phi)
        summary["mean_reversion_halflife_ticks"] = (
            float(-math.log(2) / math.log(abs(phi))) if 0 < abs(phi) < 1 else None
        )
    plt = _plt()
    fig, ax = plt.subplots(2, 1, figsize=(10, 6))
    ax[0].plot(mid.values, lw=0.5); ax[0].set_title(f"{HYDROGEL} mid")
    ax[1].hist(mid.values, bins=60); ax[1].set_title(f"{HYDROGEL} mid distribution")
    fig.tight_layout(); fig.savefig(PLOT_DIR / "H1_hydrogel.png"); plt.close(fig)
    v = (
        f"mean={summary['mean']:.2f} std={summary['std']:.3f} "
        f"ac1={summary['ac1']:.3f} hurst={summary['hurst']:.3f} "
        f"halflife={summary.get('mean_reversion_halflife_ticks')}"
    )
    verdict("H1", v)
    SUMMARY["H1"] = summary


def _hurst(x: np.ndarray) -> float:
    """R/S estimator, returns Hurst exponent (~0.5 random, <0.5 mean-rev, >0.5 trend)."""
    x = np.asarray(x, dtype=float)
    N = len(x)
    if N < 100:
        return float("nan")
    lags = np.unique(np.logspace(1.2, math.log10(N // 4), 12).astype(int))
    rs = []
    for lag in lags:
        n_chunks = N // lag
        chunk_rs = []
        for i in range(n_chunks):
            y = x[i * lag:(i + 1) * lag]
            y = y - y.mean()
            Z = np.cumsum(y)
            R = Z.max() - Z.min()
            S = y.std()
            if S > 0:
                chunk_rs.append(R / S)
        if chunk_rs:
            rs.append(np.mean(chunk_rs))
    if len(rs) < 3:
        return float("nan")
    logs_lag = np.log(lags[: len(rs)])
    logs_rs = np.log(rs)
    slope = np.polyfit(logs_lag, logs_rs, 1)[0]
    return float(slope)


# ==================================================================
# SECTION H2/H3 — VELVET trend, returns, fat tails
# ==================================================================
def H2_velvet_dynamics(prices: pd.DataFrame):
    say("\n===== H2/H3 :: VELVETFRUIT returns, drift, fat-tailedness =====")
    mid = pivot_mid(prices, VELVET).dropna()
    r = mid.diff().dropna()
    logr = np.log(mid / mid.shift(1)).dropna()
    ac = {k: float(pd.Series(r).autocorr(k)) for k in (1, 2, 5, 10, 50, 100)}
    # Ljung-Box-ish via squared returns (vol clustering)
    ac_sq = {k: float(pd.Series(r * r).autocorr(k)) for k in (1, 5, 10, 50, 100)}
    # Daily drift by day
    per_day = {}
    for d in sorted(prices["day"].unique()):
        m = pivot_mid(prices[prices["day"] == d], VELVET).dropna()
        per_day[int(d)] = dict(
            start=float(m.iloc[0]), end=float(m.iloc[-1]),
            ret=float(m.iloc[-1] - m.iloc[0]),
            std=float(m.diff().std()),
        )
    summary = dict(
        mean=float(mid.mean()), std=float(mid.std()),
        ret_mean=float(r.mean()), ret_std=float(r.std()),
        ret_skew=float(pd.Series(r).skew()), ret_kurt=float(pd.Series(r).kurt()),
        logret_annualized_vol=float(logr.std() * math.sqrt(TICK_PER_DAY * 365)),
        autocorr_returns=ac,
        autocorr_sq_returns=ac_sq,
        hurst=_hurst(mid.values),
        per_day=per_day,
    )
    plt = _plt()
    fig, ax = plt.subplots(3, 1, figsize=(10, 9))
    ax[0].plot(mid.values, lw=0.5); ax[0].set_title(f"{VELVET} mid")
    ax[1].plot(r.values, lw=0.3); ax[1].set_title(f"{VELVET} 1-tick Δmid")
    ax[2].hist(r.values, bins=120); ax[2].set_yscale("log")
    ax[2].set_title("Δmid distribution (log-y) — fat tails?")
    fig.tight_layout(); fig.savefig(PLOT_DIR / "H2_velvet.png"); plt.close(fig)
    verdict(
        "H2",
        f"mean={summary['mean']:.1f} ret_std={summary['ret_std']:.3f} "
        f"kurt={summary['ret_kurt']:.2f} ac1={ac[1]:.4f} ac(sq,1)={ac_sq[1]:.4f} "
        f"hurst={summary['hurst']:.3f} ann_vol={summary['logret_annualized_vol']:.3f}"
    )
    SUMMARY["H2"] = summary


# ==================================================================
# SECTION H4 — Order-book imbalance predicts return
# ==================================================================
def H4_imbalance_predictive(prices: pd.DataFrame):
    say("\n===== H4 :: Order-book imbalance predictive power =====")
    out = {}
    for prod in [HYDROGEL, VELVET] + VOUCHERS:
        b = best_bid_ask(prices, prod).dropna(subset=["bid_price_1", "ask_price_1"])
        if len(b) < 100:
            continue
        # L1 imbalance
        bv, av = b["bid_volume_1"].astype(float), b["ask_volume_1"].astype(float)
        imb = (bv - av) / (bv + av).replace(0, np.nan)
        mid = b["mid_price"].astype(float)
        for h in (1, 5, 10, 50):
            fwd = mid.shift(-h) - mid
            aligned = pd.concat([imb, fwd], axis=1).dropna()
            if len(aligned) > 100:
                c = aligned.corr().iloc[0, 1]
                out.setdefault(prod, {})[f"corr_imb_vs_fwd{h}"] = float(c)
        # Signed-trade / flow proxy: depth-weighted mid - mid
        wmid = (b["ask_price_1"] * bv + b["bid_price_1"] * av) / (bv + av)
        skew = wmid - mid
        for h in (1, 5, 10):
            fwd = mid.shift(-h) - mid
            aligned = pd.concat([skew, fwd], axis=1).dropna()
            if len(aligned) > 100:
                c = aligned.corr().iloc[0, 1]
                out.setdefault(prod, {})[f"corr_microprice_vs_fwd{h}"] = float(c)
    SUMMARY["H4"] = out
    # Report strongest
    best = sorted(
        ((p, k, v) for p, d in out.items() for k, v in d.items()),
        key=lambda x: -abs(x[2]),
    )[:8]
    for p, k, v in best:
        say(f"  {p:<15} {k:<28} corr={v:+.4f}")
    verdict("H4", f"Top imbalance signal: {best[0] if best else 'none'}")


# ==================================================================
# SECTION H5 — Whale / persistent resting levels
# ==================================================================
def H5_whale_levels(prices: pd.DataFrame):
    say("\n===== H5 :: Persistent large resting volumes (whales) =====")
    out = {}
    for prod in [HYDROGEL, VELVET]:
        fb = full_book(prices, prod).dropna(subset=["bid_volume_1"])
        bid_vols = fb[["bid_volume_1", "bid_volume_2", "bid_volume_3"]].stack().dropna()
        ask_vols = fb[["ask_volume_1", "ask_volume_2", "ask_volume_3"]].stack().dropna()
        q95_b = float(bid_vols.quantile(0.95))
        q95_a = float(ask_vols.quantile(0.95))
        # Count how often a size ≥ q95 appears and whether it repeats at same price
        big_bids = fb[fb["bid_volume_1"] >= q95_b]["bid_price_1"].value_counts().head(5)
        big_asks = fb[fb["ask_volume_1"] >= q95_a]["ask_price_1"].value_counts().head(5)
        out[prod] = dict(
            q95_bid_vol=q95_b, q95_ask_vol=q95_a,
            most_common_big_bid_prices=big_bids.to_dict(),
            most_common_big_ask_prices=big_asks.to_dict(),
        )
        say(f"  {prod} q95 bidvol={q95_b:.0f} askvol={q95_a:.0f} "
            f"top-recurring big bids={dict(big_bids)}")
    SUMMARY["H5"] = out
    verdict("H5", "See forensic_summary.json for recurring whale prices.")


# ==================================================================
# SECTION H6 — Volume clustering / scheduled bursts
# ==================================================================
def H6_volume_clusters(trades: pd.DataFrame):
    say("\n===== H6 :: Volume clustering / periodicity =====")
    out = {}
    for prod in [HYDROGEL, VELVET] + VOUCHERS:
        t = trades[trades["symbol"] == prod]
        if len(t) < 50:
            continue
        vps = t.groupby("t")["quantity"].sum()
        # Inter-arrival times between trades
        iat = np.diff(vps.index.values)
        # FFT on volume-per-tick series to find periodicity
        series = vps.reindex(range(int(vps.index.min()), int(vps.index.max()) + 1), fill_value=0)
        if len(series) > 32:
            spec = np.abs(np.fft.rfft(series.values - series.values.mean()))
            freqs = np.fft.rfftfreq(len(series), d=1.0)
            # top 3 frequencies excluding DC
            idx = np.argsort(spec[1:])[-3:][::-1] + 1
            top_periods = [float(1 / freqs[i]) if freqs[i] > 0 else None for i in idx]
        else:
            top_periods = []
        out[prod] = dict(
            n_trades=int(len(t)),
            total_qty=float(t["quantity"].sum()),
            mean_qty=float(t["quantity"].mean()),
            p99_qty=float(t["quantity"].quantile(0.99)),
            median_iat_ticks=float(np.median(iat)) if len(iat) else None,
            top_fft_periods_ticks=top_periods,
        )
    SUMMARY["H6"] = out
    for p in [VELVET, HYDROGEL]:
        if p in out:
            say(f"  {p}: n_trades={out[p]['n_trades']} "
                f"median_iat={out[p]['median_iat_ticks']} "
                f"top_fft_periods={out[p]['top_fft_periods_ticks']}")
    verdict("H6", "Check top_fft_periods_ticks per product for bot refresh cadence.")


# ==================================================================
# SECTION H7/H8 — Vol smile & term structure
# ==================================================================
def _compute_iv_panel(prices: pd.DataFrame) -> pd.DataFrame:
    """For each (t, strike), compute mid price and implied vol using VELVET mid as S."""
    S = pivot_mid(prices, VELVET)
    rows = []
    for K in STRIKES:
        m = pivot_mid(prices, f"VEV_{K}")
        df = pd.concat([S.rename("S"), m.rename("C")], axis=1).dropna()
        df["K"] = K
        df["day"] = (df.index // TICK_PER_DAY).astype(int)
        df["TTE_days"] = df["day"].map(HIST_TTE_DAYS)
        df["TTE_yr"] = df["TTE_days"] / 365.0
        df["m"] = np.log(df["K"] / df["S"]) / np.sqrt(df["TTE_yr"].replace(0, np.nan))
        # implied vol
        iv = []
        for S_, C_, K_, T_ in df[["S", "C", "K", "TTE_yr"]].itertuples(index=False):
            try:
                iv.append(implied_vol(C_, S_, K_, T_))
            except Exception:
                iv.append(np.nan)
        df["iv"] = iv
        df["t"] = df.index
        rows.append(df.reset_index(drop=True))
    return pd.concat(rows, ignore_index=True)


def H7_smile(prices: pd.DataFrame) -> pd.DataFrame:
    say("\n===== H7 :: Volatility smile shape (day-by-day, strike-by-strike) =====")
    panel = _compute_iv_panel(prices)
    panel.to_parquet(OUT_DIR / "iv_panel.parquet") if _have_pq() else panel.to_csv(
        OUT_DIR / "iv_panel.csv.gz", compression="gzip", index=False
    )
    # Aggregate per (day, K): mean iv & std
    grouped = panel.groupby(["day", "K"])["iv"].agg(["mean", "std", "count"]).reset_index()
    say("day  K     iv_mean  iv_std  n")
    for _, r in grouped.iterrows():
        say(f" {int(r['day'])}  {int(r['K']):<5} {r['mean']:.4f}  {r['std']:.4f}  {int(r['count'])}")
    # Fit parabola iv = a + b*m + c*m^2 per day using all timestamps
    fits = {}
    for d, g in panel.groupby("day"):
        g2 = g.dropna(subset=["iv", "m"])
        if len(g2) < 100:
            continue
        A = np.vstack([np.ones(len(g2)), g2["m"].values, g2["m"].values ** 2]).T
        coef, *_ = np.linalg.lstsq(A, g2["iv"].values, rcond=None)
        resid = g2["iv"].values - A @ coef
        fits[int(d)] = dict(a=float(coef[0]), b=float(coef[1]), c=float(coef[2]),
                             resid_std=float(resid.std()), n=int(len(g2)))
    SUMMARY["H7"] = dict(smile_fit_per_day=fits,
                          iv_by_day_strike=grouped.to_dict(orient="records"))
    # Plot: smile per day
    plt = _plt()
    fig, ax = plt.subplots(1, 1, figsize=(9, 5))
    for d, g in grouped.groupby("day"):
        ax.errorbar(g["K"], g["mean"], yerr=g["std"], marker="o", label=f"day {int(d)} TTE={HIST_TTE_DAYS[int(d)]}d")
    ax.set_xlabel("Strike"); ax.set_ylabel("Implied vol"); ax.legend()
    ax.set_title("Smile per day (mean ± std over ticks)")
    fig.tight_layout(); fig.savefig(PLOT_DIR / "H7_smile.png"); plt.close(fig)
    verdict("H7", f"Parabolic smile fits: {fits}")
    return panel


def _have_pq():
    try:
        import pyarrow  # noqa
        return True
    except Exception:
        return False


def H8_term_structure(panel: pd.DataFrame):
    say("\n===== H8 :: Term structure ATM IV across TTE =====")
    # Define ATM as |m| minimum per timestamp; pick closest strike to S each tick.
    panel = panel.dropna(subset=["iv"])
    if panel.empty:
        SUMMARY["H8"] = {}; verdict("H8", "No IV data"); return
    panel["absm"] = panel["m"].abs()
    # For each (t, day) pick min |m|
    idx = panel.groupby(["day", "t"])["absm"].idxmin()
    atm = panel.loc[idx]
    per_day = atm.groupby("day")["iv"].agg(["mean", "std", "count"]).reset_index()
    per_day["TTE_days"] = per_day["day"].map(HIST_TTE_DAYS)
    say(per_day.to_string(index=False))
    # Fit iv_atm = alpha + beta * TTE_days
    if len(per_day) >= 2:
        x = per_day["TTE_days"].values.astype(float)
        y = per_day["mean"].values
        beta = np.polyfit(x, y, 1)
        extrap_tte5 = float(np.polyval(beta, LIVE_TTE_DAYS))
    else:
        beta = [np.nan, np.nan]; extrap_tte5 = np.nan
    SUMMARY["H8"] = dict(
        atm_iv_by_day=per_day.to_dict(orient="records"),
        linear_fit_slope=float(beta[0]), linear_fit_intercept=float(beta[1]),
        extrapolated_ATM_iv_TTE5=extrap_tte5,
    )
    verdict("H8", f"ATM IV linear extrap to live TTE=5d: {extrap_tte5:.4f}")


# ==================================================================
# SECTION H9 — Static no-arb violations
# ==================================================================
def H9_noarb(prices: pd.DataFrame):
    say("\n===== H9 :: Butterfly / spread / intrinsic violations =====")
    # Need best bid/ask per voucher & underlying each t
    books = {p: best_bid_ask(prices, p) for p in VOUCHERS + [VELVET]}
    common_t = sorted(set.intersection(*(set(b.index) for b in books.values())))
    violations = {"intrinsic_lower_bound": 0, "upper_bound_S": 0,
                   "vertical_spread": 0, "butterfly": 0}
    details = {k: [] for k in violations}
    S_book = books[VELVET]
    for ti in common_t[::10]:  # stride 10 to save time
        S_bid = S_book.loc[ti, "bid_price_1"]
        S_ask = S_book.loc[ti, "ask_price_1"]
        if pd.isna(S_bid) or pd.isna(S_ask):
            continue
        S_mid = 0.5 * (S_bid + S_ask)
        quotes = {}
        for K in STRIKES:
            b = books[f"VEV_{K}"].loc[ti]
            if pd.isna(b["bid_price_1"]) or pd.isna(b["ask_price_1"]):
                continue
            quotes[K] = (float(b["bid_price_1"]), float(b["ask_price_1"]))
        # Intrinsic: C_ask < S_bid - K  => arb buy C, short S, exercise later
        for K, (cb, ca) in quotes.items():
            if ca < max(S_bid - K, 0) - 0.5:
                violations["intrinsic_lower_bound"] += 1
                details["intrinsic_lower_bound"].append((int(ti), K, ca, S_bid))
            if cb > S_ask + 0.5:
                violations["upper_bound_S"] += 1
                details["upper_bound_S"].append((int(ti), K, cb, S_ask))
        # Vertical: K1 < K2 => C(K1) >= C(K2), bid(K1) > ask(K2) => arb
        ks = sorted(quotes)
        for i, K1 in enumerate(ks):
            for K2 in ks[i + 1:]:
                cb1, ca1 = quotes[K1]
                cb2, ca2 = quotes[K2]
                if cb1 - ca2 > 0.5:  # sell K1, buy K2 risk-free >0
                    # wait, lower strike > higher strike call is correct, looking for violation opposite
                    pass
                if cb2 - ca1 > 0.5:  # C(K2_bid) > C(K1_ask) impossible => arb
                    violations["vertical_spread"] += 1
                    details["vertical_spread"].append((int(ti), K1, K2, ca1, cb2))
        # Butterfly with strictly equidistant strikes
        for i in range(len(ks) - 2):
            K1, K2, K3 = ks[i], ks[i + 1], ks[i + 2]
            if (K2 - K1) == (K3 - K2):
                # long K1, long K3 (ask), short 2x K2 (bid): cost = ca1 + ca3 - 2*cb2
                ca1 = quotes[K1][1]; ca3 = quotes[K3][1]; cb2 = quotes[K2][0]
                cost = ca1 + ca3 - 2 * cb2
                if cost < -0.5:
                    violations["butterfly"] += 1
                    details["butterfly"].append((int(ti), K1, K2, K3, cost))
    SUMMARY["H9"] = dict(counts=violations,
                          sample_details={k: v[:5] for k, v in details.items()})
    for k, v in violations.items():
        say(f"  {k}: {v} violation ticks (sampled every 10 ticks)")
    verdict("H9", f"Arb violations: {violations}")


# ==================================================================
# SECTION H10 — Vega/theta ratio: is gamma scalping profitable?
# ==================================================================
def H10_gamma_scalp(panel: pd.DataFrame):
    say("\n===== H10 :: Realized vs implied vol on ATM voucher =====")
    if panel.empty:
        verdict("H10", "No panel"); return
    S = panel.groupby("t")["S"].first().sort_index()
    log_r = np.log(S / S.shift(1)).dropna()
    # Annualized realized vol (per-tick std * sqrt(N_ticks_per_year))
    rv_ann = float(log_r.std() * math.sqrt(TICK_PER_DAY * 365))
    # Compare to mean ATM IV (use H8 output)
    atm_iv = SUMMARY.get("H8", {}).get("atm_iv_by_day", [])
    iv_mean_all = float(np.mean([d["mean"] for d in atm_iv])) if atm_iv else float("nan")
    summary = dict(realized_vol_annualized=rv_ann, atm_iv_mean_annualized=iv_mean_all,
                    iv_minus_rv=iv_mean_all - rv_ann)
    SUMMARY["H10"] = summary
    side = ("SHORT_VOL (IV > RV: straddle sell + delta hedge)"
            if iv_mean_all > rv_ann else
            "LONG_VOL  (RV > IV: straddle buy + delta hedge)")
    verdict("H10", f"RV={rv_ann:.4f} ATM_IV={iv_mean_all:.4f} -> recommend {side}")


# ==================================================================
# SECTION H11 — Bot quote periodicity
# ==================================================================
def H11_quote_periodicity(prices: pd.DataFrame):
    say("\n===== H11 :: Quote-refresh periodicity =====")
    out = {}
    for prod in [HYDROGEL, VELVET] + [VOUCHERS[i] for i in (3, 4, 5, 6)]:  # ATM-ish
        b = best_bid_ask(prices, prod).dropna(subset=["bid_price_1", "ask_price_1"])
        if len(b) < 200:
            continue
        change = (b["bid_price_1"].diff().ne(0) | b["ask_price_1"].diff().ne(0)).astype(int)
        # Inter-change intervals
        idx = np.where(change.values == 1)[0]
        gaps = np.diff(idx) if len(idx) > 1 else np.array([])
        out[prod] = dict(
            frac_ticks_with_change=float(change.mean()),
            median_gap_ticks=float(np.median(gaps)) if len(gaps) else None,
            mode_gap_ticks=float(pd.Series(gaps).mode().iloc[0]) if len(gaps) else None,
        )
        say(f"  {prod}: frac_change={out[prod]['frac_ticks_with_change']:.3f} "
            f"median_gap={out[prod]['median_gap_ticks']} "
            f"mode_gap={out[prod]['mode_gap_ticks']}")
    SUMMARY["H11"] = out
    verdict("H11", "See per-product quote-refresh stats above.")


# ==================================================================
# SECTION H12 — Trade-flow asymmetric impact
# ==================================================================
def H12_flow_impact(prices: pd.DataFrame, trades: pd.DataFrame):
    say("\n===== H12 :: Signed-trade impact on mid =====")
    out = {}
    for prod in [HYDROGEL, VELVET]:
        mid = pivot_mid(prices, prod)
        mid_before = mid  # aligned on t
        tr = trades[trades["symbol"] == prod].copy()
        if tr.empty:
            continue
        # sign by comparing trade price to last mid
        mid_at_t = mid.reindex(tr["t"].values, method="ffill").values
        tr["side"] = np.where(tr["price"].values > mid_at_t, 1,
                                np.where(tr["price"].values < mid_at_t, -1, 0))
        # forward mid move over horizons
        res = {}
        for h in (1, 5, 20):
            fwd = mid.reindex(tr["t"].values + h, method="ffill").values
            move = fwd - mid_at_t
            for s in (1, -1):
                mask = tr["side"].values == s
                if mask.sum() > 20:
                    res[f"h{h}_side{s}_n"] = int(mask.sum())
                    res[f"h{h}_side{s}_meanmove"] = float(np.nanmean(move[mask]))
        out[prod] = res
        for k, v in res.items():
            say(f"  {prod:<25} {k:<25} {v}")
    SUMMARY["H12"] = out
    verdict("H12", "See per-product asymmetric impact stats above.")


# ==================================================================
# SECTION H13 — End-of-day anomalies
# ==================================================================
def H13_eod(prices: pd.DataFrame):
    say("\n===== H13 :: End-of-day behavior =====")
    out = {}
    for prod in [HYDROGEL, VELVET]:
        mid = pivot_mid(prices, prod)
        # slice last 500 ticks of each day vs rest
        for d in sorted(prices["day"].unique()):
            day_ticks = mid[(mid.index // TICK_PER_DAY) == d]
            if len(day_ticks) < 1000:
                continue
            tail = day_ticks.iloc[-500:]
            core = day_ticks.iloc[:-500]
            out.setdefault(prod, {})[f"day{int(d)}"] = dict(
                core_std=float(core.diff().std()),
                tail_std=float(tail.diff().std()),
                tail_drift=float(tail.iloc[-1] - tail.iloc[0]),
            )
    SUMMARY["H13"] = out
    for p, dd in out.items():
        for k, v in dd.items():
            say(f"  {p} {k}: core_std={v['core_std']:.3f} "
                f"tail_std={v['tail_std']:.3f} tail_drift={v['tail_drift']:+.2f}")
    verdict("H13", "Compare tail_std vs core_std — >1.5x means volatile close.")


# ==================================================================
# SECTION H14 — Cross-asset correlations
# ==================================================================
def H14_cross(prices: pd.DataFrame):
    say("\n===== H14 :: Cross-asset correlations =====")
    mids = pd.concat({p: pivot_mid(prices, p) for p in ALL_PRODUCTS}, axis=1).dropna(how="all")
    r = mids.diff().dropna(how="all")
    corr = r.corr()
    SUMMARY["H14"] = dict(corr_matrix=corr.round(4).to_dict())
    plt = _plt()
    fig, ax = plt.subplots(figsize=(10, 8))
    im = ax.imshow(corr.values, vmin=-1, vmax=1, cmap="RdBu_r")
    ax.set_xticks(range(len(corr))); ax.set_xticklabels(corr.columns, rotation=75, fontsize=7)
    ax.set_yticks(range(len(corr))); ax.set_yticklabels(corr.index, fontsize=7)
    ax.set_title("Return correlation (Δmid)")
    fig.colorbar(im); fig.tight_layout()
    fig.savefig(PLOT_DIR / "H14_corr.png"); plt.close(fig)
    # Off-diagonal top
    cv = corr.where(~np.eye(len(corr), dtype=bool))
    pairs = cv.stack().sort_values(ascending=False).head(10)
    say("Top 10 return correlations (non-self):")
    for (a, b), v in pairs.items():
        say(f"  {a:<20} {b:<20} {v:+.3f}")
    verdict("H14", f"HYDROGEL↔VELVET corr: "
                    f"{float(corr.loc[HYDROGEL, VELVET]):.3f}")


# ==================================================================
# SECTION H15 — Spread & edge available per product
# ==================================================================
def H15_spread(prices: pd.DataFrame):
    say("\n===== H15 :: Spread & tradeable edge per product =====")
    out = {}
    for prod in ALL_PRODUCTS:
        b = best_bid_ask(prices, prod).dropna(subset=["bid_price_1", "ask_price_1"])
        if b.empty:
            continue
        spread = (b["ask_price_1"] - b["bid_price_1"])
        out[prod] = dict(
            mean_spread=float(spread.mean()),
            median_spread=float(spread.median()),
            p10_spread=float(spread.quantile(0.1)),
            p90_spread=float(spread.quantile(0.9)),
            mean_price=float(b["mid_price"].mean()),
            spread_bps=float(1e4 * spread.mean() / max(b["mid_price"].mean(), 1e-9)),
            n=int(len(b)),
        )
    SUMMARY["H15"] = out
    say(f"{'product':<22} {'px':>8} {'sprd':>7} {'bps':>8} {'n':>6}")
    for p, d in out.items():
        say(f"  {p:<20} {d['mean_price']:>8.1f} {d['mean_spread']:>7.2f} "
            f"{d['spread_bps']:>8.1f} {d['n']:>6}")
    verdict("H15", "Wider spread = more MM edge potential; penny-wide = pure queue priority.")


# ==================================================================
# SECTION H16 — Regime shift across days (stability for unseen day 4)
# ==================================================================
def H16_regime(prices: pd.DataFrame):
    say("\n===== H16 :: Regime stability across days =====")
    out = {}
    for prod in ALL_PRODUCTS:
        mid = pivot_mid(prices, prod)
        stats = {}
        for d in sorted(prices["day"].unique()):
            m = mid[(mid.index // TICK_PER_DAY) == d]
            if len(m) < 100:
                continue
            stats[int(d)] = dict(
                mean=float(m.mean()), std=float(m.std()),
                ret_std=float(m.diff().std()),
                start=float(m.iloc[0]), end=float(m.iloc[-1]),
            )
        out[prod] = stats
    SUMMARY["H16"] = out
    # Flag products whose per-day mean or vol swings > 25% day-to-day
    say("Products with regime instability (|Δmean|/mean > 2% or |Δretstd|/retstd > 25%):")
    for p, stats in out.items():
        days = sorted(stats)
        if len(days) < 2: continue
        means = [stats[d]["mean"] for d in days]
        stds = [stats[d]["ret_std"] for d in days]
        dm = max(means) / min(means) - 1 if min(means) else 0
        ds = max(stds) / max(min(stds), 1e-9) - 1
        if dm > 0.02 or ds > 0.25:
            say(f"  {p:<22} mean-swing={dm*100:.2f}%  retstd-swing={ds*100:.1f}%")
    verdict("H16", "Stable-regime products = safer for fixed-param strategies. "
                    "Unstable = need adaptive estimators.")


# ==================================================================
# SECTION H17 — Fill plausibility: can we even trade at these levels?
# ==================================================================
def H17_fill_density(prices: pd.DataFrame, trades: pd.DataFrame):
    say("\n===== H17 :: Fill density & available volume =====")
    out = {}
    for prod in ALL_PRODUCTS:
        t = trades[trades["symbol"] == prod]
        total_qty = float(t["quantity"].sum()) if not t.empty else 0.0
        n_days = prices[prices["product"] == prod]["day"].nunique() or 1
        out[prod] = dict(
            total_qty=total_qty,
            qty_per_day=total_qty / n_days,
            # trade count per 1000 ticks
            trades_per_1000t=float(len(t) / (n_days * TICK_PER_DAY) * 1000),
        )
    SUMMARY["H17"] = out
    for p, d in out.items():
        say(f"  {p:<22} qty/day={d['qty_per_day']:>8.0f} trades/1000t={d['trades_per_1000t']:>6.2f}")
    verdict("H17", "Low qty_per_day & trades_per_1000t = illiquid; MM strategy will starve.")


# ==================================================================
# Main
# ==================================================================
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--section", default="ALL",
                     help="One of ALL,H0..H17 (comma-separated ok)")
    args = ap.parse_args()

    say("Loading data…")
    prices = load_prices()
    trades = load_trades()
    say(f"Loaded prices={len(prices)} trades={len(trades)}")

    sections = args.section.upper().split(",")
    do = lambda s: "ALL" in sections or s in sections

    if do("H0"):  H0_schema(prices, trades)
    if do("H1"):  H1_hydrogel_stationarity(prices)
    if do("H2"):  H2_velvet_dynamics(prices)
    if do("H4"):  H4_imbalance_predictive(prices)
    if do("H5"):  H5_whale_levels(prices)
    if do("H6"):  H6_volume_clusters(trades)
    panel = pd.DataFrame()
    if do("H7"):  panel = H7_smile(prices)
    if do("H8"):
        if panel.empty: panel = _compute_iv_panel(prices)
        H8_term_structure(panel)
    if do("H9"):  H9_noarb(prices)
    if do("H10"):
        if panel.empty: panel = _compute_iv_panel(prices)
        H10_gamma_scalp(panel)
    if do("H11"): H11_quote_periodicity(prices)
    if do("H12"): H12_flow_impact(prices, trades)
    if do("H13"): H13_eod(prices)
    if do("H14"): H14_cross(prices)
    if do("H15"): H15_spread(prices)
    if do("H16"): H16_regime(prices)
    if do("H17"): H17_fill_density(prices, trades)

    # Dump
    with open(OUT_DIR / "forensic_summary.json", "w") as f:
        json.dump(SUMMARY, f, indent=2, default=str)
    with open(OUT_DIR / "forensic_report.md", "w", encoding="utf-8") as f:
        f.write("\n".join(REPORT_LINES))
    say(f"\nWrote {OUT_DIR / 'forensic_summary.json'}")
    say(f"Wrote {OUT_DIR / 'forensic_report.md'}")
    say(f"Plots in {PLOT_DIR}")


if __name__ == "__main__":
    main()
