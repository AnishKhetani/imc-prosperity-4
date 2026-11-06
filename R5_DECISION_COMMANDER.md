# R5 DECISION COMMANDER PLAYBOOK

> **Single source of truth during the live round.** Open this on a second monitor.
> Every decision is pre-defined here. **No improvisation.**

R5 has **NO LIVE LEADERBOARD**. Every signal in this playbook is derived from
your own logs, your own positions, and the live order book. There is no
competitor information available during the round.

Round length: **N = 1,000,000 timestamps** (10,000 ticks at 100 ms cadence).
Position limit: **10 per product, 50 products** — enforced by `_clip_orders`.

---

## 0. PRE-FLIGHT (T-30 minutes before round start)

| # | Check | Command / criterion | Recovery if fail |
|---|---|---|---|
| 1 | Variants present | `Get-ChildItem variants/built/trader_V*.py` returns 6 files | `python variants/build.py` |
| 2 | Variants validate | `python variants/validate_variants.py --sims 5 --ticks 500` ends `TOTAL BREACHES: 0  (PASS)` | Stop. Diagnose. Do not deploy. |
| 3 | Stress harness | `python r5_stress_harness.py --sims 5 --ticks 500` shows `BREACHES: 0` across 6 scenarios | Stop. Diagnose. |
| 4 | Monitor renders | `python monitor.py --prices round_data\ROUND_5\prices_round_5_day_2.csv --once --no-color` shows all 5 panels | Reinstall Python stdlib only — no third-party deps required. |
| 5 | Liquidator imports | `python liquidate.py` prints 3 sections of test output | Re-pull file. |
| 6 | Submit BASE | upload `submission.py` (or `variants/built/CONTINGENCY_BASE.py` — identical) | — |
| 7 | live/ folder | `mkdir live` and `mkdir snapshots` | — |
| 8 | Decision log | `New-Item snapshots/decision_log.md` | — |

---

## 1. PART A — REAL-TIME MONITOR

Launch in a dedicated terminal at round start:

```powershell
python monitor.py --dir live\ --my-team "<TEAM>" --refresh 30
```

Monitor refreshes every 30 seconds. Five panels (top to bottom):

1. **PnL Tracker** — total + per-strategy + velocity (50/200/500-tick) + MC base-case overlay (`MC_FINAL_MEAN=970, MC_FINAL_STD=743`). Verdict: `BEHIND CI` / `WITHIN CI` / `AHEAD CI`.
2. **Strategy Health** — per-component PnL, status `HEALTHY|DEGRADED|TRIPPED`, last-fill staleness.
3. **Position & Risk** — per-product position vs limit (green<70%, amber 70-90%, red>90%), aggregate exposure, 1-sigma adverse-move PnL impact.
4. **Order Book Health** — observed spread vs Step-1 historical median, depth vs 5th-pct depth, mid prices.
5. **Anomaly Alert Feed** — coloured `BLOCKER`/`WARNING` lines, never suppressed; persists across refreshes.

Monitor degrades gracefully — every panel renders `NO DATA` if its inputs are empty. Never crashes.

**Source files** for `live/`: download from IMC platform's *Live algorithm logs* page periodically (every 5–10 min) and save as `live/prices_<HH><MM>.csv` and `live/trades_<HH><MM>.csv`. The monitor's `--dir` mode auto-picks the newest of each by mtime.

