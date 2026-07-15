"""
Laboratory Router — RoyanHealth / Royan Hospital
===================================================
Manages lab test orders, sample collection, results entry, and turnaround metrics.

Endpoints:
  POST /lab/orders                       – Place a lab order
  GET  /lab/orders                       – List orders (filter by status/patient)
  GET  /lab/orders/{order_id}            – Get order detail
  POST /lab/orders/{order_id}/collect    – Mark sample collected
  POST /lab/orders/{order_id}/result     – Record lab result
  GET  /lab/turnaround                   – Turnaround time summary
  GET  /lab/critical                     – List unacknowledged critical results
"""
from __future__ import annotations

import logging
from typing import Optional

import os
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from src.db import db, audit_event
from src.middleware import verify_jwt, require_role
from src.services.event_service import emit_clinical_event
from src.constants import (
    LAB_INTERPRETATION_ALLOWED,
    LAB_ORDER_STATUS_ALLOWED,
    LAB_URGENCY_ALLOWED,
    TABLE_LAB_ORDERS,
    TABLE_LAB_RESULTS,
    TABLE_LAB_REFERENCE_RANGES,
    TABLE_PATIENTS,
    TABLE_ENCOUNTERS,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/lab", tags=["Laboratory"])

ORDER_STATUSES   = LAB_ORDER_STATUS_ALLOWED
URGENCY_LEVELS   = LAB_URGENCY_ALLOWED
INTERPRETATIONS  = LAB_INTERPRETATION_ALLOWED


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class LabOrderCreate(BaseModel):
    encounter_id: int
    patient_id: int
    test_name: str = Field(..., min_length=1, max_length=200)
    test_code: Optional[str] = None
    loinc_code: Optional[str] = None
    urgency: str = "routine"
    sample_type: Optional[str] = None
    notes: Optional[str] = None
    ordered_by: Optional[str] = None
    external_lab: Optional[str] = None


class SampleCollectedRequest(BaseModel):
    notes: Optional[str] = None


class LabResultCreate(BaseModel):
    result_data: Optional[dict] = None         # flexible: {"haemoglobin": "12.4 g/dL"}
    result_value: Optional[str] = None
    result_unit: Optional[str] = None
    result_summary: Optional[str] = None
    reference_range: Optional[str] = None
    interpretation: Optional[str] = None
    is_critical: bool = False
    resulted_by: Optional[str] = None
    notes: Optional[str] = None

    model_config = {"extra": "ignore"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_order(order_id: int) -> dict:
    result = db.table(TABLE_LAB_ORDERS).select("*").eq("id", order_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail=f"Lab order {order_id} not found")
    return result.data[0]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/orders", status_code=201)
async def place_lab_order(payload: LabOrderCreate, user=Depends(verify_jwt)):
    """Place a new lab order for a patient encounter."""
    if payload.urgency not in URGENCY_LEVELS:
        raise HTTPException(status_code=422, detail=f"urgency must be one of {URGENCY_LEVELS}")

    data = payload.model_dump(exclude_none=True)
    data["ordered_by"] = payload.ordered_by or user.get("sub") or "system"
    data["status"] = "ordered"

    try:
        result = db.table(TABLE_LAB_ORDERS).insert(data).execute()
    except Exception as exc:
        logger.error("Lab order creation failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to place lab order")

    order = result.data[0] if result.data else data
    audit_event(
        "lab_order_placed",
        {"test": payload.test_name, "urgency": payload.urgency},
        actor_id=user.get("sub"),
        subject_type="lab_order",
        subject_id=str(order.get("id") or ""),
    )
    return {"ok": True, "order": order}


@router.get("/stats")
async def lab_stats(user=Depends(verify_jwt)):
    """Return aggregate counts per status for the KPI dashboard cards."""
    result = db.table(TABLE_LAB_ORDERS).select("status, urgency, ordered_at").is_("external_source", None).execute()
    rows = result.data or []

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)

    pending          = sum(1 for r in rows if r.get("status") in ("ordered", "pending"))
    sample_collecting= sum(1 for r in rows if r.get("status") == "sample_collected")
    processing       = sum(1 for r in rows if r.get("status") == "processing")

    def _secs(r: dict) -> float:
        try:
            return (now - datetime.fromisoformat(r["ordered_at"].replace("Z", "+00:00"))).total_seconds()
        except Exception:
            return 0.0

    stat_overdue = sum(
        1 for r in rows
        if r.get("urgency") == "stat" and r.get("status") in ("ordered", "pending")
        and r.get("ordered_at") and _secs(r) > 1800
    )
    urgent_overdue = sum(
        1 for r in rows
        if r.get("urgency") == "urgent" and r.get("status") in ("ordered", "pending")
        and r.get("ordered_at") and _secs(r) > 7200
    )

    return {
        "pending": pending,
        "sample_collecting": sample_collecting,
        "processing": processing,
        "stat_overdue": stat_overdue,
        "urgent_overdue": urgent_overdue,
        "total": len(rows),
    }


@router.get("/orders")
async def list_lab_orders(
    status: Optional[str] = Query(None),
    patient_id: Optional[int] = Query(None),
    encounter_id: Optional[int] = Query(None),
    urgency: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    user=Depends(verify_jwt),
):
    query = db.table(TABLE_LAB_ORDERS).select("*").is_("external_source", None).order("ordered_at", desc=True).limit(limit)
    if status:
        query = query.eq("status", status)
    if patient_id:
        query = query.eq("patient_id", patient_id)
    if encounter_id:
        query = query.eq("encounter_id", encounter_id)
    if urgency:
        query = query.eq("urgency", urgency)
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
                        order["patient_name"]        = f"{fn} {ln}".strip() or None
                        order["patient_mrn"]         = p.get("mrn")
                        order["patient_gender"]      = p.get("gender")
                        order["patient_dob"]         = p.get("date_of_birth")
                        order["patient_blood_group"] = p.get("blood_group")
                        order["patient_hmo"]         = p.get("hmo_provider")
                        order["patient_phone"]       = p.get("phone")
        except Exception as exc:
            logger.warning("lab order patient enrichment failed: %s", exc)

    return {"orders": orders, "count": len(orders)}


@router.get("/orders/{order_id}")
async def get_lab_order(order_id: int, user=Depends(verify_jwt)):
    order = _get_order(order_id)
    # Attach result if available
    result_rec = db.table(TABLE_LAB_RESULTS).select("*").eq("lab_order_id", order_id).execute()
    return {"order": order, "result": result_rec.data[0] if result_rec.data else None}


@router.post("/orders/{order_id}/collect")
async def collect_sample(order_id: int, payload: SampleCollectedRequest, user=Depends(verify_jwt)):
    """Mark a sample as collected."""
    order = _get_order(order_id)
    if order["status"] != "ordered":
        raise HTTPException(status_code=409, detail=f"Order is '{order['status']}'; sample collection requires 'ordered' status")

    from datetime import datetime, timezone
    db.table(TABLE_LAB_ORDERS).update({
        "status": "sample_collected",
        "sample_collected_at": datetime.now(timezone.utc).isoformat(),
        "notes": payload.notes or order.get("notes"),
    }).eq("id", order_id).execute()

    audit_event("lab_sample_collected", {}, actor_id=user.get("sub"), subject_type="lab_order", subject_id=str(order_id))
    emit_clinical_event(
        event_type="LAB_SAMPLE_COLLECTED",
        encounter_id=order.get("encounter_id"),
        patient_id=order.get("patient_id"),
        entity_type="lab_order", entity_id=order_id,
        performed_by=user.get("sub"),
        event_data={"test_name": order.get("test_name")},
    )
    return {"ok": True, "order_id": order_id, "status": "sample_collected"}


@router.post("/orders/{order_id}/result", status_code=201)
async def record_result(order_id: int, payload: LabResultCreate, user=Depends(verify_jwt)):
    """Record the lab result for an order."""
    order = _get_order(order_id)
    if order["status"] in ("resulted", "cancelled"):
        raise HTTPException(status_code=409, detail=f"Order already '{order['status']}'")

    if payload.interpretation and payload.interpretation not in INTERPRETATIONS:
        raise HTTPException(status_code=422, detail=f"interpretation must be one of {INTERPRETATIONS}")

    data = payload.model_dump(exclude_none=True)
    if payload.result_value or payload.result_unit:
        data["result_data"] = {
            **(payload.result_data or {}),
            "value": payload.result_value,
            "unit": payload.result_unit,
        }
        data["result_summary"] = payload.result_summary or " ".join(
            part for part in [payload.result_value, payload.result_unit] if part
        )
        data.pop("result_value", None)
        data.pop("result_unit", None)
    data["lab_order_id"] = order_id
    data["patient_id"] = order["patient_id"]
    data["resulted_by"] = payload.resulted_by or user.get("sub") or "system"

    try:
        result = db.table(TABLE_LAB_RESULTS).insert(data).execute()
    except Exception as exc:
        logger.error("Lab result insert failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to save result")

    # Update order status
    db.table(TABLE_LAB_ORDERS).update({"status": "resulted"}).eq("id", order_id).execute()

    res_row = result.data[0] if result.data else data
    if payload.is_critical:
        logger.warning("CRITICAL lab result for order %s patient %s", order_id, order["patient_id"])
        audit_event("lab_critical_result", {"test": order.get("test_name")}, actor_id=user.get("sub"), subject_type="lab_order", subject_id=str(order_id))
        emit_clinical_event(
            event_type="LAB_RESULT_CRITICAL",
            encounter_id=order.get("encounter_id"),
            patient_id=order.get("patient_id"),
            entity_type="lab_order", entity_id=order_id,
            performed_by=user.get("sub"),
            event_data={"test_name": order.get("test_name"), "is_critical": True},
        )

    audit_event("lab_result_recorded", {"interpretation": payload.interpretation}, actor_id=user.get("sub"), subject_type="lab_order", subject_id=str(order_id))
    emit_clinical_event(
        event_type="LAB_RESULT_READY",
        encounter_id=order.get("encounter_id"),
        patient_id=order.get("patient_id"),
        entity_type="lab_order", entity_id=order_id,
        performed_by=user.get("sub"),
        event_data={
            "test_name": order.get("test_name"),
            "interpretation": payload.interpretation,
            "is_critical": payload.is_critical,
        },
    )
    return {"ok": True, "result": res_row}


@router.get("/turnaround")
async def lab_turnaround(
    limit: int = Query(50, ge=1, le=500),
    user=Depends(verify_jwt),
):
    """Return TAT data from the royan_lab_turnaround view."""
    try:
        import psycopg2.extras
        conn = db.pool.getconn()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            "SELECT * FROM public.royan_lab_turnaround ORDER BY ordered_at DESC LIMIT %s",
            (limit,)
        )
        rows = [dict(r) for r in cur.fetchall()]
        cur.close()
        db.pool.putconn(conn)
        return {"records": rows, "count": len(rows)}
    except Exception as exc:
        logger.error("Turnaround query failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to fetch turnaround data")


