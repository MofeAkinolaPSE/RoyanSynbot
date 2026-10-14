"""Phase A3 ("finish the job") combined loader -- every remaining real Hope
table that was already staged, loaded in one pass.

  ward_patient_services -> royan_ward_service_charges
  patient_documents     -> royan_patient_documents
  direct_consumptions   -> royan_ward_consumption
  doctor_chambers       -> royan_doctor_schedule_blocks
  medication_administering_records -> royan_medication_administration
  patient_profiles      -> royan_encounter_notes (note_type='nursing')
  account_receipts + voucher_payments -> royan_account_receipts
  voucher_entries       -> royan_voucher_entries
  patient_cards         -> royan_patient_card_transactions
  discount_requests     -> royan_discount_requests
  settlement_billings   -> royan_settlement_billings

Applies the canonical patient-id remap to every patient-linked stream
(see load_nursing_notes.py -- without it, historical Hope tables resolve
at only ~10-25% because Hope keeps multiple patient rows per MRN).

Usage:
    python scripts/load_phase_a3.py --dry-run
    python scripts/load_phase_a3.py --execute
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# db_loader logs per-row skips at WARNING via _exec_with_savepoint. Without
# this the first A3 run lost all 749 doctor_schedule_blocks rows completely
# silently -- the warnings were emitted but nothing was listening.
logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

from staging.sqlite_store import StagingStore
import transformers.patients as t_patients
from transformers import ward_services_and_ops as ops
from transformers import accounting_ledger as acct
from loaders.db_loader import get_conn, load_generic, load_encounter_notes, log_run


def _build_pid_canonical(store: StagingStore) -> dict[str, str]:
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


def _remap(rows: list[dict], pid_canonical: dict[str, str]) -> list[dict]:
    out = []
    for row in rows:
        old = str(row.get("_hope_patient_id") or "")
        canon = pid_canonical.get(old)
        if canon and canon != old:
            row = {**row, "_hope_patient_id": canon}
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
    R = store.read_latest_run

    wards_raw = R("hope_wards")
    rooms_raw = R("hope_rooms")
    persons_raw = R("hope_persons")

    print("Building canonical patient-id remap...")
    pid_canonical = _build_pid_canonical(store)
    print(f"  {len(pid_canonical):,} entries -> {len(set(pid_canonical.values())):,} canonical ids")

    person_to_mrn = acct.build_person_to_mrn(persons_raw)
    print(f"  person_id -> MRN bridge: {len(person_to_mrn):,} entries")

    # (label, table, payloads, require_patient)
    jobs = [
        ("ward_service_charges", "royan_ward_service_charges",
         _remap(ops.transform_ward_service_charges(R("hope_ward_patient_services"), wards_raw, rooms_raw), pid_canonical), True),
        ("patient_documents", "royan_patient_documents",
         _remap(ops.transform_patient_documents(R("hope_patient_documents")), pid_canonical), True),
        ("ward_consumption", "royan_ward_consumption",
         _remap(ops.transform_ward_consumption(R("hope_direct_consumptions")), pid_canonical), False),
        ("doctor_schedule_blocks", "royan_doctor_schedule_blocks",
         ops.transform_doctor_schedule_blocks(R("hope_doctor_chambers")), False),
        ("medication_administration", "royan_medication_administration",
         _remap(ops.transform_medication_administration(R("hope_medication_administering_records")), pid_canonical), True),
        ("account_receipts", "royan_account_receipts",
         _remap(acct.transform_account_receipts(R("hope_account_receipts"), R("hope_voucher_payments")), pid_canonical), False),
        ("voucher_entries", "royan_voucher_entries",
         _remap(acct.transform_voucher_entries(R("hope_voucher_entries")), pid_canonical), False),
        ("patient_card_transactions", "royan_patient_card_transactions",
         acct.transform_patient_card_transactions(R("hope_patient_cards"), person_to_mrn), False),
        ("discount_requests", "royan_discount_requests",
         _remap(acct.transform_discount_requests(R("hope_discount_requests")), pid_canonical), False),
        ("settlement_billings", "royan_settlement_billings",
         _remap(acct.transform_settlement_billings(R("hope_settlement_billings")), pid_canonical), False),
    ]

    conn = None
    if not dry_run:
        from config import DATABASE_URL
        conn = get_conn(DATABASE_URL)
        print("Connected to PostgreSQL.\n")

    results = []
    for label, table, payloads, require_patient in jobs:
        seen, upserted = load_generic(conn, table, payloads, dry_run=dry_run, require_patient=require_patient)
        if conn and not dry_run:
            log_run(conn, label, seen, upserted)
        results.append((label, seen, upserted))
        print(f"{label}: {seen:,} seen, {upserted:,} {'would upsert' if dry_run else 'upserted'}")

    # patient_profiles -> royan_encounter_notes (reuses the notes loader)
    notes = _remap(ops.transform_patient_profile_notes(R("hope_patient_profiles")), pid_canonical)
    seen, upserted = load_encounter_notes(conn, notes, dry_run=dry_run)
    if conn and not dry_run:
        log_run(conn, "patient_profile_notes", seen, upserted)
    results.append(("patient_profile_notes", seen, upserted))
    print(f"patient_profile_notes: {seen:,} seen, {upserted:,} {'would upsert' if dry_run else 'upserted'}")

    print("\n=== Phase A3 summary ===")
    for label, seen, upserted in results:
        print(f"  {label:32s} {upserted:>8,} / {seen:>8,}")

    if conn:
        conn.close()


if __name__ == "__main__":
    main()
