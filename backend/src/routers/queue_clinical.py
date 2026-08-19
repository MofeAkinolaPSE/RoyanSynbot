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
    TABLE_APPOINTMENTS,
    TABLE_BILLING,
    TABLE_DISPENSING,
    TABLE_ENCOUNTER_NOTES,
    TABLE_ENCOUNTERS,
    TABLE_LAB_ORDERS,
    TABLE_LAB_RESULTS,
    TABLE_NOTE_TITLES,
    TABLE_PATIENTS,
    TABLE_PAYMENTS,
    TABLE_PRESCRIPTIONS,
    TABLE_RADIOLOGY_ORDERS,
    TABLE_STAFF,
    TABLE_VITALS,
    TRIAGE_LEVELS,
)
from src.cache import invalidate_cache_tags
from src.db import audit_event, db
from src.middleware import verify_jwt
from src.services.patient_context import invalidate_patient_context
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


def _find_active_encounter(patient_id: int | str) -> Optional[dict]:
    """A patient's current non-discharged, native (not Hope-imported) encounter,
    if any — the single source of truth for "is this patient already on the
    queue," shared by both the open_encounter dedup check below and the
    active-encounter lookup endpoint so the two can never drift apart."""
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
    return existing.data[0] if existing.data else None


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


class AssignNurseRequest(BaseModel):
    nurse_id: Optional[str] = None  # royan_staff.id; None clears the assignment


class PauseConsultationRequest(BaseModel):
    reason: Optional[str] = None


class EndConsultationRequest(BaseModel):
    force_status: Optional[str] = None  # explicit override; still validated by _assert_transition
    disposition_notes: Optional[str] = None


class EncounterNoteCreate(BaseModel):
    note_type: str = "general"  # general | assessment | plan | soap | progress | discharge | nursing | handover | referral_letter | soap_summary
    note_title_id: Optional[int] = None  # resolves note_type from royan_note_titles.category when given
    note_title: Optional[str] = None     # denormalized title text; falls back to the looked-up title
    content: Optional[str] = None        # required unless SOAP fields are given (server composes a fallback)
    subjective: Optional[str] = None
    objective: Optional[str] = None
    assessment: Optional[str] = None
    plan: Optional[str] = None
    icd10_codes: Optional[list[str]] = None
    vitals_id: Optional[int] = None
    signed_by: Optional[str] = None      # staff.id override; auto-resolved from the acting user if omitted

    model_config = {"extra": "ignore"}


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


