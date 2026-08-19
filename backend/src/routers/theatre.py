"""
Surgical Theatre Router — RoyanHealth / Royan Hospital
=========================================================
Theatre case scheduling, pre-op assessment, anaesthetic records,
operative notes, and post-op recovery tracking.
VistA Reference: Operating Room (OR) Management module.

Endpoints:
  POST   /theatre/cases                        – Schedule theatre case
  GET    /theatre/cases                        – List cases (filter: date, status, surgeon)
  GET    /theatre/cases/{id}                   – Case detail
  PATCH  /theatre/cases/{id}/pre-op            – Submit pre-op checklist
  PATCH  /theatre/cases/{id}/anaesthetic       – Anaesthetic record
  PATCH  /theatre/cases/{id}/operative-notes   – Intraoperative notes
  PATCH  /theatre/cases/{id}/post-op           – Post-op recovery notes
  PATCH  /theatre/cases/{id}/status            – Advance status
  GET    /theatre/schedule                     – Daily/weekly schedule (date filter)
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.db import db, audit_event
from src.middleware import verify_jwt
from src.constants import (
    TABLE_THEATRE_CASES,
    TABLE_PATIENTS,
    THEATRE_STATUS_ALLOWED,
    THEATRE_STATUS_TRANSITIONS,
    THEATRE_URGENCY_ALLOWED,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/theatre", tags=["Surgical Theatre"])

STATUSES    = THEATRE_STATUS_ALLOWED
TRANSITIONS = THEATRE_STATUS_TRANSITIONS
URGENCIES   = THEATRE_URGENCY_ALLOWED


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class TheatreCaseCreate(BaseModel):
    encounter_id: int
    patient_id: int
    theatre_name: Optional[str] = None          # e.g. "Theatre 1", "Day Surgery"
    procedure_name: str = Field(..., min_length=1, max_length=500)
    case_type: Optional[str] = None              # general | regional | local
    urgency: str = "elective"
    scheduled_date: Optional[str] = None         # ISO date
    start_time: Optional[str] = None             # HH:MM
    surgeon_id: Optional[str] = None
    anaesthetist_id: Optional[str] = None
    scrub_nurse: Optional[str] = None
    circulating_nurse: Optional[str] = None
    notes: Optional[str] = None

    model_config = {"extra": "ignore"}


class PreOpChecklist(BaseModel):
    consent_signed: bool = False
    site_marked: bool = False
    allergies_confirmed: bool = False
    blood_group_confirmed: bool = False
    fasting_confirmed: bool = False
    iv_access: bool = False
    premedication_given: bool = False
    imaging_available: bool = False
    blood_available: bool = False
    equipment_checked: bool = False
    notes: Optional[str] = None

    model_config = {"extra": "ignore"}


class AnaestheticRecord(BaseModel):
    anaesthetic_type: str = "general"            # general | regional | spinal | local | sedation
    asa_grade: Optional[str] = None              # ASA physical status I-VI
    induction_agent: Optional[str] = None
    maintenance_agent: Optional[str] = None
    airway_management: Optional[str] = None      # ETT | LMA | mask | awake intubation
    positioning: Optional[str] = None
    total_duration_minutes: Optional[int] = None
    blood_loss_ml: Optional[float] = None
    fluids_given_ml: Optional[float] = None
    complications: Optional[str] = None
    notes: Optional[str] = None

    model_config = {"extra": "ignore"}


class OperativeNotes(BaseModel):
    incision: Optional[str] = None
    findings: str = Field(..., min_length=1)
    procedure_performed: str = Field(..., min_length=1)
    specimens_sent: Optional[str] = None
    drains_inserted: bool = False
    closure_method: Optional[str] = None
    complications: Optional[str] = None
    blood_loss_ml: Optional[float] = None
    surgeon_notes: Optional[str] = None

    model_config = {"extra": "ignore"}


class PostOpRecord(BaseModel):
    recovery_location: Optional[str] = None     # PACU | ICU | Ward
    vital_signs_stable: bool = True
    pain_score: Optional[int] = Field(None, ge=0, le=10)
    nausea_vomiting: bool = False
    oxygen_therapy: bool = False
    diet_instructions: Optional[str] = None
    wound_status: Optional[str] = None
    discharge_criteria_met: bool = False
    follow_up_date: Optional[str] = None
    post_op_medications: Optional[str] = None
    complications: Optional[str] = None
    notes: Optional[str] = None

    model_config = {"extra": "ignore"}


class StatusAdvance(BaseModel):
    status: str
    notes: Optional[str] = None

    model_config = {"extra": "ignore"}


class OperativeNotesVerifyRequest(BaseModel):
    notes: Optional[str] = None

    model_config = {"extra": "ignore"}


class OperativeNotesAmend(OperativeNotes):
    """Corrects a verified operative note. Verified notes are immutable in
    place — this snapshots the current version into operative_notes_history
    and resets verified_by/verified_at, mirroring Radiology's ReportAmend."""
    amendment_reason: str = Field(..., min_length=1)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_case(case_id: int) -> dict:
    r = db.table(TABLE_THEATRE_CASES).select("*").eq("id", case_id).execute()
    if not r.data:
        raise HTTPException(status_code=404, detail=f"Theatre case {case_id} not found")
    return r.data[0]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _jsonable(v):
    return v.isoformat() if isinstance(v, datetime) else v


