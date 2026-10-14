"""Transform + load Hope's per-batch pharmacy pricing into
royan_pharmacy_item_rates (migration 195).

Usage:
    python scripts/load_pharmacy_item_rates.py --dry-run
    python scripts/load_pharmacy_item_rates.py --execute
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

from staging.sqlite_store import StagingStore
from transformers.pharmacy_item_rates import transform
from loaders.db_loader import get_conn, load_generic, log_run


def main() -> None:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    dry_run = args.dry_run

    store = StagingStore()
    raw = store.read_latest_run("hope_pharmacy_item_rates")
    print(f"pharmacy_item_rates: {len(raw):,} raw")

    payloads = transform(raw)
    print(f"pharmacy_item_rates: {len(payloads):,} payloads ready")

    conn = None
    if not dry_run:
        from config import DATABASE_URL
        conn = get_conn(DATABASE_URL)
        print("Connected to PostgreSQL.")

    seen, up = load_generic(
        conn, "royan_pharmacy_item_rates", payloads, dry_run=dry_run, require_patient=False,
    )
    if conn and not dry_run:
        log_run(conn, "pharmacy_item_rates", seen, up)
    print(f"pharmacy_item_rates: {seen:,} seen, {up:,} {'would upsert' if dry_run else 'upserted'}")

    if conn:
        conn.close()


if __name__ == "__main__":
    main()
