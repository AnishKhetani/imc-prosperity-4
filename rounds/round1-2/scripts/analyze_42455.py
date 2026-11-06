import json
import csv
from collections import defaultdict, Counter

# Parse the platform JSON log
with open(r'.\logs\42455\42455.json') as f:
    data = json.load(f)

# Structure exploration
if isinstance(data, list):
    print(f'Top-level: list of {len(data)} items')
    if len(data) > 0:
        first = data[0]
        if isinstance(first, dict):
            print(f'First item keys: {list(first.keys())}')
elif isinstance(data, dict):
    print(f'Top-level keys: {list(data.keys())}')

# Try to find the sandbox logs structure
# Typically: list of dicts with timestamp, product info, orders, trades, etc.
def explore_item(item, prefix=''):
    if isinstance(item, dict):
        for k, v in item.items():
            if isinstance(v, (int, float, str, bool, type(None))):
                print(f'{prefix}{k}: {v}')
            elif isinstance(v, list):
                print(f'{prefix}{k}: list[{len(v)}]')
                if len(v) > 0 and isinstance(v[0], dict):
                    print(f'{prefix}  first: {list(v[0].keys())}')
            elif isinstance(v, dict):
                print(f'{prefix}{k}: dict[{len(v)}]')
                if len(v) <= 5:
                    for k2, v2 in v.items():
                        if isinstance(v2, (int, float, str)):
                            print(f'{prefix}  {k2}: {v2}')
                        elif isinstance(v2, dict):
                            print(f'{prefix}  {k2}: dict[{len(v2)}] keys={list(v2.keys())[:5]}')
                        elif isinstance(v2, list):
                            print(f'{prefix}  {k2}: list[{len(v2)}]')

if isinstance(data, list) and len(data) > 0:
    print('\n=== FIRST ITEM ===')
    explore_item(data[0])
    print('\n=== LAST ITEM ===')
    explore_item(data[-1])
elif isinstance(data, dict):
    explore_item(data)
