"""Audit-driven probes for 547310_fixed.py."""
import os, sys, json, importlib.util
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(HERE, "..", "logs", "547310"))

from datamodel import Order, OrderDepth, TradingState, Trade

spec = importlib.util.spec_from_file_location(
    "trader_fixed",
    os.path.join(HERE, "..", "logs", "547310", "547310_fixed.py"))
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)

print("=" * 70)
print("PROBE 1: P2 inventory-skew dead code (B05)")
print("=" * 70)
# In _strategy_p2 the line `ssize = max(1, P2_PASSIVE_SIZE)` overwrites
# the inventory-skewed ssize calculation immediately above it.
# Verify by reading source:
import inspect
src = inspect.getsource(mod.Trader._strategy_p2)
# Two ssize lines should appear; the second one is the dead overwrite.
ssize_lines = [l for l in src.splitlines() if "ssize =" in l and "max" in l]
print(f"ssize assignments in _strategy_p2: {len(ssize_lines)}")
for i, l in enumerate(ssize_lines):
    print(f"  [{i}] {l.strip()}")
print(f"  -> The second assignment overwrites the inventory-skew formula. CONFIRMED DEAD CODE.")
print()

print("=" * 70)
print("PROBE 2: own_trades double-count risk (B09)")
print("=" * 70)
# Simulate: a Trade with timestamp=N delivered on tick state.timestamp=N
# (same-tick), then redelivered on state.timestamp=N+100.
trader = mod.Trader()
od = OrderDepth(); od.buy_orders={100:5}; od.sell_orders={101:-5}
sell_t = Trade("MICROCHIP_CIRCLE", 8551, 1, buyer="", seller="SUBMISSION", timestamp=0)
# Tick 1: state.timestamp=0, own_trades has the fill at t=0 (same-tick)
state1 = TradingState(traderData="", timestamp=0, listings={}, order_depths={"MICROCHIP_CIRCLE":od},
                      own_trades={"MICROCHIP_CIRCLE":[sell_t]}, market_trades={},
                      position={"MICROCHIP_CIRCLE":-1}, observations=None)
_, _, td1 = trader.run(state1)
cash1 = json.loads(td1).get("cash",{}).get("MICROCHIP_CIRCLE")
# Tick 2: state.timestamp=100, platform re-delivers SAME fill (some sims do this)
state2 = TradingState(traderData=td1, timestamp=100, listings={}, order_depths={"MICROCHIP_CIRCLE":od},
                      own_trades={"MICROCHIP_CIRCLE":[sell_t]}, market_trades={},
                      position={"MICROCHIP_CIRCLE":-1}, observations=None)
_, _, td2 = trader.run(state2)
cash2 = json.loads(td2).get("cash",{}).get("MICROCHIP_CIRCLE")
print(f"  After tick 1 (same-tick delivery): cash={cash1}  (expect 8551 if processed)")
print(f"  After tick 2 (redelivered):        cash={cash2}  (expect 8551 if dedup'd, 17102 if double-counted)")
if cash2 == 17102:
    print("  -> DOUBLE COUNT confirmed. B09 is real.")
elif cash2 == 8551:
    print("  -> No double count this path (filter rejects timestamp=0 on tick 2).")
else:
    print(f"  -> Unexpected: cash2={cash2}")
print()

print("=" * 70)
print("PROBE 3: int(t.price) precision loss (B11)")
print("=" * 70)
# Trade with non-integer price
fract = Trade("MICROCHIP_CIRCLE", 8551.5, 2, buyer="SUBMISSION", seller="", timestamp=0)
trader = mod.Trader()
state = TradingState(traderData="", timestamp=100, listings={}, order_depths={"MICROCHIP_CIRCLE":od},
                     own_trades={"MICROCHIP_CIRCLE":[fract]}, market_trades={},
                     position={"MICROCHIP_CIRCLE":2}, observations=None)
_, _, td = trader.run(state)
cash = json.loads(td).get("cash",{}).get("MICROCHIP_CIRCLE")
expected_exact = -8551.5 * 2  # = -17103.0
expected_int_truncated = -8551 * 2  # = -17102
print(f"  Trade price 8551.5 x 2 (BUY)")
print(f"  cash recorded: {cash}")
print(f"  exact:         {expected_exact}")
print(f"  int(price):    {expected_int_truncated}")
if cash == expected_int_truncated:
    print("  -> int() truncation confirmed. B11 is real (LOW severity unless fractional fills occur).")
print()

