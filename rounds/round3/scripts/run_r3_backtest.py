"""
Run prosperity3bt backtester on our Prosperity 4 Round 3 data.

Monkey-patches the LIMITS dict to include R3 products:
  HYDROGEL_PACK=200, VELVETFRUIT_EXTRACT=200, VEV_*=300 each.

THE LIVE ROUND IS 1 DAY (day 3, TTE=5d at start, ~10k ticks).

Two modes:
  Default (3-day conservative sweep):
    * Runs all 3 historical days (days 0, 1, 2)
    * match-trades = worse  (only fills when we definitely cross the market)
    * TTE = 5 for all days  (live setting throughout)
    * Good for catching regressions across many scenarios

  --live (single-day live simulation):
    * Runs day 2 only (most recent historical day, closest proxy to live day 3)
    * match-trades = all  (fills every order we submit — prosperity3bt's most
      optimistic mode; approximates a live platform where bots sweep all quotes)
    * TTE = 5 (correct live setting — live round starts with 5d to expiry)
    * Use this to estimate actual live PnL

Usage:
  python scripts/run_r3_backtest.py <submission.py> [day] [--live]
      day: 0, 1, 2, or 'all' (default 'all'; ignored when --live)
      --live: single-day live simulation (day 2, better fills, TTE=5)
"""
import sys
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = ROOT / "backtester_data"

LIVE_TTE = 5   # live round always starts with 5 days to expiry


def run_day(algo: Path, day: int, match_mode: str, tte_days: int) -> tuple:
    """Run one day via a clean subprocess so LIMITS patch + IMC_TTE_DAYS env
    are isolated per invocation.  Returns (stdout, stderr) strings."""
    env = os.environ.copy()
    env["IMC_TTE_DAYS"] = str(tte_days)

    cmd = [
        sys.executable,
        str(Path(__file__)),
        str(algo), str(day),
        "--match-mode", match_mode,
        "--tte", str(tte_days),
        "--_subprocess",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if result.returncode != 0:
        print(result.stderr[-2000:], file=sys.stderr)
    return result.stdout, result.stderr


def _subprocess_main(algo: str, day: int, match_mode: str):
    """Actual backtester call — runs inside a subprocess where LIMITS and the
    IMC_TTE_DAYS env var are already set correctly for this day."""
    import prosperity3bt.data as p3_data

    R3_LIMITS = {"HYDROGEL_PACK": 200, "VELVETFRUIT_EXTRACT": 200}
    for k in [4000, 4500, 5000, 5100, 5200, 5300, 5400, 5500, 6000, 6500]:
        R3_LIMITS[f"VEV_{k}"] = 300
    p3_data.LIMITS.update(R3_LIMITS)

    import prosperity3bt.runner as p3_runner
    p3_runner.LIMITS = p3_data.LIMITS

    sys.argv = [
        "prosperity3bt", algo,
        f"3-{day}",
        "--data", str(DATA_ROOT),
        "--match-trades", match_mode,
        "--no-progress",
    ]
    from prosperity3bt.__main__ import main as bt_main
    bt_main()


def main():
    args = sys.argv[1:]

    # Sub-process mode (invoked internally by run_day())
    if "--_subprocess" in args:
        idx = args.index("--_subprocess")
        args = args[:idx]
        algo       = args[0]
        day        = int(args[1])
        match_mode = args[args.index("--match-mode") + 1]
        _subprocess_main(algo, day, match_mode)
        return

    # ---- User-facing entry ----
    algo      = args[0] if len(args) > 0 else "submission.py"
    live_mode = "--live" in args

    if live_mode:
        # Single day, better fills — simulate the live round
        days_to_run = [2]    # day 2 is the closest proxy for live day 3
        match_mode  = "all"
        print("\n*** LIVE SIMULATION MODE ***")
        print("    Day 2 only | TTE=5d | match=all (fills every order we submit)")
    else:
        day_arg    = next((a for a in args[1:] if not a.startswith("--")), "all")
        days_to_run = [0, 1, 2] if day_arg == "all" else [int(day_arg)]
        match_mode = "worse"
        print("\n--- Conservative sweep mode (all days, TTE=5, match=worse) ---")

    print(f"    Algorithm : {algo}\n")

    day_pnls: dict = {}
    for day in days_to_run:
        stdout, stderr = run_day(Path(ROOT / algo), day, match_mode, LIVE_TTE)
        print(f"--- Day {day} (TTE={LIVE_TTE}d, match={match_mode}) ---")
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

    print("\n=== PNL SUMMARY ===")
    total = 0
    for day in days_to_run:
        pnl = day_pnls.get(day, 0)
        total += pnl
        print(f"  Day {day}: {pnl:>10,}")
    if len(days_to_run) > 1:
        print(f"  {'TOTAL':>5}: {total:>10,}")


if __name__ == "__main__":
    main()
