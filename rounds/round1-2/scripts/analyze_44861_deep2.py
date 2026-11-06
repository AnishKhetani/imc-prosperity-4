"""
Deep-dive analysis #2: Fill mechanics, adverse selection, and competition readiness.
"""

import json
import csv
import io
from collections import defaultdict
import math

LOG_PATH = r".\logs\44861\44861.json"
TRAIN_PRICES_D1 = r".\tutorial-round\data\TUTORIAL_ROUND_1\prices_round_0_day_-1.csv"
TRAIN_PRICES_D2 = r".\tutorial-round\data\TUTORIAL_ROUND_1\prices_round_0_day_-2.csv"


def parse_activities_log(log_str):
    reader = csv.DictReader(io.StringIO(log_str), delimiter=';')
    return list(reader)


def analyze_fills_and_position():
    """Track every PnL change and map it to book state / position changes."""
    with open(LOG_PATH, 'r') as f:
        data = json.load(f)

    activities = parse_activities_log(data['activitiesLog'])

    by_product = defaultdict(list)
    for row in activities:
        by_product[row['product']].append(row)

    for product in ["EMERALDS", "TOMATOES"]:
        rows = by_product[product]
        print(f"\n{'='*70}")
        print(f"  {product} - FILL & POSITION ANALYSIS")
        print(f"{'='*70}")

        # Build tick-by-tick PnL and identify fill ticks
        prev_pnl = 0
        fill_ticks = []
        for i, row in enumerate(rows):
            pnl = float(row['profit_and_loss'])
            ts = int(row['timestamp'])
            bp1 = float(row['bid_price_1']) if row.get('bid_price_1') else None
            ap1 = float(row['ask_price_1']) if row.get('ask_price_1') else None
            mid = (bp1 + ap1) / 2 if bp1 and ap1 else None
            spread = (ap1 - bp1) if bp1 and ap1 else None
            bv1 = int(row['bid_volume_1']) if row.get('bid_volume_1') else 0
            av1 = int(row['ask_volume_1']) if row.get('ask_volume_1') else 0

            delta_pnl = pnl - prev_pnl
            if abs(delta_pnl) > 0.001:
                fill_ticks.append({
                    'ts': ts,
                    'delta_pnl': delta_pnl,
                    'cumul_pnl': pnl,
                    'mid': mid,
                    'spread': spread,
                    'bp1': bp1,
                    'ap1': ap1,
                    'bv1': bv1,
                    'av1': av1,
                })
            prev_pnl = pnl

        print(f"\nTotal fill events: {len(fill_ticks)}")

        if product == "EMERALDS":
            # EMERALDS analysis: all fills are 7*qty multiples
            print(f"\nFill edge analysis (WIDTH=7):")
            for ft in fill_ticks:
                # edge = delta_pnl, should be multiple of 7
                qty = ft['delta_pnl'] / 7
                print(f"  t={ft['ts']:6d}: delta={ft['delta_pnl']:+.0f}, "
                      f"inferred_qty={qty:.0f}, spread={ft['spread']:.0f}, "
                      f"mid={ft['mid']:.1f}, bv1={ft['bv1']}, av1={ft['av1']}")

            # Are fills correlated with narrow spread (8 instead of 16)?
            narrow_fills = sum(1 for ft in fill_ticks if ft['spread'] and ft['spread'] < 16)
            print(f"\nFills during narrow spread (8): {narrow_fills}/{len(fill_ticks)}")

        elif product == "TOMATOES":
            # Analyze adverse selection: after each fill, does mid move against us?
            print(f"\n--- Adverse Selection Analysis ---")

            # Build mid-price series indexed by timestamp
            mid_by_ts = {}
            for row in rows:
                ts = int(row['timestamp'])
                bp1 = float(row['bid_price_1']) if row.get('bid_price_1') else None
                ap1 = float(row['ask_price_1']) if row.get('ask_price_1') else None
                if bp1 and ap1:
                    mid_by_ts[ts] = (bp1 + ap1) / 2

            all_ts = sorted(mid_by_ts.keys())

            # For each fill tick, check mid change after
            horizons = [1, 3, 5, 10]  # ticks ahead
            for h in horizons:
                favorable = 0
                adverse = 0
                neutral = 0
                total_move = 0

                for ft in fill_ticks:
                    ts = ft['ts']
                    idx = all_ts.index(ts) if ts in all_ts else -1
                    if idx < 0 or idx + h >= len(all_ts):
                        continue
                    future_ts = all_ts[idx + h]
                    mid_now = mid_by_ts.get(ts, 0)
                    mid_future = mid_by_ts.get(future_ts, 0)
                    move = mid_future - mid_now

                    # If we gained PnL, we likely sold high or bought low
                    # Adverse = price moved in direction of our trade
                    if ft['delta_pnl'] > 0:
                        # Profitable tick - could be buy below mid or sell above mid
                        pass
                    total_move += abs(move)
                    if abs(move) < 0.1:
                        neutral += 1
                    elif move > 0:
                        favorable += 1
                    else:
                        adverse += 1

                print(f"  {h}-tick ahead: favorable={favorable}, adverse={adverse}, neutral={neutral}")

            # Analyze PnL by spread regime
            print(f"\n--- PnL by Spread Regime ---")
            narrow_pnl = sum(ft['delta_pnl'] for ft in fill_ticks if ft['spread'] and ft['spread'] < 10)
            normal_pnl = sum(ft['delta_pnl'] for ft in fill_ticks if ft['spread'] and ft['spread'] >= 10)
            narrow_count = sum(1 for ft in fill_ticks if ft['spread'] and ft['spread'] < 10)
            normal_count = sum(1 for ft in fill_ticks if ft['spread'] and ft['spread'] >= 10)
            print(f"  Narrow (<10): {narrow_count} fills, PnL={narrow_pnl:.2f}")
            print(f"  Normal (>=10): {normal_count} fills, PnL={normal_pnl:.2f}")

            # Consecutive loss streaks
            print(f"\n--- Loss Streak Analysis ---")
            streak = 0
            max_streak = 0
            streaks = []
            for ft in fill_ticks:
                if ft['delta_pnl'] < -0.01:
                    streak += 1
                else:
                    if streak > 0:
                        streaks.append(streak)
                    streak = 0
                max_streak = max(max_streak, streak)
            if streak > 0:
                streaks.append(streak)
            print(f"  Max loss streak: {max_streak}")
            print(f"  Avg loss streak: {sum(streaks)/len(streaks):.1f}" if streaks else "  No loss streaks")

            # Maximum drawdown
            print(f"\n--- Drawdown Analysis ---")
            peak = 0
            max_dd = 0
            for ft in fill_ticks:
                peak = max(peak, ft['cumul_pnl'])
                dd = peak - ft['cumul_pnl']
                max_dd = max(max_dd, dd)
            print(f"  Max drawdown: {max_dd:.2f}")

            # PnL per tick analysis
            gains_per_tick = [ft['delta_pnl'] for ft in fill_ticks if ft['delta_pnl'] > 0]
            losses_per_tick = [ft['delta_pnl'] for ft in fill_ticks if ft['delta_pnl'] < 0]
            print(f"\n--- Win/Loss Stats ---")
            print(f"  Win rate: {len(gains_per_tick)}/{len(fill_ticks)} = {len(gains_per_tick)/len(fill_ticks)*100:.1f}%")
            print(f"  Avg win: {sum(gains_per_tick)/len(gains_per_tick):.2f}" if gains_per_tick else "")
            print(f"  Avg loss: {sum(losses_per_tick)/len(losses_per_tick):.2f}" if losses_per_tick else "")
            print(f"  Win/Loss ratio: {abs(sum(gains_per_tick)/len(gains_per_tick)) / abs(sum(losses_per_tick)/len(losses_per_tick)):.2f}" if gains_per_tick and losses_per_tick else "")
            print(f"  Profit factor: {sum(gains_per_tick) / abs(sum(losses_per_tick)):.2f}" if losses_per_tick else "")


