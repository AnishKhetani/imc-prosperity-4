"""Focused grid search for IPR parameters and advanced ACO improvements."""
import subprocess, re, sys, os, copy

BASE_DIR = r"."
SUBMISSION = os.path.join(BASE_DIR, "submission.py")
TEMPLATE = os.path.join(BASE_DIR, "logs", "277766", "277766.py")

with open(TEMPLATE, "r", encoding="utf-8") as f:
    original = f.read()

def run_test(code, label):
    with open(SUBMISSION, "w", encoding="utf-8") as f:
        f.write(code)
    try:
        result = subprocess.run(
            ["prosperity4btx", SUBMISSION, "2"],
            capture_output=True, text=True, timeout=120, cwd=BASE_DIR
        )
        output = result.stdout + result.stderr
        # Extract per-product per-day PnL
        aco_pnls = re.findall(r"ASH_COATED_OSMIUM:\s*([\d,]+)", output)
        ipr_pnls = re.findall(r"INTARIAN_PEPPER_ROOT:\s*([\d,]+)", output)
        total_match = re.findall(r"Total profit:\s*([\d,]+)", output)
        
        aco_total = sum(int(x.replace(",","")) for x in aco_pnls) if aco_pnls else 0
        ipr_total = sum(int(x.replace(",","")) for x in ipr_pnls) if ipr_pnls else 0
        grand = int(total_match[-1].replace(",","")) if total_match else 0
        
        print(f"  {label:35s} ACO={aco_total:>7,}  IPR={ipr_total:>7,}  TOTAL={grand:>7,}")
        return grand
    except Exception as e:
        print(f"  {label:35s} FAILED: {e}")
        return 0

# Restore and confirm baseline
print("=" * 80)
print("IPR PARAMETER SWEEP (ACO fixed at soft=70)")
print("=" * 80)
run_test(original, "BASELINE (ACO=70, IPR=50)")

# IPR soft_limit sweep
for ipr_soft in [40, 45, 50, 55, 60]:
    code = original.replace(
        'IPRStrategy("INTARIAN_PEPPER_ROOT", position_limit=80, soft_limit=50)',
        f'IPRStrategy("INTARIAN_PEPPER_ROOT", position_limit=80, soft_limit={ipr_soft})'
    )
    run_test(code, f"IPR soft={ipr_soft}")

# IPR inv_skew sweep
for skew in [0.0, 0.05, 0.1, 0.15, 0.2, 0.3]:
    code = original.replace(
        'inv_skew = 0.1 * position',
        f'inv_skew = {skew} * position'
    )
    run_test(code, f"IPR inv_skew={skew}")

# IPR EMA sweep
for ema_win in [4, 5, 6, 8, 10]:
    alpha = 2.0 / ema_win
    code = original.replace(
        'EMA_ALPHA = 2.0 / 6  # window = 5',
        f'EMA_ALPHA = {alpha}  # window = {ema_win-1}'
    )
    run_test(code, f"IPR EMA_window={ema_win-1}")

# IPR imb_weight sweep
for imb_w in [0.0, 0.3, 0.5, 0.7, 0.9, 1.2, 1.5]:
    code = original.replace(
        'fair = round(self.ema_fair + imb * 0.9 - inv_skew)',
        f'fair = round(self.ema_fair + imb * {imb_w} - inv_skew)'
    )
    run_test(code, f"IPR imb_weight={imb_w}")

# ACO EMA sweep
print("\n" + "=" * 80)
print("ACO EMA SWEEP")
print("=" * 80)
for ema_win in [8, 10, 12, 16, 20, 30]:
    alpha = 2.0 / ema_win
    code = original.replace(
        'EMA_ALPHA = 2.0 / 16  # window',
        f'EMA_ALPHA = {alpha}  # window {ema_win-1}'
    )
    # Handle the encoded version
    code = code.replace(
        'EMA_ALPHA = 2.0 / 16  # window ≈ 15, slow to reduce noise',
        f'EMA_ALPHA = {alpha}  # window {ema_win-1}'
    )
    run_test(code, f"ACO EMA_window={ema_win-1}")

# ACO: Add inventory skew
print("\n" + "=" * 80)
print("ACO INVENTORY SKEW")
print("=" * 80)
for skew in [0.0, 0.02, 0.05, 0.1, 0.15]:
    code = original.replace(
        'fair = round(self.ema_fair + imb * 0.7)',
        f'fair = round(self.ema_fair + imb * 0.7 - {skew} * position)'
    )
    run_test(code, f"ACO inv_skew={skew}")

# Restore original
with open(SUBMISSION, "w", encoding="utf-8") as f:
    f.write(original)
print("\nRestored original submission.py")
