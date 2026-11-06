"""
Grid search for v4 parameters.
Uses days 0+1 as TRAIN, day 2 as TEST (held out).
Sweeps HYDROGEL make_offset, soft_limit, trend_drift.
Then tests VELVETFRUIT with various soft_limits.
"""
import sys, os, re, shutil, subprocess
from pathlib import Path
from itertools import product

ROOT = Path(__file__).resolve().parent.parent
BASELINE = ROOT / "trader_r3_v3.py"
SCRIPTS  = ROOT / "scripts"

# ---------- backtester runner ----------

def run_bt(script: Path, days: list[int]) -> dict[str, float]:
    """Run per-day backtests via run_r3_backtest.py subprocess."""
    results = {}
    for d in days:
        cmd = [
            sys.executable,
            str(SCRIPTS / "run_r3_backtest.py"),
            str(script),
            str(d),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT))
        out = res.stdout + res.stderr
        # "Total profit: 6,629" line
        m = re.search(r"Total profit: ([\-\d,]+)", out)
        if m:
            results[d] = float(m.group(1).replace(",",""))
        else:
            results[d] = 0.0
    results["total"] = sum(results[d] for d in days)
    return results


def patch_param(src: str, name: str, value) -> str:
    """Replace `NAME = <value>` line in source."""
    pattern = rf"^({re.escape(name)}\s*=\s*)(.+)$"
    new_line = f"{name} = {value}"
    result, n = re.subn(pattern, new_line, src, flags=re.MULTILINE)
    if n == 0:
        raise ValueError(f"Parameter {name} not found in source")
    return result


def make_temp(params: dict) -> Path:
    src = BASELINE.read_text(encoding="utf-8")
    for name, value in params.items():
        src = patch_param(src, name, value)
    tmp = ROOT / "_grid_tmp.py"
    tmp.write_text(src, encoding="utf-8")
    return tmp


# ======================================================================
# SWEEP 1: HYDROGEL make_offset (train on day 0+1)
# ======================================================================
print("=" * 60)
print("SWEEP 1: HYDROGEL_MAKE_OFFSET  (train days 0+1)")
print("=" * 60)
print(f"{'offset':>8}  {'d0':>8}  {'d1':>8}  {'train':>8}  {'d2(test)':>10}")
best_offset_row = None
best_offset_score = -1e9

for offset in [1, 2, 3, 4, 5, 6, 7]:
    tmp = make_temp({"HYDROGEL_MAKE_OFFSET": offset})
    r = run_bt(tmp, [0, 1, 2])
    train = r.get(0, 0) + r.get(1, 0)
    test  = r.get(2, 0)
    total = r.get("total", train + test)
    print(f"{offset:>8}  {r.get(0,0):>8,.0f}  {r.get(1,0):>8,.0f}  {train:>8,.0f}  {test:>10,.0f}")
    if train > best_offset_score:
        best_offset_score = train
        best_offset_row = (offset, r)

best_offset = best_offset_row[0]
print(f"\n→ Best train: make_offset={best_offset}\n")

# ======================================================================
# SWEEP 2: HYDROGEL_SOFT_LIMIT (with best offset)
# ======================================================================
print("=" * 60)
print(f"SWEEP 2: HYDROGEL_SOFT_LIMIT  (make_offset={best_offset}, train days 0+1)")
print("=" * 60)
print(f"{'sl':>8}  {'d0':>8}  {'d1':>8}  {'train':>8}  {'d2(test)':>10}")
best_sl_row = None
best_sl_score = -1e9

for sl in [25, 40, 50, 75, 100, 150]:
    tmp = make_temp({"HYDROGEL_MAKE_OFFSET": best_offset, "HYDROGEL_SOFT_LIMIT": sl})
    r = run_bt(tmp, [0, 1, 2])
    train = r.get(0, 0) + r.get(1, 0)
    test  = r.get(2, 0)
    print(f"{sl:>8}  {r.get(0,0):>8,.0f}  {r.get(1,0):>8,.0f}  {train:>8,.0f}  {test:>10,.0f}")
    if train > best_sl_score:
        best_sl_score = train
        best_sl_row = (sl, r)

best_sl = best_sl_row[0]
print(f"\n→ Best train: soft_limit={best_sl}\n")

