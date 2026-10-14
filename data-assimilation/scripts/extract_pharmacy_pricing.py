"""Pharmacy pricing chain extraction (2026-08-22, user directive:
"Pull that in as well. We might need it later").

`pharmacy_tariff_amounts` (91,036 staged rows) carries per-payer pharmacy
pricing but keys on `item_rate_id`, which resolves nowhere without
`pharmacy_item_rates`. That table was the one deliberate loose end left
after extract_final_sweep.py; this pass closes it.

Chain being completed:
    pharmacy_tariff_amounts.item_rate_id
      -> pharmacy_item_rates.id            (this extraction)
      -> pharmacy_item_rates.item_id
      -> pharmacy_items.id                 (already staged as hope_pharmacy_catalog
                                            -> loaded to royan_drug_formulary)
    pharmacy_tariff_amounts.tariff_standard_id
      -> tariff_standards.id               (already staged, -> royan_hmos)

Also grabs `pharmacy_item_details`'s sibling rate tables so the pharmacy
pricing picture is complete and nothing here needs revisiting:
    ot_pharmacy_item_rates / ot_pharmacy_items -- theatre pharmacy pricing
    pharmacy_item_rates                        -- main pharmacy pricing

Usage: python scripts/extract_pharmacy_pricing.py
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

TARGET_TABLES = {
    "pharmacy_item_rates",
    "ot_pharmacy_item_rates",
    "ot_pharmacy_items",
    "ot_item_categories",
    "ot_item_quantities",
    "ot_items",
}

ENTITY_MAP = {t: f"hope_{t}" for t in TARGET_TABLES}


def main() -> None:
    print(f"Streaming {DUMP_PATH} for {len(TARGET_TABLES)} tables")
    t0 = time.time()
    data = parse_dump(DUMP_PATH, target_tables=TARGET_TABLES)
    print(f"Parse complete in {time.time() - t0:.0f}s")

    store = StagingStore()
    run_id = f"pharmacy_pricing_{int(time.time())}"

    for hope_table, entity in sorted(ENTITY_MAP.items()):
        rows = data.get(hope_table, [])
        store.clear(entity)
        count = store.write(entity, rows, run_id=run_id)
        store.record_run(entity, "dump", count, run_id=run_id)
        print(f"  {hope_table:26s} -> {count:>8,} rows staged")

    print("Done.")


if __name__ == "__main__":
    main()
