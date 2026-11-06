"""Deep analysis of platform log 155873 - focusing on improvement opportunities."""
import json
import re

with open(r'.\logs\155873\155873.json') as f:
    d = json.load(f)

with open(r'.\logs\155873\155873.log') as f:
    log_content = f.read()

# Parse the log JSON to get trade data
log_data = json.loads(log_content)

# The log has sandboxLog field with per-tick data
sandbox_log = log_data.get('sandboxLog', '')
activities_log = d['activitiesLog']

# Parse our trader's compressed logs from the sandbox
# Each line in sandboxLog is our logger output
sandbox_lines = sandbox_log.strip().split('\n') if sandbox_log else []
print(f"Sandbox log lines: {len(sandbox_lines)}")

# Try to find our trades in the sandbox log
# Look for trade records  
trade_pattern = re.compile(r'"buyer":"(SUBMISSION|[^"]*?)","seller":"(SUBMISSION|[^"]*?)","symbol":"([^"]+)","currency":"[^"]+","price":([0-9.]+),"quantity":(\d+)')

trades = []
for match in trade_pattern.finditer(log_content):
    buyer, seller, symbol, price, qty = match.groups()
    side = 'BUY' if buyer == 'SUBMISSION' else 'SELL'
    trades.append({
        'symbol': symbol,
        'side': side,
        'price': float(price),
        'qty': int(qty),
    })

print(f"\nTotal trades found: {len(trades)}")

# Trades per product/side
from collections import Counter, defaultdict
trade_counts = Counter((t['symbol'], t['side']) for t in trades)
for key, count in sorted(trade_counts.items()):
    total_qty = sum(t['qty'] for t in trades if (t['symbol'], t['side']) == key)
    total_val = sum(t['qty'] * t['price'] for t in trades if (t['symbol'], t['side']) == key)
    avg_price = total_val / total_qty if total_qty > 0 else 0
    print(f"  {key[0]} {key[1]}: {count} trades, {total_qty} qty, avg_price={avg_price:.1f}")

# OSM trade analysis
print("\n=== OSM Trade Analysis ===")
osm_trades = [t for t in trades if t['symbol'] == 'ASH_COATED_OSMIUM']
osm_buys = [t for t in osm_trades if t['side'] == 'BUY']
osm_sells = [t for t in osm_trades if t['side'] == 'SELL']

buy_qty = sum(t['qty'] for t in osm_buys)
sell_qty = sum(t['qty'] for t in osm_sells)
buy_val = sum(t['qty'] * t['price'] for t in osm_buys)
sell_val = sum(t['qty'] * t['price'] for t in osm_sells)

print(f"  Bought: {buy_qty} units @ avg {buy_val/buy_qty:.1f}" if buy_qty else "  Bought: 0")
print(f"  Sold:   {sell_qty} units @ avg {sell_val/sell_qty:.1f}" if sell_qty else "  Sold: 0")
matched = min(buy_qty, sell_qty)
if buy_qty and sell_qty:
    trade_pnl = sell_val/sell_qty * matched - buy_val/buy_qty * matched
    print(f"  Matched qty: {matched}, avg spread capture: {(sell_val/sell_qty - buy_val/buy_qty):.2f}")
    print(f"  Net position: {buy_qty - sell_qty}")

# Buy/Sell price distributions
buy_prices = Counter(int(t['price']) for t in osm_buys)
sell_prices = Counter(int(t['price']) for t in osm_sells)
print(f"  Buy prices:  {sorted(buy_prices.items())}")
print(f"  Sell prices: {sorted(sell_prices.items())}")

# IPR trade analysis
print("\n=== IPR Trade Analysis ===")
ipr_trades = [t for t in trades if t['symbol'] == 'INTARIAN_PEPPER_ROOT']
ipr_buys = [t for t in ipr_trades if t['side'] == 'BUY']
ipr_sells = [t for t in ipr_trades if t['side'] == 'SELL']

buy_qty = sum(t['qty'] for t in ipr_buys)
sell_qty = sum(t['qty'] for t in ipr_sells)
buy_val = sum(t['qty'] * t['price'] for t in ipr_buys)
sell_val = sum(t['qty'] * t['price'] for t in ipr_sells)

