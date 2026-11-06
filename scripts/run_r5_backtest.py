"""
Round-5 wrapper around prosperity3bt.

Monkey-patches LIMITS to add all 50 R5 products with limit=10, points data
at backtester_data/round5/, and exposes a clean entrypoint that prints:

  ROUND5_TOTAL_PROFIT: <int>
  ROUND5_PER_PRODUCT_PNL: <json {product: pnl}>
  ROUND5_BREACHES: <int>

Usage:
  python scripts/run_r5_backtest.py [algo.py] [day|all] [--match worse|all|none]
"""
from __future__ import annotations
import json
import re
import sys
import io
import contextlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = ROOT / "backtester_data"

R5_GROUPS = {
    "GALAXY_SOUNDS": ["GALAXY_SOUNDS_BLACK_HOLES", "GALAXY_SOUNDS_DARK_MATTER",
                       "GALAXY_SOUNDS_PLANETARY_RINGS", "GALAXY_SOUNDS_SOLAR_FLAMES",
                       "GALAXY_SOUNDS_SOLAR_WINDS"],
    "MICROCHIP": ["MICROCHIP_CIRCLE", "MICROCHIP_OVAL", "MICROCHIP_RECTANGLE",
                   "MICROCHIP_SQUARE", "MICROCHIP_TRIANGLE"],
    "OXYGEN_SHAKE": ["OXYGEN_SHAKE_CHOCOLATE", "OXYGEN_SHAKE_EVENING_BREATH",
                      "OXYGEN_SHAKE_GARLIC", "OXYGEN_SHAKE_MINT",
                      "OXYGEN_SHAKE_MORNING_BREATH"],
    "PANEL": ["PANEL_1X2", "PANEL_1X4", "PANEL_2X2", "PANEL_2X4", "PANEL_4X4"],
    "PEBBLES": ["PEBBLES_XS", "PEBBLES_S", "PEBBLES_M", "PEBBLES_L", "PEBBLES_XL"],
    "ROBOT": ["ROBOT_DISHES", "ROBOT_IRONING", "ROBOT_LAUNDRY",
               "ROBOT_MOPPING", "ROBOT_VACUUMING"],
    "SLEEP_POD": ["SLEEP_POD_COTTON", "SLEEP_POD_LAMB_WOOL", "SLEEP_POD_NYLON",
                   "SLEEP_POD_POLYESTER", "SLEEP_POD_SUEDE"],
    "SNACKPACK": ["SNACKPACK_CHOCOLATE", "SNACKPACK_PISTACHIO", "SNACKPACK_RASPBERRY",
                   "SNACKPACK_STRAWBERRY", "SNACKPACK_VANILLA"],
    "TRANSLATOR": ["TRANSLATOR_ASTRO_BLACK", "TRANSLATOR_ECLIPSE_CHARCOAL",
                    "TRANSLATOR_GRAPHITE_MIST", "TRANSLATOR_SPACE_GRAY",
                    "TRANSLATOR_VOID_BLUE"],
    "UV_VISOR": ["UV_VISOR_AMBER", "UV_VISOR_MAGENTA", "UV_VISOR_ORANGE",
                  "UV_VISOR_RED", "UV_VISOR_YELLOW"],
}
R5_ALL = [s for g in R5_GROUPS.values() for s in g]


def patch_limits():
    import prosperity3bt.data as d
    import prosperity3bt.runner as r
    for s in R5_ALL:
        d.LIMITS[s] = 10
    # runner.py imports LIMITS by name so patch already lives there


def run(algo: str, days: list[int], match: str = "worse"):
    patch_limits()
    sys.path.insert(0, str(ROOT))
    sys.argv = [
        "prosperity3bt", str(ROOT / algo),
        *[f"5-{d}" for d in days],
        "--data", str(DATA_ROOT),
        "--match-trades", match,
        "--no-progress",
        "--no-out",
        "--merge-pnl",
    ]
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        from prosperity3bt.__main__ import main
        try:
            main()
        except SystemExit:
            pass
    out = buf.getvalue()
    sys.stdout.write(out)
    return out


def parse(out: str):
    # Total profit line: "Total profit: ..."
    total = None
    per_product = {}
    for line in out.splitlines():
        m = re.search(r"Total profit:\s*([-\d,]+)", line)
        if m:
            total = int(m.group(1).replace(",", ""))
        m = re.match(r"\s*([A-Z][A-Z0-9_]+):\s*([-\d,]+)", line)
        if m and m.group(1) in R5_ALL:
            per_product[m.group(1)] = int(m.group(2).replace(",", ""))
    breaches = sum(1 for ln in out.splitlines() if "exceeded limit" in ln)
    return total, per_product, breaches


def main():
    args = sys.argv[1:]
    algo = args[0] if args else "submission.py"
    day_arg = args[1] if len(args) > 1 else "all"
    match = "worse"
    if "--match" in args:
        match = args[args.index("--match") + 1]
    days = [2, 3, 4] if day_arg == "all" else [int(day_arg)]
    out = run(algo, days, match)
    total, per_product, breaches = parse(out)
    print(f"\nROUND5_TOTAL_PROFIT: {total}")
    print(f"ROUND5_BREACHES: {breaches}")
    print(f"ROUND5_PER_PRODUCT_PNL: {json.dumps(per_product)}")


if __name__ == "__main__":
    main()
