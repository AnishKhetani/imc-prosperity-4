"""
In-process combinatorial tester — avoids subprocess entirely.
Directly patches strategy class attributes between backtest runs.
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

# Save original act methods
_orig_tomatoes_act = TomatoesStrategy.act

FLAG_NAMES = ["EM_NO_SKEW", "STALE_GUARD", "WIND_DOWN", "TOM_SKEW_005", "IMB_ZERO", "NO_DEPTH_CTR"]

OUTFILE = Path(__file__).parent / "combo_results_final.txt"


def make_patched_tomatoes_act(stale_guard, wind_down):
    """Create a patched act() method with optional stale guard and wind-down."""
    orig = _orig_tomatoes_act

    def patched_act(self, state):
        from datamodel import Order
        position = self.get_position(state)
        orders = []

        mid = self.mid_price(state)
        if mid is None:
            return []

        self.price_history.append(mid)
        self.ema = self._compute_ema(mid)

        imb = self.l1_imbalance(state)
        adjusted_fair = self.ema + imb * self.IMB_WEIGHT - position * 0.05
        fair = round(adjusted_fair)

        # STALE_GUARD: clamp fair to within 2 of current mid
        if stale_guard:
            int_mid = int(mid)
            if fair > int_mid + 2:
                fair = int_mid + 2
            elif fair < int_mid - 2:
                fair = int_mid - 2

        depth_imb = self.depth_imbalance(state)

        take_buys, position = self.take_best_asks(state, position, fair - self.TAKE_EDGE)
        orders.extend(take_buys)
        take_sells, position = self.take_best_bids(state, position, fair + self.TAKE_EDGE)
        orders.extend(take_sells)

        bid_price, ask_price = self._make_prices(fair, position, depth_imb)

        pos_ratio = position / self.position_limit
        remaining_buy = self.max_buy_qty(position)
        remaining_sell = self.max_sell_qty(position)
        buy_qty, sell_qty = self._asymmetric_size(remaining_buy, remaining_sell, pos_ratio)

        # WIND_DOWN: end-of-day position reduction
        if wind_down and state.timestamp >= 180000:
            if position > 5:
                buy_qty = max(1, buy_qty // 4)
                ask_price -= 1
            elif position < -5:
                sell_qty = max(1, sell_qty // 4)
                bid_price += 1

        buy_order = self.buy(bid_price, buy_qty, position) if buy_qty > 0 else None
        if buy_order:
            orders.append(buy_order)
        sell_order = self.sell(ask_price, sell_qty, position) if sell_qty > 0 else None
        if sell_order:
            orders.append(sell_order)
        return orders

    return patched_act


def apply_combo(flags):
    """Apply a combination of changes by patching class attributes."""
    em_no_skew, stale_guard, wind_down, tom_skew_005, imb_zero, no_depth_ctr = flags

    # Patch EMERALDS
    EmeraldsStrategy.SKEW_THRESHOLD = 1.0 if em_no_skew else 0.3
    EmeraldsStrategy.HEAVY_THRESHOLD = 1.0 if em_no_skew else 0.6

    # Patch TOMATOES params
    TomatoesStrategy.SKEW_THRESHOLD = 0.05 if tom_skew_005 else 0.15
    TomatoesStrategy.IMB_WEIGHT = 0.0 if imb_zero else 0.5
    TomatoesStrategy.DEPTH_CONTRARIAN = 0 if no_depth_ctr else 1

    # Patch TOMATOES act method for behavioral changes
    if stale_guard or wind_down:
        TomatoesStrategy.act = make_patched_tomatoes_act(stale_guard, wind_down)
    else:
        TomatoesStrategy.act = _orig_tomatoes_act


def run_backtest_combo():
    """Run a backtest and return PnL breakdown."""
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
            row.columns[-1] for row in reversed(result.activity_logs) if row.timestamp == last_ts
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
    all_combos = list(itertools.product([False, True], repeat=6))
    total = len(all_combos)

    with open(OUTFILE, "w", encoding="utf-8") as f:
        f.write("flags,changes,total,day2,day1,em_d2,em_d1,tom_d2,tom_d1\n")

        results_data = []
        start_time = time.time()

        for i, flags in enumerate(all_combos):
            elapsed = time.time() - start_time
            eta = (elapsed / (i + 1)) * (total - i - 1) if i > 0 else 0

            flag_str = "".join("1" if fl else "0" for fl in flags)
            active = [name for name, on in zip(FLAG_NAMES, flags) if on]
            active_str = "+".join(active) if active else "BASELINE"

            try:
                apply_combo(flags)
                r = run_backtest_combo()
                results_data.append((flags, r))

                line = f"[{i+1:2d}/{total}] {flag_str} {active_str:50s} Total={r['total']:>10,.0f}  D-2={r['day-2']:>8,.0f}  D-1={r['day-1']:>8,.0f}  [{eta:.0f}s]"
                print(line, flush=True)
                f.write(f"{flag_str},{active_str},{r['total']},{r['day-2']},{r['day-1']},{r['em_d2']},{r['em_d1']},{r['tom_d2']},{r['tom_d1']}\n")
                f.flush()

            except Exception as ex:
                import traceback
                err = traceback.format_exc()
                print(f"[{i+1:2d}/{total}] {flag_str} {active_str:50s} ERROR: {err}", flush=True)
                results_data.append((flags, {"total": float("nan")}))

        # Restore originals
        EmeraldsStrategy.SKEW_THRESHOLD = 0.3
        EmeraldsStrategy.HEAVY_THRESHOLD = 0.6
        TomatoesStrategy.SKEW_THRESHOLD = 0.15
        TomatoesStrategy.IMB_WEIGHT = 0.5
        TomatoesStrategy.DEPTH_CONTRARIAN = 1
        TomatoesStrategy.act = _orig_tomatoes_act

    # ── ANALYSIS ──────────────────────────────────────────
    valid = [(fl, r) for fl, r in results_data if r.get("total", float("nan")) == r.get("total", float("nan"))]
    baseline_pnl = None
    for fl, r in valid:
        if not any(fl):
            baseline_pnl = r["total"]

    valid.sort(key=lambda x: x[1]["total"], reverse=True)

    print("\n" + "=" * 120)
    print("RANKED RESULTS")
    print("=" * 120)
    print(f"{'Rk':>3}  {'Flags':6}  {'Changes':50s}  {'Total':>10}  {'D-2':>8}  {'D-1':>8}  {'EM':>8}  {'TOM':>8}  {'vs Base':>8}")
    print("-" * 120)

    for rank, (fl, r) in enumerate(valid, 1):
        flag_str = "".join("1" if f else "0" for f in fl)
        active = [name for name, on in zip(FLAG_NAMES, fl) if on]
        active_str = "+".join(active) if active else "BASELINE"
        diff = r["total"] - baseline_pnl if baseline_pnl else 0
        em_t = r.get("em_d2", 0) + r.get("em_d1", 0)
        tom_t = r.get("tom_d2", 0) + r.get("tom_d1", 0)
        marker = " <<BASE" if not any(fl) else (" ***" if rank <= 3 else "")
        print(f"{rank:3d}  {flag_str}  {active_str:50s}  {r['total']:>10,.0f}  {r.get('day-2',0):>8,.0f}  {r.get('day-1',0):>8,.0f}  {em_t:>8,.0f}  {tom_t:>8,.0f}  {diff:>+8,.0f}{marker}")

    print("\n" + "=" * 80)
    print("MARGINAL IMPACT (avg PnL when ON vs OFF across all combos)")
    print("=" * 80)
    for j, name in enumerate(FLAG_NAMES):
        on_pnls = [r["total"] for fl, r in valid if fl[j]]
        off_pnls = [r["total"] for fl, r in valid if not fl[j]]
        avg_on = sum(on_pnls) / len(on_pnls) if on_pnls else 0
        avg_off = sum(off_pnls) / len(off_pnls) if off_pnls else 0
        delta = avg_on - avg_off
        direction = "BETTER" if delta > 0 else "WORSE" if delta < 0 else "NEUTRAL"
        print(f"  {name:20s}  ON={avg_on:>10,.1f}  OFF={avg_off:>10,.1f}  delta={delta:>+8,.1f}  [{direction}]")

    print("\n" + "=" * 80)
    print("SINGLE-CHANGE vs BASELINE")
    print("=" * 80)
    for fl, r in sorted(valid, key=lambda x: x[1]["total"], reverse=True):
        if sum(fl) == 1:
            active = [name for name, on in zip(FLAG_NAMES, fl) if on][0]
            diff = r["total"] - baseline_pnl if baseline_pnl else 0
            em_t = r.get("em_d2", 0) + r.get("em_d1", 0)
            tom_t = r.get("tom_d2", 0) + r.get("tom_d1", 0)
            print(f"  {active:20s}  Total={r['total']:>10,.1f}  EM={em_t:>8,.1f}  TOM={tom_t:>8,.1f}  delta={diff:>+8,.1f}")
    if baseline_pnl:
        print(f"  {'BASELINE':20s}  Total={baseline_pnl:>10,.1f}")

    print("\n" + "=" * 80)
    print("TOP 2-CHANGE COMBINATIONS")
    print("=" * 80)
    two = [(fl, r) for fl, r in valid if sum(fl) == 2]
    two.sort(key=lambda x: x[1]["total"], reverse=True)
    for fl, r in two[:10]:
        active = " + ".join(name for name, on in zip(FLAG_NAMES, fl) if on)
        diff = r["total"] - baseline_pnl if baseline_pnl else 0
        print(f"  {active:45s}  Total={r['total']:>10,.1f}  delta={diff:>+8,.1f}")

    elapsed_total = time.time() - start_time
    n = max(1, len(valid))
    print(f"\nDone: {len(valid)} combos in {elapsed_total:.0f}s ({elapsed_total/n:.1f}s each)")


if __name__ == "__main__":
    main()