**Manual fallback if monitor crashes** — track these by hand every 10 min:
- Total PnL  vs MC expected at this tick (`970 * tick/10000 ± 743 * sqrt(tick/10000)`)
- Per-strategy PnL (sum of `profit_and_loss` over each strategy's products in the latest prices CSV)
- Largest absolute position
- Spread on PEBBLES_M (P2 health proxy) and SNACKPACK_CHOCOLATE (S1S2 proxy)

---

## 2. PART B — TRIP-WIRES (per strategy component)

All thresholds derived from Step-4 Monte Carlo. A trip-wire that fires in baseline is miscalibrated; a trip-wire that only fires after ruin is useless.

### 2.1 P2 — PEBBLES synthetic-fair MM

| Field | Value |
|---|---|
| **Expected signature (first 20%)** | mean +20 to +200; baseline 1000-tick MC mean +97 std 235. P2 is a *slow starter* — first 200 ticks frequently flat. Do NOT trip before tick 1500. |
| **Trip 1** | P2 strategy MTM `< -100` by tick 1500 |
| **Trip 2** | PEBBLES residual rolling-200 std `> 8.0` (vs base 2.8) |
| **Trip 3** | Zero P2 fills for >=500 ticks after tick 500 |
| **Diagnosis A — VARIANCE** | MC base case at tick 1500: 5%-CI lower bound = `-110`. If P2 PnL is in [-110, base], no action. |
| **Diagnosis B — MODEL BREAK** | Sum of 5 PEBBLES mids drifts > 50 from 50,000 *and stays*. Compute manually from the `mid_price` column in latest prices CSV. |
| **Diagnosis C — ADVERSARIAL** | Our P2 takes fill instantly but post-fill 50-tick PnL is negative on >=10 of last 15 fills. Confirms picking-off behaviour. |
| **Variant** | A => none; B => `trader_V1_no_insider`; C => `trader_V3_adversarial` |

### 2.2 S1+S2 — SNACK CHOC+VAN pair stat-arb

| Field | Value |
|---|---|
| **Expected signature** | Mean -20 std 33 / 1000 ticks. Inventory builds over first 200-500 ticks when |z|>1.5; do NOT trip before tick 1500. |
| **Trip 1** | S1+S2 MTM `< -100` by tick 1500 |
| **Trip 2** | `|z| > 2.0` for 500 consecutive ticks without crossing 0.5 |
| **Trip 3** | CHOC+VAN sum drifts > 250 from 19,940 for 1000 ticks |
| **Diagnosis A — VARIANCE** | |z| oscillates +/-3 with mean-reversion within 500 ticks: hold. |
| **Diagnosis B — MODEL BREAK** | Empirical CHOC+VAN mean over rolling 1000 ticks != 19,940 +/- 50 — cointegration broken. |
| **Diagnosis C — ADVERSARIAL** | Pair entries fill at z>1.5 but post-fill 100-tick z keeps widening on >=8 of last 12 entries. |
| **Variant** | A => none; B => `trader_V1_no_insider`; C => `trader_V3_adversarial` |

### 2.3 S2 — SNACK PISTACHIO/RASPBERRY/STRAWBERRY wide MM

| Field | Value |
|---|---|
| **Expected signature** | Mean -6 std 26 / 1000 ticks. Spread capture dominates; near-zero start. |
| **Trip 1** | S2 MTM `< -100` by tick 2000 |
| **Trip 2** | best_bid-best_ask on any leg <= 4 (vs ~13 base) for 200 ticks |
| **Trip 3** | Position pinned at +/-10 on any leg for 500 ticks |
| **Diagnosis A — VARIANCE** | Spread back >= 8 within 500 ticks — hold. |
| **Diagnosis B — MODEL BREAK** | Permanent spread compression — wide-MM premise gone. |
| **Diagnosis C — ADVERSARIAL** | Position-pin: someone is exhausting our quotes one-side. |
| **Variant** | A => none; B => `trader_V2_high_vol`; C => `trader_V3_adversarial` |

### 2.4 R2 — ROBOT_DISHES / ROBOT_IRONING tick-fade

| Field | Value |
|---|---|
| **Expected signature** | Mean ~0, designed noise-bounded. |
| **Trip 1** | R2 MTM `< -100` by tick 1500 |
| **Trip 2** | Lag-1 mid ACF on rolling 200 ticks > +0.05 on either leg (regime-flip from negative ACF) |
| **Trip 3** | Position pinned at +/-`R2_INVENTORY_CAP` (4) for 500 ticks |
| **Diagnosis A — VARIANCE** | ACF still negative, MTM oscillates +/-50 — hold. |
| **Diagnosis B — MODEL BREAK** | ACF positive AND mid drifts in direction of held inventory (trend regime). |
| **Diagnosis C — ADVERSARIAL** | Every fill followed by >=2 ticks against us. |
| **Variant** | A => none; B => `trader_V2_high_vol`; C => `trader_V3_adversarial` |

### 2.5 M1 — Wide+deep MM (GALAXY_SOUNDS / UV_VISOR / OXYGEN_SHAKE / PANEL)

| Field | Value |
|---|---|
| **Expected signature** | Largest contributor (mean +314 / 1000 ticks). |
| **Trip 1** | M1 MTM `< -300` by tick 2000 |
| **Trip 2** | Spread halves on >=5 of 20 M1 products within 500 ticks |
| **Trip 3** | Sum of |M1 positions| > 100 |
| **Diagnosis A — VARIANCE** | One product wide but rest normal — hold. |
| **Diagnosis B — MODEL BREAK** | Multiple-product spread compression — vol regime shift. |
| **Diagnosis C — ADVERSARIAL** | Multiple products show pin + adverse-fill pattern. |
| **Variant** | A => none; B => `trader_V2_high_vol`; C => `trader_V3_adversarial` |

### 2.6 M3 — Tight MM (MICROCHIP / SLEEP_POD / TRANSLATOR / non-DI ROBOTs)

| Field | Value |
|---|---|
| **Expected signature** | Near-zero mean (std 69 / 1000 ticks); designed to give back small adverse-selection cost in exchange for inventory option value. |
| **Trip 1** | M3 MTM `< -200` by tick 3000 |
| **Trip 2** | MICROCHIP top-of-book depth < 5 for 200 ticks (vs ~16 base) |
| **Trip 3** | Position on any single M3 product hits +/-10 for 300 ticks |
| **Diagnosis A — VARIANCE** | Within +/- 2 sigma — hold. |
| **Diagnosis B — MODEL BREAK** | Book thinning across multiple M3 products. |
| **Diagnosis C — ADVERSARIAL** | Single product targeted with picking-off pattern. |
| **Variant** | A => none; B => `trader_V5_signal_loss`; C => `trader_V3_adversarial` |

### 2.7 Global

| Trigger | Variant |
|---|---|
| Total MTM `< -400` | `trader_V4_inventory_trap` if positions > +/-5 on >=3 products, else `trader_V2_high_vol` |
| Total MTM `< -700` | `trader_V6_emergency_brake` (one-way door) |
| >=2 strategies TRIPPED before 50% of round | `trader_V5_signal_loss` |
| Both P2 and S1+S2 TRIPPED at any tick | `trader_V1_no_insider` |
| Spread > 2x median on >=10 products | `trader_V2_high_vol` |
| Adversarial diagnosis confirmed on any strategy | `trader_V3_adversarial` |

---

## 3. PART C — CONTINGENCY VARIANT REGISTRY

All six variants live under [variants/built/](variants/built/), generated by [variants/build.py](variants/build.py). Each is **self-contained, single-file, ready to upload**. Validation results: see end of section.

### V1 — `trader_V1_no_insider`

**Trigger**: Both P2 AND S1+S2 underperforming MC base by tick 2000 (Diagnosis B on either strategy that depended on insider/anomaly capture).
**Assumed market**: All informed-participant signals have gone stale; baskets and pairs no longer mean-revert.

**Parameter delta from BASE**:
- `ENABLE_P2 = False` — disable PEBBLES basket alpha (anomaly arbitraged out).
- `ENABLE_S1S2 = False` — disable pair stat-arb (cointegration broken).
- `ENABLE_R2 = False` — disable tick-fade (negative-ACF assumption is in same family).
- `MM_PASSIVE_SIZE = 2` (was 3) — halve passive size to bound adverse-selection cost when alphas are gone.
- `PRODUCT_HALF_SPREAD[k] += 2` for all k — widen all quotes by 2 ticks.

**MC validation** (no_insider scenario, 5 sims x 500 ticks): mean **+19**, std 44, max DD 82, breaches 0. Better than passive (constant 0). **PASS**.
**Reversion**: P2 PnL recovers to +50 sustained for 500 ticks AND PEBBLES sum-residual std < 4 sustained. (Stay deployed otherwise.)
**Escalation**: PnL drops further -200 -> `trader_V5_signal_loss`. Global DD < -700 -> `trader_V6_emergency_brake`.

### V2 — `trader_V2_high_vol`

**Trigger**: Spread > 2x median on >=10 products, OR rolling 200-tick mid-vol on any product > 2x its baseline std (Diagnosis B on any strategy).
**Assumed market**: Volatility regime has shifted; spreads wide, sizes must shrink.

**Parameter delta from BASE**:
- `MM_PASSIVE_SIZE = 1` (was 3).
- `MM_TAKE_SIZE = 4` (was 8) — halve.
- `P2_PASSIVE_SIZE = 1`, `P2_TAKE_SIZE = 4` — halve.
- `PAIR_TAKE_SIZE = 3` (was 6) — halve.
- `R2_INVENTORY_CAP = 2` (was 4) — half.
- `EMERGENCY_BRAKE_PNL = -120` (was -200) — fire 40% earlier.
- `GLOBAL_DD_BRAKE = -500` (was -800) — fire 37% earlier.
- `PEBBLES_TAKE_EDGE = 8.0` (was 4.0) — require 2x edge to take.
- `SNACK_PAIR_ENTRY_Z = 2.5` (was 1.5) — require stronger pair signal.
- `PRODUCT_HALF_SPREAD[k] += 3` — widen quotes 3 ticks.

**MC validation** (regime_shift, 5x500): mean **-99**, std 188, max DD 230, breaches 0. Contains losses while still earning. **PASS**.
**Reversion**: spread > 2x median on < 3 products for 1000 consecutive ticks AND velocity > 0 over 500-tick window.
**Escalation**: total MTM < -300 -> `trader_V4_inventory_trap`. < -700 -> `trader_V6_emergency_brake`.

### V3 — `trader_V3_adversarial`

**Trigger**: Diagnosis C confirmed on any single strategy (passive orders picked off within 1-2 ticks; post-fill PnL negative on >=10 of last 15 fills).
**Assumed market**: A specific competitor is reacting to our order flow; our passive quotes are toxic.

**Parameter delta from BASE — derived from first principles**:

If every passive order is adversely selected, the only safe quote is no quote:
- `MM_PASSIVE_SIZE = 0` — disable all passive MM.
- `P2_PASSIVE_SIZE = 0` — disable P2 passive.
- `MM_TAKE_SIZE = 2` — minimum take size to bound per-fill loss.
- `P2_TAKE_SIZE = 2`, `PAIR_TAKE_SIZE = 2` — minimum.
- `PEBBLES_TAKE_EDGE = 12.0` — require 3x base edge to act (only takes when edge is so large adverse selection cannot eat it).
- `SNACK_PAIR_ENTRY_Z = 3.0` — require 2x base z.
- `ENABLE_R2 = False` — R2 fade is the most exposed strategy to picking-off.
- `EMERGENCY_BRAKE_PNL = -100` — tighten 50%.
- `PRODUCT_HALF_SPREAD[k] += 5` — sentinel hardening so any residual passive code path posts so far from mid it cannot be hit at parity.

**Why minimum-size take-only**: max safe quote size when every fill is adverse = `edge / per_fill_loss = 12 / 6 ~= 2 lots` per take. Keeps per-tick loss <= 6 ticks/share x 2 = 12 PnL units worst-case.

**MC validation** (regime_shift as proxy, 5x500): mean **+33**, std 51, max DD 24, breaches 0. **Best risk-adjusted variant in the registry**. PASS — better than passive.
**Reversion**: zero adverse-fill events in 1000 consecutive ticks AND velocity > 0 -> revert to BASE.
**Escalation**: continued losses < -200 -> `trader_V5_signal_loss`. < -700 -> `trader_V6_emergency_brake`.

### V4 — `trader_V4_inventory_trap`

**Trigger**: |position| > 5 on >=3 products simultaneously AND last fill on those products > 100 ticks ago (offload not coming).
**Assumed market**: Liquidity has dried up at our price levels; we cannot offload via passive quotes.

**Parameter delta from BASE**:
- `ENABLE_P2 = False`, `ENABLE_S1S2 = False`, `ENABLE_R2 = False` — stop adding directional risk.
- `MM_PASSIVE_SIZE = 1`, `MM_TAKE_SIZE = 1` — minimum size to keep liquidity engagement.
- `EMERGENCY_BRAKE_PNL = -100` — tight per-strategy brake.
- `GLOBAL_DD_BRAKE = -400` — fire global liquidation early.
- `_clip_orders` monkey-patch: on any product with `|pos| > 5`, drop any order whose sign would push position further from zero. **Forces every order to be inventory-reducing once we are at 50%+ of limit.**

**MC validation** (limit_stress, 5x500): mean **+198,814** — correctly flushes preloaded inventory; std 3,773; max DD 4,408; breaches 0. **PASS** — actively unwinds traps.
**Reversion**: |position| <= 3 on every product for 500 ticks -> revert to BASE.
**Escalation**: total MTM < -700 -> `trader_V6_emergency_brake`.

### V5 — `trader_V5_signal_loss`

**Trigger**: >=2 strategies TRIPPED simultaneously, OR monitor cannot read book data on >=5 products. Last active-trading variant before brake.
**Assumed market**: Multiple signal failures; we cannot tell which assumption is broken; survive only via baseline MM.

**Parameter delta from BASE**:
- `ENABLE_P2 = False`, `ENABLE_S1S2 = False`, `ENABLE_R2 = False` — disable everything alpha-style.
- `MM_PASSIVE_SIZE = 1`, `MM_TAKE_SIZE = 2` — minimum size.
- `EMERGENCY_BRAKE_PNL = -80`, `GLOBAL_DD_BRAKE = -350` — tightest brakes short of full liquidation.
- `PRODUCT_HALF_SPREAD[k] += 4` — maximum spread widening.

**MC validation** (no_insider, 5x500): mean **+1,144**, std 2,270, max DD 152, breaches 0. **PASS** — passive MM still earns when alphas are gone.
**Reversion**: any one tripped strategy clears AND velocity > 0 for 500 ticks -> consider reverting to V1 or V2 (not BASE).
**Escalation**: total MTM < -350 -> `trader_V6_emergency_brake`.

### V6 — `trader_V6_emergency_brake`

**Trigger**: Total drawdown < -700 OR single-tick swing < -300 OR >=2 active variants have been deployed and a third trip-wire fires.
**Assumed market**: Conditions are unsalvageable for the remainder of the round.

**Parameter delta from BASE**:
- All `ENABLE_*` flags `= False` — every strategy off.
- `GLOBAL_DD_BRAKE = 999999` — sentinel; the natural brake never fires because we force it manually.
- `_load_state` monkey-patch — every tick `global_brake = True`, which routes the engine through the base class's Level-3 hard liquidation path: cross spread to flatten everything, post no MM quotes.

**MC validation** (limit_stress, 5x500): mean **+197,103** — correctly liquidates preloaded inventory under stress, breaches 0. **PASS**.
**Reversion**: **NEVER**. One-way door. Once deployed, runs to round end.
**Escalation**: none — terminal state.

### Validation summary

```
trader_V1_no_insider         no_insider                 +19         44      0
trader_V2_high_vol           regime_shift               -99        188      0
trader_V3_adversarial        regime_shift               +33         51      0
trader_V4_inventory_trap     limit_stress          +198,814      3,773      0
trader_V5_signal_loss        no_insider              +1,144      2,270      0
trader_V6_emergency_brake    limit_stress          +197,103        575      0
TOTAL BREACHES: 0  (PASS)
```

### Deployment procedure (live)

1. `Copy-Item variants\built\trader_V<N>_<role>.py submission_live.py`
2. Upload `submission_live.py` to the IMC platform.
3. Append one stanza to [snapshots/decision_log.md](snapshots/decision_log.md):
```
ts <NNNNNN> :: trader_V<N>_<role>
diagnosis: A | B | C
trip-wire: <description>
total_PnL at deploy: <value>
strategy PnLs: P2=.. S1S2=.. S2=.. R2=.. M1=.. M3=..
```
4. Within next 30 sec the variant is live; monitor will show updated panels.

**Reversion rule**: never revert under pressure. The only auto-reversion conditions are stated per-variant above. Default = stay deployed.

---

## 4. PART D — END-GAME POSTURE

### 4.1 Forced settlement

R5 has **no forced end-of-round settlement formula** for any product (unlike R3 vouchers). Cash settlement is at last mid-price for any non-zero residual position. There is no convergence trade; do not chase one.

### 4.2 Inventory zero-out (timestamp triggers)

Liquidation function: [liquidate.py](liquidate.py).

Derivation (Step-1 EDA + Step-4 worst-case fill rate):
- 5th-pct top-of-book depth across R5 products: **4 lots**
- Conservative fill rate per tick: **2 lots** (50% of 5th-pct)
- Worst-case offload of 10 units: **5 ticks** per product
- 5x safety margin: **25 ticks** per product
- 50 products possibly held -> 1,250 ticks worst-case (12.5% of round)

Two trigger times encoded in `liquidate.py`:
- `LIQ_START_TS = 875,000` (87.5%) — late-bound. Only required if positions are unusually large at that point.
- **Decision Commander default trigger: `850,000` (85%)** — one tick of CP3 grace, then mandatory liquidation pacing begins.

**Drop-in usage from any variant** (append to your variant's `Trader.run()` method just before the `return result, conversions, traderData` line):

```python
from liquidate import build_liquidation_orders
extra = build_liquidation_orders(state.position, state.order_depths,
                                 state.timestamp,
                                 start_ts=850_000, end_ts=999_900)
for sym, lst in extra.items():
    result.setdefault(sym, []).extend(lst)
# base Trader._clip_orders still runs and bounds breaches
```

### 4.3 Variance budget at 85% (tick 8500)

Read total PnL from monitor and apply Step-4 MC reference at this tick (mean `970 * 0.85 = +824.5`, std `743 * sqrt(0.85) ~ +685`).

| Live PnL vs MC at tick 8500 | Posture | Action |
|---|---|---|
| > +1,510 (mean + 1σ) | **AHEAD** | Deploy `trader_V5_signal_loss` for the final 1500 ticks. Lock in. |
| within [+140, +1,510] | **ON TRACK** | Stay on current variant. |
| < +140 (mean - 1σ) | **BEHIND** | Stay on BASE. Do **NOT** escalate to defensive. Maintain `MM_TAKE_SIZE` and `PEBBLES_TAKE_EDGE` at base. **Hard cap**: incremental loss from this point capped at -150 PnL. If incremental loss reaches -150 -> switch to `trader_V5_signal_loss`. |
| < -785 (mean - 2σ) | **MATERIALLY BEHIND** | Maximum-EV swing: stay on BASE; the base parameters give widest passive capture and tail-EV strategies still positive in expectation. Hard cap on additional loss: -150 from current. After that, V5. |

The MATERIALLY BEHIND case is the only case in the round where escalating into defensive is *worse than* holding. Defensive variants (V2/V5) reduce variance, which is precisely the wrong direction when we need a recovery distribution.

---

## 5. PART E — DECISION TREE BY TIMELINE

> All checkpoints fire on the monitor tick reaching the threshold. Read the dashboard, then walk the tree top-down; deploy on the **first** matching branch.

### 5.1 ROUND START (timestamp 0)

```
1. Submit submission.py (== CONTINGENCY_BASE.py).
2. Launch monitor:
       python monitor.py --dir live\ --my-team "<TEAM>" --refresh 30
3. Wait for first refresh; confirm all 5 panels render with data.
4. If any panel shows NO DATA after 2 refreshes:
     - Re-check live/ folder has prices_*.csv
     - Re-run with --once to surface the error
     - If still NO DATA: switch to manual fallback (Section 1)
5. Confirm anomaly feed shows "no alerts."
6. Append to decision_log.md: "ts 0 :: BASE deployed; monitor live"
```

### 5.2 CHECKPOINT 1 — tick 2000 (20%)

For each strategy component, read PnL + status from Strategy Health panel.

```
For each component s in {P2, S1S2, S2, R2, M1, M3}:
    if status[s] == HEALTHY: continue
    if status[s] == DEGRADED:
        log "CP1: <s> degraded, monitoring"
        continue
    if status[s] == TRIPPED:
        run diagnosis triangle (Part B section for s):
            A (variance):    log "CP1: <s> variance, no action"
            B (model break): deploy variant per Part B mapping
            C (adversarial): deploy trader_V3_adversarial

if total_PnL <= -400:    deploy trader_V4_inventory_trap (or V2 if no inventory issue)
if total_PnL <= -700:    deploy trader_V6_emergency_brake (one-way door)
if no actions taken:     log "CP1 CLEAR"
```

### 5.3 CHECKPOINT 2 — tick 5000 (50%)

Same structure as CP1, plus:

```
Read Order Book Health panel.
if >=10 products show spread > 2x median:
    deploy trader_V2_high_vol  (regime shift confirmed)

if >=2 strategies are TRIPPED:
    deploy trader_V5_signal_loss

Re-evaluate trip-wire thresholds with mid-round MC reference:
    expected_PnL_at_tick_5000 = 970 * 0.5 = +485
    1-sigma                   = 743 * sqrt(0.5) ~ +/-525
    if total_PnL < -40:  warn (below 1-sigma lower bound)
    if total_PnL < -565: deploy trader_V2_high_vol
                         (we are below 2-sigma lower bound: 485 - 2*525)
```

### 5.4 CHECKPOINT 3 — tick 8500 (85%)

Execute Part D variance budget exactly. Then:

```
Check inventory zero-out:
    if any |position| >= 6: import liquidate; activate liquidation orders
        even if current variant disagrees, liquidation orders are appended
        (append snippet from Section 4.2 to your live submission file)

If current_timestamp >= 875_000 (87.5%):
    INVOKE liquidate.build_liquidation_orders REGARDLESS OF VARIANT.
    This overrides any other strategic instruction.
```

### 5.5 FINAL TIMESTAMPS — tick 9000-10000

```
NO new strategic decisions. Execution only.
Monitor:
    - liquidation fills coming in
    - any single-tick swing > +/- 100 -> log

If a liquidation order on a product is not filling for 50 ticks:
    Escalate aggression in liquidate.py call:
        replace start_ts=850_000 with start_ts=current_ts - 100
        so progress jumps to >75%, forcing best_bid (sell) / best_ask (buy)
    If still unfilled at 200 ticks: accept best_bid - 1 / best_ask + 1
    (cross by 1 tick); Trader._clip_orders bounds breach risk to zero.

Round end at ts 999_900. Engine cash-settles residual positions at last mid.
No further action. Save logs.
```

### 5.6 HARD OVERRIDES (apply regardless of any other signal)

1. **Never manually cancel V6_emergency_brake once deployed** — one-way door, permanent for the round.
2. **Never deploy a new variant after tick 9500** (final 5%) — insufficient time to observe/respond.
3. **Never exceed POSITION_LIMIT** — `_clip_orders` enforces; do not edit or bypass.
4. **Never disable `_clip_orders`** — single defensive boundary against breach count.
5. **Never deploy a variant not present in `variants/built/`** — no hand-edited submissions. Regenerate via `python variants/build.py` if a parameter must change.
6. **Never deploy two variant changes within 500 ticks of each other** — whipsaw cost dominates information value.
7. **Never run with `DEBUG = True`** in any variant — printing stalls the engine.
8. **Never edit `submission.py` during the round** — it is the read-only reference.
9. **Never average down on a losing position** — the rules do not reward this; `_clip_orders` will reject the orders anyway.
10. **If monitor crashes**: switch to manual fallback (Section 1). Do NOT abort. Do NOT deploy reactively without metrics — wait for the next manual reading.

---

## 6. ARTIFACT INDEX

| Artifact | Path | Purpose |
|---|---|---|
| Base trader (read-only) | [submission.py](submission.py) | Single source of truth for parameters |
| Variant generator | [variants/build.py](variants/build.py) | Regenerates V1-V6 + 9 named contingencies from base |
| Variant validator | [variants/validate_variants.py](variants/validate_variants.py) | MC-validates all 15 variants in their target scenarios |
| V1 — no_insider | [variants/built/trader_V1_no_insider.py](variants/built/trader_V1_no_insider.py) | All alphas dead, MM-only |
| V2 — high_vol | [variants/built/trader_V2_high_vol.py](variants/built/trader_V2_high_vol.py) | Vol regime shift, halve sizes, widen spreads |
| V3 — adversarial | [variants/built/trader_V3_adversarial.py](variants/built/trader_V3_adversarial.py) | Take-only, minimum size, max edge requirements |
| V4 — inventory_trap | [variants/built/trader_V4_inventory_trap.py](variants/built/trader_V4_inventory_trap.py) | Inventory-bleed clipper, no new directional risk |
| V5 — signal_loss | [variants/built/trader_V5_signal_loss.py](variants/built/trader_V5_signal_loss.py) | Pure MM, minimum size, max spread |
| V6 — emergency_brake | [variants/built/trader_V6_emergency_brake.py](variants/built/trader_V6_emergency_brake.py) | One-way liquidation; everything off |
| Live monitor | [monitor.py](monitor.py) | Refreshing 5-panel terminal dashboard |
| Liquidator | [liquidate.py](liquidate.py) | Drop-in `build_liquidation_orders()` function |
| Decision log (live) | snapshots/decision_log.md | One stanza per variant deploy during round |

---

**End of playbook.**
If a situation arises that is not covered above, the answer is: **stay on the
current variant**. The cost of an unforeseen-but-not-catastrophic deviation is
bounded by `EMERGENCY_BRAKE_PNL` and `GLOBAL_DD_BRAKE` in the active variant.
The cost of an off-script edit is unbounded.
