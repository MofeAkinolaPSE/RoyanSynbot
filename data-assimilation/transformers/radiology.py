"""Transform raw Hope radiology/imaging rows → royan_operations_events payloads."""
from __future__ import annotations

from typing import Any, Dict, List

from transformers._helpers import EXTERNAL_SOURCE, apply_map, safe_str, utcnow
from transformers.field_maps import RADIOLOGY_MAP

_STUDY_TYPE_ALIASES = {
    "x_ray": "xray", "x-ray": "xray", "plain film": "xray",
    "computed tomography": "ct", "ct scan": "ct",
    "magnetic resonance": "mri", "mri scan": "mri",
    "sonography": "ultrasound", "echo": "ultrasound",
    "fluoroscopy": "fluoroscopy",
    "mammogram": "mammography", "mammography": "mammography",
}
_VALID_STATUSES = {"ordered", "in_progress", "reported", "verified", "cancelled"}


def _normalise_study_type(val: Any) -> str:
    if not val:
        return "other"
    norm = str(val).strip().lower()
    return _STUDY_TYPE_ALIASES.get(norm, norm if norm in {
        "xray", "ultrasound", "ct", "mri", "fluoroscopy", "mammography", "other"
    } else "other")


def _normalise_status(val: Any) -> str:
    if not val:
        return "ordered"
    norm = str(val).strip().lower()
    aliases = {
        "pending": "ordered", "requested": "ordered", "new": "ordered",
        "done": "reported", "completed": "reported",
        "in progress": "in_progress",
    }
    norm = aliases.get(norm, norm)
    return norm if norm in _VALID_STATUSES else "ordered"


def transform(raw_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Returns a list of dicts ready for royan_operations_events (event_type=radiology)
    and also exposes _hope_patient_id + _encounter_key for the loader to resolve."""
    out = []
    seen_external_ids: set = set()

    for row in raw_rows:
        mapped = apply_map(row, RADIOLOGY_MAP)

        external_id = safe_str(mapped.get("external_id"))
        hope_patient_id = safe_str(mapped.get("_hope_patient_id"))
        if not external_id or not hope_patient_id:
            continue
        if external_id in seen_external_ids:
            continue
        seen_external_ids.add(external_id)

        ordering_doctor = safe_str(mapped.get("ordering_doctor")) or "Unknown"
        study_type = _normalise_study_type(mapped.get("study_type"))
        status = _normalise_status(mapped.get("status"))
        body_region = safe_str(mapped.get("body_region"))
        report_text = safe_str(mapped.get("report_text"))
        performed_at = safe_str(mapped.get("performed_at"))
        reported_at = safe_str(mapped.get("reported_at"))
        radiographer = safe_str(mapped.get("radiographer"))

        title = f"{study_type.upper()} — {body_region or 'unspecified'}"

        out.append({
            "_hope_patient_id":     hope_patient_id,
            "_encounter_key":       f"radiology:{external_id}",
            # Packed as operations_events fields
            "event_type":           "radiology",
            "event_date":           performed_at or utcnow()[:10],
            "title":                title,
            "status":               status,
            "performed_by":         radiographer or ordering_doctor,
            "department":           "Laboratory & Diagnostics",
            "metadata": {
                "study_type":       study_type,
                "body_region":      body_region,
                "ordering_doctor":  ordering_doctor,
                "report_text":      report_text,
                "performed_at":     performed_at,
                "reported_at":      reported_at,
            },
            "source_table":         "radiology_orders",
            "external_source":      EXTERNAL_SOURCE,
            "external_id":          external_id,
            "external_updated_at":  safe_str(mapped.get("external_updated_at")) or utcnow(),
        })

    return out
