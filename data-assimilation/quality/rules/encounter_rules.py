"""Domain-specific quality rules for the encounters entity."""
from __future__ import annotations

from typing import Any, Dict, List

ENCOUNTER_CONFIG: Dict[str, Any] = {
    "required_fields": ["patient_id", "encounter_type", "status"],
    "optional_fields": ["department", "consulting_doctor", "chief_complaint"],
    "date_fields": ["created_at", "triage_at", "discharge_at"],
    "max_age_days": None,
    "unique_key": "source_record_id",
}

_VALID_STATUSES = {
    "registered", "waiting", "triaged", "in_consultation",
    "billing_pending", "discharged", "cancelled", "admitted",
    "completed", "follow_up",
}

_VALID_TYPES = {
    "outpatient", "inpatient", "emergency", "day_case",
    "referral", "antenatal", "postnatal",
}


def extra_checks(record: Dict[str, Any]) -> List[str]:
    violations: List[str] = []

    status = str(record.get("status") or "").strip().lower()
    if status and status not in _VALID_STATUSES:
        violations.append(f"Unknown encounter status: '{status}'")

    enc_type = str(record.get("encounter_type") or "").strip().lower()
    if enc_type and enc_type not in _VALID_TYPES:
        violations.append(f"Unknown encounter_type: '{enc_type}'")

    # Discharge must be after triage (cross-field — supplement dimensions.check_consistency)
    triage = record.get("triage_at")
    discharge = record.get("discharge_at")
    if triage and discharge and str(discharge) < str(triage):
        violations.append(f"discharge_at ({discharge}) precedes triage_at ({triage})")

    return violations
