"""Experiment harness: regex-patch a constant in submissionr4.py and backtest.

Usage:
    python scripts/exp_patch.py KEY=VALUE [KEY=VALUE ...]

Runs 3-day backtest match=worse + day-3 live-sim match=all and prints summary.
Restores file to original state after each test.
"""
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ALGO = ROOT / "submissionr4.py"
RUNNER = ROOT / "scripts" / "run_r4_backtest.py"


def patch(text: str, key: str, value: str) -> str:
    pat = re.compile(rf"^({re.escape(key)}\s*=\s*).*$", re.M)
    new, n = pat.subn(rf"\g<1>{value}", text, count=1)
    if n != 1:
        raise RuntimeError(f"Failed to patch {key}: {n} matches")
    return new


def run_3day() -> tuple:
    r = subprocess.run([sys.executable, str(RUNNER), "submissionr4.py", "all"],
                       capture_output=True, text=True, cwd=str(ROOT))
    out = r.stdout
    days = {}
    total = None
    for line in out.splitlines():
        line = line.strip()
        m = re.match(r"Day (\d):\s+([-\d,]+)", line)
        if m:
            days[int(m.group(1))] = int(m.group(2).replace(",", ""))
        m = re.match(r"TOTAL:\s+([-\d,]+)", line)
        if m:
            total = int(m.group(1).replace(",", ""))
    return days, total


def run_live() -> int:
    r = subprocess.run([sys.executable, str(RUNNER), "submissionr4.py", "--live"],
                       capture_output=True, text=True, cwd=str(ROOT))
    out = r.stdout
    for line in out.splitlines():
        m = re.search(r"Total profit:\s+([-\d,]+)", line)
        if m:
            return int(m.group(1).replace(",", ""))
    return 0


def main():
    if len(sys.argv) < 2:
        print("usage: exp_patch.py KEY=VAL [KEY=VAL ...]")
        return
    pairs = [a.split("=", 1) for a in sys.argv[1:]]

    backup = ALGO.with_suffix(".py.bak")
    shutil.copy(ALGO, backup)
    try:
        text = ALGO.read_text(encoding="utf-8")
        for k, v in pairs:
            text = patch(text, k, v)
        ALGO.write_text(text, encoding="utf-8")

        days, total = run_3day()
        live = run_live()
        spec = " ".join(f"{k}={v}" for k, v in pairs)
        print(f"\n[{spec}]")
        print(f"  D1={days.get(1,0):>7,} D2={days.get(2,0):>7,} D3={days.get(3,0):>7,}  "
              f"3D_TOTAL={total or 0:>7,}  LIVE3={live:>7,}")
    finally:
        shutil.move(backup, ALGO)


if __name__ == "__main__":
    main()
