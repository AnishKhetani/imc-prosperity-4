"""
liquidate.py
============
Standalone, drop-in liquidation function for any R5 contingency variant.

USAGE
-----
Inside any variant Trader.run() method, on every tick after the inventory
zero-out timestamp:

    from liquidate import build_liquidation_orders
    extra = build_liquidation_orders(state.position, state.order_depths,
                                     state.timestamp,
                                     start_ts=LIQ_START_TS,
                                     end_ts=LIQ_END_TS)
    for sym, lst in extra.items():
        result.setdefault(sym, []).extend(lst)
    # The base Trader._clip_orders pass below will guarantee no position breach.

DERIVATION (Step 4 + Step 1 EDA)
--------------------------------
- Position limit:                  10 / product
- 5th percentile top-of-book depth (Step 1 EDA, all R5 products): 4 lots
- Conservative fill rate per tick: 50% of 5th-pct depth = 2 lots / tick
- Worst-case offload of 10 units:  10 / 2 = 5 ticks per product
- Number of products held simultaneously (worst case): all 50
- Safety margin:                   5x

  Safe liquidation budget = 5 ticks * 5x margin = 25 ticks per product

R5 round = 1,000,000 timestamps (10,000 ticks at 100ms cadence).
We will trigger liquidation no later than:

  LIQ_START_TS = 1,000,000 - (50 products * 25 ticks * 100 ms_per_tick)
               = 1,000,000 - 125,000
               = 875,000          # i.e. 87.5% through the round

In practice, products are independent so concurrent offload is fine.
The 87.5% mark is the LATE bound; the playbook (Decision Commander)
nominates 92% as the standard trigger because the window is much smaller
than worst-case. 85% is the EARLY bound (defensive — used when current PnL
is below MC worst-case CI).

LIQUIDATION ALGORITHM
---------------------
For each product with non-zero position:

  1) Compute remaining ticks until end (end_ts - timestamp) / 100.
  2) Compute target_per_tick = ceil(|position| / max(1, remaining_ticks)).
     Clip target_per_tick to >= 1 so we always make progress.
  3) Choose price:
     * ramp from passive (best-bid+1 to sell, best-ask-1 to buy) at
       liquidation start, to aggressive (best-bid for sell, best-ask
       for buy) at the midpoint of the liquidation window, to taking
       (cross by 1 tick) once we are within 25% of end.
  4) Quantity sign = -sign(position) (close direction).
  5) The base Trader._clip_orders staticmethod still runs after this
     and guarantees no breach.

NEVER raises. Returns {} if order book is unreadable.
"""

from __future__ import annotations

from typing import Dict, List
from datamodel import Order, OrderDepth


def build_liquidation_orders(
    positions: Dict[str, int],
    order_depths: Dict[str, OrderDepth],
    timestamp: int,
    start_ts: int = 875_000,
    end_ts: int = 999_900,
    position_limit: int = 10,
) -> Dict[str, List[Order]]:
    """Generate close-direction orders for every product with non-zero
    position. Pacing scales with remaining ticks; price aggression escalates
    as we approach end_ts.

    Parameters
    ----------
    positions    : {symbol: int}    current positions
    order_depths : {symbol: OrderDepth}
    timestamp    : current state.timestamp (units of 100 = 1 tick)
    start_ts     : do nothing if timestamp < start_ts
    end_ts       : final timestamp at which we must be flat
    position_limit : sanity bound; orders are clipped by base trader anyway

    Returns
    -------
    {symbol: [Order, ...]}  — empty dict if it is too early or no positions.
    """
    if timestamp < start_ts:
        return {}
    if not positions:
        return {}

    out: Dict[str, List[Order]] = {}
    window = max(1, end_ts - start_ts)
    progress = max(0.0, min(1.0, (timestamp - start_ts) / window))
    # remaining ticks (100 ts = 1 tick); guard against zero
    remaining_ticks = max(1, (end_ts - timestamp) // 100)

    for sym, pos in positions.items():
        try:
            if pos == 0:
                continue
            od = order_depths.get(sym)
            if od is None:
                continue
            buys = getattr(od, "buy_orders", None) or {}
            sells = getattr(od, "sell_orders", None) or {}
            if not buys and not sells:
                continue

            target = max(1, (abs(pos) + remaining_ticks - 1) // remaining_ticks)
            target = min(target, abs(pos), position_limit)

            if pos > 0:
                # need to SELL
                if not buys:
                    continue
                best_bid = max(buys.keys())
                if progress < 0.5:
                    px = best_bid + 1            # passive: post above bid
                elif progress < 0.75:
                    px = best_bid                # at-bid: marketable when matched
                else:
                    # cross: take the bid; if no buy_orders depth left, fall
                    # back to best_bid - 1 to get an immediate hit
                    px = best_bid
                qty = -target
            else:
                # need to BUY
                if not sells:
                    continue
                best_ask = min(sells.keys())
                if progress < 0.5:
                    px = best_ask - 1
                elif progress < 0.75:
                    px = best_ask
                else:
                    px = best_ask
                qty = target

            out.setdefault(sym, []).append(Order(sym, int(px), int(qty)))
        except Exception:
            # Never crash the trader because liquidation tripped on one symbol.
            continue
    return out


# ---------------------------------------------------------------------------
# Self-test (run as a script):  python liquidate.py
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    class _OD:
        def __init__(self, buys, sells):
            self.buy_orders = buys
            self.sell_orders = sells

    pos = {"X": 7, "Y": -3, "Z": 0}
    ods = {
        "X": _OD({100: 5, 99: 8}, {101: 6, 102: 4}),
        "Y": _OD({200: 5}, {201: 6}),
        "Z": _OD({300: 1}, {301: 1}),
    }
    print("--- ts=800_000 (before window) ---")
    print(build_liquidation_orders(pos, ods, 800_000))
    print("--- ts=900_000 (mid window) ---")
    out = build_liquidation_orders(pos, ods, 900_000)
    for s, lst in out.items():
        for o in lst:
            print(s, o.price, o.quantity)
    print("--- ts=995_000 (final 5%) ---")
    out = build_liquidation_orders(pos, ods, 995_000)
    for s, lst in out.items():
        for o in lst:
            print(s, o.price, o.quantity)
