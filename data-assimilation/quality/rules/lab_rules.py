"""Domain-specific quality rules for the lab_orders entity."""
from __future__ import annotations

from typing import Any, Dict, List

LAB_CONFIG: Dict[str, Any] = {
    "required_fields": ["patient_id", "test_name"],
    "optional_fields": ["encounter_id", "test_code", "urgency", "ordered_by", "sample_type"],
    "date_fields": ["ordered_at"],
    "max_age_days": None,
    "unique_key": "source_record_id",
    "placeholder_names": {
        "lab test", "laboratory test", "test", "investigation",
        "imported lab order", "n/a", "na", "unknown", "",
    },
}

_VALID_URGENCY = {"routine", "urgent", "stat", "asap"}
_VALID_STATUSES = {"pending", "collected", "processing", "resulted", "verified", "cancelled"}


def extra_checks(record: Dict[str, Any]) -> List[str]:
    violations: List[str] = []

    urgency = str(record.get("urgency") or "routine").strip().lower()
    if urgency not in _VALID_URGENCY:
        violations.append(f"Unknown urgency value: '{urgency}'")

    status = str(record.get("status") or "").strip().lower()
    if status and status not in _VALID_STATUSES:
        violations.append(f"Unknown lab order status: '{status}'")

    # test_name that is just a number is suspicious
    name = str(record.get("test_name") or "").strip()
    if name.isdigit():
        violations.append(f"test_name is a raw numeric ID: '{name}'")

    return violations
