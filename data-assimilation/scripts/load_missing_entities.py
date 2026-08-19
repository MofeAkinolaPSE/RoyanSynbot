"""Transform + load the 4 previously-empty entities (payments,
insurance_claims, dispensing, lab_results) from the tables staged by
extract_missing_entities.py.

Usage:
    python scripts/load_missing_entities.py --dry-run
    python scripts/load_missing_entities.py --execute
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from staging.sqlite_store import StagingStore
import transformers.dispensing as t_dispensing
import transformers.insurance_claims as t_insurance_claims
import transformers.lab_results as t_lab_results
import transformers.patients as t_patients
import transformers.payments as t_payments
from loaders.db_loader import (
    get_conn,
    load_dispensing,
    load_insurance_claims,
    load_lab_results,
    load_payments,
    log_run,
)


def _build_item_catalog(rows: list[dict]) -> dict[str, str]:
    catalog: dict[str, str] = {}
    for row in rows:
        raw = {k.lower(): v for k, v in row.items()}
        item_id = str(raw.get("id") or "").strip()
        if not item_id:
            continue
        name = (
            (raw.get("product_name") or "").strip()
            or (raw.get("name") or "").strip()
            or (raw.get("generic") or "").strip()
            or (raw.get("genericdrugname") or "").strip()
        )
        if name:
            catalog[item_id] = name
    return catalog


def _build_pid_canonical(store: StagingStore) -> dict[str, str]:
    """Hope keeps multiple patient rows per MRN (one per historical
    registration event); only the latest-per-MRN is loaded into
    royan_patients. Rows from other staged entities can carry any of
    those historical Hope patient ids, so they need remapping to the one
    canonical id that was actually loaded -- otherwise most direct
    patient_id lookups silently fail (confirmed: without this, only
    ~25% of payments resolved; with it, 99.999% do)."""
    patients_raw = store.read_latest_run("patients")
    patients_transformed = t_patients.transform(patients_raw)
    mrn_to_canonical = {p["mrn"]: p["external_id"] for p in patients_transformed}
    pid_canonical: dict[str, str] = {}
    for r in patients_raw:
        pk = str(r.get("id") or r.get("patientid") or "")
        mrn = str(r.get("patient_id") or "")
        if pk and mrn and mrn in mrn_to_canonical:
            pid_canonical[pk] = mrn_to_canonical[mrn]
    return pid_canonical


def _remap_patient_ids(rows: list[dict], pid_canonical: dict[str, str]) -> list[dict]:
    out = []
    for row in rows:
        old_val = str(row.get("patient_id") or "")
        canonical = pid_canonical.get(old_val)
        if canonical and canonical != old_val:
            row = {**row, "patient_id": canonical}
        out.append(row)
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    dry_run = args.dry_run

    store = StagingStore()

    print("Reading staged rows...")
    payments_raw = store.read_latest_run("hope_payments")
    claims_raw = store.read_latest_run("hope_claims")
    dispensing_raw = store.read_latest_run("hope_dispensing_lines")
    lab_results_raw = store.read_latest_run("hope_lab_results")
    catalog_raw = store.read_latest_run("hope_pharmacy_catalog")
    print(f"  payments: {len(payments_raw)}, claims: {len(claims_raw)}, "
          f"dispensing_lines: {len(dispensing_raw)}, lab_results: {len(lab_results_raw)}, "
          f"pharmacy_catalog: {len(catalog_raw)}")

    item_catalog = _build_item_catalog(catalog_raw)
    print(f"  resolved {len(item_catalog)} drug names from catalog")

    print("Building canonical patient-id remap (Hope has multiple rows per MRN)...")
    pid_canonical = _build_pid_canonical(store)
    print(f"  {len(pid_canonical)} entries -> {len(set(pid_canonical.values()))} canonical ids")
    payments_raw = _remap_patient_ids(payments_raw, pid_canonical)
    lab_results_raw = _remap_patient_ids(lab_results_raw, pid_canonical)

    print("\nTransforming...")
    payments = t_payments.transform(payments_raw)
    claims = t_insurance_claims.transform(claims_raw)
    dispensing = t_dispensing.transform(dispensing_raw, item_catalog=item_catalog)
    lab_results = t_lab_results.transform(lab_results_raw)
    print(f"  payments: {len(payments)} payloads ready ({len(payments_raw)} raw)")
    print(f"  insurance_claims: {len(claims)} payloads ready ({len(claims_raw)} raw)")
    print(f"  dispensing: {len(dispensing)} payloads ready ({len(dispensing_raw)} raw)")
    print(f"  lab_results: {len(lab_results)} payloads ready ({len(lab_results_raw)} raw)")

    conn = None
    if not dry_run:
        from config import DATABASE_URL
        conn = get_conn(DATABASE_URL)
        print("\nConnected to PostgreSQL.")

    print(f"\nLoading{' (DRY RUN)' if dry_run else ''}...")
    for entity, data, loader in [
        ("payments", payments, load_payments),
        ("insurance_claims", claims, load_insurance_claims),
        ("dispensing", dispensing, load_dispensing),
        ("lab_results", lab_results, load_lab_results),
    ]:
        seen, upserted = loader(conn, data, dry_run=dry_run)
        if conn and not dry_run:
            log_run(conn, entity, seen, upserted)
        print(f"  {entity}: {seen} seen, {upserted} {'would upsert' if dry_run else 'upserted'}")

    if conn:
        conn.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
