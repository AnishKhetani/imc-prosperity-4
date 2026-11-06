"""
Analysis #3: Understanding TOMATOES fill mechanics and testing improvement hypotheses.
Focus on:
1. What causes PnL changes (fills vs mark-to-market)?
2. Narrow spread signal: how to exploit it?
3. What does the narrow-spread book look like exactly?
4. WIDTH sensitivity analysis
5. Position trajectory reconstruction
"""

import json
import csv
import io
from collections import defaultdict
import math

LOG_PATH = r".\logs\44861\44861.json"
TRAIN_PRICES_D1 = r".\tutorial-round\data\TUTORIAL_ROUND_1\prices_round_0_day_-1.csv"
TRAIN_PRICES_D2 = r".\tutorial-round\data\TUTORIAL_ROUND_1\prices_round_0_day_-2.csv"
TRAIN_TRADES_D1 = r".\tutorial-round\data\TUTORIAL_ROUND_1\trades_round_0_day_-1.csv"
TRAIN_TRADES_D2 = r".\tutorial-round\data\TUTORIAL_ROUND_1\trades_round_0_day_-2.csv"


def parse_activities_log(log_str):
    reader = csv.DictReader(io.StringIO(log_str), delimiter=';')
    return list(reader)


def analyze_narrow_spread_microstructure():
    """Deep dive into what happens during narrow spread periods."""
    print(f"\n{'#'*70}")
    print(f"  NARROW SPREAD MICROSTRUCTURE (Training Data)")
    print(f"{'#'*70}")

    for label, pfile, tfile in [
        ("Day -1", TRAIN_PRICES_D1, TRAIN_TRADES_D1),
        ("Day -2", TRAIN_PRICES_D2, TRAIN_TRADES_D2),
    ]:
        with open(pfile, 'r') as f:
            reader = csv.DictReader(f, delimiter=';')
            prices = list(reader)

        tomato_prices = [r for r in prices if r['product'] == 'TOMATOES']

        with open(tfile, 'r') as f:
            reader = csv.DictReader(f, delimiter=';')
            trades = list(reader)

        tomato_trades_by_ts = defaultdict(list)
        for t in trades:
            if t['symbol'] == 'TOMATOES':
                tomato_trades_by_ts[int(t['timestamp'])].append(t)

        print(f"\n  {label}")
        print(f"  Showing first 20 narrow spread (<=7) events with context:")

        count = 0
        for i, row in enumerate(tomato_prices):
            bp1 = float(row['bid_price_1']) if row.get('bid_price_1') else None
            ap1 = float(row['ask_price_1']) if row.get('ask_price_1') else None
            if not bp1 or not ap1:
                continue
            spread = ap1 - bp1
            if spread > 7:
                continue

            ts = int(row['timestamp'])
            mid = (bp1 + ap1) / 2

            # Get context: what were prices before and after?
            context = []
            for j in range(max(0, i-2), min(len(tomato_prices), i+5)):
                r = tomato_prices[j]
                b = float(r['bid_price_1']) if r.get('bid_price_1') else None
                a = float(r['ask_price_1']) if r.get('ask_price_1') else None
                bv = int(r['bid_volume_1']) if r.get('bid_volume_1') else 0
                av = int(r['ask_volume_1']) if r.get('ask_volume_1') else 0
                m = (b + a) / 2 if b and a else None
                s = (a - b) if b and a else None
                marker = ">>>" if j == i else "   "
                t_ts = int(r['timestamp'])
                trade_info = ""
                if t_ts in tomato_trades_by_ts:
                    for t in tomato_trades_by_ts[t_ts]:
                        trade_info += f" TRADE: {t['buyer']}->{t['seller']} {t['quantity']}@{t['price']}"
                context.append(f"    {marker} t={t_ts:6d}: bid={b:.0f}({bv:2d}) ask={a:.0f}({av:2d}) spread={s:.0f} mid={m:.1f}{trade_info}")

            count += 1
            print(f"\n  Event {count}: t={ts}, bid={bp1:.0f}, ask={ap1:.0f}, spread={spread:.0f}")
            for line in context:
                print(line)

            if count >= 20:
                break

        # Now analyze the DIRECTION of narrow spreads
        print(f"\n\n  Narrow spread direction analysis:")
        up_narrows = 0  # bid moved up causing narrow
        down_narrows = 0  # ask moved down causing narrow
        both_narrows = 0

        for i in range(1, len(tomato_prices)):
            row = tomato_prices[i]
            prev = tomato_prices[i-1]

            bp1 = float(row['bid_price_1']) if row.get('bid_price_1') else None
            ap1 = float(row['ask_price_1']) if row.get('ask_price_1') else None
            pbp1 = float(prev['bid_price_1']) if prev.get('bid_price_1') else None
            pap1 = float(prev['ask_price_1']) if prev.get('ask_price_1') else None

            if not all([bp1, ap1, pbp1, pap1]):
                continue

            spread = ap1 - bp1
            prev_spread = pap1 - pbp1

            if spread <= 7 and prev_spread > 7:
                # Just narrowed
                bid_moved_up = bp1 > pbp1
                ask_moved_down = ap1 < pap1

                if bid_moved_up and not ask_moved_down:
                    up_narrows += 1
                elif ask_moved_down and not bid_moved_up:
                    down_narrows += 1
                else:
                    both_narrows += 1

        print(f"    Bid moved up (price rising): {up_narrows}")
        print(f"    Ask moved down (price falling): {down_narrows}")
        print(f"    Both or neither: {both_narrows}")


