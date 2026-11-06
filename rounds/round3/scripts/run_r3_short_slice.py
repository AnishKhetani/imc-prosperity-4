"""
Simulate a 'platform-like' 1000-tick slice of day 2 for a trader file.

Log 365182 showed only ~1,000 ticks (ts 0..99900) where HYDROGEL drifted
10011 -> 9927 without time for mean-reversion. We replay just that slice.

Usage:
    python scripts/run_r3_short_slice.py trader_r3_v3.py    # default: day 2 first 1000t
    python scripts/run_r3_short_slice.py trader_r3_v3.py 1  # day 1 first 1000t
"""
import sys, os, csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = ROOT / "backtester_data" / "round3"

import prosperity3bt.data as p3_data
R3_LIMITS = {"HYDROGEL_PACK": 200, "VELVETFRUIT_EXTRACT": 200}
for k in [4000, 4500, 5000, 5100, 5200, 5300, 5400, 5500, 6000, 6500]:
    R3_LIMITS[f"VEV_{k}"] = 300
p3_data.LIMITS.update(R3_LIMITS)
import prosperity3bt.runner as p3_runner
p3_runner.LIMITS = p3_data.LIMITS


def truncate(src: Path, dst: Path, max_ts: int) -> None:
    with open(src, "r", newline="") as f:
        rdr = csv.reader(f, delimiter=";")
        rows = list(rdr)
    header, data = rows[0], rows[1:]
    ts_idx = header.index("timestamp")
    kept = [r for r in data if int(r[ts_idx]) <= max_ts]
    with open(dst, "w", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(header)
        w.writerows(kept)


def main():
    algo = sys.argv[1] if len(sys.argv) > 1 else "trader_r3_v3.py"
    day  = int(sys.argv[2]) if len(sys.argv) > 2 else 2
    max_ts = int(sys.argv[3]) if len(sys.argv) > 3 else 99900

    # Build truncated data dir
    tmp_root = ROOT / "backtester_data" / f"_slice_d{day}_ts{max_ts}"
    tmp_round = tmp_root / "round3"
    tmp_round.mkdir(parents=True, exist_ok=True)
    for kind in ("prices", "trades"):
        src = DATA_ROOT / f"{kind}_round_3_day_{day}.csv"
        dst = tmp_round / f"{kind}_round_3_day_{day}.csv"
        if src.exists():
            truncate(src, dst, max_ts)

    sys.argv = [
        "prosperity3bt", algo, f"3-{day}",
        "--data", str(tmp_root),
        "--match-trades", "worse",
        "--no-progress",
    ]
    from prosperity3bt.__main__ import main as bt_main
    bt_main()


if __name__ == "__main__":
    main()
