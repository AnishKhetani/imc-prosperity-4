"""
setup_data.py — Copy P4 tutorial CSVs into the directory structure prosperity3bt expects.

prosperity3bt expects:
    data_root/
        round{N}/
            prices_round_{N}_day_{D}.csv
            trades_round_{N}_day_{D}.csv
            observations_round_{N}_day_{D}.csv  (optional)

Our P4 tutorial data is already in the correct format (semicolon-delimited,
same column layout). We just need to copy/organize into the right directory tree.
"""

import shutil
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
BACKTESTER_DIR = PROJECT_ROOT / "backtester"

# Source: tutorial data location
TUTORIAL_SRC = PROJECT_ROOT / "tutorial-round" / "data" / "TUTORIAL_ROUND_1"

# Destination: prosperity3bt-compatible layout
DATA_DEST = BACKTESTER_DIR / "data" / "tutorial"


def setup_tutorial_data():
    """Copy tutorial CSVs into prosperity3bt's expected directory structure."""
    if not TUTORIAL_SRC.is_dir():
        print(f"Error: Tutorial data not found at {TUTORIAL_SRC}")
        print("Make sure the tutorial-round/data/TUTORIAL_ROUND_1/ directory exists.")
        return False

    # Find all CSV files and determine rounds
    csv_files = list(TUTORIAL_SRC.glob("*.csv"))
    if not csv_files:
        print(f"No CSV files found in {TUTORIAL_SRC}")
        return False

    print(f"Found {len(csv_files)} CSV files in tutorial data")

    # Parse round numbers and create directories
    for csv_file in csv_files:
        name = csv_file.name
        # Extract round number from filename like prices_round_0_day_-2.csv
        parts = name.split("_")
        try:
            round_idx = parts.index("round")
            round_num = parts[round_idx + 1]
        except (ValueError, IndexError):
            print(f"  Skipping {name} — can't parse round number")
            continue

        round_dir = DATA_DEST / f"round{round_num}"
        round_dir.mkdir(parents=True, exist_ok=True)

        dest_file = round_dir / name
        shutil.copy2(csv_file, dest_file)
        print(f"  {name} -> {dest_file.relative_to(PROJECT_ROOT)}")

    print(f"\nData setup complete: {DATA_DEST}")
    return True


if __name__ == "__main__":
    success = setup_tutorial_data()
    if not success:
        exit(1)
