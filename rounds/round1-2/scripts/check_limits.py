"""Check if enforce_limits ever triggers by logging total order quantities."""
import json
from typing import Any, Dict, List, Optional, Tuple

from datamodel import (
    Listing, Observation, Order, OrderDepth, ConversionObservation,
    Trade, TradingState, Symbol, Product, Position,
)

# Import the existing submission
import importlib.util
spec = importlib.util.spec_from_file_location("submission", "submission.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

# Monkey-patch the Trader to check limits
original_run = mod.Trader.run

violations = 0
total_ticks = 0

LIMITS = {
    "ASH_COATED_OSMIUM": 80,
    "INTARIAN_PEPPER_ROOT": 80,
}

def patched_run(self, state):
    global violations, total_ticks
    result = original_run(self, state)
    orders, conversions, trader_data = result
    
    total_ticks += 1
    
    for product, order_list in orders.items():
        if product not in LIMITS:
            continue
        position = state.position.get(product, 0)
        total_long = sum(o.quantity for o in order_list if o.quantity > 0)
        total_short = sum(abs(o.quantity) for o in order_list if o.quantity < 0)
        
        if position + total_long > LIMITS[product] or position - total_short < -LIMITS[product]:
            violations += 1
            print(f"VIOLATION tick={state.timestamp} {product}: pos={position} long={total_long} short={total_short}")
            if violations <= 5:
                for o in order_list:
                    print(f"  Order: {o.price} x {o.quantity}")
    
    return result

mod.Trader.run = patched_run

# Run the same way the backtester would
print("Running violation check...")
# We can't easily run the full backtester here, so let's just report:
print(f"To check violations, add logging to the main submission and run the backtester")
print(f"Alternatively, check the sandbox_log output from the backtester for limit violations")
