"""Transform + load Royan's real diagnosis catalog from the tables staged
by extract_phase_a_reference_data.py.

Usage:
    python scripts/load_diagnosis_catalog.py --dry-run
    python scripts/load_diagnosis_catalog.py --execute
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from staging.sqlite_store import StagingStore
from transformers.diagnosis_catalog import transform
from loaders.db_loader import get_conn, load_diagnosis_catalog, log_run


def main() -> None:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    dry_run = args.dry_run

    store = StagingStore()
    raw = store.read_latest_run("hope_diagnosis_masters")
    print(f"diagnosis_masters: {len(raw)} raw")

    payloads = transform(raw)
    print(f"diagnosis_catalog: {len(payloads)} payloads ready")

    conn = None
    if not dry_run:
        from config import DATABASE_URL
        conn = get_conn(DATABASE_URL)
        print("Connected to PostgreSQL.")

    seen, upserted = load_diagnosis_catalog(conn, payloads, dry_run=dry_run)
    if conn and not dry_run:
        log_run(conn, "diagnosis_catalog", seen, upserted)
    print(f"diagnosis_catalog: {seen} seen, {upserted} {'would upsert' if dry_run else 'upserted'}")

    if conn:
        conn.close()


if __name__ == "__main__":
    main()
