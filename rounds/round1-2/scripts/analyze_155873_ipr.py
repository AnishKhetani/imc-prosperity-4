"""
Deep analysis of IPR fill execution logic from platform log 155873.
Questions:
  1. How does position evolve over time?
  2. Are fills asymmetric (more sells than buys) due to drift?
  3. How much PnL is lost to adverse selection?
  4. What would different strategies have earned?
"""
import json
import re
from collections import defaultdict

LOG_PATH = r'.\logs\155873\155873.json'
RAW_LOG_PATH = r'.\logs\155873\155873.log'

with open(LOG_PATH) as f:
    d = json.load(f)
with open(RAW_LOG_PATH) as f:
    raw = json.loads(f.read())

# ── 1. Extract timestamped trades from tradeHistory ──
all_trades = []
for trade in raw['tradeHistory']:
    if trade['symbol'] != 'INTARIAN_PEPPER_ROOT':
        continue
    is_our_buy = trade['buyer'] == 'SUBMISSION'
    is_our_sell = trade['seller'] == 'SUBMISSION'
    if is_our_buy or is_our_sell:
        all_trades.append({
            'ts': trade['timestamp'],
            'side': 'BUY' if is_our_buy else 'SELL',
            'price': trade['price'],
            'qty': trade['quantity'],
        })

all_trades.sort(key=lambda t: t['ts'])
print(f"IPR trades: {len(all_trades)}")

# ── 2. Reconstruct position over time ──
position = 0
position_history = [(0, 0)]  # (timestamp, position)
pnl_cash = 0  # Cash PnL from trades

buy_count = 0
sell_count = 0
buy_qty_total = 0
sell_qty_total = 0

for t in all_trades:
    if t['side'] == 'BUY':
        position += t['qty']
        pnl_cash -= t['price'] * t['qty']
        buy_count += 1
        buy_qty_total += t['qty']
    else:
        position -= t['qty']
        pnl_cash += t['price'] * t['qty']
        sell_count += 1
        sell_qty_total += t['qty']
    position_history.append((t['ts'], position))

print(f"\nBuys:  {buy_count} trades, {buy_qty_total} qty")
print(f"Sells: {sell_count} trades, {sell_qty_total} qty")
print(f"Final position: {position}")
print(f"Cash PnL from trades: {pnl_cash:.2f}")

# ── 3. Parse mid-price timeline from activities log ──
lines = d['activitiesLog'].strip().split('\n')
ipr_mids = {}
ipr_books = {}
for line in lines[1:]:
    parts = line.split(';')
    if len(parts) > 15 and parts[2] == 'INTARIAN_PEPPER_ROOT':
        ts = int(parts[1])
        mid_str = parts[15]
        bid1 = parts[3]
        ask1 = parts[9]
        if mid_str:
            ipr_mids[ts] = float(mid_str)
        if bid1 and ask1:
            ipr_books[ts] = (float(bid1), float(ask1))

# End-of-day mark
final_mid = ipr_mids[max(ipr_mids.keys())]
mark_to_market = position * final_mid
total_pnl = pnl_cash + mark_to_market
print(f"Final mid: {final_mid}")
print(f"Mark-to-market ({position} * {final_mid}): {mark_to_market:.2f}")
print(f"Total PnL (cash + mtm): {total_pnl:.2f}")

# ── 4. Analyze each fill relative to fair value at that tick ──
print("\n" + "="*70)
print("FILL-BY-FILL ANALYSIS (every trade vs. mid at that tick)")
print("="*70)
adverse_pnl = 0
for t in all_trades:
    # Find closest mid
    closest_ts = min(ipr_mids.keys(), key=lambda k: abs(k - t['ts']))
    mid = ipr_mids[closest_ts]
    
    if t['side'] == 'BUY':
        edge = mid - t['price']  # positive = bought below mid = good
    else:
        edge = t['price'] - mid  # positive = sold above mid = good
    
    adverse_pnl += edge * t['qty']
    
    print(f"  t={t['ts']:6d} {t['side']:4s} {t['qty']:3d} @ {t['price']:.0f}  "
          f"mid={mid:.1f}  edge={edge:+.1f}  edge*qty={edge*t['qty']:+.1f}")

print(f"\nTotal edge-weighted fill quality: {adverse_pnl:+.1f}")

# ── 5. Position vs mid-price over time (adverse selection) ──
print("\n" + "="*70)
print("POSITION EVOLUTION vs MID-PRICE")
print("="*70)
# Sample position at regular intervals
checkpoints = list(range(0, 100001, 10000))
pos_idx = 0
for cp in checkpoints:
    # Find position at this timestamp
    pos_at_cp = 0
    for ts, pos in position_history:
        if ts <= cp:
            pos_at_cp = pos
        else:
            break
    
    mid_at_cp = ipr_mids.get(cp, None)
    if mid_at_cp is None:
        # Find closest
        closest = min(ipr_mids.keys(), key=lambda k: abs(k - cp))
        mid_at_cp = ipr_mids[closest]
    
    print(f"  t={cp:6d}  pos={pos_at_cp:+4d}  mid={mid_at_cp:.1f}")

