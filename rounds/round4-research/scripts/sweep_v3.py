"""Batch sweep v3 — push HGP harder + combine winners.

Baseline: 73,820 / 25,454. Best so far: HGP_SOFT=180 → 78,486 / 25,599.
"""
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ALGO = ROOT / "submissionr4.py"
RUNNER = ROOT / "scripts" / "run_r4_backtest.py"


def patch(text: str, key: str, value) -> str:
    pat = re.compile(rf"^({re.escape(key)}\s*=\s*)[^\n#]*?(\s*#.*)?$", re.M)
    repl = lambda m: f"{m.group(1)}{value}" + (m.group(2) or "")
    new, n = pat.subn(repl, text, count=1)
    if n != 1:
        raise RuntimeError(f"Failed to patch {key}: {n} matches")
    return new


def run_3day():
    r = subprocess.run([sys.executable, str(RUNNER), "submissionr4.py", "all"],
                       capture_output=True, text=True, cwd=str(ROOT), timeout=300)
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


def run_live():
    r = subprocess.run([sys.executable, str(RUNNER), "submissionr4.py", "--live"],
                       capture_output=True, text=True, cwd=str(ROOT), timeout=180)
    for line in r.stdout.splitlines():
        m = re.search(r"Total profit:\s+([-\d,]+)", line)
        if m:
            return int(m.group(1).replace(",", ""))
    return 0


EXPERIMENTS = [
    ("HGP_SOFT=200", {"HGP_SOFT": 200}),
    ("HGP_SOFT=180+TREND_DRIFT=200", {"HGP_SOFT": 180, "HGP_TREND_DRIFT": 200}),
    ("HGP_SOFT=180+LOSS_FLOOR=-99k", {"HGP_SOFT": 180, "HGP_LOSS_FLOOR": -99999}),
    ("HGP_SOFT=180+TAKE_EDGE=0", {"HGP_SOFT": 180, "HGP_TAKE_EDGE": 0}),
    ("HGP_SOFT=180+MAKE_OFFSET=2", {"HGP_SOFT": 180, "HGP_MAKE_OFFSET": 2}),
    ("HGP_SOFT=180+MAKE_OFFSET=1", {"HGP_SOFT": 180, "HGP_MAKE_OFFSET": 1}),
    ("VFE_SOFT=190+VFE_MAKE_PER_TICK=200", {"VFE_SOFT": 190, "VFE_MAKE_PER_TICK": 200}),
    ("VFE_TAKE_EDGE=1", {"VFE_TAKE_EDGE": 1}),
    ("VFE_TAKE_EDGE=0", {"VFE_TAKE_EDGE": 0}),
    ("VFE_MAKE_OFFSET=0", {"VFE_MAKE_OFFSET": 0}),
    ("HGP180+VFE_TAKE_EDGE=1+MAKE0", {"HGP_SOFT": 180, "VFE_TAKE_EDGE": 1, "VFE_MAKE_OFFSET": 0}),
    ("HGP180+VEV_DEEP_QTY=20", {"HGP_SOFT": 180, "VEV_DEEP_ITM_QTY": 20}),
    ("HGP180+VEV_TAKE_MARGIN=0", {"HGP_SOFT": 180, "VEV_TAKE_MARGIN": 0}),
    ("HGP180+VEV_EDGE=0", {"HGP_SOFT": 180, "VEV_EDGE": 0}),
]


def main():
    backup = ALGO.with_suffix(".py.bak")
    shutil.copy(ALGO, backup)
    results = []
    try:
        for name, patches in EXPERIMENTS:
            text = backup.read_text(encoding="utf-8")
            try:
                for k, v in patches.items():
                    text = patch(text, k, v)
            except RuntimeError as e:
                print(f"[{name}] PATCH-FAIL: {e}", flush=True)
                continue
            ALGO.write_text(text, encoding="utf-8")
            try:
                days, total = run_3day()
                live = run_live()
            except subprocess.TimeoutExpired:
                print(f"[{name}] TIMEOUT", flush=True)
                continue
            print(f"[{name:<40}] D1={days.get(1,0):>7,} D2={days.get(2,0):>7,} "
                  f"D3={days.get(3,0):>7,} 3D={total or 0:>7,} LIVE={live:>6,}",
                  flush=True)
            results.append((name, total or 0, live))
    finally:
        shutil.move(backup, ALGO)

    print("\n=== SORTED ===", flush=True)
    for name, total, live in sorted(results, key=lambda r: -(r[1] + r[2])):
        print(f"  3D={total:>7,} LIVE={live:>6,}  {name}", flush=True)


if __name__ == "__main__":
    main()
