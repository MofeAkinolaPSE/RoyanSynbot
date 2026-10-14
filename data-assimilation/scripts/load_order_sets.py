"""Transform + load Royan's real "treatment templates" (Hope's Order Set
subsystem) from the tables staged by extract_phase_a_reference_data.py.

Usage:
    python scripts/load_order_sets.py --dry-run
    python scripts/load_order_sets.py --execute
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from staging.sqlite_store import StagingStore
from transformers.order_sets import transform_order_sets, transform_order_set_items, valid_master_ids
from loaders.db_loader import get_conn, load_order_sets, load_order_set_items, log_run


def main() -> None:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    dry_run = args.dry_run

    store = StagingStore()
    masters_raw = store.read_latest_run("hope_orderset_masters")
    items_raw = store.read_latest_run("hope_order_subcategories")
    categories_raw = store.read_latest_run("hope_order_categories")
    print(f"orderset_masters: {len(masters_raw)} raw, order_subcategories: {len(items_raw)} raw, "
          f"order_categories: {len(categories_raw)} raw")

    order_sets = transform_order_sets(masters_raw, items_raw)
    valid_ids = valid_master_ids(order_sets)
    print(f"order_sets: {len(order_sets)} payloads ready (of {len(masters_raw)} raw masters)")

    items = transform_order_set_items(items_raw, categories_raw, valid_ids)
    print(f"order_set_items: {len(items)} payloads ready (of {len(items_raw)} raw subcategory rows)")

    conn = None
    if not dry_run:
        from config import DATABASE_URL
        conn = get_conn(DATABASE_URL)
        print("Connected to PostgreSQL.")

    seen, upserted = load_order_sets(conn, order_sets, dry_run=dry_run)
    if conn and not dry_run:
        log_run(conn, "order_sets", seen, upserted)
    print(f"order_sets: {seen} seen, {upserted} {'would upsert' if dry_run else 'upserted'}")

    seen2, upserted2 = load_order_set_items(conn, items, dry_run=dry_run)
    if conn and not dry_run:
        log_run(conn, "order_set_items", seen2, upserted2)
    print(f"order_set_items: {seen2} seen, {upserted2} {'would upsert' if dry_run else 'upserted'}")

    if conn:
        conn.close()


if __name__ == "__main__":
    main()
