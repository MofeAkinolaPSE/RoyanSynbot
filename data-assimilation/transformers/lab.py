"""Transform raw Hope lab order rows → royan_lab_orders."""
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
from transformers.field_maps import LAB_MAP

LAB_STATUSES = {"ordered", "sample_collected", "processing", "resulted", "sent_out", "cancelled"}


def transform(raw_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for row in raw_rows:
        mapped = apply_map(row, LAB_MAP)

        external_id = safe_str(mapped.get("external_id"))
        hope_patient_id = safe_str(mapped.get("_hope_patient_id"))
        if not external_id or not hope_patient_id:
            continue

        test_name = safe_str(
            mapped.get("test_name")
            or mapped.get("investigation")
            or mapped.get("lab_test")
            or mapped.get("test_type")
            or mapped.get("description")
            or mapped.get("service_name")
            or mapped.get("item_name")
        )
        out.append({
            "_hope_patient_id":     hope_patient_id,
            "_encounter_key":       f"lab:{external_id}",
            "test_name":            test_name or "Imported lab order",
            "test_code":            safe_str(mapped.get("test_code")),
            "urgency":              safe_str(mapped.get("urgency")) or "routine",
            "status":               status(mapped.get("status"), LAB_STATUSES, "ordered"),
            "sample_type":          safe_str(mapped.get("sample_type")),
            "ordered_by":           safe_str(mapped.get("ordered_by")) or "hope_ingest",
            "ordered_at":           safe_date(mapped.get("ordered_at")) or utcnow(),
            "notes":                safe_str(mapped.get("notes")),
            "external_source":      EXTERNAL_SOURCE,
            "external_id":          external_id,
            "external_updated_at":  safe_date(mapped.get("external_updated_at")) or utcnow(),
        })

    return out
