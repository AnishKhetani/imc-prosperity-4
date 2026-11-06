import json

with open(r'.\logs\42455\42455.log') as f:
    data = json.load(f)

# Examine lambdaLog format in detail
logs = data['logs']
for i in [0, 1, 100, 500]:
    entry = logs[i]
    ll = entry['lambdaLog']
    sl = entry['sandboxLog']
    print(f'\n=== Log entry {i}, timestamp={entry["timestamp"]} ===')
    print(f'sandboxLog preview: {sl[:500] if sl else "empty"}')
    print(f'lambdaLog preview: {ll[:800] if ll else "empty"}')