# ======================================================================
# SWEEP 3: HYDROGEL_TREND_DRIFT
# ======================================================================
print("=" * 60)
print(f"SWEEP 3: HYDROGEL_TREND_DRIFT  (offset={best_offset}, sl={best_sl})")
print("=" * 60)
print(f"{'drift':>8}  {'d0':>8}  {'d1':>8}  {'train':>8}  {'d2(test)':>10}")
best_drift_row = None
best_drift_score = -1e9

for drift in [10, 15, 20, 30, 40, 60]:
    tmp = make_temp({
        "HYDROGEL_MAKE_OFFSET": best_offset,
        "HYDROGEL_SOFT_LIMIT": best_sl,
        "HYDROGEL_TREND_DRIFT": drift,
    })
    r = run_bt(tmp, [0, 1, 2])
    train = r.get(0, 0) + r.get(1, 0)
    test  = r.get(2, 0)
    print(f"{drift:>8}  {r.get(0,0):>8,.0f}  {r.get(1,0):>8,.0f}  {train:>8,.0f}  {test:>10,.0f}")
    if train > best_drift_score:
        best_drift_score = train
        best_drift_row = (drift, r)

best_drift = best_drift_row[0]
print(f"\n→ Best train: trend_drift={best_drift}\n")

# ======================================================================
# SWEEP 4: VELVETFRUIT soft_limit activation
# ======================================================================
print("=" * 60)
print(f"SWEEP 4: VELVETFRUIT reactivation  (VELVET_SOFT_LIMIT sweep)")
print("=" * 60)
print(f"{'velvet_sl':>10}  {'d0':>8}  {'d1':>8}  {'train':>8}  {'d2(test)':>10}")

# To test velvet, we need a version where VelvetStrategy is re-enabled.
# We patch the VELVET_SOFT_LIMIT AND the VelvetStrategy.act() stub.
# The patch: replace `return []` in VelvetStrategy with actual logic.
# Simplest: we'll use a separate src block.

BASE_SRC = BASELINE.read_text(encoding="utf-8")

VELVET_STUB = '''    def act(self, state: TradingState, ctx: dict) -> List[Order]:
        return []'''

def make_velvet_act(soft_limit: int, make_offset: int = 1, take_edge: int = 2,
                    ema_alpha_num: int = 2, ema_alpha_den: int = 20,
                    anchor: int = 5250) -> str:
    return f'''    def act(self, state: TradingState, ctx: dict) -> List[Order]:
        od = self.order_depth(state)
        if not od or not od.buy_orders or not od.sell_orders:
            return []
        position = self.position(state)
        orders: List[Order] = []
        flat_only = ctx.get("flat_only", False)

        bb = max(od.buy_orders.keys())
        ba = min(od.sell_orders.keys())
        mid = (bb + ba) / 2.0

        alpha = {ema_alpha_num} / {ema_alpha_den}
        if self.ema_fair is None:
            self.ema_fair = mid
        else:
            self.ema_fair = alpha * mid + (1 - alpha) * self.ema_fair

        # Blend: 60% EMA + 40% anchor (anchor is 3-day mean 5250)
        fair = 0.6 * self.ema_fair + 0.4 * {anchor}
        fair_i = round(fair)

        sl = {soft_limit}

        # -- TAKE (only when significant mispricing) --
        for ap in sorted(od.sell_orders.keys()):
            vol = abs(od.sell_orders[ap])
            if ap <= fair_i - {take_edge}:
                cap = sl - position
                qty = min(vol, max(0, cap))
                if qty > 0 and not flat_only:
                    orders.append(Order(self.symbol, ap, qty))
                    position += qty
        for bp in sorted(od.buy_orders.keys(), reverse=True):
            vol = od.buy_orders[bp]
            if bp >= fair_i + {take_edge}:
                cap = sl + position
                qty = min(vol, max(0, cap))
                if qty > 0 and not flat_only:
                    orders.append(Order(self.symbol, bp, -qty))
                    position -= qty

        if flat_only:
            return orders

        # -- MAKE: 1 tick inside bot spread, capped at soft_limit --
        my_bid = bb + {make_offset}
        my_ask = ba - {make_offset}
        if my_bid >= my_ask:
            my_bid = fair_i - 1
            my_ask = fair_i + 1
        my_bid = min(my_bid, fair_i - 1)
        my_ask = max(my_ask, fair_i + 1)

        q_buy  = max(0, sl - position)
        q_sell = max(0, sl + position)

        # Inventory-skewed sizing: reduce size on the side we're already heavy
        if position > sl // 2:
            q_buy = q_buy // 2
        elif position < -(sl // 2):
            q_sell = q_sell // 2

        if q_buy  > 0: orders.append(Order(self.symbol, my_bid,  q_buy))
        if q_sell > 0: orders.append(Order(self.symbol, my_ask, -q_sell))
        return orders'''

