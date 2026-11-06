"""
Definitive fill analysis from tradeHistory — this is the actual trade record.
Analyze both sim 44861 (baseline, PnL=2175) and 44953 (WIDTH=6, PnL=1814).
"""
import json
from collections import defaultdict

def load_trades(path):
    with open(path) as f:
        data = json.load(f)
    return data['tradeHistory']

trades_861 = load_trades('logs/44861/44861.log')
trades_953 = load_trades('logs/44953/44953.log')

for label, trades in [("44861 (WIDTH=5, PnL=2175)", trades_861), ("44953 (WIDTH=6, PnL=1814)", trades_953)]:
    print("=" * 80)
    print(f"SIM {label}")
    print("=" * 80)
    
    em_trades = [t for t in trades if t['symbol'] == 'EMERALDS']
    tom_trades = [t for t in trades if t['symbol'] == 'TOMATOES']
    
    print(f"\nTotal trades: {len(trades)}")
    print(f"EMERALDS: {len(em_trades)}, TOMATOES: {len(tom_trades)}")
    
    # ── EMERALDS ──
    print(f"\n--- EMERALDS ({len(em_trades)} trades) ---")
    em_buys = [t for t in em_trades if t['buyer'] == 'SUBMISSION']
    em_sells = [t for t in em_trades if t['seller'] == 'SUBMISSION']
    
    em_buy_pnl = sum(t['quantity'] * (10000 - t['price']) for t in em_buys)
    em_sell_pnl = sum(t['quantity'] * (t['price'] - 10000) for t in em_sells)
    em_net_pos = sum(t['quantity'] for t in em_buys) - sum(t['quantity'] for t in em_sells)
    
    print(f"  Buys: {len(em_buys)} trades, {sum(t['quantity'] for t in em_buys)} units")
    print(f"  Sells: {len(em_sells)} trades, {sum(t['quantity'] for t in em_sells)} units")
    print(f"  Net position: {em_net_pos}")
    print(f"  Buy edge PnL: {em_buy_pnl:.0f}")
    print(f"  Sell edge PnL: {em_sell_pnl:.0f}")
    print(f"  Total edge PnL: {em_buy_pnl + em_sell_pnl:.0f}")
    
    # Price distribution
    buy_prices = defaultdict(int)
    sell_prices = defaultdict(int)
    for t in em_buys:
        buy_prices[t['price']] += t['quantity']
    for t in em_sells:
        sell_prices[t['price']] += t['quantity']
    
    print(f"  Buy price distribution: {dict(sorted(buy_prices.items()))}")
    print(f"  Sell price distribution: {dict(sorted(sell_prices.items()))}")
    
    # ── TOMATOES ──
    print(f"\n--- TOMATOES ({len(tom_trades)} trades) ---")
    tom_buys = [t for t in tom_trades if t['buyer'] == 'SUBMISSION']
    tom_sells = [t for t in tom_trades if t['seller'] == 'SUBMISSION']
    
    print(f"  Buys: {len(tom_buys)} trades, {sum(t['quantity'] for t in tom_buys)} units")
    print(f"  Sells: {len(tom_sells)} trades, {sum(t['quantity'] for t in tom_sells)} units")
    
    # Classify: take vs make
    # Take buys: buyer=SUBMISSION, price = bot's ask level (we're crossing the spread)
    # Make buys: buyer=SUBMISSION, price = our bid level (bot crosses to us)
    # We can tell by comparing trade price to the typical bot spread
    
    # Actually with WIDTH=5 and MAKE:
    #   our bid = fair - 5, our ask = fair + 5
    #   takes: buy at bot_ask (high price), sell at bot_bid (low price)  
    #   makes: buy at our_bid (lower price), sell at our_ask (higher price)
    # Given bot spread ~13-14, if we buy at a price that's close to the bot's ask
    # (mid + 6 or 7), that's a take. If we buy at mid - 5 or lower, that's a make.
    
    # Simplification: look at buy/sell quantities per trade
    buy_qtys = defaultdict(int)
    sell_qtys = defaultdict(int)
    for t in tom_buys:
        buy_qtys[t['quantity']] += 1
    for t in tom_sells:
        sell_qtys[t['quantity']] += 1
    
    print(f"  Buy qty distribution: {dict(sorted(buy_qtys.items()))}")
    print(f"  Sell qty distribution: {dict(sorted(sell_qtys.items()))}")
    
    # Net position over time
    position = 0
    max_pos = 0
    min_pos = 0
    pos_trajectory = []
    for t in sorted(tom_trades, key=lambda x: x['timestamp']):
        if t['buyer'] == 'SUBMISSION':
            position += t['quantity']
        else:
            position -= t['quantity']
        max_pos = max(max_pos, position)
        min_pos = min(min_pos, position)
        pos_trajectory.append((t['timestamp'], position))
    
    print(f"  Position range: [{min_pos}, {max_pos}]")
    print(f"  Final position: {position}")
    
    # Position at regular intervals
    print(f"  Position at intervals:")
    for target_ts in range(0, 200001, 20000):
        closest = min(pos_trajectory, key=lambda x: abs(x[0] - target_ts))
        print(f"    t={target_ts:6d}: pos={closest[1]:+4d} (actual t={closest[0]})")
    
    # Cash flow analysis
    total_buy_cost = sum(t['price'] * t['quantity'] for t in tom_buys)
    total_sell_revenue = sum(t['price'] * t['quantity'] for t in tom_sells)
    total_buy_qty = sum(t['quantity'] for t in tom_buys)
    total_sell_qty = sum(t['quantity'] for t in tom_sells)
    
    avg_buy = total_buy_cost / total_buy_qty if total_buy_qty > 0 else 0
    avg_sell = total_sell_revenue / total_sell_qty if total_sell_qty > 0 else 0
    
    print(f"\n  Total buy cost: {total_buy_cost:.0f} ({total_buy_qty} units, avg {avg_buy:.2f})")
    print(f"  Total sell revenue: {total_sell_revenue:.0f} ({total_sell_qty} units, avg {avg_sell:.2f})")
    print(f"  Avg spread earned: {avg_sell - avg_buy:.2f}")
    print(f"  Cash PnL: {total_sell_revenue - total_buy_cost:.0f}")
    print(f"  + Liquidation value (pos={position} * mid=4996.5): {position * 4996.5:.1f}")
    print(f"  = Total: {total_sell_revenue - total_buy_cost + position * 4996.5:.1f}")
    
    # ── Trade timing analysis ──
    print(f"\n  Trade timing (fills per 20k timestamp window):")
    for start in range(0, 200000, 20000):
        end = start + 20000
        window_trades = [t for t in tom_trades if start <= t['timestamp'] < end]
        window_buys = [t for t in window_trades if t['buyer'] == 'SUBMISSION']
        window_sells = [t for t in window_trades if t['seller'] == 'SUBMISSION']
        if window_trades:
            print(f"    [{start:6d}-{end:6d}): {len(window_trades):3d} trades ({len(window_buys)} buys, {len(window_sells)} sells)")