def analyze_narrow_spread_opportunities():
    """When spread narrows to 5-9, what's happening? These are trading moments."""
    print(f"\n\n{'#'*70}")
    print(f"  NARROW SPREAD ANALYSIS (Training Data)")
    print(f"{'#'*70}")

    for label, pfile in [
        ("Day -1", TRAIN_PRICES_D1),
        ("Day -2", TRAIN_PRICES_D2),
    ]:
        with open(pfile, 'r') as f:
            reader = csv.DictReader(f, delimiter=';')
            prices = list(reader)

        by_product = defaultdict(list)
        for row in prices:
            by_product[row['product']].append(row)

        for product in ["TOMATOES"]:
            rows = by_product[product]
            print(f"\n  {label} - {product}")

            # Identify narrow spread periods and what happens to mid after
            mids = []
            spreads_list = []
            for r in rows:
                bp1 = float(r['bid_price_1']) if r.get('bid_price_1') else None
                ap1 = float(r['ask_price_1']) if r.get('ask_price_1') else None
                if bp1 and ap1:
                    mids.append((bp1 + ap1) / 2)
                    spreads_list.append(ap1 - bp1)
                else:
                    mids.append(None)
                    spreads_list.append(None)

            # When spread narrowed, what happened to mid in next N ticks?
            for threshold in [9, 8, 7, 6, 5]:
                events = []
                for i in range(len(spreads_list) - 20):
                    if spreads_list[i] is not None and spreads_list[i] <= threshold:
                        # Check mid movement
                        mid_now = mids[i]
                        if mid_now is None:
                            continue
                        moves = {}
                        for h in [1, 5, 10, 20]:
                            if i + h < len(mids) and mids[i + h] is not None:
                                moves[h] = mids[i + h] - mid_now
                        events.append(moves)

                if events:
                    print(f"\n    Spread <= {threshold}: {len(events)} events")
                    for h in [1, 5, 10, 20]:
                        vals = [e[h] for e in events if h in e]
                        if vals:
                            avg = sum(vals) / len(vals)
                            std = (sum((v - avg)**2 for v in vals) / len(vals)) ** 0.5
                            print(f"      {h}-tick ahead: mean={avg:+.3f}, std={std:.3f}, "
                                  f"up={sum(1 for v in vals if v > 0)}, down={sum(1 for v in vals if v < 0)}")


