"""
Comprehensive analysis of sim 44861 for EMERALDS and TOMATOES.
Parses the JSON log to extract:
- PnL breakdown by product
- Fill counts, fill rates, edge per fill
- Market microstructure (spread distribution, book depth)
- Position trajectory
- Take vs Make fill analysis
- Adverse selection analysis
"""

import json
import csv
import io
from collections import defaultdict

LOG_PATH = r".\logs\44861\44861.json"
TRAIN_PRICES_D1 = r".\tutorial-round\data\TUTORIAL_ROUND_1\prices_round_0_day_-1.csv"
TRAIN_PRICES_D2 = r".\tutorial-round\data\TUTORIAL_ROUND_1\prices_round_0_day_-2.csv"
TRAIN_TRADES_D1 = r".\tutorial-round\data\TUTORIAL_ROUND_1\trades_round_0_day_-1.csv"
TRAIN_TRADES_D2 = r".\tutorial-round\data\TUTORIAL_ROUND_1\trades_round_0_day_-2.csv"


def parse_activities_log(log_str):
    """Parse the activities log CSV from the JSON."""
    reader = csv.DictReader(io.StringIO(log_str), delimiter=';')
    rows = []
    for row in reader:
        rows.append(row)
    return rows


def analyze_sim():
    with open(LOG_PATH, 'r') as f:
        data = json.load(f)

    print(f"Status: {data['status']}")
    print(f"Total Profit: {data['profit']}")
    print()

    activities = parse_activities_log(data['activitiesLog'])

    # Group by product
    by_product = defaultdict(list)
    for row in activities:
        by_product[row['product']].append(row)

    for product in sorted(by_product.keys()):
        rows = by_product[product]
        print(f"\n{'='*70}")
        print(f"  {product}")
        print(f"{'='*70}")

        # Final PnL
        final_pnl = float(rows[-1]['profit_and_loss'])
        print(f"Final PnL: {final_pnl:.2f}")
        print(f"Ticks: {len(rows)}")

        # Spread analysis
        spreads = []
        mids = []
        bid1s = []
        ask1s = []
        for row in rows:
            bp1 = row.get('bid_price_1', '')
            ap1 = row.get('ask_price_1', '')
            if bp1 and ap1:
                b = float(bp1)
                a = float(ap1)
                spreads.append(a - b)
                mids.append((a + b) / 2)
                bid1s.append(b)
                ask1s.append(a)

        if spreads:
            print(f"\nSpread stats:")
            print(f"  Mean: {sum(spreads)/len(spreads):.2f}")
            print(f"  Min: {min(spreads)}")
            print(f"  Max: {max(spreads)}")
            print(f"  Median: {sorted(spreads)[len(spreads)//2]:.2f}")

        # Spread distribution
        spread_dist = defaultdict(int)
        for s in spreads:
            spread_dist[s] += 1
        print(f"  Distribution:")
        for s in sorted(spread_dist.keys()):
            pct = spread_dist[s] / len(spreads) * 100
            print(f"    {s:6.0f}: {spread_dist[s]:5d} ({pct:5.1f}%)")

        # Mid price stats
        if mids:
            print(f"\nMid price stats:")
            print(f"  Mean: {sum(mids)/len(mids):.2f}")
            print(f"  Min: {min(mids):.2f}")
            print(f"  Max: {max(mids):.2f}")
            print(f"  Std: {(sum((m - sum(mids)/len(mids))**2 for m in mids)/len(mids))**0.5:.2f}")

        # Bid/Ask volume at L1
        bid_vols = []
        ask_vols = []
        for row in rows:
            bv1 = row.get('bid_volume_1', '')
            av1 = row.get('ask_volume_1', '')
            if bv1:
                bid_vols.append(int(bv1))
            if av1:
                ask_vols.append(int(av1))

        if bid_vols:
            print(f"\nL1 Bid Volume: mean={sum(bid_vols)/len(bid_vols):.1f}, min={min(bid_vols)}, max={max(bid_vols)}")
        if ask_vols:
            print(f"L1 Ask Volume: mean={sum(ask_vols)/len(ask_vols):.1f}, min={min(ask_vols)}, max={max(ask_vols)}")

        # PnL trajectory (sample at intervals)
        pnl_values = [float(row['profit_and_loss']) for row in rows]
        timestamps = [int(row['timestamp']) for row in rows]

        # Find unique timestamps
        unique_ts = sorted(set(timestamps))
        print(f"\nUnique timestamps: {len(unique_ts)}")
        print(f"Timestamp range: {unique_ts[0]} to {unique_ts[-1]}")

        # PnL at 10 points
        sample_points = [int(len(unique_ts) * i / 10) for i in range(11)]
        print(f"\nPnL trajectory:")
        for i, idx in enumerate(sample_points):
            if idx < len(unique_ts):
                ts = unique_ts[idx]
                # Find last row with this timestamp for this product
                pnl = None
                for row in rows:
                    if int(row['timestamp']) == ts:
                        pnl = float(row['profit_and_loss'])
                if pnl is not None:
                    print(f"  t={ts:6d}: {pnl:8.2f}")

        # Tick-by-tick PnL changes
        pnl_changes = []
        last_pnl = 0
        for row in rows:
            p = float(row['profit_and_loss'])
            if p != last_pnl:
                pnl_changes.append((int(row['timestamp']), p - last_pnl, p))
                last_pnl = p

        print(f"\nPnL change events: {len(pnl_changes)}")
        if pnl_changes:
            gains = [c for _, c, _ in pnl_changes if c > 0]
            losses = [c for _, c, _ in pnl_changes if c < 0]
            print(f"  Gains: {len(gains)}, total={sum(gains):.2f}, avg={sum(gains)/len(gains):.2f}" if gains else "  No gains")
            print(f"  Losses: {len(losses)}, total={sum(losses):.2f}, avg={sum(losses)/len(losses):.2f}" if losses else "  No losses")

            # Largest PnL changes
            sorted_changes = sorted(pnl_changes, key=lambda x: abs(x[1]), reverse=True)
            print(f"\n  Top 10 PnL changes:")
            for ts, chg, cumul in sorted_changes[:10]:
                print(f"    t={ts:6d}: {chg:+8.2f} (cumul={cumul:.2f})")

            # Distribution of gain sizes
            print(f"\n  Gain size distribution:")
            gain_buckets = defaultdict(int)
            for g in gains:
                bucket = round(g, 0)
                gain_buckets[bucket] += 1
            for b in sorted(gain_buckets.keys()):
                print(f"    {b:+8.0f}: {gain_buckets[b]:4d}")


