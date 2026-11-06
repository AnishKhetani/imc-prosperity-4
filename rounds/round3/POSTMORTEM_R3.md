# Round 3 — Post-Mortem & Submission Notes

**Submission file:** [trader_r3.py](trader_r3.py)
**Harness:** [scripts/run_r3_backtest.py](scripts/run_r3_backtest.py)
**Backtester:** `prosperity3bt==0.12.0` (monkey-patched for Round-3 P4 product names)

---

## 1. Ground truth — what the raw logs told us

All quantitative claims below are sourced from [scripts/forensic_output/forensic_report.md](scripts/forensic_output/forensic_report.md), which ingested `round_data/ROUND_3/prices_round_3_day_{0,1,2}.csv` + `trades_round_3_day_{0,1,2}.csv`.

| # | Hypothesis | Evidence | Decision |
|---|-----------|----------|---------|
| H1 | **HYDROGEL_PACK is stationary mean-reverter.** | mean=9990.8, σ=32, spread=16, AC1=−0.13, half-life≈300 ticks. Bot quotes cluster ±5 around 10 000. | **TRADE** — classic MM product. |
| H4 | **VELVETFRUIT_EXTRACT is a strongly trending series.** | Hurst = 0.97, return σ=1.13, bid-ask spread=5. | **DO NOT MARKET-MAKE.** Spread too tight to cover adverse selection on a hurst-0.97 path. Attempts bled −2.8k/day. |
| H7 | **Voucher IV smile is quadratic-in-moneyness, stable day-to-day.** | Fit σ(m)=0.227·m²+0·m+0.15, m=ln(K/S)/√T. Residual σ 0.013 (day 0) → 0.020 (day 2). Drift is small. | **SMILE-FIT MM** survives regime shift if we EMA-track IV deviations. |
| H15 | **No arbitrage bound violations** in voucher book (butterfly, vertical spread, intrinsic). | 0 violations across 3 days. | No free money via arbitrage — pure MM. |
| H17 | **Liquidity is concentrated in ~6 strikes.** | VEV_6000/6500 (334/d), 5500 (312/d), 4000 (313/d), 5400 (262/d), 5300 (140/d), 5200 (21/d sparse). VEV_4500/5000/5100 < 1/d → dead. | Only quote **[4000, 5400, 5500, 6000, 6500]**. |
| RV vs IV | Underlying realized vol 0.41 vs ATM IV 0.23 → long-vol bias. | One-sample observation; only 3 days. | **REJECTED** for live: 3 days is insufficient to ship naked vega, and a single-day adverse IV move swamps expected edge. |

---

## 2. Strategy tournament — what we kept and why

| Strategy | Kept? | Reason |
|---|---|---|
| **S1: Hydrogel MM** (anchored EMA around 10 000, take-if-edge, make-inside) | ✅ | Textbook stationary MM. +23k to +35k/day in all 3 days. |
| **S2: Velvet MM** | ❌ | H4 kills it. 5-tick spread vs trending path → adverse fills. Disabled (soft no-op stub retained in code). |
| **S3: Voucher smile-fit MM** (online IV EMA per strike → BS fair ± 2 ticks, inventory skew, starvation widen to ±4, min-trade margin 1 tick) | ✅ | Takes small edge vs its own quotes; bounded tail. |
| **S4: Delta-hedge overlay** (hedge voucher delta via Velvet) | ❌ | Hedge leg cost −2.8k/day (Velvet spread). With voucher soft-limit=150 on 5 liquid strikes, naked delta risk is bounded. `VELVET_MAX_HEDGE_SIZE = 0`. |
| **S5: Naked long straddle (RV>IV)** | ❌ | See RV/IV row above. |
| Legacy R1/R2 products (OSMIUM, PEPPER_ROOT) | ❌ | Not listed in Round-3 prices; `NoopStrategy` placeholder only, issues zero orders. |

---

## 3. Risk controls actually in the code

Every control has a numeric threshold traceable to data:

1. **Hard per-product position limits** — copied from IMC spec tables, monkey-patched into `prosperity3bt` (`scripts/run_r3_backtest.py`). 200 for HYDROGEL/VELVET, 300 for each VEV_*.
2. **Soft limits** — `HYDROGEL_SOFT_LIMIT=150`, `VOUCHER_SOFT_LIMIT=150`. We stop adding size once breached; existing-side clears only.
3. **Session PnL circuit breaker** — `SESSION_PNL_FLOOR = −50 000`. Measured 3-day min PnLs are **−5.9k / −4.9k / −9.3k**, so the CB sits ~5× below worst observed drawdown. Once tripped, `flat_only=True` is sticky and all orders become flatten-only.
4. **Starvation fallback** — if a voucher has <1 fill in 1000 ticks, widen quotes to ±4 (prevents stale fair values from sticky at-edge quotes).
5. **Inventory skew** — `VOUCHER_INV_SKEW_TICKS=0.02`: quote midpoint shifts 0.02 ticks per unit of inventory, biasing us toward flatness. Most leveraged single knob on tail risk.
6. **Regime-drift detection via IV EMA** — each voucher maintains its own half-life-50 IV EMA, falling back to global smile when count<50. Drift on day 2 (residual σ 0.020 vs 0.013 on day 0) is auto-tracked.
7. **Liquid-strike gating** — only 5 strikes live. Dead strikes can't feed bad marks into the smile.

---

## 4. Self-audit — 3 days, live parametrization (TTE=5)

