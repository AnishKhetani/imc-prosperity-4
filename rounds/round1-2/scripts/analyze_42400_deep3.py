"""
Part 3: Skew mechanism analysis — are extra fills caused by position skew?
And what's the optimal TOMATOES Width?
"""
import csv
import io
import json

for sim_id in ["42400"]:
    with open(f"logs/{sim_id}/{sim_id}.json") as f:
        data = json.load(f)

# Parse the actual log to find own trades and position
log_text = data.get("logFile", "") or ""
if not log_text:
    # Try reading the .log file directly
    with open(f"logs/42400/42400.log", "r") as f:
        log_text = f.read()

# Parse own trades from activities log
rows = list(csv.DictReader(io.StringIO(data["activitiesLog"]), delimiter=";"))
em = [r for r in rows if r["product"] == "EMERALDS"]

# Look for EMERALDS own_trades in log
# The compressed log format: state[4] = own_trades
# Let's try parsing the JSON log entries
print("=" * 80)
print("PARSING LOG FOR OWN TRADES")
print("=" * 80)

# Read the .py file which has the readable log
with open("logs/42400/42400.py", "r", encoding="utf-8", errors="replace") as f:
    py_content = f.read()

# Search for key patterns in the log
import re

# Find lines that mention EMERALDS fills
# The log should contain compressed state data as JSON arrays
# Let's search for our trade data

# Look at our trade data - the log format is JSON with compressed state
# Try to find own trades mentioning EMERALDS
emerald_trades = []
for line in py_content.split("\n"):
    if "EMERALDS" in line and ("9993" in line or "10007" in line or "9994" in line or "10006" in line):
        # This line likely has fill info
        emerald_trades.append(line[:200])

print(f"Lines with EMERALDS fill prices: {len(emerald_trades)}")
for i, line in enumerate(emerald_trades[:40]):
    print(f"  {i}: {line[:180]}")


# Alternative: parse the JSON log entries
print("\n" + "=" * 80)
print("PARSING COMPRESSED LOG ENTRIES")
print("=" * 80)

# The .py file contains output from logger.flush()
# Format: JSON array [compressed_state, compressed_orders, conversions, trader_data, logs]
entries = []
parse_errors = 0
for line in py_content.strip().split("\n"):
    line = line.strip()
    if not line:
        continue
    try:
        entry = json.loads(line)
        entries.append(entry)
    except json.JSONDecodeError:
        parse_errors += 1
        
print(f"Parsed {len(entries)} log entries, {parse_errors} errors")

if entries:
    # Each entry: [state, orders, conversions, trader_data, logs]
    # state: [timestamp, traderData, listings, orderDepths, ownTrades, marketTrades, position, obs]
    # ownTrades: {symbol: [[symbol, price, qty, buyer, seller, timestamp], ...]}
    
    # Extract own trades for EMERALDS
    em_own_trades = []
    for entry in entries:
        state = entry[0]
        timestamp = state[0]
        own_trades = state[4]  # ownTrades
        position = state[6]  # position dict
        
        if "EMERALDS" in own_trades:
            for trade in own_trades["EMERALDS"]:
                # [symbol, price, qty, buyer, seller, timestamp]
                em_own_trades.append({
                    "tick_ts": timestamp,
                    "trade_price": trade[1],
                    "trade_qty": trade[2],
                    "buyer": trade[3],
                    "seller": trade[4],
                    "trade_ts": trade[5],
                    "position": position.get("EMERALDS", 0),
                })
    
    print(f"\nEMERALDS own trades: {len(em_own_trades)}")
    print(f"{'tick_ts':>8} {'price':>6} {'qty':>4} {'buyer':>10} {'seller':>10} {'position':>5}")
    print("-" * 50)
    for t in em_own_trades:
        print(f"{t['tick_ts']:>8} {t['trade_price']:>6} {t['trade_qty']:>4} {t['buyer']:>10} {t['seller']:>10} {t['position']:>5}")
    
    # Now we can see the EXACT prices and directions!
    # Price 9993 = we bought (bid filled) 
    # Price 10007 = we sold (ask filled)
    # Price 9994 = we bought at skewed bid
    # Price 10006 = we sold at skewed ask
    
    print("\n\nFILL PRICE DISTRIBUTION:")
    from collections import Counter
    price_counts = Counter(t['trade_price'] for t in em_own_trades)
    for price, count in sorted(price_counts.items()):
        total_qty = sum(t['trade_qty'] for t in em_own_trades if t['trade_price'] == price)
        print(f"  Price {price}: {count} fills, total qty={total_qty}")
    
    # Position at each fill
    print("\n\nPOSITION AT FILL TIME:")
    for t in em_own_trades:
        # Position is AFTER the fill (position at the tick where own_trade appears)
        # own_trades appear at the NEXT tick after the fill
        print(f"  t={t['tick_ts']:>6} price={t['trade_price']} qty={t['trade_qty']:>3} pos_after={t['position']:>4}")
    
    # Track position evolution
    print("\n\nPOSITION EVOLUTION:")
    position_timeline = []
    for entry in entries:
        state = entry[0]
        ts = state[0]
        pos = state[6].get("EMERALDS", 0)
        position_timeline.append((ts, pos))
    
    # Find max and min position
    max_pos = max(p for _, p in position_timeline)
    min_pos = min(p for _, p in position_timeline)
    print(f"  Max position: {max_pos}")
    print(f"  Min position: {min_pos}")
    print(f"  Final position: {position_timeline[-1][1]}")
    
    # Count ticks at each position extreme
    extreme_ticks = sum(1 for _, p in position_timeline if abs(p) > 24)
    print(f"  Ticks with |pos| > 24 (skew active): {extreme_ticks}/{len(position_timeline)}")
    heavy_ticks = sum(1 for _, p in position_timeline if abs(p) > 48)
    print(f"  Ticks with |pos| > 48 (heavy skew): {heavy_ticks}/{len(position_timeline)}")
