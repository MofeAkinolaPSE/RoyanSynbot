"""Transform + load Royan's real radiology report section templates from
the tables staged by extract_locations_radiology_templates.py.

Usage:
    python scripts/load_radiology_report_templates.py --dry-run
    python scripts/load_radiology_report_templates.py --execute
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from staging.sqlite_store import StagingStore
from transformers.radiology_report_templates import (
    transform_templates, transform_template_texts, valid_template_ids,
)
from loaders.db_loader import (
    get_conn, load_radiology_report_templates, load_radiology_report_template_texts, log_run,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    dry_run = args.dry_run

    store = StagingStore()
    templates_raw = store.read_latest_run("hope_radiology_templates")
    texts_raw = store.read_latest_run("hope_radiology_template_texts")
    print(f"radiology_templates: {len(templates_raw)}, radiology_template_texts: {len(texts_raw)}")

    templates = transform_templates(templates_raw)
    valid_ids = valid_template_ids(templates)
    texts = transform_template_texts(texts_raw, valid_ids)
    print(f"templates: {len(templates)} payloads ready, texts: {len(texts)} payloads ready")

    conn = None
    if not dry_run:
        from config import DATABASE_URL
        conn = get_conn(DATABASE_URL)
        print("Connected to PostgreSQL.")

    seen, upserted = load_radiology_report_templates(conn, templates, dry_run=dry_run)
    if conn and not dry_run:
        log_run(conn, "radiology_report_templates", seen, upserted)
    print(f"radiology_report_templates: {seen} seen, {upserted} {'would upsert' if dry_run else 'upserted'}")

    seen2, upserted2 = load_radiology_report_template_texts(conn, texts, dry_run=dry_run)
    if conn and not dry_run:
        log_run(conn, "radiology_report_template_texts", seen2, upserted2)
    print(f"radiology_report_template_texts: {seen2} seen, {upserted2} {'would upsert' if dry_run else 'upserted'}")

    if conn:
        conn.close()


if __name__ == "__main__":
    main()
