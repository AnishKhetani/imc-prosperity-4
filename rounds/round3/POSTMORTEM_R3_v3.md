# POST-MORTEM — Log 365182 → trader_r3_v3.py

## 1. What happened on the live platform (log 365182)

Submission PnL: **−4,482 XIRECS** on a single-day session (day=2, 1,000 ticks,
ts 0→99,900). Breakdown per product:

| Product | Final PnL | Max DD | Fills | Final Position |
|---|---:|---:|---:|---:|
| HYDROGEL_PACK | −2,667 | −13,066 | 38 | **+150** |
| VEV_4000 | −1,567 | −5,283 | 19 | **+150** |
| VEV_6500 | −150 | −150 | 22 | **+150** |
| VEV_5500 | −72 | −409 | 15 | −150 |
| VEV_5400 | −25 | −952 | 16 | −150 |
| VELVETFRUIT_EXTRACT | 0 | 0 | 0 | 0 (disabled) |
| Others | 0 | — | 0 | 0 |

Every position finished **at soft_limit** on one side — an unambiguous
inventory-spiral signature.

## 2. Classification of the loss

* **HYDROGEL_PACK: adverse-selection + inventory spiral.** Mid trajectory
  10011 → 9927 across 1,000 ticks. The static `FV_ANCHOR=10000` (combined
  50/50 with a fast EMA) kept our fair value near 9990 while market traded
  at 9920–9970. We bought 317 lots @ avg 9994.52 but only managed to sell
  167 @ avg 10008.91. Price never mean-reverted within the session, so we
  finished long +150 at MTM 9927.
* **VEV_6500: structural stuck-long trap.** Bid = 0, ask = 1. The parabolic
  smile model said IV≈0.88 → fair≈5, so we bought every $1 ask. There is
  no counterparty at bid=0 → we **cannot** sell. Any long accumulation is
  permanent. The −150 loss = cash (−150) + MTM (150 × 0.5 = 75) − entry
  (150 × 1 = 150). Trivially toxic.
* **VEV_4000: underlying proxy risk (delta ≈ 1).** K=4000, S≈5267 →
  deep-ITM. Its price = S − K + tiny vega. We held +150 and got run over
  as VELVETFRUIT drifted.
* **VEV_5400 / VEV_5500: smile-fit mispricing vs live market.** The smile
  we fit on days 0–2 predicted IVs that disagreed with whatever the live
  market was pricing, and we built lopsided shorts stuck at soft_limit.

## 3. Why the local backtester missed all of this

Running the identical submitted code `trader_r3.py` over the full
10,000-tick days 0–2 **scored +86,442** — of which HYDROGEL alone earned
+84,703. The gap vs live is structural, not a code bug:

1. **Session length mismatch.** The live platform ran only ~1,000 ticks
   (ts 0–99,900). Our backtester runs 10,000 ticks/day. HYDROGEL is
   mean-reverting over ~300-tick half-life, so the 10× longer window
   gives reversion time for anchor-based quoting to collect the spread.
   The 1,000-tick slice can easily be a one-way drift.
2. **No platform-equivalent penalty for toxic options.** The backtester
   happily lets VEV_6500 sit at bid=0/ask=1 and treats the $0.50 mid as
   real MTM. Live, this position is pinned and impossible to unwind.
3. **Data distribution.** The live day-2 slice started with the same
   price (10011) but drifted harder (ended 9927) than the corresponding
   window of our backtester data (ended 9960 at ts 99,900, 10,010 by end
   of day). Our data is *close* but not identical — a 30-tick worse slice
   is enough to flip a MM strategy from breakeven to −5k.

I confirmed this by replaying the exact 1,000-tick slice with both
codes under `scripts/run_r3_short_slice.py`:
* v1 (submitted): −4,381 — matches the live result within noise.
* v3 (fixed): **−936** — same hostile slice, 5× smaller loss.

## 4. Fixes in trader_r3_v3.py

All fixes are surgical edits to the submitted code. The structural edge
(HYDROGEL adaptive EMA with a long-run anchor — forensic H1 mean 9990.8)
is **preserved**.

