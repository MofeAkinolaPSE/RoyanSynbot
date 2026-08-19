"""Appointment slots and patient bookings."""
from __future__ import annotations

import asyncio
import logging
from datetime import date as Date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.constants import APPOINTMENT_STATUS_ALLOWED, HOSPITAL_DEPARTMENTS, TABLE_APPOINTMENT_SLOTS, TABLE_APPOINTMENTS, TABLE_PATIENTS
from src.db import audit_event, db
from src.middleware import require_role, verify_jwt
from src.routers.queue_clinical import open_encounter_for_patient
from src.services.realtime import realtime_hub

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/appointments", tags=["Appointments"])


class SlotCreate(BaseModel):
    doctor_name: Optional[str] = Field(None, max_length=200)
    provider_name: Optional[str] = Field(None, max_length=200)
    department: str = Field("OPD", max_length=100)
    slot_date: Optional[str] = None
    date: Optional[str] = None
    slot_time: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    duration_mins: Optional[int] = Field(None, gt=0)
    max_patients: Optional[int] = Field(None, ge=1)
    capacity: Optional[int] = Field(None, ge=1)

    model_config = {"extra": "ignore"}


class AppointmentBook(BaseModel):
    patient_id: int | str
    slot_id: int
    reason: Optional[str] = Field(None, max_length=1000)
    appointment_type: Optional[str] = Field(None, max_length=100)
    notes: Optional[str] = Field(None, max_length=2000)
    booked_by: Optional[str] = Field(None, max_length=200)

    model_config = {"extra": "ignore"}


class AppointmentCancel(BaseModel):
    cancellation_reason: Optional[str] = Field(None, max_length=1000)
    reason: Optional[str] = Field(None, max_length=1000)

    model_config = {"extra": "ignore"}


def _get_appointment(appointment_id: int) -> dict:
    result = db.table(TABLE_APPOINTMENTS).select("*").eq("id", appointment_id).limit(1).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail=f"Appointment {appointment_id} not found")
    return result.data[0]


def _get_slot(slot_id: int) -> dict:
    result = db.table(TABLE_APPOINTMENT_SLOTS).select("*").eq("id", slot_id).limit(1).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail=f"Slot {slot_id} not found")
    return result.data[0]


def _department(value: str | None) -> str:
    if value == "General OPD":
        return "OPD"
    return value if value in HOSPITAL_DEPARTMENTS else "OPD"


def _resolve_patient_id(value: int | str) -> int:
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if text.isdigit():
        return int(text)
    patient = db.table(TABLE_PATIENTS).select("id").eq("mrn", text.upper()).limit(1).execute()
    if not patient.data:
        raise HTTPException(status_code=404, detail=f"Patient '{value}' not found")
    return int(patient.data[0]["id"])


def _duration(start_time: str, end_time: str | None, fallback: int | None) -> int:
    if fallback:
        return fallback
    if not end_time:
        return 15
    try:
        sh, sm = [int(part) for part in start_time[:5].split(":")]
        eh, em = [int(part) for part in end_time[:5].split(":")]
        mins = (eh * 60 + em) - (sh * 60 + sm)
        return mins if mins > 0 else 15
    except Exception:
        return 15


# Statuses that no longer occupy a slot's capacity — mirrors the
# `status NOT IN ('cancelled', 'no_show')` filter already used in
# view_model_factory.py's active-appointments query.
_SLOT_FREEING_STATUSES = {"cancelled", "no_show"}


def _slot_booked_counts(slot_ids: list[int]) -> dict[int, int]:
    """Batch-count appointments still occupying capacity, per slot_id."""
    if not slot_ids:
        return {}
    rows = db.table(TABLE_APPOINTMENTS).select("slot_id,status").in_("slot_id", slot_ids).execute().data or []
    counts: dict[int, int] = {}
    for row in rows:
        if row.get("status") in _SLOT_FREEING_STATUSES:
            continue
        sid = row.get("slot_id")
        counts[sid] = counts.get(sid, 0) + 1
    return counts


def _compute_end_time(slot_time: str | None, duration_mins: int | None) -> str | None:
    """Derive end_time from slot_time + duration_mins (a real, correctly
    populated column — see create_slot's _duration())."""
    if not slot_time:
        return None
    try:
        h, m = [int(p) for p in str(slot_time)[:5].split(":")]
        total = (h * 60 + m + int(duration_mins or 15)) % (24 * 60)
        return f"{total // 60:02d}:{total % 60:02d}"
    except Exception:
        return None


