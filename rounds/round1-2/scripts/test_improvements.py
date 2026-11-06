"""
Test 5 structural improvements individually and in all 32 combinations.
Uses in-process class attribute patching on backtester strategies.

Changes tested (against current submission.py baseline):
  1. NO_WINDDOWN:    Remove end-of-day wind-down (ts>=180000 block)
  2. AS_PENALTY:     Avellaneda-Stoikov time-decaying inventory penalty
  3. ADAPTIVE_WIDTH: TOMATOES width adapts to observed spread
  4. EMA_10:         Longer EMA window (10 vs 5)
  5. MULTI_LEVEL:    Two-level TOMATOES quoting (60/40 split)

Baseline = current submission.py:
  - EMERALDS: SKEW=1.0, HEAVY=1.0, WIDTH=7 (no position skew)
  - TOMATOES: EMA=5, WIDTH=5, SKEW=0.15, HEAVY=0.6, IMB=0.5,
              DEPTH_CONTRARIAN=1, position*0.05 penalty, wind-down at 180000
"""

import sys
import os
import time
import itertools
from pathlib import Path

BACKTESTER_DIR = Path(__file__).parent.parent / "backtester"
sys.path.insert(0, str(BACKTESTER_DIR))
os.chdir(str(BACKTESTER_DIR))

from prosperity3bt.file_reader import FileSystemReader
from prosperity3bt.models import TradeMatchingMode
from prosperity3bt.runner import run_backtest
from prosperity3bt.data import has_day_data, LIMITS

LIMITS["EMERALDS"] = 80
LIMITS["TOMATOES"] = 80

DATA_DIR = BACKTESTER_DIR / "data" / "tutorial"
file_reader = FileSystemReader(DATA_DIR)

from strategies.emeralds import EmeraldsStrategy
from strategies.tomatoes import TomatoesStrategy

# Save original methods
_orig_tomatoes_act = TomatoesStrategy.act

FLAG_NAMES = ["NO_WINDDOWN", "AS_PENALTY", "ADAPTIVE_WIDTH", "EMA_10", "MULTI_LEVEL"]
OUTFILE = Path(__file__).parent / "improvement_results.txt"

# Backtester session: 10K ticks, timestamps 0-999900
BACKTESTER_T = 1_000_000
# Wind-down threshold: use same value as submission.py for consistency
# (On platform this is 90% through. On backtester it's 18% but that's the established baseline.)
WINDDOWN_TS = 180_000

# A-S penalty parameters
AS_GAMMA = 0.10  # calibrated so avg penalty over session = 0.05 (matching current)


