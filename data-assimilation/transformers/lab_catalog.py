"""Extract Royan's real lab test catalog from Hope's `laboratories` table
(staged as hope_laboratories) -> royan_lab_catalog (migration 130, already
exists with 20 hand-seeded rows). Distinct from the already-loaded lab
*orders* table (laboratory_test_orders) -- this is the master test/price
catalog that powers a lab-order autocomplete/dropdown.

`code` is NOT NULL UNIQUE on the live table. Only 35/271 real Hope rows
have a populated test_code; the rest fall back to a synthesized "HOPE{id}"
code (guaranteed unique since Hope ids are unique) rather than skipping
real test names for lack of a short code.

category_name/specimen_collection_type are empty on 100% of rows in this
dump (confirmed by direct check, not assumed) -- category/specimen_type
are left at the live table's own defaults ('other'/'blood') rather than
guessed.
"""
from __future__ import annotations

from typing import Any, Dict, List

from transformers._helpers import EXTERNAL_SOURCE, safe_str


def transform(raw_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for row in raw_rows:
        if safe_str(row.get("is_deleted")) == "1":
            continue
        name = safe_str(row.get("name"))
        ext_id = safe_str(row.get("id"))
        if not name or not ext_id:
            continue

        code = safe_str(row.get("test_code"))
        if not code:
            code = f"HOPE{ext_id}"

        out.append({
            "code":             code.upper()[:64],
            "loinc_code":       safe_str(row.get("lonic_code")),
            "name":             name,
            "is_active":        safe_str(row.get("is_active")) != "0",
            "external_source":  EXTERNAL_SOURCE,
            "external_id":      ext_id,
        })
    return out
