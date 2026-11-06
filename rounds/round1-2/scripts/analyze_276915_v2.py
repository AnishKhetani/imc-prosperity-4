"""Parse platform log 276915.log — correct structure."""
import json
from collections import defaultdict
import statistics

LOG_PATH = r".\logs\276915\276915.log"

with open(LOG_PATH, "r", encoding="utf-8") as f:
    data = json.load(f)

# ── Trade History (filled trades) ──
trades = data["tradeHistory"]
print(f"=== TRADE HISTORY: {len(trades)} trades ===")

by_sym = defaultdict(list)
for t in trades:
    by_sym[t["symbol"]].append(t)

for sym in sorted(by_sym.keys()):
    st = by_sym[sym]
    print(f"\n{sym}: {len(st)} trades")
    
    buy_qty = sum(t["quantity"] for t in st if t["buyer"] == "SUBMISSION")
    sell_qty = sum(t["quantity"] for t in st if t["seller"] == "SUBMISSION")
    buy_cost = sum(t["quantity"] * t["price"] for t in st if t["buyer"] == "SUBMISSION")
    sell_rev = sum(t["quantity"] * t["price"] for t in st if t["seller"] == "SUBMISSION")
    
    print(f"  Bought: {buy_qty} lots, cost={buy_cost:.0f}")
    print(f"  Sold: {sell_qty} lots, rev={sell_rev:.0f}")
    print(f"  Net position: {buy_qty - sell_qty}")
    print(f"  Realized PnL: {sell_rev - buy_cost:.0f}")
    
    # Price stats
    prices = [t["price"] for t in st]
    print(f"  Price range: {min(prices):.0f} - {max(prices):.0f}")
    
    # Who are the counterparties?
    buyers = defaultdict(int)
    sellers = defaultdict(int)
    for t in st:
        buyers[t["buyer"]] += t["quantity"]
        sellers[t["seller"]] += t["quantity"]
    print(f"  Buyers: {dict(buyers)}")
    print(f"  Sellers: {dict(sellers)}")
    
    # Timestamps
    ts_list = [t["timestamp"] for t in st]
    print(f"  Time range: {min(ts_list)} - {max(ts_list)}")
    
    # Show first 10 and last 10 trades
    print(f"  First 5 trades:")
    for t in st[:5]:
        direction = "BUY" if t["buyer"] == "SUBMISSION" else "SELL"
        print(f"    ts={t['timestamp']}: {direction} {t['quantity']}@{t['price']:.0f} vs {t['buyer'] if direction=='SELL' else t['seller']}")
    print(f"  Last 5 trades:")
    for t in st[-5:]:
        direction = "BUY" if t["buyer"] == "SUBMISSION" else "SELL"
        print(f"    ts={t['timestamp']}: {direction} {t['quantity']}@{t['price']:.0f} vs {t['buyer'] if direction=='SELL' else t['seller']}")

# ── Algo Logs ──
logs = data["logs"]
print(f"\n=== ALGO LOGS: {len(logs)} ticks ===")

positions = defaultdict(list)
orders_placed = defaultdict(list)

for i, entry in enumerate(logs):
    lambda_log = entry.get("lambdaLog", "")
    if not lambda_log:
        continue
    
    try:
        parsed = json.loads(lambda_log)
        state = parsed[0]
        orders_dict = parsed[1]
        
        ts = state[0]
        pos = state[6]
        
        for sym, p in pos.items():
            positions[sym].append((ts, p))
        
        for sym, ords in orders_dict.items():
            for o in ords:
                orders_placed[sym].append({
                    "ts": ts,
                    "price": o[1],
                    "qty": o[2],
                })
    except (json.JSONDecodeError, IndexError, TypeError, KeyError) as e:
        if i < 3:
            print(f"  Parse error at tick {i}: {e}")

print(f"\n=== POSITION ANALYSIS ===")
for sym in sorted(positions.keys()):
    pts = positions[sym]
    vals = [p for _, p in pts]
    print(f"\n{sym}: {len(pts)} ticks")
    print(f"  Range: {min(vals)} to {max(vals)}")
    print(f"  Final: {vals[-1]}")
    print(f"  Mean: {statistics.mean(vals):.1f}")
    if len(vals) > 1:
        print(f"  Stdev: {statistics.stdev(vals):.1f}")
    # Time at extreme positions
    print(f"  |pos| > 50: {sum(1 for p in vals if abs(p) > 50)} ({sum(1 for p in vals if abs(p) > 50)/len(vals)*100:.1f}%)")
    print(f"  |pos| > 60: {sum(1 for p in vals if abs(p) > 60)} ({sum(1 for p in vals if abs(p) > 60)/len(vals)*100:.1f}%)")
    print(f"  |pos| > 70: {sum(1 for p in vals if abs(p) > 70)} ({sum(1 for p in vals if abs(p) > 70)/len(vals)*100:.1f}%)")
    print(f"  First 30: {vals[:30]}")
    print(f"  Last 30:  {vals[-30:]}")
    
    # Position flips (sign changes)
    flips = sum(1 for j in range(1, len(vals)) if vals[j] * vals[j-1] < 0)
    print(f"  Sign flips: {flips}")
    
    # Time series of extremes
    max_pos_ts = [(ts, p) for ts, p in pts if abs(p) >= 60]
    if max_pos_ts:
        print(f"  Extreme positions (|pos|>=60):")
        for ts, p in max_pos_ts[:10]:
            print(f"    ts={ts}: pos={p}")
        if len(max_pos_ts) > 10:
            print(f"    ... {len(max_pos_ts)-10} more")

print(f"\n=== ORDER ANALYSIS ===")
for sym in sorted(orders_placed.keys()):
    ords = orders_placed[sym]
    print(f"\n{sym}: {len(ords)} orders")
    buy_orders = [o for o in ords if o["qty"] > 0]
    sell_orders = [o for o in ords if o["qty"] < 0]
    print(f"  Buy orders: {len(buy_orders)}, total vol: {sum(o['qty'] for o in buy_orders)}")
    print(f"  Sell orders: {len(sell_orders)}, total vol: {sum(abs(o['qty']) for o in sell_orders)}")
    
    # Fill rate comparison
    filled_buys = sum(t["quantity"] for t in by_sym.get(sym, []) if t["buyer"] == "SUBMISSION")
    filled_sells = sum(t["quantity"] for t in by_sym.get(sym, []) if t["seller"] == "SUBMISSION")
    total_buy_ordered = sum(o["qty"] for o in buy_orders)
    total_sell_ordered = sum(abs(o["qty"]) for o in sell_orders)
    if total_buy_ordered > 0:
        print(f"  Buy fill rate: {filled_buys}/{total_buy_ordered} = {filled_buys/total_buy_ordered*100:.1f}%")
    if total_sell_ordered > 0:
        print(f"  Sell fill rate: {filled_sells}/{total_sell_ordered} = {filled_sells/total_sell_ordered*100:.1f}%")

# ── Graph log (PnL over time) ──
json_data = json.load(open(r".\logs\276915\276915.json", "r", encoding="utf-8"))
gl = json_data.get("graphLog", "")
if gl:
    gl_lines = gl.strip().split("\n")
    print(f"\n=== GRAPH LOG: {len(gl_lines)} entries ===")
    # Parse it
    if gl_lines:
        print(f"First: {gl_lines[0][:200]}")
        print(f"Last:  {gl_lines[-1][:200]}")
