"""Phase 2 deeper analysis: simulate trader against the actual log."""
import json, csv, io, os, sys, traceback
from collections import defaultdict

ROOT = os.path.join(os.path.dirname(__file__), "..", "logs", "547310")
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Use the workspace datamodel
from datamodel import Order, OrderDepth, TradingState, Trade

# Import the failing trader as a module
import importlib.util
spec = importlib.util.spec_from_file_location("trader_547310", os.path.join(ROOT, os.environ.get("TRADER_FILE","547310.py")))
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)

def load_log():
    with open(os.path.join(ROOT, "547310.log"), "r", encoding="utf-8") as f:
        return json.load(f)

def main():
    env = load_log()
    rdr = csv.DictReader(io.StringIO(env["activitiesLog"]), delimiter=";")
    rows = list(rdr)
    by_ts = defaultdict(dict)
    for r in rows:
        by_ts[int(r["timestamp"])][r["product"]] = r
    timestamps = sorted(by_ts.keys())

    # ---- engine logs ----
    engine_logs = env.get("logs","")
    print(f"engine logs len: {len(engine_logs)}; first 1500 chars:")
    print(engine_logs[:1500])
    print("\n...last 1500 chars:")
    print(engine_logs[-1500:] if len(engine_logs)>1500 else engine_logs)
    print()

    # ---- Reconstruct order books and run trader on each tick to inspect orders ----
    trades = env.get("tradeHistory", [])
    # group own_trades by NEXT tick (own_trades arrive one tick later)
    own_by_next_ts = defaultdict(lambda: defaultdict(list))
    for t in trades:
        ts = int(t["timestamp"])
        if t.get("buyer") == "SUBMISSION" or t.get("seller") == "SUBMISSION":
            sym = t["symbol"]
            tr = Trade(sym, int(t["price"]), int(t["quantity"]),
                       buyer=t.get("buyer",""), seller=t.get("seller",""),
                       timestamp=ts)
            own_by_next_ts[ts+100][sym].append(tr)

    def od_from_row(r):
        od = OrderDepth(); od.buy_orders={}; od.sell_orders={}
        for i in (1,2,3):
            bp = r.get(f"bid_price_{i}"); bv = r.get(f"bid_volume_{i}")
            ap = r.get(f"ask_price_{i}"); av = r.get(f"ask_volume_{i}")
            if bp and bv:
                try: od.buy_orders[int(float(bp))] = int(bv)
                except: pass
            if ap and av:
                try: od.sell_orders[int(float(ap))] = -int(av)
                except: pass
        return od

    # Patch _run_safe-internal compute by mirroring it after run() for transparency
    def compute_spnl_after_run(state, td):
        s = mod.Trader._load_state(td)
        positions = {p: int(state.position.get(p,0)) for p in mod.ALL_PRODUCTS}
        # Re-apply cash update logic from _run_safe (without mutating real state)
        # Note: this uses the trader_data from BEFORE the current run, so cash here
        # is what the trader saw entering the tick (BEFORE own_trades processed).
        # Better: read the post-run trader_data after run() returns.
        return s

    trader = mod.Trader()
    trader_data = ""
    position = {p:0 for p in mod.ALL_PRODUCTS}

    # Apply own trades to position
    own_now = defaultdict(lambda: defaultdict(list))
    for t in trades:
        ts = int(t["timestamp"]); sym=t["symbol"]
        if t.get("buyer")=="SUBMISSION":
            own_now[ts][sym].append(("BUY", int(t["quantity"]), int(t["price"])))
        elif t.get("seller")=="SUBMISSION":
            own_now[ts][sym].append(("SELL", int(t["quantity"]), int(t["price"])))

    print(f"\n=== Simulating trader against historical books (first 20 ticks + diagnostic at key ticks) ===")
    diag_ticks = set([0, 100, 200, 500, 800, 900, 1000, 1100, 1200, 2000, 5000, 10000, 50000, 99900])
    summary = []
    for ts in timestamps:
        ods = {p: od_from_row(by_ts[ts][p]) for p in by_ts[ts]}
        # own_trades at this tick = trades that resolved at ts-100 (matched previous tick, surfaced now)
        ot = own_by_next_ts.get(ts, {})
        state = TradingState(traderData=trader_data, timestamp=ts,
                             listings={}, order_depths=ods, own_trades=dict(ot),
                             market_trades={}, position=dict(position), observations=None)
        try:
            orders, conv, td = trader.run(state)
            err = None
        except Exception as e:
            orders, conv, td, err = {}, 0, trader_data, traceback.format_exc()
        n_orders = sum(len(v) for v in orders.values())
        # apply own fills that happened AT this ts to position for next tick
        for sym, lst in own_now.get(ts, {}).items():
            for side,q,_ in lst:
                position[sym] = position.get(sym,0) + (q if side=="BUY" else -q)
        if ts in diag_ticks or ts <= 1000 and ts % 100 == 0:
            # decode state to read brakes
            try:
                ds = json.loads(td) if td else {}
            except:
                ds = {}
            print(f"ts={ts:6d} orders={n_orders:3d}  brake={ds.get('global_brake')} disabled={ds.get('spnl_disabled')} tick={ds.get('tick')}")
            if ts in (700, 800, 900, 1000):
                # Recompute spnl/global_pnl by hand
                cash = ds.get('cash', {})
                lp   = ds.get('last_pos', {})
                # Use post-run positions (from real position dict that we update each loop)
                spnl = {}; gpnl = 0.0
                for sym in mod.ALL_PRODUCTS:
                    od = ods.get(sym)
                    mid = mod._mid(od) if od else None
                    if mid is None: continue
                    pos = position.get(sym, 0)
                    mtm = float(cash.get(sym, 0.0)) + pos * mid
                    st = mod._strategy_of(sym)
                    spnl[st] = spnl.get(st, 0.0) + mtm
                    gpnl += mtm
                # show non-zero per-product cash + pos snapshot
                nz = {k: v for k,v in cash.items() if abs(v)>1e-6}
                print(f"   cash entries={len(cash)} non-zero={len(nz)} first5={list(cash.items())[:5]}")
                print(f"   spnl={spnl}")
                print(f"   global_pnl={gpnl:.2f}")
                # show a few microchip cash + position
                for sym in mod.GROUPS['MICROCHIP']:
                    print(f"     {sym} cash={cash.get(sym,0)} pos={position.get(sym,0)} mid={mod._mid(ods.get(sym))}")
            if err: print("  ERROR:", err.splitlines()[-1])
        if n_orders == 0 and ts < 5000:
            summary.append((ts, "ZERO_ORDERS", err))
        trader_data = td

    # report zero-order ticks in early window
    zo = [s for s in summary if s[1]=="ZERO_ORDERS"]
    print(f"\nZero-order ticks before ts=5000: {len(zo)}")
    for s in zo[:20]: print(" ",s)

    # decode final trader_data
    try:
        final = json.loads(trader_data) if trader_data else {}
    except: final = {}
    print(f"\nFinal trader state:")
    print("  global_brake:", final.get("global_brake"))
    print("  spnl_disabled:", final.get("spnl_disabled"))
    print("  cash entries:", len(final.get("cash",{})), "first 5:",
          list(final.get("cash",{}).items())[:5])
    # Final realized + MTM PnL = sum(cash[s] + position[s] * mid_at_last_ts)
    last_ts = timestamps[-1]
    last_row = by_ts[last_ts]
    cash = final.get("cash", {})
    final_pnl = 0.0
    for sym in mod.ALL_PRODUCTS:
        c = float(cash.get(sym, 0.0))
        pos = position.get(sym, 0)
        r = last_row.get(sym)
        mid = float(r["mid_price"]) if r and r.get("mid_price") else 0.0
        final_pnl += c + pos * mid
    print(f"\nSimulated FINAL PnL (cash + pos*mid_last): {final_pnl:+.2f}")
    nz_pos = {k:v for k,v in position.items() if v!=0}
    print(f"Final non-zero positions: {nz_pos}")

if __name__ == "__main__":
    main()
