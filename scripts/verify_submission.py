"""Verification script for 547310_fixed.py â€” confirms the 4 critical fixes."""
import os, sys, json, importlib.util
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))      # workspace root for datamodel

from datamodel import Order, OrderDepth, TradingState, Trade

spec = importlib.util.spec_from_file_location("trader_fixed", os.path.join(HERE, "..", "submission.py"))
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)

failures = []

# ------------------------------------------------------------------
# 1. own_trades cash-update correctly attributes a fill on a product
#    whose cash entry was previously dropped by _encode_state (B01).
# ------------------------------------------------------------------
trader = mod.Trader()
# Tick 1: no fills, cash all-zero, encoded compactly (drops zero entries).
od = OrderDepth(); od.buy_orders={100:5}; od.sell_orders={101:-5}
state1 = TradingState(traderData="", timestamp=0, listings={}, order_depths={"MICROCHIP_CIRCLE":od},
                      own_trades={}, market_trades={}, position={}, observations=None)
_, _, td1 = trader.run(state1)
encoded = json.loads(td1)
assert encoded.get("cash") == {} or "MICROCHIP_CIRCLE" not in encoded.get("cash",{}), \
    "expected sparse cash after tick 1"

# Tick 2: own_trades reports a SELL fill on MICROCHIP_CIRCLE (we sold 1 @ 8551
# at timestamp 0). Cash must move to +8551 even though prior cash dict was sparse.
sell = Trade("MICROCHIP_CIRCLE", 8551, 1, buyer="", seller="SUBMISSION", timestamp=0)
state2 = TradingState(traderData=td1, timestamp=100, listings={}, order_depths={"MICROCHIP_CIRCLE":od},
                      own_trades={"MICROCHIP_CIRCLE":[sell]}, market_trades={},
                      position={"MICROCHIP_CIRCLE":-1}, observations=None)
_, _, td2 = trader.run(state2)
encoded2 = json.loads(td2)
chip_cash = encoded2.get("cash",{}).get("MICROCHIP_CIRCLE")
if chip_cash != 8551:
    failures.append(f"[B01] cash not credited: got {chip_cash}, want 8551")
else:
    print("[OK] B01 fix: cash correctly credited (+8551 on prior-zero product)")

# Decode brake state â€” should NOT be tripped (mtm = 8551 + (-1)*100.5 = 8450.5,
# but because we passed an artificial book at price 100/101, the trader's
# computed mtm is dominated by the sell receipt minus the (low) mark mid;
# either way the post-fill mtm should not be < -200).
if encoded2.get("global_brake") is True:
    failures.append("[B01] global_brake spuriously set after a single small fill")
else:
    print("[OK] B01 fix: brake not spuriously tripped")

# ------------------------------------------------------------------
# 2. _clip_orders never produces a quantity that breaches POSITION_LIMIT
#    from any starting position.
# ------------------------------------------------------------------
LIM = mod.POSITION_LIMIT
for start in (-LIM, -5, 0, 5, LIM):
    raw = {"X":[Order("X", 100, 50), Order("X", 100, -50)]}  # absurd over-sized
    out = mod.Trader._clip_orders(raw, {"X": start})
    net_buy  = sum(o.quantity for o in out.get("X",[]) if o.quantity>0)
    net_sell = -sum(o.quantity for o in out.get("X",[]) if o.quantity<0)
    if start + net_buy > LIM:   failures.append(f"[clip] breach long from {start}")
    if start - net_sell < -LIM: failures.append(f"[clip] breach short from {start}")
print(f"[OK] _clip_orders: no breaches across starts {[-LIM,-5,0,5,LIM]}")

# ------------------------------------------------------------------
# 3. _post_mm_quotes never returns an order set where buy_px >= sell_px.
# ------------------------------------------------------------------
for spread in (1, 2, 4, 10, 50):
    od = OrderDepth(); od.buy_orders={100:5}; od.sell_orders={100+spread:-5}
    out = {}
    mod.Trader._post_mm_quotes(out, {"X":od}, "X", 100+spread/2, 0, 3)
    orders = out.get("X",[])
    buys = [o.price for o in orders if o.quantity>0]
    sells = [o.price for o in orders if o.quantity<0]
    if buys and sells and max(buys) >= min(sells):
        failures.append(f"[mm] crossed quotes spread={spread} buys={buys} sells={sells}")
print("[OK] _post_mm_quotes: never crosses for spreads in (1,2,4,10,50)")

# ------------------------------------------------------------------
# 4. _encode_state / _load_state round-trip without data loss.
# ------------------------------------------------------------------
src = mod.Trader._default_state()
src["cash"]["MICROCHIP_CIRCLE"] = -14.0
src["cash"]["SNACKPACK_VANILLA"] = 19.5
src["spnl_disabled"] = ["R2"]
src["global_brake"] = False
src["tick"] = 42
src["last_pos"] = {"MICROCHIP_OVAL": -1, "SNACKPACK_VANILLA": 3}
encoded = mod.Trader._encode_state(src)
decoded = mod.Trader._load_state(encoded)
for k in ("MICROCHIP_CIRCLE","SNACKPACK_VANILLA"):
    if abs(decoded["cash"].get(k,0) - src["cash"][k]) > 1e-6:
        failures.append(f"[encode] cash[{k}] lost in round-trip: {decoded['cash'].get(k)} != {src['cash'][k]}")
if decoded["spnl_disabled"] != src["spnl_disabled"]:
    failures.append("[encode] spnl_disabled lost")
if decoded["tick"] != src["tick"]:
    failures.append("[encode] tick lost")
# B01 fix: every product must have a cash key in the loaded state
missing = [p for p in mod.ALL_PRODUCTS if p not in decoded["cash"]]
if missing:
    failures.append(f"[B01] {len(missing)} products missing from loaded cash dict")
print("[OK] _encode_state / _load_state round-trip preserves all fields")

# ------------------------------------------------------------------
# 5. Full run() returns valid orders on a mock TradingState with empty
#    traderData (first-tick simulation).
# ------------------------------------------------------------------
ods = {}
for p in mod.ALL_PRODUCTS[:5]:
    od = OrderDepth(); od.buy_orders={1000:10}; od.sell_orders={1010:-10}
    ods[p] = od
state = TradingState(traderData="", timestamp=0, listings={}, order_depths=ods,
                     own_trades={}, market_trades={}, position={}, observations=None)
trader = mod.Trader()
orders, conv, td = trader.run(state)
n_orders = sum(len(v) for v in orders.values())
if n_orders == 0:
    failures.append("[run] zero orders on first tick")
print(f"[OK] run() first tick: produced {n_orders} orders, conversions={conv}, traderData len={len(td)}")

# ------------------------------------------------------------------
# Summary
# ------------------------------------------------------------------
if failures:
    print("\nFAIL:")
    for f in failures: print(" -", f)
    sys.exit(1)
else:
    print("\nALL VERIFICATION CHECKS PASS")

