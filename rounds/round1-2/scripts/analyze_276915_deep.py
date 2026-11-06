"""Deep analysis of platform log 276915 — understand the 2K vs 98K gap."""
import json, re
from collections import defaultdict

LOG_DIR = r".\logs\276915"

# ── Parse JSON ──
with open(f"{LOG_DIR}\\276915.json", "r", encoding="utf-8") as f:
    d = json.load(f)

print(f"=== PLATFORM RUN 276915 ===")
print(f"Round: {d['round']}, Status: {d['status']}, Profit: {d['profit']}")
print(f"Final positions: {d['positions']}")
print()

# ── Parse activities log (CSV) ──
activities = d["activitiesLog"]
# It's a single string with newlines
lines = activities.strip().split("\n") if isinstance(activities, str) else [activities]
# Actually it seems like it was split into individual chars. Let me rejoin
if isinstance(activities, str):
    lines = activities.strip().split("\n")
else:
    # activities is already a list... but first entry was 'd' — so it's chars of a string
    full_text = "".join(str(x) for x in activities)
    lines = full_text.strip().split("\n")

print(f"Activities: {len(lines)} lines")
header = lines[0]
print(f"Header: {header}")
print()

# Parse CSV
rows = []
cols = header.split(";")
for line in lines[1:]:
    if not line.strip():
        continue
    parts = line.split(";")
    row = {}
    for i, col in enumerate(cols):
        row[col] = parts[i] if i < len(parts) else ""
    rows.append(row)

print(f"Parsed {len(rows)} data rows")

# Group by product
products = defaultdict(list)
for r in rows:
    products[r["product"]].append(r)

for prod, prows in products.items():
    print(f"\n{'='*60}")
    print(f"  {prod}: {len(prows)} ticks")
    
    # Extract timestamps  
    days = set()
    timestamps = []
    for r in prows:
        days.add(int(r["day"]))
        timestamps.append(int(r["timestamp"]))
    
    print(f"  Days: {sorted(days)}")
    print(f"  Timestamps: {min(timestamps)} to {max(timestamps)}, unique={len(set(timestamps))}")
    
    # Spreads
    spreads = []
    mids = []
    for r in prows:
        bp1 = r.get("bid_price_1", "")
        ap1 = r.get("ask_price_1", "")
        mid = r.get("mid_price", "")
        if bp1 and ap1:
            try:
                spread = float(ap1) - float(bp1)
                spreads.append(spread)
            except:
                pass
        if mid:
            try:
                mids.append(float(mid))
            except:
                pass
    
    if spreads:
        import statistics
        print(f"  Spread: mean={statistics.mean(spreads):.1f}, median={statistics.median(spreads):.1f}, min={min(spreads)}, max={max(spreads)}")
    if mids:
        print(f"  Mid: first={mids[0]}, last={mids[-1]}, range={min(mids):.1f}-{max(mids):.1f}")
    
    # PnL trajectory
    pnls = []
    for r in prows:
        pnl = r.get("profit_and_loss", "")
        if pnl:
            try:
                pnls.append(float(pnl))
            except:
                pass
    if pnls:
        print(f"  PnL: first={pnls[0]}, last={pnls[-1]}, max={max(pnls):.1f}, min={min(pnls):.1f}")
        
        # PnL by day
        day_pnl = defaultdict(list)
        for r in prows:
            try:
                day_pnl[int(r["day"])].append(float(r["profit_and_loss"]))
            except:
                pass
        for day in sorted(day_pnl.keys()):
            vals = day_pnl[day]
            print(f"    Day {day}: start={vals[0]:.1f}, end={vals[-1]:.1f}, ticks={len(vals)}")

    # Bid/ask volumes
    bvols = []
    avols = []
    for r in prows:
        bv1 = r.get("bid_volume_1", "")
        av1 = r.get("ask_volume_1", "")
        if bv1:
            try: bvols.append(int(bv1))
            except: pass
        if av1:
            try: avols.append(int(av1))
            except: pass
    if bvols:
        print(f"  Bid L1 vol: mean={statistics.mean(bvols):.1f}, median={statistics.median(bvols)}")
    if avols:
        print(f"  Ask L1 vol: mean={statistics.mean(avols):.1f}, median={statistics.median(avols)}")


