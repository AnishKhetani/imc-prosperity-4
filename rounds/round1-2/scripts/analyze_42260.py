"""Deep analysis of platform sim 42260 vs 42183."""
import json, csv, io
from collections import Counter, defaultdict

with open('logs/42260/42260.json', 'r') as f:
    data = json.load(f)

print(f"=== SIM 42260 OVERVIEW ===")
print(f"Profit: {data['profit']}")
print(f"Status: {data['status']}")
print(f"Positions: {data['positions']}")

# Parse activity log
activities = data['activitiesLog']
reader = csv.DictReader(io.StringIO(activities), delimiter=';')
rows = list(reader)
print(f"Total activity rows: {len(rows)}")

emeralds_rows = [r for r in rows if r['product'] == 'EMERALDS']
tomatoes_rows = [r for r in rows if r['product'] == 'TOMATOES']

print(f"\nEMERALDS rows: {len(emeralds_rows)}")
print(f"TOMATOES rows: {len(tomatoes_rows)}")

e_last = emeralds_rows[-1]
t_last = tomatoes_rows[-1]
print(f"EMERALDS final PnL: {e_last['profit_and_loss']}")
print(f"TOMATOES final PnL: {t_last['profit_and_loss']}")

# === EMERALDS ORDER BOOK ANALYSIS ===
print(f"\n=== EMERALDS ORDER BOOK ===")
bp1_dist = Counter()
ap1_dist = Counter()
spreads = []
for r in emeralds_rows:
    bp1 = int(r['bid_price_1']) if r['bid_price_1'] else None
    ap1 = int(r['ask_price_1']) if r['ask_price_1'] else None
    if bp1: bp1_dist[bp1] += 1
    if ap1: ap1_dist[ap1] += 1
    if bp1 and ap1:
        spreads.append(ap1 - bp1)

print(f"Bid P1 distribution: {sorted(bp1_dist.items())}")
print(f"Ask P1 distribution: {sorted(ap1_dist.items())}")
print(f"Avg spread: {sum(spreads)/len(spreads):.2f}" if spreads else "No spreads")

# Count ticks with our orders visible in book
our_in_book = sum(1 for r in emeralds_rows 
    if r['bid_price_1'] and int(r['bid_price_1']) >= 9999)
print(f"Ticks with bid >= 9999 (our orders): {our_in_book}")

our_ask_in_book = sum(1 for r in emeralds_rows 
    if r['ask_price_1'] and int(r['ask_price_1']) <= 10001)
print(f"Ticks with ask <= 10001 (our orders): {our_ask_in_book}")

# === TOMATOES ORDER BOOK ANALYSIS ===
print(f"\n=== TOMATOES ORDER BOOK ===")
tom_spreads = []
for r in tomatoes_rows:
    bp1 = int(r['bid_price_1']) if r['bid_price_1'] else None
    ap1 = int(r['ask_price_1']) if r['ask_price_1'] else None
    if bp1 and ap1:
        tom_spreads.append(ap1 - bp1)

print(f"Avg spread: {sum(tom_spreads)/len(tom_spreads):.2f}" if tom_spreads else "No spreads")
print(f"Min spread: {min(tom_spreads)}" if tom_spreads else "")
print(f"Max spread: {max(tom_spreads)}" if tom_spreads else "")

# Count ticks with narrow spreads (our orders tightening)
narrow = sum(1 for s in tom_spreads if s <= 4)
print(f"Ticks with spread <= 4 (our orders tightening): {narrow}/{len(tom_spreads)}")

# === PARSE ALGO LOGS ===
print(f"\n=== ALGO LOG ANALYSIS ===")
log_text = data.get('graphLog', '')
if not log_text:
    # Try the .log file
    try:
        with open('logs/42260/42260.log', 'r') as f:
            log_text = f.read()
    except:
        pass

# Parse the compressed log format from our Logger
# Each line is: [compressed_state, compressed_orders, conversions, trader_data, logs]
import re

# Count fills from activity log pattern
# Let's look at PnL progression
print(f"\n=== PNL PROGRESSION ===")
e_pnl = []
t_pnl = []
for r in emeralds_rows:
    ts = int(r['timestamp'])
    pnl = float(r['profit_and_loss'])
    e_pnl.append((ts, pnl))

for r in tomatoes_rows:
    ts = int(r['timestamp'])
    pnl = float(r['profit_and_loss'])
    t_pnl.append((ts, pnl))

# Sample at intervals
for label, pnl_list in [("EMERALDS", e_pnl), ("TOMATOES", t_pnl)]:
    print(f"\n{label} PnL timeline (sampled):")
    step = max(1, len(pnl_list) // 20)
    for i in range(0, len(pnl_list), step):
        ts, pnl = pnl_list[i]
        print(f"  t={ts:6d}: PnL={pnl:.2f}")
    print(f"  FINAL:  PnL={pnl_list[-1][1]:.2f}")

# === LOOK FOR OUR TRADES IN THE LOG ===
print(f"\n=== LOG FILE ANALYSIS ===")
try:
    with open('logs/42260/42260.log', 'r') as f:
        log_lines = f.readlines()
    print(f"Log file lines: {len(log_lines)}")
    
    # Each line should be our compressed JSON output
    total_orders = 0
    ticks_with_orders = 0
    emerald_orders = 0
    tomato_orders = 0
    errors = 0
    
    for line in log_lines:
        line = line.strip()
        if not line:
            continue
        try:
            parsed = json.loads(line)
            if isinstance(parsed, list) and len(parsed) >= 5:
                state_info, orders_info, conversions, trader_data, logs = parsed
                if isinstance(orders_info, dict):
                    for sym, order_list in orders_info.items():
                        count = len(order_list)
                        total_orders += count
                        if sym == 'EMERALDS':
                            emerald_orders += count
                        elif sym == 'TOMATOES':
                            tomato_orders += count
                    if orders_info:
                        ticks_with_orders += 1
                
                # Check for warnings/errors in logs
                if isinstance(logs, str) and ('WARN' in logs or 'ERROR' in logs or 'CRITICAL' in logs):
                    errors += 1
        except (json.JSONDecodeError, ValueError):
            pass
    
    print(f"Ticks with orders: {ticks_with_orders}")
    print(f"Total orders placed: {total_orders}")
    print(f"  EMERALDS: {emerald_orders}")
    print(f"  TOMATOES: {tomato_orders}")
    print(f"Ticks with warnings/errors: {errors}")
    
except FileNotFoundError:
    print("No log file found")

# === COMPARE WITH 42183 ===
print(f"\n=== COMPARISON WITH 42183 ===")
print(f"42183 total profit: 898.578125")
print(f"42260 total profit: {data['profit']}")
print(f"Difference: {data['profit'] - 898.578125:.2f}")
print(f"42183 EMERALDS final PnL: 121")
print(f"42183 TOMATOES final PnL: 777.6")
print(f"42260 EMERALDS final PnL: {e_last['profit_and_loss']}")
print(f"42260 TOMATOES final PnL: {t_last['profit_and_loss']}")
