"""Grid search for optimal parameters on R2 data."""
import subprocess, re, sys, os

SUBMISSION = r".\submission.py"
TEMPLATE = r".\logs\277766\277766.py"

# Read the original template
with open(TEMPLATE, "r", encoding="utf-8") as f:
    original = f.read()

def run_backtest(params):
    """Apply params to submission.py and run backtester."""
    code = original
    
    # Apply parameter overrides
    if "aco_soft" in params:
        code = code.replace(
            'ACOStrategy("ASH_COATED_OSMIUM", position_limit=80, soft_limit=70)',
            f'ACOStrategy("ASH_COATED_OSMIUM", position_limit=80, soft_limit={params["aco_soft"]})'
        )
    if "ipr_soft" in params:
        code = code.replace(
            'IPRStrategy("INTARIAN_PEPPER_ROOT", position_limit=80, soft_limit=50)',
            f'IPRStrategy("INTARIAN_PEPPER_ROOT", position_limit=80, soft_limit={params["ipr_soft"]})'
        )
    if "aco_ema" in params:
        code = code.replace(
            'EMA_ALPHA = 2.0 / 16  # window ≈ 15, slow to reduce noise',
            f'EMA_ALPHA = 2.0 / {params["aco_ema"]}'
        )
    if "ipr_ema" in params:
        code = code.replace(
            'EMA_ALPHA = 2.0 / 6  # window = 5',
            f'EMA_ALPHA = 2.0 / {params["ipr_ema"]}'
        )
    if "aco_imb" in params:
        code = code.replace(
            'fair = round(self.ema_fair + imb * 0.7)',
            f'fair = round(self.ema_fair + imb * {params["aco_imb"]})'
        )
    if "ipr_imb" in params:
        code = code.replace(
            'fair = round(self.ema_fair + imb * 0.9 - inv_skew)',
            f'fair = round(self.ema_fair + imb * {params["ipr_imb"]} - inv_skew)'
        )
    if "ipr_skew" in params:
        code = code.replace(
            'inv_skew = 0.1 * position',
            f'inv_skew = {params["ipr_skew"]} * position'
        )
    
    with open(SUBMISSION, "w", encoding="utf-8") as f:
        f.write(code)
    
    try:
        result = subprocess.run(
            ["prosperity4btx", SUBMISSION, "2", "--print"],
            capture_output=True, text=True, timeout=120,
            cwd=r"."
        )
        output = result.stdout + result.stderr
        # Find total profit line
        matches = re.findall(r"Total profit:\s*([\d,.]+)", output)
        if matches:
            return float(matches[-1].replace(",", ""))
        # Try to find individual day profits
        day_profits = re.findall(r"Profit.*?:\s*([\d,.]+)", output)
        if day_profits:
            return sum(float(x.replace(",", "")) for x in day_profits[-3:])
        return None
    except Exception as e:
        return None

# Baseline
print("=" * 60)
print("PARAMETER GRID SEARCH - R2")
print("=" * 60)

# Test configurations
configs = [
    ("baseline", {}),
    ("aco_soft=75", {"aco_soft": 75}),
    ("aco_soft=78", {"aco_soft": 78}),
    ("ipr_soft=60", {"ipr_soft": 60}),
    ("ipr_soft=65", {"ipr_soft": 65}),
    ("ipr_soft=70", {"ipr_soft": 70}),
    ("aco_ema=12", {"aco_ema": 12}),
    ("aco_ema=20", {"aco_ema": 20}),
    ("ipr_ema=4", {"ipr_ema": 4}),
    ("ipr_ema=8", {"ipr_ema": 8}),
    ("aco_imb=0.5", {"aco_imb": 0.5}),
    ("aco_imb=1.0", {"aco_imb": 1.0}),
    ("ipr_imb=0.5", {"ipr_imb": 0.5}),
    ("ipr_imb=1.2", {"ipr_imb": 1.2}),
    ("ipr_skew=0.05", {"ipr_skew": 0.05}),
    ("ipr_skew=0.15", {"ipr_skew": 0.15}),
    ("ipr_skew=0.2", {"ipr_skew": 0.2}),
]

results = []
for name, params in configs:
    pnl = run_backtest(params)
    results.append((name, pnl))
    print(f"  {name:25s} → {pnl:>12,.0f}" if pnl else f"  {name:25s} → FAILED")

# Restore original
with open(SUBMISSION, "w", encoding="utf-8") as f:
    f.write(original)

print("\n" + "=" * 60)
print("SORTED RESULTS")
print("=" * 60)
for name, pnl in sorted(results, key=lambda x: x[1] or 0, reverse=True):
    if pnl:
        diff = pnl - (results[0][1] or 0)
        print(f"  {name:25s} → {pnl:>12,.0f}  ({'+' if diff >= 0 else ''}{diff:,.0f})")
