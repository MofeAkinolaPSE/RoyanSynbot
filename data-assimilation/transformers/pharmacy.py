"""Transform raw Hope pharmacy/prescription rows → royan_prescriptions."""
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
from transformers.field_maps import PHARMACY_MAP

RX_STATUSES = {"pending", "dispensed", "partially_dispensed", "cancelled", "returned"}


def transform(raw_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for row in raw_rows:
        mapped = apply_map(row, PHARMACY_MAP)

        external_id = safe_str(mapped.get("external_id"))
        hope_patient_id = safe_str(mapped.get("_hope_patient_id"))
        if not external_id or not hope_patient_id:
            continue

        qty_raw = mapped.get("quantity")
        try:
            qty = int(float(str(qty_raw))) if qty_raw is not None else 1
        except (ValueError, TypeError):
            qty = 1

        out.append({
            "_hope_patient_id":     hope_patient_id,
            "_encounter_key":       f"{external_id}:encounter",
            "drug_name":            safe_str(mapped.get("drug_name")) or "Imported prescription",
            "drug_code":            safe_str(mapped.get("drug_code")),
            "dosage":               safe_str(mapped.get("dosage")) or "as directed",
            "frequency":            safe_str(mapped.get("frequency")) or "as directed",
            "duration":             safe_str(mapped.get("duration")),
            "route":                safe_str(mapped.get("route")) or "oral",
            "quantity":             qty,
            "unit":                 safe_str(mapped.get("unit")) or "unit",
            "special_instructions": safe_str(mapped.get("special_instructions")),
            "prescribed_by":        safe_str(mapped.get("prescribed_by")) or "hope_ingest",
            "prescribed_at":        safe_date(mapped.get("prescribed_at")) or utcnow(),
            "status":               status(mapped.get("status"), RX_STATUSES, "pending"),
            "external_source":      EXTERNAL_SOURCE,
            "external_id":          external_id,
            "external_updated_at":  safe_date(mapped.get("external_updated_at")) or utcnow(),
        })

    return out