def _enrich(appointments: list[dict], slots: list[dict] | None = None) -> list[dict]:
    if slots is None:
        slot_ids = list({a.get("slot_id") for a in appointments if a.get("slot_id")})
        slots = []
        if slot_ids:
            slots = db.table(TABLE_APPOINTMENT_SLOTS).select("*").in_("id", slot_ids).execute().data or []
    slot_map = {s["id"]: s for s in slots or []}
    patient_ids = list({a.get("patient_id") for a in appointments if a.get("patient_id")})
    patient_map: dict = {}
    if patient_ids:
        try:
            patients = db.table(TABLE_PATIENTS).select("id,mrn,first_name,last_name,phone,email,hmo_provider,hmo_id").in_("id", patient_ids).execute()
            patient_map = {p["id"]: p for p in patients.data or []}
        except Exception:
            patient_map = {}

    out = []
    for appt in appointments:
        slot = slot_map.get(appt.get("slot_id")) or {}
        patient = patient_map.get(appt.get("patient_id")) or {}
        patient_name = f"{patient.get('first_name', '')} {patient.get('last_name', '')}".strip() or None
        status = appt.get("status") or "booked"
        out.append({
            **appt,
            "patient": patient or None,
            "patient_name": patient_name,
            "mrn": patient.get("mrn"),
            "patient_phone": patient.get("phone"),
            "patient_email": patient.get("email"),
            "doctor_name": slot.get("doctor_name"),
            "department": slot.get("department"),
            "slot_date": slot.get("slot_date"),
            "slot_time": slot.get("slot_time"),
            "duration_mins": slot.get("duration_mins"),
            "appointment_type": appt.get("appointment_type") or appt.get("reason"),
            "slot": {
                "start_time": slot.get("slot_time"),
                "end_time": _compute_end_time(slot.get("slot_time"), slot.get("duration_mins")),
                "provider_name": slot.get("doctor_name"),
                "department": slot.get("department"),
            },
            "ui_status": "scheduled" if status in {"booked", "confirmed"} else status,
        })
    return out


@router.post("/slots", status_code=201)
async def create_slot(payload: SlotCreate, user=Depends(verify_jwt)):
    doctor = payload.doctor_name or payload.provider_name
    if not doctor:
        raise HTTPException(status_code=422, detail="doctor_name is required")
    slot_date = payload.slot_date or payload.date
    slot_time = payload.slot_time or payload.start_time
    if not slot_date or not slot_time:
        raise HTTPException(status_code=422, detail="slot_date and slot_time are required")
    data = {
        "doctor_name": doctor,
        "department": _department(payload.department),
        "slot_date": slot_date,
        "slot_time": slot_time[:5],
        "duration_mins": _duration(slot_time, payload.end_time, payload.duration_mins),
        "max_patients": payload.max_patients or payload.capacity or 1,
        "is_available": True,
    }
    try:
        result = db.table(TABLE_APPOINTMENT_SLOTS).insert(data).execute()
    except Exception as exc:
        logger.error("Slot creation failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to create slot")
    return {"ok": True, "slot": (result.data or [data])[0]}


@router.get("/slots")
async def list_slots(
    slot_date: Optional[str] = Query(None),
    date: Optional[str] = Query(None),
    department: Optional[str] = Query(None),
    doctor_name: Optional[str] = Query(None),
    provider_name: Optional[str] = Query(None),
    available_only: bool = Query(True),
    limit: int = Query(100, ge=1, le=500),
    user=Depends(verify_jwt),
):
    query = db.table(TABLE_APPOINTMENT_SLOTS).select("*").order("slot_date").order("slot_time").limit(limit)
    if slot_date or date:
        query = query.eq("slot_date", slot_date or date)
    if department:
        query = query.eq("department", _department(department))
    if doctor_name or provider_name:
        query = query.eq("doctor_name", doctor_name or provider_name)
    if available_only:
        query = query.eq("is_available", True)
    result = query.execute()
    raw_slots = result.data or []
    booked_counts = _slot_booked_counts([s["id"] for s in raw_slots])
    slots = []
    for slot in raw_slots:
        slots.append({
            **slot,
            "date": slot.get("slot_date"),
            "start_time": slot.get("slot_time"),
            "end_time": _compute_end_time(slot.get("slot_time"), slot.get("duration_mins")),
            "provider_name": slot.get("doctor_name"),
            "capacity": slot.get("max_patients"),
            "booked_count": booked_counts.get(slot["id"], 0),
        })
    return {"slots": slots, "count": len(slots)}