# ═══════════════════════════════════════════════════════════════
#  COMPARE: Per-trade price comparison between sims
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("TRADE-BY-TRADE COMPARISON: 44861 vs 44953 (TOMATOES only)")
print("=" * 80)

tom_861 = sorted([t for t in trades_861 if t['symbol'] == 'TOMATOES'], key=lambda x: x['timestamp'])
tom_953 = sorted([t for t in trades_953 if t['symbol'] == 'TOMATOES'], key=lambda x: x['timestamp'])

# Match by timestamp
ts_861 = {t['timestamp']: t for t in tom_861}
ts_953 = {t['timestamp']: t for t in tom_953}
all_ts = sorted(set(ts_861.keys()) | set(ts_953.keys()))

only_861 = 0
only_953 = 0
both = 0
price_diffs = []

for ts in all_ts:
    in_861 = ts in ts_861
    in_953 = ts in ts_953
    if in_861 and in_953:
        both += 1
        p_diff = ts_953[ts]['price'] - ts_861[ts]['price']
        q_diff = ts_953[ts]['quantity'] - ts_861[ts]['quantity']
        if abs(p_diff) > 0 or abs(q_diff) > 0:
            price_diffs.append((ts, p_diff, q_diff))
    elif in_861:
        only_861 += 1
    else:
        only_953 += 1

print(f"Trades in both: {both}")
print(f"Only in 44861 (WIDTH=5): {only_861}")
print(f"Only in 44953 (WIDTH=6): {only_953}")
print(f"Price/qty differences in matched trades: {len(price_diffs)}")

if price_diffs:
    print(f"\nFirst 15 differences:")
    for ts, pd, qd in price_diffs[:15]:
        t861 = ts_861.get(ts, {})
        t953 = ts_953.get(ts, {})
        side861 = 'BUY' if t861.get('buyer') == 'SUBMISSION' else 'SELL'
        side953 = 'BUY' if t953.get('buyer') == 'SUBMISSION' else 'SELL'
        print(f"  t={ts:6d}: 861={t861.get('price',0):.0f}x{t861.get('quantity',0)}({side861}), 953={t953.get('price',0):.0f}x{t953.get('quantity',0)}({side953}), Δprice={pd:+.0f}, Δqty={qd:+d}")

# List trades only in 44861 (missed with WIDTH=6)
print(f"\nTrades ONLY in 44861 (lost with WIDTH=6):")
for ts in sorted(ts_861.keys()):
    if ts not in ts_953:
        t = ts_861[ts]
        side = 'BUY' if t['buyer'] == 'SUBMISSION' else 'SELL'
        print(f"  t={ts:6d}: {side} {t['quantity']}x @ {t['price']:.0f}")

print("\n\nDONE.")