print(f"  Bought: {buy_qty} units @ avg {buy_val/buy_qty:.1f}" if buy_qty else "  Bought: 0")
print(f"  Sold:   {sell_qty} units @ avg {sell_val/sell_qty:.1f}" if sell_qty else "  Sold: 0")
if buy_qty and sell_qty:
    print(f"  Matched qty: {min(buy_qty, sell_qty)}, avg spread capture: {(sell_val/sell_qty - buy_val/buy_qty):.2f}")
    print(f"  Net position: {buy_qty - sell_qty}")

buy_prices = Counter(int(t['price']) for t in ipr_buys)
sell_prices = Counter(int(t['price']) for t in ipr_sells)
print(f"  Buy prices (top5):  {buy_prices.most_common(5)}")
print(f"  Sell prices (top5): {sell_prices.most_common(5)}")

# How many ticks had no book (one side missing)?
print("\n=== Book Availability ===")
lines = activities_log.strip().split('\n')
osm_no_book = 0
ipr_no_book = 0 
osm_total = 0
ipr_total = 0
for line in lines[1:]:
    parts = line.split(';')
    if len(parts) > 10:
        prod = parts[2]
        bid1 = parts[3]
        ask1 = parts[9]
        if prod == 'ASH_COATED_OSMIUM':
            osm_total += 1
            if not bid1 or not ask1:
                osm_no_book += 1
        elif prod == 'INTARIAN_PEPPER_ROOT':
            ipr_total += 1
            if not bid1 or not ask1:
                ipr_no_book += 1

print(f"  OSM: {osm_no_book}/{osm_total} ticks with incomplete book ({100*osm_no_book/osm_total:.1f}%)")
print(f"  IPR: {ipr_no_book}/{ipr_total} ticks with incomplete book ({100*ipr_no_book/ipr_total:.1f}%)")

# What's our fill rate? Compare orders placed vs filled
# Check how often we're getting our make orders filled
# Estimate: with WIDTH=6 for OSM (FV=10000), we bid at 9994 and ask at 10006
# How often does the market reach our levels?
print("\n=== OSM: How often does market cross our levels (WIDTH=6, FV=10000)? ===")
bid_level = 9994
ask_level = 10006
market_hits_bid = 0
market_hits_ask = 0
for line in lines[1:]:
    parts = line.split(';')
    if len(parts) > 10 and parts[2] == 'ASH_COATED_OSMIUM':
        ask1 = parts[9]
        bid1 = parts[3]
        if ask1 and float(ask1) <= bid_level:
            market_hits_bid += 1
        if bid1 and float(bid1) >= ask_level:
            market_hits_ask += 1
print(f"  Market ask <= {bid_level} (fills our bid): {market_hits_bid} ticks")
print(f"  Market bid >= {ask_level} (fills our ask): {market_hits_ask} ticks")

# Also check take opportunities (prices below/above FV)
print("\n=== OSM: Take opportunities (price crossing FV) ===")
takes_buy = 0
takes_sell = 0
for line in lines[1:]:
    parts = line.split(';')
    if len(parts) > 10 and parts[2] == 'ASH_COATED_OSMIUM':
        ask1 = parts[9]
        bid1 = parts[3]
        if ask1 and float(ask1) <= 9999:  # take_best_asks at FV-1
            takes_buy += 1
        if bid1 and float(bid1) >= 10001:  # take_best_bids at FV+1
            takes_sell += 1
print(f"  Ask <= 9999 (take buy): {takes_buy} ticks")
print(f"  Bid >= 10001 (take sell): {takes_sell} ticks")

# IPR: check makes at WIDTH=4
print("\n=== IPR: Fill opportunity analysis ===")
# IPR mid drifts from ~12000 to ~12100, so fair ~ wmid
# With WIDTH=4, bid at fair-4, ask at fair+4
# With spread mode=13, our WIDTH=4 means we're 4 ticks inside the bot spread half (6.5)
# So we should fill when bot's L1 crosses our level
ipr_narrow_spread = 0
for line in lines[1:]:
    parts = line.split(';')
    if len(parts) > 10 and parts[2] == 'INTARIAN_PEPPER_ROOT':
        bid1 = parts[3]
        ask1 = parts[9]
        if bid1 and ask1:
            s = float(ask1) - float(bid1)
            if s <= 8:  # Narrow enough that WIDTH=4 could be inside
                ipr_narrow_spread += 1
print(f"  IPR ticks with spread <= 8: {ipr_narrow_spread}")
