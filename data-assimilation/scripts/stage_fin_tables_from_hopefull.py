"""One-pass staging of the Hope tables the books pipeline (fin_hope_charges /
fin_hope_payers) needs, parsed from the latest complete extract hopefull.sql.gz.

The clinical ETL only stages patients/appointments/admissions/lab/pharmacy/billing.
hope_charges.load_charges additionally reads:
  raw_hope_pharmacy_sales_bills, raw_hope_radiology_test_orders,
  raw_hope_ward_patient_services, raw_hope_tariff_lists,
  raw_hope_service_categories, raw_hope_laboratories, raw_hope_radiologies
and load_payers reads raw_hope_tariff_standards.

StagingStore.write("hope_<t>", rows) -> table raw_hope_<t>, rows stored as JSON
in a `data` column (same format _rows()/_names() decode).

Usage: python scripts/stage_fin_tables_from_hopefull.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from extractors.mysql_dump import parse_dump
from staging.sqlite_store import StagingStore

DUMP_PATH = str(
    Path(__file__).resolve().parent.parent / "datadump" / "latestdata" / "hopefull.sql.gz"
)

# Hope source table name -> staging entity ("hope_" + name -> raw_hope_<name>)
TARGET_TABLES = {
    "tariff_standards",
    "tariff_lists",
    "service_categories",
    "laboratories",
    "radiologies",
    "pharmacy_sales_bills",
    "radiology_test_orders",
    "ward_patient_services",
}


def main() -> None:
    if not Path(DUMP_PATH).exists():
        print(f"ERROR: dump not found at {DUMP_PATH}")
        sys.exit(1)
    print(f"Streaming {DUMP_PATH}")
    print(f"Targeting {len(TARGET_TABLES)} tables: {sorted(TARGET_TABLES)}")
    t0 = time.time()
    data = parse_dump(DUMP_PATH, target_tables=TARGET_TABLES)
    print(f"Parse complete in {time.time() - t0:.0f}s")

    store = StagingStore()
    run_id = f"fin_stage_{int(time.time())}"
    total = 0
    for t in sorted(TARGET_TABLES):
        entity = f"hope_{t}"
        rows = data.get(t, [])
        store.clear(entity)
        count = store.write(entity, rows, run_id=run_id)
        store.record_run(entity, "dump", count, run_id=run_id)
        total += count
        flag = "" if count else "   <-- EMPTY (table name may differ in dump)"
        print(f"  {t:28s} -> raw_{entity}: {count:>8,} rows{flag}")
    print(f"Done. {total:,} rows staged across {len(TARGET_TABLES)} tables.")


if __name__ == "__main__":
    main()