Parametrization matches the live submission exactly (`TTE_DAYS_AT_T0=5`). Historical days had true TTE 8/7/6, so these numbers are slightly **pessimistic** vs running each day with its own TTE (running with TTE=8 yields +94.6k; the smile coefs are in reduced moneyness `m=ln(K/S)/√T`, so IV EMA absorbs most of the bias within the 50-tick warm-up).

| Day | Hydrogel | Vouchers | Total | Min PnL (drawdown) |
|----:|---------:|---------:|------:|-------------------:|
| 0 | 23,583 | −1,575 | **22,008** | −5,930 |
| 1 | 34,948 |    986 | **35,934** | −4,926 |
| 2 | 26,172 |  2,328 | **28,500** | −9,308 |
| **Σ** | **84,703** | **1,739** | **86,442** | — |

Rough per-day PnL std ≈ 7k → Sharpe-per-day ≈ 28.8k / 7k ≈ 4.1 (informational; 3 samples).

**Zero CB trips** in all three days. Zero hard-limit violations.

---

## 5. Where the backtester may understate / overstate live PnL

| Direction | Why |
|---|---|
| **Overstates** | `prosperity3bt` replays a static book with no competing bots. Live traders will consume the same edges we see. Hydrogel bot-resting quotes 10001/10008 may not sit as patiently when others also undercut. |
| **Overstates** | VEV_4000 contributed **+5k on day 2** largely from a single late-session trend overshoot (underlying dropped, OTM puts richened). Not statistically repeatable in one live day. Day 0 gave −2.3k on the same leg. Expected live-day contribution ≈ 0 ± 3k. |
| **Understates** | Our `--match-trades worse` setting is the conservative fill mode (we only fill when the book crosses past our price, not at our price). Live matching is usually closer to "best". |
| **Understates** | We're using live-configured TTE=5 against historical days whose true TTE was 8/7/6; smile pricing is slightly off, mostly hurting voucher PnL. |
| **Unknown** | Smile may drift more on live day 3 than the day-0→day-2 residual-σ drift (0.013→0.020). IV EMA half-life=50 ticks helps but won't catch a sudden shift. |

---

## 6. Failure modes & mitigations

| Failure | Symptom | Mitigation in code |
|---|---|---|
| Smile regime break (residual σ > 0.05) | IV EMA lags truth → voucher quotes off | Inventory skew + starvation widen. If PnL floor breached, CB flattens everything. |
| Hydrogel mean drifts off 10 000 | Anchor biased → accumulated one-sided inventory | EMA fair value (half-life ≈ spread width) tracks drift, anchor is only seed. Soft-limit=150 caps exposure. |
| Underlying gaps on last day | Voucher delta losses | Soft-limit=150 across 5 strikes bounds dollar-delta; CB at −50k. |
| Backtester/live data schema difference | Crash | `datamodel.py` dual-imports; wrapped strategy `.run()` in try/except returning empty orders. |
| Velvet re-enabled accidentally | Bleeds capital | Strategy is a no-op stub with a code comment; `VELVET_MAX_HEDGE_SIZE=0`. |

---

## 7. The one knob to tune if you only touch one thing

**`VOUCHER_INV_SKEW_TICKS`** (currently 0.02). Raise it (e.g. 0.04) to tighten flatness — trades edge for lower tail risk. Lower it (0.01) to capture more MM edge if live regime looks benign in the first 2000 ticks. This single value dominates voucher-side tail behavior.

---

## 8. Non-obvious bugs we found and fixed in the harness

These are operational notes worth preserving for future rounds:

1. **`prosperity3bt` does not clear `state.own_trades` between ticks.** `runner.py:297` only *overwrites* a symbol's entry when new fills exist. If a symbol trades at t=1200 and then goes quiet, its old trade is still present at t=5900. Naive PnL loops double-count. **Fix:** gate on `trade.timestamp > last_processed_ts` (see `Trader._compute_pnl`).
2. **`Trade.quantity` is always positive.** Direction lives in `buyer`/`seller` strings. Naive `pos += trade.quantity` is wrong for sells. **Fix:** `if trade.buyer=='SUBMISSION': cash -= qty*price; elif trade.seller=='SUBMISSION': cash += qty*price`.
3. **`LIMITS` is frozen to P3 product names.** P4 products throw "Unknown product" at order submission. **Fix:** monkey-patch `prosperity3bt.data.LIMITS` and `prosperity3bt.runner.LIMITS` in the harness.
4. **Early CB false-trip** when notional (`pos*mid`) was used instead of realized+unrealized PnL. A 200-lot hydrogel position at mid 10000 reads −2M "PnL" instantly. **Fix:** `cum_cash + Σ(pos*mid)`, never `pos*mid` alone.

---

## 9. Go / No-Go checklist before submission

- [x] `TTE_DAYS_AT_T0 = 5` (live) — confirmed line 124 of trader_r3.py
- [x] `VELVET_MAX_HEDGE_SIZE = 0` — Velvet does not hedge or MM
- [x] `SESSION_PNL_FLOOR = −50 000` — 5× worst observed drawdown
- [x] `LIVE_VOUCHER_STRIKES` includes only liquid strikes
- [x] No diagnostic `logger.print` left in hot path
- [x] All 3 backtest days green (PnL > 0, no CB trip)
- [x] Hard limits never touched in any of 3 days
- [ ] **Copy `trader_r3.py` to submission upload field.**
