"""Phase 1+2+3 forensics for submission 547310."""
import json, csv, io, os, statistics
from collections import defaultdict, Counter

ROOT = os.path.join(os.path.dirname(__file__), "..", "logs", "547310")

def load_log():
    """The .log is a JSON envelope; activitiesLog is a CSV string."""
    with open(os.path.join(ROOT, "547310.log"), "r", encoding="utf-8") as f:
        env = json.load(f)
    return env

def load_result():
    with open(os.path.join(ROOT, "547310.json"), "r", encoding="utf-8") as f:
        return json.load(f)

def main():
    env = load_log()
    res = load_result()
    print("=== TOP-LEVEL KEYS ===")
    print("log keys :", sorted(env.keys()))
    print("json keys:", sorted(res.keys()))

    # ---- activitiesLog CSV ----
    act_csv = env.get("activitiesLog","")
    rdr = csv.DictReader(io.StringIO(act_csv), delimiter=";")
    rows = list(rdr)
    print(f"\nactivities rows: {len(rows)}")
    print("activities cols:", rdr.fieldnames)
    # group by timestamp
    by_ts = defaultdict(dict)
    for r in rows:
        ts = int(r["timestamp"]); by_ts[ts][r["product"]] = r
    timestamps = sorted(by_ts.keys())
    print(f"timestamps: {len(timestamps)} from {timestamps[0]} to {timestamps[-1]}")

    # ---- Phase 1: PnL trajectory ----
    # PnL is in profit_and_loss column per row.
    pnl_total_by_ts = {}
    for ts in timestamps:
        s = 0.0
        for r in by_ts[ts].values():
            try: s += float(r.get("profit_and_loss") or 0)
            except: pass
        pnl_total_by_ts[ts] = s
    # find first non-zero
    first_nz = next((ts for ts in timestamps if abs(pnl_total_by_ts[ts])>1e-9), None)
    print(f"\nFirst non-zero total PnL at ts={first_nz}, value={pnl_total_by_ts.get(first_nz)}")
    # last non-zero
    last_nz = None
    for ts in timestamps:
        if abs(pnl_total_by_ts[ts])>1e-9: last_nz = ts
    final_pnl = pnl_total_by_ts[timestamps[-1]]
    print(f"Final total PnL = {final_pnl}")
    # find when PnL stopped changing
    last_change_ts = timestamps[0]; prev = pnl_total_by_ts[timestamps[0]]
    for ts in timestamps[1:]:
        if abs(pnl_total_by_ts[ts]-prev) > 1e-9:
            last_change_ts = ts; prev = pnl_total_by_ts[ts]
    print(f"Last PnL change at ts={last_change_ts}, value={pnl_total_by_ts[last_change_ts]}")

    # ---- per-product PnL trajectory ----
    print("\n=== Per-product final PnL (non-zero only) ===")
    prods_with_pnl = []
    for prod in sorted({r["product"] for r in rows}):
        last = 0.0
        for ts in timestamps:
            r = by_ts[ts].get(prod)
            if r:
                try: last = float(r.get("profit_and_loss") or 0)
                except: pass
        if abs(last) > 1e-9:
            prods_with_pnl.append((prod,last))
            print(f"  {prod:35s}  {last:+.2f}")
    print(f"  SUM: {sum(v for _,v in prods_with_pnl):.2f}")

    # ---- Phase 1: trade reconstruction ----
    # tradeHistory lives in .log envelope per IMC backtester schema
    trades = env.get("tradeHistory") or res.get("trades") or []
    print(f"\n=== tradeHistory count: {len(trades)} ===")
    if trades:
        print("first trade keys:", sorted(trades[0].keys()))
        print("first 5 trades:")
        for t in trades[:5]: print(" ", t)
    # find own trades — trades where buyer or seller == "" (per task)
    # Per platform, SUBMISSION trades use empty string in buyer/seller fields.
    own_buys = [t for t in trades if t.get("buyer")=="SUBMISSION"]
    own_sells = [t for t in trades if t.get("seller")=="SUBMISSION"]
    own_empty = [t for t in trades if t.get("buyer")=="" or t.get("seller")==""]
    print(f"trades with buyer=='SUBMISSION': {len(own_buys)}")
    print(f"trades with seller=='SUBMISSION': {len(own_sells)}")
    print(f"trades with empty buyer or seller: {len(own_empty)}")
    # Buyer/seller value distribution
    buyers = Counter(t.get("buyer","?") for t in trades)
    sellers = Counter(t.get("seller","?") for t in trades)
    print("buyer values:", dict(buyers.most_common(10)))
    print("seller values:", dict(sellers.most_common(10)))

    # ---- own trades are usually in res['ownTrades'] or res['tradeHistory'] - check ----
    for k in ("ownTrades","trade_history","activities","sandboxLog"):
        if k in res:
            v = res[k]
            print(f"key {k}: type={type(v).__name__} len={len(v) if hasattr(v,'__len__') else 'na'}")

    # ---- check the sandboxLog from .log envelope ----
    sand = env.get("sandboxLog","")
    print(f"\nsandboxLog length: {len(sand)} chars; first 500:")
    print(repr(sand[:500]))

    # ---- locate all trades around first PnL change ----
    if first_nz is not None:
        print(f"\n=== Trades in window [{first_nz-200},{first_nz+200}] ===")
        window = [t for t in trades if first_nz-200 <= int(t.get("timestamp",0)) <= first_nz+200]
        for t in window[:50]: print(" ",t)
        print(f"  ({len(window)} trades in window)")

    # ---- PEBBLES sum at ts 0 ----
    print("\n=== PEBBLES mids at ts=0 ===")
    pebbles_legs = ["PEBBLES_XS","PEBBLES_S","PEBBLES_M","PEBBLES_L","PEBBLES_XL"]
    s_mid = 0.0; ok = True
    for p in pebbles_legs:
        r = by_ts[0].get(p)
        if not r: print(p,"MISSING"); ok=False; continue
        try:
            mid = float(r.get("mid_price") or 0)
            print(f"  {p:14s} mid={mid}")
            s_mid += mid
        except: pass
    print(f"  SUM = {s_mid} (target 50000)  delta={s_mid-50000}")

    print("\n=== SNACK pair at ts=0 ===")
    for p in ("SNACKPACK_CHOCOLATE","SNACKPACK_VANILLA"):
        r = by_ts[0].get(p)
        if r: print(f"  {p}: bid={r['bid_price_1']} ask={r['ask_price_1']} mid={r['mid_price']}")

    # ---- Phase 3: who trades at strict-inside? Use trades vs touch ----
    # We need order book context per (ts,prod) and trade price. Compare to touch.
    print("\n=== Trade price vs touch analysis (sample 1000) ===")
    inside_count = 0; at_touch = 0; through = 0; missing = 0
    sample = trades[:5000]
    for t in sample:
        ts = int(t.get("timestamp",0)); prod = t.get("symbol",""); px = float(t.get("price",0))
        r = by_ts.get(ts,{}).get(prod)
        if not r: missing += 1; continue
        try:
            bid = float(r.get("bid_price_1") or 0); ask = float(r.get("ask_price_1") or 0)
        except: continue
        if px == bid or px == ask: at_touch += 1
        elif bid < px < ask: inside_count += 1
        else: through += 1
    print(f"  at_touch={at_touch}  inside={inside_count}  through={through}  missing_book={missing}  (sample {len(sample)})")

    # ---- Phase 3: for own trades (if identifiable), where did we fill? ----
    own_set = [t for t in trades if (t.get("buyer")=="SUBMISSION" or t.get("seller")=="SUBMISSION")]
    print(f"\nOwn trades (buyer/seller=='SUBMISSION'): {len(own_set)}")
    for t in own_set[:30]: print(" ",t)

    # ---- Save summary ----
    return env, res, by_ts, timestamps, pnl_total_by_ts, trades

if __name__ == "__main__":
    main()
