"""Clinical Documentation Router — ICD-10 lookup + Problem List."""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.constants import TABLE_ICD10_CODES, TABLE_PATIENTS, TABLE_PROBLEM_LIST
from src.db import audit_event, db
from src.middleware import verify_jwt

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/clinical", tags=["Clinical Documentation"])

PROBLEM_STATUS_ALLOWED = {"active", "resolved", "inactive", "chronic"}


# ─── Schemas ─────────────────────────────────────────────────────────────────

class ProblemCreate(BaseModel):
    icd10_code: Optional[str] = None
    description: str = Field(..., min_length=1)
    encounter_id: Optional[int] = None
    onset_date: Optional[str] = None
    status: str = "active"

    model_config = {"extra": "ignore"}


class ProblemUpdate(BaseModel):
    status: Optional[str] = None
    description: Optional[str] = None
    resolved_at: Optional[str] = None

    model_config = {"extra": "ignore"}


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _get_patient(patient_id: int) -> dict:
    r = db.table(TABLE_PATIENTS).select("id,mrn").eq("id", patient_id).execute()
    if not r.data:
        raise HTTPException(status_code=404, detail=f"Patient {patient_id} not found")
    return r.data[0]


# ─── ICD-10 Search ───────────────────────────────────────────────────────────

@router.get("/icd10")
async def search_icd10(
    q: str = Query(..., min_length=2, description="Code prefix or diagnosis keyword"),
    limit: int = Query(20, ge=1, le=50),
    user=Depends(verify_jwt),
):
    """Search ICD-10 codes by code prefix or description keyword."""
    q = q.strip()
    try:
        results = (
            db.table(TABLE_ICD10_CODES)
            .select("code,description,category")
            .or_(f"code.ilike.{q}%,description.ilike.%{q}%")
            .order("code")
            .limit(limit)
            .execute()
        )
        return {"codes": results.data or [], "count": len(results.data or [])}
    except Exception as exc:
        logger.error("ICD-10 search failed: %s", exc)
        return {"codes": [], "count": 0}


# ─── Problem List ─────────────────────────────────────────────────────────────

@router.post("/patients/{patient_id}/problems", status_code=201)
async def add_problem(patient_id: int, payload: ProblemCreate, user=Depends(verify_jwt)):
    """Add a problem to a patient's problem list."""
    _get_patient(patient_id)
    if payload.status not in PROBLEM_STATUS_ALLOWED:
        raise HTTPException(status_code=422, detail=f"status must be one of {sorted(PROBLEM_STATUS_ALLOWED)}")

    data = {
        "patient_id": patient_id,
        "icd10_code": payload.icd10_code,
        "description": payload.description,
        "encounter_id": payload.encounter_id,
        "onset_date": payload.onset_date,
        "status": payload.status,
        "noted_by": user.get("sub") or user.get("email"),
    }
    try:
        result = db.table(TABLE_PROBLEM_LIST).insert(data).execute()
    except Exception as exc:
        logger.error("Problem insert failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to add problem")

    problem = (result.data or [data])[0]
    audit_event(
        "problem_added",
        {"icd10_code": payload.icd10_code, "description": payload.description},
        actor_id=user.get("sub"),
        subject_type="patient",
        subject_id=str(patient_id),
    )
    return {"ok": True, "problem": problem}


@router.get("/patients/{patient_id}/problems")
async def list_problems(
    patient_id: int,
    status: Optional[str] = Query(None),
    user=Depends(verify_jwt),
):
    """List all problems on a patient's problem list."""
    _get_patient(patient_id)
    query = (
        db.table(TABLE_PROBLEM_LIST)
        .select("*")
        .eq("patient_id", patient_id)
        .order("created_at", desc=True)
    )
    if status:
        query = query.eq("status", status)
    result = query.execute()
    return {"problems": result.data or [], "count": len(result.data or [])}


@router.patch("/problems/{problem_id}")
async def update_problem(problem_id: int, payload: ProblemUpdate, user=Depends(verify_jwt)):
    """Update a problem status or description."""
    r = db.table(TABLE_PROBLEM_LIST).select("id,patient_id").eq("id", problem_id).execute()
    if not r.data:
        raise HTTPException(status_code=404, detail=f"Problem {problem_id} not found")

    updates = payload.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    if "status" in updates and updates["status"] not in PROBLEM_STATUS_ALLOWED:
        raise HTTPException(status_code=422, detail=f"status must be one of {sorted(PROBLEM_STATUS_ALLOWED)}")

    try:
        db.table(TABLE_PROBLEM_LIST).update(updates).eq("id", problem_id).execute()
    except Exception as exc:
        logger.error("Problem update failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to update problem")

    audit_event(
        "problem_updated",
        {"problem_id": problem_id, "fields": list(updates.keys())},
        actor_id=user.get("sub"),
        subject_type="patient",
        subject_id=str(r.data[0]["patient_id"]),
    )
    return {"ok": True, "problem_id": problem_id, "updated_fields": list(updates.keys())}


@router.delete("/problems/{problem_id}", status_code=200)
async def delete_problem(problem_id: int, user=Depends(verify_jwt)):
    """Remove a problem from the problem list."""
    r = db.table(TABLE_PROBLEM_LIST).select("id,patient_id").eq("id", problem_id).execute()
    if not r.data:
        raise HTTPException(status_code=404, detail=f"Problem {problem_id} not found")
    patient_id = r.data[0]["patient_id"]
    try:
        db.table(TABLE_PROBLEM_LIST).update({"status": "inactive"}).eq("id", problem_id).execute()
    except Exception as exc:
        logger.error("Problem delete failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to remove problem")

    audit_event(
        "problem_removed",
        {"problem_id": problem_id},
        actor_id=user.get("sub"),
        subject_type="patient",
        subject_id=str(patient_id),
    )
    return {"ok": True, "problem_id": problem_id}