def _merge_jsonb(existing: Optional[dict], updates: dict) -> dict:
    return {**(existing or {}), **updates}


def _enrich_patients(rows: list) -> None:
    """Batch-merge patient_name/patient_mrn onto a list of case rows in place."""
    if not rows:
        return
    try:
        pid_set = list({r["patient_id"] for r in rows if r.get("patient_id") is not None})
        if not pid_set:
            return
        pt_rows = db.table(TABLE_PATIENTS).select("id,mrn,first_name,last_name").in_("id", pid_set).execute()
        pt_map = {p["id"]: p for p in (pt_rows.data or [])}
        for r in rows:
            p = pt_map.get(r.get("patient_id"))
            if p:
                fn = (p.get("first_name") or "").strip()
                ln = (p.get("last_name") or "").strip()
                r["patient_name"] = f"{fn} {ln}".strip() or None
                r["patient_mrn"] = p.get("mrn")
    except Exception as exc:
        logger.warning("theatre patient enrichment failed: %s", exc)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/cases", status_code=201)
async def schedule_case(payload: TheatreCaseCreate, user=Depends(verify_jwt)):
    """Schedule a new theatre case."""
    if payload.urgency not in URGENCIES:
        raise HTTPException(status_code=422, detail=f"urgency must be one of {URGENCIES}")

    data = payload.model_dump(exclude_none=True)
    data["status"]      = "scheduled"
    data["booked_by"]   = user.get("sub") or "system"

    try:
        result = db.table(TABLE_THEATRE_CASES).insert(data).execute()
    except Exception as exc:
        logger.error("Theatre case creation failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to schedule theatre case")

    case = result.data[0] if result.data else data
    audit_event(
        "theatre_case_scheduled",
        {"procedure": payload.procedure_name, "urgency": payload.urgency},
        actor_id=user.get("sub"),
        subject_type="theatre_case",
        subject_id=str(case.get("id") or ""),
    )
    return {"ok": True, "case": case}


@router.get("/cases")
async def list_cases(
    status: Optional[str]   = Query(None),
    urgency: Optional[str]  = Query(None),
    surgeon_id: Optional[str] = Query(None),
    date: Optional[str]     = Query(None),   # ISO date — filters on scheduled_date
    patient_id: Optional[int] = Query(None),
    limit: int              = Query(50, ge=1, le=200),
    user=Depends(verify_jwt),
):
    query = db.table(TABLE_THEATRE_CASES).select("*").order("scheduled_date", desc=True).limit(limit)
    if status:
        query = query.eq("status", status)
    if urgency:
        query = query.eq("urgency", urgency)
    if surgeon_id:
        query = query.eq("surgeon_id", surgeon_id)
    if date:
        query = query.eq("scheduled_date", date)
    if patient_id:
        query = query.eq("patient_id", patient_id)
    result = query.execute()
    cases = list(result.data or [])
    _enrich_patients(cases)
    return {"cases": cases, "count": len(cases)}


@router.get("/stats")
async def theatre_stats(user=Depends(verify_jwt)):
    rows = db.table(TABLE_THEATRE_CASES).select("status,urgency").execute().data or []
    counts = {s: sum(1 for r in rows if r.get("status") == s) for s in STATUSES}
    emergency_active = sum(
        1 for r in rows if r.get("urgency") == "emergency" and r.get("status") not in ("completed", "cancelled")
    )
    return {**counts, "emergency": emergency_active, "total": len(rows)}


