"""Sweep soft_limit and inv_skew for R2 optimization."""
import subprocess
import re

# We'll modify submission.py via string replacement and run backtests
SUBMISSION = "submission.py"

def run_backtest(soft_limit_aco, soft_limit_ipr):
    """Modify submission.py and run backtest."""
    with open(SUBMISSION, "r", encoding="utf-8") as f:
        code = f.read()
    
    # Replace strategy instantiation
    old_line = f'            ACOStrategy("ASH_COATED_OSMIUM", position_limit=80, soft_limit={50}),'
    new_line = f'            ACOStrategy("ASH_COATED_OSMIUM", position_limit=80, soft_limit={soft_limit_aco}),'
    
    # Need to be more flexible with matching
    code_mod = re.sub(
        r'ACOStrategy\("ASH_COATED_OSMIUM", position_limit=80, soft_limit=\d+\)',
        f'ACOStrategy("ASH_COATED_OSMIUM", position_limit=80, soft_limit={soft_limit_aco})',
        code
    )
    code_mod = re.sub(
        r'IPRStrategy\("INTARIAN_PEPPER_ROOT", position_limit=80, soft_limit=\d+\)',
        f'IPRStrategy("INTARIAN_PEPPER_ROOT", position_limit=80, soft_limit={soft_limit_ipr})',
        code_mod
    )
    
    with open(SUBMISSION, "w", encoding="utf-8") as f:
        f.write(code_mod)
    
    result = subprocess.run(
        ["prosperity4btx", SUBMISSION, "2"],
        capture_output=True, text=True
    )
    
    # Parse output
    days = {}
    total = 0
    for line in result.stdout.split("\n"):
        m = re.search(r'Round 2 day (-?\d+): ([\d,]+)', line)
        if m:
            day = int(m.group(1))
            pnl = int(m.group(2).replace(",", ""))
            days[day] = pnl
        m = re.search(r'Total profit: ([\d,]+)', line)
        if m:
            total = int(m.group(1).replace(",", ""))
    
    # Get per-product from the individual day outputs
    aco_total = 0
    ipr_total = 0
    for line in result.stdout.split("\n"):
        m = re.search(r'ASH_COATED_OSMIUM: ([\d,-]+)', line)
        if m:
            aco_total += int(m.group(1).replace(",", ""))
        m = re.search(r'INTARIAN_PEPPER_ROOT: ([\d,-]+)', line)
        if m:
            ipr_total += int(m.group(1).replace(",", ""))
    
    return total, days, aco_total, ipr_total

print(f"{'SL_ACO':>6} {'SL_IPR':>6} | {'Day-1':>8} {'Day0':>8} {'Day1':>8} | {'ACO':>8} {'IPR':>8} | {'Total':>8}")
print("-" * 80)

best_total = 0
best_params = (50, 50)

for sl_aco in [40, 50, 60]:
    for sl_ipr in [35, 40, 45, 50, 55, 60]:
        total, days, aco, ipr = run_backtest(sl_aco, sl_ipr)
        d_m1 = days.get(-1, 0)
        d_0 = days.get(0, 0)
        d_1 = days.get(1, 0)
        print(f"{sl_aco:>6} {sl_ipr:>6} | {d_m1:>8} {d_0:>8} {d_1:>8} | {aco:>8} {ipr:>8} | {total:>8}")
        if total > best_total:
            best_total = total
            best_params = (sl_aco, sl_ipr)

print(f"\nBest: soft_limit_aco={best_params[0]}, soft_limit_ipr={best_params[1]}, total={best_total}")

# Restore best params
run_backtest(best_params[0], best_params[1])
print("Restored best params to submission.py")
