"""Transform + load the real Royan doctor roster from Hope's `doctors`
table (staged by extract_staff.py as hope_doctors/hope_departments).

Usage:
    python scripts/load_staff.py --dry-run
    python scripts/load_staff.py --execute
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from staging.sqlite_store import StagingStore
import transformers.staff as t_staff
from loaders.db_loader import get_conn, load_staff, log_run


def main() -> None:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    dry_run = args.dry_run

    store = StagingStore()
    doctors_raw = store.read_latest_run("hope_doctors")
    departments_raw = store.read_latest_run("hope_departments")
    print(f"doctors: {len(doctors_raw)} raw, departments: {len(departments_raw)} raw")

    department_names = {
        str(r.get("id")): (r.get("name") or "").strip()
        for r in departments_raw if r.get("id")
    }

    staff = t_staff.transform(doctors_raw, department_names=department_names)
    print(f"staff: {len(staff)} payloads ready (after demo-exclusion + name-dedup)")

    conn = None
    if not dry_run:
        from config import DATABASE_URL
        conn = get_conn(DATABASE_URL)
        print("Connected to PostgreSQL.")

    seen, upserted = load_staff(conn, staff, dry_run=dry_run)
    if conn and not dry_run:
        log_run(conn, "staff", seen, upserted)
    print(f"staff: {seen} seen, {upserted} {'would upsert' if dry_run else 'upserted'}")

    if conn:
        conn.close()


if __name__ == "__main__":
    main()
