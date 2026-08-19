"""Targeted extraction of Hope's tariff_standards -- the real payer/pricing-
tier name table that corporate_super_bills.tariff_standard_id points to.
Needed to resolve corporate_patient_details.corporate_bill_id (-> a
corporate_super_bills row, not directly a corporates row) back to a real
payer name for the HMO ingestion pipeline.

Usage: python scripts/extract_tariff_standards.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from extractors.mysql_dump import parse_dump
from staging.sqlite_store import StagingStore

DUMP_PATH = str(
    Path(__file__).resolve().parent.parent / "Docs" / "NEw Dump" / "db_drmnigeria-20260125.sql.gz"
)

TARGET_TABLES = {"tariff_standards"}


def main() -> None:
    print(f"Streaming {DUMP_PATH} for tables: {sorted(TARGET_TABLES)}")
    t0 = time.time()
    data = parse_dump(DUMP_PATH, target_tables=TARGET_TABLES)
    print(f"Parse complete in {time.time() - t0:.0f}s")

    store = StagingStore()
    run_id = f"tariff_standards_{int(time.time())}"
    rows = data.get("tariff_standards", [])
    store.clear("hope_tariff_standards")
    count = store.write("hope_tariff_standards", rows, run_id=run_id)
    store.record_run("hope_tariff_standards", "dump", count, run_id=run_id)
    print(f"  tariff_standards -> raw_hope_tariff_standards: {count} rows staged")
    print("Done.")


if __name__ == "__main__":
    main()
