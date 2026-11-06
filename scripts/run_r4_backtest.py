"""
Run prosperity3bt backtester on Round 4 data.

Round 4 data structure (in backtester_data/round4):
  prices_round_4_day_{1,2,3}.csv
  trades_round_4_day_{1,2,3}.csv

TTE schedule (per wiki — Round 4 LIVE day 4 has TTE=4d):
  day 1 → TTE=7
  day 2 → TTE=6
  day 3 → TTE=5    (this is our HOLDOUT — never tune on it)
  live day 4 → TTE=4

Usage:
  python scripts/run_r4_backtest.py <algo.py> [day|all] [--match-mode <mode>] [--live]
    day: 1, 2, 3, or 'all' (default 'all')
    --match-mode: worse | best | all (default 'worse'; 'all' for live sim)
    --live: shorthand for day=3 (most recent), match=all
"""
import sys
import os
import re
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = ROOT / "backtester_data"

DAY_TTE = {1: 7, 2: 6, 3: 5}    # historical days


def run_day(algo: Path, day: int, match_mode: str, tte_days: int) -> tuple:
    # Write a temp copy with TTE_DAYS_AT_T0 patched (submission no longer uses os.environ)
    src = algo.read_text(encoding="utf-8")
    patched = re.sub(r"^TTE_DAYS_AT_T0\s*=.*$", f"TTE_DAYS_AT_T0  = {tte_days}",
                     src, count=1, flags=re.M)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False,
                                     encoding="utf-8", dir=algo.parent) as tf:
        tf.write(patched)
        tmp_path = Path(tf.name)
    try:
        cmd = [
            sys.executable, str(Path(__file__)),
            str(tmp_path), str(day),
            "--match-mode", match_mode,
            "--_subprocess",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(result.stderr[-2000:], file=sys.stderr)
        return result.stdout, result.stderr
    finally:
        tmp_path.unlink(missing_ok=True)


def _subprocess_main(algo: str, day: int, match_mode: str):
    import prosperity3bt.data as p3_data

    R3_LIMITS = {"HYDROGEL_PACK": 200, "VELVETFRUIT_EXTRACT": 200}
    for k in [4000, 4500, 5000, 5100, 5200, 5300, 5400, 5500, 6000, 6500]:
        R3_LIMITS[f"VEV_{k}"] = 300
    p3_data.LIMITS.update(R3_LIMITS)

    import prosperity3bt.runner as p3_runner
    p3_runner.LIMITS = p3_data.LIMITS

    sys.argv = [
        "prosperity3bt", algo,
        f"4-{day}",
        "--data", str(DATA_ROOT),
        "--match-trades", match_mode,
        "--no-progress",
    ]
    from prosperity3bt.__main__ import main as bt_main
    bt_main()


def main():
    args = sys.argv[1:]

    if "--_subprocess" in args:
        idx = args.index("--_subprocess")
        args = args[:idx]
        algo       = args[0]
        day        = int(args[1])
        match_mode = args[args.index("--match-mode") + 1]
        _subprocess_main(algo, day, match_mode)
        return

    algo      = args[0] if len(args) > 0 else "submissionr4.py"
    live_mode = "--live" in args
    match_mode = "worse"
    if "--match-mode" in args:
        match_mode = args[args.index("--match-mode") + 1]

    if live_mode:
        days_to_run = [3]
        match_mode  = "all"
        print("\n*** LIVE-SIM MODE *** (day 3, TTE=5, match=all)")
    else:
        day_arg = next((a for a in args[1:] if not a.startswith("--")
                        and a not in ("worse", "best", "all")), "all")
        days_to_run = list(DAY_TTE.keys()) if day_arg == "all" else [int(day_arg)]

    print(f"  Algorithm : {algo}")
    print(f"  Match     : {match_mode}")
    print(f"  Days      : {days_to_run}\n")

    day_pnls: dict = {}
    for day in days_to_run:
        tte = DAY_TTE[day]
        stdout, stderr = run_day(Path(ROOT / algo), day, match_mode, tte)
        print(f"--- Day {day} (TTE={tte}d, match={match_mode}) ---")
        print(stdout)
        if stderr.strip():
            print("[stderr]", stderr[-500:])
        for line in stdout.splitlines():
            if "Total profit:" in line:
                pnl_str = line.split("Total profit:")[-1].strip().replace(",", "")
                try:
                    day_pnls[day] = int(pnl_str)
                except ValueError:
                    day_pnls[day] = 0

    print("\n=== R4 PNL SUMMARY ===")
    total = 0
    for day in days_to_run:
        pnl = day_pnls.get(day, 0)
        total += pnl
        print(f"  Day {day}: {pnl:>10,}")
    if len(days_to_run) > 1:
        print(f"  {'TOTAL':>5}: {total:>10,}")


if __name__ == "__main__":
    main()
