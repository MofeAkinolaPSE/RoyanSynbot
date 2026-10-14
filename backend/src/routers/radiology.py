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
from src.services.clinical_shared import attach_staff_names
from src.middleware import verify_jwt, require_role
from src.services.realtime import realtime_hub
from src.constants import (
    TABLE_PATIENT_INSURANCE,
    TABLE_PAYER_SERVICE_PRICES,
    TABLE_HMOS,
    TABLE_RADIOLOGY_ORDERS,
    TABLE_RADIOLOGY_REPORT_TEMPLATE_TEXTS,
    TABLE_RADIOLOGY_REPORT_TEMPLATES,
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
    # Optional, because radiology also takes WALK-INS.
    #
    # Requiring an encounter meant every study had to originate from a
    # consultation, so a client arriving at ScanCare asking for a scan could not
    # be booked at all — the department could only wait for work to be sent to
    # it. The column has always been nullable in the database; only this model
    # forced it.
    encounter_id: Optional[int] = None
    patient_id: int
    modality: str                          # xray | ultrasound | ct | mri | ecg | echo | …
    body_part: Optional[str] = None
    clinical_indication: Optional[str] = None
    urgency: str = "routine"
    ordered_by: Optional[str] = None
    notes: Optional[str] = None
    pacs_study_uid: Optional[str] = None
    # A walk-in asks for a named study, not a modality code. Both are accepted:
    # the catalogue supplies the name and price, modality stays for filtering.
    radiology_catalog_id: Optional[int] = None
    test_name: Optional[str] = None
    ordering_doctor: Optional[str] = None

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
def create_order(payload: RadiologyOrderCreate, user=Depends(verify_jwt)):
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

    # A walk-in has no referring clinician. Said plainly on the record rather
    # than left as an empty field someone later reads as missing data.
    if not payload.encounter_id:
        data.setdefault("ordering_doctor", "Walk-in (no referral)")
        note = (payload.notes or "").strip()
        marker = "Walk-in booked at radiology."
        data["notes"] = f"{marker} {note}".strip() if note else marker

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
def list_orders(
    status: Optional[str]   = Query(None),
    modality: Optional[str] = Query(None),
    patient_id: Optional[int] = Query(None),
    encounter_id: Optional[int] = Query(None),
    urgency: Optional[str]  = Query(None),
    date: Optional[str]     = Query(None),   # ISO date prefix filter on ordered_at
    ordered_by: Optional[str] = Query(None, description="Filter to orders placed by this user (JWT sub)"),
    view: Optional[str]     = Query(None, pattern="^(active|done)$", description="active: still to do (any day); done: reported today"),
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
    from src.services.worklist import apply_view
    query = apply_view(query, view, {"ordered", "scheduled", "in_progress"}, {"reported"}, "reported_at")
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
def get_order(order_id: int, user=Depends(verify_jwt)):
    order = _get_order(order_id)
    # Same uuid-instead-of-a-name problem as lab: the panel prints whoever
    # verified the report, and the column holds a JWT subject.
    attach_staff_names([order], {
        "verified_by": "verified_by_name",
        "radiologist_id": "radiologist_name",
    })
    return {"order": order}


@router.patch("/orders/{order_id}/status")
def advance_status(order_id: int, payload: StatusAdvance, user=Depends(verify_jwt)):
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

    if payload.status == "in_progress":
        from src.services.stage_billing import require_clearance   # pay before the scan (private outpatients)
        require_clearance("radiology_order", order_id)
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
        realtime_hub.publish("encounter_updates", {
            "event": "radiology_result_ready",
            "encounter_id": order.get("encounter_id"),
            "order_id": order_id,
            "modality": order.get("modality"),
        })
    return {"ok": True, "order_id": order_id, "tat_minutes": tat_minutes}


@router.post("/orders/{order_id}/verify")
def verify_report(order_id: int, payload: RadiologyVerifyRequest, user=Depends(verify_jwt)):
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
def amend_report(order_id: int, payload: ReportAmend, user=Depends(verify_jwt)):
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
def patient_history(
    patient_id: int,
    modality: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    user=Depends(verify_jwt),
):
    """Cumulative imaging history for a patient.

    Unlike GET /radiology/orders (the live worklist, which is deliberately
    restricted to native orders so 56k Hope-imported rows never appear as
    active queue entries), this INCLUDES migrated history — that is the whole
    point of a patient's cumulative record. 41,536 of those rows carry a real
    report, and the patient chart is where they belong.

    test_name/report/findings/radiologist_id are selected so the chart can show
    the actual result rather than just a row saying a study happened.
    """
    query = (
        db.table(TABLE_RADIOLOGY_ORDERS)
        .select(
            "id,test_name,modality,body_part,clinical_indication,urgency,status,"
            "ordered_at,reported_at,impression,findings,report,radiologist_id,tat_minutes"
        )
        .eq("patient_id", patient_id)
        .order("ordered_at", desc=True)
        .limit(limit)
    )
    if modality:
        query = query.eq("modality", modality.lower())
    result = query.execute()
    return {"history": result.data or [], "count": len(result.data or []), "patient_id": patient_id}


@router.get("/templates")
def list_report_templates(
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
def get_report_template(template_id: int, user=Depends(verify_jwt)):
    """Fetch one template's full text — the 'load template' action pre-fills
    the report/impression form fields from this before the radiologist edits."""
    r = db.table(TABLE_REPORT_TEMPLATES).select("*").eq("id", template_id).execute()
    if not r.data:
        raise HTTPException(status_code=404, detail=f"Report template {template_id} not found")
    return {"template": r.data[0]}


# ─── Royan's own section templates (migrated from Hope, migration 184) ───────
# DELIBERATELY SEPARATE from /templates above. Two different real datasets:
#
#   royan_report_templates          (42)  — licensed canned-findings library,
#                                           shaped modality / body_part /
#                                           variant_name / template_text
#   royan_radiology_report_templates (175) — Royan's OWN section templates,
#                                           shaped exam_type / section
#                                           (FINDINGS | OPINIONS | IMPRESSION)
#                                           with 181 selectable phrase texts
#
# Repointing /templates at the migrated table would have silently broken the
# radiology workspace, which depends on the variant_name shape. Both are
# served, under names that say which is which.

@router.get("/section-templates")
def list_radiology_section_templates(
    exam_type_ref: Optional[str] = Query(None, description="Hope radiology_id of the exam type"),
    section: Optional[str] = Query(None, description="e.g. FINDINGS / OPINIONS / IMPRESSION"),
    user=Depends(verify_jwt),
):
    """Royan's own per-exam-type report section templates."""
    try:
        query = (
            db.table(TABLE_RADIOLOGY_REPORT_TEMPLATES)
            .select("id,exam_type_ref,section,location_ref")
            .eq("is_active", True)
        )
        if exam_type_ref:
            query = query.eq("exam_type_ref", str(exam_type_ref).strip())
        if section:
            query = query.ilike("section", f"%{section.strip()}%")
        rows = query.order("section").execute().data or []
        return {"templates": rows, "count": len(rows)}
    except Exception as exc:
        logger.error("Radiology section template list failed: %s", exc)
        return {"templates": [], "count": 0}


@router.get("/section-templates/{template_id}/texts")
def list_radiology_section_template_texts(template_id: int, user=Depends(verify_jwt)):
    """Selectable phrase snippets for one report section."""
    try:
        rows = (
            db.table(TABLE_RADIOLOGY_REPORT_TEMPLATE_TEXTS)
            .select("id,template_id,text,sort_order")
            .eq("template_id", template_id)
            .order("sort_order")
            .execute()
            .data
            or []
        )
        return {"texts": rows, "count": len(rows)}
    except Exception as exc:
        logger.error("Radiology section template text lookup failed: %s", exc)
        return {"texts": [], "count": 0}


@router.get("/stats")
def radiology_stats(user=Depends(verify_jwt)):
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


# ── ScanCare billing ─────────────────────────────────────────────────────────
#
# "as a standalone company, they should be able to bill clients based on the
# services they provide."
#
# Radiology is both a hospital department and ScanCare, a separate company. A
# walk-in who is not a hospital patient still needs a receipt, so this prices a
# study from the radiology catalogue (209 of 211 priced) and applies the
# patient's HMO rate when they have one (7,143 negotiated radiology rates).
#
# Deliberately NOT a second billing system: the charge is written to the same
# royan_billing the rest of the hospital uses, so the money reconciles in one
# place. What is different is the presentation — a ScanCare receipt rather than
# a hospital invoice.

class RadiologyChargeCreate(BaseModel):
    patient_id: int
    order_id: Optional[int] = None
    radiology_catalog_id: Optional[int] = None
    description: Optional[str] = None
    amount: Optional[float] = None
    payment_method: Optional[str] = None
    notes: Optional[str] = None

    model_config = {"extra": "ignore"}


@router.get("/orders/{order_id}/charge-preview")
def radiology_charge_preview(order_id: int, user=Depends(verify_jwt)):
    """What this study costs for this patient, before anything is charged.

    Returns the list price and the patient's negotiated rate separately rather
    than only the final figure: a receptionist quoting a walk-in needs to see
    which one is being applied, and why it differs from the wall price.
    """
    order = _get_order(order_id)

    study, list_price = {}, 0.0
    cid = order.get("radiology_catalog_id")
    if cid:
        try:
            found = db.table("royan_radiology_catalog").select(
                "id,name,modality,base_price").eq("id", cid).limit(1).execute().data
            study = found[0] if found else {}
            list_price = float(study.get("base_price") or 0)
        except Exception as exc:
            logger.warning("Radiology catalogue lookup failed for %s: %s", cid, exc)

    if not list_price and order.get("test_name"):
        # Fall back to a name match: migrated orders carry a test_name and no
        # catalogue id.
        try:
            found = db.table("royan_radiology_catalog").select(
                "id,name,modality,base_price").ilike("name", order["test_name"]).limit(1).execute().data
            if found:
                study = found[0]
                list_price = float(study.get("base_price") or 0)
        except Exception:
            pass

    payer_price, payer_name = None, None
    try:
        ins = (
            db.table(TABLE_PATIENT_INSURANCE)
            .select("hmo_id").eq("patient_id", order["patient_id"])
            .eq("is_primary", True).eq("status", "active").limit(1).execute().data
        )
        if ins and study.get("id"):
            hmo_id = ins[0]["hmo_id"]
            rate = (
                db.table(TABLE_PAYER_SERVICE_PRICES).select("price")
                .eq("hmo_id", hmo_id).eq("radiology_catalog_id", study["id"])
                .limit(1).execute().data
            )
            if rate:
                payer_price = float(rate[0]["price"])
            h = db.table(TABLE_HMOS).select("name").eq("id", hmo_id).limit(1).execute().data
            payer_name = h[0]["name"] if h else None
    except Exception as exc:
        logger.warning("Radiology payer price lookup failed: %s", exc)

    return {
        "order_id": order_id,
        "patient_id": order.get("patient_id"),
        "study": study or {"name": order.get("test_name")},
        "list_price": list_price,
        "payer_name": payer_name,
        "payer_price": payer_price,
        "amount_due": payer_price if payer_price is not None else list_price,
        "is_walk_in": not order.get("encounter_id"),
        # Stated so nobody quotes a zero as if it were free.
        "unpriced": list_price <= 0 and payer_price is None,
    }



# ── Scancare: its own dashboard and billing ───────────────────────────────────
#
# Scancare is a separate business with its own books (finance meeting, 10 Oct 2026). Every study it performs is
# billed on a Scancare bill - one visit can carry a Royan invoice and a Scancare invoice - and its revenue, cash and
# receivables land in Scancare's books. This is the department's own view of its work and its money.

@router.get("/scancare/overview")
def scancare_overview(date_from: Optional[str] = None, date_to: Optional[str] = None, include_history: bool = False,
                      user=Depends(verify_jwt)):
    import datetime as _dt
    from src.fin.db import q as _q, q1 as _q1, tx as _tx
    d_to = _dt.date.fromisoformat(date_to) if date_to else _dt.date.today()
    d_from = _dt.date.fromisoformat(date_from) if date_from else d_to.replace(day=1)
    rng = (d_from, d_to)
    with _tx() as conn:
        work = _q1(conn, """SELECT COUNT(*) AS studies,
                                   COUNT(*) FILTER (WHERE encounter_id IS NULL) AS walk_ins,
                                   COUNT(*) FILTER (WHERE encounter_id IS NOT NULL) AS referrals,
                                   COUNT(*) FILTER (WHERE status='reported') AS reported,
                                   COUNT(*) FILTER (WHERE status='cancelled') AS cancelled,
                                   ROUND(AVG(tat_minutes) FILTER (WHERE status='reported' AND tat_minutes IS NOT NULL)::numeric, 1) AS avg_tat
                            FROM royan_radiology_orders
                            WHERE (%s OR external_source IS NULL) AND COALESCE(ordered_at, created_at, order_date::timestamptz)::date BETWEEN %s AND %s""", (include_history, *rng))
        queue = _q1(conn, """SELECT COUNT(*) FILTER (WHERE status IN ('ordered','scheduled')) AS waiting,
                                    COUNT(*) FILTER (WHERE status='in_progress') AS in_progress,
                                    COUNT(*) FILTER (WHERE urgency='stat' AND status NOT IN ('reported','cancelled')) AS stat_open,
                                    COUNT(*) FILTER (WHERE status IN ('ordered','scheduled','in_progress')
                                                     AND COALESCE(ordered_at, created_at) < now() - interval '24 hours') AS over_24h
                             FROM royan_radiology_orders WHERE external_source IS NULL""")
        modalities = _q(conn, """SELECT COALESCE(NULLIF(modality,'other'), CASE
                                            WHEN test_name ILIKE '%%x%%ray%%' OR test_name ILIKE 'xr%%' THEN 'xray'
                                            WHEN test_name ILIKE '%%ultras%%' OR test_name ILIKE '%%uss%%' OR test_name ILIKE '%%doppler%%' OR test_name ILIKE '%%scan%%' THEN 'ultrasound'
                                            WHEN test_name ILIKE '%%mri%%' THEN 'mri'
                                            WHEN test_name ILIKE '%%ct %%' OR test_name ILIKE 'ct%%' THEN 'ct'
                                            WHEN test_name ILIKE '%%mammo%%' THEN 'mammography'
                                            WHEN test_name ILIKE '%%ecg%%' THEN 'ecg'
                                            WHEN test_name ILIKE '%%echo%%' THEN 'echo'
                                            ELSE 'other' END) AS modality, COUNT(*) AS studies,
                                        ROUND(AVG(tat_minutes) FILTER (WHERE status='reported')::numeric, 1) AS avg_tat
                                 FROM royan_radiology_orders
                                 WHERE (%s OR external_source IS NULL) AND COALESCE(ordered_at, created_at, order_date::timestamptz)::date BETWEEN %s AND %s
                                 GROUP BY 1 ORDER BY 2 DESC""", (include_history, *rng))
        money = _q1(conn, """SELECT COUNT(*) AS bills, COALESCE(SUM(subtotal),0) AS billed, COALESCE(SUM(hmo_covered),0) AS hmo,
                                    COALESCE(SUM(patient_balance),0) AS patient_due,
                                    COUNT(*) FILTER (WHERE status IN ('pending','partial','disputed')) AS awaiting_payment
                             FROM royan_billing WHERE entity='SCANCARE' AND status <> 'void' AND billed_at::date BETWEEN %s AND %s""", rng)
        paid = _q1(conn, """SELECT COALESCE(SUM(p.amount),0) AS collected FROM royan_payments p JOIN royan_billing b ON b.id=p.billing_id
                            WHERE b.entity='SCANCARE' AND COALESCE(p.status,'posted') <> 'void'
                              AND p.payment_method NOT IN ('waiver','hmo') AND p.received_at::date BETWEEN %s AND %s""", rng)
        owing = _q1(conn, """SELECT COALESCE(SUM(b.patient_balance - COALESCE(x.paid,0)),0) AS outstanding, COUNT(*) AS bills
                             FROM royan_billing b LEFT JOIN LATERAL (SELECT SUM(amount) paid FROM royan_payments
                                 WHERE billing_id=b.id AND COALESCE(status,'posted') <> 'void') x ON true
                             WHERE b.entity='SCANCARE' AND b.status IN ('pending','partial','disputed')""")
        top = _q(conn, """SELECT i.description, COUNT(*) AS studies, SUM(i.gross_amount) AS revenue
                          FROM royan_bill_items i JOIN royan_billing b ON b.id=i.billing_id
                          WHERE b.entity='SCANCARE' AND b.status <> 'void' AND b.billed_at::date BETWEEN %s AND %s
                          GROUP BY 1 ORDER BY 3 DESC NULLS LAST LIMIT 10""", rng)
        payers = _q(conn, """SELECT COALESCE(i.payer_type,'private') AS payer, SUM(i.gross_amount) AS revenue, COUNT(DISTINCT b.id) AS bills
                             FROM royan_bill_items i JOIN royan_billing b ON b.id=i.billing_id
                             WHERE b.entity='SCANCARE' AND b.status <> 'void' AND b.billed_at::date BETWEEN %s AND %s
                             GROUP BY 1 ORDER BY 2 DESC""", rng)
        unbilled = _q(conn, """SELECT o.id, o.test_name, o.modality, o.patient_id, o.status, o.encounter_id,
                                      p.first_name || ' ' || p.last_name AS patient_name, p.mrn
                               FROM royan_radiology_orders o LEFT JOIN royan_patients p ON p.id=o.patient_id
                               WHERE o.external_source IS NULL AND o.status <> 'cancelled'
                                 AND COALESCE(o.ordered_at, o.created_at) >= now() - interval '30 days'
                                 AND NOT EXISTS (SELECT 1 FROM royan_bill_items i WHERE i.source='radiology_order' AND i.source_id=o.id::text)
                               ORDER BY COALESCE(o.ordered_at, o.created_at) DESC LIMIT 50""")
        books = _q1(conn, "SELECT id, code, name FROM fin_legal_entities WHERE code='SCN' AND status='ACTIVE'")
        ledger = None
        if books:
            ledger = _q1(conn, """SELECT COALESCE(SUM(credit-debit) FILTER (WHERE account_type='REVENUE'),0) AS revenue,
                                         COALESCE(SUM(debit-credit) FILTER (WHERE account_type IN ('EXPENSE','COGS')),0) AS expenses
                                  FROM fin_v_ledger WHERE legal_entity_id=%s AND journal_date BETWEEN %s AND %s""",
                          (books["id"], d_from, d_to))
    return {"date_from": d_from, "date_to": d_to, "work": work, "queue": queue, "modalities": modalities,
            "money": {**money, **paid, "outstanding": owing["outstanding"], "outstanding_bills": owing["bills"]},
            "top_studies": top, "payers": payers, "unbilled": unbilled,
            "books": {"live": bool(books), **(ledger or {})}}


@router.post("/orders/{order_id}/bill")
def bill_study(order_id: int, user=Depends(verify_jwt)):
    """Raise the Scancare bill for one study - a walk-in client, or a referral not billed yet. Priced from the
    radiology tariff (the patient's HMO rate applies through their cover)."""
    from src.fin.db import q1 as _q1, tx as _tx
    from src.routers.billing_hospital import create_coverage_bill
    order = _get_order(order_id)
    cid = str(order.get("radiology_catalog_id") or "")
    with _tx() as conn:
        if _q1(conn, "SELECT 1 FROM royan_bill_items WHERE source='radiology_order' AND source_id=%s", (str(order_id),)):
            raise HTTPException(status_code=409, detail="This study is already on a bill")
        price = _q1(conn, """SELECT id, name, base_price FROM royan_radiology_catalog
                             WHERE id::text=%s OR upper(name)=upper(%s) ORDER BY (id::text=%s) DESC LIMIT 1""",
                    (cid, order.get("test_name") or "", cid))
    if not price or not float(price.get("base_price") or 0):
        raise HTTPException(status_code=422, detail="This study has no price in the radiology tariff - set its price first")
    item = {"description": order.get("test_name") or price["name"], "category": "imaging", "quantity": 1,
            "unit_price": float(price["base_price"]), "source": "radiology_order", "source_id": str(order_id)}
    return create_coverage_bill(order.get("encounter_id"), int(order["patient_id"]), [item], user, entity="SCANCARE",
                                stage="services", notes="Scancare study" + ("" if order.get("encounter_id") else " (walk-in)"))


class ScancareWalkIn(BaseModel):
    patient_id: int
    studies: list[int] = Field(..., min_length=1)        # radiology catalogue ids
    urgency: str = "routine"
    clinical_indication: Optional[str] = None
    referred_by: Optional[str] = None


@router.post("/scancare/walk-in", status_code=201)
def scancare_walk_in(payload: ScancareWalkIn, user=Depends(verify_jwt)):
    """Scancare's own front desk: a client walks in (or is referred from outside), the studies are booked and one
    Scancare invoice is raised for them - in Scancare's books, numbered in Scancare's own series."""
    from src.fin.db import q as _q, tx as _tx
    from src.routers.billing_hospital import create_coverage_bill
    with _tx() as conn:
        cat = {r["id"]: r for r in _q(conn, "SELECT id, name, modality, base_price FROM royan_radiology_catalog WHERE id = ANY(%s)",
                                      (payload.studies,))}
    missing = [s for s in payload.studies if s not in cat]
    if missing:
        raise HTTPException(status_code=404, detail=f"Studies not in the radiology tariff: {missing}")
    unpriced = [cat[s]["name"] for s in payload.studies if not float(cat[s]["base_price"] or 0)]
    if unpriced:
        raise HTTPException(status_code=422, detail=f"No price in the radiology tariff for: {', '.join(unpriced)}")
    orders, items = [], []
    for sid in payload.studies:
        c = cat[sid]
        o = create_order(RadiologyOrderCreate(patient_id=payload.patient_id, modality=(c["modality"] or "other").lower(),
                                              radiology_catalog_id=sid, test_name=c["name"], urgency=payload.urgency,
                                              clinical_indication=payload.clinical_indication,
                                              ordered_by=payload.referred_by or "Walk-in (Scancare)"), user)
        oid = (o.get("order") or o)["id"]
        orders.append(oid)
        items.append({"description": c["name"], "category": "imaging", "quantity": 1, "unit_price": float(c["base_price"]),
                      "source": "radiology_order", "source_id": str(oid)})
    bill = create_coverage_bill(None, payload.patient_id, items, user, entity="SCANCARE", stage="services",
                                notes="Scancare walk-in" + (f" - referred by {payload.referred_by}" if payload.referred_by else ""))
    return {"ok": True, "orders": orders, **bill}