def analyze_volume_timing():
    """When do fills happen? Analyze volume patterns."""
    print(f"\n\n{'#'*70}")
    print(f"  VOLUME TIMING ANALYSIS (Training Data)")
    print(f"{'#'*70}")

    for label, pfile in [
        ("Day -1", TRAIN_PRICES_D1),
    ]:
        with open(pfile, 'r') as f:
            reader = csv.DictReader(f, delimiter=';')
            prices = list(reader)

        by_product = defaultdict(list)
        for row in prices:
            by_product[row['product']].append(row)

        for product in ["EMERALDS", "TOMATOES"]:
            rows = by_product[product]
            print(f"\n  {label} - {product}")

            # Analyze L1 volume dynamics
            # When volume drops below average, it might indicate a recent fill
            vols = []
            for r in rows:
                bv1 = int(r['bid_volume_1']) if r.get('bid_volume_1') else 0
                av1 = int(r['ask_volume_1']) if r.get('ask_volume_1') else 0
                vols.append((bv1, av1))

            # Volume changes that could indicate fills
            bid_vol_drops = 0
            ask_vol_drops = 0
            for i in range(1, len(vols)):
                if vols[i][0] < vols[i-1][0]:
                    bid_vol_drops += 1
                if vols[i][1] < vols[i-1][1]:
                    ask_vol_drops += 1

            print(f"    Bid volume drops: {bid_vol_drops}")
            print(f"    Ask volume drops: {ask_vol_drops}")

            # Analyze bid/ask volume distribution
            bv_dist = defaultdict(int)
            av_dist = defaultdict(int)
            for bv, av in vols:
                bv_dist[bv] += 1
                av_dist[av] += 1

            print(f"    Bid volume distribution:")
            for v in sorted(bv_dist.keys()):
                print(f"      {v:3d}: {bv_dist[v]:5d}")
            print(f"    Ask volume distribution:")
            for v in sorted(av_dist.keys()):
                print(f"      {v:3d}: {av_dist[v]:5d}")


