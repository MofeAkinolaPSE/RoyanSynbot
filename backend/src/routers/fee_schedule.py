"""Fee Schedule Router — manage hospital service pricing."""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.constants import TABLE_FEE_SCHEDULE
from src.db import audit_event, db
from src.middleware import verify_jwt

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/fee-schedule", tags=["Fee Schedule"])

FEE_CATEGORIES = {
    "consultation",
    "procedure",
    "lab",
    "radiology",
    "pharmacy",
    "nursing",
    "theatre",
    "ward",
    "other",
}


class FeeCreate(BaseModel):
    service_name: str = Field(..., min_length=1)
    category: str = "other"
    base_price: float = Field(..., ge=0)
    unit: str = "per visit"
    active: bool = True
    notes: Optional[str] = None

    model_config = {"extra": "ignore"}


class FeeUpdate(BaseModel):
    service_name: Optional[str] = None
    category: Optional[str] = None
    base_price: Optional[float] = None
    unit: Optional[str] = None
    active: Optional[bool] = None
    notes: Optional[str] = None

    model_config = {"extra": "ignore"}


@router.get("")
async def list_fees(
    category: Optional[str] = Query(None),
    active_only: bool = Query(True),
    user=Depends(verify_jwt),
):
    """List fee schedule entries."""
    query = db.table(TABLE_FEE_SCHEDULE).select("*").order("category").order("service_name")
    if category:
        query = query.eq("category", category)
    if active_only:
        query = query.eq("active", True)
    result = query.execute()
    fees = result.data or []

    summary: dict[str, dict] = {}
    for f in fees:
        cat = f.get("category", "other")
        if cat not in summary:
            summary[cat] = {"count": 0, "total": 0.0}
        summary[cat]["count"] += 1
        summary[cat]["total"] += float(f.get("base_price") or 0)

    return {"fees": fees, "count": len(fees), "summary": summary}


@router.post("", status_code=201)
async def create_fee(payload: FeeCreate, user=Depends(verify_jwt)):
    """Create a new fee schedule entry."""
    if payload.category not in FEE_CATEGORIES:
        raise HTTPException(status_code=422, detail=f"category must be one of {sorted(FEE_CATEGORIES)}")

    data = payload.model_dump()
    try:
        result = db.table(TABLE_FEE_SCHEDULE).insert(data).execute()
    except Exception as exc:
        logger.error("Fee schedule insert failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to create fee entry")

    fee = (result.data or [data])[0]
    audit_event(
        "fee_schedule_created",
        {"service_name": payload.service_name, "base_price": payload.base_price},
        actor_id=user.get("sub"),
        subject_type="fee_schedule",
        subject_id=str(fee.get("id") or ""),
    )
    return {"ok": True, "fee": fee}


@router.patch("/{fee_id}")
async def update_fee(fee_id: int, payload: FeeUpdate, user=Depends(verify_jwt)):
    """Update a fee schedule entry."""
    r = db.table(TABLE_FEE_SCHEDULE).select("id").eq("id", fee_id).execute()
    if not r.data:
        raise HTTPException(status_code=404, detail=f"Fee entry {fee_id} not found")

    updates = payload.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    if "category" in updates and updates["category"] not in FEE_CATEGORIES:
        raise HTTPException(status_code=422, detail=f"category must be one of {sorted(FEE_CATEGORIES)}")

    try:
        db.table(TABLE_FEE_SCHEDULE).update(updates).eq("id", fee_id).execute()
    except Exception as exc:
        logger.error("Fee schedule update failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to update fee entry")

    audit_event(
        "fee_schedule_updated",
        {"fee_id": fee_id, "fields": list(updates.keys())},
        actor_id=user.get("sub"),
        subject_type="fee_schedule",
        subject_id=str(fee_id),
    )
    return {"ok": True, "fee_id": fee_id, "updated_fields": list(updates.keys())}


@router.delete("/{fee_id}")
async def delete_fee(fee_id: int, user=Depends(verify_jwt)):
    """Deactivate a fee schedule entry."""
    r = db.table(TABLE_FEE_SCHEDULE).select("id").eq("id", fee_id).execute()
    if not r.data:
        raise HTTPException(status_code=404, detail=f"Fee entry {fee_id} not found")

    try:
        db.table(TABLE_FEE_SCHEDULE).update({"active": False}).eq("id", fee_id).execute()
    except Exception as exc:
        logger.error("Fee schedule delete failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to deactivate fee entry")

    audit_event("fee_schedule_deactivated", {"fee_id": fee_id}, actor_id=user.get("sub"), subject_type="fee_schedule", subject_id=str(fee_id))
    return {"ok": True, "fee_id": fee_id}
