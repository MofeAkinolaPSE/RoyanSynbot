"""
Facility Audits & Equipment Maintenance Router — RoyanHealth / Royan Hospital
================================================================================
General facility audits (fire safety, infection control, JCI-style, etc.) and
biomedical/facility equipment maintenance tracking. NOT the pharma QMS tables
(audit_schedule/equipment_registry, migration 070) and NOT the platform-
reliability tables (royan_maintenance_assets/tasks, migration 110) — a
separate, genuinely hospital-native pair.

Endpoints:
  POST   /facility/audits                    – Schedule an audit
  GET    /facility/audits                    – List audits (filter: status, department)
  GET    /facility/audits/{id}                – Audit detail
  PATCH  /facility/audits/{id}/start          – scheduled -> in_progress
  PATCH  /facility/audits/{id}/complete       – in_progress -> completed

  POST   /facility/maintenance                – Create a maintenance task
  GET    /facility/maintenance                – List tasks (filter: all|overdue|upcoming)
  GET    /facility/maintenance/{id}            – Task detail
  PATCH  /facility/maintenance/{id}/complete   – pending -> completed

  GET    /facility/stats                      – Dashboard KPIs
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.db import db, audit_event
from src.middleware import require_role
from src.constants import (
    TABLE_STAFF,
    TABLE_FACILITY_AUDITS,
    TABLE_EQUIPMENT_MAINTENANCE,
    FACILITY_AUDIT_RISK_ALLOWED,
    FACILITY_AUDIT_STATUS_ALLOWED,
    EQUIPMENT_MAINTENANCE_TYPE_ALLOWED,
    EQUIPMENT_MAINTENANCE_STATUS_ALLOWED,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/facility", tags=["Facility Audits & Maintenance"])

# Matches the "Audits & Maintenance" nav entry (nav-items.ts) exactly —
# facility/equipment maintenance is an operations concern, not a doctor/
# nurse workflow, so no clinical roles are included here.
FACILITY_ROLES = ("admin", "ops", "quality_assurance", "management")


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class AuditCreate(BaseModel):
    audit_title: str = Field(..., min_length=3)
    department: str
    scheduled_date: str
    risk_level: str = "medium"

    model_config = {"extra": "ignore"}


class AuditComplete(BaseModel):
    findings: Optional[str] = None
    recommendations: Optional[str] = None
    score: Optional[float] = None

    model_config = {"extra": "ignore"}


class MaintenanceCreate(BaseModel):
    equipment_name: str = Field(..., min_length=1)
    equipment_type: Optional[str] = None
    location: Optional[str] = None
    maintenance_type: str = "preventive"
    description: Optional[str] = None
    due_date: str

    model_config = {"extra": "ignore"}


class MaintenanceComplete(BaseModel):
    completion_notes: Optional[str] = None
    next_due_date: Optional[str] = None

    model_config = {"extra": "ignore"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _clean(data: dict) -> dict:
    """Drop empty-string values alongside None — the frontend sends "" for
    untouched optional inputs (date fields especially), which
    `exclude_none=True` doesn't catch and Postgres rejects outright for
    typed columns like date."""
    return {k: v for k, v in data.items() if v != ""}


def _resolve_staff_id_for_user(user: dict) -> Optional[str]:
    """Map the acting JWT subject (an auth user id) to their own royan_staff.id,
    via royan_staff.user_id — the two are different uuid spaces, `sub` is never
    itself a valid royan_staff.id, so it can't be passed through directly."""
    sub = user.get("sub")
    if not sub:
        return None
    r = db.table(TABLE_STAFF).select("id").eq("user_id", sub).limit(1).execute()
    return r.data[0]["id"] if r.data else None


def _get_audit(audit_id: str) -> dict:
    r = db.table(TABLE_FACILITY_AUDITS).select("*").eq("id", audit_id).execute()
    if not r.data:
        raise HTTPException(status_code=404, detail=f"Audit {audit_id} not found")
    return r.data[0]


def _get_maintenance(task_id: str) -> dict:
    r = db.table(TABLE_EQUIPMENT_MAINTENANCE).select("*").eq("id", task_id).execute()
    if not r.data:
        raise HTTPException(status_code=404, detail=f"Maintenance task {task_id} not found")
    return r.data[0]


# ---------------------------------------------------------------------------
# Audit Endpoints
# ---------------------------------------------------------------------------

