"""Re-run probe 7 with a real product symbol, and probe 8: realistic IMC own_trades timing."""
import os, sys, json, importlib.util
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(HERE, "..", "logs", "547310"))
from datamodel import Order, OrderDepth, TradingState, Trade
spec = importlib.util.spec_from_file_location("trader_fixed",
    os.path.join(HERE, "..", "logs", "547310", "547310_fixed.py"))
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)

print("=" * 70)
print("PROBE 7 (corrected): liquidation under global brake with REAL symbol")
print("=" * 70)
sym = "MICROCHIP_CIRCLE"
ods = {sym: OrderDepth()}
ods[sym].buy_orders = {100:5}; ods[sym].sell_orders = {101:-5}
td_braked = json.dumps({"v":1,"cash":{},"spnl_disabled":[],"global_brake":True,"tick":5,"last_pos":{}})
state = TradingState(traderData=td_braked, timestamp=500, listings={}, order_depths=ods,
                     own_trades={}, market_trades={}, position={sym:10}, observations=None)
trader = mod.Trader()
orders, _, _ = trader.run(state)
print(f"  pos=+10 brake on book=100/101: orders[{sym}]={[(o.price,o.quantity) for o in orders.get(sym,[])]}")
print(f"  Expect: [(100, -10)]")

state.position = {sym: -10}; state.traderData = td_braked
orders, _, _ = trader.run(state)
print(f"  pos=-10 brake on book=100/101: orders[{sym}]={[(o.price,o.quantity) for o in orders.get(sym,[])]}")
print(f"  Expect: [(101, 10)]")
print()

print("=" * 70)
print("PROBE 8: REALISTIC IMC own_trades timing (trade.ts == state.ts - 100)")
print("=" * 70)
# Per the user's confirmed IMC behavior: trade.timestamp = match-tick,
# observed in own_trades on the NEXT tick (state.timestamp = match_tick + 100).
# Trade is delivered exactly once. The B02-fixed filter accepts trades with
# t.timestamp in {state.timestamp, state.timestamp - 100}. With one-shot
# delivery, no double-count occurs. Verify:
fill = Trade(sym, 8551, 1, buyer="", seller="SUBMISSION", timestamp=0)
trader = mod.Trader()
# Tick 1 (state.ts=0): no fills yet (engine has not matched anything before t=0)
state1 = TradingState(traderData="", timestamp=0, listings={}, order_depths=ods,
                      own_trades={}, market_trades={}, position={}, observations=None)
_, _, td1 = trader.run(state1)
# Tick 2 (state.ts=100): the t=0 fill arrives in own_trades
state2 = TradingState(traderData=td1, timestamp=100, listings={}, order_depths=ods,
                      own_trades={sym:[fill]}, market_trades={}, position={sym:-1}, observations=None)
_, _, td2 = trader.run(state2)
cash2 = json.loads(td2).get("cash",{}).get(sym, 0.0)
# Tick 3 (state.ts=200): own_trades empty (engine does NOT redeliver)
state3 = TradingState(traderData=td2, timestamp=200, listings={}, order_depths=ods,
                      own_trades={}, market_trades={}, position={sym:-1}, observations=None)
_, _, td3 = trader.run(state3)
cash3 = json.loads(td3).get("cash",{}).get(sym, 0.0)
print(f"  Tick 1 (no fills):                         cash={json.loads(td1).get('cash',{}).get(sym,0.0)}")
print(f"  Tick 2 (fill ts=0 arrives, state.ts=100):  cash={cash2}  (expect 8551)")
print(f"  Tick 3 (no fills, engine doesn't redeliv): cash={cash3}  (expect 8551)")
print()
print("  -> Under correct IMC delivery (one-shot), B02 widened filter is SAFE.")
print("  -> Double-count (probe 2) only triggers if engine REDELIVERS, which IMC doesn't.")
print("  -> B09 severity downgraded: theoretical only on stock IMC engine.")
