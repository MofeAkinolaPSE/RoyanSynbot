"""
Radiology Router — RoyanHealth / Royan Hospital
==================================================
Imaging requests, worklist management, report entry, and TAT analytics.
VistA Reference: Clinical Procedures / Imaging module.

Endpoints:
  POST   /radiology/orders                          – Create imaging request
  GET    /radiology/orders                          – Worklist (filter: status, modality, date)
  GET    /radiology/orders/{id}                     – Single order detail
  PATCH  /radiology/orders/{id}/report              – Radiologist submits report + impression
  PATCH  /radiology/orders/{id}/status              – Advance order status
  GET    /radiology/patients/{patient_id}/history   – Cumulative imaging history
  GET    /radiology/stats                           – TAT + modality volume report
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
    TABLE_RADIOLOGY_ORDERS,
    TABLE_REPORT_TEMPLATES,
    RADIOLOGY_MODALITIES_ALLOWED,
    RADIOLOGY_STATUS_ALLOWED,
    RADIOLOGY_STATUS_TRANSITIONS,
    LAB_URGENCY_ALLOWED,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/radiology", tags=["Radiology"])

MODALITIES  = RADIOLOGY_MODALITIES_ALLOWED
STATUSES    = RADIOLOGY_STATUS_ALLOWED
TRANSITIONS = RADIOLOGY_STATUS_TRANSITIONS
URGENCIES   = LAB_URGENCY_ALLOWED      # routine | urgent | stat


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class RadiologyOrderCreate(BaseModel):
    encounter_id: int
    patient_id: int
    modality: str                          # xray | ultrasound | ct | mri | ecg | echo | …
    body_part: Optional[str] = None
    clinical_indication: Optional[str] = None
    urgency: str = "routine"
    ordered_by: Optional[str] = None
    notes: Optional[str] = None
    pacs_study_uid: Optional[str] = None

    model_config = {"extra": "ignore"}


class ReportSubmit(BaseModel):
    report: str = Field(..., min_length=1)
    impression: Optional[str] = None
    radiologist_id: Optional[str] = None
    findings: Optional[str] = None        # structured findings JSON string

    model_config = {"extra": "ignore"}


class StatusAdvance(BaseModel):
    status: str
    notes: Optional[str] = None
    scheduled_at: Optional[str] = None   # ISO datetime — used when advancing to "scheduled"

    model_config = {"extra": "ignore"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_order(order_id: int) -> dict:
    r = db.table(TABLE_RADIOLOGY_ORDERS).select("*").eq("id", order_id).execute()
    if not r.data:
        raise HTTPException(status_code=404, detail=f"Radiology order {order_id} not found")
    return r.data[0]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/orders", status_code=201)
async def create_order(payload: RadiologyOrderCreate, user=Depends(verify_jwt)):
    """Create a new imaging request."""
    mod = payload.modality.lower()
    if mod not in MODALITIES:
        raise HTTPException(status_code=422, detail=f"modality must be one of {MODALITIES}")
    if payload.urgency not in URGENCIES:
        raise HTTPException(status_code=422, detail=f"urgency must be one of {URGENCIES}")

    data = payload.model_dump(exclude_none=True)
    data["modality"]   = mod
    data["ordered_by"] = payload.ordered_by or user.get("sub") or "system"
    data["status"]     = "ordered"

    try:
        result = db.table(TABLE_RADIOLOGY_ORDERS).insert(data).execute()
    except Exception as exc:
        logger.error("Radiology order creation failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to create radiology order")

    order = result.data[0] if result.data else data
    audit_event(
        "radiology_order_created",
        {"modality": mod, "urgency": payload.urgency},
        actor_id=user.get("sub"),
        subject_type="radiology_order",
        subject_id=str(order.get("id") or ""),
    )
    return {"ok": True, "order": order}


@router.get("/orders")
async def list_orders(
    status: Optional[str]   = Query(None),
    modality: Optional[str] = Query(None),
    patient_id: Optional[int] = Query(None),
    encounter_id: Optional[int] = Query(None),
    urgency: Optional[str]  = Query(None),
    date: Optional[str]     = Query(None),   # ISO date prefix filter on ordered_at
    limit: int              = Query(50, ge=1, le=200),
    user=Depends(verify_jwt),
):
    """Radiology worklist with optional filters."""
    query = db.table(TABLE_RADIOLOGY_ORDERS).select("*").order("ordered_at", desc=True).limit(limit)
    if status:
        query = query.eq("status", status)
    if modality:
        query = query.eq("modality", modality.lower())
    if patient_id:
        query = query.eq("patient_id", patient_id)
    if encounter_id:
        query = query.eq("encounter_id", encounter_id)
    if urgency:
        query = query.eq("urgency", urgency)
    if date:
        query = query.gte("ordered_at", date).lt("ordered_at", date + "T99")
    result = query.execute()
    return {"orders": result.data or [], "count": len(result.data or [])}


@router.get("/orders/{order_id}")
async def get_order(order_id: int, user=Depends(verify_jwt)):
    return {"order": _get_order(order_id)}


@router.patch("/orders/{order_id}/status")
async def advance_status(order_id: int, payload: StatusAdvance, user=Depends(verify_jwt)):
    """Advance the order through the status state machine."""
    order = _get_order(order_id)
    current = order["status"]

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
    if payload.scheduled_at and payload.status == "scheduled":
        updates["scheduled_at"] = payload.scheduled_at
    if payload.status == "in_progress":
        updates["started_at"] = _now()

    db.table(TABLE_RADIOLOGY_ORDERS).update(updates).eq("id", order_id).execute()
    audit_event(
        "radiology_status_advanced",
        {"from": current, "to": payload.status},
        actor_id=user.get("sub"),
        subject_type="radiology_order",
        subject_id=str(order_id),
    )
    return {"ok": True, "order_id": order_id, "status": payload.status}


@router.patch("/orders/{order_id}/report", status_code=200)
async def submit_report(order_id: int, payload: ReportSubmit, user=Depends(verify_jwt)):
    """Radiologist submits final report and impression."""
    order = _get_order(order_id)
    if order["status"] == "cancelled":
        raise HTTPException(status_code=409, detail="Cannot report a cancelled order")
    if order["status"] == "reported":
        raise HTTPException(status_code=409, detail="Order already reported")

    # Calculate TAT in minutes if ordered_at is available
    tat_minutes = None
    if order.get("ordered_at"):
        try:
            ordered_ts = datetime.fromisoformat(order["ordered_at"].replace("Z", "+00:00"))
            tat_minutes = round((datetime.now(timezone.utc) - ordered_ts).total_seconds() / 60)
        except Exception:
            pass

    updates = {
        "status": "reported",
        "report": payload.report,
        "impression": payload.impression,
        "radiologist_id": payload.radiologist_id or user.get("sub") or "system",
        "reported_at": _now(),
    }
    if payload.findings:
        updates["findings"] = payload.findings
    if tat_minutes is not None:
        updates["tat_minutes"] = tat_minutes

    db.table(TABLE_RADIOLOGY_ORDERS).update(updates).eq("id", order_id).execute()
    audit_event(
        "radiology_report_submitted",
        {"modality": order.get("modality"), "tat_minutes": tat_minutes},
        actor_id=user.get("sub"),
        subject_type="radiology_order",
        subject_id=str(order_id),
    )
    return {"ok": True, "order_id": order_id, "tat_minutes": tat_minutes}


@router.get("/patients/{patient_id}/history")
async def patient_history(
    patient_id: int,
    modality: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    user=Depends(verify_jwt),
):
    """Cumulative imaging history for a patient."""
    query = (
        db.table(TABLE_RADIOLOGY_ORDERS)
        .select("id,modality,body_part,clinical_indication,urgency,status,ordered_at,reported_at,impression,tat_minutes")
        .eq("patient_id", patient_id)
        .order("ordered_at", desc=True)
        .limit(limit)
    )
    if modality:
        query = query.eq("modality", modality.lower())
    result = query.execute()
    return {"history": result.data or [], "count": len(result.data or []), "patient_id": patient_id}


@router.get("/templates")
async def list_report_templates(
    modality: Optional[str] = Query(None),
    search: Optional[str] = Query(None, description="Match against variant_name"),
    limit: int = Query(100, ge=1, le=500),
    user=Depends(verify_jwt),
):
    """List canned-findings report templates, e.g. to populate a study-type
    picker before the radiologist edits and submits their report."""
    query = (
        db.table(TABLE_REPORT_TEMPLATES)
        .select("id,modality,body_part,variant_name,template_text,source_file")
        .eq("is_active", True)
        .order("variant_name")
        .limit(limit)
    )
    if modality:
        query = query.eq("modality", modality.lower())
    if search:
        query = query.ilike("variant_name", f"%{search.strip()}%")
    result = query.execute()
    return {"templates": result.data or [], "count": len(result.data or [])}


@router.get("/templates/{template_id}")
async def get_report_template(template_id: int, user=Depends(verify_jwt)):
    """Fetch one template's full text — the 'load template' action pre-fills
    the report/impression form fields from this before the radiologist edits."""
    r = db.table(TABLE_REPORT_TEMPLATES).select("*").eq("id", template_id).execute()
    if not r.data:
        raise HTTPException(status_code=404, detail=f"Report template {template_id} not found")
    return {"template": r.data[0]}


@router.get("/stats")
async def radiology_stats(user=Depends(verify_jwt)):
    """TAT summary and modality volume counts."""
    result = db.table(TABLE_RADIOLOGY_ORDERS).select("modality,status,tat_minutes,urgency").execute()
    rows = result.data or []

    modality_counts: dict = {}
    tat_by_modality: dict = {}
    pending_count = 0
    reported_count = 0

    for r in rows:
        mod = r.get("modality") or "other"
        modality_counts[mod] = modality_counts.get(mod, 0) + 1
        if r.get("status") in ("ordered", "scheduled", "in_progress"):
            pending_count += 1
        if r.get("status") == "reported":
            reported_count += 1
            if r.get("tat_minutes") is not None:
                tat_by_modality.setdefault(mod, []).append(r["tat_minutes"])

    avg_tat = {
        mod: round(sum(vals) / len(vals), 1)
        for mod, vals in tat_by_modality.items()
    }

    return {
        "modality_counts": modality_counts,
        "avg_tat_minutes": avg_tat,
        "pending_count": pending_count,
        "reported_count": reported_count,
        "total": len(rows),
    }