@router.get("/critical")
async def critical_results(user=Depends(verify_jwt)):
    """List all critical lab results that have not been verified."""
    result = db.table(TABLE_LAB_RESULTS).select("*") \
        .eq("is_critical", True) \
        .is_("verified_at", None) \
        .order("resulted_at", desc=True) \
        .execute()
    return {"critical_results": result.data, "count": len(result.data)}


# ─── Lab Reference Ranges ─────────────────────────────────────────────────────

class ReferenceRangeCreate(BaseModel):
    test_name: str = Field(..., min_length=1)
    loinc_code: Optional[str] = None
    gender: Optional[str] = None       # male | female | all
    age_min: Optional[float] = None
    age_max: Optional[float] = None
    unit: Optional[str] = None
    normal_low: Optional[float] = None
    normal_high: Optional[float] = None
    critical_low: Optional[float] = None
    critical_high: Optional[float] = None
    notes: Optional[str] = None

    model_config = {"extra": "ignore"}


@router.get("/reference-ranges")
async def list_reference_ranges(
    test_name: Optional[str] = Query(None),
    user=Depends(verify_jwt),
):
    """List lab reference ranges, optionally filtered by test name."""
    query = db.table(TABLE_LAB_REFERENCE_RANGES).select("*").order("test_name")
    if test_name:
        query = query.ilike("test_name", f"%{test_name.strip()}%")
    result = query.execute()
    return {"ranges": result.data or [], "count": len(result.data or [])}


