"""Creates v4 test variant files for the parameter grid search."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
src = (ROOT / "trader_r3_v3.py").read_text(encoding="utf-8")


def patch(s: str, name: str, val) -> str:
    result, n = re.subn(
        rf"^({re.escape(name)}\s*=\s*).+$", f"{name} = {val}", s, flags=re.MULTILINE
    )
    if n == 0:
        raise ValueError(f"{name} not found")
    return result


VELVET_STUB = """    def act(self, state: TradingState, ctx: dict) -> List[Order]:
        return []"""

VELVET_FULL = """    def act(self, state: TradingState, ctx: dict) -> List[Order]:
        od = self.order_depth(state)
        if not od or not od.buy_orders or not od.sell_orders:
            return []
        position = self.position(state)
        orders: List[Order] = []
        flat_only = ctx.get("flat_only", False)
        bb = max(od.buy_orders.keys())
        ba = min(od.sell_orders.keys())
        mid = (bb + ba) / 2.0
        alpha = 2.0 / 20.0
        ema = getattr(self, "_v_ema", None)
        if ema is None:
            ema = mid
        else:
            ema = alpha * mid + (1.0 - alpha) * ema
        self._v_ema = ema
        # 60% adaptive EMA + 40% long-run anchor
        fair = 0.6 * ema + 0.4 * 5250.0
        fair_i = round(fair)
        sl = VELVET_SOFT_LIMIT
        # TAKE: 2-tick edge
        for ap in sorted(od.sell_orders.keys()):
            vol = abs(od.sell_orders[ap])
            if ap <= fair_i - 2:
                qty = min(vol, max(0, sl - position))
                if qty > 0 and not flat_only:
                    orders.append(Order(self.symbol, ap, qty))
                    position += qty
        for bp in sorted(od.buy_orders.keys(), reverse=True):
            vol = od.buy_orders[bp]
            if bp >= fair_i + 2:
                qty = min(vol, max(0, sl + position))
                if qty > 0 and not flat_only:
                    orders.append(Order(self.symbol, bp, -qty))
                    position -= qty
        if flat_only:
            return orders
        # MAKE: 1 tick inside best bid/ask, clamped to fair±1 minimum
        my_bid = min(bb + 1, fair_i - 1)
        my_ask = max(ba - 1, fair_i + 1)
        if my_bid >= my_ask:
            my_bid, my_ask = fair_i - 1, fair_i + 1
        q_buy  = max(0, sl - position)
        q_sell = max(0, sl + position)
        # Inventory-skew: halve size on the already-heavy side
        if position > sl // 2:
            q_buy = q_buy // 2
        elif position < -(sl // 2):
            q_sell = q_sell // 2
        if q_buy  > 0:
            orders.append(Order(self.symbol, my_bid,  q_buy))
        if q_sell > 0:
            orders.append(Order(self.symbol, my_ask, -q_sell))
        return orders"""


# ── verify stub can be found ──────────────────────────────────────────────
if VELVET_STUB not in src:
    raise RuntimeError("VELVET_STUB not found in source - check whitespace/indentation")

# _t7: sl=150 + offset=5
s7 = patch(patch(src, "HYDROGEL_MAKE_OFFSET", 5), "HYDROGEL_SOFT_LIMIT", 150)
(ROOT / "_t7.py").write_text(s7, encoding="utf-8")
print("_t7: sl=150 + offset=5")

# _t8: sl=150 + offset=5 + velvet enabled (sl=60)
s8 = patch(patch(src, "HYDROGEL_MAKE_OFFSET", 5), "HYDROGEL_SOFT_LIMIT", 150)
s8 = s8.replace(VELVET_STUB, VELVET_FULL, 1)
(ROOT / "_t8.py").write_text(s8, encoding="utf-8")
print("_t8: sl=150 + offset=5 + velvet sl=60")

# _t9: sl=150 + offset=5 + edge_ticks=1 + VEV_5300 added
s9 = patch(patch(patch(src, "HYDROGEL_MAKE_OFFSET", 5), "HYDROGEL_SOFT_LIMIT", 150),
           "VOUCHER_EDGE_TICKS", 1)
s9 = s9.replace(
    "LIVE_VOUCHER_STRIKES   = [5400, 5500]",
    "LIVE_VOUCHER_STRIKES   = [5300, 5400, 5500]"
)
(ROOT / "_t9.py").write_text(s9, encoding="utf-8")
print("_t9: sl=150 + offset=5 + edge=1 + VEV_5300")

# _t10: sl=150 + offset=5 + velvet + edge=1 + VEV_5300 (full kitchen sink)
s10 = s8.replace(
    "LIVE_VOUCHER_STRIKES   = [5400, 5500]",
    "LIVE_VOUCHER_STRIKES   = [5300, 5400, 5500]"
)
s10 = patch(s10, "VOUCHER_EDGE_TICKS", 1)
(ROOT / "_t10.py").write_text(s10, encoding="utf-8")
print("_t10: sl=150 + offset=5 + velvet + edge=1 + VEV_5300 (kitchen sink)")

print("All files created.")
