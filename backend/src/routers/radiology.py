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

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.db import db, audit_event
from src.middleware import verify_jwt, require_role
from src.services.realtime import realtime_hub
from src.constants import (
    TABLE_RADIOLOGY_ORDERS,
    TABLE_REPORT_TEMPLATES,
    TABLE_PATIENTS,
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


class RadiologyVerifyRequest(BaseModel):
    notes: Optional[str] = None

    model_config = {"extra": "ignore"}


class ReportAmend(ReportSubmit):
    """Corrects a verified report. Verified reports are immutable in place —
    this snapshots the current version into report_history and resets
    verified_by/verified_at, mirroring Lab's ResultAmendRequest."""
    amendment_reason: str = Field(..., min_length=1)


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


def _jsonable(v):
    """The db layer returns timestamptz columns as native datetime objects —
    stringify them before embedding in a jsonb column (json.dumps can't
    serialize datetime directly)."""
    return v.isoformat() if isinstance(v, datetime) else v


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
    ordered_by: Optional[str] = Query(None, description="Filter to orders placed by this user (JWT sub)"),
    limit: int              = Query(50, ge=1, le=200),
    user=Depends(verify_jwt),
):
    """Radiology worklist with optional filters."""
    # Live worklist = native orders only (external_source IS NULL). The ~24k
    # Hope-imported historical rows must never count as active queue entries —
    # same rule as queue_clinical.py's encounter queue and lab.py's /orders.
    query = (
        db.table(TABLE_RADIOLOGY_ORDERS)
        .select("*")
        .is_("external_source", None)
        .order("ordered_at", desc=True)
        .limit(limit)
    )
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
    if ordered_by:
        query = query.eq("ordered_by", ordered_by)
    result = query.execute()
    orders: list = list(result.data or [])

    # Batch-enrich each order with basic patient demographics (1 extra query for all)
    if orders:
        try:
            pid_set = list({o["patient_id"] for o in orders if o.get("patient_id") is not None})
            if pid_set:
                pt_rows = db.table(TABLE_PATIENTS).select(
                    "id,mrn,first_name,last_name,gender,date_of_birth,blood_group,hmo_provider,phone"
                ).in_("id", pid_set).execute()
                pt_map = {p["id"]: p for p in (pt_rows.data or [])}
                for order in orders:
                    p = pt_map.get(order.get("patient_id"))
                    if p:
                        fn = (p.get("first_name") or "").strip()
                        ln = (p.get("last_name") or "").strip()
                        order["patient_name"]   = f"{fn} {ln}".strip() or None
                        order["patient_mrn"]    = p.get("mrn")
                        order["patient_gender"] = p.get("gender")
                        order["patient_dob"]    = p.get("date_of_birth")
                        order["patient_blood_group"] = p.get("blood_group")
                        order["patient_hmo"]    = p.get("hmo_provider")
                        order["patient_phone"]  = p.get("phone")
        except Exception as exc:
            logger.warning("radiology order patient enrichment failed: %s", exc)

    return {"orders": orders, "count": len(orders)}


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
    if payload.status == "scheduled":
        updates["scheduled_at"] = payload.scheduled_at or _now()
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
    """Radiologist submits the report and impression. An unverified report is
    updated in place on re-submission; a verified report must go through
    /report/amend instead, since authenticated reports are immutable."""
    order = _get_order(order_id)
    if order["status"] == "cancelled":
        raise HTTPException(status_code=409, detail="Cannot report a cancelled order")
    if order["status"] == "reported" and order.get("verified_at"):
        raise HTTPException(
            status_code=409,
            detail="Report already verified — use PATCH /radiology/orders/{order_id}/report/amend to correct it",
        )

    # Calculate TAT in minutes if ordered_at is available — only computed
    # once, so a pre-verify edit doesn't distort turnaround-time metrics.
    tat_minutes = order.get("tat_minutes")
    if tat_minutes is None and order.get("ordered_at"):
        try:
            ordered_ts = order["ordered_at"]
            # The db layer returns timestamptz columns as native datetime
            # objects, not strings — only string responses need parsing.
            if isinstance(ordered_ts, str):
                ordered_ts = datetime.fromisoformat(ordered_ts.replace("Z", "+00:00"))
            tat_minutes = round((datetime.now(timezone.utc) - ordered_ts).total_seconds() / 60)
        except Exception:
            pass

    updates = {
        "status": "reported",
        "report": payload.report,
        "impression": payload.impression,
        "radiologist_id": payload.radiologist_id or user.get("sub") or "system",
    }
    if order.get("reported_at") is None:
        updates["reported_at"] = _now()
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
    if order.get("encounter_id"):
        asyncio.create_task(realtime_hub.broadcast("encounter_updates", {
            "event": "radiology_result_ready",
            "encounter_id": order.get("encounter_id"),
            "order_id": order_id,
            "modality": order.get("modality"),
        }))
    return {"ok": True, "order_id": order_id, "tat_minutes": tat_minutes}


