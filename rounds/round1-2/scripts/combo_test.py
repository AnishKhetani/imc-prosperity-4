"""
Combinatorial strategy variant tester — uses subprocess for clean module loading.
Tests all 2^6 = 64 combinations of 6 proposed changes.

Changes tested:
  1. EM_NO_SKEW     — Remove EMERALDS position skew (SKEW=1.0, HEAVY=1.0)
  2. STALE_GUARD    — Clamp TOMATOES fair to mid±2 to prevent stale EMA takes
  3. WIND_DOWN      — End-of-day position wind-down (last 10% of ticks)
  4. TOM_SKEW_005   — Lower TOMATOES SKEW_THRESHOLD from 0.15 to 0.05
  5. IMB_ZERO       — Set IMB_WEIGHT to 0.0 (remove imbalance signal)
  6. NO_DEPTH_CONTR — Set DEPTH_CONTRARIAN to 0 (remove depth signal)
"""

import subprocess
import sys
import time
import itertools
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
BACKTESTER_DIR = SCRIPT_DIR.parent / "backtester"
RUNNER_SCRIPT = SCRIPT_DIR / "run_single_combo.py"

FLAG_NAMES = [
    "EM_NO_SKEW",
    "STALE_GUARD",
    "WIND_DOWN",
    "TOM_SKEW_005",
    "IMB_ZERO",
    "NO_DEPTH_CTR",
]


def flags_to_params(flags):
    em_no_skew, stale_guard, wind_down, tom_skew_005, imb_zero, no_depth_contr = flags
    return {
        "em_skew": 1.0 if em_no_skew else 0.3,
        "em_heavy": 1.0 if em_no_skew else 0.6,
        "tom_skew": 0.05 if tom_skew_005 else 0.15,
        "imb_weight": 0.0 if imb_zero else 0.5,
        "depth_contrarian": 0 if no_depth_contr else 1,
        "stale_guard": 1 if stale_guard else 0,
        "wind_down": 1 if wind_down else 0,
    }


def run_combo(flags):
    params = flags_to_params(flags)
    cmd = [
        sys.executable,
        str(RUNNER_SCRIPT),
        str(params["em_skew"]),
        str(params["em_heavy"]),
        str(params["tom_skew"]),
        str(params["imb_weight"]),
        str(params["depth_contrarian"]),
        str(params["stale_guard"]),
        str(params["wind_down"]),
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(BACKTESTER_DIR),
        )
        output = result.stdout + result.stderr
        for line in output.split("\n"):
            if line.startswith("RESULT|"):
                parts = line.strip().split("|")
                return {
                    "total": float(parts[1]),
                    "day-2": float(parts[2]),
                    "day-1": float(parts[3]),
                    "em_d2": float(parts[4]),
                    "em_d1": float(parts[5]),
                    "tom_d2": float(parts[6]),
                    "tom_d1": float(parts[7]),
                }
        return {"total": float("nan"), "error": output[-500:]}
    except Exception as e:
        return {"total": float("nan"), "error": str(e)}


def log(msg, logfile=None):
    print(msg, flush=True)
    if logfile:
        logfile.write(msg + "\n")
        logfile.flush()


