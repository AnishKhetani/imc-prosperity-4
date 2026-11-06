"""
Generate variants with different position fade values to test on platform.
Each variant is a complete submission.py with only POS_FADE changed.
Also test a mean-reversion beta variant.
"""
import os

BASE = r'.\submission.py'
OUT = r'.\variants'

with open(BASE, encoding='utf-8') as f:
    baseline = f.read()

# === Variant 1: POS_FADE = 0 (no position adjustment to fair) ===
def make_fade_variant(code, fade_val):
    return code.replace(
        "adjusted_fair = self.ema + imb * self.IMB_WEIGHT - position * 0.05",
        f"adjusted_fair = self.ema + imb * self.IMB_WEIGHT - position * {fade_val}"
    )

# === Variant 2: Mean-reversion beta ===
# Add: fair shifts opposite to (mid - ema), anticipating reversion
def make_meanrev_variant(code, beta):
    old = "        adjusted_fair = self.ema + imb * self.IMB_WEIGHT - position * 0.05\n        fair = round(adjusted_fair)"
    new = f"""        # Mean-reversion: shift fair opposite to deviation from EMA
        deviation = mid - self.ema
        adjusted_fair = self.ema + imb * self.IMB_WEIGHT - position * 0.05 - deviation * {beta}
        fair = round(adjusted_fair)"""
    return code.replace(old, new, 1)

# === Variant 3: No skew/asymmetric sizing (pure symmetric) ===
def make_nosizing_variant(code):
    # Remove asymmetric sizing — just use full remaining capacity
    old = """        pos_ratio = position / self.position_limit
        remaining_buy = self.max_buy_qty(position)
        remaining_sell = self.max_sell_qty(position)
        buy_qty, sell_qty = self._asymmetric_size(remaining_buy, remaining_sell, pos_ratio)"""
    new = """        remaining_buy = self.max_buy_qty(position)
        remaining_sell = self.max_sell_qty(position)
        buy_qty, sell_qty = remaining_buy, remaining_sell"""
    return code.replace(old, new, 1)

variants = {
    'v_fade0': lambda c: make_fade_variant(c, 0),
    'v_fade01': lambda c: make_fade_variant(c, 0.1),
    'v_fade02': lambda c: make_fade_variant(c, 0.02),
    'v_meanrev03': lambda c: make_meanrev_variant(c, 0.3),
    'v_meanrev05': lambda c: make_meanrev_variant(c, 0.5),
    'v_nosizing': make_nosizing_variant,
}

os.makedirs(OUT, exist_ok=True)
for name, transform in variants.items():
    code = transform(baseline)
    path = os.path.join(OUT, f'{name}.py')
    with open(path, 'w', encoding='utf-8') as f:
        f.write(code)
    print(f'Created {name}.py')

print('\nAll variants generated.')
print('Recommended test order:')
print('  1. v_fade0.py    — tests if position fade helps at all')
print('  2. v_meanrev03.py — mild mean-reversion (low overfit risk)')  
print('  3. v_nosizing.py  — removes asymmetric sizing (barely triggers)')
