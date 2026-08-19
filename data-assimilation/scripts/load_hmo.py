"""Transform + load Royan's real HMO/payer list and patient<->HMO links from
the tables staged by extract_hmo_corporate.py + extract_tariff_standards.py.

Usage:
    python scripts/load_hmo.py --dry-run
    python scripts/load_hmo.py --execute
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from staging.sqlite_store import StagingStore
import transformers.patients as t_patients
from transformers.hmo import transform_hmos, transform_patient_links
from loaders.db_loader import get_conn, load_hmos, load_patient_hmo_links, log_run


def _build_pid_canonical(store: StagingStore) -> dict[str, str]:
    """Hope keeps multiple patient rows per MRN (one per historical
    registration event); only the latest-per-MRN is loaded into
    royan_patients. corporate_patient_details.patient_id can carry any of
    those historical Hope patient ids, so it needs remapping to the one
    canonical id that was actually loaded -- same fix already proven for
    payments/lab_results in load_missing_entities.py (25% -> 99.999%)."""
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
    tariff_raw = store.read_latest_run("hope_tariff_standards")
    cpd_raw = store.read_latest_run("hope_corporate_patient_details")
    csb_raw = store.read_latest_run("hope_corporate_super_bills")
    print(f"tariff_standards: {len(tariff_raw)}, corporate_patient_details: {len(cpd_raw)}, "
          f"corporate_super_bills: {len(csb_raw)}")

    print("Building canonical patient-id remap (Hope has multiple rows per MRN)...")
    pid_canonical = _build_pid_canonical(store)
    print(f"  {len(pid_canonical)} entries -> {len(set(pid_canonical.values()))} canonical ids")
    cpd_raw = _remap_patient_ids(cpd_raw, pid_canonical)

    hmos = transform_hmos(tariff_raw)
    links = transform_patient_links(cpd_raw, csb_raw, tariff_raw)
    print(f"hmos: {len(hmos)} payloads ready")
    print(f"patient_hmo_links: {len(links)} payloads ready (of {len(cpd_raw)} raw corporate_patient_details)")

    conn = None
    if not dry_run:
        from config import DATABASE_URL
        conn = get_conn(DATABASE_URL)
        print("Connected to PostgreSQL.")

    seen, upserted = load_hmos(conn, hmos, dry_run=dry_run)
    if conn and not dry_run:
        log_run(conn, "hmos", seen, upserted)
    print(f"hmos: {seen} seen, {upserted} {'would upsert' if dry_run else 'upserted'}")

    seen2, updated = load_patient_hmo_links(conn, links, dry_run=dry_run)
    if conn and not dry_run:
        log_run(conn, "patient_hmo_links", seen2, updated)
    print(f"patient_hmo_links: {seen2} seen, {updated} {'would update' if dry_run else 'updated'} "
          f"(skipped = patient not found, e.g. deduped-away duplicate registration)")

    if conn:
        conn.close()


if __name__ == "__main__":
    main()