def make_patched_tomatoes_act(no_winddown, as_penalty, adaptive_width, multi_level):
    """Build a patched act() that toggles structural changes.

    EMA_10 is handled via class attribute patching (EMA_WINDOW), not here.
    """
    from datamodel import Order

    def patched_act(self, state):
        position = self.get_position(state)
        orders = []

        mid = self.mid_price(state)
        if mid is None:
            return []

        self.price_history.append(mid)
        self.ema = self._compute_ema(mid)

        imb = self.l1_imbalance(state)

        # --- Inventory penalty ---
        if as_penalty:
            # Avellaneda-Stoikov: penalty decays linearly with remaining time
            remaining_frac = max(0.001, (BACKTESTER_T - state.timestamp) / BACKTESTER_T)
            inv_penalty = AS_GAMMA * remaining_frac * position
            adjusted_fair = self.ema + imb * self.IMB_WEIGHT - inv_penalty
        else:
            adjusted_fair = self.ema + imb * self.IMB_WEIGHT - position * 0.05

        fair = round(adjusted_fair)
        depth_imb = self.depth_imbalance(state)

        # --- Phase 1: Takes ---
        take_buys, position = self.take_best_asks(state, position, fair - self.TAKE_EDGE)
        orders.extend(take_buys)
        take_sells, position = self.take_best_bids(state, position, fair + self.TAKE_EDGE)
        orders.extend(take_sells)

        # --- Width ---
        if adaptive_width:
            observed_spread = self.spread(state)
            if observed_spread is not None:
                width = max(2, min(self.MAKE_WIDTH, (observed_spread - 1) // 2))
            else:
                width = self.MAKE_WIDTH
        else:
            width = self.MAKE_WIDTH

        # --- Make prices (using chosen width) ---
        bid = fair - width
        ask = fair + width

        pos_ratio = position / self.position_limit
        if pos_ratio > self.HEAVY_THRESHOLD:
            bid -= 1; ask -= 1
        elif pos_ratio > self.SKEW_THRESHOLD:
            ask -= 1
        elif pos_ratio < -self.HEAVY_THRESHOLD:
            ask += 1; bid += 1
        elif pos_ratio < -self.SKEW_THRESHOLD:
            bid += 1

        if depth_imb > 0.1:
            ask -= self.DEPTH_CONTRARIAN
        elif depth_imb < -0.1:
            bid += self.DEPTH_CONTRARIAN

        remaining_buy = self.max_buy_qty(position)
        remaining_sell = self.max_sell_qty(position)
        buy_qty, sell_qty = self._asymmetric_size(remaining_buy, remaining_sell, pos_ratio)

        # --- Wind-down (original: reduce position in last 10%) ---
        if not no_winddown and state.timestamp >= WINDDOWN_TS:
            if position > 5:
                buy_qty = max(1, buy_qty // 4)
                ask -= 1
            elif position < -5:
                sell_qty = max(1, sell_qty // 4)
                bid += 1

        # --- Quoting ---
        if multi_level:
            # Level 1: primary at bid/ask (60% size)
            # Level 2: wider at bid-3/ask+3 (40% size) for extra edge
            buy_qty1 = max(1, int(buy_qty * 0.6))
            buy_qty2 = buy_qty - buy_qty1
            sell_qty1 = max(1, int(sell_qty * 0.6))
            sell_qty2 = sell_qty - sell_qty1

            buy_order = self.buy(bid, buy_qty1, position) if buy_qty1 > 0 else None
            if buy_order:
                orders.append(buy_order)
                position += buy_order.quantity

            if buy_qty2 > 0:
                buy_order2 = self.buy(bid - 3, buy_qty2, position)
                if buy_order2:
                    orders.append(buy_order2)
                    position += buy_order2.quantity

            sell_order = self.sell(ask, sell_qty1, position) if sell_qty1 > 0 else None
            if sell_order:
                orders.append(sell_order)
                position += sell_order.quantity

            if sell_qty2 > 0:
                sell_order2 = self.sell(ask + 3, sell_qty2, position)
                if sell_order2:
                    orders.append(sell_order2)
                    position += sell_order2.quantity
        else:
            buy_order = self.buy(bid, buy_qty, position) if buy_qty > 0 else None
            if buy_order:
                orders.append(buy_order)
            sell_order = self.sell(ask, sell_qty, position) if sell_qty > 0 else None
            if sell_order:
                orders.append(sell_order)

        return orders

    return patched_act


def apply_combo(flags):
    """Apply a combination of changes by patching class attributes and methods."""
    no_winddown, as_penalty, adaptive_width, ema_10, multi_level = flags

    # EMERALDS: unchanged from baseline (SKEW=1.0, HEAVY=1.0 already set)
    EmeraldsStrategy.SKEW_THRESHOLD = 1.0
    EmeraldsStrategy.HEAVY_THRESHOLD = 1.0

    # TOMATOES: reset to baseline first
    TomatoesStrategy.SKEW_THRESHOLD = 0.15
    TomatoesStrategy.HEAVY_THRESHOLD = 0.6
    TomatoesStrategy.IMB_WEIGHT = 0.5
    TomatoesStrategy.DEPTH_CONTRARIAN = 1
    TomatoesStrategy.MAKE_WIDTH = 5
    TomatoesStrategy.TAKE_EDGE = 0

    # EMA_10: simple attribute patch
    TomatoesStrategy.EMA_WINDOW = 10 if ema_10 else 5

    # Always use patched act for consistent baseline behavior
    TomatoesStrategy.act = make_patched_tomatoes_act(
        no_winddown, as_penalty, adaptive_width, multi_level
    )


def run_backtest_combo():
    """Run backtest and return PnL breakdown."""
    from trader import Trader

    results = {}
    total = 0.0

    for day_num in [-2, -1]:
        if not has_day_data(file_reader, 0, day_num):
            continue
        trader = Trader()
        result = run_backtest(
            trader=trader,
            file_reader=file_reader,
            round_num=0,
            day_num=day_num,
            print_output=False,
            trade_matching_mode=TradeMatchingMode.all,
            no_names=True,
            show_progress_bar=False,
        )
        last_ts = result.activity_logs[-1].timestamp
        for row in reversed(result.activity_logs):
            if row.timestamp != last_ts:
                break
            product = row.columns[2]
            profit = row.columns[-1]
            results[f"{product}_day{day_num}"] = profit
            total += profit
        results[f"day{day_num}"] = sum(
            row.columns[-1]
            for row in reversed(result.activity_logs)
            if row.timestamp == last_ts
        )

    return {
        "total": total,
        "day-2": results.get("day-2", 0),
        "day-1": results.get("day-1", 0),
        "em_d2": results.get("EMERALDS_day-2", 0),
        "em_d1": results.get("EMERALDS_day-1", 0),
        "tom_d2": results.get("TOMATOES_day-2", 0),
        "tom_d1": results.get("TOMATOES_day-1", 0),
    }


def main():
    all_combos = list(itertools.product([False, True], repeat=5))
    total_combos = len(all_combos)

    print(f"Testing {total_combos} combinations of {len(FLAG_NAMES)} improvements")
    print(f"Flags: {', '.join(FLAG_NAMES)}")
    print(f"Wind-down threshold (scaled for backtester): {WINDDOWN_TS}")
    print(f"A-S gamma: {AS_GAMMA}")
    print()

    with open(OUTFILE, "w", encoding="utf-8") as f:
        f.write("flags,changes,total,day2,day1,em_d2,em_d1,tom_d2,tom_d1\n")

        results_data = []
        start_time = time.time()
        baseline_total = None

        for i, flags in enumerate(all_combos):
            elapsed = time.time() - start_time
            eta = (elapsed / (i + 1)) * (total_combos - i - 1) if i > 0 else 0

            flag_str = "".join("1" if fl else "0" for fl in flags)
            active = [name for name, on in zip(FLAG_NAMES, flags) if on]
            active_str = "+".join(active) if active else "BASELINE"

            try:
                apply_combo(flags)
                r = run_backtest_combo()
                results_data.append((flags, r))

                if baseline_total is None:
                    baseline_total = r["total"]

                delta = r["total"] - baseline_total
                delta_str = f"{'+'if delta>=0 else ''}{delta:,.0f}"

                line = (
                    f"[{i+1:2d}/{total_combos}] {flag_str} {active_str:55s} "
                    f"Total={r['total']:>10,.0f}  EM={r['em_d2']+r['em_d1']:>8,.0f}  "
                    f"TOM={r['tom_d2']+r['tom_d1']:>8,.0f}  d={delta_str:>7s}  [{eta:.0f}s]"
                )
                print(line, flush=True)
                f.write(
                    f"{flag_str},{active_str},{r['total']},{r['day-2']},{r['day-1']},"
                    f"{r['em_d2']},{r['em_d1']},{r['tom_d2']},{r['tom_d1']}\n"
                )
                f.flush()

            except Exception as ex:
                import traceback
                err = traceback.format_exc()
                print(f"[{i+1:2d}/{total_combos}] {flag_str} {active_str:55s} ERROR: {ex}")
                print(err)
                results_data.append((flags, {"total": float("nan")}))

        # Restore originals
        TomatoesStrategy.act = _orig_tomatoes_act
        TomatoesStrategy.EMA_WINDOW = 5

    # -- Analysis --------------------------------------------------
    elapsed = time.time() - start_time
    print(f"\n{'='*80}")
    print(f"Completed {total_combos} combos in {elapsed:.1f}s ({elapsed/total_combos:.1f}s/combo)")
    print(f"Results written to: {OUTFILE}")

    if baseline_total is None:
        return

    print(f"\nBaseline PnL: {baseline_total:,.0f}")
    print(f"\n{'-'*80}")
    print("INDIVIDUAL IMPACT (single flag on, all others off):")
    print(f"{'-'*80}")

    for j, name in enumerate(FLAG_NAMES):
        for flags, r in results_data:
            if flags[j] and sum(flags) == 1:
                delta = r["total"] - baseline_total
                em_total = r["em_d2"] + r["em_d1"]
                tom_total = r["tom_d2"] + r["tom_d1"]
                print(
                    f"  {name:20s}  Total={r['total']:>10,.0f}  "
                    f"d={'+' if delta>=0 else ''}{delta:>7,.0f}  "
                    f"EM={em_total:>8,.0f}  TOM={tom_total:>8,.0f}"
                )
                break

    # Find best single change
    single_changes = []
    for j, name in enumerate(FLAG_NAMES):
        for flags, r in results_data:
            if flags[j] and sum(flags) == 1:
                single_changes.append((name, r["total"] - baseline_total, r))
                break

    positive = [(n, d, r) for n, d, r in single_changes if d > 0]
    negative = [(n, d, r) for n, d, r in single_changes if d < 0]

    if positive:
        print(f"\n  + POSITIVE: {', '.join(f'{n} ({d:+,.0f})' for n,d,r in sorted(positive, key=lambda x: -x[1]))}")
    if negative:
        print(f"  - NEGATIVE: {', '.join(f'{n} ({d:+,.0f})' for n,d,r in sorted(negative, key=lambda x: x[1]))}")

    # Best overall combo
    print(f"\n{'-'*80}")
    print("TOP 5 COMBINATIONS:")
    print(f"{'-'*80}")

    ranked = sorted(results_data, key=lambda x: x[1].get("total", float("-inf")), reverse=True)
    for rank, (flags, r) in enumerate(ranked[:5], 1):
        active = [name for name, on in zip(FLAG_NAMES, flags) if on]
        active_str = "+".join(active) if active else "BASELINE"
        delta = r["total"] - baseline_total
        print(
            f"  #{rank}: {active_str:55s}  Total={r['total']:>10,.0f}  d={'+' if delta>=0 else ''}{delta:>7,.0f}"
        )

    # Marginal contribution analysis
    print(f"\n{'-'*80}")
    print("MARGINAL CONTRIBUTION (avg impact when added to other combos):")
    print(f"{'-'*80}")

    for j, name in enumerate(FLAG_NAMES):
        deltas = []
        for flags, r in results_data:
            if not flags[j]:
                # Find the combo with this flag turned on
                on_flags = list(flags)
                on_flags[j] = True
                on_flags = tuple(on_flags)
                for f2, r2 in results_data:
                    if f2 == on_flags:
                        deltas.append(r2["total"] - r["total"])
                        break
        if deltas:
            avg_delta = sum(deltas) / len(deltas)
            print(f"  {name:20s}  avg marginal: {'+' if avg_delta>=0 else ''}{avg_delta:>7,.0f}  "
                  f"(min={min(deltas):>+7,.0f}, max={max(deltas):>+7,.0f})")


if __name__ == "__main__":
    main()
