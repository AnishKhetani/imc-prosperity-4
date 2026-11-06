"""Robust experiment runner — tests one change at a time, no subprocess hang risk.
Uses file-based backtest output instead of capturing subprocess stdout/stderr.
"""
import subprocess, re, shutil, os, sys, time

WORKSPACE = r"."
SUBMISSION = os.path.join(WORKSPACE, "submission.py")
BACKUP = os.path.join(WORKSPACE, "_experiment_backup.py")

shutil.copy2(SUBMISSION, BACKUP)

def read_sub():
    with open(SUBMISSION, "r", encoding="utf-8") as f:
        return f.read()

def write_sub(code):
    with open(SUBMISSION, "w", encoding="utf-8") as f:
        f.write(code)

def backtest():
    """Run backtest, write output to temp file to avoid subprocess hang."""
    out_file = os.path.join(WORKSPACE, "_bt_output.txt")
    cmd = f'prosperity4btx submission.py 2 > "{out_file}" 2>&1'
    os.system(f'cd /d "{WORKSPACE}" && {cmd}')
    with open(out_file, "r", encoding="utf-8", errors="replace") as f:
        output = f.read()
    days = re.findall(r"Round 2 day [^:]+:\s*([\d,\-]+)", output)
    total_m = re.search(r"Total profit:\s*([\d,\-]+)", output)
    if total_m:
        total = int(total_m.group(1).replace(",", ""))
        dv = [int(d.replace(",", "")) for d in days]
        return total, dv
    return None, []

def test(name, code):
    write_sub(code)
    total, days = backtest()
    if total is not None:
        ds = "/".join(f"{d:>7,}" for d in days)
        delta = total - 91618
        sign = "+" if delta >= 0 else ""
        print(f"  {name:45s} {ds:>25s}  {total:>7,}  ({sign}{delta:,})")
    else:
        print(f"  {name:45s} {'FAILED':>25s}")
    return total

orig = read_sub()
print(f"  {'Experiment':45s} {'D-1  /  D0  /  D1':>25s}  {'Total':>7s}  {'Delta':>8s}")
print("  " + "-" * 95)

# Baseline
test("Baseline (91,618 expected)", orig)

# --- ACO experiments ---
# A1: ACO soft=55
c = orig.replace(
    'ACOStrategy("ASH_COATED_OSMIUM", position_limit=80, soft_limit=50)',
    'ACOStrategy("ASH_COATED_OSMIUM", position_limit=80, soft_limit=55)')
test("ACO soft=55", c)

# A2: ACO soft=60
c = orig.replace(
    'ACOStrategy("ASH_COATED_OSMIUM", position_limit=80, soft_limit=50)',
    'ACOStrategy("ASH_COATED_OSMIUM", position_limit=80, soft_limit=60)')
test("ACO soft=60", c)

# --- IPR experiments ---
# I1: IPR soft=45
c = orig.replace(
    'IPRStrategy("INTARIAN_PEPPER_ROOT", position_limit=80, soft_limit=50)',
    'IPRStrategy("INTARIAN_PEPPER_ROOT", position_limit=80, soft_limit=45)')
test("IPR soft=45", c)

# I2: IPR soft=55
c = orig.replace(
    'IPRStrategy("INTARIAN_PEPPER_ROOT", position_limit=80, soft_limit=50)',
    'IPRStrategy("INTARIAN_PEPPER_ROOT", position_limit=80, soft_limit=55)')
test("IPR soft=55", c)

# I3: IPR skew 0.05 (less inventory aversion → hold longer in drift)
c = orig.replace("inv_skew = 0.1 * position", "inv_skew = 0.05 * position")
test("IPR skew=0.05", c)

# I4: IPR skew 0.15
c = orig.replace("inv_skew = 0.1 * position", "inv_skew = 0.15 * position")
test("IPR skew=0.15", c)

# I5: IPR skew 0.0 (pure EMA+imb, no inventory penalty)
c = orig.replace("inv_skew = 0.1 * position", "inv_skew = 0.0 * position")
test("IPR skew=0.0", c)

# I6: IPR EMA alpha=0.5 (window=3)
c = orig.replace("EMA_ALPHA = 2.0 / 6", "EMA_ALPHA = 2.0 / 4")
test("IPR EMA w=3 (alpha=0.5)", c)

# I7: IPR EMA alpha=0.25 (window=7)
c = orig.replace("EMA_ALPHA = 2.0 / 6", "EMA_ALPHA = 2.0 / 8")
test("IPR EMA w=7 (alpha=0.25)", c)

# I8: IPR imbalance weight 0.3
c = orig.replace("imb * 0.5", "imb * 0.3")
test("IPR imb=0.3", c)

# I9: IPR imbalance weight 0.7
c = orig.replace("imb * 0.5", "imb * 0.7")
test("IPR imb=0.7", c)

# I10: IPR imbalance weight 1.0
c = orig.replace("imb * 0.5", "imb * 1.0")
test("IPR imb=1.0", c)

# --- Remove features ---
# R1: No depth contrarian
depth_block = """        # Depth contrarian: shift makes against full-book imbalance (mean-reversion)
        bid_depth = sum(od.buy_orders.values())
        ask_depth = sum(abs(v) for v in od.sell_orders.values())
        total_depth = bid_depth + ask_depth
        if total_depth > 0:
            depth_imb = (bid_depth - ask_depth) / total_depth
            if depth_imb > 0.1:
                ask_price -= 1
            elif depth_imb < -0.1:
                bid_price += 1"""
c = orig.replace(depth_block, "        pass  # depth contrarian removed")
test("No depth contrarian", c)

# R2: No asymmetric sizing
asym_block = """        pos_ratio = position / self.soft_limit

        if abs(pos_ratio) > 0.6:
            if position > 0:
                max_buy = max(1, max_buy // 2)
            else:
                max_sell = max(1, max_sell // 2)
        elif abs(pos_ratio) > 0.15:
            if position > 0:
                max_buy = max(1, int(max_buy * 0.7))
            else:
                max_sell = max(1, int(max_sell * 0.7))"""
c = orig.replace(asym_block, "        pass  # asymmetric sizing removed")
test("No asymmetric sizing", c)

# --- Combos of winners ---
# C1: ACO soft=55 + IPR skew=0.05
c = orig.replace(
    'ACOStrategy("ASH_COATED_OSMIUM", position_limit=80, soft_limit=50)',
    'ACOStrategy("ASH_COATED_OSMIUM", position_limit=80, soft_limit=55)')
c = c.replace("inv_skew = 0.1 * position", "inv_skew = 0.05 * position")
test("ACO s=55 + IPR skew=0.05", c)

# C2: ACO soft=60 + IPR imb=0.7
c = orig.replace(
    'ACOStrategy("ASH_COATED_OSMIUM", position_limit=80, soft_limit=50)',
    'ACOStrategy("ASH_COATED_OSMIUM", position_limit=80, soft_limit=60)')
c = c.replace("imb * 0.5", "imb * 0.7")
test("ACO s=60 + IPR imb=0.7", c)

# Restore
write_sub(orig)
try:
    os.remove(BACKUP)
    os.remove(os.path.join(WORKSPACE, "_bt_output.txt"))
except:
    pass
print(f"\n  Restored submission.py.")
