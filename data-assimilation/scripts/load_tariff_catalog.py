"""Transform + load Royan's real service price catalog from the tables
staged by extract_phase_a2_audit_findings.py (tariff_lists) and
extract_phase_a3_audit_findings.py (tariff_amounts).

Usage:
    python scripts/load_tariff_catalog.py --dry-run
    python scripts/load_tariff_catalog.py --execute
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from staging.sqlite_store import StagingStore
from transformers.tariff_catalog import transform
from loaders.db_loader import get_conn, load_tariff_catalog, log_run


def main() -> None:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    dry_run = args.dry_run

    store = StagingStore()
    tariff_lists_raw = store.read_latest_run("hope_tariff_lists")
    tariff_amounts_raw = store.read_latest_run("hope_tariff_amounts")
    print(f"tariff_lists: {len(tariff_lists_raw)}, tariff_amounts: {len(tariff_amounts_raw)}")

    payloads = transform(tariff_lists_raw, tariff_amounts_raw)
    print(f"tariff_catalog: {len(payloads)} payloads ready")

    conn = None
    if not dry_run:
        from config import DATABASE_URL
        conn = get_conn(DATABASE_URL)
        print("Connected to PostgreSQL.")

    seen, upserted = load_tariff_catalog(conn, payloads, dry_run=dry_run)
    if conn and not dry_run:
        log_run(conn, "tariff_catalog", seen, upserted)
    print(f"tariff_catalog: {seen} seen, {upserted} {'would upsert' if dry_run else 'upserted'}")

    if conn:
        conn.close()


if __name__ == "__main__":
    main()