def _resolve_staff_id_for_user(user: dict) -> Optional[str]:
    """Map the acting JWT subject (an auth user id) to their own royan_staff.id,
    via royan_staff.user_id — the two are different uuid spaces, `sub` is never
    itself a valid royan_staff.id, so it can't be passed through directly."""
    sub = user.get("sub")
    if not sub:
        return None
    r = db.table(TABLE_STAFF).select("id").eq("user_id", sub).limit(1).execute()
    return r.data[0]["id"] if r.data else None


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
    encounter_ids = list({row.get("id") for row in rows if row.get("id") is not None})
    nurse_ids = list({row.get("assigned_nurse_id") for row in rows if row.get("assigned_nurse_id")})

    patient_map: dict = {}
    if patient_ids:
        try:
            patients = (
                db.table(TABLE_PATIENTS)
                .select("id,mrn,first_name,last_name,phone,hmo_provider,hmo_id,patient_type")
                .in_("id", patient_ids)
                .execute()
            )
            patient_map = {row["id"]: row for row in patients.data or []}
        except Exception:
            patient_map = {}

    nurse_map: dict = {}
    if nurse_ids:
        try:
            nurses = db.table(TABLE_STAFF).select("id,full_name").in_("id", nurse_ids).execute()
            nurse_map = {row["id"]: row.get("full_name") for row in nurses.data or []}
        except Exception:
            nurse_map = {}

    # Lab/Radiology order counts + a "has assessment note" flag per encounter —
    # matches Hope's "LAB 0/0, RAD 0/0" + Initial Assmt/SOAP indicators on the
    # Outpatient Dashboard row. Batched (one query per domain, not per row).
    lab_counts: dict = {}
    rad_counts: dict = {}
    rx_counts: dict = {}
    note_flags: dict = {}
    if encounter_ids:
        try:
            lab_rows = db.table(TABLE_LAB_ORDERS).select("encounter_id,status").in_("encounter_id", encounter_ids).execute().data or []
            for r in lab_rows:
                eid = r.get("encounter_id")
                bucket = lab_counts.setdefault(eid, {"total": 0, "done": 0})
                bucket["total"] += 1
                if r.get("status") in ("resulted", "sent_out"):
                    bucket["done"] += 1
        except Exception:
            pass
        try:
            rad_rows = db.table(TABLE_RADIOLOGY_ORDERS).select("encounter_id,status").in_("encounter_id", encounter_ids).execute().data or []
            for r in rad_rows:
                eid = r.get("encounter_id")
                bucket = rad_counts.setdefault(eid, {"total": 0, "done": 0})
                bucket["total"] += 1
                if r.get("status") == "reported":
                    bucket["done"] += 1
        except Exception:
            pass
        try:
            rx_rows = db.table(TABLE_PRESCRIPTIONS).select("encounter_id,status").in_("encounter_id", encounter_ids).execute().data or []
            for r in rx_rows:
                eid = r.get("encounter_id")
                bucket = rx_counts.setdefault(eid, {"total": 0, "done": 0})
                bucket["total"] += 1
                if r.get("status") in ("dispensed", "partially_dispensed"):
                    bucket["done"] += 1
        except Exception:
            pass
        try:
            note_rows = (
                db.table(TABLE_ENCOUNTER_NOTES).select("encounter_id,note_type")
                .in_("encounter_id", encounter_ids)
                .in_("note_type", ["assessment", "soap", "soap_summary", "progress"])
                .execute().data or []
            )
            for r in note_rows:
                note_flags[r.get("encounter_id")] = True
        except Exception:
            pass

    enriched: list[dict] = []
    for row in rows:
        patient = patient_map.get(row.get("patient_id")) or {}
        name = f"{patient.get('first_name', '')} {patient.get('last_name', '')}".strip()
        eid = row.get("id")
        lab = lab_counts.get(eid, {"total": 0, "done": 0})
        rad = rad_counts.get(eid, {"total": 0, "done": 0})
        rx = rx_counts.get(eid, {"total": 0, "done": 0})
        enriched.append({
            **row,
            "patient": patient or None,
            "patient_name": name or None,
            "mrn": patient.get("mrn"),
            "hmo_provider": patient.get("hmo_provider"),
            "hmo_id": patient.get("hmo_id"),
            "patient_type": patient.get("patient_type"),
            "assigned_nurse_name": nurse_map.get(row.get("assigned_nurse_id")),
            "lab_order_count": lab["total"],
            "lab_resulted_count": lab["done"],
            "radiology_order_count": rad["total"],
            "radiology_resulted_count": rad["done"],
            "prescription_count": rx["total"],
            "prescription_dispensed_count": rx["done"],
            "has_assessment_note": bool(note_flags.get(eid)),
        })
    return enriched


