"""Focused experiments — fix output parsing, test key improvements."""
import subprocess, re, shutil, os, sys

WORKSPACE = r"."
SUBMISSION = os.path.join(WORKSPACE, "submission.py")
BACKUP = os.path.join(WORKSPACE, "submission_exp_bak.py")

shutil.copy2(SUBMISSION, BACKUP)

def read_file():
    with open(SUBMISSION, "r", encoding="utf-8") as f:
        return f.read()

def write_file(code):
    with open(SUBMISSION, "w", encoding="utf-8") as f:
        f.write(code)

def run_bt():
    r = subprocess.run(
        ["prosperity4btx", "submission.py", "2"],
        cwd=WORKSPACE, capture_output=True, text=True, timeout=120,
        encoding="utf-8", errors="replace"
    )
    out = r.stdout + "\n" + r.stderr
    days = re.findall(r"Round 2 day [^:]+:\s*([\d,\-]+)", out)
    total_m = re.search(r"Total profit:\s*([\d,\-]+)", out)
    if total_m:
        total = int(total_m.group(1).replace(",", ""))
        dv = [int(d.replace(",", "")) for d in days]
        return total, dv
    # Debug: print raw output
    print(f"  [DEBUG] stdout last 300 chars: {r.stdout[-300:]}")
    print(f"  [DEBUG] stderr last 300 chars: {r.stderr[-300:]}")
    return None, []

def test(name, code):
    write_file(code)
    total, days = run_bt()
    if total is not None:
        ds = " / ".join(f"{d:>7,}" for d in days)
        print(f"  {name:45s} {ds:>30s}   {total:>7,}")
    else:
        print(f"  {name:45s} PARSE FAILED")
    return total

orig = read_file()
print(f"  {'Experiment':45s} {'Day-1 / Day0 / Day1':>30s}   {'Total':>7s}")
print("  " + "-" * 90)

# 0. Baseline
test("Baseline (soft=50/50)", orig)

# 1. ACO soft=55
c = orig.replace("soft_limit=50)", "soft_limit=55)", 1)  # first occurrence = ACO
test("ACO soft=55", c)

# 2. ACO soft=60
c = orig.replace("soft_limit=50)", "soft_limit=60)", 1)
test("ACO soft=60", c)

# 3. IPR soft=45 (second occurrence)
c = orig.replace("soft_limit=50)", "soft_limit=45)")  # both
c = c.replace("soft_limit=45)", "soft_limit=50)", 1)  # restore ACO
test("IPR soft=45", c)

# 4. IPR soft=55
c = orig.replace("soft_limit=50)", "soft_limit=55)")
c = c.replace("soft_limit=55)", "soft_limit=50)", 1)
test("IPR soft=55", c)

# 5. IPR skew 0.05
c = orig.replace("inv_skew = 0.1 * position", "inv_skew = 0.05 * position")
test("IPR skew=0.05", c)

# 6. IPR skew 0.15
c = orig.replace("inv_skew = 0.1 * position", "inv_skew = 0.15 * position")
test("IPR skew=0.15", c)

# 7. IPR skew 0.0
c = orig.replace("inv_skew = 0.1 * position", "inv_skew = 0.0 * position")
test("IPR skew=0.0", c)

# 8. IPR EMA alpha=0.5 (window=3)
c = orig.replace("EMA_ALPHA = 2.0 / 6", "EMA_ALPHA = 2.0 / 4")
test("IPR EMA alpha=0.5 (w=3)", c)

# 9. IPR EMA alpha=0.25 (window=7)
c = orig.replace("EMA_ALPHA = 2.0 / 6", "EMA_ALPHA = 2.0 / 8")
test("IPR EMA alpha=0.25 (w=7)", c)

# 10. IPR imb weight 0.3
c = orig.replace("imb * 0.5", "imb * 0.3")
test("IPR imb=0.3", c)

# 11. IPR imb weight 0.7
c = orig.replace("imb * 0.5", "imb * 0.7")
test("IPR imb=0.7", c)

# 12. No depth contrarian
marker = """        # Depth contrarian: shift makes against full-book imbalance (mean-reversion)
        bid_depth = sum(od.buy_orders.values())
        ask_depth = sum(abs(v) for v in od.sell_orders.values())
        total_depth = bid_depth + ask_depth
        if total_depth > 0:
            depth_imb = (bid_depth - ask_depth) / total_depth
            if depth_imb > 0.1:
                ask_price -= 1
            elif depth_imb < -0.1:
                bid_price += 1"""
c = orig.replace(marker, "        # Depth contrarian: DISABLED")
test("IPR no depth contrarian", c)

# 13. IPR no asymmetric sizing
marker2 = """        pos_ratio = position / self.soft_limit

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
c = orig.replace(marker2, "        # Asymmetric sizing: DISABLED")
test("IPR no asymmetric sizing", c)

# 14. ACO + IPR: best combo candidates (will try combos of winners)
# Combine: ACO soft=55 + IPR skew=0.05
c = orig.replace("soft_limit=50)", "soft_limit=55)", 1)
c = c.replace("inv_skew = 0.1 * position", "inv_skew = 0.05 * position")
test("ACO s=55 + IPR skew=0.05", c)

# Restore
write_file(orig)
os.remove(BACKUP)
print("\n  Restored to baseline.")