@router.post("/audits", status_code=201)
async def create_audit(payload: AuditCreate, user=Depends(require_role(*FACILITY_ROLES))):
    if payload.risk_level not in FACILITY_AUDIT_RISK_ALLOWED:
        raise HTTPException(status_code=422, detail=f"risk_level must be one of {sorted(FACILITY_AUDIT_RISK_ALLOWED)}")

    data = _clean(payload.model_dump(exclude_none=True))
    data["status"] = "scheduled"
    resolved = _resolve_staff_id_for_user(user)
    if resolved:
        data["created_by"] = resolved

    try:
        result = db.table(TABLE_FACILITY_AUDITS).insert(data).execute()
    except Exception as exc:
        logger.error("Audit scheduling failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to schedule audit")

    audit = result.data[0] if result.data else data
    audit_event("facility_audit_scheduled", {"department": payload.department, "risk_level": payload.risk_level},
                actor_id=user.get("sub"), subject_type="facility_audit", subject_id=str(audit.get("id") or ""))
    return {"ok": True, "audit": audit}


@router.get("/audits")
async def list_audits(
    status: Optional[str]     = Query(None),
    department: Optional[str] = Query(None),
    limit: int                = Query(100, ge=1, le=500),
    user=Depends(require_role(*FACILITY_ROLES)),
):
    query = db.table(TABLE_FACILITY_AUDITS).select("*").order("scheduled_date", desc=True).limit(limit)
    if status:     query = query.eq("status", status)
    if department: query = query.eq("department", department)
    result = query.execute()
    rows = result.data or []
    today = _today()
    for r in rows:
        r["is_overdue"] = bool(
            r.get("status") in ("scheduled", "in_progress")
            and r.get("scheduled_date") and str(r["scheduled_date"]) < today
        )
    return {"audits": rows, "count": len(rows)}


@router.get("/audits/{audit_id}")
async def get_audit(audit_id: str, user=Depends(require_role(*FACILITY_ROLES))):
    return {"audit": _get_audit(audit_id)}


@router.patch("/audits/{audit_id}/start")
async def start_audit(audit_id: str, user=Depends(require_role(*FACILITY_ROLES))):
    audit = _get_audit(audit_id)
    if audit["status"] != "scheduled":
        raise HTTPException(status_code=409, detail=f"Cannot start an audit in '{audit['status']}' status")
    db.table(TABLE_FACILITY_AUDITS).update({"status": "in_progress", "started_at": _now()}).eq("id", audit_id).execute()
    audit_event("facility_audit_started", {}, actor_id=user.get("sub"),
                subject_type="facility_audit", subject_id=str(audit_id))
    return {"ok": True, "audit_id": audit_id, "status": "in_progress"}


@router.patch("/audits/{audit_id}/complete")
async def complete_audit(audit_id: str, payload: AuditComplete, user=Depends(require_role(*FACILITY_ROLES))):
    audit = _get_audit(audit_id)
    if audit["status"] != "in_progress":
        raise HTTPException(status_code=409, detail=f"Cannot complete an audit in '{audit['status']}' status")
    updates = _clean(payload.model_dump(exclude_none=True))
    updates["status"] = "completed"
    updates["completed_at"] = _now()
    db.table(TABLE_FACILITY_AUDITS).update(updates).eq("id", audit_id).execute()
    audit_event("facility_audit_completed", {"score": updates.get("score")}, actor_id=user.get("sub"),
                subject_type="facility_audit", subject_id=str(audit_id))
    return {"ok": True, "audit_id": audit_id, "status": "completed"}


# ---------------------------------------------------------------------------
# Maintenance Endpoints
# ---------------------------------------------------------------------------

@router.post("/maintenance", status_code=201)
async def create_maintenance(payload: MaintenanceCreate, user=Depends(require_role(*FACILITY_ROLES))):
    if payload.maintenance_type not in EQUIPMENT_MAINTENANCE_TYPE_ALLOWED:
        raise HTTPException(status_code=422, detail=f"maintenance_type must be one of {sorted(EQUIPMENT_MAINTENANCE_TYPE_ALLOWED)}")

    data = _clean(payload.model_dump(exclude_none=True))
    data["status"] = "pending"
    resolved = _resolve_staff_id_for_user(user)
    if resolved:
        data["created_by"] = resolved

    try:
        result = db.table(TABLE_EQUIPMENT_MAINTENANCE).insert(data).execute()
    except Exception as exc:
        logger.error("Maintenance task creation failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to create maintenance task")

    task = result.data[0] if result.data else data
    audit_event("maintenance_task_created", {"equipment_name": payload.equipment_name, "type": payload.maintenance_type},
                actor_id=user.get("sub"), subject_type="equipment_maintenance", subject_id=str(task.get("id") or ""))
    return {"ok": True, "task": task}


