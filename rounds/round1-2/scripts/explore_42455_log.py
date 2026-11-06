import json

# The .log file is a JSON with additional fields including sandbox logs and trades
with open(r'.\logs\42455\42455.log') as f:
    data = json.load(f)

keys = list(data.keys())
print(f'Log keys: {keys}')

for k in keys:
    v = data[k]
    if isinstance(v, str):
        print(f'  {k}: str[{len(v)}]')
    elif isinstance(v, (int, float)):
        print(f'  {k}: {v}')
    elif isinstance(v, list):
        print(f'  {k}: list[{len(v)}]')
        if v and isinstance(v[0], dict):
            print(f'    first keys: {list(v[0].keys())}')
            print(f'    first: {v[0]}')
    elif isinstance(v, dict):
        print(f'  {k}: dict keys={list(v.keys())[:10]}')
    elif v is None:
        print(f'  {k}: None')

# Look for sandboxLog or tradeLog
if 'sandboxLog' in data:
    sl = data['sandboxLog']
    print(f'\nsandboxLog type={type(sl).__name__}')
    if isinstance(sl, str):
        print(f'  First 1000 chars: {sl[:1000]}')

if 'tradeHistory' in data:
    th = data['tradeHistory']
    print(f'\ntradeHistory: {type(th).__name__}')
