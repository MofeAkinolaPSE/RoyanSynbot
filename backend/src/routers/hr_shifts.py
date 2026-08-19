"""
HR Shifts & Leave Router — RoyanHealth / Royan Hospital
=========================================================
Staff shift scheduling, leave request management, and payroll.

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
from src.middleware import verify_jwt, require_role
from src.constants import (
    TABLE_STAFF,
    TABLE_STAFF_SHIFTS,
    TABLE_LEAVE_REQUESTS,
    TABLE_PAYROLL_RECORDS,
    SHIFT_TYPE_ALLOWED,
    LEAVE_TYPE_ALLOWED,
    LEAVE_STATUS_ALLOWED,
    PAYROLL_STATUS_ALLOWED,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/hr", tags=["HR — Shifts & Leave"])

SHIFT_TYPES    = SHIFT_TYPE_ALLOWED
LEAVE_TYPES    = LEAVE_TYPE_ALLOWED
LEAVE_STATUS   = LEAVE_STATUS_ALLOWED
PAYROLL_STATUS = PAYROLL_STATUS_ALLOWED


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class ShiftCreate(BaseModel):
    staff_id: str = Field(..., min_length=1)     # uuid, FK -> royan_staff.id
    department: Optional[str] = None
    shift_type: str = "morning"                  # morning | afternoon | night | on_call
    shift_date: str                               # ISO date
    start_time: str                                # HH:MM — NOT NULL on the table
    end_time: str                                  # HH:MM — NOT NULL on the table
    notes: Optional[str] = None

    model_config = {"extra": "ignore"}


class ShiftUpdate(BaseModel):
    shift_type: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    status: Optional[str] = None               # scheduled | completed | missed | swapped
    notes: Optional[str] = None

    model_config = {"extra": "ignore"}


class LeaveRequest(BaseModel):
    staff_id: str = Field(..., min_length=1)     # uuid, FK -> royan_staff.id
    leave_type: str = "annual"
    start_date: str                             # ISO date
    end_date: str                               # ISO date
    reason: Optional[str] = None

    model_config = {"extra": "ignore"}


class LeaveStatusUpdate(BaseModel):
    status: str                                 # approved | rejected | cancelled
    approved_by: Optional[str] = None           # staff.id of the acting approver, if known

    model_config = {"extra": "ignore"}


class PayrollRecord(BaseModel):
    staff_id: str = Field(..., min_length=1)     # uuid, FK -> royan_staff.id
    period_month: int = Field(..., ge=1, le=12)
    period_year: int = Field(..., ge=2000)
    gross_salary: float = Field(..., ge=0)
    overtime_hours: float = 0.0
    overtime_rate: float = 0.0
    allowances: float = 0.0
    deductions: float = 0.0
    tax: float = 0.0
    pension: float = 0.0
    net_salary: Optional[float] = None          # auto-computed if not provided
    status: str = "draft"                       # draft | approved | paid
    payment_date: Optional[str] = None
    payment_method: Optional[str] = None        # bank_transfer | cash | cheque
    notes: Optional[str] = None

    model_config = {"extra": "ignore"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_leave(leave_id: str) -> dict:
    r = db.table(TABLE_LEAVE_REQUESTS).select("*").eq("id", leave_id).execute()
    if not r.data:
        raise HTTPException(status_code=404, detail=f"Leave request {leave_id} not found")
    return r.data[0]


def _get_shift(shift_id: str) -> dict:
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


def _resolve_staff_id_for_user(user: dict) -> Optional[str]:
    """Map the acting JWT subject (an auth user id) to their own royan_staff.id,
    via royan_staff.user_id — the two are different uuid spaces, `sub` is never
    itself a valid royan_staff.id, so it can't be passed through directly."""
    sub = user.get("sub")
    if not sub:
        return None
    r = db.table(TABLE_STAFF).select("id").eq("user_id", sub).limit(1).execute()
    return r.data[0]["id"] if r.data else None


