import json
import sys
from pathlib import Path

LOG = Path(r".\logs\487874\487874.json")
d = json.load(open(LOG))

lines = d["activitiesLog"].strip().split("\n")
hdr = lines[0].split(";")
ipnl = hdr.index("profit_and_loss")
ip = hdr.index("product")
its = hdr.index("timestamp")
imid = hdr.index("mid_price")

last_pnl, last_ts, last_mid = {}, {}, {}
days = set()
for l in lines[1:]:
    parts = l.split(";")
    p = parts[ip]
    ts = int(parts[its])
    days.add(parts[0])
    try:
        pnl = float(parts[ipnl])
        mid = float(parts[imid])
    except Exception:
        continue
    if p not in last_ts or ts > last_ts[p]:
        last_ts[p] = ts
        last_pnl[p] = pnl
        last_mid[p] = mid

print("Final per-product PnL:")
total = 0.0
for k, v in sorted(last_pnl.items(), key=lambda x: -x[1]):
    total += v
    print(f"  {k:>22}: {v:>12,.1f}   mid={last_mid[k]:.1f}")
print(f"  {'TOTAL':>22}: {total:>12,.1f}")

print()
print("days seen:", sorted(days))
all_ts = [int(l.split(";")[its]) for l in lines[1:]]
print("ts range:", min(all_ts), "->", max(all_ts))
print("positions at end:", d["positions"])