def analyze_competition_impact():
    """What happens when we have competitors? Simulate the impact."""
    print(f"\n\n{'#'*70}")
    print(f"  COMPETITION IMPACT ANALYSIS")
    print(f"{'#'*70}")

    with open(LOG_PATH, 'r') as f:
        data = json.load(f)

    activities = parse_activities_log(data['activitiesLog'])

    by_product = defaultdict(list)
    for row in activities:
        by_product[row['product']].append(row)

    for product in ["EMERALDS", "TOMATOES"]:
        rows = by_product[product]
        print(f"\n  {product}:")

        if product == "EMERALDS":
            # With WIDTH=7, we quote at 9993/10007
            # Bot spread: 9992/10008
            # If competitors quote at same level, our fill rate drops proportionally
            # If competitors quote tighter (9994/10006), we get NO fills

            fill_count = 0
            prev_pnl = 0
            for row in rows:
                pnl = float(row['profit_and_loss'])
                if abs(pnl - prev_pnl) > 0.001:
                    fill_count += 1
                prev_pnl = pnl

            print(f"    Solo fills: {fill_count}")
            print(f"    Solo PnL: {float(rows[-1]['profit_and_loss']):.0f}")
            print(f"    If 1 competitor at same level: ~{fill_count//2} fills, PnL ~{float(rows[-1]['profit_and_loss'])/2:.0f}")
            print(f"    If 1 competitor at tighter level: ~0 fills from makes")
            print(f"    Recommendation: Be prepared to tighten to WIDTH=6 or even 5 if needed")

            # What if we could ALSO take profitably?
            # Current: take at 9999/10001 (never hits since bot bid=9992, ask=10008)
            # Could we take during narrow spread periods?
            narrow_ticks = sum(1 for r in rows if r.get('bid_price_1') and r.get('ask_price_1')
                             and float(r['ask_price_1']) - float(r['bid_price_1']) < 16)
            print(f"    Narrow spread (bot-crossing) ticks: {narrow_ticks}")
            # During narrow spread, L1 is at 10000/10000 or similar
            for r in rows:
                if r.get('bid_price_1') and r.get('ask_price_1'):
                    spread = float(r['ask_price_1']) - float(r['bid_price_1'])
                    if spread < 10:
                        print(f"      t={r['timestamp']}: bid={r['bid_price_1']}, ask={r['ask_price_1']}, "
                              f"bv={r['bid_volume_1']}, av={r['ask_volume_1']}, spread={spread:.0f}")
                        break  # just show first

        elif product == "TOMATOES":
            # Tomatoes is more complex since fair value moves
            # Competition will narrow the effective spread we can capture
            # Key: our edge comes from:
            # 1. Make fills (capturing spread)
            # 2. Take fills (crossing when mispriced)

            # For competition, we need to think about:
            # - Better fair value estimation = less adverse selection
            # - Faster position management = less inventory risk
            # - Optimal width balancing fill rate vs edge

            prev_pnl = 0
            pos_gain = 0
            neg_gain = 0
            for row in rows:
                pnl = float(row['profit_and_loss'])
                delta = pnl - prev_pnl
                if delta > 0.5:
                    pos_gain += delta
                elif delta < -0.5:
                    neg_gain += abs(delta)
                prev_pnl = pnl

            print(f"    Gross gain: {pos_gain:.2f}")
            print(f"    Gross loss: {neg_gain:.2f}")
            print(f"    Net: {pos_gain - neg_gain:.2f}")
            print(f"    Loss ratio: {neg_gain / (pos_gain + neg_gain) * 100:.1f}%")
            print(f"    With competitors, expect ~{neg_gain / (pos_gain + neg_gain) * 100 * 1.3:.0f}% loss ratio due to adverse selection")


if __name__ == "__main__":
    analyze_fills_and_position()
    analyze_narrow_spread_opportunities()
    analyze_volume_timing()
    analyze_competition_impact()
