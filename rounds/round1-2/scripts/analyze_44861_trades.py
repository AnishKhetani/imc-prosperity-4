"""
Analysis #4: Complete trade history analysis from 44861.log
"""
import json
from collections import defaultdict

LOG_PATH = r".\logs\44861\44861.log"


def main():
    with open(LOG_PATH, 'r') as f:
        data = json.load(f)

    trades = data['tradeHistory']

    print(f"Total trades: {len(trades)}")

    by_product = defaultdict(list)
    for t in trades:
        by_product[t['symbol']].append(t)

    for product in sorted(by_product.keys()):
        tlist = by_product[product]
        print(f"\n{'='*70}")
        print(f"  {product}: {len(tlist)} trades")
        print(f"{'='*70}")

        buys = [t for t in tlist if t['buyer'] == 'SUBMISSION']
        sells = [t for t in tlist if t['seller'] == 'SUBMISSION']

        print(f"  OUR buys: {len(buys)}, volume={sum(t['quantity'] for t in buys)}")
        print(f"  OUR sells: {len(sells)}, volume={sum(t['quantity'] for t in sells)}")

        # Accumulate position
        position = 0
        positions = []
        for t in tlist:
            if t['buyer'] == 'SUBMISSION':
                position += t['quantity']
            else:
                position -= t['quantity']
            positions.append((t['timestamp'], position, t))

        print(f"  Final position: {position}")
        print(f"  Max position: {max(p for _, p, _ in positions)}")
        print(f"  Min position: {min(p for _, p, _ in positions)}")

        # Position at limits
        at_max = sum(1 for _, p, _ in positions if p >= 78)
        at_min = sum(1 for _, p, _ in positions if p <= -78)
        print(f"  Ticks near max pos (>=78): {at_max}")
        print(f"  Ticks near min pos (<=-78): {at_min}")

        # Calculate realized PnL from trades (sell revenue - buy cost)
        buy_cost = sum(t['price'] * t['quantity'] for t in buys)
        sell_revenue = sum(t['price'] * t['quantity'] for t in sells)
        buy_vol = sum(t['quantity'] for t in buys)
        sell_vol = sum(t['quantity'] for t in sells)

        print(f"\n  Buy avg price: {buy_cost/buy_vol:.2f}" if buy_vol else "")
        print(f"  Sell avg price: {sell_revenue/sell_vol:.2f}" if sell_vol else "")

        # For fixed-price products, realized PnL = sell_revenue - buy_cost + position * fair
        if product == "EMERALDS":
            fair = 10000
            realized = sell_revenue - buy_cost + position * fair
            print(f"  Realized PnL (incl position@{fair}): {realized:.2f}")
            print(f"  Edge per unit bought: {(fair - buy_cost/buy_vol):.2f}" if buy_vol else "")
            print(f"  Edge per unit sold: {(sell_revenue/sell_vol - fair):.2f}" if sell_vol else "")

        elif product == "TOMATOES":
            # For random walk, need to know final mid to calculate
            # Let's just show trade distribution
            buy_prices = [t['price'] for t in buys]
            sell_prices = [t['price'] for t in sells]

            if buy_prices:
                print(f"\n  Buy price distribution:")
                price_dist = defaultdict(int)
                vol_dist = defaultdict(int)
                for t in buys:
                    price_dist[t['price']] += 1
                    vol_dist[t['price']] += t['quantity']
                # Show relative to fair value at time of trade
                # We don't have fair, but we know width=5
                # Buy should be at fair - 5 (make) or at ask (take)

            # Analyze takes vs makes
            print(f"\n  --- Take vs Make Analysis ---")
            # Takes: we cross the spread to fill
            # Makes: someone else fills our resting order
            # Takes happen when we buy at ask or sell at bid
            # For TOMATOES, our take threshold: buy at price <= fair, sell at price >= fair
            # But we need to know what the book looked like
            # Instead, let's look at the trade patterns

            # Looking at trade prices: if we buy LOW (below mid), it's likely a take
            # If we buy above a certain threshold, it's a make fill

            # Better approach: look at trade quantity patterns
            # Bot fills our order: qty comes from bot order, price is our price
            # We fill bot order: qty from bot order, price is bot price

            print(f"\n  Buy trade sizes:")
            size_dist = defaultdict(int)
            for t in buys:
                size_dist[t['quantity']] += 1
            for s in sorted(size_dist.keys()):
                print(f"    qty={s}: {size_dist[s]} trades")

            print(f"\n  Sell trade sizes:")
            size_dist = defaultdict(int)
            for t in sells:
                size_dist[t['quantity']] += 1
            for s in sorted(size_dist.keys()):
                print(f"    qty={s}: {size_dist[s]} trades")

        # Trade timing
        print(f"\n  Trade timing:")
        timestamps = [t['timestamp'] for t in tlist]
        intervals = [timestamps[i+1] - timestamps[i] for i in range(len(timestamps)-1) if timestamps[i+1] > timestamps[i]]
        if intervals:
            print(f"  Inter-trade intervals: mean={sum(intervals)/len(intervals):.0f}, min={min(intervals)}, max={max(intervals)}")

        # Are there clusters of trades?
        unique_ts = set(timestamps)
        ts_counts = defaultdict(int)
        for ts in timestamps:
            ts_counts[ts] += 1
        multi_trade_ts = sum(1 for c in ts_counts.values() if c > 1)
        max_trades_per_ts = max(ts_counts.values())
        print(f"  Unique timestamps: {len(unique_ts)}")
        print(f"  Multi-trade timestamps: {multi_trade_ts}")
        print(f"  Max trades per timestamp: {max_trades_per_ts}")

        # Show first 20 trades
        print(f"\n  First 20 trades:")
        for t in tlist[:20]:
            side = "BUY" if t['buyer'] == 'SUBMISSION' else "SELL"
            print(f"    t={t['timestamp']:6d}: {side:4s} {t['quantity']}x @ {t['price']:.0f}")

        # Show last 10 trades
        print(f"\n  Last 10 trades:")
        for t in tlist[-10:]:
            side = "BUY" if t['buyer'] == 'SUBMISSION' else "SELL"
            print(f"    t={t['timestamp']:6d}: {side:4s} {t['quantity']}x @ {t['price']:.0f}")


if __name__ == "__main__":
    main()
