"""Forensic analysis of live R4 log 487874."""
import json
from collections import defaultdict
from pathlib import Path

LOG = Path(r".\logs\487874\487874.log")
d = json.load(open(LOG, "r", encoding="utf-8", errors="replace"))

trades = d["tradeHistory"]
print(f"Total SUBMISSION trades: {len([t for t in trades if 'SUBMISSION' in (t['buyer'], t['seller'])])}")
print(f"Total trades observed:   {len(trades)}")

# Per-symbol fill stats for SUBMISSION
buys = defaultdict(list)   # symbol -> list of (price, qty)
sells = defaultdict(list)
cp_buy = defaultdict(lambda: defaultdict(int))   # symbol -> {cp -> qty filled by us}
cp_sell = defaultdict(lambda: defaultdict(int))

for t in trades:
    sym = t["symbol"]
    px = float(t["price"])
    qty = int(t["quantity"])
    if t["buyer"] == "SUBMISSION":
        buys[sym].append((px, qty))
        cp_buy[sym][t["seller"]] += qty
    elif t["seller"] == "SUBMISSION":
        sells[sym].append((px, qty))
        cp_sell[sym][t["buyer"]] += qty

print("\n=== Submission fills per symbol ===")
print(f"{'symbol':>22} {'buys':>6} {'sells':>6} {'avgBuy':>8} {'avgSell':>8} {'spread':>7}")
for sym in sorted(set(list(buys.keys()) + list(sells.keys()))):
    bq = sum(q for _, q in buys[sym]); sq = sum(q for _, q in sells[sym])
    bp = sum(p*q for p, q in buys[sym]) / bq if bq else 0
    sp = sum(p*q for p, q in sells[sym]) / sq if sq else 0
    spread = sp - bp if bq and sq else 0
    print(f"{sym:>22} {bq:>6} {sq:>6} {bp:>8.1f} {sp:>8.1f} {spread:>7.2f}")

print("\n=== VFE counterparty breakdown (top 5) ===")
print("buys from (we lifted offers):")
for cp, q in sorted(cp_buy["VELVETFRUIT_EXTRACT"].items(), key=lambda x: -x[1])[:8]:
    print(f"  {cp:>15}: {q:>6}")
print("sells to (we hit bids):")
for cp, q in sorted(cp_sell["VELVETFRUIT_EXTRACT"].items(), key=lambda x: -x[1])[:8]:
    print(f"  {cp:>15}: {q:>6}")

print("\n=== HGP counterparty breakdown ===")
print("buys from:")
for cp, q in sorted(cp_buy["HYDROGEL_PACK"].items(), key=lambda x: -x[1])[:8]:
    print(f"  {cp:>15}: {q:>6}")
print("sells to:")
for cp, q in sorted(cp_sell["HYDROGEL_PACK"].items(), key=lambda x: -x[1])[:8]:
    print(f"  {cp:>15}: {q:>6}")

# For each symbol, count fills per ts (volume rate)
ts_counts = defaultdict(int)
for t in trades:
    if "SUBMISSION" in (t["buyer"], t["seller"]):
        ts_counts[t["timestamp"]] += 1
print(f"\nFill timestamps active: {len(ts_counts)} of 1000")
print(f"Mean fills/active-ts: {sum(ts_counts.values())/max(1,len(ts_counts)):.2f}")

# Mid drift per product
lines = d["activitiesLog"].strip().split("\n")
hdr = lines[0].split(";")
ip, its, imid, ipnl = hdr.index("product"), hdr.index("timestamp"), hdr.index("mid_price"), hdr.index("profit_and_loss")
mids_by_sym = defaultdict(list)
for l in lines[1:]:
    parts = l.split(";")
    try: mids_by_sym[parts[ip]].append((int(parts[its]), float(parts[imid])))
    except Exception: pass

print("\n=== Mid first/last/min/max ===")
for sym in ["HYDROGEL_PACK", "VELVETFRUIT_EXTRACT", "VEV_5300", "VEV_5400", "VEV_5500"]:
    if sym not in mids_by_sym: continue
    series = sorted(mids_by_sym[sym])
    mids = [m for _, m in series]
    print(f"  {sym:>22}: first={mids[0]:.1f} last={mids[-1]:.1f} min={min(mids):.1f} max={max(mids):.1f} ticks={len(mids)}")
