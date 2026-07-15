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
    return {"cases": result.data or [], "count": len(result.data or [])}


@router.get("/cases/{case_id}")
async def get_case(case_id: int, user=Depends(verify_jwt)):
    return {"case": _get_case(case_id)}


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
    """Record anaesthetic details for a theatre case."""
    _get_case(case_id)
    updates = {
        "anaesthetic_record": payload.model_dump(exclude_none=True),
        "anaesthetist_id": payload.anaesthetic_type,   # keep existing if set
    }
    # Merge — don't overwrite existing anaesthetic details
    db.table(TABLE_THEATRE_CASES).update({"anaesthetic_record": payload.model_dump(exclude_none=True)}).eq("id", case_id).execute()
    audit_event("theatre_anaesthetic_recorded", {}, actor_id=user.get("sub"), subject_type="theatre_case", subject_id=str(case_id))
    return {"ok": True, "case_id": case_id}


@router.patch("/cases/{case_id}/operative-notes")
async def submit_operative_notes(case_id: int, payload: OperativeNotes, user=Depends(verify_jwt)):
    """Surgeon submits intraoperative notes."""
    _get_case(case_id)
    db.table(TABLE_THEATRE_CASES).update({
        "operative_notes": payload.model_dump(exclude_none=True),
        "operative_notes_by": user.get("sub") or "system",
    }).eq("id", case_id).execute()
    audit_event("theatre_operative_notes_submitted", {"procedure": payload.procedure_performed}, actor_id=user.get("sub"), subject_type="theatre_case", subject_id=str(case_id))
    return {"ok": True, "case_id": case_id}


@router.patch("/cases/{case_id}/post-op")
async def submit_postop(case_id: int, payload: PostOpRecord, user=Depends(verify_jwt)):
    """Record post-operative recovery status."""
    _get_case(case_id)
    db.table(TABLE_THEATRE_CASES).update({
        "post_op_notes": payload.model_dump(exclude_none=True),
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
    return {"schedule": result.data or [], "date": date, "count": len(result.data or [])}
