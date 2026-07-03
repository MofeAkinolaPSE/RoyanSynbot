"""Domain-specific quality rules for the patients entity."""
from __future__ import annotations

import re
from typing import Any, Dict, List

# Override the base domain config with patient-specific settings
PATIENT_CONFIG: Dict[str, Any] = {
    "required_fields": ["first_name", "last_name"],
    "optional_fields": ["date_of_birth", "gender", "phone", "email", "mrn"],
    "date_fields": ["date_of_birth", "registered_at"],
    "gender_field": "gender",
    "mrn_field": "mrn",
    "max_age_days": None,
    "unique_key": "mrn",
}

_PHONE_RE = re.compile(r"^[\+\d\s\-\(\)]{7,20}$")


def extra_checks(record: Dict[str, Any]) -> List[str]:
    """Return additional violation strings beyond the seven standard dimensions."""
    violations: List[str] = []

    # Nigerian phone number sanity
    phone = str(record.get("phone") or "").strip()
    if phone and not _PHONE_RE.match(phone):
        violations.append(f"Suspicious phone format: '{phone}'")

    # Both first and last name cannot be 'Unknown' / 'N/A' simultaneously
    fn = str(record.get("first_name") or "").strip().lower()
    ln = str(record.get("last_name") or "").strip().lower()
    if fn in {"unknown", "n/a", "na", "."} and ln in {"unknown", "n/a", "na", "."}:
        violations.append("Both first_name and last_name are placeholder values")

    return violations