@router.delete("/slots/{slot_id}")
async def delete_slot(slot_id: int, user=Depends(require_role("admin"))):
    booked = db.table(TABLE_APPOINTMENTS).select("id").eq("slot_id", slot_id).neq("status", "cancelled").execute()
    if booked.data:
        raise HTTPException(status_code=409, detail="Cannot delete slot with active bookings")
    db.table(TABLE_APPOINTMENT_SLOTS).update({"is_available": False}).eq("id", slot_id).execute()
    return {"ok": True, "slot_id": slot_id, "status": "unavailable"}


def _calendar_appointments_core(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    doctor_name: Optional[str] = None,
    doctor_id: Optional[str] = None,
    department: Optional[str] = None,
    limit: int = 500,
) -> dict:
    """Plain (undecorated) core so it's safe to call directly from other
    functions in this module — a `Query(...)`-defaulted parameter left
    unspecified in a direct Python call stays a `Query` sentinel object
    (FastAPI only resolves it to `None` when a real HTTP request goes
    through dependency injection), which broke `.eq("doctor_id", ...)`
    with a psycopg2 "can't adapt type 'Query'" error whenever this was
    called internally without every param spelled out."""
    slots_query = db.table(TABLE_APPOINTMENT_SLOTS).select("*").limit(limit)
    if date_from:
        slots_query = slots_query.gte("slot_date", date_from)
    if date_to:
        slots_query = slots_query.lte("slot_date", date_to)
    if doctor_id:
        # Preferred: royan_staff.id FK (migration 146) — exact match, unlike the
        # free-text doctor_name below which only works if the caller knows the
        # exact display string a slot was booked under.
        slots_query = slots_query.eq("doctor_id", doctor_id)
    elif doctor_name:
        slots_query = slots_query.eq("doctor_name", doctor_name)
    if department:
        slots_query = slots_query.eq("department", _department(department))
    slots = slots_query.execute().data or []
    if not slots:
        return {"appointments": [], "count": 0}
    slot_ids = [s["id"] for s in slots]
    appointments = db.table(TABLE_APPOINTMENTS).select("*").in_("slot_id", slot_ids).limit(limit).execute().data or []
    enriched = _enrich(appointments, slots)
    enriched.sort(key=lambda row: (row.get("slot_date") or "", row.get("slot_time") or ""))
    return {"appointments": enriched, "count": len(enriched)}


@router.get("/calendar")
async def calendar_appointments(
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    doctor_name: Optional[str] = Query(None),
    doctor_id: Optional[str] = Query(None),
    department: Optional[str] = Query(None),
    limit: int = Query(500, ge=1, le=1000),
    user=Depends(verify_jwt),
):
    return _calendar_appointments_core(
        date_from=date_from, date_to=date_to, doctor_name=doctor_name,
        doctor_id=doctor_id, department=department, limit=limit,
    )


@router.get("/doctors")
async def list_doctors(user=Depends(verify_jwt)):
    # limit() was previously applied *before* dedup at 500 rows — with
    # 200k+ historical slot rows and numeric-junk doctor_name values from
    # the legacy Hope import sorting ahead of real names alphabetically,
    # every real doctor got crowded out of the first 500 sorted rows and
    # never appeared in the deduped result. Raised well past the real row
    # count so every distinct name is actually considered.
    result = db.table(TABLE_APPOINTMENT_SLOTS).select("doctor_name,department").order("doctor_name").limit(250_000).execute()
    seen: set = set()
    doctors = []
    for row in result.data or []:
        name = (row.get("doctor_name") or "").strip()
        if not name or name.isdigit():
            continue
        key = (name, row.get("department"))
        if key not in seen:
            seen.add(key)
            doctors.append({"doctor_name": name, "department": row.get("department")})
    return {"doctors": doctors, "count": len(doctors)}


@router.get("/next-slot")
async def next_available_slot(
    doctor_name: Optional[str] = Query(None),
    department: Optional[str] = Query(None),
    user=Depends(verify_jwt),
):
    today = Date.today().isoformat()
    query = db.table(TABLE_APPOINTMENT_SLOTS).select("*").eq("is_available", True).gte("slot_date", today).order("slot_date").order("slot_time").limit(1)
    if doctor_name:
        query = query.eq("doctor_name", doctor_name)
    if department:
        query = query.eq("department", _department(department))
    result = query.execute()
    return {"slot": (result.data or [None])[0]}


