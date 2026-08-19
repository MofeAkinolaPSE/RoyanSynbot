from fastapi import APIRouter, HTTPException, Request, Depends
from src.schemas.staff_dashboard import StaffDashboard, ActivityItem, PendingApproval, TaskItem, KPIWidget, Badge, AssignedProjectItem, StaffIdentity, UpcomingItem
from src.middleware import verify_jwt, require_role
from src.services.staff_ops import get_staff_by_user_id
from typing import List
import asyncio, os, json, logging
import datetime as dt
from src.db import db
from src.constants import TABLE_APPOINTMENT_SLOTS, TABLE_APPOINTMENTS, TABLE_PATIENTS

router = APIRouter()
logger = logging.getLogger(__name__)

LEDGER_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "event_ledger.jsonl")
TASKS_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "staff_tasks.json")


def _read_event_ledger_db(limit: int = 500):
    """Primary ledger source — mirrors workflow_jobs.py's DB-backed reader.
    Returns None (not []) on a genuine query failure so callers can tell that
    apart from a real, empty result and fall back to the flat file only then.
    """
    try:
        resp = (
            db.table("event_ledger")
            .select("event_id,department,event_type,payload,approval_status,created_by,created_at")
            .order("created_at", desc=True)
            .limit(max(1, min(limit, 5000)))
            .execute()
        )
        rows = list(reversed(resp.data or []))
        for row in rows:
            row.setdefault("timestamp", row.get("created_at"))
            if row.get("event_id") is not None:
                row["event_id"] = str(row["event_id"])
        return rows
    except Exception as exc:
        logger.warning("event_ledger DB query failed; falling back to local file err=%s", exc)
        return None


