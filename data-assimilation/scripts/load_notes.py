"""Transform + load Royan's real clinical notes from Hope's `notes` table
(staged by extract_notes.py as hope_notes) -> royan_encounter_notes.

Usage:
    python scripts/load_notes.py --dry-run
    python scripts/load_notes.py --execute
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from staging.sqlite_store import StagingStore
from transformers.hope_notes import transform
from loaders.db_loader import get_conn, load_encounter_notes, log_run


def main() -> None:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    dry_run = args.dry_run

    store = StagingStore()
    raw = store.read_latest_run("hope_notes")
    print(f"notes: {len(raw)} raw rows")

    payloads = transform(raw)
    print(f"notes: {len(payloads)} payloads ready (after content/patient_id/date filtering)")

    conn = None
    if not dry_run:
        from config import DATABASE_URL
        conn = get_conn(DATABASE_URL)
        print("Connected to PostgreSQL.")

    seen, upserted = load_encounter_notes(conn, payloads, dry_run=dry_run)
    if conn and not dry_run:
        log_run(conn, "encounter_notes", seen, upserted)
    print(f"notes: {seen} seen, {upserted} {'would upsert' if dry_run else 'upserted'} "
          f"(skipped = unresolved patient or patient has zero encounters)")

    if conn:
        conn.close()


if __name__ == "__main__":
    main()
