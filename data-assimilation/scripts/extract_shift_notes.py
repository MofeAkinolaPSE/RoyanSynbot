"""Supplementary extraction: shift_notes (68,196 rows per earlier audit) was
missed from extract_phase_a_reference_data.py's target list -- only its
smaller sibling nurse_notes (1,558 rows) was included there. Separate pass
since the combined run already completed.

Usage: python scripts/extract_shift_notes.py
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

TARGET_TABLES = {"shift_notes"}


def main() -> None:
    print(f"Streaming {DUMP_PATH} for tables: {sorted(TARGET_TABLES)}")
    t0 = time.time()
    data = parse_dump(DUMP_PATH, target_tables=TARGET_TABLES)
    print(f"Parse complete in {time.time() - t0:.0f}s")

    store = StagingStore()
    run_id = f"shift_notes_{int(time.time())}"
    rows = data.get("shift_notes", [])
    store.clear("hope_shift_notes")
    count = store.write("hope_shift_notes", rows, run_id=run_id)
    store.record_run("hope_shift_notes", "dump", count, run_id=run_id)
    print(f"  shift_notes -> raw_hope_shift_notes: {count} rows staged")
    print("Done.")


if __name__ == "__main__":
    main()