@router.get("/maintenance")
async def list_maintenance(
    status_filter: Optional[str] = Query(None, description="all | overdue | upcoming"),
    limit: int                   = Query(100, ge=1, le=500),
    user=Depends(require_role(*FACILITY_ROLES)),
):
    result = db.table(TABLE_EQUIPMENT_MAINTENANCE).select("*").order("due_date").limit(limit).execute()
    rows = result.data or []
    today = _today()
    for r in rows:
        r["is_overdue"] = bool(
            r.get("status") == "pending" and r.get("due_date") and str(r["due_date"]) < today
        )
    if status_filter == "overdue":
        rows = [r for r in rows if r["is_overdue"]]
    elif status_filter == "upcoming":
        rows = [r for r in rows if r.get("status") == "pending" and not r["is_overdue"]]
    return {"tasks": rows, "count": len(rows)}


@router.get("/maintenance/{task_id}")
async def get_maintenance(task_id: str, user=Depends(require_role(*FACILITY_ROLES))):
    return {"task": _get_maintenance(task_id)}


@router.patch("/maintenance/{task_id}/complete")
async def complete_maintenance(task_id: str, payload: MaintenanceComplete, user=Depends(require_role(*FACILITY_ROLES))):
    task = _get_maintenance(task_id)
    if task["status"] != "pending":
        raise HTTPException(status_code=409, detail=f"Cannot complete a task in '{task['status']}' status")
    updates = _clean(payload.model_dump(exclude_none=True))
    updates["status"] = "completed"
    updates["completed_at"] = _now()
    resolved = _resolve_staff_id_for_user(user)
    if resolved:
        updates["completed_by"] = resolved
    db.table(TABLE_EQUIPMENT_MAINTENANCE).update(updates).eq("id", task_id).execute()
    audit_event("maintenance_task_completed", {}, actor_id=user.get("sub"),
                subject_type="equipment_maintenance", subject_id=str(task_id))

    # A next_due_date now actually schedules the follow-up occurrence —
    # previously this was recorded on the completed row and nothing else
    # ever read it, so equipment silently fell out of the pending list
    # after every completion. Failure here doesn't fail the completion
    # itself, which has already succeeded.
    next_task = None
    next_due = updates.get("next_due_date")
    if next_due:
        next_task_data = {
            "equipment_name":   task["equipment_name"],
            "maintenance_type": task["maintenance_type"],
            "due_date":         next_due,
            "status":           "pending",
        }
        if task.get("equipment_type"): next_task_data["equipment_type"] = task["equipment_type"]
        if task.get("location"):       next_task_data["location"] = task["location"]
        if task.get("description"):    next_task_data["description"] = task["description"]
        if resolved:
            next_task_data["created_by"] = resolved
        try:
            result = db.table(TABLE_EQUIPMENT_MAINTENANCE).insert(next_task_data).execute()
            next_task = result.data[0] if result.data else next_task_data
            audit_event("maintenance_task_created",
                        {"equipment_name": task["equipment_name"], "auto_scheduled_from": task_id},
                        actor_id=user.get("sub"), subject_type="equipment_maintenance",
                        subject_id=str(next_task.get("id") or ""))
        except Exception as exc:
            logger.error("Auto-scheduling next maintenance task failed: %s", exc)

    return {"ok": True, "task_id": task_id, "status": "completed", "next_task": next_task}


# ---------------------------------------------------------------------------
# Dashboard Stats
# ---------------------------------------------------------------------------

@router.get("/stats")
async def facility_stats(user=Depends(require_role(*FACILITY_ROLES))):
    today = _today()

    audits_result = db.table(TABLE_FACILITY_AUDITS).select("status,scheduled_date").execute()
    audits = audits_result.data or []
    audits_overdue = sum(
        1 for a in audits
        if a.get("status") in ("scheduled", "in_progress") and a.get("scheduled_date") and str(a["scheduled_date"]) < today
    )

    maint_result = db.table(TABLE_EQUIPMENT_MAINTENANCE).select("status,due_date").execute()
    maint = maint_result.data or []
    maintenance_overdue = sum(
        1 for m in maint
        if m.get("status") == "pending" and m.get("due_date") and str(m["due_date"]) < today
    )

    return {
        "audits":      {"total": len(audits), "overdue": audits_overdue},
        "maintenance": {"total": len(maint), "overdue": maintenance_overdue},
    }
