"""Targeted extraction of `doctors` + `departments` from the local Hope
dump, staged for analysis/loading without re-parsing the 654MB file again.

`consultants` is deliberately excluded -- inspection showed it's a
referring-facility/external-referrer directory (refferer_doctor_id,
hospital_name, referal_spot_amount, doctor_commision), not Royan's own
staff, so it does not belong in royan_staff.
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

TARGET_TABLES = {"doctors", "departments"}
ENTITY_MAP = {"doctors": "hope_doctors", "departments": "hope_departments"}


def main() -> None:
    print(f"Streaming {DUMP_PATH} for tables: {sorted(TARGET_TABLES)}")
    t0 = time.time()
    data = parse_dump(DUMP_PATH, target_tables=TARGET_TABLES)
    print(f"Parse complete in {time.time() - t0:.0f}s")

    store = StagingStore()
    run_id = f"staff_{int(time.time())}"
    for hope_table, entity in ENTITY_MAP.items():
        rows = data.get(hope_table, [])
        store.clear(entity)
        count = store.write(entity, rows, run_id=run_id)
        store.record_run(entity, "dump", count, run_id=run_id)
        print(f"  {hope_table} -> raw_{entity}: {count} rows staged")


if __name__ == "__main__":
    main()