def _enrich_with_staff(rows: list[dict]) -> list[dict]:
    """Batch-attach staff_name/designation/staff_department for a list of rows
    that carry a staff_id — same pattern as list_anc/list_authorizations this
    session. Falls back to the row's own `department` (shifts can cover a
    different department than the staff's home one) when present."""
    staff_ids = list({r["staff_id"] for r in rows if r.get("staff_id")})
    if not staff_ids:
        return rows
    staff = db.table(TABLE_STAFF).select("id,full_name,department,designation").in_("id", staff_ids).execute()
    by_id = {s["id"]: s for s in (staff.data or [])}
    for r in rows:
        s = by_id.get(r.get("staff_id"))
        r["staff_name"] = s.get("full_name") if s else None
        r["designation"] = s.get("designation") if s else None
        if not r.get("department"):
            r["department"] = s.get("department") if s else None
    return rows


# ---------------------------------------------------------------------------
# Shift Endpoints
# ---------------------------------------------------------------------------

@router.post("/shifts", status_code=201)
async def create_shift(payload: ShiftCreate, user=Depends(verify_jwt)):
    if payload.shift_type not in SHIFT_TYPES:
        raise HTTPException(status_code=422, detail=f"shift_type must be one of {sorted(SHIFT_TYPES)}")

    data = payload.model_dump(exclude_none=True)
    data["status"] = "scheduled"
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
    shifts = _enrich_with_staff(result.data or [])
    return {"shifts": shifts, "count": len(shifts)}


@router.patch("/shifts/{shift_id}")
async def update_shift(shift_id: str, payload: ShiftUpdate, user=Depends(verify_jwt)):
    _get_shift(shift_id)
    updates = payload.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=422, detail="No fields to update")
    if "status" in updates and updates["status"] not in ("scheduled", "completed", "missed", "swapped"):
        raise HTTPException(status_code=422, detail="status must be one of scheduled, completed, missed, swapped")
    db.table(TABLE_STAFF_SHIFTS).update(updates).eq("id", shift_id).execute()
    audit_event("shift_updated", updates, actor_id=user.get("sub"), subject_type="shift", subject_id=str(shift_id))
    return {"ok": True, "shift_id": shift_id}


@router.delete("/shifts/{shift_id}")
async def delete_shift(shift_id: str, user=Depends(verify_jwt)):
    shift = _get_shift(shift_id)
    # No "cancelled" status exists on this table (CHECK only allows scheduled/
    # completed/missed/swapped) — a real delete is what this endpoint's verb
    # already promises, and audit_event preserves the history independent of
    # the row's existence.
    db.table(TABLE_STAFF_SHIFTS).delete().eq("id", shift_id).execute()
    audit_event("shift_deleted", {"staff_id": shift.get("staff_id"), "date": shift.get("shift_date")},
                actor_id=user.get("sub"), subject_type="shift", subject_id=str(shift_id))
    return {"ok": True, "shift_id": shift_id}


# ---------------------------------------------------------------------------
# Leave Endpoints
# ---------------------------------------------------------------------------

@router.post("/leave", status_code=201)
async def submit_leave(payload: LeaveRequest, user=Depends(verify_jwt)):
    if payload.leave_type not in LEAVE_TYPES:
        raise HTTPException(status_code=422, detail=f"leave_type must be one of {sorted(LEAVE_TYPES)}")

    days = _calc_leave_days(payload.start_date, payload.end_date)
    data = payload.model_dump(exclude_none=True)
    data["status"]     = "pending"
    data["days_count"] = days
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
    limit: int                 = Query(50, ge=1, le=200),
    user=Depends(verify_jwt),
):
    query = db.table(TABLE_LEAVE_REQUESTS).select("*").order("start_date", desc=True).limit(limit)
    if staff_id:   query = query.eq("staff_id", staff_id)
    if status:     query = query.eq("status", status)
    if leave_type: query = query.eq("leave_type", leave_type)
    result = query.execute()
    requests = _enrich_with_staff(result.data or [])
    return {"requests": requests, "count": len(requests)}


@router.get("/leave/{leave_id}")
async def get_leave(leave_id: str, user=Depends(verify_jwt)):
    return {"request": _get_leave(leave_id)}


