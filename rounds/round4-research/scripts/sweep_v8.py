"""sweep_v8: fine TREND_DRIFT scan + combined winners from v7."""
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

# Combine v7 winners step by step
EXPERIMENTS = [
    ("BASELINE",                      []),
    ("TREND=10",                      [(r"^HGP_TREND_DRIFT\s*=\s*\d+", "HGP_TREND_DRIFT    = 10")]),
    ("TREND=12",                      [(r"^HGP_TREND_DRIFT\s*=\s*\d+", "HGP_TREND_DRIFT    = 12")]),
    ("TREND=15",                      [(r"^HGP_TREND_DRIFT\s*=\s*\d+", "HGP_TREND_DRIFT    = 15")]),
    ("TREND=18",                      [(r"^HGP_TREND_DRIFT\s*=\s*\d+", "HGP_TREND_DRIFT    = 18")]),
    ("TREND=20",                      [(r"^HGP_TREND_DRIFT\s*=\s*\d+", "HGP_TREND_DRIFT    = 20")]),
    ("TREND=8",                       [(r"^HGP_TREND_DRIFT\s*=\s*\d+", "HGP_TREND_DRIFT    = 8")]),
    ("TREND=15+TAKE=-1",              [(r"^HGP_TREND_DRIFT\s*=\s*\d+", "HGP_TREND_DRIFT    = 15"),
                                       (r"^HGP_TAKE_EDGE\s*=\s*-?\d+",  "HGP_TAKE_EDGE      = -1")]),
    ("TREND=15+MAKE=4",               [(r"^HGP_TREND_DRIFT\s*=\s*\d+", "HGP_TREND_DRIFT    = 15"),
                                       (r"^HGP_MAKE_OFFSET\s*=\s*\d+",  "HGP_MAKE_OFFSET    = 4")]),
    ("ALL3 (T=15+TAKE=-1+M=4)",       [(r"^HGP_TREND_DRIFT\s*=\s*\d+", "HGP_TREND_DRIFT    = 15"),
                                       (r"^HGP_TAKE_EDGE\s*=\s*-?\d+",  "HGP_TAKE_EDGE      = -1"),
                                       (r"^HGP_MAKE_OFFSET\s*=\s*\d+",  "HGP_MAKE_OFFSET    = 4")]),
]

def main():
    orig = SUB.read_text(encoding="utf-8")
    log = open(ROOT / "sweep_v8.log", "w")
    def emit(s):
        print(s, flush=True)
        log.write(s + "\n"); log.flush()
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
                emit(f"[{name:25s}] ERR {e}")
                continue
            d1 = days[0] if len(days) > 0 else 0
            d2 = days[1] if len(days) > 1 else 0
            d3 = days[2] if len(days) > 2 else 0
            emit(f"[{name:25s}] D1={d1:6,} D2={d2:6,} D3={d3:6,} 3D={total:7,} LIVE={live:6,}  ({time.time()-t0:.0f}s)")
            results.append((name, total, live, total + live))
    finally:
        restore(orig)

    emit("\n=== SORTED by 3D+LIVE ===")
    for name, t, l, s in sorted(results, key=lambda x: -x[3]):
        emit(f"[{name:25s}] 3D={t:7,} LIVE={l:6,} SUM={s:7,}")
    log.close()

if __name__ == "__main__":
    main()
