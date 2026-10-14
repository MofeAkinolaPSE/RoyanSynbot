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
from src.constants import TABLE_REPLENISHMENT_REQUESTS, INVENTORY_CATEGORY_ALLOWED, TABLE_INVENTORY_BATCHES, TABLE_DISPENSING
from src.cache import invalidate_cache_tags
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
def list_inventory_cards(
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
def search_drugs(
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
def get_drug_drilldown(formulary_id: int, user=Depends(verify_jwt)):
    detail = inv.get_drug_detail(formulary_id)
    if not detail:
        raise HTTPException(status_code=404, detail=f"Drug {formulary_id} not found")
    return detail


@router.get("/inventory/drugs/{formulary_id}/rates")
def get_drug_rates(formulary_id: int, user=Depends(verify_jwt)):
    """Historical per-batch pricing migrated from Hope (migration 195).

    Each row carries a full price set — mrp / purchase_price / cost_price /
    sale_price — plus batch number, expiry and stock. royan_inventory_batches
    has only a single `unit_cost` column, so this is the only place the actual
    margin per batch is visible.

    Returns the batches newest-first with a derived margin so the pharmacy can
    see cost against retail without doing the arithmetic per row.
    """
    from src.constants import TABLE_PHARMACY_ITEM_RATES
    try:
        rows = (
            db.table(TABLE_PHARMACY_ITEM_RATES)
            .select("id,batch_number,expiry_date,mrp,purchase_price,cost_price,"
                    "sale_price,stock,loose_stock,vat_class_name,is_active")
            .eq("formulary_id", formulary_id)
            .order("expiry_date", desc=True)
            .limit(100)
            .execute()
            .data
            or []
        )
        for r in rows:
            mrp = r.get("mrp")
            cost = r.get("purchase_price") or r.get("cost_price")
            r["margin"] = round(float(mrp) - float(cost), 2) if (mrp and cost) else None
            r["margin_pct"] = (
                round((float(mrp) - float(cost)) / float(mrp) * 100, 1)
                if (mrp and cost and float(mrp) > 0) else None
            )
        return {"rates": rows, "count": len(rows)}
    except Exception as exc:
        logger.error("Drug rate lookup failed for %s: %s", formulary_id, exc)
        return {"rates": [], "count": 0}


def _books_receipt(formulary_id, batch, batch_number, quantity, unit_cost, supplier, expiry_date, user) -> None:
    """Roy Books: stock the pharmacy receives is valued into the books (DR stock / CR goods
    received not invoiced) in its own transaction; the supplier's bill later clears it."""
    try:
        from src.fin.integrations import post_event
        post_event("PHARMACY_RECEIPT", {
            "formulary_id": formulary_id, "ops_batch_id": (batch or {}).get("id"), "batch_number": batch_number,
            "quantity": quantity, "unit_cost": unit_cost if unit_cost is not None else (batch or {}).get("unit_cost"),
            "supplier": supplier, "expiry_date": expiry_date, "date": dt.date.today().isoformat()}, actor=user.get("sub") or "pharmacy")
    except Exception:
        logger.exception("Roy Books receipt hook failed")


def _books_adjustment(batch_id, quantity, reason_code, reason, user) -> None:
    """Roy Books: a pharmacy adjustment / disposal becomes a DRAFT stock adjustment that
    Finance approves (maker-checker); the pharmacy's own stock has already moved."""
    try:
        from src.fin.integrations import post_event
        b = db.table(TABLE_INVENTORY_BATCHES).select("formulary_id,batch_number,expiry_date,unit_cost").eq("id", batch_id).limit(1).execute().data
        if not b:
            return
        post_event("PHARMACY_ADJUST", {
            "formulary_id": b[0]["formulary_id"], "ops_batch_id": batch_id, "batch_number": b[0].get("batch_number"),
            "expiry_date": b[0].get("expiry_date"), "unit_cost": b[0].get("unit_cost"), "quantity": quantity,
            "reason_code": reason_code, "reason": reason, "date": dt.date.today().isoformat()}, actor=user.get("sub") or "pharmacy")
    except Exception:
        logger.exception("Roy Books adjustment hook failed")


@router.post("/inventory/drugs", status_code=201, dependencies=[Depends(require_role("pharmacist", "admin"))])
def add_drug(payload: AddDrugRequest, user=Depends(verify_jwt)):
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
    if batch and payload.quantity_received:
        _books_receipt(drug["id"], batch, payload.batch_number, payload.quantity_received, payload.unit_cost,
                       payload.supplier, payload.expiry_date, user)
    return {"ok": True, "drug": drug, "batch": batch}


@router.post("/inventory/drugs/{formulary_id}/receive", status_code=201, dependencies=[Depends(require_role("pharmacist", "admin"))])
def receive_batch(formulary_id: int, payload: ReceiveBatchRequest, user=Depends(verify_jwt)):
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
    _books_receipt(formulary_id, batch, payload.batch_number, payload.quantity_received, payload.unit_cost,
                   payload.supplier, payload.expiry_date, user)
    return {"ok": True, "batch": batch}


@router.post("/inventory/batches/{batch_id}/adjust", dependencies=[Depends(require_role("pharmacist", "admin"))])
def adjust_inventory_batch(batch_id: int, payload: BatchAdjustRequest, user=Depends(verify_jwt)):
    try:
        result = inv.adjust_batch(batch_id, payload.adjustment, payload.reason)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    audit_event(
        "inventory_batch_adjusted",
        {"batch_id": batch_id, "adjustment": payload.adjustment, "reason": payload.reason},
        actor_id=user.get("sub"), subject_type="inventory_batch", subject_id=str(batch_id),
    )
    moved = float(result.get("new_qty") or 0) - float(result.get("previous_qty") or 0)
    if moved:
        _books_adjustment(batch_id, moved, None, payload.reason, user)
    return {"ok": True, **result}


# ---------------------------------------------------------------------------
# Workspace summary / trends
# ---------------------------------------------------------------------------

@router.get("/inventory/summary")
def inventory_summary(user=Depends(verify_jwt)):
    return inv.get_workspace_summary()


@router.get("/inventory/trends/most-prescribed")
def trends_most_prescribed(
    window_days: int = Query(30, ge=1, le=365),
    limit: int = Query(10, ge=1, le=50),
    user=Depends(verify_jwt),
):
    rows = inv.most_prescribed(window_days=window_days, limit=limit)
    return {"drugs": rows, "count": len(rows), "window_days": window_days}


@router.get("/inventory/trends/recently-dispensed")
def trends_recently_dispensed(limit: int = Query(20, ge=1, le=100), user=Depends(verify_jwt)):
    rows = inv.recently_dispensed(limit=limit)
    return {"events": rows, "count": len(rows)}


# ---------------------------------------------------------------------------
# Replenishment requests (moved from pharmacy_dispensing.py — real columns
# instead of the old notes-folding workaround)
# ---------------------------------------------------------------------------

@router.post("/replenishment-request", status_code=201, dependencies=[Depends(require_role("nurse", "doctor", "pharmacist", "admin", "ops"))])
def create_replenishment_request(payload: ReplenishmentRequestCreate, user=Depends(verify_jwt)):
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
def list_replenishment_requests(
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
def update_replenishment_status(req_id: int, status: str = Query(...), user=Depends(verify_jwt)):
    if status not in REPLENISHMENT_STATUS_ALLOWED:
        raise HTTPException(status_code=422, detail=f"status must be one of {REPLENISHMENT_STATUS_ALLOWED}")
    if status == "received":
        # reportGUide.md s6: an order is received by the stock arriving, never ticked by hand
        raise HTTPException(status_code=409, detail="An order is received automatically when its stock is received "
                                                    "(Pharmacy > Inventory > Receive stock, or a supplier delivery in Roy Books)")
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


# -- Expired stock ------------------------------------------------------------
#
# "We need to give the pharmacy the ability to remove any expired inventory."
#
# WHICH TABLE
# -----------
# pharmacy_dispensing.py already has /inventory/expired, but it reads
# royan_drug_inventory, which holds 0 rows. The stock the hospital actually has
# is in royan_inventory_batches: 17,281 batches, 536 of them carrying quantity
# on hand. These endpoints use that.
#
# WHY DISPOSAL IS NOT A DELETE
# ----------------------------
# Destroying expired drugs is a regulated act -- NAFDAC expects a record of what
# was destroyed, how much, and who authorised it. So the batch row stays, its
# quantity goes to zero, and the quantity and value destroyed are written into
# the audit trail. A delete would erase the evidence that the disposal happened.

class DisposeBatchRequest(BaseModel):
    reason: Optional[str] = Field(None, max_length=500)
    # Partial disposal is real: a batch can be part-damaged rather than wholly
    # expired. Omitted means dispose of everything on hand.
    quantity: Optional[float] = Field(None, gt=0)

    model_config = {"extra": "ignore"}


@router.get("/inventory/expired")
def list_expired_batches(
    include_empty: bool = Query(False),
    limit: int = Query(200, ge=1, le=1000),
    user=Depends(verify_jwt),
):
    """Batches past their expiry date.

    Defaults to those still holding stock, because those are the ones that can
    be dispensed by mistake. Empty expired batches are historical records, not a
    hazard, and there are ~15,000 of them -- showing those by default would bury
    the handful that matter.
    """
    today = dt.date.today().isoformat()
    try:
        q = (
            db.table(TABLE_INVENTORY_BATCHES)
            .select("id,formulary_id,batch_number,quantity_on_hand,unit_cost,"
                    "expiry_date,supplier,location,received_at")
            .lt("expiry_date", today)
        )
        if not include_empty:
            q = q.gt("quantity_on_hand", 0)
        rows = q.order("expiry_date", desc=False).limit(limit).execute().data or []
    except Exception as exc:
        logger.warning("Expired batch listing failed: %s: %s", type(exc).__name__, exc)
        return {"batches": [], "count": 0, "total_value": 0, "with_stock": 0}

    names = {}
    ids = list({r["formulary_id"] for r in rows if r.get("formulary_id")})
    if ids:
        try:
            for f in db.table("royan_drug_formulary").select("id,generic_name,brand_name").in_("id", ids).execute().data or []:
                names[f["id"]] = f.get("generic_name") or f.get("brand_name")
        except Exception:
            pass

    total_value = 0.0
    for r in rows:
        r["drug_name"] = names.get(r.get("formulary_id"))
        qty = float(r.get("quantity_on_hand") or 0)
        r["value_at_risk"] = round(qty * float(r.get("unit_cost") or 0), 2)
        total_value += r["value_at_risk"]

    return {
        "batches": rows,
        "count": len(rows),
        "with_stock": sum(1 for r in rows if float(r.get("quantity_on_hand") or 0) > 0),
        "total_value": round(total_value, 2),
    }


@router.post("/inventory/batches/{batch_id}/dispose",
             dependencies=[Depends(require_role("pharmacist", "admin"))])
def dispose_batch(batch_id: int, payload: DisposeBatchRequest, user=Depends(verify_jwt)):
    """Write off expired or damaged stock, leaving a record of what went."""
    found = (
        db.table(TABLE_INVENTORY_BATCHES)
        .select("id,formulary_id,batch_number,quantity_on_hand,unit_cost,expiry_date")
        .eq("id", batch_id).limit(1).execute().data
    )
    if not found:
        raise HTTPException(status_code=404, detail=f"Batch {batch_id} not found")
    batch = found[0]

    on_hand = float(batch.get("quantity_on_hand") or 0)
    if on_hand <= 0:
        raise HTTPException(status_code=409, detail="That batch already holds no stock.")

    qty = float(payload.quantity) if payload.quantity is not None else on_hand
    if qty > on_hand:
        raise HTTPException(
            status_code=422,
            detail=f"Cannot dispose of {qty:g} — the batch holds {on_hand:g}.",
        )

    remaining = on_hand - qty
    value = round(qty * float(batch.get("unit_cost") or 0), 2)

    try:
        db.table(TABLE_INVENTORY_BATCHES).update(
            {"quantity_on_hand": remaining, "updated_at": "now()"}
        ).eq("id", batch_id).execute()
    except Exception as exc:
        logger.error("Batch disposal failed: %s: %s", type(exc).__name__, exc)
        raise HTTPException(status_code=500, detail="Could not record the disposal")

    # The regulatory record. Quantity and value are captured at disposal time
    # because unit_cost can be corrected later and this must not move with it.
    audit_event(
        "pharmacy_stock_disposed",
        {
            "batch_id": batch_id,
            "batch_number": batch.get("batch_number"),
            "formulary_id": batch.get("formulary_id"),
            "expiry_date": batch.get("expiry_date"),
            "quantity_disposed": qty,
            "quantity_remaining": remaining,
            "value_disposed": value,
            "reason": (payload.reason or "").strip() or "expired",
        },
        actor_id=user.get("sub"),
        subject_type="inventory_batch",
        subject_id=str(batch_id),
    )
    invalidate_cache_tags("inventory", "pharmacy", "hospital")
    reason = (payload.reason or "").strip() or "expired"
    _books_adjustment(batch_id, -qty, "EXPIRY" if "expir" in reason.lower() else "DAMAGE", reason, user)

    return {
        "ok": True,
        "batch_id": batch_id,
        "disposed": qty,
        "remaining": remaining,
        "value_disposed": value,
    }


@router.get("/inventory/report")
def inventory_report(user=Depends(verify_jwt)):
    """Stock valuation, expiry exposure and dead stock.

    "we need to create an inventory report and add whatever metrics that we
    think we can also add to make our inventory a lot better."

    WHY THIS REPORTS POSITION, NOT MOVEMENT
    ---------------------------------------
    A movement report would be almost empty: only 2 dispensing events fall in
    the last 90 days because the 618,452 migrated records predate go-live. What
    the pharmacy can act on today is the 50.7m sitting on the shelf -- what it
    is worth, what is about to expire, and what has never moved.

    DEAD STOCK IS THE METRIC WORTH ADDING
    -------------------------------------
    Stock that is held but never dispensed is money on a shelf, and nothing in
    the app surfaced it. Judged by whether the drug has EVER been dispensed
    rather than by a recent window, because a recent window would call almost
    everything dead given the migration cut-off.
    """
    today = dt.date.today()
    horizon_30 = (today + dt.timedelta(days=30)).isoformat()
    horizon_90 = (today + dt.timedelta(days=90)).isoformat()

    try:
        batches = (
            db.table(TABLE_INVENTORY_BATCHES)
            .select("id,formulary_id,batch_number,quantity_on_hand,unit_cost,expiry_date")
            .gt("quantity_on_hand", 0).limit(5000).execute().data or []
        )
    except Exception as exc:
        logger.error("Inventory report failed: %s: %s", type(exc).__name__, exc)
        raise HTTPException(status_code=500, detail="Could not build the inventory report")

    names = {}
    ids = list({b["formulary_id"] for b in batches if b.get("formulary_id")})
    if ids:
        try:
            for f in db.table("royan_drug_formulary").select("id,generic_name,brand_name,category").in_("id", ids).execute().data or []:
                names[f["id"]] = f
        except Exception:
            pass

    # Which drugs have ever moved.
    #
    # DISTINCT in SQL, not by pulling rows: there are 614,133 dispensing records
    # carrying a formulary_id, so any row limit silently marks the drugs beyond
    # it as never-dispensed. A first attempt capped at 50,000 and reported all
    # 536 in-stock drugs as dead stock worth 50.7m -- confidently, and wrongly.
    dispensed_ever = set()
    dead_stock_known = True
    conn = db.pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT DISTINCT formulary_id FROM public.%s WHERE formulary_id IS NOT NULL"
                % TABLE_DISPENSING
            )
            dispensed_ever = {r[0] for r in cur.fetchall()}
    except Exception as exc:
        # Reported rather than silently producing a wrong dead-stock figure.
        dead_stock_known = False
        logger.warning("Dead-stock lookup failed: %s: %s", type(exc).__name__, exc)
    finally:
        db.pool.putconn(conn)

    by_drug, expiry = {}, {"expired": 0.0, "within_30": 0.0, "within_90": 0.0, "beyond_90": 0.0, "no_date": 0.0}
    total_value = 0.0

    for b in batches:
        qty = float(b.get("quantity_on_hand") or 0)
        value = qty * float(b.get("unit_cost") or 0)
        total_value += value

        exp = b.get("expiry_date")
        if not exp:
            expiry["no_date"] += value
        elif str(exp) < today.isoformat():
            expiry["expired"] += value
        elif str(exp) < horizon_30:
            expiry["within_30"] += value
        elif str(exp) < horizon_90:
            expiry["within_90"] += value
        else:
            expiry["beyond_90"] += value

        fid = b.get("formulary_id")
        meta = names.get(fid) or {}
        entry = by_drug.setdefault(fid, {
            "formulary_id": fid,
            "drug_name": meta.get("generic_name") or meta.get("brand_name") or f"Drug {fid}",
            "category": meta.get("category"),
            "batches": 0, "quantity": 0.0, "value": 0.0,
            "ever_dispensed": fid in dispensed_ever,
            "earliest_expiry": None,
        })
        entry["batches"] += 1
        entry["quantity"] += qty
        entry["value"] += value
        if exp and (entry["earliest_expiry"] is None or str(exp) < str(entry["earliest_expiry"])):
            entry["earliest_expiry"] = exp

    drugs = sorted(by_drug.values(), key=lambda d: d["value"], reverse=True)
    dead = [d for d in drugs if not d["ever_dispensed"]]

    return {
        "as_at": today.isoformat(),
        "totals": {
            "stock_value": round(total_value, 2),
            "batches": len(batches),
            "drugs": len(drugs),
        },
        "expiry_exposure": {k: round(v, 2) for k, v in expiry.items()},
        # Every in-stock batch currently lacks an expiry date, so the exposure
        # bands are all zero. Said plainly, because "no stock expiring" and "we
        # do not know when this stock expires" are very different facts.
        "batches_without_expiry": sum(1 for b in batches if not b.get("expiry_date")),
        "dead_stock": {
            # None rather than a misleading number if the lookup failed.
            "known": dead_stock_known,
            "count": len(dead) if dead_stock_known else None,
            "value": round(sum(d["value"] for d in dead), 2) if dead_stock_known else None,
            "drugs": dead[:50] if dead_stock_known else [],
        },
        "top_by_value": drugs[:50],
    }


@router.get("/inventory/restock-suggestion/{formulary_id}")
def restock_suggestion(formulary_id: int, user=Depends(verify_jwt)):
    """Everything needed to receive a new batch, prefilled from the last one.

    "if they say, oh, it's amoxiclav, you can just type a-m-o and the rest comes
    in. You automate the input for the expiring date and all those other
    information to come with the restock."

    Sourced from the most recent batch of this drug — including expired ones,
    which is the one place expired records are genuinely useful: last time this
    drug came in, it cost this much, from this supplier, and sat here. That is a
    sensible starting point for the next delivery even if the batch itself is
    long gone.

    Everything returned is a SUGGESTION. The expiry in particular is shifted
    forward by the observed shelf life rather than copied, because copying a
    past date would silently receive stock that is already expired.
    """
    # The column is `form`, not `formulation`. Asking for a column that does not
    # exist makes the query fail, the wrapper return empty, and this raise a
    # "not found" for a drug that exists — so the error named the wrong problem.
    formulary = db.table("royan_drug_formulary").select(
        "id,generic_name,brand_name,category,strength,form,unit,reorder_level"
    ).eq("id", formulary_id).limit(1).execute().data
    if not formulary:
        raise HTTPException(status_code=404, detail=f"Drug {formulary_id} not found")
    drug = formulary[0]

    last = (
        db.table(TABLE_INVENTORY_BATCHES)
        .select("batch_number,unit_cost,supplier,location,expiry_date,received_at,quantity_received")
        .eq("formulary_id", formulary_id)
        .order("received_at", desc=True).limit(1).execute().data
    )
    prev = last[0] if last else {}

    # Shelf life observed on the last delivery, used to propose the next expiry
    # instead of repeating a date that has already passed.
    suggested_expiry = None
    shelf_life_days = None
    if prev.get("received_at") and prev.get("expiry_date"):
        try:
            r = dt.date.fromisoformat(str(prev["received_at"])[:10])
            e = dt.date.fromisoformat(str(prev["expiry_date"])[:10])
            shelf_life_days = (e - r).days
            if shelf_life_days > 0:
                suggested_expiry = (dt.date.today() + dt.timedelta(days=shelf_life_days)).isoformat()
        except (ValueError, TypeError):
            pass

    on_hand = 0.0
    try:
        for b in inv.list_live_batches(formulary_id):
            on_hand += float(b.get("quantity_on_hand") or 0)
    except Exception:
        pass

    return {
        "drug": drug,
        "current_stock": on_hand,
        "suggested": {
            # Deliberately NOT the previous batch number: two deliveries sharing
            # one batch number makes them impossible to tell apart on a recall.
            "batch_number": None,
            "unit_cost": prev.get("unit_cost"),
            "supplier": prev.get("supplier"),
            "location": prev.get("location"),
            "expiry_date": suggested_expiry,
            "quantity": prev.get("quantity_received"),
        },
        "based_on": {
            "last_received_at": prev.get("received_at"),
            "last_batch_number": prev.get("batch_number"),
            "last_expiry_date": prev.get("expiry_date"),
            "observed_shelf_life_days": shelf_life_days,
        } if prev else None,
    }
