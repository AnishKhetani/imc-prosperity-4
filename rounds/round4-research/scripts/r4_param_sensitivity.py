"""
R4 parameter sensitivity sweep.

Goal: confirm submissionr4.py is not over-fit to specific parameter values.
Sweeps: HGP_SOFT, VEV_SOFT, HGP_TREND_DRIFT.
For each combo, runs 3 days at match=worse and reports total PnL.
"""
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "submissionr4.py"
TMP = ROOT / "submissionr4_sens.py"


def run(algo: Path, day: int, tte: int) -> int:
    env = os.environ.copy(); env["IMC_TTE_DAYS"] = str(tte)
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "run_r4_backtest.py"),
                        str(algo.name), str(day)], capture_output=True, text=True, env=env, cwd=str(ROOT))
    pnl = 0
    for line in r.stdout.splitlines():
        if "Total profit:" in line:
            try:
                pnl = int(line.split("Total profit:")[-1].strip().replace(",", ""))
            except Exception:
                pnl = 0
    return pnl


def patch(content: str, name: str, value) -> str:
    pattern = rf"^({name}\s*=\s*).*$"
    return re.sub(pattern, rf"\g<1>{value}", content, count=1, flags=re.M)


def main():
    base = SRC.read_text(encoding="utf-8")
    # Small one-at-a-time sweep around (80, 80, 25) to test sensitivity.
    grid = [
        (80, 80, 25),  # baseline
        (60, 80, 25), (100, 80, 25),
        (80, 60, 25), (80, 100, 25),
        (80, 80, 20), (80, 80, 30),
    ]

    print(f"{'HGP_SOFT':>9} {'VEV_SOFT':>9} {'TREND':>6} {'D1':>9} {'D2':>9} {'D3':>9} {'TOT':>10}")
    for hgp_soft, vev_soft, trend in grid:
        c = base
        c = patch(c, "HGP_SOFT", hgp_soft)
        c = patch(c, "VEV_SOFT", vev_soft)
        c = patch(c, "HGP_TREND_DRIFT", trend)
        TMP.write_text(c, encoding="utf-8")
        # Need to also create _sens variant in cwd so submissionr4.py-relative
        # backtester picks the right algo path
        d1 = run(TMP, 1, 7)
        d2 = run(TMP, 2, 6)
        d3 = run(TMP, 3, 5)
        print(f"{hgp_soft:>9} {vev_soft:>9} {trend:>6} {d1:>9,} {d2:>9,} {d3:>9,} {d1+d2+d3:>10,}")

    if TMP.exists():
        TMP.unlink()


if __name__ == "__main__":
    main()