def open_encounter_for_patient(
    patient_id: int,
    *,
    encounter_type: str = "outpatient",
    department: Optional[str] = None,
    chief_complaint: Optional[str] = None,
    registered_by: Optional[str] = None,
    actor_sub: Optional[str] = None,
) -> tuple[dict, bool]:
    """Core "open an encounter" logic, shared by POST /encounters and any other
    flow that should land a patient on the live clinical queue (e.g. marking an
    appointment as arrived). Returns (encounter, already_active) — already_active
    is True when the patient already had a non-discharged encounter and this
    call reused it instead of creating a duplicate."""
    patient = db.table(TABLE_PATIENTS).select("id,mrn,first_name,last_name").eq("id", patient_id).limit(1).execute()
    if not patient.data:
        raise HTTPException(status_code=404, detail=f"Patient {patient_id} not found")

    # Don't silently create a second open encounter for a patient who already has one —
    # this is what produced duplicate queue numbers when the CPRS page suggested
    # "New Encounter" for a patient whose Front-Desk encounter just hadn't refreshed yet.
    existing = _find_active_encounter(patient_id)
    if existing:
        return existing, True

    dept = department or "OPD"
    data = {
        "patient_id": patient_id,
        "encounter_type": encounter_type,
        "department": dept,
        "chief_complaint": chief_complaint,
        "status": "patient_registered",
        "registered_by": registered_by or actor_sub or "system",
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
        actor_id=actor_sub,
        subject_type="encounter",
        subject_id=str(enc_id or ""),
    )
    invalidate_cache_tags("hospital", "patient_flow", "queue", "encounters", "executive")

    pt = patient.data[0]
    asyncio.create_task(realtime_hub.broadcast("encounter_updates", {
        "event": "encounter_opened",
        "encounter_id": enc_id,
        "queue_number": queue_number,
        "department": dept,
        "patient_name": f"{pt.get('first_name', '')} {pt.get('last_name', '')}".strip(),
    }))

    return encounter, False


@router.post("/encounters", status_code=201)
async def open_encounter(payload: EncounterCreate, user=Depends(verify_jwt)):
    if payload.encounter_type not in ENCOUNTER_TYPES:
        raise HTTPException(status_code=422, detail=f"encounter_type must be one of {sorted(ENCOUNTER_TYPES)}")
    if payload.department and payload.department not in HOSPITAL_DEPARTMENTS:
        raise HTTPException(status_code=422, detail=f"Unknown department '{payload.department}'")

    patient_id = _resolve_patient_id(payload.patient_id)
    encounter, already_active = open_encounter_for_patient(
        patient_id,
        encounter_type=payload.encounter_type,
        department=payload.department,
        chief_complaint=payload.chief_complaint,
        registered_by=payload.registered_by,
        actor_sub=user.get("sub"),
    )
    return {"ok": True, "encounter": encounter, **({"already_active": True} if already_active else {})}


@router.get("/patients/{patient_id}/active-encounter")
async def get_active_encounter(patient_id: str, user=Depends(verify_jwt)):
    """Lets front-desk/queue UIs check *before* submitting whether a patient
    already has an active encounter, so the 'can't double-book' rule can be
    surfaced as a clear, proactive lock rather than a silent no-op discovered
    only after the fact. Accepts either a numeric patient id or an MRN, same
    as open_encounter above, since the Queue page's dialog collects a raw MRN."""
    resolved_id = _resolve_patient_id(patient_id)
    return {"active_encounter": _find_active_encounter(resolved_id)}


