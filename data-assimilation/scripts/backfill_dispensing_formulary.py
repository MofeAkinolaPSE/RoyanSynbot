"""Backfill royan_dispensing.formulary_id on the 618k already-loaded rows.

dispensing.py's transform always had Hope's item_id available (same id
space as pharmacy_items.id, which pharmacy_catalog.py used for
royan_drug_formulary.external_id) but discarded it after resolving
drug_name. It's now threaded through as _hope_item_id; this re-runs the
transform+load against the already-staged data (no dump re-parse needed)
so the ON CONFLICT upsert backfills formulary_id on every existing row.

Usage:
    python scripts/backfill_dispensing_formulary.py --dry-run
    python scripts/backfill_dispensing_formulary.py --execute
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from staging.sqlite_store import StagingStore
import transformers.dispensing as t_dispensing
from loaders.db_loader import get_conn, load_dispensing, log_run


def _build_item_catalog(rows: list[dict]) -> dict[str, str]:
    catalog: dict[str, str] = {}
    for row in rows:
        raw = {k.lower(): v for k, v in row.items()}
        item_id = str(raw.get("id") or "").strip()
        if not item_id:
            continue
        name = (
            (raw.get("product_name") or "").strip()
            or (raw.get("name") or "").strip()
            or (raw.get("generic") or "").strip()
            or (raw.get("genericdrugname") or "").strip()
        )
        if name:
            catalog[item_id] = name
    return catalog


def main() -> None:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    dry_run = args.dry_run

    store = StagingStore()
    dispensing_raw = store.read_latest_run("hope_dispensing_lines")
    catalog_raw = store.read_latest_run("hope_pharmacy_catalog")
    print(f"dispensing_lines: {len(dispensing_raw)}, pharmacy_catalog: {len(catalog_raw)}")

    item_catalog = _build_item_catalog(catalog_raw)
    dispensing = t_dispensing.transform(dispensing_raw, item_catalog=item_catalog)
    with_item_id = sum(1 for r in dispensing if r.get("_hope_item_id"))
    print(f"dispensing: {len(dispensing)} payloads ready ({with_item_id} carry a Hope item_id)")

    conn = None
    if not dry_run:
        from config import DATABASE_URL
        conn = get_conn(DATABASE_URL)
        print("Connected to PostgreSQL.")

    seen, upserted = load_dispensing(conn, dispensing, dry_run=dry_run)
    if conn and not dry_run:
        log_run(conn, "dispensing_formulary_backfill", seen, upserted)
    print(f"dispensing: {seen} seen, {upserted} {'would upsert' if dry_run else 'upserted'}")

    if conn:
        conn.close()


if __name__ == "__main__":
    main()