@router.post("/reference-ranges", status_code=201)
async def create_reference_range(payload: ReferenceRangeCreate, user=Depends(verify_jwt)):
    """Create a lab reference range entry."""
    data = payload.model_dump(exclude_none=True)
    try:
        result = db.table(TABLE_LAB_REFERENCE_RANGES).insert(data).execute()
    except Exception as exc:
        logger.error("Reference range insert failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to save reference range")
    rr = (result.data or [data])[0]
    audit_event("lab_ref_range_created", {"test_name": payload.test_name}, actor_id=user.get("sub"), subject_type="lab_reference_range", subject_id=str(rr.get("id") or ""))
    return {"ok": True, "range": rr}


@router.patch("/reference-ranges/{range_id}")
async def update_reference_range(range_id: int, payload: ReferenceRangeCreate, user=Depends(verify_jwt)):
    r = db.table(TABLE_LAB_REFERENCE_RANGES).select("id").eq("id", range_id).execute()
    if not r.data:
        raise HTTPException(status_code=404, detail=f"Reference range {range_id} not found")
    updates = payload.model_dump(exclude_none=True)
    db.table(TABLE_LAB_REFERENCE_RANGES).update(updates).eq("id", range_id).execute()
    return {"ok": True, "range_id": range_id}


@router.delete("/reference-ranges/{range_id}")
async def delete_reference_range(range_id: int, user=Depends(verify_jwt)):
    r = db.table(TABLE_LAB_REFERENCE_RANGES).select("id").eq("id", range_id).execute()
    if not r.data:
        raise HTTPException(status_code=404, detail=f"Reference range {range_id} not found")
    db.table(TABLE_LAB_REFERENCE_RANGES).update({"active": False}).eq("id", range_id).execute()
    return {"ok": True, "range_id": range_id}


