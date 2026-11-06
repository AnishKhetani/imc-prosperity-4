"""Push HGP_SOFT=200 + LOSS_FLOOR disabled, combine with other knobs."""
import re, shutil, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ALGO = ROOT / "submissionr4.py"
RUNNER = ROOT / "scripts" / "run_r4_backtest.py"


def patch(text, key, value):
    pat = re.compile(rf"^({re.escape(key)}\s*=\s*)[^\n#]*?(\s*#.*)?$", re.M)
    repl = lambda m: f"{m.group(1)}{value}" + (m.group(2) or "")
    new, n = pat.subn(repl, text, count=1)
    if n != 1:
        raise RuntimeError(f"Failed to patch {key}: {n} matches")
    return new


def run_3day():
    r = subprocess.run([sys.executable, str(RUNNER), "submissionr4.py", "all"],
                       capture_output=True, text=True, cwd=str(ROOT), timeout=300)
    days, total = {}, None
    for line in r.stdout.splitlines():
        line = line.strip()
        m = re.match(r"Day (\d):\s+([-\d,]+)", line)
        if m: days[int(m.group(1))] = int(m.group(2).replace(",", ""))
        m = re.match(r"TOTAL:\s+([-\d,]+)", line)
        if m: total = int(m.group(1).replace(",", ""))
    return days, total


def run_live():
    r = subprocess.run([sys.executable, str(RUNNER), "submissionr4.py", "--live"],
                       capture_output=True, text=True, cwd=str(ROOT), timeout=180)
    for line in r.stdout.splitlines():
        m = re.search(r"Total profit:\s+([-\d,]+)", line)
        if m: return int(m.group(1).replace(",", ""))
    return 0


# Anchor the LOSS_FLOOR=-99k disable as proven and stack on top
ANCHOR = {"HGP_SOFT": 180, "HGP_LOSS_FLOOR": -99999}
EXPERIMENTS = [
    ("HGP200+NO_FLOOR", {"HGP_SOFT": 200, "HGP_LOSS_FLOOR": -99999}),
    ("HGP180+NF+MAKE2", {**ANCHOR, "HGP_MAKE_OFFSET": 2}),
    ("HGP180+NF+MAKE1", {**ANCHOR, "HGP_MAKE_OFFSET": 1}),
    ("HGP200+NF+MAKE2", {"HGP_SOFT": 200, "HGP_LOSS_FLOOR": -99999, "HGP_MAKE_OFFSET": 2}),
    ("HGP200+NF+TAKE0", {"HGP_SOFT": 200, "HGP_LOSS_FLOOR": -99999, "HGP_TAKE_EDGE": 0}),
    ("HGP200+NF+TREND200", {"HGP_SOFT": 200, "HGP_LOSS_FLOOR": -99999, "HGP_TREND_DRIFT": 200}),
    ("HGP180+NF+VFE_TAKE1", {**ANCHOR, "VFE_TAKE_EDGE": 1}),
    ("HGP180+NF+VFE_MAKE0", {**ANCHOR, "VFE_MAKE_OFFSET": 0}),
    ("HGP180+NF+VEV_DEEP_QTY=20", {**ANCHOR, "VEV_DEEP_ITM_QTY": 20}),
    ("HGP180+NF+VEV_TAKE0", {**ANCHOR, "VEV_TAKE_MARGIN": 0}),
    ("HGP180+NF+VEV_SOFT=150", {**ANCHOR, "VEV_SOFT": 150}),
    ("HGP180+NF+VEV_MAX_QTY=30", {**ANCHOR, "VEV_MAX_QTY": 30}),
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
                print(f"[{name}] PATCH-FAIL: {e}", flush=True); continue
            ALGO.write_text(text, encoding="utf-8")
            try:
                days, total = run_3day()
                live = run_live()
            except subprocess.TimeoutExpired:
                print(f"[{name}] TIMEOUT", flush=True); continue
            print(f"[{name:<35}] D1={days.get(1,0):>7,} D2={days.get(2,0):>7,} "
                  f"D3={days.get(3,0):>7,} 3D={total or 0:>7,} LIVE={live:>6,}", flush=True)
            results.append((name, total or 0, live))
    finally:
        shutil.move(backup, ALGO)

    print("\n=== SORTED ===", flush=True)
    for name, total, live in sorted(results, key=lambda r: -(r[1] + r[2])):
        print(f"  3D={total:>7,} LIVE={live:>6,}  {name}", flush=True)


if __name__ == "__main__":
    main()
