"""Transform raw Hope encounters → royan_encounters.

Handles two source shapes:
  1. Hope `diagnoses` table — outpatient consultation records.
  2. Traditional `admissions` table — inpatient ward admissions.

Encounter type is derived from available fields:
  - `admitted_at` or ward info present → inpatient
  - otherwise → outpatient (diagnoses row)

Ward/bed names are passed through as private fields (_ward_name, _bed_label)
so the loader can resolve them to integer FKs in royan_wards / royan_beds.

ICD codes are stored in both diagnosis_notes (as free text) and the
diagnosis_codes text[] column so queries can use either form.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from transformers._helpers import (
    EXTERNAL_SOURCE,
    apply_map,
    department,
    safe_date,
    safe_str,
    utcnow,
)
from transformers.field_maps import ADMISSION_MAP

_VALID_STATUSES = {
    "patient_registered", "triaged", "consulting",
    "lab_ordered", "pharmacy_dispensing", "billing_pending", "discharged",
}

_TRIAGE_LEVELS = {"immediate", "urgent", "less_urgent", "non_urgent"}

# Map common Hope triage labels to the CHECK constraint values
_TRIAGE_LEVEL_ALIASES = {
    "1": "immediate", "i": "immediate", "red": "immediate", "resuscitation": "immediate",
    "2": "urgent", "ii": "urgent", "orange": "urgent",
    "3": "less_urgent", "iii": "less_urgent", "yellow": "less_urgent",
    "4": "non_urgent", "iv": "non_urgent", "green": "non_urgent", "5": "non_urgent",
    "blue": "non_urgent", "white": "non_urgent",
}

# Recognise ICD-10 style codes (e.g. "J06.9", "B54", "Z00.00")
_ICD_PATTERN = re.compile(r'\b([A-Z]\d{2}(?:\.\d{1,4})?)\b')


def _normalise_triage_level(value: Any) -> Optional[str]:
    s = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if s in _TRIAGE_LEVELS:
        return s
    return _TRIAGE_LEVEL_ALIASES.get(s)


def _extract_icd_codes(raw_icd: Optional[str], notes: Optional[str]) -> List[str]:
    """Return a deduplicated list of ICD-10 codes found in icd_code field or notes."""
    codes: list = []
    seen: set = set()
    for text in (raw_icd or "", notes or ""):
        for match in _ICD_PATTERN.finditer(text.upper()):
            code = match.group(1)
            if code not in seen:
                seen.add(code)
                codes.append(code)
    return codes


def transform(raw_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for row in raw_rows:
        mapped = apply_map(row, ADMISSION_MAP)

        external_id = safe_str(mapped.get("external_id"))
        hope_patient_id = safe_str(mapped.get("_hope_patient_id"))
        if not external_id or not hope_patient_id:
            continue

        ward_name = safe_str(mapped.get("_ward_name"))
        bed_label = safe_str(mapped.get("_bed_label"))
        has_ward = bool(ward_name or bed_label)
        has_admission_date = bool(mapped.get("admitted_at"))
        encounter_type = "inpatient" if (has_ward or has_admission_date) else "outpatient"

        discharged = bool(safe_date(mapped.get("discharged_at")))
        consulted = bool(safe_date(mapped.get("consultation_at")))
        triage_at = safe_date(mapped.get("triage_at"))
        if discharged:
            enc_status = "discharged"
        elif consulted:
            enc_status = "consulting"
        elif triage_at:
            enc_status = "triaged"
        else:
            enc_status = "patient_registered"

        dept = department(mapped.get("department")) if encounter_type == "outpatient" else "Inpatient Ward"

        diagnosis_notes = safe_str(mapped.get("diagnosis_notes")) or None
        icd_raw = safe_str(mapped.get("icd_code"))

        # Append ICD code as bracketed tag to diagnosis_notes (legacy text search)
        if icd_raw:
            diagnosis_notes = (
                f"{diagnosis_notes} [{icd_raw}]".strip() if diagnosis_notes else f"[{icd_raw}]"
            )

        # Build structured diagnosis_codes array (ICD-10 codes found in both fields)
        diagnosis_codes = _extract_icd_codes(icd_raw, safe_str(mapped.get("diagnosis_notes"))) or None

        payload: Dict[str, Any] = {
            "_hope_patient_id":     hope_patient_id,
            "_ward_name":           ward_name,
            "_bed_label":           bed_label,
            "encounter_type":       encounter_type,
            "status":               enc_status,
            "department":           dept,
            "consulting_doctor":    safe_str(mapped.get("consulting_doctor")),
            "chief_complaint":      safe_str(mapped.get("chief_complaint")),
            "diagnosis_notes":      diagnosis_notes,
            "diagnosis_codes":      diagnosis_codes,
            # Triage
            "triage_level":         _normalise_triage_level(mapped.get("triage_level")),
            "triage_notes":         safe_str(mapped.get("triage_notes")),
            "triage_at":            triage_at,
            "triage_by":            safe_str(mapped.get("triage_by")),
            # Consultation / discharge
            "consultation_at":      safe_date(mapped.get("consultation_at")),
            "discharge_at":         safe_date(mapped.get("discharged_at")),
            "discharge_summary":    safe_str(mapped.get("discharge_summary")),
            "discharge_by":         safe_str(mapped.get("discharge_by")),
            "registered_by":        safe_str(mapped.get("registered_by")) or "hope_ingest",
            "external_source":      EXTERNAL_SOURCE,
            "external_id":          external_id,
            "external_updated_at":  safe_date(mapped.get("external_updated_at")) or utcnow(),
        }

        inv_json = mapped.get("_hope_investigation_json")
        if inv_json:
            payload["_hope_investigation_json"] = safe_str(inv_json)

        out.append(payload)

    return out
