"""Transform + load Royan's real Review-of-Systems / Physical-Exam finding
picker (Hope's template_categories/templates/template_sub_categories) from
the tables staged by extract_phase_a_reference_data.py.

Usage:
    python scripts/load_exam_templates.py --dry-run
    python scripts/load_exam_templates.py --execute
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from staging.sqlite_store import StagingStore
from transformers.exam_templates import (
    transform_exam_templates, transform_exam_template_findings, valid_template_ids,
)
from loaders.db_loader import get_conn, load_exam_templates, load_exam_template_findings, log_run


def main() -> None:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    dry_run = args.dry_run

    store = StagingStore()
    templates_raw = store.read_latest_run("hope_templates")
    categories_raw = store.read_latest_run("hope_template_categories")
    sub_categories_raw = store.read_latest_run("hope_template_sub_categories")
    print(f"templates: {len(templates_raw)}, template_categories: {len(categories_raw)}, "
          f"template_sub_categories: {len(sub_categories_raw)}")

    exam_templates = transform_exam_templates(templates_raw, categories_raw)
    valid_ids = valid_template_ids(exam_templates)
    print(f"exam_templates: {len(exam_templates)} payloads ready")

    findings = transform_exam_template_findings(sub_categories_raw, valid_ids)
    print(f"exam_template_findings: {len(findings)} payloads ready")

    conn = None
    if not dry_run:
        from config import DATABASE_URL
        conn = get_conn(DATABASE_URL)
        print("Connected to PostgreSQL.")

    seen, upserted = load_exam_templates(conn, exam_templates, dry_run=dry_run)
    if conn and not dry_run:
        log_run(conn, "exam_templates", seen, upserted)
    print(f"exam_templates: {seen} seen, {upserted} {'would upsert' if dry_run else 'upserted'}")

    seen2, upserted2 = load_exam_template_findings(conn, findings, dry_run=dry_run)
    if conn and not dry_run:
        log_run(conn, "exam_template_findings", seen2, upserted2)
    print(f"exam_template_findings: {seen2} seen, {upserted2} {'would upsert' if dry_run else 'upserted'}")

    if conn:
        conn.close()


if __name__ == "__main__":
    main()
