"""
Pharmacy Inventory Router — RoyanHealth / Royan Hospital
============================================================
The Pharmacy Inventory workspace: batch/lot-aware drug & vaccine stock,
live risk-tier classification, demand trends, and replenishment requests.
Separate from pharmacy_dispensing.py (prescriptions/dispense/MAR/returns)
since Inventory is now its own workspace, not a Dispensing tab.

Endpoints:
  GET  /pharmacy/inventory/cards                        – Grouped-by-drug, live-stock-only cards
  GET  /pharmacy/inventory/drugs                         – Catalog search/typeahead
  GET  /pharmacy/inventory/drugs/{formulary_id}          – Drill-down: batches + trend
  POST /pharmacy/inventory/drugs                         – Add drug (+ optional first batch)
  POST /pharmacy/inventory/drugs/{formulary_id}/receive   – Receive/stock-in a batch
  POST /pharmacy/inventory/batches/{batch_id}/adjust      – Adjust a specific batch
  GET  /pharmacy/inventory/summary                       – Workspace KPI rollup
  GET  /pharmacy/inventory/trends/most-prescribed         – Leaderboard
  GET  /pharmacy/inventory/trends/recently-dispensed      – Recent activity feed
  POST /pharmacy/replenishment-request                    – Submit a replenishment request
  GET  /pharmacy/replenishment-requests                   – List requests
  PATCH /pharmacy/replenishment-requests/{id}/status       – Approve/order/receive/cancel
"""
from __future__ import annotations

import datetime as dt
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.db import db, audit_event
from src.middleware import verify_jwt, require_role
from src.constants import TABLE_REPLENISHMENT_REQUESTS, INVENTORY_CATEGORY_ALLOWED
from src.services import pharmacy_inventory_service as inv

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/pharmacy", tags=["Pharmacy Inventory"])

REPLENISHMENT_STATUS_ALLOWED = {"recommended", "approved", "ordered", "received", "cancelled"}
URGENCY_ALLOWED = {"routine", "urgent", "stat"}


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class AddDrugRequest(BaseModel):
    code: Optional[str] = None
    generic_name: str = Field(..., min_length=1, max_length=200)
    brand_name: Optional[str] = None
    drug_class: Optional[str] = None
    category: str = "drug"   # drug | vaccine | consumable | other
    form: Optional[str] = None
    strength: Optional[str] = None
    unit: Optional[str] = None
    unit_cost: Optional[float] = None
    lead_time_days: Optional[int] = None
    safety_stock_days: Optional[int] = None
    reorder_level: Optional[float] = None
    # optional first batch, received in the same call
    batch_number: Optional[str] = None
    quantity_received: Optional[float] = None
    supplier: Optional[str] = None
    location: Optional[str] = None
    expiry_date: Optional[str] = None
    notes: Optional[str] = None

    model_config = {"extra": "ignore"}


class ReceiveBatchRequest(BaseModel):
    batch_number: str = Field(..., min_length=1)
    quantity_received: float = Field(..., gt=0)
    unit_cost: Optional[float] = None
    supplier: Optional[str] = None
    location: Optional[str] = None
    expiry_date: Optional[str] = None
    notes: Optional[str] = None

    model_config = {"extra": "ignore"}


class BatchAdjustRequest(BaseModel):
    adjustment: float
    reason: str = "manual_adjustment"
    notes: Optional[str] = None

    model_config = {"extra": "ignore"}


class ReplenishmentRequestCreate(BaseModel):
    formulary_id: Optional[int] = None
    drug_name: Optional[str] = None            # legacy fallback / free-text drug, maps to `sku`
    requested_qty: Optional[float] = Field(None, gt=0)   # server computes from risk tier when omitted
    ward: Optional[str] = None
    urgency: Optional[str] = None
    unit: Optional[str] = None
    notes: Optional[str] = None

    model_config = {"extra": "ignore"}


# ---------------------------------------------------------------------------
# Cards / catalog / drill-down
# ---------------------------------------------------------------------------

@router.get("/inventory/cards")
async def list_inventory_cards(
    category: Optional[str] = Query(None),
    risk_tier: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    limit: int = Query(60, ge=1, le=200, description="Cap the card list to the N most recently-dispensed drugs"),
    offset: int = Query(0, ge=0),
    user=Depends(verify_jwt),
):
    if category and category not in INVENTORY_CATEGORY_ALLOWED:
        raise HTTPException(status_code=422, detail=f"category must be one of {sorted(INVENTORY_CATEGORY_ALLOWED)}")
    if risk_tier and risk_tier not in {"CRITICAL", "WARNING", "MONITOR", "ADEQUATE"}:
        raise HTTPException(status_code=422, detail="risk_tier must be one of CRITICAL/WARNING/MONITOR/ADEQUATE")
    cards = inv.list_drug_cards(category=category, risk_tier=risk_tier, search=search, limit=limit, offset=offset)
    return {"cards": cards, "count": len(cards)}