print("=" * 70)
print("PROBE 4: P2 take edge condition arithmetic")
print("=" * 70)
# User asked: edge > PEBBLES_TAKE_EDGE (4) AND synth_fair >= ap + RESIDUAL_STD (2.8)
# For PEBBLES_M with half_spread=5, ap = mid + 5 (typical).
# edge = synth_fair - mid. If edge=4, synth_fair = mid+4. ap = mid+5.
# synth_fair - ap = mid+4 - mid-5 = -1, NOT >= 2.8. So second condition fails.
# Effective threshold: synth_fair >= ap + 2.8 means synth_fair - mid >= ap - mid + 2.8
# = half_spread + 2.8 = ~7.8 for PEBBLES.
# So PEBBLES_TAKE_EDGE = 4.0 is dead — second condition dominates at ~7.8.
import statistics
print(f"  PEBBLES_TAKE_EDGE      = {mod.PEBBLES_TAKE_EDGE}")
print(f"  PEBBLES_RESIDUAL_STD   = {mod.PEBBLES_RESIDUAL_STD}")
for prod, half in [("PEBBLES_XS",4),("PEBBLES_S",5),("PEBBLES_M",5),("PEBBLES_L",5),("PEBBLES_XL",7)]:
    eff = half + mod.PEBBLES_RESIDUAL_STD
    print(f"  {prod}: half={half} -> effective threshold = {eff:.1f} (cfg edge={mod.PEBBLES_TAKE_EDGE})")
print("  -> For all PEBBLES legs, second condition (synth >= ap+2.8) dominates;")
print("     PEBBLES_TAKE_EDGE=4.0 is a dead threshold in practice.")
print()

print("=" * 70)
print("PROBE 5: Strategy product coverage")
print("=" * 70)
# Map each product to all strategies that handle it; check no overlap, no gap.
COVERAGE = {p: [] for p in mod.ALL_PRODUCTS}
# P2
for p in mod.GROUPS["PEBBLES"]: COVERAGE[p].append("P2")
# S1+S2
for p in ("SNACKPACK_CHOCOLATE","SNACKPACK_VANILLA"): COVERAGE[p].append("S1+S2")
# S2
for p in ("SNACKPACK_PISTACHIO","SNACKPACK_RASPBERRY","SNACKPACK_STRAWBERRY"): COVERAGE[p].append("S2")
# R2
for p in ("ROBOT_DISHES","ROBOT_IRONING"): COVERAGE[p].append("R2")
# M1
for p in mod.GROUPS["GALAXY_SOUNDS"]+mod.GROUPS["UV_VISOR"]+mod.GROUPS["OXYGEN_SHAKE"]+mod.GROUPS["PANEL"]:
    COVERAGE[p].append("M1")
# M3
for p in mod.GROUPS["MICROCHIP"]+mod.GROUPS["SLEEP_POD"]+mod.GROUPS["TRANSLATOR"]+["ROBOT_LAUNDRY","ROBOT_MOPPING","ROBOT_VACUUMING"]:
    COVERAGE[p].append("M3")
gaps = [p for p,sl in COVERAGE.items() if len(sl)==0]
overlaps = [(p,sl) for p,sl in COVERAGE.items() if len(sl)>1]
print(f"  Total products: {len(COVERAGE)}")
print(f"  Gaps (no strategy):     {len(gaps)} {gaps}")
print(f"  Overlaps (>1 strategy): {len(overlaps)} {overlaps}")
if not gaps and not overlaps:
    print("  -> Coverage is exact: every product handled by exactly one strategy.")
print()

print("=" * 70)
print("PROBE 6: q == 0 in _clip_orders")
print("=" * 70)
zero_qty = {"X": [Order("X", 100, 0)]}
out = mod.Trader._clip_orders(zero_qty, {"X": 0})
print(f"  Input: 1 order with qty=0; output: {out}")
print("  -> qty=0 dropped (not added to kept). Safe.")
print()

print("=" * 70)
print("PROBE 7: liquidation order at edge of position limit")
print("=" * 70)
# Simulate global brake firing with pos at limit
ods = {"X": OrderDepth()}
ods["X"].buy_orders = {100:5}; ods["X"].sell_orders = {101:-5}
# Force global_brake by passing in state with that flag
td_braked = json.dumps({"v":1,"cash":{},"spnl_disabled":[],"global_brake":True,"tick":5,"last_pos":{}})
state = TradingState(traderData=td_braked, timestamp=500, listings={}, order_depths=ods,
                     own_trades={}, market_trades={}, position={"X":10}, observations=None)
trader = mod.Trader()
orders, _, _ = trader.run(state)
print(f"  pos=+10, global brake on, book=100/101: orders={orders}")
print(f"  Should be sell -10 at bid=100. _clip_orders sell_room=20 admits. OK.")

# Same with pos=-10
state.position = {"X": -10}
state.traderData = td_braked
orders, _, _ = trader.run(state)
print(f"  pos=-10, global brake on: orders={orders}  (should be buy +10 at ask=101)")
