"""Transform + load real historical purchase batches (real batch numbers +
expiry dates) from Hope's inventory_purchase_details/item_details tables
(staged by extract_inventory_remainder.py) -> royan_inventory_batches.

Usage:
    python scripts/load_purchase_batches.py --dry-run
    python scripts/load_purchase_batches.py --execute
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from staging.sqlite_store import StagingStore
from transformers.pharmacy_purchase_batches import transform
from loaders.db_loader import get_conn, load_purchase_batches, log_run


def main() -> None:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    dry_run = args.dry_run

    store = StagingStore()
    items = store.read_latest_run("hope_inv_purchase_item_details")
    purchases = store.read_latest_run("hope_inv_purchase_details")
    print(f"purchase_item_details: {len(items)} raw, purchase_details: {len(purchases)} raw")

    payloads = transform(items, purchases)
    print(f"purchase_batches: {len(payloads)} payloads ready")

    conn = None
    if not dry_run:
        from config import DATABASE_URL
        conn = get_conn(DATABASE_URL)
        print("Connected to PostgreSQL.")

    seen, upserted = load_purchase_batches(conn, payloads, dry_run=dry_run)
    if conn and not dry_run:
        log_run(conn, "purchase_batches", seen, upserted)
    print(f"purchase_batches: {seen} seen, {upserted} {'would upsert' if dry_run else 'upserted'} "
          f"(skipped = item_id not in the loaded formulary)")

    if conn:
        conn.close()


if __name__ == "__main__":
    main()