@router.get("/inventory/drugs")
async def search_drugs(
    search: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    user=Depends(verify_jwt),
):
    """Flat catalog search (includes zero-stock rows) — for add-batch pickers."""
    query = db.table("royan_drug_formulary").select("*").order("generic_name").limit(limit)
    if search:
        query = query.ilike("generic_name", f"%{search.strip()}%")
    if category:
        query = query.eq("category", category)
    result = query.execute()
    return {"drugs": result.data or [], "count": len(result.data or [])}


@router.get("/inventory/drugs/{formulary_id}")
async def get_drug_drilldown(formulary_id: int, user=Depends(verify_jwt)):
    detail = inv.get_drug_detail(formulary_id)
    if not detail:
        raise HTTPException(status_code=404, detail=f"Drug {formulary_id} not found")
    return detail


@router.post("/inventory/drugs", status_code=201, dependencies=[Depends(require_role("pharmacist", "admin"))])
async def add_drug(payload: AddDrugRequest, user=Depends(verify_jwt)):
    if payload.category not in INVENTORY_CATEGORY_ALLOWED:
        raise HTTPException(status_code=422, detail=f"category must be one of {sorted(INVENTORY_CATEGORY_ALLOWED)}")

    formulary_data = {
        "code": payload.code, "generic_name": payload.generic_name, "brand_name": payload.brand_name,
        "drug_class": payload.drug_class, "category": payload.category, "form": payload.form,
        "strength": payload.strength, "unit": payload.unit, "unit_cost": payload.unit_cost,
        "lead_time_days": payload.lead_time_days, "safety_stock_days": payload.safety_stock_days,
        "reorder_level": payload.reorder_level,
    }
    drug = inv.upsert_formulary_drug(formulary_data)

    batch = None
    if payload.batch_number and payload.quantity_received:
        batch = inv.upsert_batch(
            formulary_id=drug["id"], batch_number=payload.batch_number, quantity_received=payload.quantity_received,
            unit_cost=payload.unit_cost, supplier=payload.supplier, location=payload.location,
            expiry_date=payload.expiry_date, notes=payload.notes, created_by=user.get("sub") or "system",
        )

    audit_event("drug_catalog_added", {"drug": drug.get("generic_name")}, actor_id=user.get("sub"), subject_type="drug_formulary", subject_id=str(drug.get("id") or ""))
    return {"ok": True, "drug": drug, "batch": batch}


@router.post("/inventory/drugs/{formulary_id}/receive", status_code=201, dependencies=[Depends(require_role("pharmacist", "admin"))])
async def receive_batch(formulary_id: int, payload: ReceiveBatchRequest, user=Depends(verify_jwt)):
    exists = db.table("royan_drug_formulary").select("id").eq("id", formulary_id).execute()
    if not exists.data:
        raise HTTPException(status_code=404, detail=f"Drug {formulary_id} not found")

    batch = inv.upsert_batch(
        formulary_id=formulary_id, batch_number=payload.batch_number, quantity_received=payload.quantity_received,
        unit_cost=payload.unit_cost, supplier=payload.supplier, location=payload.location,
        expiry_date=payload.expiry_date, notes=payload.notes, created_by=user.get("sub") or "system",
    )
    audit_event(
        "inventory_batch_received",
        {"formulary_id": formulary_id, "batch_number": payload.batch_number, "quantity": payload.quantity_received},
        actor_id=user.get("sub"), subject_type="inventory_batch", subject_id=str(batch.get("id") or ""),
    )
    return {"ok": True, "batch": batch}


@router.post("/inventory/batches/{batch_id}/adjust", dependencies=[Depends(require_role("pharmacist", "admin"))])
async def adjust_inventory_batch(batch_id: int, payload: BatchAdjustRequest, user=Depends(verify_jwt)):
    try:
        result = inv.adjust_batch(batch_id, payload.adjustment, payload.reason)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    audit_event(
        "inventory_batch_adjusted",
        {"batch_id": batch_id, "adjustment": payload.adjustment, "reason": payload.reason},
        actor_id=user.get("sub"), subject_type="inventory_batch", subject_id=str(batch_id),
    )
    return {"ok": True, **result}


# ---------------------------------------------------------------------------
# Workspace summary / trends
# ---------------------------------------------------------------------------

@router.get("/inventory/summary")
async def inventory_summary(user=Depends(verify_jwt)):
    return inv.get_workspace_summary()