# ── 6. Analyze what the fills tell us about WIDTH/SKEW ──
print("\n" + "="*70)
print("FILL TIMING ANALYSIS")
print("="*70)

# Group fills into time buckets
buckets = defaultdict(lambda: {'buys': 0, 'sells': 0, 'buy_qty': 0, 'sell_qty': 0})
for t in all_trades:
    bucket = (t['ts'] // 10000) * 10000
    if t['side'] == 'BUY':
        buckets[bucket]['buys'] += 1
        buckets[bucket]['buy_qty'] += t['qty']
    else:
        buckets[bucket]['sells'] += 1
        buckets[bucket]['sell_qty'] += t['qty']

print(f"{'Period':>12s}  {'Buys':>5s}  {'BuyQty':>6s}  {'Sells':>5s}  {'SellQty':>7s}  {'Net':>5s}")
for bucket in sorted(buckets.keys()):
    b = buckets[bucket]
    net = b['buy_qty'] - b['sell_qty']
    print(f"  {bucket:6d}-{bucket+9999:5d}  {b['buys']:5d}  {b['buy_qty']:6d}  "
          f"{b['sells']:5d}  {b['sell_qty']:7d}  {net:+5d}")

# ── 7. Hypothetical: what if we also TOOK profitable crosses? ──
print("\n" + "="*70)
print("HYPOTHETICAL: TAKING OPPORTUNITIES")
print("="*70)
# How often is the best ask below wmid or best bid above wmid?
take_buy_opps = 0
take_sell_opps = 0
take_buy_profit = 0
take_sell_profit = 0

for ts in sorted(ipr_books.keys()):
    bid1, ask1 = ipr_books[ts]
    mid = ipr_mids.get(ts, (bid1 + ask1) / 2)
    
    # Conservative take: price must be at least 1 tick favorable
    if ask1 < mid - 1:
        take_buy_opps += 1
        take_buy_profit += mid - ask1
    if bid1 > mid + 1:
        take_sell_opps += 1
        take_sell_profit += bid1 - mid

print(f"Take-buy opportunities (ask < mid-1): {take_buy_opps} ticks, est profit: {take_buy_profit:.1f}")
print(f"Take-sell opportunities (bid > mid+1): {take_sell_opps} ticks, est profit: {take_sell_profit:.1f}")

# ── 8. Hypothetical: wider/narrower WIDTH comparison ──
print("\n" + "="*70)
print("WIDTH IMPACT ON FILLS")
print("="*70)
for test_width in [2, 3, 4, 5, 6]:
    would_fill_bid = 0
    would_fill_ask = 0
    for ts in sorted(ipr_books.keys()):
        bid1, ask1 = ipr_books[ts]
        mid = ipr_mids.get(ts, (bid1 + ask1) / 2)
        our_bid = round(mid) - test_width
        our_ask = round(mid) + test_width
        # Our bid fills when best ask <= our_bid
        if ask1 <= our_bid:
            would_fill_bid += 1
        # Our ask fills when best bid >= our_ask
        if bid1 >= our_ask:
            would_fill_ask += 1
    print(f"  WIDTH={test_width}: bid_fills={would_fill_bid:3d}, ask_fills={would_fill_ask:3d}, "
          f"ratio={would_fill_ask/max(would_fill_bid,1):.2f}")

# ── 9. Asymmetric width analysis ──
print("\n" + "="*70)
print("ASYMMETRIC WIDTH: tighter bid (buy more) vs wider ask")
print("="*70)
for bid_w, ask_w in [(3, 5), (3, 6), (4, 5), (4, 6), (2, 6), (3, 7)]:
    would_fill_bid = 0
    would_fill_ask = 0
    for ts in sorted(ipr_books.keys()):
        bid1, ask1 = ipr_books[ts]
        mid = ipr_mids.get(ts, (bid1 + ask1) / 2)
        our_bid = round(mid) - bid_w
        our_ask = round(mid) + ask_w
        if ask1 <= our_bid:
            would_fill_bid += 1
        if bid1 >= our_ask:
            would_fill_ask += 1
    print(f"  bid_w={bid_w} ask_w={ask_w}: bid_fills={would_fill_bid:3d}, ask_fills={would_fill_ask:3d}, "
          f"ratio={would_fill_ask/max(would_fill_bid,1):.2f}")