def analyze_training_data():
    """Analyze the training data for market microstructure insights."""
    print(f"\n\n{'#'*70}")
    print(f"  TRAINING DATA ANALYSIS")
    print(f"{'#'*70}")

    for label, pfile, tfile in [
        ("Day -1", TRAIN_PRICES_D1, TRAIN_TRADES_D1),
        ("Day -2", TRAIN_PRICES_D2, TRAIN_TRADES_D2),
    ]:
        print(f"\n{'='*50}")
        print(f"  {label}")
        print(f"{'='*50}")

        # Parse prices
        with open(pfile, 'r') as f:
            reader = csv.DictReader(f, delimiter=';')
            prices = list(reader)

        by_product = defaultdict(list)
        for row in prices:
            by_product[row['product']].append(row)

        for product in sorted(by_product.keys()):
            rows = by_product[product]
            print(f"\n  {product}: {len(rows)} ticks")

            spreads = []
            mids = []
            for row in rows:
                bp1 = row.get('bid_price_1', '')
                ap1 = row.get('ask_price_1', '')
                if bp1 and ap1:
                    b = float(bp1)
                    a = float(ap1)
                    spreads.append(a - b)
                    mids.append((a + b) / 2)

            if spreads:
                print(f"    Spread: mean={sum(spreads)/len(spreads):.2f}, min={min(spreads):.0f}, max={max(spreads):.0f}")

                spread_dist = defaultdict(int)
                for s in spreads:
                    spread_dist[s] += 1
                print(f"    Spread distribution:")
                for s in sorted(spread_dist.keys()):
                    pct = spread_dist[s] / len(spreads) * 100
                    print(f"      {s:6.0f}: {spread_dist[s]:5d} ({pct:5.1f}%)")

            if mids:
                mean_mid = sum(mids) / len(mids)
                std_mid = (sum((m - mean_mid)**2 for m in mids) / len(mids)) ** 0.5
                print(f"    Mid: mean={mean_mid:.2f}, std={std_mid:.2f}, min={min(mids):.2f}, max={max(mids):.2f}")

            # L1 volumes
            bid_vols = [int(row['bid_volume_1']) for row in rows if row.get('bid_volume_1')]
            ask_vols = [int(row['ask_volume_1']) for row in rows if row.get('ask_volume_1')]
            if bid_vols:
                print(f"    L1 Bid Vol: mean={sum(bid_vols)/len(bid_vols):.1f}")
            if ask_vols:
                print(f"    L1 Ask Vol: mean={sum(ask_vols)/len(ask_vols):.1f}")

        # Parse trades
        try:
            with open(tfile, 'r') as f:
                reader = csv.DictReader(f, delimiter=';')
                trades = list(reader)

            trade_by_product = defaultdict(list)
            for t in trades:
                trade_by_product[t['symbol']].append(t)

            for product in sorted(trade_by_product.keys()):
                tlist = trade_by_product[product]
                print(f"\n  {product} Trades: {len(tlist)} total")
                # Buyer/seller analysis
                buyers = defaultdict(int)
                sellers = defaultdict(int)
                for t in tlist:
                    buyers[t.get('buyer', '')] += 1
                    sellers[t.get('seller', '')] += 1
                print(f"    Buyers: {dict(buyers)}")
                print(f"    Sellers: {dict(sellers)}")

                # Price distribution of trades
                trade_prices = [float(t['price']) for t in tlist]
                if trade_prices:
                    print(f"    Trade prices: mean={sum(trade_prices)/len(trade_prices):.2f}, min={min(trade_prices):.0f}, max={max(trade_prices):.0f}")

                # Volume per trade
                trade_vols = [int(t['quantity']) for t in tlist]
                if trade_vols:
                    print(f"    Trade qty: mean={sum(trade_vols)/len(trade_vols):.1f}, min={min(trade_vols)}, max={max(trade_vols)}, total={sum(trade_vols)}")
        except Exception as e:
            print(f"  No trades file or error: {e}")