# ─── Cumulative Patient History ───────────────────────────────────────────────

@router.get("/patients/{patient_id}/history")
async def patient_lab_history(
    patient_id: int,
    test_name: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    user=Depends(verify_jwt),
):
    """Return all lab results for a patient, optionally filtered by test name."""
    query = (
        db.table(TABLE_LAB_ORDERS)
        .select("id,test_name,test_code,urgency,status,ordered_at")
        .eq("patient_id", patient_id)
        .eq("status", "resulted")
        .order("ordered_at", desc=True)
        .limit(limit)
    )
    if test_name:
        query = query.ilike("test_name", f"%{test_name.strip()}%")
    orders = query.execute().data or []
    if not orders:
        return {"history": [], "count": 0, "patient_id": patient_id}
    order_ids = [o["id"] for o in orders]
    results = (
        db.table(TABLE_LAB_RESULTS)
        .select("lab_order_id,result_data,result_summary,is_critical,interpretation,reference_range,resulted_at")
        .in_("lab_order_id", order_ids)
        .execute()
        .data or []
    )
    result_map = {r["lab_order_id"]: r for r in results}
    history = [{**o, **result_map.get(o["id"], {})} for o in orders]
    return {"history": history, "count": len(history), "patient_id": patient_id}


# ─── Send-out Tracking ────────────────────────────────────────────────────────

