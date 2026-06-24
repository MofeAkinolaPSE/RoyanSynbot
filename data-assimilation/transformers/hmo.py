"""Transform raw Hope HMO and patient insurance rows."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from transformers._helpers import EXTERNAL_SOURCE, apply_map, safe_str, utcnow
from transformers.field_maps import HMO_MAP, PATIENT_INSURANCE_MAP


def transform_hmos(raw_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Returns payloads for royan_hmos."""
    out = []
    seen: set = set()

    for row in raw_rows:
        mapped = apply_map(row, HMO_MAP)

        external_id = safe_str(mapped.get("external_id"))
        name = safe_str(mapped.get("name"))
        if not name:
            continue
        if not external_id:
            external_id = f"hope-hmo-{name.lower().replace(' ', '-')}"
        if external_id in seen:
            continue
        seen.add(external_id)

        is_active_raw = mapped.get("is_active")
        is_active = True
        if is_active_raw is not None:
            val = str(is_active_raw).strip().lower()
            is_active = val in {"1", "true", "yes", "active"}

        out.append({
            "name":             name,
            "code":             safe_str(mapped.get("code")),
            "contact_phone":    safe_str(mapped.get("contact_phone")),
            "contact_email":    safe_str(mapped.get("contact_email")),
            "is_active":        is_active,
            "notes":            "Created from Hope bulk import",
            "external_source":  EXTERNAL_SOURCE,
            "external_id":      external_id,
        })

    return out


def transform_patient_insurance(raw_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Returns payloads for royan_patient_insurance (FKs resolved by loader)."""
    out = []
    seen: set = set()

    for row in raw_rows:
        mapped = apply_map(row, PATIENT_INSURANCE_MAP)

        external_id = safe_str(mapped.get("external_id"))
        hope_patient_id = safe_str(mapped.get("_hope_patient_id"))
        hope_hmo_id = safe_str(mapped.get("_hope_hmo_id"))
        if not hope_patient_id or not hope_hmo_id:
            continue
        if not external_id:
            external_id = f"{hope_patient_id}:{hope_hmo_id}"
        if external_id in seen:
            continue
        seen.add(external_id)

        is_primary_raw = mapped.get("is_primary")
        is_primary = True
        if is_primary_raw is not None:
            val = str(is_primary_raw).strip().lower()
            is_primary = val in {"1", "true", "yes", "primary"}

        out.append({
            "_hope_patient_id":     hope_patient_id,
            "_hope_hmo_id":         hope_hmo_id,
            "membership_id":        safe_str(mapped.get("membership_id")),
            "status":               safe_str(mapped.get("status")) or "active",
            "valid_from":           safe_str(mapped.get("valid_from")),
            "valid_to":             safe_str(mapped.get("valid_to")),
            "is_primary":           is_primary,
            "source":               "hope_ingest",
            "external_source":      EXTERNAL_SOURCE,
            "external_id":          external_id,
        })

    return out


def transform(raw_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Default entry point — transforms as HMO providers."""
    return transform_hmos(raw_rows)
