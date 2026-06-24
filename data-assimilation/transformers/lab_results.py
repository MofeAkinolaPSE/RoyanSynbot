"""Extract lab result data from Hope lab order rows → royan_lab_results.

Hope stores the result in the same row as the order (result_summary, findings,
comments, etc.).  A result row is only emitted when there is actual result text
OR the order status indicates the test was resulted/completed.

The transformer produces payloads keyed by `_hope_lab_order_ext_id` (the Hope
lab order external_id) so the loader can look up royan_lab_orders.id.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from transformers._helpers import safe_date, safe_str, utcnow

# Hope status values that indicate a result exists
_RESULTED_STATUSES = {
    "resulted", "completed", "done", "complete", "verified",
    "resulted_positive", "resulted_negative", "reported",
}

# Result-bearing columns (in priority order for result_summary)
_RESULT_TEXT_COLS = (
    "result_summary", "result", "findings", "impression",
    "comments", "relevant_clinical_info",
)

# Columns whose values are collected into the result_data JSON blob
_RESULT_DATA_COLS = (
    "result_summary", "result", "findings", "impression",
    "comments", "relevant_clinical_info", "reference_range",
    "result_value", "result_unit", "unit",
)


def _to_bool(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "critical"}


def transform(raw_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    seen_ext_ids: set = set()

    for row in raw_rows:
        raw = {k.lower(): v for k, v in row.items()}

        ext_id = safe_str(raw.get("id") or raw.get("lab_id") or raw.get("order_id") or raw.get("request_id"))
        hope_pid = safe_str(raw.get("patient_id") or raw.get("patientid"))
        if not ext_id or not hope_pid:
            continue
        if ext_id in seen_ext_ids:
            continue

        # Collect the primary result summary text
        result_text: Optional[str] = None
        for col in _RESULT_TEXT_COLS:
            v = safe_str(raw.get(col))
            if v:
                result_text = v
                break

        stat_raw = str(raw.get("labdash_status") or raw.get("status") or "").strip().lower()
        has_result = bool(result_text) or stat_raw in _RESULTED_STATUSES
        if not has_result:
            continue

        seen_ext_ids.add(ext_id)

        # Build result_data JSON from all available result fields
        result_data: Dict[str, str] = {}
        for col in _RESULT_DATA_COLS:
            v = safe_str(raw.get(col))
            if v:
                result_data[col] = v

        # Resulted-at timestamp (try multiple column names)
        resulted_at = (
            safe_date(raw.get("resulted_at"))
            or safe_date(raw.get("result_date"))
            or safe_date(raw.get("updated_at"))
            or safe_date(raw.get("modify_time"))
        )

        # resulted_by: lab scientist — fall back to doctor_id / user_id
        resulted_by = (
            safe_str(raw.get("resulted_by"))
            or safe_str(raw.get("lab_scientist"))
            or safe_str(raw.get("doctor_id"))
            or safe_str(raw.get("user_id"))
            or "hope_ingest"
        )

        is_critical = _to_bool(raw.get("is_critical") or raw.get("critical"))

        out.append({
            "_hope_patient_id":       hope_pid,
            "_hope_lab_order_ext_id": ext_id,
            "result_data":            result_data if result_data else None,
            "result_summary":         result_text,
            "reference_range":        safe_str(raw.get("reference_range")),
            "interpretation":         None,   # Hope has no structured interpretation field
            "resulted_by":            resulted_by,
            "resulted_at":            resulted_at or utcnow(),
            "is_critical":            is_critical,
            "notes":                  None,
        })

    return out
