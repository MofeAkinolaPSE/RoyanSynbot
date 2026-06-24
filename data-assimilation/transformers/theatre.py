"""Transform raw Hope surgical theatre rows → royan_operations_events payloads."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from transformers._helpers import EXTERNAL_SOURCE, apply_map, safe_str, utcnow
from transformers.field_maps import THEATRE_MAP

_VALID_STATUSES = {"scheduled", "in_progress", "completed", "cancelled", "abandoned"}
_VALID_ANAESTHESIA = {"general", "spinal", "epidural", "local", "sedation", "none", "other"}


def _normalise_status(val: Any) -> str:
    if not val:
        return "scheduled"
    norm = str(val).strip().lower()
    aliases = {
        "pending": "scheduled", "booked": "scheduled",
        "done": "completed", "finished": "completed",
        "in progress": "in_progress", "ongoing": "in_progress",
        "aborted": "abandoned",
    }
    norm = aliases.get(norm, norm)
    return norm if norm in _VALID_STATUSES else "scheduled"


def _normalise_anaesthesia(val: Any) -> Optional[str]:
    if not val:
        return None
    norm = str(val).strip().lower()
    aliases = {
        "ga": "general", "general anaesthesia": "general",
        "spinal block": "spinal", "epidural block": "epidural",
        "la": "local", "local anaesthesia": "local",
        "conscious sedation": "sedation",
    }
    norm = aliases.get(norm, norm)
    return norm if norm in _VALID_ANAESTHESIA else "other"


def _safe_int(val: Any) -> Optional[int]:
    try:
        return int(float(str(val))) if val is not None else None
    except (ValueError, TypeError):
        return None


def transform(raw_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Returns a list of dicts ready for royan_operations_events (event_type=theatre)."""
    out = []
    seen_external_ids: set = set()

    for row in raw_rows:
        mapped = apply_map(row, THEATRE_MAP)

        external_id = safe_str(mapped.get("external_id"))
        hope_patient_id = safe_str(mapped.get("_hope_patient_id"))
        if not external_id or not hope_patient_id:
            continue
        if external_id in seen_external_ids:
            continue
        seen_external_ids.add(external_id)

        procedure_name = safe_str(mapped.get("procedure_name")) or "Unknown Procedure"
        surgeon = safe_str(mapped.get("surgeon")) or "Unknown"
        status = _normalise_status(mapped.get("status"))
        scheduled_at = safe_str(mapped.get("scheduled_at"))
        started_at = safe_str(mapped.get("started_at"))
        ended_at = safe_str(mapped.get("ended_at"))
        anaesthesia_type = _normalise_anaesthesia(mapped.get("anaesthesia_type"))
        duration_mins = _safe_int(mapped.get("duration_mins"))
        theatre_room = safe_str(mapped.get("theatre_room"))
        anaesthetist = safe_str(mapped.get("anaesthetist"))
        scrub_nurse = safe_str(mapped.get("scrub_nurse"))
        notes = safe_str(mapped.get("notes"))

        event_date = (scheduled_at or started_at or utcnow())[:10]

        out.append({
            "_hope_patient_id":     hope_patient_id,
            "_encounter_key":       f"theatre:{external_id}",
            "event_type":           "theatre",
            "event_date":           event_date,
            "title":                procedure_name,
            "status":               status,
            "performed_by":         surgeon,
            "department":           "Surgery",
            "metadata": {
                "procedure_name":   procedure_name,
                "surgeon":          surgeon,
                "anaesthetist":     anaesthetist,
                "scrub_nurse":      scrub_nurse,
                "theatre_room":     theatre_room,
                "scheduled_at":     scheduled_at,
                "started_at":       started_at,
                "ended_at":         ended_at,
                "duration_mins":    duration_mins,
                "anaesthesia_type": anaesthesia_type,
                "notes":            notes,
            },
            "source_table":         "theatre_records",
            "external_source":      EXTERNAL_SOURCE,
            "external_id":          external_id,
            "external_updated_at":  safe_str(mapped.get("external_updated_at")) or utcnow(),
        })

    return out
