"""Extract dispensing events from Hope pharmacy/prescription rows → royan_dispensing.

A dispensing record is only emitted when the prescription status indicates the
drug was actually dispensed (dispensed / partially_dispensed / issued / given).

Payloads are keyed by `_hope_rx_ext_id` (the Hope prescription external_id) so
the loader can look up royan_prescriptions.id.
"""
from __future__ import annotations

from typing import Any, Dict, List

from transformers._helpers import safe_date, safe_str, utcnow

_DISPENSED_STATUSES = {
    "dispensed", "partially_dispensed", "issued", "given",
    "collected", "sold", "complete", "completed",
}


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        v = float(str(value).replace(",", "")) if value is not None else default
        return v if v >= 0 else default
    except (ValueError, TypeError):
        return default


def transform(raw_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    seen_ext_ids: set = set()

    for row in raw_rows:
        raw = {k.lower(): v for k, v in row.items()}

        stat_raw = str(raw.get("status") or "").strip().lower().replace("-", "_").replace(" ", "_")
        if stat_raw not in _DISPENSED_STATUSES:
            continue

        ext_id = safe_str(
            raw.get("order_id") or raw.get("prescription_id") or raw.get("dispense_id") or raw.get("id")
        )
        hope_pid = safe_str(raw.get("patient_id") or raw.get("patientid"))
        if not ext_id or not hope_pid:
            continue
        if ext_id in seen_ext_ids:
            continue
        seen_ext_ids.add(ext_id)

        # Quantity dispensed — prefer qty_dispensed, fall back to quantity / qty
        qty = _to_float(
            raw.get("qty_dispensed") or raw.get("quantity_dispensed")
            or raw.get("quantity") or raw.get("qty"),
            default=1.0,
        )
        if qty <= 0:
            qty = 1.0

        drug_name = (
            safe_str(raw.get("drug_name"))
            or safe_str(raw.get("drug"))
            or safe_str(raw.get("medication"))
            or safe_str(raw.get("item_name"))
            or "Imported dispensing"
        )

        # Dispensed-at: updated_at is most likely to reflect actual dispense time
        dispensed_at = (
            safe_date(raw.get("dispensed_at"))
            or safe_date(raw.get("updated_at"))
            or safe_date(raw.get("modify_time"))
            or safe_date(raw.get("created_at"))
            or safe_date(raw.get("create_time"))
        )

        out.append({
            "_hope_patient_id": hope_pid,
            "_hope_rx_ext_id":  ext_id,
            "drug_name":        drug_name,
            "batch_number":     safe_str(raw.get("batch_no") or raw.get("batch_number") or raw.get("batch")),
            "expiry_date":      safe_date(raw.get("expiry_date") or raw.get("expiry") or raw.get("exp_date")),
            "quantity_dispensed": qty,
            "unit":             safe_str(raw.get("unit") or raw.get("unit_of_measure") or raw.get("form")) or "tablet",
            "dispensed_by":     safe_str(raw.get("dispensed_by") or raw.get("pharmacist") or raw.get("user_id")) or "hope_ingest",
            "dispensed_at":     dispensed_at or utcnow(),
            "unit_cost":        _to_float(raw.get("unit_cost") or raw.get("unit_price") or raw.get("price")),
            "counselling_given": False,
            "notes":            None,
        })

    return out
