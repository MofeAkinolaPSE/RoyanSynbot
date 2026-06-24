"""
Nursing Router — SynbotHealth / Royan Hospital
================================================
Covers inpatient nursing workflows: vitals, care plans, pain scores,
fluid balance, and nursing notes.

Endpoints:
  POST /nursing/vitals                              – Record a vitals set
  GET  /nursing/vitals/{patient_id}                 – Patient vitals history
  POST /nursing/care-plans                          – Create care plan
  GET  /nursing/care-plans/{patient_id}             – List care plans
  PATCH /nursing/care-plans/{plan_id}               – Update care plan
  POST /nursing/fluid-balance                       – Log a fluid balance entry
  GET  /nursing/fluid-balance/{encounter_id}        – 24-hour fluid balance summary
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.db import db, audit_event
from src.middleware import verify_jwt
from src.constants import (
    TABLE_VITALS,
    TABLE_NURSING_CARE_PLANS,
    TABLE_FLUID_BALANCE,
    TABLE_MAR_ENTRIES,
    MAR_STATUS_ALLOWED,
    TABLE_PATIENTS,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/nursing", tags=["Nursing"])

CARE_PLAN_STATUSES = {"active", "resolved", "deferred", "discontinued"}
FLUID_TYPES        = {"intake", "output"}
PAIN_SCALE_MAX     = 10


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class VitalsCreate(BaseModel):
    patient_id: int
    encounter_id: Optional[int] = None
    temperature: Optional[float] = None       # Celsius
    pulse: Optional[int] = None               # bpm
    respiratory_rate: Optional[int] = None    # breaths/min
    bp_systolic: Optional[int] = None         # mmHg
    bp_diastolic: Optional[int] = None        # mmHg
    spo2: Optional[float] = None              # %
    weight: Optional[float] = None            # kg
    height: Optional[float] = None            # cm
    bmi: Optional[float] = None
    pain_score: Optional[int] = Field(None, ge=0, le=10)
    gcs: Optional[int] = Field(None, ge=3, le=15)   # Glasgow Coma Scale
    blood_glucose: Optional[float] = None     # mmol/L
    notes: Optional[str] = None

    model_config = {"extra": "ignore"}


class CarePlanCreate(BaseModel):
    patient_id: int
    encounter_id: Optional[int] = None
    problem: str = Field(..., min_length=1, max_length=500)
    goal: Optional[str] = None
    interventions: Optional[str] = None       # free-text or JSON
    evaluation: Optional[str] = None
    priority: str = "medium"                  # low | medium | high | critical
    status: str = "active"
    assigned_to: Optional[str] = None
    review_date: Optional[str] = None

    model_config = {"extra": "ignore"}


class CarePlanUpdate(BaseModel):
    goal: Optional[str] = None
    interventions: Optional[str] = None
    evaluation: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    assigned_to: Optional[str] = None
    review_date: Optional[str] = None

    model_config = {"extra": "ignore"}


class FluidEntry(BaseModel):
    patient_id: int
    encounter_id: int
    fluid_type: str                            # intake | output
    route: Optional[str] = None               # oral | iv | ng | urine | drain | vomit | etc.
    volume_ml: float = Field(..., gt=0)
    fluid_name: Optional[str] = None          # "Normal Saline", "Urine", etc.
    notes: Optional[str] = None

    model_config = {"extra": "ignore"}


# ---------------------------------------------------------------------------
# Endpoints — Vitals
# ---------------------------------------------------------------------------

@router.post("/vitals", status_code=201)
async def record_vitals(payload: VitalsCreate, user=Depends(verify_jwt)):
    """Record a vitals observation for a patient."""
    data = payload.model_dump(exclude_none=True)

    # Auto-calculate BMI if height + weight present and bmi not supplied
    if not data.get("bmi") and data.get("weight") and data.get("height"):
        h_m = data["height"] / 100
        data["bmi"] = round(data["weight"] / (h_m ** 2), 1)

    data["recorded_by"] = user.get("sub") or "system"

    try:
        result = db.table(TABLE_VITALS).insert(data).execute()
    except Exception as exc:
        logger.error("Vitals insert failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to save vitals")

    row = (result.data or [data])[0]
    audit_event(
        "vitals_recorded",
        {"pain_score": payload.pain_score, "spo2": payload.spo2},
        actor_id=user.get("sub"),
        subject_type="vitals",
        subject_id=str(row.get("id") or ""),
    )
    return {"ok": True, "vitals": row}


@router.get("/vitals/{patient_id}")
async def list_vitals(
    patient_id: int,
    encounter_id: Optional[int] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    user=Depends(verify_jwt),
):
    """Return vitals history for a patient, most recent first."""
    query = (
        db.table(TABLE_VITALS)
        .select("*")
        .eq("patient_id", patient_id)
        .order("recorded_at", desc=True)
        .limit(limit)
    )
    if encounter_id:
        query = query.eq("encounter_id", encounter_id)
    result = query.execute()
    return {"vitals": result.data or [], "count": len(result.data or []), "patient_id": patient_id}


# ---------------------------------------------------------------------------
# Endpoints — Care Plans
# ---------------------------------------------------------------------------

@router.post("/care-plans", status_code=201)
async def create_care_plan(payload: CarePlanCreate, user=Depends(verify_jwt)):
    """Create a nursing care plan entry for a patient problem."""
    if payload.status not in CARE_PLAN_STATUSES:
        raise HTTPException(status_code=422, detail=f"status must be one of {CARE_PLAN_STATUSES}")

    data = payload.model_dump(exclude_none=True)
    data["created_by"] = user.get("sub") or "system"

    try:
        result = db.table(TABLE_NURSING_CARE_PLANS).insert(data).execute()
    except Exception as exc:
        logger.error("Care plan insert failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to save care plan")

    plan = (result.data or [data])[0]
    audit_event("care_plan_created", {"problem": payload.problem}, actor_id=user.get("sub"), subject_type="care_plan", subject_id=str(plan.get("id") or ""))
    return {"ok": True, "care_plan": plan}


@router.get("/care-plans/{patient_id}")
async def list_care_plans(
    patient_id: int,
    encounter_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    user=Depends(verify_jwt),
):
    """List nursing care plans for a patient."""
    query = db.table(TABLE_NURSING_CARE_PLANS).select("*").eq("patient_id", patient_id).order("created_at", desc=True)
    if encounter_id:
        query = query.eq("encounter_id", encounter_id)
    if status:
        query = query.eq("status", status)
    result = query.execute()
    return {"care_plans": result.data or [], "count": len(result.data or [])}


@router.patch("/care-plans/{plan_id}")
async def update_care_plan(plan_id: int, payload: CarePlanUpdate, user=Depends(verify_jwt)):
    r = db.table(TABLE_NURSING_CARE_PLANS).select("id").eq("id", plan_id).execute()
    if not r.data:
        raise HTTPException(status_code=404, detail=f"Care plan {plan_id} not found")
    updates = payload.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=422, detail="No update fields provided")
    if updates.get("status") and updates["status"] not in CARE_PLAN_STATUSES:
        raise HTTPException(status_code=422, detail=f"status must be one of {CARE_PLAN_STATUSES}")
    db.table(TABLE_NURSING_CARE_PLANS).update(updates).eq("id", plan_id).execute()
    return {"ok": True, "plan_id": plan_id}


# ---------------------------------------------------------------------------
# Endpoints — Fluid Balance
# ---------------------------------------------------------------------------

@router.post("/fluid-balance", status_code=201)
async def log_fluid_entry(payload: FluidEntry, user=Depends(verify_jwt)):
    """Log a single fluid intake or output entry for a patient encounter."""
    if payload.fluid_type not in FLUID_TYPES:
        raise HTTPException(status_code=422, detail=f"fluid_type must be one of {FLUID_TYPES}")

    data = payload.model_dump(exclude_none=True)
    data["recorded_by"] = user.get("sub") or "system"

    try:
        result = db.table(TABLE_FLUID_BALANCE).insert(data).execute()
    except Exception as exc:
        logger.error("Fluid balance insert failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to save fluid entry")

    row = (result.data or [data])[0]
    return {"ok": True, "entry": row}


@router.get("/fluid-balance/{encounter_id}")
async def get_fluid_balance(encounter_id: int, user=Depends(verify_jwt)):
    """Return all fluid entries for an encounter with running totals."""
    result = (
        db.table(TABLE_FLUID_BALANCE)
        .select("*")
        .eq("encounter_id", encounter_id)
        .order("recorded_at")
        .execute()
    )
    entries = result.data or []
    total_intake  = sum(float(e.get("volume_ml") or 0) for e in entries if e.get("fluid_type") == "intake")
    total_output  = sum(float(e.get("volume_ml") or 0) for e in entries if e.get("fluid_type") == "output")
    balance       = round(total_intake - total_output, 1)
    return {
        "entries": entries,
        "count": len(entries),
        "total_intake_ml": round(total_intake, 1),
        "total_output_ml": round(total_output, 1),
        "balance_ml": balance,
        "encounter_id": encounter_id,
    }


# ---------------------------------------------------------------------------
# Endpoints — MAR (Medication Administration Record)
# ---------------------------------------------------------------------------

class MARCreate(BaseModel):
    encounter_id: int
    patient_id: int
    prescription_id: Optional[int] = None
    drug_name: str = Field(..., min_length=1, max_length=200)
    dose: Optional[str] = None
    route: Optional[str] = None
    scheduled_time: Optional[str] = None   # ISO datetime when dose was scheduled
    administered_at: Optional[str] = None  # ISO datetime when actually given
    status: str = "administered"
    notes: Optional[str] = None
    override_reason: Optional[str] = None  # required if status is "held" or "refused"

    model_config = {"extra": "ignore"}


class MARUpdate(BaseModel):
    status: Optional[str] = None
    administered_at: Optional[str] = None
    notes: Optional[str] = None
    override_reason: Optional[str] = None

    model_config = {"extra": "ignore"}


@router.post("/mar", status_code=201)
async def record_mar_entry(payload: MARCreate, user=Depends(verify_jwt)):
    """Record a medication administration event."""
    if payload.status not in MAR_STATUS_ALLOWED:
        raise HTTPException(status_code=422, detail=f"status must be one of {MAR_STATUS_ALLOWED}")

    if payload.status in {"held", "refused"} and not payload.override_reason:
        raise HTTPException(status_code=422, detail="override_reason is required when status is held or refused")

    data = payload.model_dump(exclude_none=True)
    data["administered_by"] = user.get("sub") or "system"

    try:
        result = db.table(TABLE_MAR_ENTRIES).insert(data).execute()
    except Exception as exc:
        logger.error("MAR insert failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to save MAR entry")

    row = (result.data or [data])[0]
    audit_event(
        "mar_recorded",
        {"drug": payload.drug_name, "status": payload.status},
        actor_id=user.get("sub"),
        subject_type="mar",
        subject_id=str(row.get("id") or ""),
    )
    return {"ok": True, "mar_entry": row}


@router.get("/mar/{encounter_id}")
async def list_mar(
    encounter_id: int,
    status: Optional[str] = Query(None),
    user=Depends(verify_jwt),
):
    """Return the MAR for an encounter, grouped with status summary."""
    query = (
        db.table(TABLE_MAR_ENTRIES)
        .select("*")
        .eq("encounter_id", encounter_id)
        .order("administered_at", desc=True)
    )
    if status:
        query = query.eq("status", status)
    result = query.execute()
    entries = result.data or []

    summary: dict[str, int] = {}
    for e in entries:
        s = e.get("status", "unknown")
        summary[s] = summary.get(s, 0) + 1

    return {
        "mar": entries,
        "count": len(entries),
        "summary": summary,
        "encounter_id": encounter_id,
    }


@router.patch("/mar/{entry_id}")
async def update_mar_entry(entry_id: int, payload: MARUpdate, user=Depends(verify_jwt)):
    """Update the status or notes of a MAR entry."""
    r = db.table(TABLE_MAR_ENTRIES).select("id").eq("id", entry_id).execute()
    if not r.data:
        raise HTTPException(status_code=404, detail=f"MAR entry {entry_id} not found")

    updates = payload.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=422, detail="No update fields provided")
    if updates.get("status") and updates["status"] not in MAR_STATUS_ALLOWED:
        raise HTTPException(status_code=422, detail=f"status must be one of {MAR_STATUS_ALLOWED}")

    db.table(TABLE_MAR_ENTRIES).update(updates).eq("id", entry_id).execute()
    audit_event("mar_updated", updates, actor_id=user.get("sub"), subject_type="mar", subject_id=str(entry_id))
    return {"ok": True, "entry_id": entry_id}
