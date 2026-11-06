"""Parse platform log 276915.log — full JSON with tradeHistory and logs."""
import json
from collections import defaultdict
import statistics

LOG_PATH = r".\logs\276915\276915.log"

with open(LOG_PATH, "r", encoding="utf-8") as f:
    data = json.load(f)

print("Keys:", list(data.keys()))
print()

# ── Logs (algo output from logger.flush()) ──
logs = data.get("logs", "")
if logs:
    lines = logs.strip().split("\n")
    print(f"Algo logs: {len(lines)} lines")
    
    # Each line is a JSON array: [state, orders, conversions, traderData, logText]
    fill_count = defaultdict(int)
    total_buy_fills = defaultdict(int)
    total_sell_fills = defaultdict(int)
    positions = defaultdict(list)
    order_count = defaultdict(int)
    order_buy_vol = defaultdict(int)
    order_sell_vol = defaultdict(int)
    
    take_orders = defaultdict(int)
    make_orders = defaultdict(int)
    
    errors = 0
    for i, line in enumerate(lines):
        try:
            entry = json.loads(line)
            state = entry[0]
            orders_dict = entry[1]
            
            ts = state[0]
            pos = state[6]
            own_trades = state[4]
            
            for sym, p in pos.items():
                positions[sym].append((ts, p))
            
            for sym, trades in own_trades.items():
                for t in trades:
                    qty = t[2]
                    fill_count[sym] += 1
                    if qty > 0:
                        total_buy_fills[sym] += qty
                    else:
                        total_sell_fills[sym] += abs(qty)
            
            for sym, ords in orders_dict.items():
                for o in ords:
                    q = o[2]
                    order_count[sym] += 1
                    if q > 0:
                        order_buy_vol[sym] += q
                    else:
                        order_sell_vol[sym] += abs(q)
                        
        except (json.JSONDecodeError, IndexError, TypeError, KeyError) as e:
            errors += 1
            if errors <= 3:
                print(f"  Error line {i}: {e}")
                print(f"    {line[:200]}")
    
    print(f"  Parse errors: {errors}")
    print()
    
    print("=== FILL ANALYSIS ===")
    for sym in sorted(fill_count.keys()):
        print(f"\n{sym}:")
        print(f"  Fills: {fill_count[sym]} trades")
        print(f"  Buy volume filled: {total_buy_fills[sym]}")
        print(f"  Sell volume filled: {total_sell_fills[sym]}")
        print(f"  Net filled: {total_buy_fills[sym] - total_sell_fills[sym]}")
        print(f"  Orders placed: {order_count[sym]}")
        print(f"  Order buy volume: {order_buy_vol[sym]}")
        print(f"  Order sell volume: {order_sell_vol[sym]}")
        if order_buy_vol[sym] > 0:
            print(f"  Buy fill rate: {total_buy_fills[sym]/order_buy_vol[sym]*100:.1f}%")
        if order_sell_vol[sym] > 0:
            print(f"  Sell fill rate: {total_sell_fills[sym]/order_sell_vol[sym]*100:.1f}%")
    
    print("\n=== POSITION ANALYSIS ===")
    for sym in sorted(positions.keys()):
        pts = positions[sym]
        vals = [p for _, p in pts]
        print(f"\n{sym}: {len(pts)} ticks")
        print(f"  Range: {min(vals)} to {max(vals)}")
        print(f"  Final: {vals[-1]}")
        print(f"  Mean: {statistics.mean(vals):.1f}")
        print(f"  Stdev: {statistics.stdev(vals):.1f}" if len(vals) > 1 else "  Stdev: N/A")
        print(f"  |pos|>50: {sum(1 for p in vals if abs(p) > 50)} / {len(vals)} ({sum(1 for p in vals if abs(p) > 50)/len(vals)*100:.1f}%)")
        print(f"  |pos|>60: {sum(1 for p in vals if abs(p) > 60)} / {len(vals)} ({sum(1 for p in vals if abs(p) > 60)/len(vals)*100:.1f}%)")
        print(f"  |pos|>70: {sum(1 for p in vals if abs(p) > 70)} / {len(vals)} ({sum(1 for p in vals if abs(p) > 70)/len(vals)*100:.1f}%)")
        
        # First 20 positions
        print(f"  First 20: {vals[:20]}")
        # Last 20 positions
        print(f"  Last 20:  {vals[-20:]}")

else:
    print("No logs field")

# ── Trade History ──
th = data.get("tradeHistory", {})
print(f"\n=== TRADE HISTORY ===")
if isinstance(th, dict):
    for sym, trades in th.items():
        print(f"\n{sym}: {len(trades)} trades")
        if trades:
            print(f"  First: {trades[0]}")
            print(f"  Last:  {trades[-1]}")
            # Compute profit from trades
            buy_cost = 0
            sell_rev = 0
            buy_qty = 0
            sell_qty = 0
            for t in trades:
                if isinstance(t, dict):
                    qty = t.get("quantity", 0)
                    price = t.get("price", 0)
                    if qty > 0:
                        buy_cost += qty * price
                        buy_qty += qty
                    else:
                        sell_rev += abs(qty) * price
                        sell_qty += abs(qty)
                elif isinstance(t, list):
                    # [sym, price, qty, buyer, seller, ts]
                    price = t[1]
                    qty = t[2]
                    if qty > 0:
                        buy_cost += qty * price
                        buy_qty += qty
                    else:
                        sell_rev += abs(qty) * price
                        sell_qty += abs(qty)
            print(f"  Buy: {buy_qty} lots, cost={buy_cost}")
            print(f"  Sell: {sell_qty} lots, rev={sell_rev}")
            print(f"  Net qty: {buy_qty - sell_qty}")
            if sell_rev + buy_cost > 0:
                print(f"  Realized P&L (approx): {sell_rev - buy_cost}")
elif isinstance(th, list):
    print(f"  Trade history is a list with {len(th)} entries")
    if th:
        print(f"  First: {th[0]}")
