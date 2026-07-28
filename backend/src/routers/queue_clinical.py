"""Clinical queue and encounter workflow router."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.constants import (
    ENCOUNTER_STATUS_ALLOWED,
    ENCOUNTER_STATUS_TRANSITIONS,
    ENCOUNTER_TYPES,
    HOSPITAL_DEPARTMENTS,
    TABLE_BILLING,
    TABLE_ENCOUNTER_NOTES,
    TABLE_ENCOUNTERS,
    TABLE_LAB_ORDERS,
    TABLE_PATIENTS,
    TABLE_PRESCRIPTIONS,
    TABLE_STAFF,
    TRIAGE_LEVELS,
)
from src.cache import invalidate_cache_tags
from src.db import audit_event, db
from src.middleware import verify_jwt
from src.services.realtime import realtime_hub

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/queue", tags=["Clinical Queue"])

# Department → short queue prefix mapping
_DEPT_PREFIX: dict[str, str] = {
    "OPD": "OPD",
    "A&E": "AE",
    "Maternity": "MAT",
    "Surgery": "SUR",
    "Inpatient Ward": "IPD",
    "Laboratory & Diagnostics": "LAB",
    "Pharmacy": "PHM",
    "Billing & Finance": "BIL",
    "Administration": "ADM",
    "Maintenance & Facilities": "MNT",
}


class EncounterCreate(BaseModel):
    patient_id: int | str
    encounter_type: str = "outpatient"
    department: Optional[str] = "OPD"
    chief_complaint: Optional[str] = None
    registered_by: Optional[str] = None


class TriageRequest(BaseModel):
    triage_level: Optional[str] = None
    triage_priority: Optional[str] = None
    triage_notes: Optional[str] = None
    chief_complaint: Optional[str] = None
    triage_by: Optional[str] = None

    model_config = {"extra": "ignore"}


class ConsultRequest(BaseModel):
    doctor_id: Optional[str] = None
    consulting_doctor: Optional[str] = None
    diagnosis_codes: Optional[list[str]] = None
    diagnosis_notes: Optional[str] = None


class AdvanceRequest(BaseModel):
    new_status: str
    notes: Optional[str] = None


class DischargeRequest(BaseModel):
    discharge_summary: str = Field(..., min_length=1)


class CallPatientRequest(BaseModel):
    room: Optional[str] = None
    discharge_by: Optional[str] = None


class EncounterNoteCreate(BaseModel):
    note_type: str = "general"  # general | assessment | plan | soap
    content: str = Field(..., min_length=1)


def _get_encounter(encounter_id: int) -> dict:
    result = db.table(TABLE_ENCOUNTERS).select("*").eq("id", encounter_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail=f"Encounter {encounter_id} not found")
    return result.data[0]


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


def _assert_transition(current: str, target: str) -> None:
    if target not in ENCOUNTER_STATUS_ALLOWED:
        raise HTTPException(status_code=422, detail=f"Unknown encounter status '{target}'")
    if target not in ENCOUNTER_STATUS_TRANSITIONS.get(current, set()):
        raise HTTPException(
            status_code=409,
            detail=f"Cannot transition from '{current}' to '{target}'. Allowed: {sorted(ENCOUNTER_STATUS_TRANSITIONS.get(current, set()))}",
        )


def _enrich_encounters(rows: list[dict]) -> list[dict]:
    patient_ids = list({row.get("patient_id") for row in rows if row.get("patient_id") is not None})
    patient_map: dict = {}
    if patient_ids:
        try:
            patients = (
                db.table(TABLE_PATIENTS)
                .select("id,mrn,first_name,last_name,phone,hmo_provider,hmo_id")
                .in_("id", patient_ids)
                .execute()
            )
            patient_map = {row["id"]: row for row in patients.data or []}
        except Exception:
            patient_map = {}

    enriched: list[dict] = []
    for row in rows:
        patient = patient_map.get(row.get("patient_id")) or {}
        name = f"{patient.get('first_name', '')} {patient.get('last_name', '')}".strip()
        enriched.append({
            **row,
            "patient": patient or None,
            "patient_name": name or None,
            "mrn": patient.get("mrn"),
            "hmo_provider": patient.get("hmo_provider"),
            "hmo_id": patient.get("hmo_id"),
        })
    return enriched


@router.post("/encounters", status_code=201)
async def open_encounter(payload: EncounterCreate, user=Depends(verify_jwt)):
    if payload.encounter_type not in ENCOUNTER_TYPES:
        raise HTTPException(status_code=422, detail=f"encounter_type must be one of {sorted(ENCOUNTER_TYPES)}")
    if payload.department and payload.department not in HOSPITAL_DEPARTMENTS:
        raise HTTPException(status_code=422, detail=f"Unknown department '{payload.department}'")

    patient_id = _resolve_patient_id(payload.patient_id)
    patient = db.table(TABLE_PATIENTS).select("id,mrn,first_name,last_name").eq("id", patient_id).limit(1).execute()
    if not patient.data:
        raise HTTPException(status_code=404, detail=f"Patient {payload.patient_id} not found")

    # Don't silently create a second open encounter for a patient who already has one —
    # this is what produced duplicate queue numbers when the CPRS page suggested
    # "New Encounter" for a patient whose Front-Desk encounter just hadn't refreshed yet.
    existing = (
        db.table(TABLE_ENCOUNTERS)
        .select("id,queue_number,status,department,encounter_type,created_at")
        .eq("patient_id", patient_id)
        .neq("status", "discharged")
        .is_("external_source", None)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if existing.data:
        return {"ok": True, "encounter": existing.data[0], "already_active": True}

    data = {
        "patient_id": patient_id,
        "encounter_type": payload.encounter_type,
        "department": payload.department or "OPD",
        "chief_complaint": payload.chief_complaint,
        "status": "patient_registered",
        "registered_by": payload.registered_by or user.get("sub") or "system",
    }
    try:
        result = db.table(TABLE_ENCOUNTERS).insert(data).execute()
    except Exception as exc:
        logger.error("Encounter creation failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to open encounter")

    encounter = (result.data or [data])[0]

    # Generate queue number (e.g. OPD-001) and write back to DB
    queue_number: Optional[str] = None
    enc_id = encounter.get("id")
    if enc_id is not None:
        try:
            dept = data["department"]
            prefix = _DEPT_PREFIX.get(dept, dept[:3].upper().replace("/", "").replace(" ", ""))
            today = datetime.now(timezone.utc).date().isoformat()
            conn = db.pool.getconn()
            try:
                cur = conn.cursor()
                # Serialize the count-then-write below across concurrent requests for the
                # same department+day so two near-simultaneous encounters can never be
                # handed the same queue number. Postgres releases this lock automatically
                # at the end of the transaction (conn.commit() below).
                cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (f"queue:{dept}:{today}",))
                cur.execute(
                    "SELECT COUNT(*) FROM public.royan_encounters WHERE department = %s AND created_at::date = %s AND external_source IS NULL",
                    (dept, today),
                )
                seq = int(cur.fetchone()[0] or 0)
                queue_number = f"{prefix}-{seq:03d}"
                cur.execute("UPDATE public.royan_encounters SET queue_number = %s WHERE id = %s", (queue_number, enc_id))
                conn.commit()
                encounter["queue_number"] = queue_number
            finally:
                db.pool.putconn(conn)
        except Exception as exc:
            logger.warning("Queue number generation failed: %s", exc)

    audit_event(
        "encounter_opened",
        {"patient_id": patient_id, "queue_number": queue_number},
        actor_id=user.get("sub"),
        subject_type="encounter",
        subject_id=str(enc_id or ""),
    )
    invalidate_cache_tags("hospital", "patient_flow", "queue", "encounters", "executive")

    pt = patient.data[0]
    asyncio.create_task(realtime_hub.broadcast("encounter_updates", {
        "event": "encounter_opened",
        "encounter_id": enc_id,
        "queue_number": queue_number,
        "department": data["department"],
        "patient_name": f"{pt.get('first_name', '')} {pt.get('last_name', '')}".strip(),
    }))

    return {"ok": True, "encounter": encounter}


@router.get("/encounters")
async def list_encounters(
    status: Optional[str] = Query(None),
    department: Optional[str] = Query(None),
    doctor: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    user=Depends(verify_jwt),
):
    # Live queue = native encounters only (external_source IS NULL). Any
    # imported/synthetic row — Hope historical data or a synbot_repair
    # ancillary bucket (see repair_shared_encounter_keys.py) — must never
    # count as an active queue entry. This filter has to run in SQL BEFORE
    # the limit: filtering client-side after LIMIT (the previous approach,
    # and it only excluded 'hope') let a batch of same-timestamp synthetic
    # rows silently crowd out real entries whenever they sorted first.
    query = (
        db.table(TABLE_ENCOUNTERS)
        .select("*")
        .is_("external_source", None)
        .order("created_at", desc=True)
        .limit(limit)
    )
    if status:
        if status not in ENCOUNTER_STATUS_ALLOWED:
            raise HTTPException(status_code=422, detail=f"Unknown status '{status}'")
        query = query.eq("status", status)
    if department:
        query = query.eq("department", department)
    if doctor:
        # `doctor` is the assigned doctor's royan_staff.id (uuid FK) — the
        # legacy free-text `consulting_doctor` column is display-only and
        # never a reliable match target (nurses type arbitrary names into it).
        query = query.eq("doctor_id", doctor)
    result = query.execute()
    encounters = _enrich_encounters(result.data or [])
    return {"encounters": encounters, "count": len(encounters)}


@router.get("/encounters/{encounter_id}")
async def get_encounter(encounter_id: int, user=Depends(verify_jwt)):
    encounter = _get_encounter(encounter_id)
    labs = db.table(TABLE_LAB_ORDERS).select("*").eq("encounter_id", encounter_id).order("ordered_at", desc=True).execute().data or []
    prescriptions = db.table(TABLE_PRESCRIPTIONS).select("*").eq("encounter_id", encounter_id).order("prescribed_at", desc=True).execute().data or []
    bills = db.table(TABLE_BILLING).select("*").eq("encounter_id", encounter_id).order("billed_at", desc=True).execute().data or []
    return {"encounter": _enrich_encounters([encounter])[0], "lab_orders": labs, "prescriptions": prescriptions, "bills": bills}


@router.post("/encounters/{encounter_id}/triage")
async def triage_encounter(encounter_id: int, payload: TriageRequest, user=Depends(verify_jwt)):
    encounter = _get_encounter(encounter_id)
    _assert_transition(encounter["status"], "triaged")

    triage_level = payload.triage_level or payload.triage_priority
    if triage_level == "standard":
        triage_level = "non_urgent"
    if triage_level not in TRIAGE_LEVELS:
        raise HTTPException(status_code=422, detail=f"triage_level must be one of {sorted(TRIAGE_LEVELS)}")

    updates = {
        "status": "triaged",
        "triage_level": triage_level,
        "triage_notes": payload.triage_notes,
        "chief_complaint": payload.chief_complaint or encounter.get("chief_complaint"),
        "triage_by": payload.triage_by or user.get("sub"),
        "triage_at": datetime.now(timezone.utc).isoformat(),
    }
    db.table(TABLE_ENCOUNTERS).update(updates).eq("id", encounter_id).execute()
    audit_event("encounter_triaged", {"level": triage_level}, actor_id=user.get("sub"), subject_type="encounter", subject_id=str(encounter_id))
    return {"ok": True, "encounter_id": encounter_id, "status": "triaged"}


@router.post("/encounters/{encounter_id}/nurse-done")
async def nurse_assessment_done(encounter_id: int, user=Depends(verify_jwt)):
    """Nurse marks vitals recorded — patient ready for doctor."""
    encounter = _get_encounter(encounter_id)
    _assert_transition(encounter["status"], "nurse_assessment")
    now = datetime.now(timezone.utc).isoformat()
    db.table(TABLE_ENCOUNTERS).update({"status": "nurse_assessment", "nurse_done_at": now}).eq("id", encounter_id).execute()
    invalidate_cache_tags("hospital", "queue", "patient_flow", "encounters")
    audit_event("nurse_assessment_done", {}, actor_id=user.get("sub"), subject_type="encounter", subject_id=str(encounter_id))
    asyncio.create_task(realtime_hub.broadcast("encounter_updates", {
        "event": "nurse_done",
        "encounter_id": encounter_id,
        "queue_number": encounter.get("queue_number"),
        "department": encounter.get("department"),
    }))
    return {"ok": True, "encounter_id": encounter_id, "status": "nurse_assessment"}


@router.post("/encounters/{encounter_id}/call")
async def call_patient(encounter_id: int, payload: CallPatientRequest, user=Depends(verify_jwt)):
    """Doctor calls patient into the consulting room — appears on display board."""
    encounter = _get_encounter(encounter_id)
    _assert_transition(encounter["status"], "called")
    now = datetime.now(timezone.utc).isoformat()
    updates = {"status": "called", "called_at": now}
    if payload.room:
        updates["consulting_room"] = payload.room
    db.table(TABLE_ENCOUNTERS).update(updates).eq("id", encounter_id).execute()
    invalidate_cache_tags("hospital", "queue", "patient_flow", "encounters")
    audit_event("patient_called", {"room": payload.room}, actor_id=user.get("sub"), subject_type="encounter", subject_id=str(encounter_id))
    asyncio.create_task(realtime_hub.broadcast("encounter_updates", {
        "event": "patient_called",
        "encounter_id": encounter_id,
        "queue_number": encounter.get("queue_number"),
        "department": encounter.get("department"),
        "room": payload.room,
    }))
    return {"ok": True, "encounter_id": encounter_id, "status": "called", "room": payload.room}


@router.post("/encounters/{encounter_id}/consult")
async def record_consultation(encounter_id: int, payload: ConsultRequest, user=Depends(verify_jwt)):
    encounter = _get_encounter(encounter_id)
    # ENCOUNTER_STATUS_TRANSITIONS allows a "consulting" self-loop specifically so
    # this can be re-called on an already-consulting encounter to (re)assign the
    # doctor without requiring a status change.
    _assert_transition(encounter["status"], "consulting")

    # Resolve the doctor as a stable royan_staff.id FK, not a free-text name:
    # a hand-typed name (or the submitting nurse/receptionist's own JWT sub)
    # can never match the doctor_id filter the Doctor Dashboard queries by.
    # Explicit doctor_id from the request (doctor picker) wins; otherwise, if
    # the caller is themselves a doctor self-assigning from their own
    # dashboard, fall back to their own staff record.
    doctor_id = payload.doctor_id
    if not doctor_id and "doctor" in (user.get("roles") or []):
        caller_staff = (
            db.table(TABLE_STAFF).select("id").eq("user_id", user.get("sub")).limit(1).execute()
        )
        if caller_staff.data:
            doctor_id = caller_staff.data[0]["id"]

    doctor_name = payload.consulting_doctor
    if doctor_id and not doctor_name:
        staff = db.table(TABLE_STAFF).select("full_name,email").eq("id", doctor_id).limit(1).execute()
        if staff.data:
            doctor_name = staff.data[0].get("full_name") or staff.data[0].get("email")
    doctor_name = doctor_name or "doctor"

    updates = {
        "status": "consulting",
        "doctor_id": doctor_id,
        "consulting_doctor": doctor_name,
        "diagnosis_codes": payload.diagnosis_codes or [],
        "diagnosis_notes": payload.diagnosis_notes,
        "consultation_at": datetime.now(timezone.utc).isoformat(),
    }
    db.table(TABLE_ENCOUNTERS).update(updates).eq("id", encounter_id).execute()
    invalidate_cache_tags("hospital", "queue", "patient_flow", "encounters")
    audit_event("encounter_consulting", {"doctor": doctor_name, "doctor_id": doctor_id}, actor_id=user.get("sub"), subject_type="encounter", subject_id=str(encounter_id))
    asyncio.create_task(realtime_hub.broadcast("encounter_updates", {
        "event": "consultation_started",
        "encounter_id": encounter_id,
        "queue_number": encounter.get("queue_number"),
        "department": encounter.get("department"),
        "doctor": doctor_name,
        "doctor_id": doctor_id,
    }))
    return {"ok": True, "encounter_id": encounter_id, "status": "consulting", "doctor_id": doctor_id}


@router.post("/encounters/{encounter_id}/advance")
async def advance_encounter(encounter_id: int, payload: AdvanceRequest, user=Depends(verify_jwt)):
    encounter = _get_encounter(encounter_id)
    _assert_transition(encounter["status"], payload.new_status)
    if payload.new_status == "discharged":
        raise HTTPException(status_code=400, detail="Use POST /encounters/{id}/discharge to discharge a patient")
    db.table(TABLE_ENCOUNTERS).update({"status": payload.new_status}).eq("id", encounter_id).execute()
    audit_event("encounter_advanced", {"to": payload.new_status, "notes": payload.notes}, actor_id=user.get("sub"), subject_type="encounter", subject_id=str(encounter_id))
    return {"ok": True, "encounter_id": encounter_id, "status": payload.new_status}


@router.post("/encounters/{encounter_id}/discharge")
async def discharge_encounter(encounter_id: int, payload: DischargeRequest, user=Depends(verify_jwt)):
    encounter = _get_encounter(encounter_id)
    _assert_transition(encounter["status"], "discharged")

    now = datetime.now(timezone.utc).isoformat()
    updates = {
        "status": "discharged",
        "discharge_summary": payload.discharge_summary,
        "discharge_by": user.get("sub") or "system",
        "discharge_at": now,
    }
    db.table(TABLE_ENCOUNTERS).update(updates).eq("id", encounter_id).execute()
    audit_event("encounter_discharged", {"summary_len": len(payload.discharge_summary)}, actor_id=user.get("sub"), subject_type="encounter", subject_id=str(encounter_id))
    return {"ok": True, "encounter_id": encounter_id, "status": "discharged", "discharged_at": now}


# ─── Encounter Notes ──────────────────────────────────────────────────────────

@router.post("/encounters/{encounter_id}/notes", status_code=201)
async def add_encounter_note(encounter_id: int, payload: EncounterNoteCreate, user=Depends(verify_jwt)):
    """Add a free-text clinical note to an encounter (general, assessment, plan, or SOAP)."""
    encounter = _get_encounter(encounter_id)
    data = {
        "encounter_id": encounter_id,
        "patient_id": encounter["patient_id"],
        "note_type": payload.note_type,
        "content": payload.content,
        "author_id": user.get("sub"),
        "author_name": user.get("email") or user.get("sub"),
    }
    try:
        result = db.table(TABLE_ENCOUNTER_NOTES).insert(data).execute()
    except Exception as exc:
        logger.error("Encounter note insert failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to save encounter note")
    note = (result.data or [data])[0]
    audit_event(
        "encounter_note_added",
        {"note_type": payload.note_type},
        actor_id=user.get("sub"),
        subject_type="encounter",
        subject_id=str(encounter_id),
    )
    return {"ok": True, "note": note}


@router.get("/encounters/{encounter_id}/notes")
async def list_encounter_notes(encounter_id: int, user=Depends(verify_jwt)):
    """List all clinical notes for an encounter, ordered chronologically."""
    _get_encounter(encounter_id)
    result = (
        db.table(TABLE_ENCOUNTER_NOTES)
        .select("*")
        .eq("encounter_id", encounter_id)
        .order("created_at", desc=False)
        .execute()
    )
    return {"notes": result.data or [], "count": len(result.data or [])}
