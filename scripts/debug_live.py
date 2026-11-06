"""debug helper — call run_live from sweep_v8."""
import sys, subprocess, re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SUB = ROOT / "submissionr4.py"
RUNNER = ROOT / "scripts" / "run_r4_backtest.py"

r = subprocess.run([sys.executable, str(RUNNER), "submissionr4.py", "--live"],
                   capture_output=True, text=True, cwd=str(ROOT), timeout=300)
out = r.stdout + r.stderr
print("=== STDOUT (last 2000 chars) ===")
print(r.stdout[-2000:])
print("=== STDERR ===")
print(r.stderr[-500:])
print("=== returncode ===", r.returncode)
m = re.search(r"Total profit:\s+([\d,\-]+)", out)
print("=== regex match ===", m.group(1) if m else "NONE")
