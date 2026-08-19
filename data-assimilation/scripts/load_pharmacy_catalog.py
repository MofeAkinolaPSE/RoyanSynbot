"""Transform + load Royan's real drug catalog from Hope's `pharmacy_items`
table (already staged as hope_pharmacy_catalog by extract_missing_entities.py)
-> royan_drug_formulary + an initial royan_inventory_batches stock row per drug.

Usage:
    python scripts/load_pharmacy_catalog.py --dry-run
    python scripts/load_pharmacy_catalog.py --execute
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from staging.sqlite_store import StagingStore
from transformers.pharmacy_catalog import transform_formulary
from loaders.db_loader import get_conn, load_pharmacy_catalog, log_run


def main() -> None:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    dry_run = args.dry_run

    store = StagingStore()
    raw = store.read_latest_run("hope_pharmacy_catalog")
    print(f"pharmacy_catalog: {len(raw)} raw rows")

    payloads = transform_formulary(raw)
    print(f"pharmacy_catalog: {len(payloads)} payloads ready (after is_deleted-exclusion + code-dedup)")

    conn = None
    if not dry_run:
        from config import DATABASE_URL
        conn = get_conn(DATABASE_URL)
        print("Connected to PostgreSQL.")

    seen, upserted = load_pharmacy_catalog(conn, payloads, dry_run=dry_run)
    if conn and not dry_run:
        log_run(conn, "pharmacy_catalog", seen, upserted)
    print(f"pharmacy_catalog: {seen} seen, {upserted} {'would upsert' if dry_run else 'upserted'} "
          f"(formulary + batch pairs)")

    if conn:
        conn.close()


if __name__ == "__main__":
    main()
