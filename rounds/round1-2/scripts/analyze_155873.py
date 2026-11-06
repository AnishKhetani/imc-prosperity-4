"""Analyze platform backtest log 155873."""
import json

with open(r'.\logs\155873\155873.json') as f:
    d = json.load(f)

lines = d['activitiesLog'].strip().split('\n')
header = lines[0].split(';')
print(f"Header columns ({len(header)}):")
for i, h in enumerate(header):
    print(f"  [{i}] {h}")
print()

# mid_price=col15, profit_and_loss=col16
osm_pnl = []
ipr_pnl = []
days = set()
for line in lines[1:]:
    parts = line.split(';')
    if len(parts) > 16:
        day = parts[0]
        days.add(day)
        prod = parts[2]
        ts = int(parts[1])
        mid_str = parts[15]
        pnl_str = parts[16]
        mid = float(mid_str) if mid_str else None
        pnl = float(pnl_str) if pnl_str else None
        if prod == 'ASH_COATED_OSMIUM':
            osm_pnl.append((day, ts, pnl, mid))
        elif prod == 'INTARIAN_PEPPER_ROOT':
            ipr_pnl.append((day, ts, pnl, mid))

print(f"Days: {sorted(days)}")
print(f"OSM ticks: {len(osm_pnl)}, final PnL: {osm_pnl[-1][2]:.2f}, final mid: {osm_pnl[-1][3]:.1f}")
print(f"IPR ticks: {len(ipr_pnl)}, final PnL: {ipr_pnl[-1][2]:.2f}, final mid: {ipr_pnl[-1][3]:.1f}")
print(f"SUM PnL: {osm_pnl[-1][2] + ipr_pnl[-1][2]:.2f}")
print(f"Reported total: {d['profit']}")
print()

# PnL trajectory at key points
print("=== OSM PnL trajectory ===")
for idx in [0, len(osm_pnl)//4, len(osm_pnl)//2, 3*len(osm_pnl)//4, -1]:
    day, t, pnl, mid = osm_pnl[idx]
    print(f"  day={day} t={t:6d}: PnL={pnl:.2f}, mid={mid:.1f}")

print()
print("=== IPR PnL trajectory ===")
for idx in [0, len(ipr_pnl)//4, len(ipr_pnl)//2, 3*len(ipr_pnl)//4, -1]:
    day, t, pnl, mid = ipr_pnl[idx]
    print(f"  day={day} t={t:6d}: PnL={pnl:.2f}, mid={mid:.1f}")

print()
print("=== End positions ===")
for p in d['positions']:
    print(f"  {p['symbol']}: {p['quantity']}")

# IPR mid-price drift
print()
print("=== IPR mid-price evolution ===")
ipr_mids = [(day, ts, mid) for day, ts, pnl, mid in ipr_pnl if mid is not None]
if ipr_mids:
    print(f"  Start: t={ipr_mids[0][1]} mid={ipr_mids[0][2]:.1f}")
    print(f"  End:   t={ipr_mids[-1][1]} mid={ipr_mids[-1][2]:.1f}")
    print(f"  Drift: {ipr_mids[-1][2] - ipr_mids[0][2]:.1f}")
    q1 = ipr_mids[len(ipr_mids)//4][2]
    q2 = ipr_mids[len(ipr_mids)//2][2]
    q3 = ipr_mids[3*len(ipr_mids)//4][2]
    print(f"  Q1={q1:.1f} Q2={q2:.1f} Q3={q3:.1f}")

# OSM mid stability
print()
print("=== OSM mid-price evolution ===")
osm_mids = [(day, ts, mid) for day, ts, pnl, mid in osm_pnl if mid is not None]
if osm_mids:
    mids = [m[2] for m in osm_mids]
    print(f"  Start: {osm_mids[0][2]:.1f}, End: {osm_mids[-1][2]:.1f}")
    print(f"  Min={min(mids):.1f}, Max={max(mids):.1f}, Mean={sum(mids)/len(mids):.1f}")

# Analyze spreads
# Spread analysis (bid_price_1=col3, ask_price_1=col9)
print()
print("=== Spread analysis ===")
for prod_name in ['ASH_COATED_OSMIUM', 'INTARIAN_PEPPER_ROOT']:
    spreads = []
    for line in lines[1:]:
        parts = line.split(';')
        if len(parts) > 10 and parts[2] == prod_name:
            bid1 = parts[3]
            ask1 = parts[9]
            if bid1 and ask1:
                spreads.append(float(ask1) - float(bid1))
    if spreads:
        from collections import Counter
        sp_counts = Counter(int(s) for s in spreads)
        top5 = sp_counts.most_common(5)
        print(f"  {prod_name}: mean={sum(spreads)/len(spreads):.1f}, min={min(spreads):.0f}, max={max(spreads):.0f}, ticks_w_book={len(spreads)}")
        print(f"    Top spreads: {top5}")

# XIRECS investigation  
print()
print("=== XIRECS Investigation ===")
with open(r'.\logs\155873\155873.log') as f:
    log_content = f.read()

# Parse the log (it's one big JSON line)
import re
xirecs_snippets = []
# Find contexts around XIRECS
for match in re.finditer(r'.{0,80}XIRECS.{0,80}', log_content):
    xirecs_snippets.append(match.group())
    if len(xirecs_snippets) >= 5:
        break

print(f"  XIRECS mentions: {log_content.count('XIRECS')}")
for i, snip in enumerate(xirecs_snippets):
    print(f"  [{i}] ...{snip}...")

# What is XIRECS? Check if it's a denomination/currency
# Look for listing info in log
listing_snippets = []
for match in re.finditer(r'.{0,50}listing.{0,100}', log_content, re.IGNORECASE):
    listing_snippets.append(match.group())
    if len(listing_snippets) >= 5:
        break
print()
print("=== Listing info ===")
for i, snip in enumerate(listing_snippets):
    print(f"  [{i}] ...{snip}...")
