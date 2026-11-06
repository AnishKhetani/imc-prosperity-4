"""Per-product PnL breakdown for a backtest run — works with prosperity3bt output logs."""
import subprocess, sys, io, csv, json
from pathlib import Path
from collections import defaultdict

trader = sys.argv[1] if len(sys.argv) > 1 else 'trader_r3_v7.py'
day    = sys.argv[2] if len(sys.argv) > 2 else '0'

# Run backtester and capture JSON output
# prosperity3bt writes a JSON result to stdout with the activities log embedded
import prosperity3bt.data as p3_data
R3_LIMITS = {"HYDROGEL_PACK": 200, "VELVETFRUIT_EXTRACT": 200}
for k in [4000, 4500, 5000, 5100, 5200, 5300, 5400, 5500, 6000, 6500]:
    R3_LIMITS[f"VEV_{k}"] = 300
p3_data.LIMITS.update(R3_LIMITS)
import prosperity3bt.runner as p3_runner
p3_runner.LIMITS = p3_data.LIMITS

DATA_ROOT = Path('backtester_data')
import sys as _sys
old_argv = _sys.argv[:]
_sys.argv = [
    'prosperity3bt', trader, f'3-{day}',
    '--data', str(DATA_ROOT),
    '--match-trades', 'worse',
    '--no-progress',
    '--print',
]

from io import StringIO
old_stdout = _sys.stdout
_sys.stdout = buf = StringIO()
try:
    from prosperity3bt.__main__ import main as bt_main
    bt_main()
except SystemExit:
    pass
finally:
    _sys.stdout = old_stdout
    _sys.argv = old_argv

output = buf.getvalue()

# Parse per-product lines from the output (prosperity3bt prints product PnL)
print(f'\n=== PER-PRODUCT PnL: {trader} day={day} ===')
for line in output.split('\n'):
    if any(p in line for p in ['HYDROGEL', 'VELVET', 'VEV_', 'Total']):
        print(line)
