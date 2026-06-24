"""Transform raw Hope patient rows → royan_patients upsert payloads."""
from __future__ import annotations

from typing import Any, Dict, List

from transformers._helpers import (
    EXTERNAL_SOURCE,
    apply_map,
    blood_group,
    gender,
    generate_mrn_fallback,
    genotype,
    safe_date,
    safe_str,
    utcnow,
)
from transformers.field_maps import PATIENT_MAP


def transform(raw_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen_external_ids: set = set()
    # Keyed by MRN → keep the row with the latest external_updated_at.
    # Hope accumulates duplicate MRN rows over time (edits, archived copies).
    by_mrn: Dict[str, Dict] = {}

    for row in raw_rows:
        mapped = apply_map(row, PATIENT_MAP)

        external_id = safe_str(mapped.get("external_id"))
        if not external_id:
            for col in ("patient_id", "id", "patientid"):
                v = safe_str(row.get(col) or row.get(col.upper()))
                if v:
                    external_id = v
                    break
        if not external_id:
            continue
        if external_id in seen_external_ids:
            continue
        seen_external_ids.add(external_id)

        first = safe_str(mapped.get("first_name")) or "Unknown"
        last = safe_str(mapped.get("last_name")) or "Patient"
        mrn = safe_str(mapped.get("mrn")) or generate_mrn_fallback()
        updated_at = safe_date(mapped.get("external_updated_at")) or utcnow()

        # allergies: Hope stores as comma-separated string → PostgreSQL text[]
        allergies_raw = safe_str(mapped.get("allergies"))
        allergies = [a.strip() for a in allergies_raw.split(",") if a.strip()] if allergies_raw else None

        payload = {
            "mrn":                mrn,
            "first_name":         first,
            "last_name":          last,
            "date_of_birth":      safe_date(mapped.get("date_of_birth")),
            "gender":             gender(mapped.get("gender")),
            "phone":              safe_str(mapped.get("phone")),
            "email":              safe_str(mapped.get("email")),
            "address":            safe_str(mapped.get("address")),
            "next_of_kin_name":   safe_str(mapped.get("next_of_kin_name")),
            "next_of_kin_phone":  safe_str(mapped.get("next_of_kin_phone")),
            "blood_group":        blood_group(mapped.get("blood_group")),
            "genotype":           genotype(mapped.get("genotype")),
            "allergies":          allergies,
            "hmo_provider":       safe_str(mapped.get("hmo_provider")),
            "hmo_id":             safe_str(mapped.get("hmo_id")),
            "registered_by":      "hope_ingest",
            "registered_at":      safe_date(mapped.get("registered_at")) or utcnow(),
            "external_source":    EXTERNAL_SOURCE,
            "external_id":        external_id,
            "external_updated_at": safe_date(updated_at) or utcnow(),
        }

        existing = by_mrn.get(mrn)
        if not existing or (updated_at or "") >= (existing["external_updated_at"] or ""):
            by_mrn[mrn] = payload

    return list(by_mrn.values())
