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

import asyncio
import logging
from datetime import datetime, timezone
from typing import List, Optional

import os
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from src.db import db, audit_event
from src.middleware import verify_jwt, require_role
from src.services.event_service import emit_clinical_event
from src.services.realtime import realtime_hub
from src.constants import (
    LAB_INTERPRETATION_ALLOWED,
    LAB_ORDER_STATUS_ALLOWED,
    LAB_URGENCY_ALLOWED,
    TABLE_LAB_CATALOG,
    TABLE_LAB_ORDERS,
    TABLE_LAB_RESULTS,
    TABLE_LAB_REFERENCE_RANGES,
    TABLE_LAB_SPECIMENS,
    TABLE_LAB_TEST_TEMPLATES,
    TABLE_PATIENTS,
    TABLE_ENCOUNTERS,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/lab", tags=["Laboratory"])

ORDER_STATUSES   = LAB_ORDER_STATUS_ALLOWED
URGENCY_LEVELS   = LAB_URGENCY_ALLOWED
INTERPRETATIONS  = LAB_INTERPRETATION_ALLOWED
SPECIMEN_TYPES   = {"blood", "urine", "stool", "sputum", "csf", "swab", "tissue", "serum", "plasma", "other"}


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
    specimen_type: Optional[str] = None
    container: Optional[str] = None
    volume: Optional[str] = None
    specimen_label: Optional[str] = None
    collected_by: Optional[str] = None


class ReceiveRequest(BaseModel):
    notes: Optional[str] = None
    specimen_id: Optional[int] = None


class RejectRequest(BaseModel):
    rejection_reason: str = Field(..., min_length=1)
    specimen_id: Optional[int] = None


class VerifyRequest(BaseModel):
    notes: Optional[str] = None


class AnalyteValue(BaseModel):
    """One filled-in row of a structured result pop-up (see AnalyteDef for the
    template shape this is validated against)."""
    name: str = Field(..., min_length=1)
    observed_value: Optional[str] = None
    unit: Optional[str] = None
    is_abnormal: Optional[bool] = None     # auto-computed from the template's range if omitted
    comment: Optional[str] = None

    model_config = {"extra": "ignore"}


class LabResultCreate(BaseModel):
    result_data: Optional[dict] = None         # flexible: {"haemoglobin": "12.4 g/dL"}
    result_value: Optional[str] = None
    result_unit: Optional[str] = None
    analyte_values: Optional[List[AnalyteValue]] = None   # structured, per-test-template entry
    result_summary: Optional[str] = None
    reference_range: Optional[str] = None
    interpretation: Optional[str] = None
    is_critical: bool = False
    resulted_by: Optional[str] = None
    notes: Optional[str] = None

    model_config = {"extra": "ignore"}


class ResultAmendRequest(LabResultCreate):
    """Corrects a verified result. Authenticated results are immutable, so
    this always produces a new row referencing the one it supersedes."""
    amendment_reason: str = Field(..., min_length=1)


class AnalyteDef(BaseModel):
    """One named field in a lab test template, e.g. "Total Bilirubin"."""
    name: str = Field(..., min_length=1)
    unit: Optional[str] = None
    normal_low: Optional[float] = None
    normal_high: Optional[float] = None
    critical_low: Optional[float] = None
    critical_high: Optional[float] = None

    model_config = {"extra": "ignore"}


class LabTemplateCreate(BaseModel):
    test_name: str = Field(..., min_length=1)
    catalog_id: Optional[int] = None
    analytes: List[AnalyteDef] = Field(..., min_length=1)

    model_config = {"extra": "ignore"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_order(order_id: int) -> dict:
    result = db.table(TABLE_LAB_ORDERS).select("*").eq("id", order_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail=f"Lab order {order_id} not found")
    return result.data[0]


def _get_active_template(test_name: str) -> Optional[dict]:
    result = (
        db.table(TABLE_LAB_TEST_TEMPLATES)
        .select("*")
        .eq("test_name", test_name)
        .eq("is_active", True)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


def _apply_template(template: dict, analyte_values: List["AnalyteValue"]) -> tuple[list, bool, bool]:
    """Validate/enrich submitted analyte values against a template.

    Returns (analytes_out, any_abnormal, any_critical) — analytes_out is what
    gets stored in result_data; the two flags drive the overall
    interpretation/is_critical when the caller didn't set them explicitly.
    """
    defs_by_name = {d["name"].strip().lower(): d for d in (template.get("analytes") or [])}
    analytes_out = []
    any_abnormal = False
    any_critical = False

    for av in analyte_values:
        key = av.name.strip().lower()
        adef = defs_by_name.get(key)
        if adef is None:
            raise HTTPException(
                status_code=422,
                detail=f"'{av.name}' is not a field on the '{template['test_name']}' template (v{template['version']})",
            )
        unit = av.unit or adef.get("unit")
        is_abnormal = av.is_abnormal
        is_critical_flag = False
        numeric_value: Optional[float] = None
        if av.observed_value is not None:
            try:
                numeric_value = float(av.observed_value)
            except ValueError:
                numeric_value = None
        if numeric_value is not None:
            lo, hi = adef.get("normal_low"), adef.get("normal_high")
            if is_abnormal is None and (lo is not None or hi is not None):
                is_abnormal = (lo is not None and numeric_value < lo) or (hi is not None and numeric_value > hi)
            clo, chi = adef.get("critical_low"), adef.get("critical_high")
            if (clo is not None and numeric_value < clo) or (chi is not None and numeric_value > chi):
                is_critical_flag = True

        if is_abnormal:
            any_abnormal = True
        if is_critical_flag:
            any_critical = True

        analytes_out.append({
            "name": adef["name"],
            "observed_value": av.observed_value,
            "unit": unit,
            "normal_low": adef.get("normal_low"),
            "normal_high": adef.get("normal_high"),
            "is_abnormal": bool(is_abnormal),
            "is_critical": is_critical_flag,
            "comment": av.comment,
        })

    return analytes_out, any_abnormal, any_critical


def _get_latest_result(order_id: int) -> Optional[dict]:
    """Most recent result row for an order — an order can have more than one
    once amendments exist, so callers must never fetch unordered."""
    result = (
        db.table(TABLE_LAB_RESULTS)
        .select("*")
        .eq("lab_order_id", order_id)
        .order("id", desc=True)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


def _build_result_row(order: dict, payload: "LabResultCreate", resulted_by: str) -> dict:
    """Build a royan_lab_results row from a result payload — shared by
    record_result (insert/update) and amend_result (always insert)."""
    if payload.interpretation and payload.interpretation not in INTERPRETATIONS:
        raise HTTPException(status_code=422, detail=f"interpretation must be one of {INTERPRETATIONS}")

    data = payload.model_dump(exclude_none=True)
    data.pop("analyte_values", None)

    if payload.analyte_values:
        template = _get_active_template(order["test_name"])
        if template is None:
            raise HTTPException(
                status_code=422,
                detail=f"No active result template for test '{order['test_name']}' — record a template first or use result_value/result_data instead.",
            )
        analytes_out, any_abnormal, any_critical = _apply_template(template, payload.analyte_values)
        data["result_data"] = {**(payload.result_data or {}), "analytes": analytes_out}
        data["template_id"] = template["id"]
        if not payload.result_summary:
            data["result_summary"] = "; ".join(
                f"{a['name']}: {a['observed_value']}{(' ' + a['unit']) if a.get('unit') else ''}"
                for a in analytes_out if a.get("observed_value") is not None
            )
        if not payload.interpretation:
            data["interpretation"] = "critical" if any_critical else ("abnormal" if any_abnormal else "normal")
        if not payload.is_critical:
            data["is_critical"] = any_critical
        data.pop("result_value", None)
        data.pop("result_unit", None)
    elif payload.result_value or payload.result_unit:
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

    data["lab_order_id"] = order["id"]
    data["patient_id"] = order["patient_id"]
    data["resulted_by"] = resulted_by
    return data


def _get_specimen_for_order(order_id: int, specimen_id: Optional[int], statuses: tuple) -> Optional[dict]:
    """Resolve the specimen a receive/reject call applies to: an explicit
    specimen_id if given, else the most recent specimen in one of `statuses`."""
    query = db.table(TABLE_LAB_SPECIMENS).select("*").eq("lab_order_id", order_id)
    if specimen_id:
        query = query.eq("id", specimen_id)
    else:
        query = query.in_("status", list(statuses))
    result = query.order("id", desc=True).limit(1).execute()
    return result.data[0] if result.data else None


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
    ordered_by: Optional[str] = Query(None, description="Filter to orders placed by this user (JWT sub)"),
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
    result = _get_latest_result(order_id)
    specimens = (
        db.table(TABLE_LAB_SPECIMENS)
        .select("*")
        .eq("lab_order_id", order_id)
        .order("id", desc=True)
        .execute()
    )
    return {"order": order, "result": result, "specimens": specimens.data or []}


@router.post("/orders/{order_id}/collect")
async def collect_sample(order_id: int, payload: SampleCollectedRequest, user=Depends(verify_jwt)):
    """Mark a sample as collected and log the specimen."""
    order = _get_order(order_id)
    if order["status"] != "ordered":
        raise HTTPException(status_code=409, detail=f"Order is '{order['status']}'; sample collection requires 'ordered' status")

    now_iso = datetime.now(timezone.utc).isoformat()
    specimen_type = payload.specimen_type or order.get("sample_type") or "blood"
    if specimen_type not in SPECIMEN_TYPES:
        specimen_type = "other"
    collected_by = payload.collected_by or user.get("sub") or "system"

    specimen = None
    try:
        specimen_result = db.table(TABLE_LAB_SPECIMENS).insert({
            "lab_order_id": order_id,
            "patient_id": order["patient_id"],
            "specimen_type": specimen_type,
            "specimen_label": payload.specimen_label,
            "volume": payload.volume,
            "container": payload.container,
            "status": "collected",
            "collected_by": collected_by,
            "collected_at": now_iso,
            "notes": payload.notes,
        }).execute()
        specimen = specimen_result.data[0] if specimen_result.data else None
    except Exception as exc:
        logger.error("Lab specimen insert failed: %s", exc)

    db.table(TABLE_LAB_ORDERS).update({
        "status": "sample_collected",
        "sample_collected_at": now_iso,
        "notes": payload.notes or order.get("notes"),
    }).eq("id", order_id).execute()

    audit_event(
        "lab_sample_collected",
        {"specimen_id": specimen.get("id") if specimen else None},
        actor_id=user.get("sub"), subject_type="lab_order", subject_id=str(order_id),
    )
    emit_clinical_event(
        event_type="LAB_SAMPLE_COLLECTED",
        encounter_id=order.get("encounter_id"),
        patient_id=order.get("patient_id"),
        entity_type="lab_order", entity_id=order_id,
        performed_by=user.get("sub"),
        event_data={"test_name": order.get("test_name")},
    )
    if specimen:
        emit_clinical_event(
            event_type="SPECIMEN_COLLECTED",
            encounter_id=order.get("encounter_id"),
            patient_id=order.get("patient_id"),
            entity_type="lab_specimen", entity_id=specimen["id"],
            performed_by=user.get("sub"),
            event_data={"specimen_type": specimen_type},
        )
    return {"ok": True, "order_id": order_id, "status": "sample_collected", "specimen": specimen}


@router.post("/orders/{order_id}/receive")
async def receive_specimen(order_id: int, payload: ReceiveRequest, user=Depends(verify_jwt)):
    """Mark a collected specimen as received by the lab and start processing."""
    order = _get_order(order_id)
    if order["status"] != "sample_collected":
        raise HTTPException(status_code=409, detail=f"Order is '{order['status']}'; receiving requires 'sample_collected' status")

    now_iso = datetime.now(timezone.utc).isoformat()
    specimen = _get_specimen_for_order(order_id, payload.specimen_id, ("collected",))
    if specimen:
        db.table(TABLE_LAB_SPECIMENS).update({
            "status": "received",
            "received_at": now_iso,
            "notes": payload.notes or specimen.get("notes"),
        }).eq("id", specimen["id"]).execute()

    db.table(TABLE_LAB_ORDERS).update({"status": "processing"}).eq("id", order_id).execute()

    audit_event(
        "lab_specimen_received",
        {"specimen_id": specimen.get("id") if specimen else None},
        actor_id=user.get("sub"), subject_type="lab_order", subject_id=str(order_id),
    )
    return {"ok": True, "order_id": order_id, "status": "processing", "specimen_id": specimen.get("id") if specimen else None}


@router.post("/orders/{order_id}/reject")
async def reject_specimen(order_id: int, payload: RejectRequest, user=Depends(verify_jwt)):
    """Reject a specimen and reopen the order for a redraw."""
    order = _get_order(order_id)
    if order["status"] not in ("sample_collected", "processing"):
        raise HTTPException(status_code=409, detail=f"Order is '{order['status']}'; rejection requires 'sample_collected' or 'processing' status")

    specimen = _get_specimen_for_order(order_id, payload.specimen_id, ("collected", "received"))
    if specimen:
        db.table(TABLE_LAB_SPECIMENS).update({
            "status": "rejected",
            "rejection_reason": payload.rejection_reason,
        }).eq("id", specimen["id"]).execute()

    db.table(TABLE_LAB_ORDERS).update({
        "status": "ordered",
        "sample_collected_at": None,
    }).eq("id", order_id).execute()

    audit_event(
        "lab_specimen_rejected",
        {"reason": payload.rejection_reason, "specimen_id": specimen.get("id") if specimen else None},
        actor_id=user.get("sub"), subject_type="lab_order", subject_id=str(order_id),
    )
    return {"ok": True, "order_id": order_id, "status": "ordered", "specimen_id": specimen.get("id") if specimen else None}


@router.post("/orders/{order_id}/result", status_code=201)
async def record_result(order_id: int, payload: LabResultCreate, user=Depends(verify_jwt)):
    """Record the lab result for an order. An unverified result is updated
    in place on re-submission; a verified result must go through
    /result/amend instead, since authenticated results are immutable."""
    order = _get_order(order_id)
    if order["status"] == "cancelled":
        raise HTTPException(status_code=409, detail="Order is cancelled")

    existing = _get_latest_result(order_id)
    if existing and existing.get("verified_at"):
        raise HTTPException(
            status_code=409,
            detail="Result already verified — use POST /lab/orders/{order_id}/result/amend to correct it",
        )
    if not existing and order["status"] not in ("processing", "sent_out"):
        raise HTTPException(
            status_code=409,
            detail=f"Order is '{order['status']}'; recording a result requires the specimen to be received first ('processing'), or the order to be 'sent_out'",
        )

    resulted_by = payload.resulted_by or user.get("sub") or "system"
    data = _build_result_row(order, payload, resulted_by)

    try:
        if existing:
            result = db.table(TABLE_LAB_RESULTS).update(data).eq("id", existing["id"]).execute()
        else:
            result = db.table(TABLE_LAB_RESULTS).insert(data).execute()
    except Exception as exc:
        logger.error("Lab result save failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to save result")

    # Update order status
    db.table(TABLE_LAB_ORDERS).update({"status": "resulted"}).eq("id", order_id).execute()

    res_row = result.data[0] if result.data else {**data, "id": existing["id"] if existing else None}
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
    # emit_clinical_event only writes to the audit log — nothing pushes this
    # to connected clients without it, so the OPD queue/doctor dashboard
    # would only pick a new result up on a manual refresh.
    if order.get("encounter_id"):
        asyncio.create_task(realtime_hub.broadcast("encounter_updates", {
            "event": "lab_result_ready",
            "encounter_id": order.get("encounter_id"),
            "order_id": order_id,
            "test_name": order.get("test_name"),
            "is_critical": payload.is_critical,
        }))
    return {"ok": True, "result": res_row}


@router.post("/orders/{order_id}/verify")
async def verify_result(order_id: int, payload: VerifyRequest, user=Depends(verify_jwt)):
    """Verify and authenticate the current lab result. This also serves as
    critical-result acknowledgement — /lab/critical already filters on
    verified_at IS NULL. Authenticated results are immutable from here on;
    corrections go through /result/amend instead."""
    order = _get_order(order_id)
    result = _get_latest_result(order_id)
    if not result:
        raise HTTPException(status_code=404, detail="No result recorded for this order yet")
    if result.get("verified_at"):
        raise HTTPException(
            status_code=409,
            detail=f"Already verified by {result.get('verified_by') or 'unknown'} at {result['verified_at']}",
        )

    now_iso = datetime.now(timezone.utc).isoformat()
    verified_by = user.get("sub") or "system"
    db.table(TABLE_LAB_RESULTS).update({
        "verified_by": verified_by,
        "verified_at": now_iso,
    }).eq("id", result["id"]).execute()

    audit_event("lab_result_verified", {"test_name": order.get("test_name")}, actor_id=user.get("sub"), subject_type="lab_order", subject_id=str(order_id))
    emit_clinical_event(
        event_type="LAB_RESULT_VERIFIED",
        encounter_id=order.get("encounter_id"),
        patient_id=order.get("patient_id"),
        entity_type="lab_order", entity_id=order_id,
        performed_by=user.get("sub"),
        event_data={"test_name": order.get("test_name"), "result_id": result["id"]},
    )
    return {"ok": True, "order_id": order_id, "result_id": result["id"], "verified_by": verified_by, "verified_at": now_iso}


@router.post("/orders/{order_id}/result/amend", status_code=201)
async def amend_result(order_id: int, payload: ResultAmendRequest, user=Depends(verify_jwt)):
    """Correct a verified result. Authenticated results are immutable, so
    this inserts a new row referencing the one it supersedes rather than
    editing verified_by/verified_at in place. The amendment starts its own
    verify cycle — verified_by/verified_at are left null on the new row."""
    order = _get_order(order_id)
    prior = _get_latest_result(order_id)
    if not prior or not prior.get("verified_at"):
        raise HTTPException(status_code=409, detail="No verified result exists to amend")

    resulted_by = payload.resulted_by or user.get("sub") or "system"
    data = _build_result_row(order, payload, resulted_by)
    data["amends_result_id"] = prior["id"]
    data["amendment_reason"] = payload.amendment_reason

    try:
        result = db.table(TABLE_LAB_RESULTS).insert(data).execute()
    except Exception as exc:
        logger.error("Lab result amendment insert failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to save amended result")

    res_row = result.data[0] if result.data else data
    audit_event(
        "lab_result_amended",
        {"prior_result_id": prior["id"], "reason": payload.amendment_reason},
        actor_id=user.get("sub"), subject_type="lab_order", subject_id=str(order_id),
    )
    emit_clinical_event(
        event_type="LAB_RESULT_READY",
        encounter_id=order.get("encounter_id"),
        patient_id=order.get("patient_id"),
        entity_type="lab_order", entity_id=order_id,
        performed_by=user.get("sub"),
        event_data={"test_name": order.get("test_name"), "amended": True, "amends_result_id": prior["id"]},
    )
    return {"ok": True, "result": res_row}


@router.get("/orders/{order_id}/results")
async def list_result_versions(order_id: int, user=Depends(verify_jwt)):
    """All result-row versions for an order, oldest first — the amendment trail."""
    _get_order(order_id)
    result = (
        db.table(TABLE_LAB_RESULTS)
        .select("*")
        .eq("lab_order_id", order_id)
        .order("id")
        .execute()
    )
    return {"results": result.data or [], "count": len(result.data or [])}


# ─── Lab Test Templates ───────────────────────────────────────────────────────
# Per-test structured result templates (item 19: attendants manually
# transcribe Mindray readings into named fields per test, e.g. "Serum
# Bilirubin" → "Total Bilirubin" / "Direct Bilirubin").

@router.post("/templates", status_code=201)
async def create_lab_template(payload: LabTemplateCreate, user=Depends(verify_jwt)):
    """Create a lab test template, or a new version if one is already active
    for this test_name (the prior version is deactivated, not deleted, so
    existing results keep resolving to the template they were entered against)."""
    existing = (
        db.table(TABLE_LAB_TEST_TEMPLATES)
        .select("id,version")
        .eq("test_name", payload.test_name)
        .eq("is_active", True)
        .execute()
    )
    next_version = 1
    if existing.data:
        for row in existing.data:
            db.table(TABLE_LAB_TEST_TEMPLATES).update({"is_active": False}).eq("id", row["id"]).execute()
        next_version = max(r["version"] for r in existing.data) + 1

    data = {
        "test_name": payload.test_name,
        "catalog_id": payload.catalog_id,
        "version": next_version,
        "analytes": [a.model_dump(exclude_none=True) for a in payload.analytes],
        "created_by": user.get("sub") or "system",
    }
    try:
        result = db.table(TABLE_LAB_TEST_TEMPLATES).insert(data).execute()
    except Exception as exc:
        logger.error("Lab template creation failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to save lab test template")

    template = result.data[0] if result.data else data
    audit_event(
        "lab_template_created",
        {"test_name": payload.test_name, "version": next_version},
        actor_id=user.get("sub"),
        subject_type="lab_test_template",
        subject_id=str(template.get("id") or ""),
    )
    return {"ok": True, "template": template}


@router.get("/templates")
async def list_lab_templates(
    test_name: Optional[str] = Query(None),
    active_only: bool = Query(True),
    user=Depends(verify_jwt),
):
    """List lab test templates, optionally filtered by test name."""
    query = db.table(TABLE_LAB_TEST_TEMPLATES).select("*").order("test_name")
    if test_name:
        query = query.ilike("test_name", f"%{test_name.strip()}%")
    if active_only:
        query = query.eq("is_active", True)
    result = query.execute()
    return {"templates": result.data or [], "count": len(result.data or [])}


@router.get("/templates/for-test")
async def get_template_for_test(
    test_name: str = Query(..., min_length=1),
    user=Depends(verify_jwt),
):
    """Fetch the active analyte template for a test name — this is what
    drives the per-patient result entry pop-up card."""
    template = _get_active_template(test_name)
    return {"template": template}


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
    """List all critical lab results that have not been verified. Enriched
    with the parent order's test_name and the patient's name/MRN so this can
    drive a clickable worklist — note `id` here is the *result* row id, the
    order to open is `lab_order_id`."""
    result = db.table(TABLE_LAB_RESULTS).select("*") \
        .eq("is_critical", True) \
        .is_("verified_at", None) \
        .order("resulted_at", desc=True) \
        .execute()
    rows = result.data or []

    if rows:
        try:
            order_ids = list({r["lab_order_id"] for r in rows if r.get("lab_order_id") is not None})
            orders = db.table(TABLE_LAB_ORDERS).select("id,test_name,urgency,status").in_("id", order_ids).execute()
            order_map = {o["id"]: o for o in (orders.data or [])}
            pid_set = list({r["patient_id"] for r in rows if r.get("patient_id") is not None})
            pt_rows = db.table(TABLE_PATIENTS).select("id,mrn,first_name,last_name").in_("id", pid_set).execute()
            pt_map = {p["id"]: p for p in (pt_rows.data or [])}
            for r in rows:
                o = order_map.get(r.get("lab_order_id"))
                if o:
                    r["test_name"] = o.get("test_name")
                    r["urgency"] = o.get("urgency")
                    r["order_status"] = o.get("status")
                p = pt_map.get(r.get("patient_id"))
                if p:
                    fn = (p.get("first_name") or "").strip()
                    ln = (p.get("last_name") or "").strip()
                    r["patient_name"] = f"{fn} {ln}".strip() or None
                    r["patient_mrn"] = p.get("mrn")
        except Exception as exc:
            logger.warning("critical results enrichment failed: %s", exc)

    return {"critical_results": rows, "count": len(rows)}


# ─── Lab Catalog Search ───────────────────────────────────────────────────────

@router.get("/catalog/search")
async def search_lab_catalog(
    q: str = Query(..., min_length=2, description="Code, name, or abbreviation keyword"),
    limit: int = Query(20, ge=1, le=50),
    user=Depends(verify_jwt),
):
    """Search the lab test catalog by code, name, or abbreviation."""
    q = q.strip()
    try:
        results = (
            db.table(TABLE_LAB_CATALOG)
            .select("id,code,name,abbreviation,category,specimen_type,unit,reference_range,turnaround_hours")
            .eq("is_active", True)
            .or_(f"code.ilike.{q}%,name.ilike.%{q}%,abbreviation.ilike.{q}%")
            .order("name")
            .limit(limit)
            .execute()
        )
        return {"tests": results.data or [], "count": len(results.data or [])}
    except Exception as exc:
        logger.error("Lab catalog search failed: %s", exc)
        return {"tests": [], "count": 0}


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
