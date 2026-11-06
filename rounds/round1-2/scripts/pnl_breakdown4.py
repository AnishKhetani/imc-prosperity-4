"""Analyze PnL breakdown with mark-to-market."""
import sys, os
sys.path.insert(0, r'.')

from prosperity4bt.file_reader import PackageResourcesReader
from prosperity4bt.runner import run_backtest
from prosperity4bt.models import TradeMatchingMode
from submission import Trader

fr = PackageResourcesReader()

total_pnl = 0
for day in [-1, 0, 1]:
    trader = Trader()
    result = run_backtest(
        trader, fr, round_num=2, day_num=day, print_output=False,
        trade_matching_mode=TradeMatchingMode.worse,
        no_names=True, show_progress_bar=False
    )
    
    # Activity log columns: last column is profit_loss
    # Get final entry per product
    final = {}
    for log in result.activity_logs:
        cols = log.columns
        # columns format: [day, timestamp, product, ..., profit_loss]
        product = cols[2]
        pnl = cols[-1]
        final[product] = pnl
    
    print(f"\n=== Day {day} ===")
    day_pnl = 0
    for prod in sorted(final.keys()):
        short = "ACO" if "ASH" in prod else ("IPR" if "PEPPER" in prod else prod)
        print(f"  {short}: PnL = {final[prod]}")
        day_pnl += final[prod]
    total_pnl += day_pnl
    print(f"  Day total: {day_pnl}")
    
    # Count trades
    for sym in ["ASH_COATED_OSMIUM", "INTARIAN_PEPPER_ROOT"]:
        short = "ACO" if "ASH" in sym else "IPR"
        buys = [(t.trade.price, t.trade.quantity) for t in result.trades if t.trade.symbol == sym and t.trade.buyer == "SUBMISSION"]
        sells = [(t.trade.price, t.trade.quantity) for t in result.trades if t.trade.symbol == sym and t.trade.seller == "SUBMISSION"]
        buy_qty = sum(q for _, q in buys)
        sell_qty = sum(q for _, q in sells)
        print(f"  {short}: {len(buys)} buy fills ({buy_qty} units), {len(sells)} sell fills ({sell_qty} units)")

print(f"\nTotal PnL: {total_pnl}")
