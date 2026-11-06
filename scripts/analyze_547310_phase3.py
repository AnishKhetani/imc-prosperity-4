"""Phase 3 strategy validity audit + edge frequency stats."""
import json, csv, io, os
from collections import defaultdict, Counter
import statistics as st

ROOT = os.path.join(os.path.dirname(__file__), "..", "logs", "547310")

with open(os.path.join(ROOT, "547310.log"), "r", encoding="utf-8") as f:
    env = json.load(f)
rdr = csv.DictReader(io.StringIO(env["activitiesLog"]), delimiter=";")
rows = list(rdr)
by_ts = defaultdict(dict)
for r in rows:
    by_ts[int(r["timestamp"])][r["product"]] = r
ts_sorted = sorted(by_ts.keys())
trades = env.get("tradeHistory", [])

def fnum(s):
    try: return float(s)
    except: return None

# ---- 1. PEBBLES synthetic edge distribution ----
print("=== PEBBLES synthetic-fair edge distribution ===")
pebbles = ["PEBBLES_XS","PEBBLES_S","PEBBLES_M","PEBBLES_L","PEBBLES_XL"]
edges = []
sum_devs = []
for ts in ts_sorted:
    row = by_ts[ts]
    mids = {p: fnum(row[p]["mid_price"]) if p in row else None for p in pebbles}
    if any(m is None for m in mids.values()): continue
    s = sum(mids.values())
    sum_devs.append(s - 50000.0)
    for p in pebbles:
        synth = 50000.0 - (s - mids[p])  # = 50000 - sum_others
        edge = synth - mids[p]
        edges.append(edge)
print(f"  PEBBLES sum: mean={st.mean(sum_devs):+.2f} std={st.pstdev(sum_devs):.2f} n={len(sum_devs)}")
print(f"  per-leg edge stats: mean={st.mean(edges):+.4f} std={st.pstdev(edges):.4f} max={max(edges):.2f} min={min(edges):.2f}")
trip_thresholds = [2,4,6,8,10]
for t in trip_thresholds:
    hits = sum(1 for e in edges if abs(e)>t)
    print(f"  |edge|>{t}: {hits} ({hits/len(edges)*100:.2f}%)")

# ---- 2. SNACK pair z analysis ----
print("\n=== SNACKPACK CHOC+VAN pair sum stats ===")
sums = []
for ts in ts_sorted:
    row = by_ts[ts]
    if "SNACKPACK_CHOCOLATE" in row and "SNACKPACK_VANILLA" in row:
        c = fnum(row["SNACKPACK_CHOCOLATE"]["mid_price"])
        v = fnum(row["SNACKPACK_VANILLA"]["mid_price"])
        if c and v: sums.append(c+v)
mean = st.mean(sums); sd = st.pstdev(sums)
print(f"  mean={mean:.2f} std(intraday)={sd:.2f} n={len(sums)} (config: target=19940 std=76)")
zs = [(s-19940)/76 for s in sums]
print(f"  z (config): mean={st.mean(zs):+.3f} std={st.pstdev(zs):.3f}")
zs2 = [(s-mean)/sd for s in sums]
print(f"  z (empirical): mean={st.mean(zs2):+.3f} std={st.pstdev(zs2):.3f}")
for thr in (1.0, 1.5, 2.0, 2.5):
    n_cfg = sum(1 for z in zs if abs(z)>thr)
    n_emp = sum(1 for z in zs2 if abs(z)>thr)
    print(f"  |z|>{thr}: cfg={n_cfg} emp={n_emp}")

# ---- 3. Trade-price vs touch (full sample) ----
print("\n=== Trade location vs touch (all 1420 trades) ===")
loc = Counter()
for t in trades:
    ts = int(t["timestamp"]); prod = t["symbol"]; px = float(t["price"])
    r = by_ts.get(ts,{}).get(prod)
    if not r: loc["no_book"] += 1; continue
    bid = fnum(r["bid_price_1"]); ask = fnum(r["ask_price_1"])
    if bid is None or ask is None: loc["no_touch"] += 1; continue
    if px == bid: loc["at_bid"] += 1
    elif px == ask: loc["at_ask"] += 1
    elif bid < px < ask: loc["inside"] += 1
    elif px < bid: loc["below_bid"] += 1
    elif px > ask: loc["above_ask"] += 1
print(f"  {dict(loc)}")
print(f"  inside-touch fraction: {loc.get('inside',0)/sum(loc.values())*100:.2f}%")

# ---- 4. Per-product depth + spread (median) ----
print("\n=== Order book health per product (median over 1000 ticks) ===")
prods = sorted({r["product"] for r in rows})
print(f"{'product':35s}  {'spread':>7s} {'depth':>6s}")
dead = []
for p in prods:
    spreads = []; depths = []
    for ts in ts_sorted:
        row = by_ts[ts].get(p)
        if not row: continue
        b = fnum(row["bid_price_1"]); a = fnum(row["ask_price_1"])
        if b and a: spreads.append(a-b)
        d = 0
        for i in (1,2,3):
            for side in ("bid_volume","ask_volume"):
                v = fnum(row.get(f"{side}_{i}",""))
                if v: d += abs(v)
        depths.append(d)
    if spreads and depths:
        ms = st.median(spreads); md = st.median(depths)
        flag = ""
        if md < 5: flag += " THIN"
        if ms > 20: flag += " WIDE"
        print(f"{p:35s}  {ms:7.1f} {md:6.1f}{flag}")
        if md < 5 or ms > 20: dead.append(p)
print(f"\nProducts with thin/wide markets: {len(dead)}")
for p in dead: print(" ", p)