@router.post("/orders/{order_id}/verify")
async def verify_report(order_id: int, payload: RadiologyVerifyRequest, user=Depends(verify_jwt)):
    """Finalize and sign off a submitted report. Once verified, corrections
    go through /report/amend instead of PATCH /report directly."""
    order = _get_order(order_id)
    if order["status"] != "reported":
        raise HTTPException(
            status_code=409,
            detail=f"Order is '{order['status']}'; verification requires a submitted report",
        )
    if order.get("verified_at"):
        raise HTTPException(
            status_code=409,
            detail=f"Already verified by {order.get('verified_by') or 'unknown'} at {order['verified_at']}",
        )

    now_iso = _now()
    verified_by = user.get("sub") or "system"
    updates = {"verified_by": verified_by, "verified_at": now_iso}
    if payload.notes:
        updates["notes"] = payload.notes
    db.table(TABLE_RADIOLOGY_ORDERS).update(updates).eq("id", order_id).execute()

    audit_event(
        "radiology_report_verified",
        {"modality": order.get("modality")},
        actor_id=user.get("sub"),
        subject_type="radiology_order",
        subject_id=str(order_id),
    )
    return {"ok": True, "order_id": order_id, "verified_by": verified_by, "verified_at": now_iso}


@router.patch("/orders/{order_id}/report/amend")
async def amend_report(order_id: int, payload: ReportAmend, user=Depends(verify_jwt)):
    """Correct a verified report. Snapshots the current version into
    report_history and resets verified_by/verified_at — the amendment starts
    its own verify cycle, mirroring Lab's amend_result."""
    order = _get_order(order_id)
    if order["status"] != "reported" or not order.get("verified_at"):
        raise HTTPException(
            status_code=409,
            detail="No verified report exists to amend — unverified reports can be corrected directly via PATCH /radiology/orders/{order_id}/report",
        )

    now_iso = _now()
    history = list(order.get("report_history") or [])
    history.append({
        "report": order.get("report"),
        "impression": order.get("impression"),
        "findings": order.get("findings"),
        "radiologist_id": order.get("radiologist_id"),
        "reported_at": _jsonable(order.get("reported_at")),
        "verified_by": order.get("verified_by"),
        "verified_at": _jsonable(order.get("verified_at")),
        "amendment_reason": order.get("amendment_reason"),
        "superseded_at": now_iso,
    })

    updates = {
        "report": payload.report,
        "impression": payload.impression,
        "radiologist_id": payload.radiologist_id or user.get("sub") or "system",
        "reported_at": now_iso,
        "verified_by": None,
        "verified_at": None,
        "amendment_reason": payload.amendment_reason,
        "report_history": history,
    }
    if payload.findings:
        updates["findings"] = payload.findings

    db.table(TABLE_RADIOLOGY_ORDERS).update(updates).eq("id", order_id).execute()
    audit_event(
        "radiology_report_amended",
        {"prior_reported_at": history[-1]["reported_at"], "reason": payload.amendment_reason},
        actor_id=user.get("sub"),
        subject_type="radiology_order",
        subject_id=str(order_id),
    )
    return {"ok": True, "order_id": order_id, "amended": True}


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
    # Same native-only rule as list_orders() above — otherwise these stats are
    # dominated by ~24k historical Hope-imported rows instead of live department activity.
    result = (
        db.table(TABLE_RADIOLOGY_ORDERS)
        .select("modality,status,tat_minutes,urgency")
        .is_("external_source", None)
        .execute()
    )
    rows = result.data or []

    modality_counts: dict = {}
    tat_by_modality: dict = {}
    pending = 0
    in_progress = 0
    reported = 0
    stat_pending = 0

    for r in rows:
        mod = r.get("modality") or "other"
        modality_counts[mod] = modality_counts.get(mod, 0) + 1
        status = r.get("status")
        if status in ("ordered", "scheduled"):
            pending += 1
        if status == "in_progress":
            in_progress += 1
        if status == "reported":
            reported += 1
            if r.get("tat_minutes") is not None:
                tat_by_modality.setdefault(mod, []).append(r["tat_minutes"])
        if r.get("urgency") == "stat" and status not in ("reported", "cancelled"):
            stat_pending += 1

    avg_tat = {
        mod: round(sum(vals) / len(vals), 1)
        for mod, vals in tat_by_modality.items()
    }

    return {
        "pending": pending,
        "in_progress": in_progress,
        "reported": reported,
        "stat_pending": stat_pending,
        "modality_counts": modality_counts,
        "avg_tat_minutes": avg_tat,
        "pending_count": pending + in_progress,  # back-compat with existing consumers
        "reported_count": reported,
        "total": len(rows),
    }