# ── Parse algo log (.log file) ──
print(f"\n{'='*60}")
print("=== ALGO LOG ANALYSIS ===")

with open(f"{LOG_DIR}\\276915.log", "r", encoding="utf-8", errors="replace") as f:
    log_text = f.read()

# The log is JSON array per line from Logger.flush()
log_lines = log_text.strip().split("\n")
print(f"Log lines: {len(log_lines)}")

# Parse each line
fill_count = defaultdict(int)
total_buy_fills = defaultdict(int)
total_sell_fills = defaultdict(int)
positions_seen = defaultdict(list)
errors = []

for i, line in enumerate(log_lines):
    try:
        data = json.loads(line)
        # data = [state, orders, conversions, traderData, logs]
        state = data[0]  # [timestamp, traderData, listings, order_depths, own_trades, market_trades, position, obs]
        orders = data[1]  # {symbol: [[sym, price, qty], ...]}
        
        timestamp = state[0]
        position = state[6]  # {symbol: qty}
        own_trades = state[4]  # {symbol: [[sym, price, qty, buyer, seller, ts], ...]}
        
        for sym, pos in position.items():
            positions_seen[sym].append((timestamp, pos))
        
        for sym, trades in own_trades.items():
            for t in trades:
                qty = t[2]
                if qty > 0:
                    total_buy_fills[sym] += qty
                else:
                    total_sell_fills[sym] += abs(qty)
                fill_count[sym] += 1
        
    except (json.JSONDecodeError, IndexError, TypeError) as e:
        if len(errors) < 5:
            errors.append(f"Line {i}: {e} - {line[:100]}")

if errors:
    print(f"\nParse errors ({len(errors)}):")
    for e in errors:
        print(f"  {e}")

print(f"\nFill counts: {dict(fill_count)}")
print(f"Total buy volume: {dict(total_buy_fills)}")
print(f"Total sell volume: {dict(total_sell_fills)}")

for sym in positions_seen:
    pts = positions_seen[sym]
    if pts:
        pos_vals = [p for _, p in pts]
        print(f"\n{sym} position:")
        print(f"  Ticks: {len(pts)}")
        print(f"  Range: {min(pos_vals)} to {max(pos_vals)}")
        print(f"  Final: {pos_vals[-1]}")
        print(f"  Mean: {statistics.mean(pos_vals):.1f}")
        print(f"  Time at 0: {sum(1 for p in pos_vals if p == 0)}")
        print(f"  Time |pos|>30: {sum(1 for p in pos_vals if abs(p) > 30)}")
        print(f"  Time |pos|>50: {sum(1 for p in pos_vals if abs(p) > 50)}")
        print(f"  Time |pos|>70: {sum(1 for p in pos_vals if abs(p) > 70)}")

# Count orders placed
order_count = defaultdict(int)
order_buy_vol = defaultdict(int)
order_sell_vol = defaultdict(int)
for line in log_lines:
    try:
        data = json.loads(line)
        orders = data[1]
        for sym, ords in orders.items():
            for o in ords:
                order_count[sym] += 1
                if o[2] > 0:
                    order_buy_vol[sym] += o[2]
                else:
                    order_sell_vol[sym] += abs(o[2])
    except:
        pass

print(f"\nOrders placed: {dict(order_count)}")
print(f"Order buy volume: {dict(order_buy_vol)}")
print(f"Order sell volume: {dict(order_sell_vol)}")

# Fill rate
for sym in order_count:
    if order_buy_vol[sym] > 0:
        buy_rate = total_buy_fills.get(sym, 0) / order_buy_vol[sym] * 100
        sell_rate = total_sell_fills.get(sym, 0) / order_sell_vol[sym] * 100
        print(f"\n{sym} fill rate:")
        print(f"  Buy: {total_buy_fills.get(sym,0)}/{order_buy_vol[sym]} = {buy_rate:.1f}%")
        print(f"  Sell: {total_sell_fills.get(sym,0)}/{order_sell_vol[sym]} = {sell_rate:.1f}%")