@router.get("/cases/{case_id}")
async def get_case(case_id: int, user=Depends(verify_jwt)):
    case = _get_case(case_id)
    pt = db.table(TABLE_PATIENTS).select("id,mrn,first_name,last_name,gender,date_of_birth").eq("id", case["patient_id"]).execute()
    if pt.data:
        p = pt.data[0]
        fn, ln = (p.get("first_name") or "").strip(), (p.get("last_name") or "").strip()
        case = {
            **case,
            "patient_name": f"{fn} {ln}".strip() or None,
            "patient_mrn": p.get("mrn"),
            "patient_gender": p.get("gender"),
            "patient_dob": p.get("date_of_birth"),
        }
    return {"case": case}


@router.patch("/cases/{case_id}/status")
async def advance_status(case_id: int, payload: StatusAdvance, user=Depends(verify_jwt)):
    """Advance theatre case through status workflow."""
    case = _get_case(case_id)
    current = case["status"]

    if payload.status not in STATUSES:
        raise HTTPException(status_code=422, detail=f"status must be one of {STATUSES}")
    if payload.status not in TRANSITIONS.get(current, set()):
        raise HTTPException(
            status_code=409,
            detail=f"Cannot transition '{current}' → '{payload.status}'. Allowed: {TRANSITIONS.get(current)}",
        )
    if payload.status == "recovery" and not case.get("operative_notes"):
        raise HTTPException(status_code=409, detail="Cannot move to recovery — operative notes must be recorded first (Op Notes tab)")
    if payload.status == "completed" and not case.get("post_op_notes"):
        raise HTTPException(status_code=409, detail="Cannot complete case — post-op recovery record must be documented first (Post-Op tab)")

    updates: dict = {"status": payload.status}
    if payload.notes:
        updates["notes"] = payload.notes
    if payload.status == "in_theatre":
        updates["actual_start_time"] = _now()
    if payload.status == "completed":
        updates["actual_end_time"] = _now()

    db.table(TABLE_THEATRE_CASES).update(updates).eq("id", case_id).execute()
    audit_event(
        "theatre_status_advanced",
        {"from": current, "to": payload.status},
        actor_id=user.get("sub"),
        subject_type="theatre_case",
        subject_id=str(case_id),
    )
    return {"ok": True, "case_id": case_id, "status": payload.status}


@router.patch("/cases/{case_id}/pre-op")
async def submit_preop(case_id: int, payload: PreOpChecklist, user=Depends(verify_jwt)):
    """Submit pre-operative safety checklist (WHO Surgical Safety Checklist)."""
    _get_case(case_id)
    updates = {
        "pre_op_checklist": payload.model_dump(),
        "pre_op_completed_by": user.get("sub") or "system",
        "pre_op_completed_at": _now(),
    }
    db.table(TABLE_THEATRE_CASES).update(updates).eq("id", case_id).execute()
    audit_event("theatre_preop_completed", {}, actor_id=user.get("sub"), subject_type="theatre_case", subject_id=str(case_id))
    return {"ok": True, "case_id": case_id}


@router.patch("/cases/{case_id}/anaesthetic")
async def submit_anaesthetic(case_id: int, payload: AnaestheticRecord, user=Depends(verify_jwt)):
    """Record anaesthetic details. Merges onto whatever is already stored so a
    resubmission that omits a previously-set optional field doesn't silently
    wipe it out."""
    case = _get_case(case_id)
    merged = _merge_jsonb(case.get("anaesthetic_record"), payload.model_dump(exclude_none=True))
    db.table(TABLE_THEATRE_CASES).update({"anaesthetic_record": merged}).eq("id", case_id).execute()
    audit_event("theatre_anaesthetic_recorded", {}, actor_id=user.get("sub"), subject_type="theatre_case", subject_id=str(case_id))
    return {"ok": True, "case_id": case_id}


@router.patch("/cases/{case_id}/operative-notes")
async def submit_operative_notes(case_id: int, payload: OperativeNotes, user=Depends(verify_jwt)):
    """Surgeon submits intraoperative notes."""
    case = _get_case(case_id)
    if case.get("operative_notes_verified_at"):
        raise HTTPException(status_code=409, detail="Operative notes already verified — use PATCH /theatre/cases/{case_id}/operative-notes/amend to correct them")
    merged = _merge_jsonb(case.get("operative_notes"), payload.model_dump(exclude_none=True))
    db.table(TABLE_THEATRE_CASES).update({
        "operative_notes": merged,
        "operative_notes_by": user.get("sub") or "system",
    }).eq("id", case_id).execute()
    audit_event("theatre_operative_notes_submitted", {"procedure": payload.procedure_performed}, actor_id=user.get("sub"), subject_type="theatre_case", subject_id=str(case_id))
    return {"ok": True, "case_id": case_id}


