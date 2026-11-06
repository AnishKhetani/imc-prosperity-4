"""Analyze platform log 276915."""
import json

with open(r".\logs\276915\276915.json", "r", encoding="utf-8") as f:
    d = json.load(f)

print("round:", d["round"])
print("status:", d["status"])
print("profit:", d["profit"])
print()

# Positions
pos = d["positions"]
print("positions type:", type(pos))
if isinstance(pos, dict):
    for k, v in pos.items():
        print(f"  {k}: {v}")
elif isinstance(pos, list):
    print(f"  len={len(pos)}")
    if pos:
        print(f"  first: {pos[0]}")
        print(f"  last:  {pos[-1]}")

print()

# Activities log
al = d["activitiesLog"]
print(f"activitiesLog: {len(al)} entries")
if al:
    print(f"  first: {str(al[0])[:300]}")
    print(f"  last:  {str(al[-1])[:300]}")

print()

# Graph log
gl = d["graphLog"]
print(f"graphLog type: {type(gl)}, len: {len(gl) if isinstance(gl, (list, str)) else 'N/A'}")

# Parse activities
if al and isinstance(al[0], str):
    # It's a string log — split by newlines
    lines = al if isinstance(al, list) else al.split("\n")
    print(f"\nActivities: {len(lines)} lines")
    # Show first few
    for line in lines[:5]:
        print(f"  {line[:200]}")
elif al and isinstance(al[0], dict):
    # Structured entries
    print(f"\nActivity keys: {list(al[0].keys())}")
    # Count by type
    from collections import Counter
    types = Counter(e.get("type", "unknown") for e in al)
    print(f"Activity types: {types}")
