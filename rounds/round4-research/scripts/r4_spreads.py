import csv, statistics
from collections import defaultdict

for day in [1, 2, 3]:
    sp = defaultdict(list); mids = defaultdict(list); n = defaultdict(int)
    f = open(f'backtester_data/round4/prices_round_4_day_{day}.csv')
    for r in csv.DictReader(f, delimiter=';'):
        s = r['product']; n[s] += 1
        try:
            b = float(r['bid_price_1']); a = float(r['ask_price_1'])
            sp[s].append(a - b); mids[s].append((a+b)/2)
        except Exception:
            pass
    print(f"\n=== DAY {day} ===")
    print(f"{'sym':>22} {'n':>5} {'spread':>8} {'mid_mean':>10} {'mid_min':>9} {'mid_max':>9}")
    for s in sorted(sp):
        if not sp[s]: continue
        print(f"{s:>22} {n[s]:>5} {statistics.mean(sp[s]):>8.2f} {statistics.mean(mids[s]):>10.1f} {min(mids[s]):>9.1f} {max(mids[s]):>9.1f}")
