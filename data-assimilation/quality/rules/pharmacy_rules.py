"""Domain-specific quality rules for the prescriptions entity."""
from __future__ import annotations

from typing import Any, Dict, List

PHARMACY_CONFIG: Dict[str, Any] = {
    "required_fields": ["patient_id", "drug_name", "dosage", "frequency"],
    "optional_fields": ["encounter_id", "drug_code", "route", "quantity", "duration_days"],
    "date_fields": ["prescribed_at"],
    "max_age_days": None,
    "unique_key": "source_record_id",
}

_VALID_ROUTES = {
    "oral", "iv", "im", "sc", "sublingual", "topical",
    "inhaled", "rectal", "nasal", "ophthalmic", "otic", "transdermal",
}

_VALID_STATUSES = {"active", "completed", "cancelled", "on_hold", "dispensed"}

_PLACEHOLDER_DRUGS = {"drug", "medication", "medicine", "tablet", "unknown", "n/a", "na", ""}


def extra_checks(record: Dict[str, Any]) -> List[str]:
    violations: List[str] = []

    drug = str(record.get("drug_name") or "").strip().lower()
    if drug in _PLACEHOLDER_DRUGS:
        violations.append(f"Placeholder drug_name: '{drug}'")

    route = str(record.get("route") or "oral").strip().lower()
    if route and route not in _VALID_ROUTES:
        violations.append(f"Unknown route of administration: '{route}'")

    status = str(record.get("status") or "").strip().lower()
    if status and status not in _VALID_STATUSES:
        violations.append(f"Unknown prescription status: '{status}'")

    qty = record.get("quantity")
    if qty is not None:
        try:
            if float(qty) < 0:
                violations.append(f"Negative quantity: {qty}")
        except (TypeError, ValueError):
            violations.append(f"Non-numeric quantity: '{qty}'")

    return violations