def analyze_tomatoes_width_sensitivity():
    """What would happen with different MAKE_WIDTH values?
    With wider width, we capture more edge per fill but fewer fills.
    """
    print(f"\n\n{'#'*70}")
    print(f"  TOMATOES WIDTH SENSITIVITY (Training Data)")
    print(f"{'#'*70}")

    for label, pfile, tfile in [
        ("Day -1", TRAIN_PRICES_D1, TRAIN_TRADES_D1),
        ("Day -2", TRAIN_PRICES_D2, TRAIN_TRADES_D2),
    ]:
        with open(pfile, 'r') as f:
            reader = csv.DictReader(f, delimiter=';')
            prices = list(reader)

        tomato_prices = [r for r in prices if r['product'] == 'TOMATOES']

        print(f"\n  {label}")
        print(f"  Normal spread distribution for TOMATOES:")

        spreads = []
        for r in tomato_prices:
            bp1 = float(r['bid_price_1']) if r.get('bid_price_1') else None
            ap1 = float(r['ask_price_1']) if r.get('ask_price_1') else None
            if bp1 and ap1:
                spreads.append(ap1 - bp1)

        # For TOMATOES, with a spread of 13:
        # bot bid = mid - 6.5 (approx), bot ask = mid + 6.5
        # Our make at fair ± WIDTH
        # For us to get filled, bot must cross our price
        # Our bid at fair-WIDTH must be >= some bot sell price, OR
        # A bot must lift our ask at fair+WIDTH

        # In the training data (no participant bots), the trades show
        # the natural bot trading. Our makes would compete with these levels.

        # With WIDTH=W:
        # Our bid = fair - W
        # Our ask = fair + W
        # For a make fill, the aggressive side crosses our level.
        # If spread is S and our width is W:
        #   - Our bid is mid - W (approx)
        #   - Bot bid is mid - S/2
        #   - If W < S/2, our bid is ABOVE bot bid (tighter), we get priority
        #   - Fill happens when an aggressive seller hits us
        print(f"\n  Width vs bot edge analysis:")
        for width in [3, 4, 5, 6, 7]:
            inside_count = sum(1 for s in spreads if width < s/2)
            at_edge = sum(1 for s in spreads if abs(width - s/2) < 0.5)
            outside_count = sum(1 for s in spreads if width > s/2)
            print(f"    WIDTH={width}: inside_spread={inside_count}/{len(spreads)} ({inside_count/len(spreads)*100:.1f}%), "
                  f"at_edge={at_edge}, outside={outside_count}")


def analyze_l1_volume_and_fills():
    """Analyze what L1 volumes look like when narrow spread occurs - this tells us how much we can take."""
    print(f"\n\n{'#'*70}")
    print(f"  L1 VOLUME DURING NARROW SPREADS")
    print(f"{'#'*70}")

    for label, pfile in [
        ("Day -1", TRAIN_PRICES_D1),
        ("Day -2", TRAIN_PRICES_D2),
    ]:
        with open(pfile, 'r') as f:
            reader = csv.DictReader(f, delimiter=';')
            prices = list(reader)

        tomato_prices = [r for r in prices if r['product'] == 'TOMATOES']
        emerald_prices = [r for r in prices if r['product'] == 'EMERALDS']

        print(f"\n  {label} TOMATOES:")

        # When spread is narrow, what volumes are available?
        for threshold in [5, 6, 7, 8]:
            vols_bid = []
            vols_ask = []
            for r in tomato_prices:
                bp1 = float(r['bid_price_1']) if r.get('bid_price_1') else None
                ap1 = float(r['ask_price_1']) if r.get('ask_price_1') else None
                if bp1 and ap1 and (ap1 - bp1) <= threshold:
                    vols_bid.append(int(r['bid_volume_1']))
                    vols_ask.append(int(r['ask_volume_1']))
            if vols_bid:
                print(f"    Spread <= {threshold}: {len(vols_bid)} ticks, "
                      f"bid_vol: mean={sum(vols_bid)/len(vols_bid):.1f}, "
                      f"ask_vol: mean={sum(vols_ask)/len(vols_ask):.1f}")