best_velvet_score = -1e9
best_velvet_sl = 0

for vsl in [0, 30, 50, 80, 120]:
    src = BASE_SRC
    # Patch hydrogel params to best found
    src = patch_param(src, "HYDROGEL_MAKE_OFFSET", best_offset)
    src = patch_param(src, "HYDROGEL_SOFT_LIMIT", best_sl)
    src = patch_param(src, "HYDROGEL_TREND_DRIFT", best_drift)
    # Inject velvet strategy
    if vsl > 0:
        new_act = make_velvet_act(soft_limit=vsl)
        src = src.replace(VELVET_STUB, new_act, 1)

    tmp = ROOT / "_grid_tmp.py"
    tmp.write_text(src, encoding="utf-8")
    r = run_bt(tmp, [0, 1, 2])
    train = r.get(0, 0) + r.get(1, 0)
    test  = r.get(2, 0)
    label = f"vsl={vsl}" if vsl > 0 else "disabled"
    print(f"{label:>10}  {r.get(0,0):>8,.0f}  {r.get(1,0):>8,.0f}  {train:>8,.0f}  {test:>10,.0f}")
    if train > best_velvet_score:
        best_velvet_score = train
        best_velvet_sl = vsl

print(f"\n→ Best velvet soft_limit={best_velvet_sl}\n")

# ======================================================================
# SWEEP 5: Voucher edge_ticks and take_margin
# ======================================================================
print("=" * 60)
print("SWEEP 5: VOUCHER_EDGE_TICKS + VEV_5300 inclusion")
print("=" * 60)
print(f"{'edge|5300':>12}  {'d0':>8}  {'d1':>8}  {'train':>8}  {'d2':>8}")

for edge_t, include_5300 in [(2, False), (1, False), (1, True), (2, True)]:
    src = BASE_SRC
    src = patch_param(src, "HYDROGEL_MAKE_OFFSET", best_offset)
    src = patch_param(src, "HYDROGEL_SOFT_LIMIT", best_sl)
    src = patch_param(src, "HYDROGEL_TREND_DRIFT", best_drift)
    src = patch_param(src, "VOUCHER_EDGE_TICKS", edge_t)
    if include_5300:
        src = src.replace(
            "LIVE_VOUCHER_STRIKES   = [5400, 5500]",
            "LIVE_VOUCHER_STRIKES   = [5300, 5400, 5500]"
        )
    if best_velvet_sl > 0:
        new_act = make_velvet_act(soft_limit=best_velvet_sl)
        src = src.replace(VELVET_STUB, new_act, 1)

    tmp = ROOT / "_grid_tmp.py"
    tmp.write_text(src, encoding="utf-8")
    r = run_bt(tmp, [0, 1, 2])
    train = r.get(0, 0) + r.get(1, 0)
    test  = r.get(2, 0)
    label = f"e{edge_t}+5300" if include_5300 else f"e{edge_t}"
    print(f"{label:>12}  {r.get(0,0):>8,.0f}  {r.get(1,0):>8,.0f}  {train:>8,.0f}  {test:>8,.0f}")

# ======================================================================
# SUMMARY: Print best combined config
# ======================================================================
print("\n" + "=" * 60)
print("SUMMARY — recommended v4 parameters")
print("=" * 60)
print(f"HYDROGEL_MAKE_OFFSET  = {best_offset}  (was 3)")
print(f"HYDROGEL_SOFT_LIMIT   = {best_sl}  (was 50)")
print(f"HYDROGEL_TREND_DRIFT  = {best_drift}  (was 20)")
print(f"VELVETFRUIT soft_limit= {best_velvet_sl}  (was 0/disabled)")

# Clean up
(ROOT / "_grid_tmp.py").unlink(missing_ok=True)
print("\nDone.")
