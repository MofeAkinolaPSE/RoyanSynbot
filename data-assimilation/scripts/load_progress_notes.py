"""Transform + load real ward/ICU progress notes from Hope's progresstbls
(staged by extract_phase_a2_audit_findings.py) into royan_encounter_notes
(note_type='progress'). Reuses load_encounter_notes unmodified.

Applies the canonical patient-id remap (see load_nursing_notes.py) --
without it, resolution was 9.5% (569/5991), matching the known ~10-25%
unremapped baseline; nurse_notes/shift_notes went from that same baseline
to 99.8% with this fix applied.

Usage:
    python scripts/load_progress_notes.py --dry-run
    python scripts/load_progress_notes.py --execute
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from staging.sqlite_store import StagingStore
import transformers.patients as t_patients
from transformers.progress_notes import transform
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
    raw = store.read_latest_run("hope_progresstbls")
    print(f"progresstbls: {len(raw)} raw")

    payloads = transform(raw)
    print(f"progress_notes: {len(payloads)} payloads ready")

    print("Building canonical patient-id remap (Hope has multiple rows per MRN)...")
    pid_canonical = _build_pid_canonical(store)
    print(f"  {len(pid_canonical)} entries -> {len(set(pid_canonical.values()))} canonical ids")
    payloads = _remap_patient_ids(payloads, pid_canonical)

    conn = None
    if not dry_run:
        from config import DATABASE_URL
        conn = get_conn(DATABASE_URL)
        print("Connected to PostgreSQL.")

    seen, upserted = load_encounter_notes(conn, payloads, dry_run=dry_run)
    if conn and not dry_run:
        log_run(conn, "progress_notes", seen, upserted)
    print(f"progress_notes: {seen} seen, {upserted} {'would upsert' if dry_run else 'upserted'} "
          f"(skipped = no resolvable patient/encounter)")

    if conn:
        conn.close()


if __name__ == "__main__":
    main()
