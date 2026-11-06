"""Diagnostic: log market_trades and own_trades to understand trade flow data."""

import json, sys
from typing import Any, Dict, List, Optional, Tuple

from datamodel import (
    Listing, Observation, Order, OrderDepth, ConversionObservation,
    Trade, TradingState, Symbol, Product, Position,
)

class Trader:
    def __init__(self):
        self.tick = 0
        self.log_lines = []

    def run(self, state: TradingState) -> Tuple[Dict[str, List[Order]], int, str]:
        self.tick += 1
        
        # Log first 30 ticks of market_trades
        if self.tick <= 30:
            for sym in ["ASH_COATED_OSMIUM", "INTARIAN_PEPPER_ROOT"]:
                trades = state.market_trades.get(sym, [])
                if trades:
                    for t in trades:
                        info = f"TICK {state.timestamp} {sym} MARKET: buyer={t.buyer} seller={t.seller} price={t.price} qty={t.quantity}"
                        self.log_lines.append(info)
                
                own = state.own_trades.get(sym, [])
                if own:
                    for t in own:
                        print(f"TICK {state.timestamp} {sym} OWN: buyer={t.buyer} seller={t.seller} price={t.price} qty={t.quantity}")
        
        # Write diagnostics at tick 35
        if self.tick == 35:
            sys.stderr.write("\n=== TRADE DIAGNOSTICS ===\n")
            for line in self.log_lines:
                sys.stderr.write(line + "\n")
            sys.stderr.write("=== END DIAGNOSTICS ===\n")
        
        # Simple MM to generate some trades
        all_orders: Dict[str, List[Order]] = {}
        for sym in ["ASH_COATED_OSMIUM", "INTARIAN_PEPPER_ROOT"]:
            od = state.order_depths.get(sym)
            if od and od.buy_orders and od.sell_orders:
                bb = max(od.buy_orders.keys())
                ba = min(od.sell_orders.keys())
                pos = state.position.get(sym, 0)
                orders = []
                if 80 - pos > 0:
                    orders.append(Order(sym, bb, min(5, 80 - pos)))
                if 80 + pos > 0:
                    orders.append(Order(sym, ba, -min(5, 80 + pos)))
                all_orders[sym] = orders
        
        return all_orders, 0, ""

    def bid(self, state: TradingState) -> int:
        return 0
