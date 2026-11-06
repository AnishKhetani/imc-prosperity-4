"""Analyze PnL breakdown: takes vs makes, by product, position distribution."""
import json, sys, os
sys.path.insert(0, os.path.dirname(__file__) + '/..')

from prosperity4bt.data import read_day_data
from prosperity4bt.file_reader import PackageResourcesReader
from prosperity4bt.runner import run_backtest
from prosperity4bt.models import TradeMatchingMode

# Import our trader
from importlib import import_module
sys.path.insert(0, os.path.dirname(__file__) + '/..')
mod = import_module('submission')

trader = mod.Trader()
fr = PackageResourcesReader()

for day in [-1, 0, 1]:
    data = read_day_data(fr, 2, day, False)
    result = run_backtest(trader, data, print_output=False)
    
    # Analyze trades
    aco_buy_pnl = 0
    aco_sell_pnl = 0
    aco_buy_count = 0
    aco_sell_count = 0
    ipr_buy_pnl = 0
    ipr_sell_pnl = 0
    ipr_buy_count = 0
    ipr_sell_count = 0
    
    for trade_row in result.trades:
        t = trade_row.trade
        if t.buyer == "SUBMISSION":
            # We bought
            cost = t.price * t.quantity
            if t.symbol == "ASH_COATED_OSMIUM":
                aco_buy_pnl -= cost
                aco_buy_count += t.quantity
            else:
                ipr_buy_pnl -= cost
                ipr_buy_count += t.quantity
        elif t.seller == "SUBMISSION":
            # We sold
            revenue = t.price * t.quantity
            if t.symbol == "ASH_COATED_OSMIUM":
                aco_sell_pnl += revenue
                aco_sell_count += t.quantity
            else:
                ipr_sell_pnl += revenue
                ipr_sell_count += t.quantity
    
    print(f"\n=== Day {day} ===")
    print(f"ACO: bought {aco_buy_count} units (spent {-aco_buy_pnl}), sold {aco_sell_count} units (earned {aco_sell_pnl})")
    print(f"  Net units: {aco_buy_count - aco_sell_count}, Net PnL from trades: {aco_buy_pnl + aco_sell_pnl}")
    print(f"  Avg buy: {-aco_buy_pnl/aco_buy_count:.1f}, Avg sell: {aco_sell_pnl/aco_sell_count:.1f}" if aco_buy_count and aco_sell_count else "")
    print(f"IPR: bought {ipr_buy_count} units (spent {-ipr_buy_pnl}), sold {ipr_sell_count} units (earned {ipr_sell_pnl})")
    print(f"  Net units: {ipr_buy_count - ipr_sell_count}, Net PnL from trades: {ipr_buy_pnl + ipr_sell_pnl}")
    print(f"  Avg buy: {-ipr_buy_pnl/ipr_buy_count:.1f}, Avg sell: {ipr_sell_pnl/ipr_sell_count:.1f}" if ipr_buy_count and ipr_sell_count else "")

    # Count fills against order book vs market trades
    ob_fills = 0
    mt_fills = 0
    for trade_row in result.trades:
        t = trade_row.trade
        if t.buyer == "SUBMISSION" and t.seller == "":
            ob_fills += 1
        elif t.seller == "SUBMISSION" and t.buyer == "":
            ob_fills += 1
        else:
            mt_fills += 1
    print(f"  OB fills: {ob_fills}, Market trade fills: {mt_fills}")
