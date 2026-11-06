"""
Round 4 counterparty EDA.
Goal: identify each Mark NN's role per instrument:
  - Insider: trades near daily extremes, small/fixed size, few trades
  - Market maker: huge trade count, balanced buy/sell
  - Trend follower / mean reverter / informed flow

For each (counterparty, symbol) pair report:
  n_trades, n_buys, n_sells, avg_size, distinct_sizes,
  buy_avg_px, sell_avg_px, buy_pct_at_or_below_low_q10, sell_pct_at_or_above_high_q90,
  daily extreme hit-rate (buy at daily low, sell at daily high),
  realised round-trip PnL if they fully closed (using mid at end of day)

Also: cross-tab buyer x seller — known MM pairs.
"""
import csv
import math
import os
from collections import defaultdict

ROOT = os.path.join(os.path.dirname(__file__), "..", "round_data", "ROUND_4")
DAYS = [1, 2, 3]


def load_trades(day):
    rows = []
    with open(os.path.join(ROOT, f"trades_round_4_day_{day}.csv"), encoding="utf-8") as f:
        for row in csv.DictReader(f, delimiter=";"):
            row["timestamp"] = int(row["timestamp"])
            row["price"] = float(row["price"])
            row["quantity"] = int(row["quantity"])
            rows.append(row)
    return rows


def load_prices(day):
    """Return dict[symbol][timestamp] = mid_price."""
    out = defaultdict(dict)
    with open(os.path.join(ROOT, f"prices_round_4_day_{day}.csv"), encoding="utf-8") as f:
        for row in csv.DictReader(f, delimiter=";"):
            sym = row["product"]
            ts = int(row["timestamp"])
            try:
                mid = float(row["mid_price"])
            except (TypeError, ValueError):
                continue
            out[sym][ts] = mid
    return out


def daily_extremes(prices_day):
    """For each symbol return (min_mid, max_mid)."""
    out = {}
    for sym, series in prices_day.items():
        if not series:
            continue
        vals = list(series.values())
        out[sym] = (min(vals), max(vals))
    return out