@router.get("/encounters")
async def list_encounters(
    status: Optional[str] = Query(None),
    department: Optional[str] = Query(None),
    doctor: Optional[str] = Query(None),
    patient_id: Optional[int] = Query(None),
    active_only: bool = Query(
        False,
        description="If true and no status filter is given, return all non-discharged encounters",
    ),
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
    elif active_only:
        # "discharged" is the only terminal status (ENCOUNTER_STATUS_ALLOWED,
        # constants.py) — every other status is a patient still under active
        # care. Computed here so every consumer (Nursing Station's worklist,
        # NurseDashboard's Active Inpatients card) shares one definition of
        # "active" instead of re-deriving it client-side.
        query = query.neq("status", "discharged")
    if department:
        query = query.eq("department", department)
    if doctor:
        # `doctor` is the assigned doctor's royan_staff.id (uuid FK) — the
        # legacy free-text `consulting_doctor` column is display-only and
        # never a reliable match target (nurses type arbitrary names into it).
        query = query.eq("doctor_id", doctor)
    if patient_id:
        query = query.eq("patient_id", patient_id)
    result = query.execute()
    encounters = _enrich_encounters(result.data or [])
    return {"encounters": encounters, "count": len(encounters)}


@router.get("/encounters/{encounter_id}")
async def get_encounter(encounter_id: int, user=Depends(verify_jwt)):
    """Full encounter detail — everything that happened during this visit, in
    one round trip, so the frontend can render it as a single chronological
    story instead of a flat status/date summary. Each clinical domain
    (labs, radiology, prescriptions, billing) is returned as orders/records
    plus their outcomes (results, dispensing, payments) so the timeline can
    show both "ordered" and "resulted" as distinct moments."""
    encounter = _get_encounter(encounter_id)

    vitals = db.table(TABLE_VITALS).select("*").eq("encounter_id", encounter_id).order("recorded_at", desc=True).execute().data or []
    notes = db.table(TABLE_ENCOUNTER_NOTES).select("*").eq("encounter_id", encounter_id).order("created_at", desc=True).execute().data or []

    labs = db.table(TABLE_LAB_ORDERS).select("*").eq("encounter_id", encounter_id).order("ordered_at", desc=True).execute().data or []
    lab_order_ids = [row["id"] for row in labs if row.get("id") is not None]
    lab_results = (
        db.table(TABLE_LAB_RESULTS).select("*").in_("lab_order_id", lab_order_ids).execute().data or []
        if lab_order_ids else []
    )

    radiology_orders = db.table(TABLE_RADIOLOGY_ORDERS).select("*").eq("encounter_id", encounter_id).order("ordered_at", desc=True).execute().data or []

    prescriptions = db.table(TABLE_PRESCRIPTIONS).select("*").eq("encounter_id", encounter_id).order("prescribed_at", desc=True).execute().data or []
    rx_ids = [row["id"] for row in prescriptions if row.get("id") is not None]
    dispensing = (
        db.table(TABLE_DISPENSING).select("*").in_("prescription_id", rx_ids).execute().data or []
        if rx_ids else []
    )

    bills = db.table(TABLE_BILLING).select("*").eq("encounter_id", encounter_id).order("billed_at", desc=True).execute().data or []
    bill_ids = [row["id"] for row in bills if row.get("id") is not None]
    payments = (
        db.table(TABLE_PAYMENTS).select("*").in_("billing_id", bill_ids).order("received_at", desc=True).execute().data or []
        if bill_ids else []
    )

    return {
        "encounter": _enrich_encounters([encounter])[0],
        "vitals": vitals,
        "notes": notes,
        "lab_orders": labs,
        "lab_results": lab_results,
        "radiology_orders": radiology_orders,
        "prescriptions": prescriptions,
        "dispensing": dispensing,
        "bills": bills,
        "payments": payments,
    }


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


@router.patch("/encounters/{encounter_id}/assign-nurse")
async def assign_nurse(encounter_id: int, payload: AssignNurseRequest, user=Depends(verify_jwt)):
    """Assign (or clear) the nurse responsible for this patient's care —
    Hope's Outpatient Dashboard has this as a per-row dropdown; this app had
    no such concept at all until now."""
    _get_encounter(encounter_id)
    nurse_name = None
    if payload.nurse_id:
        nurse = db.table(TABLE_STAFF).select("id,full_name").eq("id", payload.nurse_id).limit(1).execute()
        if not nurse.data:
            raise HTTPException(status_code=404, detail=f"Staff {payload.nurse_id} not found")
        nurse_name = nurse.data[0].get("full_name")

    db.table(TABLE_ENCOUNTERS).update({"assigned_nurse_id": payload.nurse_id}).eq("id", encounter_id).execute()
    invalidate_cache_tags("hospital", "queue", "patient_flow", "encounters")
    audit_event(
        "nurse_assigned" if payload.nurse_id else "nurse_unassigned",
        {"nurse_id": payload.nurse_id},
        actor_id=user.get("sub"),
        subject_type="encounter",
        subject_id=str(encounter_id),
    )
    asyncio.create_task(realtime_hub.broadcast("encounter_updates", {
        "event": "nurse_assigned", "encounter_id": encounter_id, "nurse_id": payload.nurse_id,
    }))
    return {"ok": True, "encounter_id": encounter_id, "assigned_nurse_id": payload.nurse_id, "assigned_nurse_name": nurse_name}


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


@router.post("/encounters/{encounter_id}/pause")
async def pause_consultation(encounter_id: int, payload: PauseConsultationRequest, user=Depends(verify_jwt)):
    """Mark a consultation paused without changing its queue status — a
    display/ops-awareness flag, not a workflow state (the department blueprint
    names Pause/Resume as a quick action with no backing status of its own)."""
    encounter = _get_encounter(encounter_id)
    if encounter["status"] != "consulting":
        raise HTTPException(status_code=409, detail="Can only pause an encounter that is currently consulting")
    db.table(TABLE_ENCOUNTERS).update({
        "paused_at": datetime.now(timezone.utc).isoformat(),
        "paused_reason": payload.reason,
    }).eq("id", encounter_id).execute()
    invalidate_cache_tags("hospital", "queue", "patient_flow", "encounters")
    audit_event("consultation_paused", {"reason": payload.reason}, actor_id=user.get("sub"), subject_type="encounter", subject_id=str(encounter_id))
    asyncio.create_task(realtime_hub.broadcast("encounter_updates", {
        "event": "consultation_paused", "encounter_id": encounter_id, "queue_number": encounter.get("queue_number"),
    }))
    return {"ok": True, "encounter_id": encounter_id, "paused": True}


@router.post("/encounters/{encounter_id}/resume")
async def resume_consultation(encounter_id: int, user=Depends(verify_jwt)):
    encounter = _get_encounter(encounter_id)
    db.table(TABLE_ENCOUNTERS).update({"paused_at": None, "paused_reason": None}).eq("id", encounter_id).execute()
    invalidate_cache_tags("hospital", "queue", "patient_flow", "encounters")
    audit_event("consultation_resumed", {}, actor_id=user.get("sub"), subject_type="encounter", subject_id=str(encounter_id))
    asyncio.create_task(realtime_hub.broadcast("encounter_updates", {
        "event": "consultation_resumed", "encounter_id": encounter_id, "queue_number": encounter.get("queue_number"),
    }))
    return {"ok": True, "encounter_id": encounter_id, "paused": False}


@router.post("/encounters/{encounter_id}/end-consultation")
async def end_consultation(encounter_id: int, payload: EndConsultationRequest, user=Depends(verify_jwt)):
    """One-click 'End Consultation': evaluates what was ordered during the
    visit and auto-routes the encounter to the correct next queue, matching
    the department standard's requirement that ending a consultation triggers
    workflow evaluation rather than requiring the clinician to pick a status."""
    encounter = _get_encounter(encounter_id)
    if encounter["status"] not in ("consulting", "lab_ordered", "pharmacy_dispensing"):
        raise HTTPException(status_code=409, detail=f"Cannot end consultation from status '{encounter['status']}'")

    has_note = db.table(TABLE_ENCOUNTER_NOTES).select("id").eq("encounter_id", encounter_id).limit(1).execute().data
    if not has_note:
        raise HTTPException(status_code=422, detail="At least one clinical note is required before ending the consultation.")

    pending_labs = (
        db.table(TABLE_LAB_ORDERS).select("id").eq("encounter_id", encounter_id)
        .not_in("status", ["resulted", "cancelled"]).execute().data or []
    )
    pending_rx = (
        db.table(TABLE_PRESCRIPTIONS).select("id").eq("encounter_id", encounter_id)
        .in_("status", ["pending", "partially_dispensed"]).execute().data or []
    )

    if payload.force_status:
        target, reason = payload.force_status, "clinician override"
    elif pending_labs:
        target, reason = "lab_ordered", f"{len(pending_labs)} lab order(s) awaiting result"
    elif pending_rx:
        target, reason = "pharmacy_dispensing", f"{len(pending_rx)} prescription(s) pending dispensing"
    else:
        target, reason = "billing_pending", "no pending labs or prescriptions"

    if target == encounter["status"]:
        # Already exactly where the evidence says it should be (e.g. doctor
        # re-clicks End Consultation on an encounter still awaiting a lab
        # result) — no transition needed; most statuses have no self-loop in
        # ENCOUNTER_STATUS_TRANSITIONS so _assert_transition would otherwise
        # reject this as an illegal no-op transition.
        return {
            "ok": True, "encounter_id": encounter_id, "status": target, "routed_to": target,
            "routing_reason": f"already {target.replace('_', ' ')} — {reason}",
            "evidence": {"pending_labs": len(pending_labs), "pending_prescriptions": len(pending_rx)},
        }

    _assert_transition(encounter["status"], target)
    db.table(TABLE_ENCOUNTERS).update({
        "status": target,
        "paused_at": None,
        "paused_reason": None,
    }).eq("id", encounter_id).execute()
    invalidate_cache_tags("hospital", "queue", "patient_flow", "encounters")
    invalidate_patient_context(encounter["patient_id"])
    audit_event("consultation_ended", {"routed_to": target, "reason": reason}, actor_id=user.get("sub"), subject_type="encounter", subject_id=str(encounter_id))
    asyncio.create_task(realtime_hub.broadcast("encounter_updates", {
        "event": "consultation_ended", "encounter_id": encounter_id,
        "queue_number": encounter.get("queue_number"), "status": target,
    }))
    return {
        "ok": True, "encounter_id": encounter_id, "status": target, "routed_to": target,
        "routing_reason": reason,
        "evidence": {"pending_labs": len(pending_labs), "pending_prescriptions": len(pending_rx)},
    }


@router.post("/encounters/{encounter_id}/advance")
async def advance_encounter(encounter_id: int, payload: AdvanceRequest, user=Depends(verify_jwt)):
    encounter = _get_encounter(encounter_id)
    _assert_transition(encounter["status"], payload.new_status)
    if payload.new_status == "discharged":
        raise HTTPException(status_code=400, detail="Use POST /encounters/{id}/discharge to discharge a patient")
    db.table(TABLE_ENCOUNTERS).update({"status": payload.new_status}).eq("id", encounter_id).execute()
    invalidate_cache_tags("hospital", "queue", "patient_flow", "encounters")
    audit_event("encounter_advanced", {"to": payload.new_status, "notes": payload.notes}, actor_id=user.get("sub"), subject_type="encounter", subject_id=str(encounter_id))
    asyncio.create_task(realtime_hub.broadcast("encounter_updates", {
        "event": "encounter_advanced",
        "encounter_id": encounter_id,
        "queue_number": encounter.get("queue_number"),
        "department": encounter.get("department"),
        "status": payload.new_status,
    }))
    return {"ok": True, "encounter_id": encounter_id, "status": payload.new_status}


@router.post("/encounters/{encounter_id}/discharge")
async def discharge_encounter(encounter_id: int, payload: DischargeRequest, user=Depends(verify_jwt)):
    encounter = _get_encounter(encounter_id)
    _assert_transition(encounter["status"], "discharged")

    has_note = db.table(TABLE_ENCOUNTER_NOTES).select("id").eq("encounter_id", encounter_id).limit(1).execute().data
    if not has_note:
        raise HTTPException(status_code=422, detail="At least one clinical note is required before discharge.")

    now = datetime.now(timezone.utc).isoformat()
    updates = {
        "status": "discharged",
        "discharge_summary": payload.discharge_summary,
        "discharge_by": user.get("sub") or "system",
        "discharge_at": now,
    }
    db.table(TABLE_ENCOUNTERS).update(updates).eq("id", encounter_id).execute()
    audit_event("encounter_discharged", {"summary_len": len(payload.discharge_summary)}, actor_id=user.get("sub"), subject_type="encounter", subject_id=str(encounter_id))
    asyncio.create_task(realtime_hub.broadcast("encounter_updates", {
        "event": "encounter_discharged",
        "encounter_id": encounter_id,
        "queue_number": encounter.get("queue_number"),
        "department": encounter.get("department"),
    }))

    # If this encounter was opened from an appointment arrival (see
    # appointments.py's mark_arrived), that appointment is still sitting in
    # "arrived" — nothing ever moved it forward, so it lingered on the
    # calendar/appointments list indefinitely even after the visit was
    # actually done. Close the loop: a completed visit completes the booking
    # that brought the patient in.
    try:
        linked = (
            db.table(TABLE_APPOINTMENTS)
            .select("id,status")
            .eq("encounter_id", encounter_id)
            .in_("status", ["arrived", "booked", "confirmed"])
            .execute()
        ).data or []
        for appt in linked:
            db.table(TABLE_APPOINTMENTS).update({"status": "completed"}).eq("id", appt["id"]).execute()
            audit_event("appointment_completed", {"reason": "encounter_discharged"}, actor_id=user.get("sub"), subject_type="appointment", subject_id=str(appt["id"]))
            asyncio.create_task(realtime_hub.broadcast("appointment_updates", {
                "event": "appointment_completed",
                "appointment_id": appt["id"],
            }))
    except Exception as exc:
        logger.warning("Auto-completing linked appointment failed for encounter %s: %s", encounter_id, exc)

    return {"ok": True, "encounter_id": encounter_id, "status": "discharged", "discharged_at": now}


# ─── Encounter Notes ──────────────────────────────────────────────────────────

@router.post("/encounters/{encounter_id}/notes", status_code=201)
async def add_encounter_note(encounter_id: int, payload: EncounterNoteCreate, user=Depends(verify_jwt)):
    """Add a clinical note to an encounter, either free-text (note_type) or
    picked from the Notes Master catalog (note_title_id — resolves note_type
    from the title's category and denormalizes the title text onto the row)."""
    encounter = _get_encounter(encounter_id)

    note_type = payload.note_type
    note_title = payload.note_title
    if payload.note_title_id is not None:
        title_row = db.table(TABLE_NOTE_TITLES).select("title,category").eq("id", payload.note_title_id).execute()
        if title_row.data:
            note_type = title_row.data[0]["category"]
            note_title = note_title or title_row.data[0]["title"]

    content = payload.content
    if not content:
        content = " | ".join(filter(None, [
            f"S: {payload.subjective}" if payload.subjective else "",
            f"O: {payload.objective}" if payload.objective else "",
            f"A: {payload.assessment}" if payload.assessment else "",
            f"P: {payload.plan}" if payload.plan else "",
        ]))
    if not content:
        raise HTTPException(status_code=422, detail="Note must have content or at least one SOAP field")

    signed_by = payload.signed_by or _resolve_staff_id_for_user(user)

    data = {
        "encounter_id": encounter_id,
        "patient_id": encounter["patient_id"],
        "note_type": note_type,
        "note_title_id": payload.note_title_id,
        "note_title": note_title,
        "content": content,
        "subjective": payload.subjective,
        "objective": payload.objective,
        "assessment": payload.assessment,
        "plan": payload.plan,
        "icd10_codes": payload.icd10_codes,
        "vitals_id": payload.vitals_id,
        "author_id": user.get("sub"),
        "author_name": user.get("email") or user.get("sub"),
    }
    if signed_by:
        data["signed_by"] = signed_by
        data["signed_at"] = datetime.now(timezone.utc).isoformat()
    try:
        result = db.table(TABLE_ENCOUNTER_NOTES).insert(data).execute()
    except Exception as exc:
        logger.error("Encounter note insert failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to save encounter note")
    note = (result.data or [data])[0]
    invalidate_patient_context(encounter["patient_id"])
    audit_event(
        "encounter_note_added",
        {"note_type": note_type, "note_title": note_title},
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
