"""Sweep VFE EMA alpha vs backtest (3 days)."""
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "submissionr4.py"
BT = ROOT / "scripts" / "run_r4_backtest.py"

base = SRC.read_text(encoding="utf-8")

print(f"{'alpha':>10} {'D1':>9} {'D2':>9} {'D3':>9} {'TOT':>10}")
for alpha_str in ["2/25", "2/20", "2/15", "2/12", "2/10"]:
    patched = re.sub(r"^VFE_EMA_ALPHA\s*=.*$", f"VFE_EMA_ALPHA      = {alpha_str}",
                     base, count=1, flags=re.M)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False,
                                      encoding="utf-8", dir=ROOT) as tf:
        tf.write(patched)
        tmp = Path(tf.name)
    try:
        r = subprocess.run([sys.executable, "-u", str(BT), tmp.name, "all"],
                           capture_output=True, text=True, cwd=str(ROOT))
        days = [0, 0, 0]
        for line in r.stdout.splitlines():
            if "Day 1:" in line: days[0] = int(line.split(":")[-1].strip().replace(",", ""))
            elif "Day 2:" in line: days[1] = int(line.split(":")[-1].strip().replace(",", ""))
            elif "Day 3:" in line: days[2] = int(line.split(":")[-1].strip().replace(",", ""))
        print(f"{alpha_str:>10} {days[0]:>9,} {days[1]:>9,} {days[2]:>9,} {sum(days):>10,}")
    finally:
        tmp.unlink(missing_ok=True)