@router.patch("/leave/{leave_id}/status")
async def update_leave_status(leave_id: str, payload: LeaveStatusUpdate, user=Depends(verify_jwt)):
    leave = _get_leave(leave_id)
    if leave["status"] not in ("pending",):
        raise HTTPException(status_code=409, detail=f"Cannot update a leave request in '{leave['status']}' status")
    if payload.status not in LEAVE_STATUS:
        raise HTTPException(status_code=422, detail=f"status must be one of {sorted(LEAVE_STATUS)}")

    approved_by = payload.approved_by or _resolve_staff_id_for_user(user)
    updates: dict = {"status": payload.status}
    if approved_by:
        updates["approved_by"] = approved_by

    db.table(TABLE_LEAVE_REQUESTS).update(updates).eq("id", leave_id).execute()
    audit_event(f"leave_{payload.status}", {"staff_id": leave["staff_id"], "days": leave.get("days_count")},
                actor_id=user.get("sub"), subject_type="leave_request", subject_id=str(leave_id))
    return {"ok": True, "leave_id": leave_id, "status": payload.status}


# ---------------------------------------------------------------------------
# Payroll Endpoints
# ---------------------------------------------------------------------------

@router.post("/payroll", status_code=201)
async def create_payroll(payload: PayrollRecord, user=Depends(require_role("admin", "hr", "management"))):
    if payload.status not in PAYROLL_STATUS:
        raise HTTPException(status_code=422, detail=f"status must be one of {sorted(PAYROLL_STATUS)}")

    data = payload.model_dump(exclude_none=True)
    if "net_salary" not in data:
        data["net_salary"] = round(
            payload.gross_salary
            + (payload.overtime_hours * payload.overtime_rate)
            + payload.allowances
            - payload.deductions - payload.tax - payload.pension,
            2,
        )
    try:
        result = db.table(TABLE_PAYROLL_RECORDS).insert(data).execute()
    except Exception as exc:
        msg = str(exc)
        if "unique" in msg.lower() or "duplicate" in msg.lower():
            raise HTTPException(status_code=409, detail="A payroll record already exists for this staff member and period")
        logger.error("Payroll record failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to create payroll record")
    record = result.data[0] if result.data else data
    audit_event("payroll_created", {"staff_id": payload.staff_id, "net_salary": data["net_salary"]},
                actor_id=user.get("sub"), subject_type="payroll", subject_id=str(record.get("id") or ""))
    return {"ok": True, "record": record}


@router.get("/payroll")
async def list_payroll(
    staff_id: Optional[str]   = Query(None),
    status: Optional[str]     = Query(None),
    limit: int                = Query(50, ge=1, le=200),
    user=Depends(require_role("admin", "hr", "management")),
):
    query = db.table(TABLE_PAYROLL_RECORDS).select("*").order("period_year", desc=True).order("period_month", desc=True).limit(limit)
    if staff_id: query = query.eq("staff_id", staff_id)
    if status:   query = query.eq("status", status)
    result = query.execute()
    records = _enrich_with_staff(result.data or [])
    return {"records": records, "count": len(records)}


@router.get("/payroll/{staff_id}/summary")
async def payroll_summary(staff_id: str, user=Depends(require_role("admin", "hr", "management"))):
    result = db.table(TABLE_PAYROLL_RECORDS).select(
        "period_month,period_year,gross_salary,net_salary,status"
    ).eq("staff_id", staff_id).order("period_year", desc=True).order("period_month", desc=True).limit(12).execute()
    rows = result.data or []
    total_gross = sum(r.get("gross_salary", 0) for r in rows)
    total_net   = sum(r.get("net_salary", 0) for r in rows)
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

    payroll_result = db.table(TABLE_PAYROLL_RECORDS).select("status,net_salary").execute()
    pay_rows       = payroll_result.data or []
    # "Pending" here means not yet paid out (draft or approved), the closest
    # equivalent to the old pending/paid/reversed vocabulary's "pending".
    pending_payroll = sum(r.get("net_salary", 0) for r in pay_rows if r.get("status") in ("draft", "approved"))

    return {
        "shifts_today":   {"total": len(shift_rows), "on_duty": on_duty, "by_type": by_shift_type},
        "leave":          {"pending": pending_leave, "approved": approved_leave, "by_type": by_leave_type},
        "payroll":        {"pending_amount": round(pending_payroll, 2)},
    }
