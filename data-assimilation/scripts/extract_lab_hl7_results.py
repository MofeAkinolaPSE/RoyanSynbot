"""Targeted extraction of Hope's laboratory_hl7_results (the real per-analyte
HL7 result rows -- e.g. a CBC panel is 1 laboratory_results row with ~7
laboratory_hl7_results child rows) + laboratory_parameters (id -> analyte
name/unit lookup), staged for the lab-results ingestion pipeline.

laboratory_hl7_results carries its own laboratory_test_order_id column
directly (confirmed via schema inspection), matching royan_lab_orders.external_id
-- so it does not need to route through laboratory_results at all.

Usage: python scripts/extract_lab_hl7_results.py
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

TARGET_TABLES = {
    "laboratory_hl7_results",
    "laboratory_parameters",
}
ENTITY_MAP = {
    "laboratory_hl7_results": "hope_lab_hl7_results",
    "laboratory_parameters":  "hope_lab_parameters",
}


def main() -> None:
    print(f"Streaming {DUMP_PATH} for tables: {sorted(TARGET_TABLES)}")
    t0 = time.time()
    data = parse_dump(DUMP_PATH, target_tables=TARGET_TABLES)
    print(f"Parse complete in {time.time() - t0:.0f}s")

    store = StagingStore()
    run_id = f"lab_hl7_{int(time.time())}"

    for hope_table, entity in ENTITY_MAP.items():
        rows = data.get(hope_table, [])
        store.clear(entity)
        count = store.write(entity, rows, run_id=run_id)
        store.record_run(entity, "dump", count, run_id=run_id)
        print(f"  {hope_table} -> raw_{entity}: {count} rows staged")

    print("Done.")


if __name__ == "__main__":
    main()
