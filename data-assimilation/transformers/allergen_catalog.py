"""Extract Royan's real allergen catalog from Hope's `allergy_masters` table
(staged as hope_allergy_masters) -> royan_allergen_catalog.

Hope's per-patient allergy tables (drug_allergies/patient_allergies/
env_allergies) are all confirmed empty -- no historical allergy events
exist to backfill royan_allergies. allergy_masters is a real First
Databank-style drug-class allergen reference vocabulary (e.g. "ACE
Inhibitors"), not Nigeria/Royan-specific but genuinely useful as an
allergen-name autocomplete catalog. status='I' (~53% of rows) reflects the
reference vendor's own taxonomy lifecycle (superseded in a later FDB
edition), not "wrong" data, so it's kept and mapped to is_active=false
rather than dropped -- broader autocomplete coverage is better than less.
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

        out.append({
            "name":              name,
            "concept_type":      safe_str(row.get("concepttype")),
            "is_active":         safe_str(row.get("status")) == "A",
            "external_source":   EXTERNAL_SOURCE,
            "external_id":       ext_id,
        })
    return out
