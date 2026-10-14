"""Combined extraction for the complete-506-table audit follow-up
(2026-08-21): every table the audit identified as real, substantial, and
not yet loaded -- staged in one dump pass so each can be content-verified
and (where real) piped into its own transformer/loader without paying the
full-file scan cost again.

Usage: python scripts/extract_phase_a2_audit_findings.py
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
    # Third template/macro system (SmartPhrase-style dot phrases)
    "smart_phrases", "smart_phrase_multiple",
    # ICU/ward progress notes w/ vitals + sign/unsign/addendum audit trail
    "progresstbls",
    # Obstetric history
    "lmp_records",
    # Person/guarantor/guardian family -- relationship to royan_patients TBD
    "persons", "guarantors", "guardians",
    # Financial / billing (major finding -- payments.py wrongly assumed billings is empty)
    "billings", "final_billings", "tariff_lists",
    "purchase_orders", "purchase_order_items",
    "voucher_entries", "voucher_payments", "account_receipts",
    "discount_requests", "settlement_billings", "patient_cards",
    # ADT / operational
    "ward_patients", "beds", "rooms", "doctor_chambers",
    # Patient documents / misc clinical
    "patient_documents", "patient_profiles", "review_patient_details",
    "medication_administering_records",
}

ENTITY_MAP = {
    "smart_phrases":                    "hope_smart_phrases",
    "smart_phrase_multiple":            "hope_smart_phrase_multiple",
    "progresstbls":                     "hope_progresstbls",
    "lmp_records":                      "hope_lmp_records",
    "persons":                          "hope_persons",
    "guarantors":                       "hope_guarantors",
    "guardians":                        "hope_guardians",
    "billings":                         "hope_billings",
    "final_billings":                   "hope_final_billings",
    "tariff_lists":                     "hope_tariff_lists",
    "purchase_orders":                  "hope_purchase_orders",
    "purchase_order_items":             "hope_purchase_order_items",
    "voucher_entries":                  "hope_voucher_entries",
    "voucher_payments":                 "hope_voucher_payments",
    "account_receipts":                 "hope_account_receipts",
    "discount_requests":                "hope_discount_requests",
    "settlement_billings":              "hope_settlement_billings",
    "patient_cards":                    "hope_patient_cards",
    "ward_patients":                    "hope_ward_patients",
    "beds":                             "hope_beds",
    "rooms":                            "hope_rooms",
    "doctor_chambers":                  "hope_doctor_chambers",
    "patient_documents":                "hope_patient_documents",
    "patient_profiles":                 "hope_patient_profiles",
    "review_patient_details":           "hope_review_patient_details",
    "medication_administering_records": "hope_medication_administering_records",
}


def main() -> None:
    print(f"Streaming {DUMP_PATH} for {len(TARGET_TABLES)} tables")
    t0 = time.time()
    data = parse_dump(DUMP_PATH, target_tables=TARGET_TABLES)
    print(f"Parse complete in {time.time() - t0:.0f}s")

    store = StagingStore()
    run_id = f"phase_a2_audit_{int(time.time())}"

    for hope_table, entity in ENTITY_MAP.items():
        rows = data.get(hope_table, [])
        store.clear(entity)
        count = store.write(entity, rows, run_id=run_id)
        store.record_run(entity, "dump", count, run_id=run_id)
        print(f"  {hope_table} -> raw_{entity}: {count} rows staged")

    print("Done.")


if __name__ == "__main__":
    main()
