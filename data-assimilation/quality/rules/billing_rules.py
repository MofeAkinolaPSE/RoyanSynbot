"""Domain-specific quality rules for the billing entity."""
from __future__ import annotations

from typing import Any, Dict, List

BILLING_CONFIG: Dict[str, Any] = {
    "required_fields": ["patient_id", "total_amount"],
    "optional_fields": ["encounter_id", "payment_method", "hmo_covered", "status"],
    "date_fields": ["billed_at", "payment_date"],
    "max_age_days": None,
    "unique_key": "source_record_id",
}

_VALID_STATUSES = {
    "draft", "submitted", "partially_paid", "paid",
    "waived", "written_off", "cancelled", "disputed",
}

_VALID_PAYMENT_METHODS = {
    "cash", "pos", "transfer", "hmo", "cheque", "online", "card", "waived",
}


def extra_checks(record: Dict[str, Any]) -> List[str]:
    violations: List[str] = []

    # Total amount must be non-negative
    total = record.get("total_amount")
    if total is not None:
        try:
            t = float(total)
            if t < 0:
                violations.append(f"Negative total_amount: {t}")
        except (TypeError, ValueError):
            violations.append(f"Non-numeric total_amount: '{total}'")

    # paid_amount cannot exceed total_amount
    paid = record.get("amount_paid") or record.get("paid_amount")
    if paid is not None and total is not None:
        try:
            if float(paid) > float(total) * 1.01:  # 1% tolerance for rounding
                violations.append(
                    f"amount_paid ({paid}) exceeds total_amount ({total})"
                )
        except (TypeError, ValueError):
            pass

    status = str(record.get("status") or "").strip().lower()
    if status and status not in _VALID_STATUSES:
        violations.append(f"Unknown billing status: '{status}'")

    method = str(record.get("payment_method") or "").strip().lower()
    if method and method not in _VALID_PAYMENT_METHODS:
        violations.append(f"Unknown payment_method: '{method}'")

    return violations
