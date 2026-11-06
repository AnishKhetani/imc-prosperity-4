"""sweep_v5: layer voucher/VFE knobs ON TOP of the v4 winner
(HGP_SOFT=200, HGP_TAKE_EDGE=0, HGP_LOSS_FLOOR=-99999)."""
import re, subprocess, sys, shutil, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SUB = ROOT / "submissionr4.py"
RUNNER = ROOT / "scripts" / "run_r4_backtest.py"

def run_3day():
    r = subprocess.run([sys.executable, str(RUNNER), "submissionr4.py", "all"],
                       capture_output=True, text=True, cwd=str(ROOT), timeout=600)
    out = r.stdout + r.stderr
    days = re.findall(r"Day \d:\s+([\d,\-]+)", out)
    days = [int(x.replace(',', '')) for x in days[:3]]
    m = re.search(r"TOTAL:\s+([\d,\-]+)", out)
    total = int(m.group(1).replace(',', '')) if m else sum(days)
    return days, total

def run_live():
    r = subprocess.run([sys.executable, str(RUNNER), "submissionr4.py", "--live"],
                       capture_output=True, text=True, cwd=str(ROOT), timeout=300)
    out = r.stdout + r.stderr
    m = re.search(r"Total profit:\s+([\d,\-]+)", out)
    return int(m.group(1).replace(',', '')) if m else 0

def patch(replacements):
    """List of (pattern, repl) regex tuples."""
    src = SUB.read_text(encoding="utf-8")
    for pat, repl in replacements:
        new = re.sub(pat, repl, src, count=1, flags=re.MULTILINE)
        assert new != src, f"PATCH FAILED: {pat}"
        src = new
    SUB.write_text(src, encoding="utf-8")

def restore(orig):
    SUB.write_text(orig, encoding="utf-8")

EXPERIMENTS = [
    # name, list of (pattern, replacement)
    ("BASELINE_v4WIN",                []),
    ("VFE_SOFT=200",                  [(r"^VFE_SOFT\s*=\s*\d+", "VFE_SOFT           = 200")]),
    ("VFE_TAKE_EDGE=1",               [(r"^VFE_TAKE_EDGE\s*=\s*\d+", "VFE_TAKE_EDGE      = 1")]),
    ("VFE_MAKE_OFFSET=0",             [(r"^VFE_MAKE_OFFSET\s*=\s*\d+", "VFE_MAKE_OFFSET    = 0")]),
    ("VFE_FV_EMA_W=0.8",              [(r"^VFE_FV_EMA_WEIGHT\s*=\s*[\d.]+", "VFE_FV_EMA_WEIGHT  = 0.8")]),
    ("VFE_FV_EMA_W=1.0",              [(r"^VFE_FV_EMA_WEIGHT\s*=\s*[\d.]+", "VFE_FV_EMA_WEIGHT  = 1.0")]),
    ("VEV_SOFT=150",                  [(r"^VEV_SOFT\s*=\s*\d+", "VEV_SOFT           = 150")]),
    ("VEV_SOFT=200",                  [(r"^VEV_SOFT\s*=\s*\d+", "VEV_SOFT           = 200")]),
    ("VEV_MAX_QTY=30",                [(r"^VEV_MAX_QTY\s*=\s*\d+", "VEV_MAX_QTY        = 30")]),
    ("VEV_MAX_QTY=50",                [(r"^VEV_MAX_QTY\s*=\s*\d+", "VEV_MAX_QTY        = 50")]),
    ("VEV_TAKE_MARGIN=0",             [(r"^VEV_TAKE_MARGIN\s*=\s*\d+", "VEV_TAKE_MARGIN    = 0")]),
    ("VEV_DEEP_SOFT=120",             [(r"^VEV_DEEP_ITM_SOFT\s*=\s*\d+", "VEV_DEEP_ITM_SOFT  = 120")]),
    ("VEV_DEEP_QTY=30",               [(r"^VEV_DEEP_ITM_QTY\s*=\s*\d+", "VEV_DEEP_ITM_QTY   = 30")]),
    # combos
    ("VEV_SOFT=150+MAX=30",           [(r"^VEV_SOFT\s*=\s*\d+", "VEV_SOFT           = 150"),
                                       (r"^VEV_MAX_QTY\s*=\s*\d+", "VEV_MAX_QTY        = 30")]),
    ("VEV_SOFT=200+MAX=50+TM=0",      [(r"^VEV_SOFT\s*=\s*\d+", "VEV_SOFT           = 200"),
                                       (r"^VEV_MAX_QTY\s*=\s*\d+", "VEV_MAX_QTY        = 50"),
                                       (r"^VEV_TAKE_MARGIN\s*=\s*\d+", "VEV_TAKE_MARGIN    = 0")]),
    ("VFE_SOFT=200+TAKE=1",           [(r"^VFE_SOFT\s*=\s*\d+", "VFE_SOFT           = 200"),
                                       (r"^VFE_TAKE_EDGE\s*=\s*\d+", "VFE_TAKE_EDGE      = 1")]),
    ("VFE_SOFT=200+MAKE=0",           [(r"^VFE_SOFT\s*=\s*\d+", "VFE_SOFT           = 200"),
                                       (r"^VFE_MAKE_OFFSET\s*=\s*\d+", "VFE_MAKE_OFFSET    = 0")]),
]

def main():
    orig = SUB.read_text(encoding="utf-8")
    results = []
    try:
        for name, reps in EXPERIMENTS:
            restore(orig)
            if reps:
                patch(reps)
            t0 = time.time()
            try:
                days, total = run_3day()
                live = run_live()
            except Exception as e:
                print(f"[{name:35s}] ERR {e}")
                continue
            d1 = days[0] if len(days) > 0 else 0
            d2 = days[1] if len(days) > 1 else 0
            d3 = days[2] if len(days) > 2 else 0
            print(f"[{name:35s}] D1={d1:7,} D2={d2:7,} D3={d3:7,} 3D={total:8,} LIVE={live:6,}  ({time.time()-t0:.0f}s)", flush=True)
            results.append((name, total, live, total + live))
    finally:
        restore(orig)

    print("\n=== SORTED by 3D+LIVE ===")
    for name, t, l, s in sorted(results, key=lambda x: -x[3]):
        print(f"[{name:35s}] 3D={t:8,} LIVE={l:6,} SUM={s:8,}")

if __name__ == "__main__":
    main()