def main():
    # Aggregate by (counterparty, symbol, side) across all days
    agg = defaultdict(lambda: {
        "trades": [],            # (day, ts, price, qty, side, daily_min, daily_max, mid_at_ts)
    })
    pair_count = defaultdict(int)  # (buyer, seller, symbol)
    daily_pnl = defaultdict(float) # (counterparty, symbol) -> realised+mark PnL using day mids

    last_mid_per_day = {}

    for day in DAYS:
        trades = load_trades(day)
        prices = load_prices(day)
        extremes = daily_extremes(prices)
        # last mid for closing mark
        for sym, series in prices.items():
            if series:
                last_ts = max(series.keys())
                last_mid_per_day[(day, sym)] = series[last_ts]

        # build per-trader inventory for round-trip PnL
        inv = defaultdict(lambda: {"qty": 0, "cash": 0.0})  # (cp, sym)

        for t in trades:
            sym = t["symbol"]
            ts = t["timestamp"]
            px = t["price"]
            qty = t["quantity"]
            # find mid at or before ts
            series = prices.get(sym, {})
            mid = series.get(ts)
            if mid is None and series:
                # fallback: nearest earlier ts
                ks = [k for k in series if k <= ts]
                if ks:
                    mid = series[max(ks)]
            dmin, dmax = extremes.get(sym, (None, None))
            for cp, side in [(t["buyer"], "B"), (t["seller"], "S")]:
                if not cp:
                    continue
                key = (cp, sym)
                agg[key]["trades"].append({
                    "day": day, "ts": ts, "px": px, "qty": qty,
                    "side": side, "dmin": dmin, "dmax": dmax, "mid": mid,
                })
                if side == "B":
                    inv[key]["qty"] += qty
                    inv[key]["cash"] -= qty * px
                else:
                    inv[key]["qty"] -= qty
                    inv[key]["cash"] += qty * px
            pair_count[(t["buyer"], t["seller"], sym)] += t["quantity"]

        # close out at day end mid
        for key, pos in inv.items():
            cp, sym = key
            close_mid = last_mid_per_day.get((day, sym))
            if close_mid is None:
                continue
            pnl = pos["cash"] + pos["qty"] * close_mid
            daily_pnl[key] += pnl

    # Summary table
    print(f"{'CP':<10} {'SYM':<28} {'N':>5} {'B':>5} {'S':>5} {'avgSz':>6} "
          f"{'sizes':>20} {'bAvg':>9} {'sAvg':>9} "
          f"{'buy@low%':>8} {'sell@hi%':>8} {'PnL':>10}")
    rows = []
    for (cp, sym), data in agg.items():
        ts = data["trades"]
        if len(ts) < 3:
            continue
        n = len(ts)
        buys = [x for x in ts if x["side"] == "B"]
        sells = [x for x in ts if x["side"] == "S"]
        sizes = [x["qty"] for x in ts]
        unique_sizes = sorted(set(sizes))
        avg_sz = sum(sizes) / n
        b_avg = sum(x["px"] * x["qty"] for x in buys) / max(1, sum(x["qty"] for x in buys)) if buys else 0
        s_avg = sum(x["px"] * x["qty"] for x in sells) / max(1, sum(x["qty"] for x in sells)) if sells else 0
        # extreme hit-rate: buy within 10% of daily range from the bottom; sell within 10% from top
        def near_extreme(t, side):
            dmin, dmax = t["dmin"], t["dmax"]
            if dmin is None or dmax is None or dmax == dmin:
                return False
            r = dmax - dmin
            if side == "B":
                return (t["px"] - dmin) <= 0.10 * r
            else:
                return (dmax - t["px"]) <= 0.10 * r
        buy_hit = sum(1 for x in buys if near_extreme(x, "B")) / max(1, len(buys))
        sell_hit = sum(1 for x in sells if near_extreme(x, "S")) / max(1, len(sells))
        pnl = daily_pnl[(cp, sym)]
        rows.append((cp, sym, n, len(buys), len(sells), avg_sz,
                     unique_sizes, b_avg, s_avg, buy_hit, sell_hit, pnl))

    # sort by abs(pnl) descending to find informed players first
    rows.sort(key=lambda r: -abs(r[11]))
    for r in rows:
        cp, sym, n, b, s, avg_sz, sizes, b_avg, s_avg, bh, sh, pnl = r
        sz_str = ",".join(str(z) for z in sizes[:6])
        print(f"{cp:<10} {sym:<28} {n:>5} {b:>5} {s:>5} {avg_sz:>6.1f} "
              f"{sz_str:>20} {b_avg:>9.2f} {s_avg:>9.2f} "
              f"{bh*100:>7.1f}% {sh*100:>7.1f}% {pnl:>10.0f}")

    print()
    print("=== Top buyer/seller pairs (by total qty) ===")
    pair_rows = sorted(pair_count.items(), key=lambda x: -x[1])[:30]
    for (b, s, sym), q in pair_rows:
        print(f"{b:<10} -> {s:<10} {sym:<28} {q}")

    # === Per-counterparty trade timing pattern ===
    print()
    print("=== Trade-count per day per (cp, sym) — looking for 1-2 trades/day = insider ===")
    by_cp_sym_day = defaultdict(int)
    for (cp, sym), data in agg.items():
        for t in data["trades"]:
            by_cp_sym_day[(cp, sym, t["day"])] += 1
    # show counterparties whose median trade count per day is small
    cp_sym_dist = defaultdict(list)
    for (cp, sym, _), n in by_cp_sym_day.items():
        cp_sym_dist[(cp, sym)].append(n)
    for (cp, sym), counts in sorted(cp_sym_dist.items()):
        if max(counts) <= 5 and len(counts) >= 2:
            print(f"{cp:<10} {sym:<28} per-day trade counts={counts}")


if __name__ == "__main__":
    main()
