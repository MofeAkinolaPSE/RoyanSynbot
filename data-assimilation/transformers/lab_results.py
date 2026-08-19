"""Extract real lab result records from Hope's `laboratory_results` table
(staged as `hope_lab_results`) -> royan_lab_results.

This REPLACES the earlier design that tried to derive results from the
SAME row as the lab order (`raw_lab` / laboratory_test_orders) -- that
table has no result-bearing columns at all (result_summary/findings were
never real Hope columns on that table), so that path always emitted zero
rows. `laboratory_results` is Hope's real, separate HL7-shaped result
table, linked back to the order via `laboratory_test_order_id` (matching
royan_lab_orders.external_id).

Hope's `laboratory_results` table has ~170 HL7-interchange columns; only a
handful are ever populated for a routine (non-culture) result. A row is
only emitted when at least one real result-bearing field has content --
many rows in this table are themselves empty HL7 message shells with no
actual result, which is a genuine Hope data-quality characteristic, not
something this transform introduces.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from transformers._helpers import EXTERNAL_SOURCE, safe_date, safe_str, utcnow

# Result-bearing columns, in priority order for result_summary
_RESULT_TEXT_COLS = (
    "text", "value", "od_relevant_clinical_information", "opinion", "service_name",
)

# Columns collected into the result_data JSON blob when present
_RESULT_DATA_COLS = (
    "value", "text", "range", "opinion", "medication",
    "od_relevant_clinical_information", "gram_stain", "isolated_organism",
    "culture_media_used", "service_name", "ori_result_status",
)

_TRUE_ISH = {"1", "true", "yes", "y", "critical", "abnormal"}


def _to_bool(value: Any) -> bool:
    return str(value or "").strip().lower() in _TRUE_ISH


def transform(raw_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    seen_order_ids: set = set()

    for row in raw_rows:
        raw = {k.lower(): v for k, v in row.items()}

        lab_order_ext_id = safe_str(raw.get("laboratory_test_order_id"))
        hope_pid = safe_str(raw.get("patient_id"))
        if not lab_order_ext_id or not hope_pid:
            continue

        result_text: Optional[str] = None
        for col in _RESULT_TEXT_COLS:
            v = safe_str(raw.get(col))
            if v:
                result_text = v
                break

        reference_range = safe_str(raw.get("range"))
        has_result = bool(result_text) or bool(reference_range)
        if not has_result:
            continue  # empty HL7 shell row, no actual result content

        # Hope allows multiple result rows per order (amendments/panels) but
        # royan_lab_results has no external_id to upsert against safely for
        # this bulk import -- keep the first (usually earliest) real result
        # per order rather than risk unbounded duplicate inserts on rerun.
        if lab_order_ext_id in seen_order_ids:
            continue
        seen_order_ids.add(lab_order_ext_id)

        result_data: Dict[str, str] = {}
        for col in _RESULT_DATA_COLS:
            v = safe_str(raw.get(col))
            if v:
                result_data[col] = v

        resulted_at = (
            safe_date(raw.get("result_publish_date"))
            or safe_date(raw.get("modify_time"))
            or safe_date(raw.get("create_time"))
            or utcnow()
        )

        resulted_by = safe_str(raw.get("user_id")) or "hope_ingest"

        out.append({
            "_hope_patient_id":       hope_pid,
            "_hope_lab_order_ext_id": lab_order_ext_id,
            "result_data":            result_data if result_data else None,
            "result_summary":         result_text,
            "reference_range":        reference_range,
            "interpretation":         None,  # Hope has no structured interpretation field
            "resulted_by":            resulted_by,
            "resulted_at":            resulted_at,
            "is_critical":            _to_bool(raw.get("is_abnormal")),
            "notes":                  None,
        })

    return out
