"""Extract Royan's real diagnosis catalog from Hope's `diagnosis_masters`
table (staged as hope_diagnosis_masters) -> royan_diagnosis_catalog.

Confirmed by direct sample inspection: `diagnosis_masters` (184 rows) is the
real, clean coded catalog -- NOT the misleadingly-named `diagnoses` table
(256K rows), which turned out to be an unrelated per-appointment
TB-screening intake form, not diagnosis data at all (excluded entirely).

Hope's `icd_id` column holds SNOMED-CT-style numeric concept codes (e.g.
"53741008" for Coronary arteriosclerosis), not real ICD-10 codes (which look
like "J06.9" -- see the existing hand-seeded rows in this same table). The
target column is named icd_code and is NOT NULL + UNIQUE, so it needs a real
per-row identifier; icd_id is used as that identifier since it's the closest
thing Hope has, honestly labelled as a SNOMED id rather than pretended to be
ICD-10. Rows with no icd_id are dropped rather than given a fabricated code.
"""
from __future__ import annotations

from typing import Any, Dict, List

from transformers._helpers import EXTERNAL_SOURCE, safe_str


def transform(raw_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    seen_codes: set = set()
    for row in sorted(raw_rows, key=lambda r: int(r.get("id") or 0)):
        name = safe_str(row.get("diagnoses_name"))
        icd_id = safe_str(row.get("icd_id"))
        ext_id = safe_str(row.get("id"))
        if not name or not icd_id or not ext_id:
            continue
        if icd_id in seen_codes:
            continue
        seen_codes.add(icd_id)

        out.append({
            "icd_code":            icd_id,
            "description":         name,
            # Hope's diagnosis_masters has no category/specialty breakdown --
            # "General" is an honest placeholder, not a guessed classification.
            "category":            "General",
            "is_clinical_default": False,
            "is_active":           True,
            "external_source":     EXTERNAL_SOURCE,
            "external_id":         ext_id,
        })
    return out
