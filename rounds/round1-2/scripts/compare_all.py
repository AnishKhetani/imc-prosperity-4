import csv, statistics

runs = [
    ('BASELINE', 'submission_run2'),
    ('C1:PosBias', 'v1'),
    ('C2:SpreadComp', 'v2_redo'),
    ('C3:TwoLevel', 'v3_100'),
    ('C1+C2', 'v12'),
    ('C1+C3', 'v13'),
    ('C2+C3', 'v23'),
    ('C1+C2+C3', 'v123_redo'),
]

base = r'.\mcbacktester\tmp'

print(f'{"Variant":16s} {"Mean":>8s} {"Std":>7s} {"Sharpe":>7s} {"5th":>8s} {"95th":>8s} | {"EM Mean":>7s} {"EM Std":>6s} {"TOM Mean":>8s} {"TOM Std":>7s}')
print('-' * 110)

for label, run_name in runs:
    try:
        with open(f'{base}/{run_name}/run_summary.csv') as f:
            rows = list(csv.DictReader(f))
        t = [float(r['total_pnl']) for r in rows]
        e = [float(r['emerald_pnl']) for r in rows]
        m = [float(r['tomato_pnl']) for r in rows]
        mn = statistics.mean(t)
        sd = statistics.stdev(t)
        s = sorted(t)
        p5 = s[int(len(s)*0.05)]
        p95 = s[int(len(s)*0.95)-1]
        em_mn = statistics.mean(e)
        em_sd = statistics.stdev(e)
        tom_mn = statistics.mean(m)
        tom_sd = statistics.stdev(m)
        sharpe = mn / sd if sd > 0 else 0
        delta = mn - 13652  # vs baseline
        print(f'{label:16s} {mn:8.0f} {sd:7.0f} {sharpe:7.1f} {p5:8.0f} {p95:8.0f} | {em_mn:7.0f} {em_sd:6.0f} {tom_mn:8.0f} {tom_sd:7.0f}  (delta={delta:+.0f})')
    except Exception as ex:
        print(f'{label:16s} FAILED: {ex}')
