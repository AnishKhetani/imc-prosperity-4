"""Focused grid search - writes results to file."""
import subprocess, re, os

BASE_DIR = r"."
SUBMISSION = os.path.join(BASE_DIR, "submission.py")
TEMPLATE = os.path.join(BASE_DIR, "logs", "277766", "277766.py")
RESULTS = os.path.join(BASE_DIR, "grid_results.txt")

with open(TEMPLATE, "r", encoding="utf-8") as f:
    original = f.read()

results = []

def run_test(code, label):
    with open(SUBMISSION, "w", encoding="utf-8") as f:
        f.write(code)
    try:
        result = subprocess.run(
            ["prosperity4btx", SUBMISSION, "2"],
            capture_output=True, text=True, timeout=120, cwd=BASE_DIR
        )
        output = result.stdout + result.stderr
        aco_pnls = re.findall(r"ASH_COATED_OSMIUM:\s*([\d,]+)", output)
        ipr_pnls = re.findall(r"INTARIAN_PEPPER_ROOT:\s*([\d,]+)", output)
        
        aco_total = sum(int(x.replace(",","")) for x in aco_pnls) if aco_pnls else 0
        ipr_total = sum(int(x.replace(",","")) for x in ipr_pnls) if ipr_pnls else 0
        grand = aco_total + ipr_total
        
        line = f"{label:40s} ACO={aco_total:>7,}  IPR={ipr_total:>7,}  TOTAL={grand:>7,}"
        results.append(line)
        # Write incrementally
        with open(RESULTS, "w", encoding="utf-8") as rf:
            rf.write("\n".join(results) + "\n")
        return grand
    except Exception as e:
        line = f"{label:40s} FAILED: {e}"
        results.append(line)
        with open(RESULTS, "w", encoding="utf-8") as rf:
            rf.write("\n".join(results) + "\n")
        return 0

results.append("=" * 80)
results.append("PARAMETER GRID SEARCH RESULTS")
results.append("=" * 80)

# Baseline
run_test(original, "BASELINE (ACO=70, IPR=50)")

# IPR soft_limit sweep
for v in [40, 45, 55, 60, 65, 70]:
    code = original.replace(
        'IPRStrategy("INTARIAN_PEPPER_ROOT", position_limit=80, soft_limit=50)',
        f'IPRStrategy("INTARIAN_PEPPER_ROOT", position_limit=80, soft_limit={v})'
    )
    run_test(code, f"IPR soft={v}")

# IPR inv_skew sweep
for v in [0.0, 0.05, 0.15, 0.2, 0.3]:
    code = original.replace(
        'inv_skew = 0.1 * position',
        f'inv_skew = {v} * position'
    )
    run_test(code, f"IPR inv_skew={v}")

# IPR EMA sweep (window = denominator - 1)
for denom in [4, 5, 8, 10, 12]:
    code = original.replace(
        'EMA_ALPHA = 2.0 / 6  # window = 5',
        f'EMA_ALPHA = 2.0 / {denom}  # window = {denom-1}'
    )
    run_test(code, f"IPR EMA denom={denom} (win={denom-1})")

# IPR imb_weight sweep
for v in [0.0, 0.3, 0.5, 0.7, 1.2, 1.5]:
    code = original.replace(
        'fair = round(self.ema_fair + imb * 0.9 - inv_skew)',
        f'fair = round(self.ema_fair + imb * {v} - inv_skew)'
    )
    run_test(code, f"IPR imb_weight={v}")

# ACO EMA sweep
for denom in [8, 10, 12, 20, 30]:
    aco_line = 'EMA_ALPHA = 2.0 / 16  # window \u2248 15, slow to reduce noise'
    code = original.replace(
        aco_line,
        f'EMA_ALPHA = 2.0 / {denom}  # window = {denom-1}'
    )
    run_test(code, f"ACO EMA denom={denom} (win={denom-1})")

# ACO inventory skew
for v in [0.02, 0.05, 0.1, 0.15]:
    code = original.replace(
        'fair = round(self.ema_fair + imb * 0.7)',
        f'fair = round(self.ema_fair + imb * 0.7 - {v} * position)'
    )
    run_test(code, f"ACO inv_skew={v}")

# Restore original
with open(SUBMISSION, "w", encoding="utf-8") as f:
    f.write(original)

results.append("=" * 80)
results.append("SEARCH COMPLETE - original restored")
with open(RESULTS, "w", encoding="utf-8") as rf:
    rf.write("\n".join(results) + "\n")
print("DONE - see grid_results.txt")
