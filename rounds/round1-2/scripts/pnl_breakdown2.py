"""Analyze PnL breakdown: takes vs makes, by product."""
import sys, os
sys.path.insert(0, r'.')

from prosperity4bt.file_reader import PackageResourcesReader
from prosperity4bt.runner import run_backtest
from prosperity4bt.models import TradeMatchingMode
from submission import Trader

fr = PackageResourcesReader()

for day in [-1, 0, 1]:
    trader = Trader()
    result = run_backtest(
        trader, fr, round_num=2, day_num=day, print_output=False,
        trade_matching_mode=TradeMatchingMode.worse,
        no_names=True, show_progress_bar=False
    )
    
    stats = {}
    for sym in ["ASH_COATED_OSMIUM", "INTARIAN_PEPPER_ROOT"]:
        stats[sym] = {"buy_cost": 0, "buy_qty": 0, "sell_rev": 0, "sell_qty": 0}
    
    for tr in result.trades:
        t = tr.trade
        sym = t.symbol
        if sym not in stats:
            continue
        if t.buyer == "SUBMISSION":
            stats[sym]["buy_cost"] += t.price * t.quantity
            stats[sym]["buy_qty"] += t.quantity
        elif t.seller == "SUBMISSION":
            stats[sym]["sell_rev"] += t.price * t.quantity
            stats[sym]["sell_qty"] += t.quantity
    
    print(f"\n=== Day {day} ===")
    for sym, s in stats.items():
        short = "ACO" if "ASH" in sym else "IPR"
        net_units = s["buy_qty"] - s["sell_qty"]
        trade_pnl = s["sell_rev"] - s["buy_cost"]
        print(f"{short}: bought {s['buy_qty']} @ avg {s['buy_cost']/s['buy_qty']:.1f}, sold {s['sell_qty']} @ avg {s['sell_rev']/s['sell_qty']:.1f}" if s['buy_qty'] and s['sell_qty'] else f"{short}: buy={s['buy_qty']}, sell={s['sell_qty']}")
        print(f"  Net units: {net_units}, Trade PnL: {trade_pnl}")