| # | Change | Evidence |
|---|---|---|
| 1 | `HYDROGEL_SOFT_LIMIT`: 150 → **50** | Caps one-sided MTM loss on a hostile 1,000-t slice. Observed 80-tick drift × 50 units = −4,000 worst case vs −13,000 previously. |
| 2 | HYDROGEL **trend-adverse MAKE sizing** | If `|EMA − 10000| > 20`, halve the side that would add to losing inventory. Additional hard cap: if drift < −20 and position > soft_limit/2, halve the buy side too. |
| 3 | Drop voucher strikes with bid = 0: VEV_6000, VEV_6500 | Cannot exit longs → guaranteed slow bleed. Log: VEV_6500 alone lost −150. |
| 4 | Drop VEV_4000 (deep-ITM) | Delta ≈ 1 → pure underlying exposure, no option edge. Log: lost −1,567. |
| 5 | `VOUCHER_SOFT_LIMIT`: 150 → **40** | Smile model extrapolation to live TTE is unreliable; keep surviving strikes VEV_5400 and VEV_5500 at bounded size. |
| 6 | `VOUCHER_TAKE_MARGIN`: 1.0 → **2.0** | Require bigger edge to cross; reduces smile-mismatch adverse selection. |

## 5. Backtest results

Full 3-day prosperity3bt (`scripts/run_r3_backtest.py trader_r3_v3.py all`,
--match-trades worse, 10,000 ticks/day):

| Day | HYDROGEL | VEV_5400 | VEV_5500 | Total |
|---|---:|---:|---:|---:|
| 0 | 6,369 | 240 | 20 | **6,629** |
| 1 | 10,752 | −40 | 20 | **10,732** |
| 2 | 8,772 | −160 | −40 | **8,572** |
| **Σ** | **25,893** | 40 | 0 | **25,933** |

* **Every day positive**, min +6,629.
* v1 scored +86,442 — we traded 70% of the backtest edge for 5× reduction
  in hostile-slice loss. Correct trade given the live evidence.

1,000-tick platform-slice replays (hostile conditions):

| Slice | v1 (submitted) | v3 |
|---|---:|---:|
| Day 2, ts 0–99,900 (= log 365182 window) | −4,381 | **−936** |
| Day 2, ts 0–199,900 | +10,403† | **+907** |
| Day 1, ts 0–99,900 | −2,105† | **−1,265** |

† v1 numbers on alternate slices computed for reference; v3's 2,000-tick day-2 turns positive while v1 only profits through lottery-sized positions.

## 6. Where this could still fail live

* **Ambient drift > 80 ticks in < 500 ticks.** If the live session starts
  with a price crash larger than day-2's, even our 50-lot cap will wear a
  bounded loss (−50 × drift) on HYDROGEL. The trend-adverse sizing makes
  us lean into reversion; if reversion doesn't happen this session, we
  close negative by ~1–2k on HYDROGEL.
* **Voucher regime shift.** VEV_5400 and VEV_5500 are kept but at
  soft_limit=40. Worst-case on a toxic regime ~ 40 × (observed edge) ~
  −400 per strike. Bounded.
* **Platform runs a completely different day.** If the platform day
  doesn't resemble days 0–2 at all, HYDROGEL EMA anchoring at 10000 might
  mis-fit. Forensic H1 gives us mean 9990.81 across 3 days with std 32;
  regime stability is good.

## 7. One-parameter dial if given one more iteration

`HYDROGEL_TREND_DRIFT` (currently 20). This is the drift-from-anchor
threshold that triggers our trend-adverse sizing. If set **tighter** (say
12), we pull size faster on mild drifts — reduces the hostile-slice loss
further at the cost of some benign-drift edge. If set **wider** (35), we
keep quoting through larger drifts and collect more mean-reversion PnL
on days like 1 and 2 — at the cost of hostile-slice exposure. A grid
search over {10, 15, 20, 25, 30, 40} across all 3 days + the 1,000-t
replays would pick the value that Pareto-dominates both dimensions.
