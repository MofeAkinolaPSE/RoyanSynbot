"""Transform raw Hope billing rows → royan_billing payloads.

Handles two Hope billing source shapes:

1. `service_bills` table — ward/service charges, may have per-shift amounts:
   - Columns: patient_id, service_id, morning, evening, night, date, create_time
   - morning/evening/night are ward billing amounts by shift; summed to ward_charges
   - category_hint derived as "ward" when shift columns are present

2. `consultant_billings` table — doctor consultation fees:
   - Columns: patient_id, consultant_id, amount, date
   - category_hint derived as "consultation"

3. Generic billing/invoice tables from other exports:
   - category_hint from category/service_type/charge_type column if present

Amount routing: raw_amount is routed to the correct fee column via route_amount()
from billing_contract.  All 6 fee columns are always populated (0.0 for unused).
"""
from __future__ import annotations

from typing import Any, Dict, List

from transformers._helpers import (
    EXTERNAL_SOURCE,
    apply_map,
    safe_date,
    safe_str,
    status,
    utcnow,
)
from transformers.field_maps import BILLING_MAP
from contracts.billing_contract import route_amount

BILL_STATUSES = {"pending", "partial", "paid", "waived", "disputed", "written_off"}

# Hope service_bills ward-shift columns
_SHIFT_COLS = {"morning", "evening", "night"}


def _to_float(val: Any) -> float:
    try:
        return float(str(val).replace(",", "")) if val is not None else 0.0
    except (ValueError, TypeError):
        return 0.0


def _detect_category_hint(raw_row: dict, mapped: dict) -> str:
    """Derive a category hint when the source row has no explicit category column.

    Detects service_bills pattern (shift columns) → "ward"
    Detects consultant_billings pattern (staff_id / consultant_id) → "consultation"
    Falls back to whatever the field_map picked up, or "misc".
    """
    existing = safe_str(mapped.get("category_hint"))
    if existing:
        return existing

    raw_lower = {k.lower(): v for k, v in raw_row.items()}
    # Ward billing: shift cols present AND have non-zero values
    if set(raw_lower.keys()) & _SHIFT_COLS:
        if any(_to_float(raw_lower.get(c)) > 0 for c in _SHIFT_COLS):
            return "ward"
    # Consultant billing: has consultant_id / staff_id
    if "consultant_id" in raw_lower or "staff_id" in raw_lower:
        return "consultation"
    return "misc"


def _sum_shift_amounts(raw_row: dict) -> float:
    """Sum morning + evening + night columns from service_bills ward rows."""
    total = 0.0
    raw_lower = {k.lower(): v for k, v in raw_row.items()}
    for col in _SHIFT_COLS:
        total += _to_float(raw_lower.get(col))
    return total


def transform(raw_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for row in raw_rows:
        # Skip soft-deleted Hope records
        raw_lower_map = {k.lower(): v for k, v in row.items()}
        if str(raw_lower_map.get("is_deleted", "0")).strip() not in ("0", "", "null", "None"):
            continue

        mapped = apply_map(row, BILLING_MAP)

        external_id = safe_str(mapped.get("external_id"))
        hope_patient_id = safe_str(mapped.get("_hope_patient_id"))
        if not external_id or not hope_patient_id:
            continue

        category_hint = _detect_category_hint(row, mapped)

        # Hope service_bills stores shift amounts in morning/evening/night columns.
        # Only use the shift sum when it is actually non-zero; otherwise fall back to
        # the `amount` column (mapped to raw_amount) which holds the real service charge.
        raw_lower_keys = set(raw_lower_map.keys())
        if raw_lower_keys & _SHIFT_COLS:
            shift_sum = _sum_shift_amounts(row)
            raw_amount = shift_sum if shift_sum > 0 else mapped.get("raw_amount")
        else:
            raw_amount = mapped.get("raw_amount")

        fee_cols = route_amount(raw_amount, category_hint)

        out.append({
            "_hope_patient_id":     hope_patient_id,
            "_encounter_key":       f"billing:{external_id}",
            "bill_number":          f"HOPE-{external_id}",
            "consultation_fee":     float(fee_cols["consultation_fee"]),
            "lab_charges":          float(fee_cols["lab_charges"]),
            "pharmacy_charges":     float(fee_cols["pharmacy_charges"]),
            "ward_charges":         float(fee_cols["ward_charges"]),
            "procedure_charges":    float(fee_cols["procedure_charges"]),
            "miscellaneous":        float(fee_cols["miscellaneous"]),
            "hmo_covered":          _to_float(mapped.get("hmo_covered")),
            "discount":             _to_float(mapped.get("discount")),
            "status":               status(mapped.get("status"), BILL_STATUSES, "pending"),
            "payment_method":       safe_str(mapped.get("payment_method")),
            "billed_by":            "hope_ingest",
            "billed_at":            safe_date(mapped.get("billed_at")) or utcnow(),
            "notes":                safe_str(mapped.get("notes")),
            "external_source":      EXTERNAL_SOURCE,
            "external_id":          external_id,
            "external_updated_at":  safe_date(mapped.get("external_updated_at")) or utcnow(),
        })

    return out
