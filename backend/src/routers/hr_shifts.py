"""
HR Shifts & Leave Router — RoyanHealth / Royan Hospital
=========================================================
Staff shift scheduling, leave request management, and payroll stub.

Endpoints:
  POST   /hr/shifts                         – Schedule a staff shift
  GET    /hr/shifts                         – List shifts (filter: staff, date, department)
  PATCH  /hr/shifts/{id}                    – Update shift (swap, cancel)
  DELETE /hr/shifts/{id}                    – Remove shift

  POST   /hr/leave                          – Submit leave request
  GET    /hr/leave                          – List leave requests (filter: staff, status, type)
  GET    /hr/leave/{id}                     – Leave request detail
  PATCH  /hr/leave/{id}/status             – Approve / reject leave

  GET    /hr/payroll                        – List payroll records
  POST   /hr/payroll                        – Create payroll record
  GET    /hr/payroll/{staff_id}/summary     – Payroll summary for a staff member

  GET    /hr/stats                          – HR dashboard KPIs
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
    TABLE_STAFF_SHIFTS,
    TABLE_LEAVE_REQUESTS,
    TABLE_PAYROLL_RECORDS,
    SHIFT_TYPE_ALLOWED,
    LEAVE_TYPE_ALLOWED,
    LEAVE_STATUS_ALLOWED,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/hr", tags=["HR — Shifts & Leave"])

SHIFT_TYPES  = SHIFT_TYPE_ALLOWED
LEAVE_TYPES  = LEAVE_TYPE_ALLOWED
LEAVE_STATUS = LEAVE_STATUS_ALLOWED


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class ShiftCreate(BaseModel):
    staff_id: str = Field(..., min_length=1)
    staff_name: Optional[str] = None
    department: Optional[str] = None
    role: Optional[str] = None                  # nurse | doctor | lab_tech | pharmacist | etc.
    shift_type: str = "morning"                 # morning | afternoon | night | on_call | split
    shift_date: str                             # ISO date
    start_time: Optional[str] = None            # HH:MM
    end_time: Optional[str] = None              # HH:MM
    notes: Optional[str] = None

    model_config = {"extra": "ignore"}


class ShiftUpdate(BaseModel):
    shift_type: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    status: Optional[str] = None               # scheduled | completed | cancelled | swapped
    swap_with_staff_id: Optional[str] = None
    notes: Optional[str] = None

    model_config = {"extra": "ignore"}


class LeaveRequest(BaseModel):
    staff_id: str = Field(..., min_length=1)
    staff_name: Optional[str] = None
    department: Optional[str] = None
    leave_type: str = "annual"
    start_date: str                             # ISO date
    end_date: str                               # ISO date
    reason: Optional[str] = None
    handover_to: Optional[str] = None          # staff_id of cover person
    documents_attached: bool = False

    model_config = {"extra": "ignore"}


class LeaveStatusUpdate(BaseModel):
    status: str                                 # approved | rejected | cancelled
    approved_by: Optional[str] = None
    rejection_reason: Optional[str] = None
    notes: Optional[str] = None

    model_config = {"extra": "ignore"}


class PayrollRecord(BaseModel):
    staff_id: str = Field(..., min_length=1)
    staff_name: Optional[str] = None
    department: Optional[str] = None
    pay_period_start: str                       # ISO date
    pay_period_end: str                         # ISO date
    basic_salary: float = Field(..., ge=0)
    allowances: float = 0.0
    overtime_pay: float = 0.0
    deductions: float = 0.0
    tax: float = 0.0
    pension: float = 0.0
    net_pay: Optional[float] = None            # auto-computed if not provided
    payment_status: str = "pending"            # pending | paid | reversed
    payment_date: Optional[str] = None
    payment_method: Optional[str] = None       # bank_transfer | cash | cheque
    notes: Optional[str] = None

    model_config = {"extra": "ignore"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_leave(leave_id: int) -> dict:
    r = db.table(TABLE_LEAVE_REQUESTS).select("*").eq("id", leave_id).execute()
    if not r.data:
        raise HTTPException(status_code=404, detail=f"Leave request {leave_id} not found")
    return r.data[0]


def _get_shift(shift_id: int) -> dict:
    r = db.table(TABLE_STAFF_SHIFTS).select("*").eq("id", shift_id).execute()
    if not r.data:
        raise HTTPException(status_code=404, detail=f"Shift {shift_id} not found")
    return r.data[0]


def _calc_leave_days(start_date: str, end_date: str) -> int:
    try:
        s = datetime.fromisoformat(start_date)
        e = datetime.fromisoformat(end_date)
        return max(1, (e - s).days + 1)
    except Exception:
        return 1


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Shift Endpoints
# ---------------------------------------------------------------------------

@router.post("/shifts", status_code=201)
async def create_shift(payload: ShiftCreate, user=Depends(verify_jwt)):
    if payload.shift_type not in SHIFT_TYPES:
        raise HTTPException(status_code=422, detail=f"shift_type must be one of {SHIFT_TYPES}")

    data = payload.model_dump(exclude_none=True)
    data["status"]     = "scheduled"
    data["created_by"] = user.get("sub") or "system"
    try:
        result = db.table(TABLE_STAFF_SHIFTS).insert(data).execute()
    except Exception as exc:
        logger.error("Shift creation failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to create shift")
    shift = result.data[0] if result.data else data
    audit_event("shift_scheduled", {"staff_id": payload.staff_id, "date": payload.shift_date, "type": payload.shift_type},
                actor_id=user.get("sub"), subject_type="shift", subject_id=str(shift.get("id") or ""))
    return {"ok": True, "shift": shift}


@router.get("/shifts")
async def list_shifts(
    staff_id: Optional[str]    = Query(None),
    department: Optional[str]  = Query(None),
    shift_date: Optional[str]  = Query(None),
    shift_type: Optional[str]  = Query(None),
    status: Optional[str]      = Query(None),
    week_start: Optional[str]  = Query(None),   # ISO date — returns 7 days from this date
    limit: int                 = Query(100, ge=1, le=500),
    user=Depends(verify_jwt),
):
    query = db.table(TABLE_STAFF_SHIFTS).select("*").order("shift_date").order("start_time").limit(limit)
    if staff_id:   query = query.eq("staff_id", staff_id)
    if department: query = query.eq("department", department)
    if shift_date: query = query.eq("shift_date", shift_date)
    if shift_type: query = query.eq("shift_type", shift_type)
    if status:     query = query.eq("status", status)
    if week_start:
        from datetime import timedelta
        week_end = (datetime.fromisoformat(week_start) + timedelta(days=6)).date().isoformat()
        query = query.gte("shift_date", week_start).lte("shift_date", week_end)
    result = query.execute()
    return {"shifts": result.data or [], "count": len(result.data or [])}


@router.patch("/shifts/{shift_id}")
async def update_shift(shift_id: int, payload: ShiftUpdate, user=Depends(verify_jwt)):
    _get_shift(shift_id)
    updates = payload.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=422, detail="No fields to update")
    db.table(TABLE_STAFF_SHIFTS).update(updates).eq("id", shift_id).execute()
    audit_event("shift_updated", updates, actor_id=user.get("sub"), subject_type="shift", subject_id=str(shift_id))
    return {"ok": True, "shift_id": shift_id}


@router.delete("/shifts/{shift_id}")
async def delete_shift(shift_id: int, user=Depends(verify_jwt)):
    _get_shift(shift_id)
    db.table(TABLE_STAFF_SHIFTS).update({"status": "cancelled"}).eq("id", shift_id).execute()
    audit_event("shift_cancelled", {}, actor_id=user.get("sub"), subject_type="shift", subject_id=str(shift_id))
    return {"ok": True, "shift_id": shift_id}


# ---------------------------------------------------------------------------
# Leave Endpoints
# ---------------------------------------------------------------------------

@router.post("/leave", status_code=201)
async def submit_leave(payload: LeaveRequest, user=Depends(verify_jwt)):
    if payload.leave_type not in LEAVE_TYPES:
        raise HTTPException(status_code=422, detail=f"leave_type must be one of {LEAVE_TYPES}")

    days = _calc_leave_days(payload.start_date, payload.end_date)
    data = payload.model_dump(exclude_none=True)
    data["status"]       = "pending"
    data["days_count"]   = days
    data["submitted_by"] = user.get("sub") or "system"
    try:
        result = db.table(TABLE_LEAVE_REQUESTS).insert(data).execute()
    except Exception as exc:
        logger.error("Leave request failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to submit leave request")
    record = result.data[0] if result.data else data
    audit_event("leave_requested", {"type": payload.leave_type, "days": days, "staff_id": payload.staff_id},
                actor_id=user.get("sub"), subject_type="leave_request", subject_id=str(record.get("id") or ""))
    return {"ok": True, "record": record}


@router.get("/leave")
async def list_leave(
    staff_id: Optional[str]    = Query(None),
    status: Optional[str]      = Query(None),
    leave_type: Optional[str]  = Query(None),
    department: Optional[str]  = Query(None),
    limit: int                 = Query(50, ge=1, le=200),
    user=Depends(verify_jwt),
):
    query = db.table(TABLE_LEAVE_REQUESTS).select("*").order("start_date", desc=True).limit(limit)
    if staff_id:   query = query.eq("staff_id", staff_id)
    if status:     query = query.eq("status", status)
    if leave_type: query = query.eq("leave_type", leave_type)
    if department: query = query.eq("department", department)
    result = query.execute()
    return {"requests": result.data or [], "count": len(result.data or [])}


@router.get("/leave/{leave_id}")
async def get_leave(leave_id: int, user=Depends(verify_jwt)):
    return {"request": _get_leave(leave_id)}


@router.patch("/leave/{leave_id}/status")
async def update_leave_status(leave_id: int, payload: LeaveStatusUpdate, user=Depends(verify_jwt)):
    leave = _get_leave(leave_id)
    if leave["status"] not in ("pending",):
        raise HTTPException(status_code=409, detail=f"Cannot update a leave request in '{leave['status']}' status")
    if payload.status not in LEAVE_STATUS:
        raise HTTPException(status_code=422, detail=f"status must be one of {LEAVE_STATUS}")

    updates: dict = {
        "status":      payload.status,
        "approved_by": payload.approved_by or user.get("sub") or "system",
        "actioned_at": _now(),
    }
    if payload.rejection_reason: updates["rejection_reason"] = payload.rejection_reason
    if payload.notes:            updates["notes"]            = payload.notes

    db.table(TABLE_LEAVE_REQUESTS).update(updates).eq("id", leave_id).execute()
    audit_event(f"leave_{payload.status}", {"staff_id": leave["staff_id"], "days": leave.get("days_count")},
                actor_id=user.get("sub"), subject_type="leave_request", subject_id=str(leave_id))
    return {"ok": True, "leave_id": leave_id, "status": payload.status}


# ---------------------------------------------------------------------------
# Payroll Endpoints (Stub)
# ---------------------------------------------------------------------------

@router.post("/payroll", status_code=201)
async def create_payroll(payload: PayrollRecord, user=Depends(verify_jwt)):
    data = payload.model_dump(exclude_none=True)
    # Auto-compute net_pay if not provided
    if "net_pay" not in data:
        data["net_pay"] = round(
            payload.basic_salary + payload.allowances + payload.overtime_pay
            - payload.deductions - payload.tax - payload.pension,
            2,
        )
    data["created_by"] = user.get("sub") or "system"
    try:
        result = db.table(TABLE_PAYROLL_RECORDS).insert(data).execute()
    except Exception as exc:
        logger.error("Payroll record failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to create payroll record")
    record = result.data[0] if result.data else data
    audit_event("payroll_created", {"staff_id": payload.staff_id, "net_pay": data["net_pay"]},
                actor_id=user.get("sub"), subject_type="payroll", subject_id=str(record.get("id") or ""))
    return {"ok": True, "record": record}


@router.get("/payroll")
async def list_payroll(
    staff_id: Optional[str]       = Query(None),
    department: Optional[str]     = Query(None),
    payment_status: Optional[str] = Query(None),
    limit: int                    = Query(50, ge=1, le=200),
    user=Depends(verify_jwt),
):
    query = db.table(TABLE_PAYROLL_RECORDS).select("*").order("pay_period_start", desc=True).limit(limit)
    if staff_id:       query = query.eq("staff_id", staff_id)
    if department:     query = query.eq("department", department)
    if payment_status: query = query.eq("payment_status", payment_status)
    result = query.execute()
    return {"records": result.data or [], "count": len(result.data or [])}


@router.get("/payroll/{staff_id}/summary")
async def payroll_summary(staff_id: str, user=Depends(verify_jwt)):
    result = db.table(TABLE_PAYROLL_RECORDS).select(
        "pay_period_start,pay_period_end,basic_salary,net_pay,payment_status"
    ).eq("staff_id", staff_id).order("pay_period_start", desc=True).limit(12).execute()
    rows = result.data or []
    total_gross = sum(r.get("basic_salary", 0) for r in rows)
    total_net   = sum(r.get("net_pay", 0) for r in rows)
    return {"staff_id": staff_id, "records": rows, "total_gross": total_gross, "total_net": total_net}


# ---------------------------------------------------------------------------
# HR Dashboard Stats
# ---------------------------------------------------------------------------

@router.get("/stats")
async def hr_stats(user=Depends(verify_jwt)):
    today = datetime.now(timezone.utc).date().isoformat()

    shifts_today = db.table(TABLE_STAFF_SHIFTS).select("shift_type,status").eq("shift_date", today).execute()
    shift_rows   = shifts_today.data or []
    on_duty      = sum(1 for r in shift_rows if r.get("status") == "scheduled")
    by_shift_type: dict = {}
    for r in shift_rows:
        t = r.get("shift_type") or "morning"
        by_shift_type[t] = by_shift_type.get(t, 0) + 1

    leave_result = db.table(TABLE_LEAVE_REQUESTS).select("status,leave_type").execute()
    leave_rows   = leave_result.data or []
    pending_leave = sum(1 for r in leave_rows if r.get("status") == "pending")
    approved_leave = sum(1 for r in leave_rows if r.get("status") == "approved")
    by_leave_type: dict = {}
    for r in leave_rows:
        lt = r.get("leave_type") or "annual"
        by_leave_type[lt] = by_leave_type.get(lt, 0) + 1

    payroll_result = db.table(TABLE_PAYROLL_RECORDS).select("payment_status,net_pay").execute()
    pay_rows       = payroll_result.data or []
    pending_payroll = sum(r.get("net_pay", 0) for r in pay_rows if r.get("payment_status") == "pending")

    return {
        "shifts_today":   {"total": len(shift_rows), "on_duty": on_duty, "by_type": by_shift_type},
        "leave":          {"pending": pending_leave, "approved": approved_leave, "by_type": by_leave_type},
        "payroll":        {"pending_amount": round(pending_payroll, 2)},
    }