def analyze_emeralds_competition_scenarios():
    """What if we used different EMERALD widths or strategies?"""
    print(f"\n\n{'#'*70}")
    print(f"  EMERALDS STRATEGY OPTIONS")
    print(f"{'#'*70}")

    with open(LOG_PATH, 'r') as f:
        data = json.load(f)

    activities = parse_activities_log(data['activitiesLog'])
    emerald_rows = [r for r in activities if r['product'] == 'EMERALDS']

    # Current: WIDTH=7 → 29 fills, 1050 PnL, avg 36.2 per fill
    # If WIDTH=6 → 29 fills * 6/7 edge = 900 PnL (fills should be same or more)
    # If WIDTH=8 → some fills outside spread, probably 0 fills

    print(f"\n  Current performance (WIDTH=7):")
    print(f"  Fills: 29, PnL: 1050, per-fill: 36.2")
    print(f"  Per-unit edge: 7")

    # Theoretical at different widths (assuming same fill count):
    for w in [3, 4, 5, 6, 7, 8]:
        # At WIDTH=w, our prices are (10000-w)/(10000+w)
        # Bot spread is 9992/10008
        # We're inside if 10000-w > 9992 i.e. w < 8
        inside = (10000 - w) > 9992
        est_pnl = 29 * w * (150/29) if inside else 0  # 150 total units
        print(f"  WIDTH={w}: prices={(10000-w)}/{10000+w}, inside_bot_spread={inside}, "
              f"est_PnL={150*w if inside else '~0'}")

    print(f"\n  In competition with N other MMs at WIDTH=7:")
    for n_competitors in [0, 1, 2, 3, 5, 10]:
        fill_share = 1.0 / (1 + n_competitors)
        est_pnl = 1050 * fill_share
        print(f"    {n_competitors} competitors: fill_share={fill_share:.0%}, est_PnL={est_pnl:.0f}")

    # With multi-level quoting in competition:
    print(f"\n  Multi-level quoting scenarios:")
    print(f"  If competitors at WIDTH=7, we quote at WIDTH=6:")
    print(f"    We get ALL fills, edge per unit = 6, est_PnL = {150*6}")
    print(f"  If competitors at WIDTH=6, we quote at WIDTH=5:")
    print(f"    We get ALL fills, edge per unit = 5, est_PnL = {150*5}")


def analyze_tomato_take_vs_make():
    """Analyze whether our fills are takes or makes using trade history."""
    print(f"\n\n{'#'*70}")
    print(f"  TAKE vs MAKE ANALYSIS (from tradeHistory)")
    print(f"{'#'*70}")

    log_path = LOG_PATH.replace('.json', '.log')
    with open(log_path, 'r') as f:
        data = json.load(f)

    trades = data.get('tradeHistory', [])
    activities = parse_activities_log(data['activitiesLog'])

    # Build book state by timestamp for TOMATOES
    tomato_rows = [r for r in activities if r['product'] == 'TOMATOES']
    book_by_ts = {}
    for r in tomato_rows:
        ts = int(r['timestamp'])
        bp1 = float(r['bid_price_1']) if r.get('bid_price_1') else None
        ap1 = float(r['ask_price_1']) if r.get('ask_price_1') else None
        book_by_ts[ts] = (bp1, ap1)

    tomato_trades = [t for t in trades if t['symbol'] == 'TOMATOES']
    print(f"  Total TOMATOES trades: {len(tomato_trades)}")

    for t in tomato_trades[:30]:
        ts = t['timestamp']
        # Book state at ts-100 (the tick BEFORE this fill happened)
        prev_ts = ts - 100
        book = book_by_ts.get(prev_ts)
        side = "BUY " if t['buyer'] == 'SUBMISSION' else "SELL"
        
        if book and book[0] and book[1]:
            bp, ap = book
            mid = (bp + ap) / 2
            spread = ap - bp
            
            # If we BUY at the ask or near it -> TAKE
            # If we BUY at our bid (below mid) -> MAKE
            price = t['price']
            if side == "BUY ":
                dist_from_ask = ap - price
                dist_from_bid = price - bp
                kind = "TAKE" if price >= mid else "MAKE"
            else:
                dist_from_ask = ap - price
                dist_from_bid = price - bp
                kind = "TAKE" if price <= mid else "MAKE"
            
            print(f"  t={ts:6d}: {side} {t['quantity']}x@{price:.0f} | book={bp:.0f}/{ap:.0f} "
                  f"spread={spread:.0f} mid={mid:.1f} | {kind}")
        else:
            print(f"  t={ts:6d}: {side} {t['quantity']}x@{t['price']:.0f} | no book data")


if __name__ == "__main__":
    analyze_narrow_spread_microstructure()
    analyze_tomatoes_width_sensitivity()
    analyze_l1_volume_and_fills()
    analyze_emeralds_competition_scenarios()
    analyze_tomato_take_vs_make()
