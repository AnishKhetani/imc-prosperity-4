"""
Corrected analysis — fix position tracking (exclude bot-to-bot trades).
Also: quantify the exact impact of each strategy parameter.
"""
import json
from collections import defaultdict

def load(path):
    with open(path) as f:
        return json.load(f)

data_861 = load('logs/44861/44861.log')
data_953 = load('logs/44953/44953.log')

for label, data in [("44861 (WIDTH=5)", data_861), ("44953 (WIDTH=6)", data_953)]:
    trades = data['tradeHistory']
    tom = sorted([t for t in trades if t['symbol'] == 'TOMATOES'], key=lambda x: x['timestamp'])
    
    # Correct position: only count OUR trades
    our_buys = [t for t in tom if t['buyer'] == 'SUBMISSION']
    our_sells = [t for t in tom if t['seller'] == 'SUBMISSION']
    bot_trades = [t for t in tom if t['buyer'] != 'SUBMISSION' and t['seller'] != 'SUBMISSION']
    
    buy_qty = sum(t['quantity'] for t in our_buys)
    sell_qty = sum(t['quantity'] for t in our_sells)
    net_pos = buy_qty - sell_qty
    
    buy_cost = sum(t['price'] * t['quantity'] for t in our_buys)
    sell_rev = sum(t['price'] * t['quantity'] for t in our_sells)
    
    print(f"\n{'='*60}")
    print(f" {label}")
    print(f"{'='*60}")
    print(f"Our buys:  {len(our_buys)} trades, {buy_qty} units, cost={buy_cost:.0f}")
    print(f"Our sells: {len(our_sells)} trades, {sell_qty} units, rev={sell_rev:.0f}")
    print(f"Bot-only:  {len(bot_trades)} trades")
    print(f"Net position: {net_pos}")
    print(f"Cash flow: {sell_rev - buy_cost:.0f}")
    
    # Reconstruct correct position trajectory
    pos = 0
    trajectory = []
    for t in tom:
        if t['buyer'] == 'SUBMISSION':
            pos += t['quantity']
        elif t['seller'] == 'SUBMISSION':
            pos -= t['quantity']
        # skip bot-only trades
        trajectory.append((t['timestamp'], pos, t['buyer'] == 'SUBMISSION' or t['seller'] == 'SUBMISSION'))
    
    print(f"Correct final pos: {pos}")
    print(f"Position range: [{min(p for _,p,_ in trajectory)}, {max(p for _,p,_ in trajectory)}]")
    
    # Edge per fill
    for t in our_buys:
        pass  # each buy at price P earns us (eventual_sell_or_liquidation - P)
    
    # Avg buy/sell prices
    avg_buy = buy_cost / buy_qty if buy_qty > 0 else 0
    avg_sell = sell_rev / sell_qty if sell_qty > 0 else 0
    print(f"Avg buy price: {avg_buy:.2f}")
    print(f"Avg sell price: {avg_sell:.2f}")
    print(f"Avg spread earned: {avg_sell - avg_buy:.2f}")
    
    # Realized PnL (round-trips) + unrealized (open position)
    # Mark-to-market PnL = cash + pos * mid(final)
    final_mid = 4996.5  # both sims end at same mid
    realized_mtm = (sell_rev - buy_cost) + pos * final_mid
    print(f"Total PnL (cash + {pos}*{final_mid}): {realized_mtm:.2f}")
    
    # Per-fill analysis
    print(f"\nAll our fills:")
    for t in sorted(our_buys + our_sells, key=lambda x: x['timestamp']):
        side = 'BUY' if t['buyer'] == 'SUBMISSION' else 'SELL'
        print(f"  t={t['timestamp']:6d} {side:4s} {t['quantity']}x @ {t['price']:.0f}")

# ═══════════════════════════════════════════════════════════════
#  SIDE-FLIP ANALYSIS: Which trades changed sides between sims?
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*60}")
print(f" SIDE FLIP ANALYSIS (44861 vs 44953)")
print(f"{'='*60}")

tom_861 = sorted([t for t in data_861['tradeHistory'] if t['symbol'] == 'TOMATOES'], key=lambda x: x['timestamp'])
tom_953 = sorted([t for t in data_953['tradeHistory'] if t['symbol'] == 'TOMATOES'], key=lambda x: x['timestamp'])

# Match by timestamp (may have multiples, handle that)
by_ts_861 = defaultdict(list)
by_ts_953 = defaultdict(list)
for t in tom_861:
    by_ts_861[t['timestamp']].append(t)
for t in tom_953:
    by_ts_953[t['timestamp']].append(t)

def get_side(trade):
    if trade['buyer'] == 'SUBMISSION':
        return 'BUY'
    elif trade['seller'] == 'SUBMISSION':
        return 'SELL'
    return 'BOT'

all_ts = sorted(set(by_ts_861.keys()) | set(by_ts_953.keys()))

flips = 0
gained = 0
lost = 0
for ts in all_ts:
    trades_861 = by_ts_861.get(ts, [])
    trades_953 = by_ts_953.get(ts, [])
    
    sides_861 = [get_side(t) for t in trades_861]
    sides_953 = [get_side(t) for t in trades_953]
    
    # Check for participation changes
    our_861 = any(s != 'BOT' for s in sides_861)
    our_953 = any(s != 'BOT' for s in sides_953)
    
    if our_861 and not our_953:
        lost += 1
        t = [t for t in trades_861 if get_side(t) != 'BOT'][0]
        print(f"  LOST:   t={ts:6d} was {get_side(t)} {t['quantity']}x @ {t['price']:.0f}")
    elif not our_861 and our_953:
        gained += 1
        t = [t for t in trades_953 if get_side(t) != 'BOT'][0]
        print(f"  GAINED: t={ts:6d} now {get_side(t)} {t['quantity']}x @ {t['price']:.0f}")
    elif our_861 and our_953:
        # Check if side flipped
        our_side_861 = [s for s in sides_861 if s != 'BOT']
        our_side_953 = [s for s in sides_953 if s != 'BOT']
        if our_side_861 and our_side_953 and our_side_861[0] != our_side_953[0]:
            flips += 1
            t861 = [t for t in trades_861 if get_side(t) != 'BOT'][0]
            t953 = [t for t in trades_953 if get_side(t) != 'BOT'][0]
            print(f"  FLIPPED: t={ts:6d} {get_side(t861)}→{get_side(t953)} (861: {t861['price']:.0f}x{t861['quantity']}, 953: {t953['price']:.0f}x{t953['quantity']})")

print(f"\nSummary: {lost} lost, {gained} gained, {flips} side-flips")
print(f"Net fill change: {gained - lost}")

print("\n\nDONE.")
