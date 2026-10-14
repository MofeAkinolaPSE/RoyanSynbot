"""Transform + load real purchase-order batch/cost records from Hope's
purchase_order_items (staged by extract_phase_a2_audit_findings.py) into
royan_inventory_batches. Reuses load_purchase_batches unmodified.

Usage:
    python scripts/load_purchase_order_batches.py --dry-run
    python scripts/load_purchase_order_batches.py --execute
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from staging.sqlite_store import StagingStore
from transformers.purchase_order_batches import transform
from loaders.db_loader import get_conn, load_purchase_batches, log_run


def main() -> None:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    dry_run = args.dry_run

    store = StagingStore()
    raw = store.read_latest_run("hope_purchase_order_items")
    print(f"purchase_order_items: {len(raw)} raw")

    payloads = transform(raw)
    print(f"purchase_order_batches: {len(payloads)} payloads ready")

    conn = None
    if not dry_run:
        from config import DATABASE_URL
        conn = get_conn(DATABASE_URL)
        print("Connected to PostgreSQL.")

    seen, upserted = load_purchase_batches(conn, payloads, dry_run=dry_run)
    if conn and not dry_run:
        log_run(conn, "purchase_order_batches", seen, upserted)
    print(f"purchase_order_batches: {seen} seen, {upserted} {'would upsert' if dry_run else 'upserted'} "
          f"(skipped = product_id not in loaded formulary)")

    if conn:
        conn.close()


if __name__ == "__main__":
    main()
