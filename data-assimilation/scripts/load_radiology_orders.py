"""Close the radiology-order coverage gap: load Hope's radiology_test_orders
(staged by extract_final_sweep.py) into royan_radiology_orders.

Only 24,080 of 56,536 real Hope orders (~43%) had ever been loaded, by an
untraceable earlier mechanism predating the canonical patient-id remap.
This applies that remap, which is what recovers the rest.

IMPORTANT: re-run scripts/load_radiology_results.py afterwards -- that
loader is UPDATE-shaped against these rows, so the newly-inserted orders
only pick up their report/impression content once it runs again.

Usage:
    python scripts/load_radiology_orders.py --dry-run
    python scripts/load_radiology_orders.py --execute
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
from transformers.radiology_orders import transform
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
    raw = store.read_latest_run("hope_radiology_test_orders")
    print(f"radiology_test_orders: {len(raw):,} raw")

    payloads = transform(raw)
    print(f"radiology_orders: {len(payloads):,} payloads ready (non-deleted, resolvable timestamp)")

    print("Building canonical patient-id remap...")
    pid_canonical = _build_pid_canonical(store)
    print(f"  {len(pid_canonical):,} entries -> {len(set(pid_canonical.values())):,} canonical ids")
    payloads = _remap(payloads, pid_canonical)

    conn = None
    if not dry_run:
        from config import DATABASE_URL
        conn = get_conn(DATABASE_URL)
        print("Connected to PostgreSQL.")

    seen, upserted = load_generic(conn, "royan_radiology_orders", payloads, dry_run=dry_run)
    if conn and not dry_run:
        log_run(conn, "radiology_orders", seen, upserted)
    print(f"radiology_orders: {seen:,} seen, {upserted:,} {'would upsert' if dry_run else 'upserted'}")

    if not dry_run:
        print("\nNEXT: re-run scripts/load_radiology_results.py so the newly-inserted "
              "orders pick up their report/impression content.")

    if conn:
        conn.close()


if __name__ == "__main__":
    main()