@router.post("/book", status_code=201)
async def book_appointment(payload: AppointmentBook, user=Depends(verify_jwt)):
    patient_id = _resolve_patient_id(payload.patient_id)
    slot = _get_slot(payload.slot_id)
    max_patients = int(slot.get("max_patients") or 1)
    booked_count = _slot_booked_counts([payload.slot_id]).get(payload.slot_id, 0)
    if not slot.get("is_available") or booked_count >= max_patients:
        raise HTTPException(status_code=409, detail="Slot is no longer available")
    data = {
        "patient_id": patient_id,
        "slot_id": payload.slot_id,
        "reason": payload.reason or payload.notes,
        "appointment_type": payload.appointment_type,
        "booked_by": payload.booked_by or user.get("sub") or "system",
        "status": "booked",
    }
    try:
        result = db.table(TABLE_APPOINTMENTS).insert(data).execute()
    except Exception as exc:
        logger.error("Appointment booking failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to book appointment")
    if booked_count + 1 >= max_patients:
        db.table(TABLE_APPOINTMENT_SLOTS).update({"is_available": False}).eq("id", payload.slot_id).execute()
    appointment = (result.data or [data])[0]
    audit_event("appointment_booked", {"patient_id": patient_id, "slot_id": payload.slot_id}, actor_id=user.get("sub"), subject_type="appointment", subject_id=str(appointment.get("id") or ""))
    asyncio.create_task(realtime_hub.broadcast("appointment_updates", {
        "event": "appointment_booked",
        "appointment_id": appointment.get("id"),
        "slot_date": slot.get("slot_date"),
    }))
    return {"ok": True, "appointment": _enrich([appointment], [slot])[0]}


@router.get("")
async def list_appointments(
    patient_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    slot_date: Optional[str] = Query(None),
    date: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None, description="End of the date range — defaults to `date`/`slot_date` (single day) when omitted"),
    limit: int = Query(50, ge=1, le=200),
    user=Depends(verify_jwt),
):
    if slot_date or date:
        return _calendar_appointments_core(date_from=slot_date or date, date_to=date_to or slot_date or date, limit=limit)
    query = db.table(TABLE_APPOINTMENTS).select("*").order("booked_at", desc=True).limit(limit)
    if patient_id:
        query = query.eq("patient_id", patient_id)
    if status:
        normalized = "booked" if status == "scheduled" else status
        if normalized not in APPOINTMENT_STATUS_ALLOWED:
            raise HTTPException(status_code=422, detail=f"Unknown status '{status}'")
        query = query.eq("status", normalized)
    appointments = query.execute().data or []
    enriched = _enrich(appointments)
    return {"appointments": enriched, "count": len(enriched)}


@router.get("/{appointment_id}")
async def get_appointment(appointment_id: int, user=Depends(verify_jwt)):
    return {"appointment": _enrich([_get_appointment(appointment_id)])[0]}


@router.patch("/{appointment_id}/arrive")
async def mark_arrived(appointment_id: int, user=Depends(verify_jwt)):
    """Marking an appointment arrived used to just flip its status column —
    nothing put the patient on the clinical queue, so "arrived" was a dead
    end front desk had to work around by separately opening an encounter
    from scratch. This now does what the status name implies: land the
    patient on the live queue (or attach to their existing active encounter,
    if front desk already opened one), same as walking up to the front desk
    in person."""
    appt = _get_appointment(appointment_id)
    if appt["status"] not in ("booked", "confirmed"):
        raise HTTPException(status_code=409, detail=f"Cannot mark arrived from status '{appt['status']}'")

    slot = _get_slot(appt["slot_id"]) if appt.get("slot_id") else {}
    department = _department(slot.get("department"))

    encounter, already_active = open_encounter_for_patient(
        appt["patient_id"],
        encounter_type="outpatient",
        department=department,
        chief_complaint=appt.get("reason"),
        actor_sub=user.get("sub"),
    )
    encounter_id = encounter.get("id")

    db.table(TABLE_APPOINTMENTS).update({"status": "arrived", "encounter_id": encounter_id}).eq("id", appointment_id).execute()
    audit_event(
        "appointment_arrived",
        {"encounter_id": encounter_id, "already_active": already_active},
        actor_id=user.get("sub"), subject_type="appointment", subject_id=str(appointment_id),
    )
    asyncio.create_task(realtime_hub.broadcast("appointment_updates", {
        "event": "appointment_arrived",
        "appointment_id": appointment_id,
        "encounter_id": encounter_id,
    }))
    return {
        "ok": True,
        "appointment_id": appointment_id,
        "status": "arrived",
        "encounter_id": encounter_id,
        "queue_number": encounter.get("queue_number"),
        "already_active": already_active,
    }


