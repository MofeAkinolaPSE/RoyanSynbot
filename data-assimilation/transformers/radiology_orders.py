"""Extract Hope's radiology orders (`radiology_test_orders`, staged as
hope_radiology_test_orders) -> royan_radiology_orders.

CLOSES A KNOWN COVERAGE GAP. royan_radiology_orders held only 24,080 rows
against 56,536 real (non-deleted) Hope orders -- ~43%. The loaded ids are
scattered across the full 7..58,065 range rather than truncated at a
cut-off, which is the signature of per-row resolution failure rather than
an interrupted run. The original load had no traceable script and predates
the canonical patient-id remap fix; applying that remap here (Hope keeps
multiple patient rows per MRN, only the latest survives dedup into
royan_patients) is what recovers the missing ~32K.

Status mapping -- Hope uses three values, the live table's own vocabulary
is lowercase:
    Completed (40,379) -> completed
    Pending   (16,387) -> ordered
    Updated    (1,299) -> completed   (a Hope edit-marker on an already
                                       fulfilled order, not a distinct
                                       workflow state)

Report content (report/impression/radiologist_id/reported_at) is NOT set
here -- that comes from transformers/radiology_results.py, which is
UPDATE-shaped against these rows. load_radiology_results.py must be re-run
after this loader so the newly-inserted orders pick up their reports.
"""
from __future__ import annotations

from typing import Any, Dict, List

from transformers._helpers import EXTERNAL_SOURCE, normalize_text, safe_date, safe_str

_STATUS_MAP = {
    "completed": "completed",
    "updated":   "completed",
    "pending":   "ordered",
}


def transform(raw_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for row in raw_rows:
        if safe_str(row.get("is_deleted")) == "1":
            continue

        ext_id = safe_str(row.get("id"))
        hope_pid = safe_str(row.get("patient_id"))
        if not ext_id or not hope_pid:
            continue

        ordered_at = (
            safe_date(row.get("radiology_order_date"))
            or safe_date(row.get("create_time"))
            or safe_date(row.get("start_date"))
        )
        if not ordered_at:
            continue  # ordered_at is NOT NULL -- don't fabricate a timestamp

        status = _STATUS_MAP.get((safe_str(row.get("status")) or "").lower(), "ordered")

        clinical = normalize_text(safe_str(row.get("relevant_clinical_info")))
        reason = normalize_text(safe_str(row.get("reason_exam")))
        indication = "; ".join(p for p in (reason, clinical) if p) or None

        out.append({
            "_hope_patient_id":     hope_pid,
            "_ordered_at":          ordered_at,
            "test_name":            safe_str(row.get("testname")),
            "radiology_catalog_id": safe_str(row.get("radiology_id")),
            "ordering_doctor":      safe_str(row.get("primary_care_pro")),
            "ordered_by":           safe_str(row.get("created_by")),
            "order_date":           ordered_at,
            "ordered_at":           ordered_at,
            "status":               status,
            "clinical_indication":  indication,
            "notes":                normalize_text(safe_str(row.get("additional_notes"))),
            "external_source":      EXTERNAL_SOURCE,
            "external_id":          ext_id,
        })
    return out
