"""Transform + load Hope's real billing archive (billings + final_billings,
staged by extract_phase_a2_audit_findings.py) into royan_billing_transactions
+ royan_billing_summaries. Supplement to royan_billing, not a replacement.

Applies the canonical patient-id remap (see load_nursing_notes.py).

Usage:
    python scripts/load_billing_archive.py --dry-run
    python scripts/load_billing_archive.py --execute
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from staging.sqlite_store import StagingStore
import transformers.patients as t_patients
from transformers.billing_archive import transform_transactions, transform_summaries
from loaders.db_loader import get_conn, load_billing_transactions, load_billing_summaries, log_run


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


def _remap_patient_ids(rows: list[dict], pid_canonical: dict[str, str]) -> list[dict]:
    out = []
    for row in rows:
        old_val = str(row.get("_hope_patient_id") or "")
        canonical = pid_canonical.get(old_val)
        if canonical and canonical != old_val:
            row = {**row, "_hope_patient_id": canonical}
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
    billings_raw = store.read_latest_run("hope_billings")
    final_billings_raw = store.read_latest_run("hope_final_billings")
    print(f"billings: {len(billings_raw)}, final_billings: {len(final_billings_raw)}")

    txn_payloads = transform_transactions(billings_raw)
    summary_payloads = transform_summaries(final_billings_raw)
    print(f"billing_transactions: {len(txn_payloads)} payloads ready")
    print(f"billing_summaries: {len(summary_payloads)} payloads ready")

    print("Building canonical patient-id remap (Hope has multiple rows per MRN)...")
    pid_canonical = _build_pid_canonical(store)
    print(f"  {len(pid_canonical)} entries -> {len(set(pid_canonical.values()))} canonical ids")
    txn_payloads = _remap_patient_ids(txn_payloads, pid_canonical)
    summary_payloads = _remap_patient_ids(summary_payloads, pid_canonical)

    conn = None
    if not dry_run:
        from config import DATABASE_URL
        conn = get_conn(DATABASE_URL)
        print("Connected to PostgreSQL.")

    seen, upserted = load_billing_transactions(conn, txn_payloads, dry_run=dry_run)
    if conn and not dry_run:
        log_run(conn, "billing_transactions", seen, upserted)
    print(f"billing_transactions: {seen} seen, {upserted} {'would upsert' if dry_run else 'upserted'}")

    seen2, upserted2 = load_billing_summaries(conn, summary_payloads, dry_run=dry_run)
    if conn and not dry_run:
        log_run(conn, "billing_summaries", seen2, upserted2)
    print(f"billing_summaries: {seen2} seen, {upserted2} {'would upsert' if dry_run else 'upserted'}")

    if conn:
        conn.close()


if __name__ == "__main__":
    main()
