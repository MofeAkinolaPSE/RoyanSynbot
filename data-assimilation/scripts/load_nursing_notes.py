"""Transform + load real nursing documentation (Hope's nurse_notes +
shift_notes) -> royan_encounter_notes (note_type='nursing').

Applies the canonical patient-id remap (Hope keeps multiple patient rows
per MRN; only the latest-per-MRN is loaded into royan_patients) before
resolution, same fix already proven for payments/lab_results/HMO links
elsewhere in this project (~25% -> 99.999% resolution) -- the original
doctor-notes loader (load_notes.py) predates that fix and doesn't have it,
kept here deliberately since this is large, high-value data worth
maximizing real landing rate for.

Usage:
    python scripts/load_nursing_notes.py --dry-run
    python scripts/load_nursing_notes.py --execute
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from staging.sqlite_store import StagingStore
import transformers.patients as t_patients
from transformers.nursing_notes import transform_nurse_notes, transform_shift_notes
from loaders.db_loader import get_conn, load_encounter_notes, log_run


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
    nurse_notes_raw = store.read_latest_run("hope_nurse_notes")
    shift_notes_raw = store.read_latest_run("hope_shift_notes")
    print(f"nurse_notes: {len(nurse_notes_raw)} raw, shift_notes: {len(shift_notes_raw)} raw")

    nurse_payloads = transform_nurse_notes(nurse_notes_raw)
    shift_payloads = transform_shift_notes(shift_notes_raw)
    print(f"nurse_notes: {len(nurse_payloads)} payloads ready")
    print(f"shift_notes: {len(shift_payloads)} payloads ready")

    print("Building canonical patient-id remap (Hope has multiple rows per MRN)...")
    pid_canonical = _build_pid_canonical(store)
    print(f"  {len(pid_canonical)} entries -> {len(set(pid_canonical.values()))} canonical ids")
    nurse_payloads = _remap_patient_ids(nurse_payloads, pid_canonical)
    shift_payloads = _remap_patient_ids(shift_payloads, pid_canonical)

    all_payloads = nurse_payloads + shift_payloads

    conn = None
    if not dry_run:
        from config import DATABASE_URL
        conn = get_conn(DATABASE_URL)
        print("Connected to PostgreSQL.")

    seen, upserted = load_encounter_notes(conn, all_payloads, dry_run=dry_run)
    if conn and not dry_run:
        log_run(conn, "nursing_notes", seen, upserted)
    print(f"nursing_notes (combined): {seen} seen, {upserted} {'would upsert' if dry_run else 'upserted'} "
          f"(skipped = unresolved patient or patient has zero encounters)")

    if conn:
        conn.close()


if __name__ == "__main__":
    main()
