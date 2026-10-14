from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File
from pydantic import BaseModel, Field, EmailStr, validator
from typing import Dict, Any, List, Optional
from datetime import date
import datetime as dt
import logging
import csv
import io
import codecs

from src.db import db, audit_event
from src.middleware import verify_jwt, require_role
from src.services.staff_ops import (
    create_staff_member,
    get_staff_by_department,
    get_staff_by_id,
    record_timesheet_entry,
    get_timesheets,
    get_latest_staff_snapshot,
)
from src.services.realtime import realtime_hub
from src.constants import TABLE_TIMESHEETS
from src.cache import invalidate_cache_tags
from src.services.oeis import process_operational_event

router = APIRouter(tags=["staff_ops"])
audit_logger = logging.getLogger("audit")
logger = logging.getLogger("staff_ops")

# --- Models ---

class StaffCreateRequest(BaseModel):
    full_name: str = Field(..., min_length=1, max_length=200)
    email: EmailStr
    department: str = Field(..., max_length=100, description="Finance, Sales, Operations, HR, Management")
    role: Optional[str] = Field(None, max_length=100)

    @validator('department')
    def validate_dept(cls, v):
        allowed = {'Finance', 'Sales', 'Operations', 'HR', 'Management'}
        if v not in allowed:
            raise ValueError(f"Department must be one of {allowed}")
        return v

class TimesheetEntryRequest(BaseModel):
    staff_id: str = Field(..., max_length=100)
    date: date
    # A timesheet entry covers ONE date, so 24 is the real ceiling. The limit is
    # correct; what was missing was any way for a user to act on it. A shift left
    # running for days used to submit its whole elapsed time here (504 hours was
    # reported from the field) and get rejected with no path forward -- the
    # client now asks the user for the hours actually worked instead.
    hours_worked: float = Field(
        ..., gt=0, le=24,
        description="Hours worked on this date. One date per entry, so at most 24.",
    )
    department: str = Field(..., max_length=100)
    activity_note: Optional[str] = Field(None, max_length=1000)

# --- Dependencies ---

def require_hr_admin(request: Request) -> Dict[str, Any]:
    """Write access for Staff Registry: HR or Admin only."""
    payload = verify_jwt(request)
    roles = payload.get("roles", [])
    if not any(r in {"admin", "hr"} for r in roles):
        raise HTTPException(403, "Insufficient privileges (HR/Admin required)")
    return payload

def require_dept_read(request: Request) -> Dict[str, Any]:
    """Read access: Must be authenticated."""
    return verify_jwt(request)

def require_timesheet_write(request: Request) -> Dict[str, Any]:
    """Write access for Timesheets: Admin, HR, Ops, Management."""
    payload = verify_jwt(request)
    roles = payload.get("roles", [])
    allowed = {"admin", "hr", "ops", "management"}
    if not any(r in allowed for r in roles):
        raise HTTPException(403, "Insufficient privileges to record timesheets")
    return payload

# --- Staff Endpoints ---

@router.post("/staff")
async def register_staff(
    staff: StaffCreateRequest, 
    user: Dict[str, Any] = Depends(require_hr_admin)
):
    """Register a new staff member manually."""
    try:
        new_staff = create_staff_member(
            staff.full_name, staff.email, staff.department, staff.role
        )
        audit_logger.info({"event": "staff_created", "target": staff.email, "actor": user.get("sub")})
        await realtime_hub.broadcast("staff_updates", {
            "event": "staff_created",
            "staff_id": new_staff.get("staff_id"),
            "department": new_staff.get("department"),
            "actor": user.get("sub"),
        })
        invalidate_cache_tags("staff", "workforce_dashboard", "hr_summary", "executive")
        try:
            await process_operational_event(
                {
                    "department": "staff",
                    "event_type": "staff_created",
                    "payload": {
                        "staff_id": new_staff.get("staff_id"),
                        "department": new_staff.get("department"),
                        "email": new_staff.get("email"),
                    },
                    "created_by": user.get("sub"),
                    "status": "submitted",
                },
                actor_id=user.get("sub"),
            )
        except Exception:
            pass
        return {"success": True, "data": new_staff}
    except Exception as e:
        audit_logger.error(f"Staff creation failed: {e}")
        raise HTTPException(500, "Failed to create staff record")

@router.get("/staff")
def list_staff(
    department: Optional[str] = None,
    user: Dict[str, Any] = Depends(require_dept_read)
):
    """List staff members (directory view)."""
    return {"data": get_staff_by_department(department)}

@router.get("/staff/snapshot")
def list_staff_snapshot(
    limit: int = 1000,
    user: Dict[str, Any] = Depends(require_dept_read)
):
    """List latest rows from sage_staff_snapshot for diagnostics/fallback UI."""
    rows = get_latest_staff_snapshot(limit=limit)
    return {"data": rows}


@router.get("/staff/{staff_id}")
def get_single_staff(
    staff_id: str,
    user: Dict[str, Any] = Depends(require_dept_read)
):
    staff = get_staff_by_id(staff_id)
    if not staff:
        raise HTTPException(404, "Staff not found")
    return {"data": staff}

