"""Transform raw Hope appointment rows → royan_appointment_slots + royan_appointments."""
from __future__ import annotations

import datetime as dt
from typing import Any, Dict, List, Tuple

from transformers._helpers import (
    EXTERNAL_SOURCE,
    apply_map,
    department,
    safe_date,
    safe_str,
    status,
    utcnow,
)
from transformers.field_maps import APPOINTMENT_MAP

APPT_STATUSES = {"booked", "confirmed", "arrived", "completed", "no_show", "cancelled", "rescheduled"}


def transform(raw_rows: List[Dict[str, Any]]) -> Tuple[List[Dict], List[Dict]]:
    """Returns (slot_payloads, appointment_payloads)."""
    slots: List[Dict[str, Any]] = []
    appointments: List[Dict[str, Any]] = []

    for row in raw_rows:
        mapped = apply_map(row, APPOINTMENT_MAP)

        external_id = safe_str(mapped.get("external_id"))
        if not external_id:
            continue

        hope_patient_id = safe_str(mapped.get("_hope_patient_id"))
        if not hope_patient_id:
            continue

        dept = department(mapped.get("department"))
        slot_date = safe_date(mapped.get("slot_date")) or dt.date.today().isoformat()
        slot_time = (safe_str(mapped.get("slot_time")) or "08:00")[:5]

        slots.append({
            "doctor_name":          safe_str(mapped.get("doctor_name")) or "Unassigned",
            "department":           dept,
            "slot_date":            slot_date,
            "slot_time":            slot_time,
            "duration_mins":        15,
            "max_patients":         1,
            "is_available":         False,
            "external_source":      EXTERNAL_SOURCE,
            "external_id":          f"{external_id}:slot",
            "external_updated_at":  safe_date(mapped.get("external_updated_at")) or utcnow(),
        })

        appointments.append({
            "_hope_patient_id":     hope_patient_id,
            "_slot_external_id":    f"{external_id}:slot",
            "status":               status(mapped.get("status"), APPT_STATUSES, "booked"),
            "reason":               safe_str(mapped.get("reason")),
            "booked_by":            "hope_ingest",
            "external_source":      EXTERNAL_SOURCE,
            "external_id":          external_id,
            "external_updated_at":  safe_date(mapped.get("external_updated_at")) or utcnow(),
        })

    return slots, appointments