class SendOutRequest(BaseModel):
    external_lab: str = Field(..., min_length=1)
    notes: Optional[str] = None


@router.post("/orders/{order_id}/send-out")
async def mark_sent_out(order_id: int, payload: SendOutRequest, user=Depends(verify_jwt)):
    """Mark a lab order as sent to an external laboratory."""
    order = _get_order(order_id)
    if order["status"] in ("resulted", "cancelled"):
        raise HTTPException(status_code=409, detail=f"Cannot send out order with status '{order['status']}'")
    from datetime import datetime, timezone
    db.table(TABLE_LAB_ORDERS).update({
        "status": "sent_out",
        "external_lab": payload.external_lab,
        "sent_out_at": datetime.now(timezone.utc).isoformat(),
        "notes": payload.notes or order.get("notes"),
    }).eq("id", order_id).execute()
    audit_event("lab_sent_out", {"external_lab": payload.external_lab}, actor_id=user.get("sub"), subject_type="lab_order", subject_id=str(order_id))
    return {"ok": True, "order_id": order_id, "status": "sent_out", "external_lab": payload.external_lab}


# ─── Lab Report Upload ────────────────────────────────────────────────────────

LAB_REPORTS_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "lab_reports"
)
ALLOWED_CONTENT_TYPES = {"application/pdf", "image/jpeg", "image/png", "image/webp"}


@router.post("/orders/{order_id}/report-upload")
async def upload_lab_report(
    order_id: int,
    file: UploadFile = File(...),
    user=Depends(verify_jwt),
):
    """Upload a lab report file (PDF or image) for a resulted lab order.
    Stores the file locally and saves the URL in the lab result record.
    """
    order = _get_order(order_id)

    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"File type '{file.content_type}' not allowed. Use PDF or image.",
        )

    contents = await file.read()
    if len(contents) > 20 * 1024 * 1024:  # 20 MB limit
        raise HTTPException(status_code=413, detail="File too large (max 20 MB)")

    os.makedirs(LAB_REPORTS_DIR, exist_ok=True)
    safe_name = f"{order_id}_{uuid.uuid4().hex[:8]}_{file.filename or 'report'}"
    # Strip path separators from filename for safety
    safe_name = safe_name.replace("/", "_").replace("\\", "_")
    storage_path = os.path.join(LAB_REPORTS_DIR, safe_name)

    with open(storage_path, "wb") as fh:
        fh.write(contents)

    report_url = f"/lab/reports/{safe_name}"

    # Update the lab_results row for this order if it exists; else update the order notes
    existing_result = db.table(TABLE_LAB_RESULTS).select("id").eq("lab_order_id", order_id).execute()
    if existing_result.data:
        db.table(TABLE_LAB_RESULTS).update({"report_file_url": report_url}).eq("lab_order_id", order_id).execute()
    else:
        # Store on the order itself until a result is recorded
        db.table(TABLE_LAB_ORDERS).update({"notes": f"report:{report_url};{order.get('notes') or ''}"}).eq("id", order_id).execute()

    audit_event(
        "lab_report_uploaded",
        {"order_id": order_id, "filename": safe_name},
        actor_id=user.get("sub"),
        subject_type="lab_order",
        subject_id=str(order_id),
    )
    return {"ok": True, "report_file_url": report_url, "filename": safe_name}


@router.get("/reports/{filename}")
async def serve_lab_report(filename: str, user=Depends(verify_jwt)):
    """Serve a stored lab report file to authenticated users."""
    # Prevent path traversal
    safe_filename = os.path.basename(filename)
    file_path = os.path.join(LAB_REPORTS_DIR, safe_filename)
    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="Report file not found")
    return FileResponse(file_path)
