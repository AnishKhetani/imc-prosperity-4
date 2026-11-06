"""Generate all 7 variant strategy files from submission.py baseline."""
import os

BASE = r'.\submission.py'
OUT = r'.\variants'

with open(BASE, encoding='utf-8') as f:
    baseline = f.read()

# === CHANGE 1: TOMATOES position bias fix ===
# - SKEW_THRESHOLD 0.3 -> 0.15 (in TomatoesStrategy only)
# - Add fair value position adjustment: fair -= position * 0.05

def apply_change1(code):
    # Change TomatoesStrategy SKEW_THRESHOLD (but NOT EmeraldsStrategy's)
    # Find the TomatoesStrategy class section and replace its SKEW_THRESHOLD
    marker = "class TomatoesStrategy(Strategy):"
    idx = code.index(marker)
    # Find the SKEW_THRESHOLD after TomatoesStrategy class definition
    skew_idx = code.index("    SKEW_THRESHOLD = 0.3", idx)
    code = code[:skew_idx] + "    SKEW_THRESHOLD = 0.15" + code[skew_idx + len("    SKEW_THRESHOLD = 0.3"):]
    
    # Add position adjustment to fair value calculation
    old = "        adjusted_fair = self.ema + imb * self.IMB_WEIGHT\n        fair = round(adjusted_fair)"
    new = "        adjusted_fair = self.ema + imb * self.IMB_WEIGHT - position * 0.05\n        fair = round(adjusted_fair)"
    code = code.replace(old, new, 1)
    return code

# === CHANGE 2: EMERALDS spread compression ===
# When spread < 12, dynamically tighten width

def apply_change2(code):
    old = """        # Phase 2: Wide makes at fair ± MAKE_WIDTH (9993/10007)
        bid_price = self.FAIR_VALUE - self.MAKE_WIDTH
        ask_price = self.FAIR_VALUE + self.MAKE_WIDTH"""
    new = """        # Phase 2: Wide makes at fair ± MAKE_WIDTH (9993/10007)
        observed_spread = self.spread(state)
        if observed_spread is not None and observed_spread < 12:
            width = max(1, observed_spread // 2 - 1)
        else:
            width = self.MAKE_WIDTH
        bid_price = self.FAIR_VALUE - width
        ask_price = self.FAIR_VALUE + width"""
    code = code.replace(old, new, 1)
    return code

# === CHANGE 3: TOMATOES two-level quoting ===
# Replace single-level make with two levels: ±4 (60%) and ±7 (40%)

def apply_change3(code):
    old = """        # Phase 2: Single-level make
        bid_price, ask_price = self._make_prices(fair, position, depth_imb)

        pos_ratio = position / self.position_limit
        remaining_buy = self.max_buy_qty(position)
        remaining_sell = self.max_sell_qty(position)
        buy_qty, sell_qty = self._asymmetric_size(remaining_buy, remaining_sell, pos_ratio)

        buy_order = self.buy(bid_price, buy_qty, position) if buy_qty > 0 else None
        if buy_order:
            orders.append(buy_order)

        sell_order = self.sell(ask_price, sell_qty, position) if sell_qty > 0 else None
        if sell_order:
            orders.append(sell_order)"""
    new = """        # Phase 2: Two-level make (±4 primary 60%, ±7 secondary 40%)
        bid_price, ask_price = self._make_prices(fair, position, depth_imb)
        bid_price2 = bid_price - 3  # ±7 from fair (outer level)
        ask_price2 = ask_price + 3

        pos_ratio = position / self.position_limit
        remaining_buy = self.max_buy_qty(position)
        remaining_sell = self.max_sell_qty(position)
        buy_qty, sell_qty = self._asymmetric_size(remaining_buy, remaining_sell, pos_ratio)

        # Split: 60% at tight level, 40% at wide level
        buy_qty1 = max(1, int(buy_qty * 0.6))
        buy_qty2 = buy_qty - buy_qty1
        sell_qty1 = max(1, int(sell_qty * 0.6))
        sell_qty2 = sell_qty - sell_qty1

        buy_order = self.buy(bid_price, buy_qty1, position) if buy_qty1 > 0 else None
        if buy_order:
            orders.append(buy_order)
            position += buy_order.quantity

        buy_order2 = self.buy(bid_price2, buy_qty2, position) if buy_qty2 > 0 else None
        if buy_order2:
            orders.append(buy_order2)
            position += buy_order2.quantity

        sell_order = self.sell(ask_price, sell_qty1, position) if sell_qty1 > 0 else None
        if sell_order:
            orders.append(sell_order)
            position += sell_order.quantity

        sell_order2 = self.sell(ask_price2, sell_qty2, position) if sell_qty2 > 0 else None
        if sell_order2:
            orders.append(sell_order2)"""
    
    # Also change MAKE_WIDTH from 5 to 4 for the primary level
    old_width = "    MAKE_WIDTH = 5"
    # We need to only change the TomatoesStrategy one
    marker = "class TomatoesStrategy(Strategy):"
    idx = code.index(marker)
    width_idx = code.index(old_width, idx)
    code_before = code[:width_idx]
    code_after = code[width_idx + len(old_width):]
    code = code_before + "    MAKE_WIDTH = 4" + code_after
    
    code = code.replace(old, new, 1)
    return code

# Generate all combinations
combos = {
    'v1_posbias': [apply_change1],
    'v2_spreadcomp': [apply_change2],
    'v3_twolevel': [apply_change3],
    'v12_posbias_spreadcomp': [apply_change1, apply_change2],
    'v13_posbias_twolevel': [apply_change1, apply_change3],
    'v23_spreadcomp_twolevel': [apply_change2, apply_change3],
    'v123_all': [apply_change1, apply_change2, apply_change3],
}

for name, transforms in combos.items():
    code = baseline
    for t in transforms:
        code = t(code)
    path = os.path.join(OUT, f'{name}.py')
    with open(path, 'w', encoding='utf-8') as f:
        f.write(code)
    print(f'Created {name}.py')

print('\nAll variants generated.')
