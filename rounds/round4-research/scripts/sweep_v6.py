"""sweep_v6: tiny VEV-only sweep on top of v4 winner."""
import re, subprocess, sys, time
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
    src = SUB.read_text(encoding="utf-8")
    for pat, repl in replacements:
        new = re.sub(pat, repl, src, count=1, flags=re.MULTILINE)
        assert new != src, f"PATCH FAILED: {pat}"
        src = new
    SUB.write_text(src, encoding="utf-8")

def restore(orig):
    SUB.write_text(orig, encoding="utf-8")

EXPERIMENTS = [
    ("BASELINE",                      []),
    ("VEV_SOFT=150",                  [(r"^VEV_SOFT\s*=\s*\d+", "VEV_SOFT           = 150")]),
    ("VEV_MAX_QTY=30",                [(r"^VEV_MAX_QTY\s*=\s*\d+", "VEV_MAX_QTY        = 30")]),
    ("VEV_TAKE_MARGIN=0",             [(r"^VEV_TAKE_MARGIN\s*=\s*\d+", "VEV_TAKE_MARGIN    = 0")]),
    ("VEV_DEEP_QTY=20",               [(r"^VEV_DEEP_ITM_QTY\s*=\s*\d+", "VEV_DEEP_ITM_QTY   = 20")]),
    ("VEV_DEEP_QTY=24",               [(r"^VEV_DEEP_ITM_QTY\s*=\s*\d+", "VEV_DEEP_ITM_QTY   = 24")]),
    ("VEV_DEEP_SOFT=120",             [(r"^VEV_DEEP_ITM_SOFT\s*=\s*\d+", "VEV_DEEP_ITM_SOFT  = 120")]),
    ("VEV_EDGE=2",                    [(r"^VEV_EDGE\s*=\s*\d+", "VEV_EDGE           = 2")]),
    ("DEEP_SOFT=120+QTY=24",          [(r"^VEV_DEEP_ITM_SOFT\s*=\s*\d+", "VEV_DEEP_ITM_SOFT  = 120"),
                                       (r"^VEV_DEEP_ITM_QTY\s*=\s*\d+", "VEV_DEEP_ITM_QTY   = 24")]),
    ("MAX=30+TAKE_M=0",               [(r"^VEV_MAX_QTY\s*=\s*\d+", "VEV_MAX_QTY        = 30"),
                                       (r"^VEV_TAKE_MARGIN\s*=\s*\d+", "VEV_TAKE_MARGIN    = 0")]),
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
                print(f"[{name:30s}] ERR {e}", flush=True)
                continue
            d1 = days[0] if len(days) > 0 else 0
            d2 = days[1] if len(days) > 1 else 0
            d3 = days[2] if len(days) > 2 else 0
            print(f"[{name:30s}] D1={d1:6,} D2={d2:6,} D3={d3:6,} 3D={total:7,} LIVE={live:6,}  ({time.time()-t0:.0f}s)", flush=True)
            results.append((name, total, live, total + live))
    finally:
        restore(orig)

    print("\n=== SORTED by 3D+LIVE ===", flush=True)
    for name, t, l, s in sorted(results, key=lambda x: -x[3]):
        print(f"[{name:30s}] 3D={t:7,} LIVE={l:6,} SUM={s:7,}", flush=True)

if __name__ == "__main__":
    main()