@router.get("/inventory/trends/most-prescribed")
async def trends_most_prescribed(
    window_days: int = Query(30, ge=1, le=365),
    limit: int = Query(10, ge=1, le=50),
    user=Depends(verify_jwt),
):
    rows = inv.most_prescribed(window_days=window_days, limit=limit)
    return {"drugs": rows, "count": len(rows), "window_days": window_days}


@router.get("/inventory/trends/recently-dispensed")
async def trends_recently_dispensed(limit: int = Query(20, ge=1, le=100), user=Depends(verify_jwt)):
    rows = inv.recently_dispensed(limit=limit)
    return {"events": rows, "count": len(rows)}


# ---------------------------------------------------------------------------
# Replenishment requests (moved from pharmacy_dispensing.py — real columns
# instead of the old notes-folding workaround)
# ---------------------------------------------------------------------------

@router.post("/replenishment-request", status_code=201, dependencies=[Depends(require_role("nurse", "doctor", "pharmacist", "admin", "ops"))])
async def create_replenishment_request(payload: ReplenishmentRequestCreate, user=Depends(verify_jwt)):
    if payload.urgency and payload.urgency not in URGENCY_ALLOWED:
        raise HTTPException(status_code=422, detail=f"urgency must be one of {sorted(URGENCY_ALLOWED)}")
    if not payload.formulary_id and not payload.drug_name:
        raise HTTPException(status_code=422, detail="formulary_id or drug_name is required")

    drug_name = payload.drug_name
    risk_tier_at_request = None
    requested_qty = payload.requested_qty

    if payload.formulary_id:
        detail = inv.get_drug_detail(payload.formulary_id)
        if detail:
            drug_name = drug_name or detail["formulary"].get("generic_name")
            risk_tier_at_request = detail["risk"]["tier"]
            if requested_qty is None:
                requested_qty = detail["risk"]["recommended_reorder_qty"] or 0

    if requested_qty is None:
        raise HTTPException(status_code=422, detail="requested_qty could not be computed automatically — supply it explicitly")

    data = {
        "sku": (drug_name or "").strip() or f"formulary:{payload.formulary_id}",
        "formulary_id": payload.formulary_id,
        "requested_qty": requested_qty,
        "status": "recommended",
        "created_by": user.get("sub") or "system",
        "ward": payload.ward,
        "urgency": payload.urgency,
        "unit": payload.unit,
        "risk_tier_at_request": risk_tier_at_request,
        "notes": payload.notes,
    }
    try:
        result = db.table(TABLE_REPLENISHMENT_REQUESTS).insert(data).execute()
    except Exception as exc:
        logger.error("Replenishment request failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to submit replenishment request")
    req = (result.data or [data])[0]
    audit_event("replenishment_requested", {"sku": data["sku"], "qty": requested_qty}, actor_id=user.get("sub"), subject_type="replenishment_request", subject_id=str(req.get("id") or ""))
    return {"ok": True, "request": req}


@router.get("/replenishment-requests")
async def list_replenishment_requests(
    sku: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    user=Depends(verify_jwt),
):
    query = db.table(TABLE_REPLENISHMENT_REQUESTS).select("*").order("created_at", desc=True).limit(limit)
    if sku:
        query = query.ilike("sku", f"%{sku.strip()}%")
    if status:
        if status not in REPLENISHMENT_STATUS_ALLOWED:
            raise HTTPException(status_code=422, detail=f"status must be one of {REPLENISHMENT_STATUS_ALLOWED}")
        query = query.eq("status", status)
    result = query.execute()
    return {"requests": result.data or [], "count": len(result.data or [])}


@router.patch("/replenishment-requests/{req_id}/status", dependencies=[Depends(require_role("pharmacist", "admin", "ops"))])
async def update_replenishment_status(req_id: int, status: str = Query(...), user=Depends(verify_jwt)):
    if status not in REPLENISHMENT_STATUS_ALLOWED:
        raise HTTPException(status_code=422, detail=f"status must be one of {REPLENISHMENT_STATUS_ALLOWED}")
    r = db.table(TABLE_REPLENISHMENT_REQUESTS).select("id").eq("id", req_id).execute()
    if not r.data:
        raise HTTPException(status_code=404, detail=f"Request {req_id} not found")

    updates: dict = {"status": status}
    now_iso = dt.datetime.now(dt.timezone.utc).isoformat()
    if status == "approved":
        updates["approved_by"] = user.get("sub") or "system"
        updates["approved_at"] = now_iso
    if status == "received":
        updates["fulfilled_at"] = now_iso

    db.table(TABLE_REPLENISHMENT_REQUESTS).update(updates).eq("id", req_id).execute()
    audit_event("replenishment_status_updated", {"status": status}, actor_id=user.get("sub"), subject_type="replenishment_request", subject_id=str(req_id))
    return {"ok": True, "req_id": req_id, "status": status}
