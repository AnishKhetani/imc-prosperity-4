"""Diagnostic: run BOTH old and new strategies on the same data and compare orders."""
import json, sys, os
sys.path.insert(0, r".")

# Read prices data
import pandas as pd

prices_dir = r".\round_data\ROUND_2"
# Find first prices file
for f in os.listdir(prices_dir):
    if f.startswith("prices_round_2_day_-1"):
        prices_file = os.path.join(prices_dir, f)
        break

df = pd.read_csv(prices_file, sep=";")
print(f"Loaded {len(df)} rows from {os.path.basename(prices_file)}")

# Check products
print(f"Products: {df['product'].unique()}")

# For each product, build the order book at tick 0
for product in ["ASH_COATED_OSMIUM", "INTARIAN_PEPPER_ROOT"]:
    tick = df[(df['product'] == product) & (df['timestamp'] == 0)]
    if tick.empty:
        tick = df[(df['product'] == product)].iloc[:1]
    
    print(f"\n{product} at timestamp {tick['timestamp'].iloc[0]}:")
    # Show all columns
    for col in tick.columns:
        print(f"  {col}: {tick[col].iloc[0]}")
