"""Full targeted extraction of the remaining Hope inventory-related tables
from the local dump, staged for analysis/loading without re-parsing the
685MB file again.

Usage: python scripts/extract_inventory_remainder.py
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
    "inventory_purchase_details",
    "inventory_purchase_item_details",
    "stock_adjustments",
    "stock_issue_details",
    "store_requisition_details",
}
ENTITY_MAP = {
    "inventory_purchase_details":      "hope_inv_purchase_details",
    "inventory_purchase_item_details": "hope_inv_purchase_item_details",
    "stock_adjustments":               "hope_stock_adjustments",
    "stock_issue_details":             "hope_stock_issue_details",
    "store_requisition_details":       "hope_store_requisition_details",
}


def main() -> None:
    print(f"Streaming {DUMP_PATH} for tables: {sorted(TARGET_TABLES)}")
    t0 = time.time()
    data = parse_dump(DUMP_PATH, target_tables=TARGET_TABLES)
    print(f"Parse complete in {time.time() - t0:.0f}s")

    store = StagingStore()
    run_id = f"inv_remainder_{int(time.time())}"

    for hope_table, entity in ENTITY_MAP.items():
        rows = data.get(hope_table, [])
        store.clear(entity)
        count = store.write(entity, rows, run_id=run_id)
        store.record_run(entity, "dump", count, run_id=run_id)
        print(f"  {hope_table} -> raw_{entity}: {count} rows staged")

    print("Done.")


if __name__ == "__main__":
    main()
