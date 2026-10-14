"""Transform + load Hope's ICU nursing observation flowsheet
(review_patient_details + its three review_* lookup tables, all staged by
extract_final_sweep.py) into royan_nursing_flowsheet.

Usage:
    python scripts/load_nursing_flowsheet.py --dry-run
    python scripts/load_nursing_flowsheet.py --execute
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

from staging.sqlite_store import StagingStore
import transformers.patients as t_patients
from transformers.nursing_flowsheet import transform
from loaders.db_loader import get_conn, load_generic, log_run


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

    raw = R("hope_review_patient_details")
    cats = R("hope_review_categories")
    subs = R("hope_review_sub_categories")
    opts = R("hope_review_sub_categories_options")
    print(f"review_patient_details: {len(raw):,} | categories: {len(cats)} "
          f"| sub_categories: {len(subs)} | options: {len(opts)}")

    payloads = transform(raw, cats, subs, opts)
    print(f"nursing_flowsheet: {len(payloads):,} payloads ready")

    print("Building canonical patient-id remap...")
    pid_canonical = _build_pid_canonical(store)
    print(f"  {len(pid_canonical):,} entries -> {len(set(pid_canonical.values())):,} canonical ids")
    payloads = _remap(payloads, pid_canonical)

    conn = None
    if not dry_run:
        from config import DATABASE_URL
        conn = get_conn(DATABASE_URL)
        print("Connected to PostgreSQL.")

    seen, upserted = load_generic(conn, "royan_nursing_flowsheet", payloads, dry_run=dry_run)
    if conn and not dry_run:
        log_run(conn, "nursing_flowsheet", seen, upserted)
    print(f"nursing_flowsheet: {seen:,} seen, {upserted:,} {'would upsert' if dry_run else 'upserted'}")

    if conn:
        conn.close()


if __name__ == "__main__":
    main()
