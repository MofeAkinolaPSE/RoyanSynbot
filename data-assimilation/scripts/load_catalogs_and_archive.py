"""Final Phase A3 loader: radiology catalog, surgery catalog, and the
generic Hope reference archive.

The archive sweeps up EVERY staged Hope entity that does not already have a
proper target table, so nothing extracted from the dump is left unloaded.
ALREADY_LOADED below lists the entities that do have real targets; anything
staged and not in that set gets archived as jsonb.

Erring toward archiving is deliberate: archiving something already loaded
is harmless duplication inside an explicitly-named archive table, whereas
omitting something is silent data loss.

Usage:
    python scripts/load_catalogs_and_archive.py --dry-run
    python scripts/load_catalogs_and_archive.py --execute
"""
from __future__ import annotations

import argparse
import logging
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

from staging.sqlite_store import StagingStore
from transformers.catalogs_and_archive import (
    transform_radiology_catalog, transform_surgery_catalog, transform_reference_archive,
)
from loaders.db_loader import get_conn, load_generic, log_run

# Staged entities that already have a real target table in synbot_health.
ALREADY_LOADED = {
    # core clinical
    "patients", "persons", "doctors", "departments", "locations",
    "notes", "nurse_notes", "shift_notes", "progresstbls", "patient_profiles",
    "note_diagnosis", "diagnoses", "diagnosis_masters", "allergy_masters",
    "discharge_details", "imunizations", "observation_charts", "lmp_records",
    # labs
    "lab", "lab_results", "lab_hl7_results", "lab_parameters",
    "laboratories", "laboratory_categories",
    # radiology
    "radiology_results", "radiology_reports", "radiology_templates",
    "radiology_template_texts", "radiology_test_orders", "radiologies",
    # pharmacy / inventory
    "pharmacy", "pharmacy_sales_bills", "pharmacy_catalog", "dispensing_lines",
    "purchase_orders", "purchase_order_items", "direct_consumptions",
    "inv_purchase_details", "inv_purchase_item_details",
    "stock_adjustments", "stock_issue_details", "store_requisition_details",
    # templates
    "note_templates", "note_template_texts", "doctor_templates",
    "doctor_template_texts", "templates", "template_categories",
    "template_sub_categories", "template_type_contents",
    "orderset_masters", "orderset_category_mappings", "order_subcategories",
    "order_categories", "smart_phrases", "smart_phrase_multiple",
    # vitals / flowsheet
    "bmi_results", "bmi_bp_results", "review_patient_details",
    "review_categories", "review_sub_categories", "review_sub_categories_options",
    # wards
    "ward_patients", "wards", "rooms", "beds", "ward_patient_services",
    # finance
    "payments", "billings", "final_billings", "tariff_lists", "tariff_amounts",
    "tariff_standards", "account_receipts", "voucher_payments", "voucher_entries",
    "patient_cards", "discount_requests", "settlement_billings",
    # insurance / HMO
    "insurance_companies", "insurance_types", "new_insurances", "claims",
    "corporate_patient_details", "corporate_super_bills", "corporate_super_bill_lists",
    "corporate_lab_rates", "corporate_locations", "corporate_sublocations", "corporates",
    # ops
    "patient_documents", "doctor_chambers", "medication_administering_records",
    "surgeries", "surgery_categories", "surgery_subcategories",
    # confirmed empty shells -- deliberately not archived
    "guarantors", "guardians",
}


def _staged_entities() -> list[str]:
    con = sqlite3.connect("staging/hope_staging.db")
    cur = con.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'raw_hope_%'")
    out = []
    for (t,) in cur.fetchall():
        cur.execute(f'SELECT COUNT(*) FROM "{t}"')
        if cur.fetchone()[0] > 0:
            out.append(t[len("raw_hope_"):])
    con.close()
    return sorted(out)


def main() -> None:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    dry_run = args.dry_run

    store = StagingStore()
    R = store.read_latest_run

    conn = None
    if not dry_run:
        from config import DATABASE_URL
        conn = get_conn(DATABASE_URL)
        print("Connected to PostgreSQL.\n")

    # 1. Radiology catalog
    rad = transform_radiology_catalog(R("hope_radiologies"))
    seen, up = load_generic(conn, "royan_radiology_catalog", rad, dry_run=dry_run, require_patient=False)
    if conn and not dry_run:
        log_run(conn, "radiology_catalog", seen, up)
    print(f"radiology_catalog: {seen:,} seen, {up:,} {'would upsert' if dry_run else 'upserted'}")

    # 2. Surgery catalog
    surg = transform_surgery_catalog(
        R("hope_surgeries"), R("hope_surgery_categories"), R("hope_surgery_subcategories"),
    )
    seen, up = load_generic(conn, "royan_surgery_catalog", surg, dry_run=dry_run, require_patient=False)
    if conn and not dry_run:
        log_run(conn, "surgery_catalog", seen, up)
    print(f"surgery_catalog: {seen:,} seen, {up:,} {'would upsert' if dry_run else 'upserted'}")

    # 3. Reference archive for everything else
    to_archive = [e for e in _staged_entities() if e not in ALREADY_LOADED]
    print(f"\nArchiving {len(to_archive)} remaining staged entities:")

    total_seen = total_up = 0
    for entity in to_archive:
        rows = R(f"hope_{entity}")
        if not rows:
            continue
        payloads = transform_reference_archive(entity, rows)
        seen, up = load_generic(
            conn, "royan_hope_reference_archive", payloads,
            dry_run=dry_run, require_patient=False,
        )
        total_seen += seen
        total_up += up
        print(f"  {entity:38s} {up if not dry_run else seen:>8,} / {seen:>8,}")

    print(f"\nreference_archive TOTAL: {total_seen:,} seen, "
          f"{total_up:,} {'would upsert' if dry_run else 'upserted'}")

    if conn:
        conn.close()


if __name__ == "__main__":
    main()
