"""Check position trajectory and skew/heavy zone activation in baseline."""
import json

trades = json.load(open('logs/44861/44861.log'))['tradeHistory']
tom = sorted(
    [t for t in trades if t['symbol'] == 'TOMATOES'
     and (t['buyer'] == 'SUBMISSION' or t['seller'] == 'SUBMISSION')],
    key=lambda x: x['timestamp']
)

pos = 0
max_abs = 0
for t in tom:
    if t['buyer'] == 'SUBMISSION':
        pos += t['quantity']
    else:
        pos -= t['quantity']
    max_abs = max(max_abs, abs(pos))
    ratio = pos / 80
    flag = ' <<< HEAVY' if abs(ratio) > 0.6 else (' << SKEW' if abs(ratio) > 0.15 else '')
    side = 'BUY' if t['buyer'] == 'SUBMISSION' else 'SELL'
    print(f"  t={t['timestamp']:6d} {side:4s} {t['quantity']}x -> pos={pos:+3d} (ratio={ratio:+.2f}){flag}")

print(f"\nMax abs position: {max_abs}")
print(f"Position limit: 80")
print(f"Final position: {pos}")
