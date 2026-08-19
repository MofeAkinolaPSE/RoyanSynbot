"""Extract real HMO/insurance claim records from Hope's `sub_claims` table
(staged as `hope_claims`) -> royan_insurance_claims.

Small table (real row count in the tens, not thousands) -- Hope's HMO
claim workflow was lightly used, but these are genuine claim records, not
placeholders. `sub_claims` links to a Hope *encounter* (`encounter_id`,
matching diagnoses.id / royan_encounters.external_id), not a bill, so the
loader resolves patient + a billing_id via the encounter rather than via
`_hope_billing_ext_id` the way payments/other entities do.
"""
from __future__ import annotations

from typing import Any, Dict, List

from transformers._helpers import EXTERNAL_SOURCE, safe_str, utcnow


def _to_float(value: Any) -> float:
    try:
        return float(str(value or 0).replace(",", ""))
    except (ValueError, TypeError):
        return 0.0


def transform(raw_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for row in raw_rows:
        raw = {k.lower(): v for k, v in row.items()}

        ext_id = safe_str(raw.get("id"))
        hope_encounter_id = safe_str(raw.get("encounter_id"))
        if not ext_id or not hope_encounter_id:
            continue

        claim_amount = _to_float(raw.get("amount"))
        if claim_amount <= 0:
            continue

        out.append({
            "_hope_encounter_ext_id": hope_encounter_id,
            "claim_amount":           round(claim_amount, 2),
            "status":                 "submitted",
            "submitted_at":           utcnow(),
            "authorisation_code":     None,
            "approved_amount":        None,
            "settled_at":             None,
            "notes":                  safe_str(raw.get("policy")) and f"Hope policy ref: {raw.get('policy')}",
            "external_source":        EXTERNAL_SOURCE,
            "external_id":            ext_id,
            "external_updated_at":    utcnow(),
        })

    return out
