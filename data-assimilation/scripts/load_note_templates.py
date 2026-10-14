"""Transform + load Royan's real per-SOAP-section note templates (Hope's
note_templates + doctor_templates families) from the tables staged by
extract_phase_a_reference_data.py.

Usage:
    python scripts/load_note_templates.py --dry-run
    python scripts/load_note_templates.py --execute
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from staging.sqlite_store import StagingStore
from transformers.note_templates import (
    transform_note_templates, transform_note_template_texts,
    transform_doctor_templates, transform_doctor_template_texts,
    _valid_ext_ids,
)
from loaders.db_loader import get_conn, load_note_templates, load_note_template_texts, log_run


def main() -> None:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    dry_run = args.dry_run

    store = StagingStore()
    nt_raw = store.read_latest_run("hope_note_templates")
    ntt_raw = store.read_latest_run("hope_note_template_texts")
    dt_raw = store.read_latest_run("hope_doctor_templates")
    dtt_raw = store.read_latest_run("hope_doctor_template_texts")
    print(f"note_templates: {len(nt_raw)}, note_template_texts: {len(ntt_raw)}, "
          f"doctor_templates: {len(dt_raw)}, doctor_template_texts: {len(dtt_raw)}")

    note_masters = transform_note_templates(nt_raw)
    doctor_masters = transform_doctor_templates(dt_raw)
    all_masters = note_masters + doctor_masters
    valid_ids = _valid_ext_ids(all_masters)

    note_texts = transform_note_template_texts(ntt_raw, valid_ids)
    doctor_texts = transform_doctor_template_texts(dtt_raw, valid_ids)
    all_texts = note_texts + doctor_texts

    print(f"masters: {len(all_masters)} payloads ready ({len(note_masters)} system + {len(doctor_masters)} personal)")
    print(f"texts: {len(all_texts)} payloads ready ({len(note_texts)} system + {len(doctor_texts)} personal)")

    conn = None
    if not dry_run:
        from config import DATABASE_URL
        conn = get_conn(DATABASE_URL)
        print("Connected to PostgreSQL.")

    seen, upserted = load_note_templates(conn, all_masters, dry_run=dry_run)
    if conn and not dry_run:
        log_run(conn, "note_templates", seen, upserted)
    print(f"note_templates: {seen} seen, {upserted} {'would upsert' if dry_run else 'upserted'}")

    seen2, upserted2 = load_note_template_texts(conn, all_texts, dry_run=dry_run)
    if conn and not dry_run:
        log_run(conn, "note_template_texts", seen2, upserted2)
    print(f"note_template_texts: {seen2} seen, {upserted2} {'would upsert' if dry_run else 'upserted'}")

    if conn:
        conn.close()


if __name__ == "__main__":
    main()
