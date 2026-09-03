#!/usr/bin/env python3
"""Check for the full dataset and report its fingerprint.

The dataset is not redistributed with this repository, so this script cannot
download it for you. It tells you where to put the file and validates it once
it is in place.

Usage:
    python scripts/download_data.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

SOURCE_VIDEO = "https://github.com/aniket2404/bank-loan-report-analytics"
EXPECTED_ROWS = 38_576
EXPECTED_FUNDED = 435_757_075
EXPECTED_RECEIVED = 473_070_933


def main() -> int:
    target = ROOT / "data" / "raw" / "financial_loan.csv"

    if not target.exists():
        print("Full dataset not found.\n")
        print(f"Expected location:\n  {target}\n")
        print("How to get it:")
        print(f"  1. Open the source standard: {SOURCE_VIDEO}")
        print("  2. Follow the 'Data Download' Google Drive link in its description")
        print("  3. Download financial_loan.csv and save it to the path above\n")
        print("Meanwhile, everything runs against the bundled 600-row sample:")
        print("  python -m bank_loan_report --sample report")
        return 1

    import pandas as pd

    df = pd.read_csv(target)
    rows, cols = df.shape
    funded = int(df["loan_amount"].sum())
    received = int(df["total_payment"].sum())

    print(f"Found {target}")
    print(f"  rows      : {rows:,}  (expected {EXPECTED_ROWS:,})")
    print(f"  columns   : {cols}  (expected 24)")
    print(f"  funded    : {funded:,}  (expected {EXPECTED_FUNDED:,})")
    print(f"  received  : {received:,}  (expected {EXPECTED_RECEIVED:,})")

    ok = (
        rows == EXPECTED_ROWS
        and cols == 24
        and funded == EXPECTED_FUNDED
        and received == EXPECTED_RECEIVED
    )
    print("\nDataset verified." if ok else "\nWarning: fingerprint does not match.")
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
