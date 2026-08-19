"""One-off targeted extraction of the real Hope source tables for the 4
entities that were never correctly wired (payments, insurance_claims,
dispensing, lab_results) — plus the pharmacy item catalog used to resolve
real drug names.

Root cause (see conversation): the original TABLE_HINTS-driven extraction
picked the wrong (or an empty) source table for each of these via
"first hint that exists in the dump wins" — e.g. `pharmacy_sales_bills`
(a billing/sale header with no drug fields) instead of the real per-line
detail table. This script bypasses TABLE_HINTS entirely and extracts the
exact real tables identified by inspecting data-assimilation/scan_reports/
db_drmnigeria_schema.json + candidates.json against the local full dump.

Writes to the existing staging/hope_staging.db under new entity names so
the 654MB dump is only streamed once.
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
    "service_cash_payments",
    "sub_claims",
    "pharmacy_sales_bill_details",
    "laboratory_results",
    "pharmacy_items",
}

# Maps Hope table name -> staging entity name
ENTITY_MAP = {
    "service_cash_payments":        "hope_payments",
    "sub_claims":                   "hope_claims",
    "pharmacy_sales_bill_details":  "hope_dispensing_lines",
    "laboratory_results":           "hope_lab_results",
    "pharmacy_items":               "hope_pharmacy_catalog",
}


def main() -> None:
    if not Path(DUMP_PATH).exists():
        print(f"ERROR: dump not found at {DUMP_PATH}")
        sys.exit(1)

    print(f"Streaming {DUMP_PATH} for tables: {sorted(TARGET_TABLES)}")
    t0 = time.time()
    data = parse_dump(DUMP_PATH, target_tables=TARGET_TABLES)
    print(f"Parse complete in {time.time() - t0:.0f}s")

    store = StagingStore()
    run_id = f"missing_entities_{int(time.time())}"

    for hope_table, entity in ENTITY_MAP.items():
        rows = data.get(hope_table, [])
        store.clear(entity)
        count = store.write(entity, rows, run_id=run_id)
        store.record_run(entity, "dump", count, run_id=run_id)
        print(f"  {hope_table} -> raw_{entity}: {count} rows staged")

    print("Done.")


if __name__ == "__main__":
    main()