@router.patch("/{appointment_id}/complete")
async def complete_appointment(appointment_id: int, user=Depends(verify_jwt)):
    appt = _get_appointment(appointment_id)
    if appt["status"] not in ("arrived", "confirmed", "booked"):
        raise HTTPException(status_code=409, detail=f"Cannot complete appointment from status '{appt['status']}'")
    db.table(TABLE_APPOINTMENTS).update({"status": "completed"}).eq("id", appointment_id).execute()
    audit_event("appointment_completed", {}, actor_id=user.get("sub"), subject_type="appointment", subject_id=str(appointment_id))
    asyncio.create_task(realtime_hub.broadcast("appointment_updates", {"event": "appointment_completed", "appointment_id": appointment_id}))
    return {"ok": True, "appointment_id": appointment_id, "status": "completed"}


@router.patch("/{appointment_id}/cancel")
async def cancel_appointment(appointment_id: int, payload: AppointmentCancel, user=Depends(verify_jwt)):
    appt = _get_appointment(appointment_id)
    if appt["status"] in ("completed", "cancelled", "no_show"):
        raise HTTPException(status_code=409, detail=f"Cannot cancel appointment with status '{appt['status']}'")
    reason = payload.cancellation_reason or payload.reason
    updates = {"status": "cancelled"}
    if reason:
        updates["cancellation_reason"] = reason
    db.table(TABLE_APPOINTMENTS).update(updates).eq("id", appointment_id).execute()
    slot = _get_slot(appt["slot_id"])
    max_patients = int(slot.get("max_patients") or 1)
    booked_count = _slot_booked_counts([appt["slot_id"]]).get(appt["slot_id"], 0)
    db.table(TABLE_APPOINTMENT_SLOTS).update({"is_available": booked_count < max_patients}).eq("id", appt["slot_id"]).execute()
    audit_event("appointment_cancelled", {"reason": reason}, actor_id=user.get("sub"), subject_type="appointment", subject_id=str(appointment_id))
    asyncio.create_task(realtime_hub.broadcast("appointment_updates", {"event": "appointment_cancelled", "appointment_id": appointment_id}))
    return {"ok": True, "appointment_id": appointment_id, "status": "cancelled"}


@router.patch("/{appointment_id}/no-show")
async def mark_no_show(appointment_id: int, user=Depends(verify_jwt)):
    appt = _get_appointment(appointment_id)
    if appt["status"] in ("completed", "cancelled", "no_show"):
        raise HTTPException(status_code=409, detail=f"Cannot mark no-show from status '{appt['status']}'")
    db.table(TABLE_APPOINTMENTS).update({"status": "no_show"}).eq("id", appointment_id).execute()
    slot = _get_slot(appt["slot_id"])
    max_patients = int(slot.get("max_patients") or 1)
    booked_count = _slot_booked_counts([appt["slot_id"]]).get(appt["slot_id"], 0)
    db.table(TABLE_APPOINTMENT_SLOTS).update({"is_available": booked_count < max_patients}).eq("id", appt["slot_id"]).execute()
    audit_event("appointment_no_show", {}, actor_id=user.get("sub"), subject_type="appointment", subject_id=str(appointment_id))
    asyncio.create_task(realtime_hub.broadcast("appointment_updates", {"event": "appointment_no_show", "appointment_id": appointment_id}))
    return {"ok": True, "appointment_id": appointment_id, "status": "no_show"}


@router.post("/{appointment_id}/remind")
async def send_appointment_reminder(appointment_id: int, user=Depends(verify_jwt)):
    appt = _get_appointment(appointment_id)
    db.table(TABLE_APPOINTMENTS).update({"reminder_sent": True}).eq("id", appointment_id).execute()
    audit_event("appointment_reminder_marked", {}, actor_id=user.get("sub"), subject_type="appointment", subject_id=str(appointment_id))
    return {"sent": True, "channel": "marked_only", "appointment_id": appt["id"]}
