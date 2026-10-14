"""Supplementary extraction: locations (to check for a distinct "Scancare"
radiology-branch location the user flagged should not be ignored) +
radiology_templates/radiology_template_texts (real radiology report
templates, previously assumed out-of-scope/"already known" but not
actually verified this session -- checking for real per-location content
now per explicit user instruction not to ignore Scancare's own templates).

Usage: python scripts/extract_locations_radiology_templates.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from extractors.mysql_dump import parse_dump
from staging.sqlite_store import StagingStore

DUMP_PATH = str(
    Path(__file__).resolve().parent.parent / "Docs" / "NEw Dump" / "db_drmnigeria-20260125.sql.gz"
)

TARGET_TABLES = {"locations", "radiology_templates", "radiology_template_texts"}
ENTITY_MAP = {
    "locations":                "hope_locations",
    "radiology_templates":      "hope_radiology_templates",
    "radiology_template_texts": "hope_radiology_template_texts",
}


def main() -> None:
    print(f"Streaming {DUMP_PATH} for tables: {sorted(TARGET_TABLES)}")
    t0 = time.time()
    data = parse_dump(DUMP_PATH, target_tables=TARGET_TABLES)
    print(f"Parse complete in {time.time() - t0:.0f}s")

    store = StagingStore()
    run_id = f"locations_radiology_templates_{int(time.time())}"

    for hope_table, entity in ENTITY_MAP.items():
        rows = data.get(hope_table, [])
        store.clear(entity)
        count = store.write(entity, rows, run_id=run_id)
        store.record_run(entity, "dump", count, run_id=run_id)
        print(f"  {hope_table} -> raw_{entity}: {count} rows staged")

    print("Done.")


if __name__ == "__main__":
    main()
