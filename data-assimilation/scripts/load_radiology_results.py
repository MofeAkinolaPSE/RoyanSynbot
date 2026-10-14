"""Transform + load real radiology report content (Hope's radiology_results)
onto the already-loaded royan_radiology_orders rows (UPDATE-shaped, not
INSERT -- see transformers/radiology_results.py).

Usage:
    python scripts/load_radiology_results.py --dry-run
    python scripts/load_radiology_results.py --execute
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from staging.sqlite_store import StagingStore
from transformers.radiology_results import transform
from loaders.db_loader import get_conn, load_radiology_results, log_run


def main() -> None:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    dry_run = args.dry_run

    store = StagingStore()
    raw = store.read_latest_run("hope_radiology_results")
    print(f"radiology_results: {len(raw)} raw")

    payloads = transform(raw)
    print(f"radiology_results: {len(payloads)} payloads ready")

    conn = None
    if not dry_run:
        from config import DATABASE_URL
        conn = get_conn(DATABASE_URL)
        print("Connected to PostgreSQL.")

    seen, updated = load_radiology_results(conn, payloads, dry_run=dry_run)
    if conn and not dry_run:
        log_run(conn, "radiology_results", seen, updated)
    print(f"radiology_results: {seen} seen, {updated} {'would update' if dry_run else 'updated'} "
          f"(skipped = matching royan_radiology_orders row not found)")

    if conn:
        conn.close()


if __name__ == "__main__":
    main()
