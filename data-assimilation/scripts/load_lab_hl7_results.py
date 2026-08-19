"""Transform + load real per-analyte lab results from Hope's
laboratory_hl7_results table (staged by extract_lab_hl7_results.py) ->
royan_lab_results.

Usage:
    python scripts/load_lab_hl7_results.py --dry-run
    python scripts/load_lab_hl7_results.py --execute
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from staging.sqlite_store import StagingStore
from transformers.lab_hl7_results import transform
from loaders.db_loader import get_conn, load_lab_hl7_results, log_run


def _build_parameter_catalog(rows: list[dict]) -> dict[str, dict[str, str]]:
    catalog: dict[str, dict[str, str]] = {}
    for row in rows:
        raw = {k.lower(): v for k, v in row.items()}
        param_id = str(raw.get("id") or "").strip()
        if not param_id:
            continue
        catalog[param_id] = {
            "name": str(raw.get("name") or "").strip(),
            "unit": str(raw.get("unit") or "").strip(),
        }
    return catalog


def main() -> None:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    dry_run = args.dry_run

    store = StagingStore()
    hl7_raw = store.read_latest_run("hope_lab_hl7_results")
    params_raw = store.read_latest_run("hope_lab_parameters")
    print(f"laboratory_hl7_results: {len(hl7_raw)} raw, laboratory_parameters: {len(params_raw)} raw")

    parameter_catalog = _build_parameter_catalog(params_raw)
    print(f"  resolved {len(parameter_catalog)} parameter names from catalog")

    payloads = transform(hl7_raw, parameter_catalog=parameter_catalog)
    print(f"lab_hl7_results: {len(payloads)} payloads ready")

    conn = None
    if not dry_run:
        from config import DATABASE_URL
        conn = get_conn(DATABASE_URL)
        print("Connected to PostgreSQL.")

    seen, upserted = load_lab_hl7_results(conn, payloads, dry_run=dry_run)
    if conn and not dry_run:
        log_run(conn, "lab_hl7_results", seen, upserted)
    print(f"lab_hl7_results: {seen} seen, {upserted} {'would upsert' if dry_run else 'upserted'} "
          f"(skipped = order not found in royan_lab_orders, or empty result content)")

    if conn:
        conn.close()


if __name__ == "__main__":
    main()
