"""Quick experiments to beat the 91,618 baseline."""
import subprocess, re, shutil, os

WORKSPACE = r"."
SUBMISSION = os.path.join(WORKSPACE, "submission.py")
BACKUP = os.path.join(WORKSPACE, "submission_experiment_backup.py")

# Save original
shutil.copy2(SUBMISSION, BACKUP)

def read_file():
    with open(SUBMISSION, "r", encoding="utf-8") as f:
        return f.read()

def write_file(code):
    with open(SUBMISSION, "w", encoding="utf-8") as f:
        f.write(code)

def run_backtest():
    result = subprocess.run(
        ["prosperity4btx", "submission.py", "2"],
        cwd=WORKSPACE,
        capture_output=True, text=True, timeout=120
    )
    output = result.stdout + result.stderr
    # Parse profit
    days = re.findall(r"Round 2 day [^:]+:\s*([\d,\-]+)", output)
    total_m = re.search(r"Total profit:\s*([\d,\-]+)", output)
    if total_m:
        total = int(total_m.group(1).replace(",", ""))
        day_vals = [int(d.replace(",", "")) for d in days]
        return total, day_vals
    return None, []

def test(name, code):
    write_file(code)
    total, days = run_backtest()
    days_str = " / ".join(f"{d:,}" for d in days) if days else "?"
    print(f"{name:40s} | {days_str:30s} | Total: {total:,}" if total else f"{name:40s} | FAILED")
    return total

original = read_file()

print("=" * 90)
print(f"{'Experiment':40s} | {'Day -1 / Day 0 / Day 1':30s} | Total")
print("-" * 90)

# Baseline
test("Baseline (soft=50/50)", original)

# Experiment 1: ACO soft_limit=55, IPR=50
code = original.replace(
    'ACOStrategy("ASH_COATED_OSMIUM", position_limit=80, soft_limit=50)',
    'ACOStrategy("ASH_COATED_OSMIUM", position_limit=80, soft_limit=55)'
)
test("ACO soft=55, IPR soft=50", code)

# Experiment 2: ACO soft_limit=60, IPR=50
code = original.replace(
    'ACOStrategy("ASH_COATED_OSMIUM", position_limit=80, soft_limit=50)',
    'ACOStrategy("ASH_COATED_OSMIUM", position_limit=80, soft_limit=60)'
)
test("ACO soft=60, IPR soft=50", code)

# Experiment 3: ACO soft=50, IPR soft=45
code = original.replace(
    'IPRStrategy("INTARIAN_PEPPER_ROOT", position_limit=80, soft_limit=50)',
    'IPRStrategy("INTARIAN_PEPPER_ROOT", position_limit=80, soft_limit=45)'
)
test("ACO soft=50, IPR soft=45", code)

# Experiment 4: ACO soft=50, IPR soft=55
code = original.replace(
    'IPRStrategy("INTARIAN_PEPPER_ROOT", position_limit=80, soft_limit=50)',
    'IPRStrategy("INTARIAN_PEPPER_ROOT", position_limit=80, soft_limit=55)'
)
test("ACO soft=50, IPR soft=55", code)

# Experiment 5: Reduce IPR skew (0.1 -> 0.05) for long bias during drift
code = original.replace("inv_skew = 0.1 * position", "inv_skew = 0.05 * position")
test("IPR skew 0.05 (long bias)", code)

# Experiment 6: Increase IPR skew (0.1 -> 0.15)
code = original.replace("inv_skew = 0.1 * position", "inv_skew = 0.15 * position")
test("IPR skew 0.15", code)

# Experiment 7: IPR EMA window 3 (faster tracking)
code = original.replace("EMA_ALPHA = 2.0 / 6", "EMA_ALPHA = 2.0 / 4")
test("IPR EMA window=3 (alpha=0.5)", code)

# Experiment 8: IPR EMA window 7 (slower tracking)
code = original.replace("EMA_ALPHA = 2.0 / 6", "EMA_ALPHA = 2.0 / 8")
test("IPR EMA window=7 (alpha=0.25)", code)

# Experiment 9: IPR imbalance weight 0.3 (less responsive)
code = original.replace("imb * 0.5", "imb * 0.3")
test("IPR imb weight 0.3", code)

# Experiment 10: IPR imbalance weight 0.7 (more responsive)
code = original.replace("imb * 0.5", "imb * 0.7")
test("IPR imb weight 0.7", code)

# Experiment 11: No depth contrarian for IPR
code = original.replace(
    "        # Depth contrarian: shift makes against full-book imbalance (mean-reversion)\n"
    "        bid_depth = sum(od.buy_orders.values())\n"
    "        ask_depth = sum(abs(v) for v in od.sell_orders.values())\n"
    "        total_depth = bid_depth + ask_depth\n"
    "        if total_depth > 0:\n"
    "            depth_imb = (bid_depth - ask_depth) / total_depth\n"
    "            if depth_imb > 0.1:\n"
    "                ask_price -= 1\n"
    "            elif depth_imb < -0.1:\n"
    "                bid_price += 1\n",
    "        # Depth contrarian disabled\n"
)
test("IPR no depth contrarian", code)

# Experiment 12: ACO take at fair (not fair±1) — more aggressive taking
code = original.replace(
    "            if ask_p <= fair - 1:\n"
    "                o = self.soft_buy(ask_p, ask_v, position)\n"
    "                if o:\n"
    "                    orders.append(o)\n"
    "                    position += o.quantity\n"
    "            elif ask_p <= fair and position < 0:",
    "            if ask_p <= fair:\n"
    "                o = self.soft_buy(ask_p, ask_v, position)\n"
    "                if o:\n"
    "                    orders.append(o)\n"
    "                    position += o.quantity\n"
    "            elif False and position < 0:",
    1  # only first occurrence (ACO)
)
# Also fix sell side for ACO
code_lines = code.split("\n")
# Find the ACO sell take section
for i, line in enumerate(code_lines):
    if "bid_p >= fair + 1:" in line and i < 260:  # ACO section
        code_lines[i] = line.replace("bid_p >= fair + 1:", "bid_p >= fair:")
        code_lines[i+4] = code_lines[i+4].replace("elif bid_p >= fair and position > 0:", "elif False and position > 0:")
        break
code = "\n".join(code_lines)
test("ACO take at fair (not fair+-1)", code)

# Restore original
write_file(original)
os.remove(BACKUP)
print("=" * 90)
print("Restored submission.py to baseline.")