def analyze_bot_behavior():
    """Analyze the bot behavior from training data to understand adversary patterns."""
    print(f"\n\n{'#'*70}")
    print(f"  BOT BEHAVIOR ANALYSIS (Training Data)")
    print(f"{'#'*70}")

    for label, tfile in [
        ("Day -1", TRAIN_TRADES_D1),
        ("Day -2", TRAIN_TRADES_D2),
    ]:
        print(f"\n{'='*50}")
        print(f"  {label}")
        print(f"{'='*50}")

        try:
            with open(tfile, 'r') as f:
                reader = csv.DictReader(f, delimiter=';')
                trades = list(reader)

            trade_by_product = defaultdict(list)
            for t in trades:
                trade_by_product[t['symbol']].append(t)

            for product in sorted(trade_by_product.keys()):
                tlist = trade_by_product[product]
                print(f"\n  {product}:")

                # Analyze inter-trade timing
                timestamps = [int(t['timestamp']) for t in tlist]
                if len(timestamps) > 1:
                    intervals = [timestamps[i+1] - timestamps[i] for i in range(len(timestamps)-1)]
                    nonzero_intervals = [i for i in intervals if i > 0]
                    if nonzero_intervals:
                        print(f"    Inter-trade intervals (non-zero): mean={sum(nonzero_intervals)/len(nonzero_intervals):.0f}, min={min(nonzero_intervals)}, max={max(nonzero_intervals)}")

                # Analyze trade direction patterns
                # Each trade: what was the price relative to mid?
                # We need prices for this
                pass

                # Count unique timestamps with trades
                unique_trade_ts = len(set(timestamps))
                print(f"    Unique timestamps with trades: {unique_trade_ts}")
                print(f"    Trades per active tick: {len(tlist)/unique_trade_ts:.1f}")

                # Analyze buyer/seller patterns
                participants = set()
                for t in tlist:
                    participants.add(t.get('buyer', ''))
                    participants.add(t.get('seller', ''))
                participants.discard('')
                print(f"    Participants: {participants}")

                # Per-participant volume
                participant_buys = defaultdict(int)
                participant_sells = defaultdict(int)
                participant_buy_vol = defaultdict(int)
                participant_sell_vol = defaultdict(int)
                for t in tlist:
                    qty = int(t['quantity'])
                    buyer = t.get('buyer', '')
                    seller = t.get('seller', '')
                    if buyer:
                        participant_buys[buyer] += 1
                        participant_buy_vol[buyer] += qty
                    if seller:
                        participant_sells[seller] += 1
                        participant_sell_vol[seller] += qty

                for p in sorted(participants):
                    print(f"    {p}: buys={participant_buys.get(p,0)} ({participant_buy_vol.get(p,0)} vol), sells={participant_sells.get(p,0)} ({participant_sell_vol.get(p,0)} vol)")

        except Exception as e:
            print(f"  Error: {e}")


