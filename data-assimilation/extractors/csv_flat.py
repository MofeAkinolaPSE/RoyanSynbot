"""CSV / Excel flat-file extractor.

Reads a folder of files where each filename (without extension) is treated as
the table name.  Supports .csv and .xlsx / .xls.

Usage:
    from extractors.csv_flat import extract_csv_folder
    data = extract_csv_folder("./hope_csvs")
    # data == {"patients": [{...}, ...], "appointments": [{...}, ...], ...}
"""
from __future__ import annotations

import os
from typing import Dict, List

import pandas as pd


def extract_csv_folder(folder: str) -> Dict[str, List[dict]]:
    """Read all CSV/Excel files in *folder*. Returns {table_name: [row_dict, ...]}."""
    result: Dict[str, List[dict]] = {}
    if not os.path.isdir(folder):
        raise FileNotFoundError(f"CSV folder not found: {folder}")

    for filename in os.listdir(folder):
        name, ext = os.path.splitext(filename)
        ext = ext.lower()
        if ext not in (".csv", ".xlsx", ".xls"):
            continue

        filepath = os.path.join(folder, filename)
        try:
            if ext == ".csv":
                df = pd.read_csv(filepath, dtype=str, keep_default_na=False, na_values=["NULL", "null", "\\N"])
            else:
                df = pd.read_excel(filepath, dtype=str, keep_default_na=False, na_values=["NULL", "null", "\\N"])

            df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
            rows = df.where(pd.notna(df), other=None).to_dict(orient="records")
            result[name.lower()] = rows
            print(f"  [csv] {filename}: {len(rows)} rows, columns: {list(df.columns)}")
        except Exception as exc:
            print(f"  [csv] WARNING: could not read {filename}: {exc}")

    return result