def main():
    all_combos = list(itertools.product([False, True], repeat=6))
    total = len(all_combos)

    outfile = SCRIPT_DIR / "combo_results_final.txt"
    lf = open(outfile, "w", encoding="utf-8")

    # Backup original strategy files
    em_path = BACKTESTER_DIR / "strategies" / "emeralds.py"
    tom_path = BACKTESTER_DIR / "strategies" / "tomatoes.py"
    em_backup = em_path.read_text(encoding="utf-8")
    tom_backup = tom_path.read_text(encoding="utf-8")

    log(f"Testing {total} combinations across 2 days each", lf)
    log(f"Flags: {FLAG_NAMES}", lf)
    log("=" * 110, lf)

    results = []
    start_time = time.time()

    try:
        for i, flags in enumerate(all_combos):
            try:
                elapsed = time.time() - start_time
                eta = (elapsed / (i + 1)) * (total - i - 1) if i > 0 else 0

                flag_str = "".join("1" if f else "0" for f in flags)
                active = [name for name, on in zip(FLAG_NAMES, flags) if on]
                active_str = "+".join(active) if active else "BASELINE"

                result = run_combo(flags)
                results.append((flags, result))

                t = result.get("total", float("nan"))
                d2 = result.get("day-2", 0)
                d1 = result.get("day-1", 0)

                if t != t:  # NaN check
                    err = result.get("error", "unknown")[:80]
                    log(f"[{i+1:2d}/{total}] {flag_str} {active_str:50s} ERROR: {err}", lf)
                else:
                    log(f"[{i+1:2d}/{total}] {flag_str} {active_str:50s} "
                        f"Total={t:>10,.0f}  D-2={d2:>8,.0f}  D-1={d1:>8,.0f}  [{eta:.0f}s]", lf)
            except Exception as ex:
                import traceback
                log(f"[{i+1:2d}/{total}] EXCEPTION: {traceback.format_exc()}", lf)
                results.append((flags, {"total": float("nan"), "error": str(ex)}))

    finally:
        # ALWAYS restore original files
        em_path.write_text(em_backup, encoding="utf-8")
        tom_path.write_text(tom_backup, encoding="utf-8")
        log("\n[Strategy files restored to originals]", lf)

    # ═══════════════════════════════════════════════════════
    # RESULTS
    # ═══════════════════════════════════════════════════════
    valid = [(f, r) for f, r in results if r.get("total", float("nan")) == r.get("total", float("nan"))]

    # Find baseline
    baseline_pnl = None
    for flags, result in valid:
        if not any(flags):
            baseline_pnl = result["total"]

    valid.sort(key=lambda x: x[1]["total"], reverse=True)

    log("\n" + "=" * 120, lf)
    log("RANKED RESULTS (all 64 combinations)", lf)
    log("=" * 120, lf)
    log(f"{'Rk':>3}  {'Flags':6}  {'Changes':50s}  {'Total':>10}  {'D-2':>8}  {'D-1':>8}  "
        f"{'EM':>8}  {'TOM':>8}  {'vs Base':>8}", lf)
    log("-" * 120, lf)

    for rank, (flags, r) in enumerate(valid, 1):
        flag_str = "".join("1" if f else "0" for f in flags)
        active = [name for name, on in zip(FLAG_NAMES, flags) if on]
        active_str = "+".join(active) if active else "BASELINE"
        diff = r["total"] - baseline_pnl if baseline_pnl else 0
        em_total = r.get("em_d2", 0) + r.get("em_d1", 0)
        tom_total = r.get("tom_d2", 0) + r.get("tom_d1", 0)

        marker = ""
        if not any(flags):
            marker = " <<BASE"
        elif rank <= 3:
            marker = " ***"

        log(f"{rank:3d}  {flag_str}  {active_str:50s}  {r['total']:>10,.0f}  "
            f"{r.get('day-2',0):>8,.0f}  {r.get('day-1',0):>8,.0f}  "
            f"{em_total:>8,.0f}  {tom_total:>8,.0f}  {diff:>+8,.0f}{marker}", lf)

    # ═══════════════════════════════════════════════════════
    # MARGINAL IMPACT ANALYSIS
    # ═══════════════════════════════════════════════════════
    log("\n" + "=" * 80, lf)
    log("MARGINAL IMPACT OF EACH CHANGE", lf)
    log("(avg PnL when ON vs avg PnL when OFF, across all other combos)", lf)
    log("=" * 80, lf)

    for j, name in enumerate(FLAG_NAMES):
        on_pnls = [r["total"] for f, r in valid if f[j]]
        off_pnls = [r["total"] for f, r in valid if not f[j]]
        avg_on = sum(on_pnls) / len(on_pnls) if on_pnls else 0
        avg_off = sum(off_pnls) / len(off_pnls) if off_pnls else 0
        delta = avg_on - avg_off
        direction = "BETTER" if delta > 0 else "WORSE" if delta < 0 else "NEUTRAL"
        log(f"  {name:20s}  ON={avg_on:>10,.0f}  OFF={avg_off:>10,.0f}  "
            f"delta={delta:>+8,.0f}  [{direction}]", lf)

    # ═══════════════════════════════════════════════════════
    # SINGLE-CHANGE ADDITIONS
    # ═══════════════════════════════════════════════════════
    log("\n" + "=" * 80, lf)
    log("SINGLE-CHANGE vs BASELINE", lf)
    log("=" * 80, lf)

    for flags, r in sorted(valid, key=lambda x: x[1]["total"], reverse=True):
        if sum(flags) == 1:
            active = [name for name, on in zip(FLAG_NAMES, flags) if on][0]
            diff = r["total"] - baseline_pnl if baseline_pnl else 0
            em_t = r.get("em_d2", 0) + r.get("em_d1", 0)
            tom_t = r.get("tom_d2", 0) + r.get("tom_d1", 0)
            log(f"  {active:20s}  Total={r['total']:>10,.0f}  EM={em_t:>8,.0f}  TOM={tom_t:>8,.0f}  delta={diff:>+8,.0f}", lf)

    if baseline_pnl:
        log(f"  {'BASELINE':20s}  Total={baseline_pnl:>10,.0f}", lf)

    # ═══════════════════════════════════════════════════════
    # TOP 2-CHANGE COMBINATIONS
    # ═══════════════════════════════════════════════════════
    log("\n" + "=" * 80, lf)
    log("TOP 2-CHANGE COMBINATIONS", lf)
    log("=" * 80, lf)

    two_change = [(f, r) for f, r in valid if sum(f) == 2]
    two_change.sort(key=lambda x: x[1]["total"], reverse=True)
    for flags, r in two_change[:10]:
        active = [name for name, on in zip(FLAG_NAMES, flags) if on]
        active_str = " + ".join(active)
        diff = r["total"] - baseline_pnl if baseline_pnl else 0
        log(f"  {active_str:45s}  Total={r['total']:>10,.0f}  delta={diff:>+8,.0f}", lf)

    elapsed_total = time.time() - start_time
    n_valid = max(1, len(valid))
    log(f"\nCompleted {len(valid)} combinations in {elapsed_total:.1f}s ({elapsed_total/n_valid:.1f}s each)", lf)
    lf.close()
    print(f"Results written to {outfile}")


if __name__ == "__main__":
    main()