@router.post("/cases/{case_id}/operative-notes/verify")
async def verify_operative_notes(case_id: int, payload: OperativeNotesVerifyRequest, user=Depends(verify_jwt)):
    case = _get_case(case_id)
    if not case.get("operative_notes"):
        raise HTTPException(status_code=409, detail="No operative notes recorded for this case yet")
    if case.get("operative_notes_verified_at"):
        raise HTTPException(status_code=409, detail=f"Already verified by {case.get('operative_notes_verified_by') or 'unknown'} at {case['operative_notes_verified_at']}")
    now_iso = _now()
    verified_by = user.get("sub") or "system"
    db.table(TABLE_THEATRE_CASES).update({
        "operative_notes_verified_by": verified_by,
        "operative_notes_verified_at": now_iso,
    }).eq("id", case_id).execute()
    audit_event("theatre_operative_notes_verified", {}, actor_id=user.get("sub"), subject_type="theatre_case", subject_id=str(case_id))
    return {"ok": True, "case_id": case_id, "verified_by": verified_by, "verified_at": now_iso}


@router.patch("/cases/{case_id}/operative-notes/amend")
async def amend_operative_notes(case_id: int, payload: OperativeNotesAmend, user=Depends(verify_jwt)):
    case = _get_case(case_id)
    if not case.get("operative_notes_verified_at"):
        raise HTTPException(status_code=409, detail="No verified operative notes exist to amend — unverified notes can be corrected directly via PATCH /theatre/cases/{case_id}/operative-notes")
    now_iso = _now()
    history = list(case.get("operative_notes_history") or [])
    history.append({
        "operative_notes": case.get("operative_notes"),
        "operative_notes_by": case.get("operative_notes_by"),
        "verified_by": case.get("operative_notes_verified_by"),
        "verified_at": _jsonable(case.get("operative_notes_verified_at")),
        "amendment_reason": case.get("operative_notes_amendment_reason"),
        "superseded_at": now_iso,
    })
    new_notes = payload.model_dump(exclude_none=True, exclude={"amendment_reason"})
    db.table(TABLE_THEATRE_CASES).update({
        "operative_notes": new_notes,
        "operative_notes_by": user.get("sub") or "system",
        "operative_notes_verified_by": None,
        "operative_notes_verified_at": None,
        "operative_notes_amendment_reason": payload.amendment_reason,
        "operative_notes_history": history,
    }).eq("id", case_id).execute()
    audit_event("theatre_operative_notes_amended", {"reason": payload.amendment_reason}, actor_id=user.get("sub"), subject_type="theatre_case", subject_id=str(case_id))
    return {"ok": True, "case_id": case_id, "amended": True}


@router.patch("/cases/{case_id}/post-op")
async def submit_postop(case_id: int, payload: PostOpRecord, user=Depends(verify_jwt)):
    """Record post-operative recovery status."""
    case = _get_case(case_id)
    merged = _merge_jsonb(case.get("post_op_notes"), payload.model_dump(exclude_none=True))
    db.table(TABLE_THEATRE_CASES).update({
        "post_op_notes": merged,
        "post_op_by": user.get("sub") or "system",
        "post_op_at": _now(),
    }).eq("id", case_id).execute()
    audit_event("theatre_postop_recorded", {}, actor_id=user.get("sub"), subject_type="theatre_case", subject_id=str(case_id))
    return {"ok": True, "case_id": case_id}


@router.get("/schedule")
async def daily_schedule(
    date: str = Query(..., description="ISO date e.g. 2026-06-01"),
    theatre_name: Optional[str] = Query(None),
    user=Depends(verify_jwt),
):
    """Return all theatre cases for a given date, ordered by start_time."""
    query = (
        db.table(TABLE_THEATRE_CASES)
        .select("*")
        .eq("scheduled_date", date)
        .order("start_time")
    )
    if theatre_name:
        query = query.eq("theatre_name", theatre_name)
    result = query.execute()
    schedule = list(result.data or [])
    _enrich_patients(schedule)
    return {"schedule": schedule, "date": date, "count": len(schedule)}
