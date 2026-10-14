"""Second follow-up extraction from the complete-506-table audit (2026-08-21):
the tables found in the final naming-pattern sweep, after the first 26-table
batch (extract_phase_a2_audit_findings.py) already landed.

Usage: python scripts/extract_phase_a3_audit_findings.py
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
    # Real per-service cost/price detail (cost_price column -- unit-cost candidate)
    "tariff_amounts",
    # Per-ward-stay billing detail
    "ward_patient_services",
    # Real lab test catalog (distinct from already-loaded lab orders)
    "laboratories", "laboratory_categories",
    # Ward-level stock usage
    "direct_consumptions",
    # Real immunization administration records (typo'd table is the real one)
    "imunizations",
    # Vitals history
    "bmi_results", "bmi_bp_results",
    # Pharmacy sales / dispense pricing
    "pharmacy_sales_bills", "pharmacy_item_details", "pharmacy_tariff_amounts",
}

ENTITY_MAP = {
    "tariff_amounts":          "hope_tariff_amounts",
    "ward_patient_services":   "hope_ward_patient_services",
    "laboratories":            "hope_laboratories",
    "laboratory_categories":   "hope_laboratory_categories",
    "direct_consumptions":     "hope_direct_consumptions",
    "imunizations":            "hope_imunizations",
    "bmi_results":             "hope_bmi_results",
    "bmi_bp_results":          "hope_bmi_bp_results",
    "pharmacy_sales_bills":    "hope_pharmacy_sales_bills",
    "pharmacy_item_details":   "hope_pharmacy_item_details",
    "pharmacy_tariff_amounts": "hope_pharmacy_tariff_amounts",
}


def main() -> None:
    print(f"Streaming {DUMP_PATH} for {len(TARGET_TABLES)} tables")
    t0 = time.time()
    data = parse_dump(DUMP_PATH, target_tables=TARGET_TABLES)
    print(f"Parse complete in {time.time() - t0:.0f}s")

    store = StagingStore()
    run_id = f"phase_a3_audit_{int(time.time())}"

    for hope_table, entity in ENTITY_MAP.items():
        rows = data.get(hope_table, [])
        store.clear(entity)
        count = store.write(entity, rows, run_id=run_id)
        store.record_run(entity, "dump", count, run_id=run_id)
        print(f"  {hope_table} -> raw_{entity}: {count} rows staged")

    print("Done.")


if __name__ == "__main__":
    main()