def _read_ledger_items_file():
    items = []
    if not os.path.exists(LEDGER_PATH):
        return items
    with open(LEDGER_PATH, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                items.append(json.loads(line))
            except Exception:
                continue
    return items


def _read_tasks():
    if not os.path.exists(TASKS_PATH):
        return []
    try:
        with open(TASKS_PATH, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return []


def _write_tasks(tasks: list):
    parent = os.path.dirname(TASKS_PATH)
    if not os.path.exists(parent):
        os.makedirs(parent, exist_ok=True)
    with open(TASKS_PATH, "w", encoding="utf-8") as fh:
        json.dump(tasks, fh, indent=2)


def _build_upcoming_appointments(staff_id: str, limit: int = 3) -> List[UpcomingItem]:
    """A doctor's own soonest booked appointments — royan_appointment_slots.
    doctor_id FKs to royan_staff.id (migration 146), an exact match unlike
    the free-text doctor_name column elsewhere in this router."""
    today = dt.date.today().isoformat()
    try:
        slots = (
            db.table(TABLE_APPOINTMENT_SLOTS)
            .select("id,slot_date,slot_time")
            .eq("doctor_id", staff_id)
            .gte("slot_date", today)
            .order("slot_date")
            .limit(200)
            .execute()
        ).data or []
        if not slots:
            return []
        slot_map = {s["id"]: s for s in slots}
        appts = (
            db.table(TABLE_APPOINTMENTS)
            .select("id,slot_id,patient_id,status")
            .in_("slot_id", list(slot_map.keys()))
            .eq("status", "booked")
            .execute()
        ).data or []
        if not appts:
            return []
        patient_ids = list({a["patient_id"] for a in appts if a.get("patient_id")})
        patients = {}
        if patient_ids:
            rows = db.table(TABLE_PATIENTS).select("id,first_name,last_name").in_("id", patient_ids).execute().data or []
            patients = {p["id"]: p for p in rows}

        items = []
        for a in appts:
            slot = slot_map.get(a.get("slot_id")) or {}
            patient = patients.get(a.get("patient_id")) or {}
            name = f"{patient.get('first_name', '')} {patient.get('last_name', '')}".strip() or "Patient"
            items.append((slot.get("slot_date") or "", slot.get("slot_time") or "", name))
        items.sort(key=lambda t: (t[0], t[1]))
        return [
            UpcomingItem(type="appointment", title=f"Appointment with {name}", when=f"{date} {time}".strip())
            for date, time, name in items[:limit]
        ]
    except Exception as exc:
        logger.warning(f"Could not build upcoming appointments for staff {staff_id}: {exc}")
        return []


@router.get("/staff/{user_id}/dashboard", response_model=StaffDashboard)
async def get_staff_dashboard(request: Request, user_id: str):
    # Auth: allow owner or admin/manager
    payload = verify_jwt(request)
    sub = payload.get("sub") or payload.get("user_id")
    roles = set(payload.get("roles") or [])
    if not (sub == user_id or "admin" in roles or "manager" in roles or "management" in roles):
        raise HTTPException(status_code=403, detail="Insufficient role to access dashboard")
    # Build activity feed from ledger (most recent 25)
    ledger = _read_event_ledger_db()
    if ledger is None:
        ledger = await asyncio.to_thread(_read_ledger_items_file)
    activities = []
    pending = []
    for ev in reversed(ledger[-500:]):
        # match created_by or linked_customer_id as quick heuristics
        created_by = ev.get("created_by")
        if created_by == user_id:
            activities.append(ActivityItem(
                event_id=ev.get("event_id"),
                timestamp=ev.get("timestamp"),
                department=ev.get("department"),
                event_type=ev.get("event_type"),
                summary=(ev.get("payload") and ev.get("payload").get("summary")) or ev.get("event_type"),
                payload=ev.get("payload") or {},
            ))
        # collect pending approvals relevant to this user (simple heuristic: department match)
        if ev.get("approval_status") == "pending" and ev.get("department") and created_by != user_id:
            # lightweight; real logic should consult workflow definitions/roles
            pending.append(PendingApproval(
                event_id=ev.get("event_id"),
                event_type=ev.get("event_type"),
                created_by=created_by,
                timestamp=ev.get("timestamp"),
                reason=(ev.get("payload") or {}).get("reason") if isinstance(ev.get("payload"), dict) else None,
            ))

    activities = activities[:25]

    # Tasks assigned to user — merge JSON file + Supabase royan_tasks
    raw_tasks = _read_tasks()
    tasks = []
    seen_task_ids: set = set()
    for t in raw_tasks:
        if str(t.get("assigned_to")) == str(user_id):
            tid = t.get("task_id")
            if tid:
                seen_task_ids.add(str(tid))
            tasks.append(TaskItem(
                task_id=tid or f"json-{len(tasks)}",
                title=t.get("title"),
                description=t.get("description"),
                assigned_to=t.get("assigned_to"),
                status=t.get("status"),
                due_date=t.get("due_date"),
            ))

    # Pull tasks from Supabase royan_tasks table
    try:
        supabase_tasks = (
            db.table("royan_tasks")
            .select("id,title,description,assigned_to,status,priority,due_date")
            .eq("assigned_to", user_id)
            .order("created_at", desc=True)
            .limit(100)
            .execute()
        ).data or []
        for t in supabase_tasks:
            tid = str(t.get("id") or "")
            if tid in seen_task_ids:
                continue  # de-dupe
            seen_task_ids.add(tid)
            tasks.append(TaskItem(
                task_id=tid,
                title=t.get("title") or "Untitled",
                description=t.get("description"),
                assigned_to=t.get("assigned_to"),
                status=t.get("status") or "pending",
                priority=t.get("priority"),
                due_date=str(t.get("due_date")) if t.get("due_date") else None,
            ))
    except Exception as exc:
        logger.warning(f"Could not query royan_tasks for user {user_id}: {exc}")

    assigned_projects: List[AssignedProjectItem] = []
    try:
        project_rows = (
            db.table("royan_projects")
            .select("id,name,status,workflow_stage,activity_type,supplier_name,quality_check_status,nafdac_sampling_status,updated_at")
            .eq("assigned_staff_id", user_id)
            .order("updated_at", desc=True)
            .limit(50)
            .execute()
        ).data or []
        for row in project_rows:
            assigned_projects.append(
                AssignedProjectItem(
                    project_id=str(row.get("id") or ""),
                    name=str(row.get("name") or "Untitled Project"),
                    status=str(row.get("status") or "unknown"),
                    workflow_stage=row.get("workflow_stage"),
                    activity_type=row.get("activity_type"),
                    supplier_name=row.get("supplier_name"),
                    quality_check_status=row.get("quality_check_status"),
                    nafdac_sampling_status=row.get("nafdac_sampling_status"),
                    updated_at=row.get("updated_at"),
                )
            )
    except Exception:
        assigned_projects = []

    # KPIs (example minimal set)
    kpis: List[KPIWidget] = []
    kpis.append(KPIWidget(key="tasks_open", label="Open Tasks", value=sum(1 for t in tasks if t.status != "done")))
    kpis.append(KPIWidget(key="approvals_pending", label="Pending Approvals", value=len(pending)))
    kpis.append(KPIWidget(key="projects_assigned_open", label="Open Assigned Projects", value=sum(1 for p in assigned_projects if p.status not in {"completed", "cancelled"})))

    # Badges (very small rule set)
    badges: List[Badge] = []
    if len([t for t in tasks if t.status == "done"]) >= 10:
        badges.append(Badge(id="task_master", name="Task Master", description="Completed 10+ tasks"))

    # Real identity (not the raw JWT `sub` UUID) — null-safe when the account
    # has no linked royan_staff row, e.g. a bare admin login.
    staff_row = get_staff_by_user_id(user_id)
    identity = None
    upcoming: List[UpcomingItem] = []
    if staff_row:
        identity = StaffIdentity(
            staff_id=str(staff_row["id"]),
            full_name=staff_row.get("full_name") or "Staff Member",
            role=staff_row.get("role"),
            department=staff_row.get("department"),
        )
        if staff_row.get("role") == "doctor":
            upcoming = _build_upcoming_appointments(str(staff_row["id"]))

    if not upcoming:
        # Fall back to (or supplement, for non-doctors) the soonest-due open
        # tasks already fetched above — zero extra backend calls.
        dated = sorted(
            (t for t in tasks if t.due_date and t.status != "done"),
            key=lambda t: t.due_date,
        )
        upcoming = [UpcomingItem(type="task", title=t.title, when=t.due_date) for t in dated[:3]]

    dashboard = StaffDashboard(
        user_id=user_id,
        identity=identity,
        upcoming=upcoming,
        activities=activities,
        pending_approvals=pending[:10],
        tasks=tasks,
        assigned_projects=assigned_projects,
        kpis=kpis,
        badges=badges,
    )

    return dashboard


@router.post("/staff/{user_id}/tasks", status_code=201)
async def create_task(request: Request, user_id: str, task: dict):
    # Auth: only creator or admin/manager can create tasks for a user
    payload = verify_jwt(request)
    sub = payload.get("sub") or payload.get("user_id")
    roles = set(payload.get("roles") or [])
    if not (sub == user_id or "admin" in roles or "manager" in roles or "management" in roles):
        raise HTTPException(status_code=403, detail="Insufficient role to create task")
    tasks = _read_tasks()
    new = {
        "task_id": task.get("task_id") or f"task-{int(dt.datetime.utcnow().timestamp())}",
        "title": task.get("title"),
        "description": task.get("description"),
        "assigned_to": user_id,
        "status": task.get("status") or "open",
        "due_date": task.get("due_date"),
    }
    tasks.append(new)
    _write_tasks(tasks)
    return {"status": "created", "task": new}


@router.put("/staff/{user_id}/tasks/{task_id}")
async def update_task(request: Request, user_id: str, task_id: str, patch: dict):
    payload = verify_jwt(request)
    sub = payload.get("sub") or payload.get("user_id")
    roles = set(payload.get("roles") or [])
    tasks = _read_tasks()
    found = False
    for t in tasks:
        if t.get("task_id") == task_id and str(t.get("assigned_to")) == str(user_id):
            # allow owner or admin/manager
            if not (sub == user_id or "admin" in roles or "manager" in roles or "management" in roles):
                raise HTTPException(status_code=403, detail="Insufficient role to update task")
            t.update(patch)
            found = True
            break
    if not found:
        raise HTTPException(status_code=404, detail="Task not found")
    _write_tasks(tasks)
    return {"status": "updated", "task": t}


@router.delete("/staff/{user_id}/tasks/{task_id}")
async def delete_task(request: Request, user_id: str, task_id: str):
    payload = verify_jwt(request)
    sub = payload.get("sub") or payload.get("user_id")
    roles = set(payload.get("roles") or [])
    tasks = _read_tasks()
    new_tasks = []
    deleted = None
    for t in tasks:
        if t.get("task_id") == task_id and str(t.get("assigned_to")) == str(user_id):
            if not (sub == user_id or "admin" in roles or "manager" in roles or "management" in roles):
                raise HTTPException(status_code=403, detail="Insufficient role to delete task")
            deleted = t
            continue
        new_tasks.append(t)
    if not deleted:
        raise HTTPException(status_code=404, detail="Task not found")
    _write_tasks(new_tasks)
    return {"status": "deleted", "task": deleted}
