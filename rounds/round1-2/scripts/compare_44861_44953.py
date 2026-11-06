"""Deep comparison: what exactly changed between 44861 (WIDTH=5) and 44953 (WIDTH=6)?"""
import json, csv, io
from collections import defaultdict

def load_trades(sim):
    with open(f'logs/{sim}/{sim}.log', 'r') as f:
        data = json.load(f)
    return data['tradeHistory']

def load_activities(sim):
    with open(f'logs/{sim}/{sim}.json', 'r') as f:
        data = json.load(f)
    reader = csv.DictReader(io.StringIO(data['activitiesLog']), delimiter=';')
    return list(reader)

# Compare fill details
for sim, width in [('44861', 5), ('44953', 6)]:
    trades = load_trades(sim)
    tom = [t for t in trades if t['symbol'] == 'TOMATOES']
    our = [t for t in tom if t['buyer'] == 'SUBMISSION' or t['seller'] == 'SUBMISSION']
    bot_bot = [t for t in tom if t['buyer'] != 'SUBMISSION' and t['seller'] != 'SUBMISSION']

    buys = [t for t in our if t['buyer'] == 'SUBMISSION']
    sells = [t for t in our if t['seller'] == 'SUBMISSION']

    buy_vol = sum(t['quantity'] for t in buys)
    sell_vol = sum(t['quantity'] for t in sells)
    pos = buy_vol - sell_vol

    buy_cost = sum(t['price'] * t['quantity'] for t in buys)
    sell_rev = sum(t['price'] * t['quantity'] for t in sells)

    print(f"\n{'='*60}")
    print(f"Sim {sim} (WIDTH={width})")
    print(f"  Our fills: {len(our)} ({len(buys)} buys + {len(sells)} sells)")
    print(f"  Bot-bot trades: {len(bot_bot)}")
    print(f"  Buy vol: {buy_vol}, Sell vol: {sell_vol}, Final pos: {pos}")
    print(f"  Avg buy: {buy_cost/buy_vol:.2f}, Avg sell: {sell_rev/sell_vol:.2f}")
    print(f"  Spread earned: {sell_rev/sell_vol - buy_cost/buy_vol:.2f}")
    
    # Calculate PnL = sell_rev - buy_cost + pos * final_mid
    acts = load_activities(sim)
    tom_acts = [r for r in acts if r['product'] == 'TOMATOES']
    last = tom_acts[-1]
    final_mid = (float(last['bid_price_1']) + float(last['ask_price_1'])) / 2
    realized_pnl = sell_rev - buy_cost + pos * final_mid
    print(f"  Final mid: {final_mid:.1f}")
    print(f"  Realized PnL (incl pos@mid): {realized_pnl:.2f}")

    # Show all our fills with timestamps to find missing fills
    print(f"\n  All our fills:")
    for t in our:
        side = 'BUY' if t['buyer'] == 'SUBMISSION' else 'SELL'
        print(f"    t={t['timestamp']:6d}: {side:4s} {t['quantity']}x@{t['price']:.0f}")

# Now find fills present in 44861 but missing in 44953
print(f"\n{'='*60}")
print("MISSING FILLS (in 44861 but not 44953):")
t_44861 = load_trades('44861')
t_44953 = load_trades('44953')
our_44861 = {t['timestamp']: t for t in t_44861 if t['symbol'] == 'TOMATOES' and (t['buyer'] == 'SUBMISSION' or t['seller'] == 'SUBMISSION')}
our_44953 = {t['timestamp']: t for t in t_44953 if t['symbol'] == 'TOMATOES' and (t['buyer'] == 'SUBMISSION' or t['seller'] == 'SUBMISSION')}

for ts in sorted(our_44861.keys()):
    if ts not in our_44953:
        t = our_44861[ts]
        side = 'BUY' if t['buyer'] == 'SUBMISSION' else 'SELL'
        print(f"  MISSING t={ts:6d}: {side:4s} {t['quantity']}x@{t['price']:.0f}")

print(f"\nNEW FILLS (in 44953 but not 44861):")
for ts in sorted(our_44953.keys()):
    if ts not in our_44861:
        t = our_44953[ts]
        side = 'BUY' if t['buyer'] == 'SUBMISSION' else 'SELL'
        print(f"  NEW    t={ts:6d}: {side:4s} {t['quantity']}x@{t['price']:.0f}")

print(f"\nPRICE CHANGES (same timestamp, different price):")
for ts in sorted(set(our_44861.keys()) & set(our_44953.keys())):
    t1 = our_44861[ts]
    t2 = our_44953[ts]
    if t1['price'] != t2['price']:
        side1 = 'BUY' if t1['buyer'] == 'SUBMISSION' else 'SELL'
        side2 = 'BUY' if t2['buyer'] == 'SUBMISSION' else 'SELL'
        diff = t2['price'] - t1['price']
        print(f"  t={ts:6d}: {side1} {t1['price']:.0f}->{t2['price']:.0f} ({diff:+.0f})")
