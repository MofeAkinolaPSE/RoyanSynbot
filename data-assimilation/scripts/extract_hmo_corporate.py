"""Targeted extraction of Hope's HMO/corporate/insurance-related tables,
staged for the HMO ingestion pipeline.

Hope calls HMOs "corporates" -- `corporates` is the real payer master list,
`corporate_patient_details` is the real patient<->HMO-bill link (the gap the
user flagged: royan_hmos exists but nothing links a patient or a bill to
one). `new_insurances` is a separate, much more detailed per-patient
subscriber/insurance record. `insurance_companies` also exists but its
cached scan sample looked like vendor demo data (Indian city/address on an
"Orient" insurer) rather than real Hope data -- included here anyway so
that can be confirmed for real instead of guessed from a cached sample.

Usage: python scripts/extract_hmo_corporate.py
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
    "corporates",
    "corporate_patient_details",
    "corporate_locations",
    "corporate_sublocations",
    "corporate_super_bills",
    "corporate_super_bill_lists",
    "corporate_lab_rates",
    "insurance_companies",
    "insurance_types",
    "new_insurances",
}
ENTITY_MAP = {
    "corporates":                   "hope_corporates",
    "corporate_patient_details":    "hope_corporate_patient_details",
    "corporate_locations":          "hope_corporate_locations",
    "corporate_sublocations":       "hope_corporate_sublocations",
    "corporate_super_bills":        "hope_corporate_super_bills",
    "corporate_super_bill_lists":   "hope_corporate_super_bill_lists",
    "corporate_lab_rates":          "hope_corporate_lab_rates",
    "insurance_companies":          "hope_insurance_companies",
    "insurance_types":              "hope_insurance_types",
    "new_insurances":               "hope_new_insurances",
}


def main() -> None:
    print(f"Streaming {DUMP_PATH} for tables: {sorted(TARGET_TABLES)}")
    t0 = time.time()
    data = parse_dump(DUMP_PATH, target_tables=TARGET_TABLES)
    print(f"Parse complete in {time.time() - t0:.0f}s")

    store = StagingStore()
    run_id = f"hmo_corporate_{int(time.time())}"

    for hope_table, entity in ENTITY_MAP.items():
        rows = data.get(hope_table, [])
        store.clear(entity)
        count = store.write(entity, rows, run_id=run_id)
        store.record_run(entity, "dump", count, run_id=run_id)
        print(f"  {hope_table} -> raw_{entity}: {count} rows staged")

    print("Done.")


if __name__ == "__main__":
    main()
