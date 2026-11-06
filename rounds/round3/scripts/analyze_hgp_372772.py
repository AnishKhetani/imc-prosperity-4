import json

with open(r'.\logs\372772\372772.json', encoding='utf-8') as f:
    d = json.load(f)

acts = d.get('activitiesLog', '')
lines = acts.strip().split('\n')

print('Total activitiesLog lines:', len(lines))
print('Header:', lines[0])

# Extract HGP data
hgp = []
for line in lines[1:]:
    parts = line.split(';')
    if len(parts) >= 17 and 'HYDROGEL' in parts[2]:
        try:
            ts = int(parts[1])
            mid = float(parts[15]) if parts[15] else 0.0
            pnl = float(parts[16]) if parts[16] else 0.0
            hgp.append((ts, mid, pnl))
        except Exception as e:
            pass

print('HGP rows found:', len(hgp))
if hgp:
    print('First 3:', hgp[:3])
    print('Last 3:', hgp[-3:])

# Show full range around worst period
print('\nHGP ts 85000-95000:')
print('ts       | mid     | pnl      | dpnl      | dmid')
prev = None
for ts, mid, pnl in hgp:
    if 85000 <= ts <= 95000:
        if prev:
            print('%7d  | %7.1f  | %8.1f  | %9.1f | %9.1f' % (
                ts, mid, pnl, pnl - prev[1], mid - prev[0]))
        else:
            print('%7d  | %7.1f  | %8.1f  |         0 |         0' % (ts, mid, pnl))
        prev = (mid, pnl)

# Compute HGP price range
if hgp:
    mids = [m for _, m, _ in hgp]
    print('\nHGP overall: min_mid=%.1f, max_mid=%.1f, range=%.1f' % (min(mids), max(mids), max(mids)-min(mids)))

# Build graphLog dict for comparison
graph = d.get('graphLog', '')
glines = graph.strip().split('\n')[1:]
gpts = {int(r.split(';')[0]): float(r.split(';')[1]) for r in glines if r}

# Align HGP mid with total PnL changes
print('\nHGP mid vs cumulative PnL at key timestamps:')
print('ts       | hgp_mid | cumPnL')
hgp_dict = {ts: (mid, pnl) for ts, mid, pnl in hgp}
for ts in sorted(gpts):
    if ts in hgp_dict and ts % 2000 == 0:
        mid, hpnl = hgp_dict[ts]
        print('%7d  | %7.1f  | %8.1f (hgp_pnl=%.1f)' % (ts, mid, gpts[ts], hpnl))