@router.post("/staff/import")
def import_staff_csv(
    file: UploadFile = File(...),
    user: Dict[str, Any] = Depends(require_hr_admin)
):
    """Bulk import staff from CSV. Columns: full_name, email, department, role"""
    try:
        reader = csv.DictReader(codecs.iterdecode(file.file, 'utf-8'))
        results = []
        for row in reader:
            # Basic map, skip errors for MVP
            try:
                res = create_staff_member(
                    full_name=row['full_name'],
                    email=row['email'],
                    department=row['department'],
                    role=row.get('role', '')
                )
                results.append(res)
            except Exception as e:
                logging.warning(f"Skipping row {row}: {e}")
        
        audit_logger.info({"event": "staff_bulk_import", "count": len(results), "actor": user.get("sub")})
        return {"success": True, "imported_count": len(results)}
    except Exception as e:
        raise HTTPException(400, f"CSV parsing failed: {str(e)}")

# --- Timesheet Endpoints ---

@router.post("/timesheets")
async def submit_timesheet(
    entry: TimesheetEntryRequest,
    user: Dict[str, Any] = Depends(require_timesheet_write)
):
    """Record a single timesheet entry."""
    try:
        data = record_timesheet_entry(
            entry.staff_id, entry.date, entry.hours_worked, 
            entry.department, entry.activity_note, 
            recorded_by=user.get("sub", "api")
        )
        await realtime_hub.broadcast("staff_updates", {
            "event": "timesheet_recorded",
            "staff_id": entry.staff_id,
            "department": entry.department,
            "hours_worked": entry.hours_worked,
            "recorded_by": user.get("sub", "api"),
        })
        invalidate_cache_tags("staff", "workforce_dashboard", "hr_summary", "executive")
        try:
            await process_operational_event(
                {
                    "department": "staff",
                    "event_type": "timesheet_recorded",
                    "payload": {
                        "staff_id": entry.staff_id,
                        "department": entry.department,
                        "hours_worked": entry.hours_worked,
                        "date": str(entry.date),
                    },
                    "created_by": user.get("sub", "api"),
                    "status": "submitted",
                },
                actor_id=user.get("sub", "api"),
            )
        except Exception:
            pass
        return {"success": True, "data": data}
    except Exception as e:
        logging.error(f"Timesheet error: {e}")
        raise HTTPException(500, "Failed to record timesheet")

@router.get("/timesheets")
def view_timesheets(
    department: Optional[str] = None,
    limit: int = 50,
    user: Dict[str, Any] = Depends(require_dept_read)
):
    """View recent timesheets."""
    return {"data": get_timesheets(department=department, limit=limit)}

@router.get("/timesheets/staff/{staff_id}")
def view_staff_timesheets(
    staff_id: str,
    limit: int = 50,
    user: Dict[str, Any] = Depends(require_dept_read)
):
    return {"data": get_timesheets(staff_id=staff_id, limit=limit)}


# ── Clock in / clock out ─────────────────────────────────────────────────────
#
# The clock now lives in the Staff Workspace (services/staff_workspace.py,
# POST /workspace/time/*): a server-side session with breaks, split at local
# midnight into royan_timesheets rows that HR reviews. These routes stay for any
# older caller and delegate to it, so there is one clock and one answer to
# "who is on shift". They were never reachable from the old Time Tracker page,
# which called /staff/clock/* while this router has no /staff prefix.

def _ws(fn, *args):
    from src.services import staff_workspace as sw
    try:
        return fn(*args)
    except sw.WorkspaceError as e:
        raise HTTPException(status_code=409, detail=str(e).replace("NEEDS_END_TIME: ", ""))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except (LookupError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/clock/status")
def clock_status(user: Dict[str, Any] = Depends(verify_jwt)):
    """Who is clocked in, and since when."""
    from src.services import staff_workspace as sw
    v = _ws(sw.my_time, user)
    s = v.get("session")
    return {"on_shift": bool(s), "status": v["status"], "started_at": s["started_at"] if s else None,
            "elapsed_hours": round(s["worked_seconds"] / 3600, 2) if s else None,
            "today_seconds": v["today_seconds"], "week_seconds": v["week_seconds"]}


@router.post("/clock/in", status_code=201)
def clock_in(payload: Optional[Dict[str, Any]] = None, user: Dict[str, Any] = Depends(verify_jwt)):
    from src.services import staff_workspace as sw
    r = _ws(sw.clock_start, user, payload or {})
    invalidate_cache_tags("staff", "workforce_dashboard", "hr_summary", "executive")
    return {"ok": True, **r}


@router.post("/clock/out")
def clock_out(payload: Optional[Dict[str, Any]] = None, user: Dict[str, Any] = Depends(verify_jwt)):
    from src.services import staff_workspace as sw
    r = _ws(sw.clock_stop, user, payload or {})
    invalidate_cache_tags("staff", "workforce_dashboard", "hr_summary", "executive")
    audit_event("staff_clock_out", {"hours": r.get("recorded_hours")}, actor_id=user.get("sub"),
                subject_type="timesheet", subject_id=str(user.get("sub")))
    return {"ok": True, "hours_worked": r.get("recorded_hours"), **r}


@router.post("/clock/cancel")
def clock_cancel(user: Dict[str, Any] = Depends(verify_jwt)):
    """Discard a running clock without recording time (a clock-in that should not have happened)."""
    from src.services import staff_workspace as sw
    r = _ws(sw.clock_discard, user)
    audit_event("staff_clock_cancelled", {}, actor_id=user.get("sub"), subject_type="timesheet",
                subject_id=str(user.get("sub")))
    return {"ok": True, "cancelled": True, **r}