def analyze_sim_detailed():
    """Deeper analysis of the 44861 sim log."""
    with open(LOG_PATH, 'r') as f:
        data = json.load(f)

    activities = parse_activities_log(data['activitiesLog'])

    # Check if we have asks at L2, L3
    print(f"\n\n{'#'*70}")
    print(f"  SIM 44861 DETAILED BOOK ANALYSIS")
    print(f"{'#'*70}")

    by_product = defaultdict(list)
    for row in activities:
        by_product[row['product']].append(row)

    for product in sorted(by_product.keys()):
        rows = by_product[product]
        print(f"\n{'='*50}")
        print(f"  {product}")
        print(f"{'='*50}")

        # Check L2/L3 presence
        l2_bid_count = sum(1 for r in rows if r.get('bid_price_2', ''))
        l3_bid_count = sum(1 for r in rows if r.get('bid_price_3', ''))
        l2_ask_count = sum(1 for r in rows if r.get('ask_price_2', ''))
        l3_ask_count = sum(1 for r in rows if r.get('ask_price_3', ''))

        print(f"  L2 presence: bids={l2_bid_count}/{len(rows)}, asks={l2_ask_count}/{len(rows)}")
        print(f"  L3 presence: bids={l3_bid_count}/{len(rows)}, asks={l3_ask_count}/{len(rows)}")

        # When L3 is present, what are the prices?
        if product == "EMERALDS":
            l3_bid_prices = defaultdict(int)
            l3_ask_prices = defaultdict(int)
            l2_bid_prices = defaultdict(int)
            l2_ask_prices = defaultdict(int)
            l1_bid_prices = defaultdict(int)
            l1_ask_prices = defaultdict(int)
            for r in rows:
                if r.get('bid_price_1'):
                    l1_bid_prices[int(float(r['bid_price_1']))] += 1
                if r.get('ask_price_1'):
                    l1_ask_prices[int(float(r['ask_price_1']))] += 1
                if r.get('bid_price_2'):
                    l2_bid_prices[int(float(r['bid_price_2']))] += 1
                if r.get('ask_price_2'):
                    l2_ask_prices[int(float(r['ask_price_2']))] += 1
                if r.get('bid_price_3'):
                    l3_bid_prices[int(float(r['bid_price_3']))] += 1
                if r.get('ask_price_3'):
                    l3_ask_prices[int(float(r['ask_price_3']))] += 1

            print(f"\n  L1 bid prices: {dict(sorted(l1_bid_prices.items()))}")
            print(f"  L1 ask prices: {dict(sorted(l1_ask_prices.items()))}")
            print(f"  L2 bid prices: {dict(sorted(l2_bid_prices.items()))}")
            print(f"  L2 ask prices: {dict(sorted(l2_ask_prices.items()))}")
            print(f"  L3 bid prices: {dict(sorted(l3_bid_prices.items()))}")
            print(f"  L3 ask prices: {dict(sorted(l3_ask_prices.items()))}")

        elif product == "TOMATOES":
            # For tomatoes, track the spread dynamics more carefully
            # since it's a random walk, the spread and levels vary more
            l1_bid_prices = defaultdict(int)
            l1_ask_prices = defaultdict(int)
            for r in rows:
                if r.get('bid_price_1'):
                    l1_bid_prices[int(float(r['bid_price_1']))] += 1
                if r.get('ask_price_1'):
                    l1_ask_prices[int(float(r['ask_price_1']))] += 1

            print(f"\n  L1 bid price distribution (top 15):")
            for p, c in sorted(l1_bid_prices.items(), key=lambda x: -x[1])[:15]:
                print(f"    {p}: {c}")
            print(f"  L1 ask price distribution (top 15):")
            for p, c in sorted(l1_ask_prices.items(), key=lambda x: -x[1])[:15]:
                print(f"    {p}: {c}")


if __name__ == "__main__":
    analyze_sim()
    analyze_training_data()
    analyze_bot_behavior()
    analyze_sim_detailed()
