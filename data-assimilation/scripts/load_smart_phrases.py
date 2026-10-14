"""Transform + load Royan's real Smart Phrases (dot-phrase macros) from the
tables staged by extract_phase_a2_audit_findings.py.

Usage:
    python scripts/load_smart_phrases.py --dry-run
    python scripts/load_smart_phrases.py --execute
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from staging.sqlite_store import StagingStore
from transformers.smart_phrases import transform_smart_phrases, transform_smart_phrase_options
from loaders.db_loader import (
    get_conn, load_smart_phrases, load_smart_phrase_options, log_run,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    dry_run = args.dry_run

    store = StagingStore()
    phrases_raw = store.read_latest_run("hope_smart_phrases")
    options_raw = store.read_latest_run("hope_smart_phrase_multiple")
    print(f"smart_phrases: {len(phrases_raw)}, smart_phrase_multiple: {len(options_raw)}")

    phrases = transform_smart_phrases(phrases_raw)
    options = transform_smart_phrase_options(options_raw)
    print(f"phrases: {len(phrases)} payloads ready, options: {len(options)} payloads ready")

    conn = None
    if not dry_run:
        from config import DATABASE_URL
        conn = get_conn(DATABASE_URL)
        print("Connected to PostgreSQL.")

    seen, upserted = load_smart_phrases(conn, phrases, dry_run=dry_run)
    if conn and not dry_run:
        log_run(conn, "smart_phrases", seen, upserted)
    print(f"smart_phrases: {seen} seen, {upserted} {'would upsert' if dry_run else 'upserted'}")

    seen2, upserted2 = load_smart_phrase_options(conn, options, dry_run=dry_run)
    if conn and not dry_run:
        log_run(conn, "smart_phrase_options", seen2, upserted2)
    print(f"smart_phrase_options: {seen2} seen, {upserted2} {'would upsert' if dry_run else 'upserted'}")

    if conn:
        conn.close()


if __name__ == "__main__":
    main()
