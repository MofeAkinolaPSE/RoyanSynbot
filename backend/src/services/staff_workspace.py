"""Staff Workspace: every member of staff's home in Royan.

Spec: backend/docs/Staff-workspace/ (ported from the Placeware build recorded in
IMPLEMENTED.md there, onto Royan's own tables).

One place to start the day and do the work - not a page of hospital metrics:

  My Day      what needs me today: my tasks and reminders, requests waiting on me,
              operational items for my role, the work clock.
  My Work     tasks, reminders and notes I keep for myself or was given
              (to do / in progress / waiting / done), each with a checklist and history.
  Inbox       requests to me or my department, answers to mine, mentions, assignments.
  Team        who is here (online + on the clock), what they are carrying, and
              message / ask / assign in place.
  Progress    my own outcomes - what I finished, on time, requests handled, hours.

Everything a person does is recorded once and read everywhere: completing a task
moves the Progress numbers, clocking out writes the timesheet HR sees, a request
lands in the other person's Inbox, an operational item taken as a task closes
itself when the record is dealt with in its module.

Identity is the login (royan_users). The HR profile (royan_staff) is linked by
user_id (migration 144) and created on first use, so everyone approved on User
Access is on the team and in HR.

Two different "departments" exist in a hospital and both are kept:
  team   who you work with and who a request to "Pharmacy" reaches - derived from
         the canonical staff role (constants.STAFF_ROLES), never typed by hand.
  unit   royan_staff.department: the clinical/administrative unit on the HR
         record (Gynaecology, OPD, ...). Shown, never used for routing.
The API calls the team `department` (it is what requests and tasks are filed
under) and the HR record's department `unit`.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import time
from collections import defaultdict
from typing import Any, Callable, Dict, Iterable, List, Optional
from zoneinfo import ZoneInfo

from src.fin.db import ex, q, q1, tx

TZ = ZoneInfo("Africa/Lagos")

# Teams, in the order a person with several roles is filed (clinical first).
# Keys of DEPT_ROLES are the canonical roles in constants.STAFF_ROLES.
DEPARTMENTS = ["Doctors", "Nursing", "Pharmacy", "Laboratory", "Radiology", "Physiotherapy", "Front Desk",
               "Billing", "HMO", "Stores", "Finance", "Audit", "HR", "Operations", "Quality", "Management", "Admin"]
DEPT_ROLES: Dict[str, set] = {
    "Doctors": {"doctor"}, "Nursing": {"nurse"}, "Pharmacy": {"pharmacist"}, "Laboratory": {"lab"},
    "Radiology": {"radiology"}, "Physiotherapy": {"physiotherapist"}, "Front Desk": {"receptionist"},
    "Billing": {"cashier"}, "HMO": {"hmo"}, "Stores": {"store"}, "Audit": {"auditor"},
    "Finance": {"finance"}, "HR": {"hr"}, "Operations": {"ops"}, "Quality": {"quality_assurance"},
    "Management": {"management"}, "Admin": {"admin"},
}
MANAGER_ROLES = {"admin", "management", "hr"}
CLINICAL_ROLES = {"doctor", "nurse", "pharmacist", "lab", "radiology", "physiotherapist"}
PRIORITIES = ("low", "medium", "high", "critical")
OPEN_STATUSES = ("pending", "in_progress", "waiting", "blocked")
DONE_STATUSES = ("completed", "done")     # 'done' is written by the older calendar/task screens
TRANSITIONS = {
    "pending": {"in_progress", "waiting", "completed", "cancelled"},
    "in_progress": {"pending", "waiting", "completed", "cancelled"},
    "waiting": {"in_progress", "pending", "completed", "cancelled"},
    "blocked": {"in_progress", "pending", "completed", "cancelled"},
    "completed": {"pending"},     # reopen
    "done": {"pending"},
    "cancelled": {"pending"},
}
STATUS_LABEL = {"pending": "to do", "in_progress": "in progress", "waiting": "waiting", "completed": "done",
                "done": "done", "cancelled": "cancelled", "blocked": "blocked"}


def norm_priority(p: Any) -> str:
    """The older task screens say 'urgent' where the workspace says 'critical'."""
    p = str(p or "medium").lower()
    p = "critical" if p == "urgent" else p
    if p not in PRIORITIES:
        raise ValueError("Unknown priority")
    return p


class WorkspaceError(ValueError):
    """A request that cannot be carried out as asked (409)."""


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def today() -> dt.date:
    return now().astimezone(TZ).date()


def week_start(d: Optional[dt.date] = None) -> dt.date:
    d = d or today()
    return d - dt.timedelta(days=d.weekday())


def local_midnight(d: dt.date) -> dt.datetime:
    return dt.datetime.combine(d, dt.time(), TZ)


def _is_uuid(v: Any) -> bool:
    return bool(re.fullmatch(r"[0-9a-fA-F-]{36}", str(v or "")))


def _me(user: Dict[str, Any]) -> str:
    sub = str(user.get("sub") or "")
    if not _is_uuid(sub):
        raise PermissionError("Sign in with a staff account to use the workspace")
    return sub


def _roles(user: Dict[str, Any]) -> set:
    return {str(r).lower() for r in (user.get("roles") or [])}


def _dt(v: Any) -> Optional[dt.datetime]:
    """Parse a date or datetime from the browser. A bare date means end of that working day."""
    if v in (None, ""):
        return None
    if isinstance(v, dt.datetime):
        return v if v.tzinfo else v.replace(tzinfo=TZ)
    s = str(v).strip()
    if len(s) == 10:
        return dt.datetime.combine(dt.date.fromisoformat(s), dt.time(17, 0), TZ)
    d = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    return d if d.tzinfo else d.replace(tzinfo=TZ)


def name_from_email(email: str) -> str:
    local = (email or "").split("@")[0]
    parts = [p for p in re.split(r"[._-]+", local) if p and not p.isdigit()]
    return " ".join(p.capitalize() for p in parts) if parts else (email or "Team member")


def dept_for_roles(roles: Iterable[str]) -> str:
    """The team for a set of roles: the first match in DEPARTMENTS order (clinical first)."""
    rs = {str(r).lower() for r in roles or []}
    for dept in DEPARTMENTS:
        if rs & DEPT_ROLES[dept]:
            return dept
    return "Operations"


def fmt_hours(seconds: float) -> str:
    m = int(round(seconds / 60))
    return f"{m // 60}h {m % 60:02d}m"


def journal(conn, user_id: str, kind: str, summary: str, entity_type: Optional[str] = None, entity_id: Optional[str] = None) -> None:
    ex(conn, """INSERT INTO staff_work_events (user_id, kind, summary, entity_type, entity_id) VALUES (%s, %s, %s, %s, %s)""",
       (user_id, kind, summary[:300], entity_type, entity_id))


def notify(conn, user_ids: Iterable[Optional[str]], kind: str, level: str, title: str, body: Optional[str] = None,
           link_type: Optional[str] = None, link_id: Optional[str] = None, actor: Optional[str] = None) -> int:
    n = 0
    for uid in {str(u) for u in user_ids if u and _is_uuid(u)}:
        if actor and uid == str(actor):
            continue
        ex(conn, """INSERT INTO staff_notifications (user_id, kind, level, title, body, link_type, link_id, actor)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
           (uid, kind, level, title[:300], (body or "")[:1000] or None, link_type, link_id, actor))
        n += 1
    return n


# ---------------------------------------------------------------------------
# People (login + HR profile)
# ---------------------------------------------------------------------------

# Everyone with a login, plus HR records that have no login yet (most doctors
# imported from Hope). Quarantined rows (migration 141) are never people.
_PEOPLE_SQL = """
    SELECT u.id::text AS user_id, u.email, u.roles, u.is_active, u.created_at AS joined_at,
           s.id::text AS staff_id, s.full_name, s.role AS staff_role, s.department AS unit, s.designation AS job_title,
           s.phone, s.is_active AS staff_active, s.weekly_hours, s.joined_at AS start_date, s.staff_number,
           s.employment_type, s.monthly_gross, s.specialty
    FROM royan_users u LEFT JOIN royan_staff s ON s.user_id = u.id AND s.quarantined_at IS NULL
    UNION ALL
    SELECT NULL, s.email, NULL, NULL, s.created_at, s.id::text, s.full_name, s.role, s.department, s.designation,
           s.phone, s.is_active, s.weekly_hours, s.joined_at, s.staff_number, s.employment_type, s.monthly_gross, s.specialty
    FROM royan_staff s WHERE s.user_id IS NULL AND s.quarantined_at IS NULL
"""


def _person(r: Dict[str, Any], on_leave: Optional[set] = None) -> Dict[str, Any]:
    roles = list(r.get("roles") or [])
    has_login = r["user_id"] is not None
    email = r.get("email") or ""
    placeholder = email.endswith("@placeholder.local")
    # the HR record's canonical role wins; a login without one is filed by its JWT roles
    team_roles = [r["staff_role"]] if r.get("staff_role") else roles
    return {
        "key": r["user_id"] or f"staff:{r['staff_id']}",
        "user_id": r["user_id"], "staff_id": r["staff_id"], "has_login": has_login,
        "name": r.get("full_name") or name_from_email(email),
        "email": None if placeholder else (email or None),
        "roles": roles, "staff_role": r.get("staff_role"),
        "department": dept_for_roles(team_roles),
        "unit": r.get("unit"),
        "job_title": r.get("job_title"), "phone": r.get("phone"), "staff_number": r.get("staff_number"),
        "specialty": r.get("specialty"), "employment_type": r.get("employment_type"),
        "monthly_gross": float(r["monthly_gross"]) if r.get("monthly_gross") is not None else None,
        "weekly_hours": float(r["weekly_hours"]) if r.get("weekly_hours") is not None else 40.0,
        "start_date": r.get("start_date"),
        "active": bool(r["is_active"]) if has_login else bool(r.get("staff_active", True)),
        "profile": r["staff_id"] is not None,
        "on_leave": bool(on_leave and r["staff_id"] in on_leave),
        "joined_at": r.get("joined_at"),
    }


def _on_leave_today(conn) -> set:
    return {r["staff_id"] for r in q(conn, """SELECT DISTINCT staff_id::text AS staff_id FROM royan_leave_requests
                                             WHERE status='approved' AND %s BETWEEN start_date AND end_date""", (today(),))}


def people(conn, include_inactive: bool = False) -> List[Dict[str, Any]]:
    leave = _on_leave_today(conn)
    out = [_person(r, leave) for r in q(conn, _PEOPLE_SQL)]
    if not include_inactive:
        out = [p for p in out if p["active"]]
    return sorted(out, key=lambda p: p["name"].lower())


def person_map(conn) -> Dict[str, Dict[str, Any]]:
    return {p["key"]: p for p in people(conn, include_inactive=True)}


def ensure_profile(conn, user_id: str) -> str:
    """The HR profile (royan_staff.id) for a login - linked by email if HR already
    added them, created otherwise, so a login can always clock in and be in HR."""
    r = q1(conn, "SELECT id::text AS staff_id FROM royan_staff WHERE user_id=%s AND quarantined_at IS NULL", (user_id,))
    if r:
        return r["staff_id"]
    u = q1(conn, "SELECT email, roles FROM royan_users WHERE id=%s", (user_id,))
    if not u:
        raise LookupError("User not found")
    r = q1(conn, """UPDATE royan_staff SET user_id=%s, updated_at=now()
                    WHERE lower(email)=lower(%s) AND user_id IS NULL AND quarantined_at IS NULL
                    RETURNING id::text AS staff_id""", (user_id, u["email"]))
    if r:
        return r["staff_id"]
    from src.constants import STAFF_ROLES
    role = next((x for x in (u["roles"] or []) if x in STAFF_ROLES), None)
    team = dept_for_roles(u["roles"])
    # same staff-number scheme as GET /staff/me/ensure-profile, made unique with the login id
    r = q1(conn, """INSERT INTO royan_staff (staff_number, full_name, email, department, designation, role, user_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id::text AS staff_id""",
           (f"SELF-{u['email'].split('@')[0].upper()}-{user_id[:4].upper()}", name_from_email(u["email"]),
            u["email"].lower(), team, "Doctor" if team == "Doctors" else "Staff", role, user_id))
    return r["staff_id"]


def online_ids() -> set:
    """Logins with a live socket (royan_presence_sessions, kept by the realtime hub)."""
    try:
        from src.constants import PRESENCE_STALE_SECONDS
        with tx() as conn:
            return {r["u"] for r in q(conn, """SELECT DISTINCT user_id::text AS u FROM royan_presence_sessions
                                               WHERE last_seen_at > now() - make_interval(secs => %s)""",
                                      (PRESENCE_STALE_SECONDS,))}
    except Exception:
        return set()


def _names(conn, ids: Iterable[Any]) -> Dict[str, str]:
    pm = person_map(conn)
    return {str(i): (pm[str(i)]["name"] if str(i) in pm else "Someone") for i in ids if i}


def _dept_members(conn, dept: str) -> List[str]:
    return [p["user_id"] for p in people(conn) if p["user_id"] and p["department"] == dept]


# ---------------------------------------------------------------------------
# Time clock -> timesheets
# ---------------------------------------------------------------------------

def _session_row(conn, user_id: str, lock: bool = False) -> Optional[Dict[str, Any]]:
    return q1(conn, f"""SELECT id::text AS id, user_id::text AS user_id, started_at, break_seconds, break_started_at, breaks,
                               department, note FROM staff_time_sessions WHERE user_id=%s AND ended_at IS NULL
                        {'FOR UPDATE' if lock else ''}""", (user_id,))


def _worked_seconds(s: Dict[str, Any], at: Optional[dt.datetime] = None) -> float:
    at = at or now()
    brk = s["break_seconds"] + ((at - s["break_started_at"]).total_seconds() if s.get("break_started_at") else 0)
    return max(0.0, (at - s["started_at"]).total_seconds() - brk)


def clock_view(conn, user_id: str) -> Dict[str, Any]:
    s = _session_row(conn, user_id)
    t0 = local_midnight(today())
    saved_today = q1(conn, """SELECT COALESCE(SUM(hours_worked),0) AS h FROM royan_timesheets
                              WHERE user_id=%s AND date=%s AND status<>'rejected'""", (user_id, today()))["h"]
    ws = week_start()
    saved_week = q1(conn, """SELECT COALESCE(SUM(hours_worked),0) AS h FROM royan_timesheets
                             WHERE user_id=%s AND date BETWEEN %s AND %s AND status<>'rejected'""",
                    (user_id, ws, ws + dt.timedelta(days=6)))["h"]
    live = 0.0
    live_today = 0.0
    if s:
        live = _worked_seconds(s)
        # only the part of a running clock that falls today counts towards today
        live_today = live if s["started_at"] >= t0 else max(0.0, live - _worked_seconds(s, t0))
    return {
        "status": "off" if not s else ("break" if s["break_started_at"] else "working"),
        "session": None if not s else {
            "id": s["id"], "started_at": s["started_at"], "break_started_at": s["break_started_at"],
            "break_seconds": s["break_seconds"] + (int((now() - s["break_started_at"]).total_seconds()) if s["break_started_at"] else 0),
            "breaks": s["breaks"], "department": s["department"], "note": s["note"],
            "worked_seconds": int(live), "running_hours": round((now() - s["started_at"]).total_seconds() / 3600, 2),
        },
        "today_seconds": int(float(saved_today) * 3600 + live_today),
        "week_seconds": int(float(saved_week) * 3600 + live),
        "server_time": now(),
    }


def clock_start(user: Dict[str, Any], data: Dict[str, Any]) -> Dict[str, Any]:
    me = _me(user)
    with tx() as conn:
        staff_id = ensure_profile(conn, me)
        if _session_row(conn, me, lock=True):
            raise WorkspaceError("You are already clocked in")
        dept = data.get("department") if data.get("department") in DEPARTMENTS else _my_dept(conn, me)
        ex(conn, """INSERT INTO staff_time_sessions (user_id, staff_id, department, note) VALUES (%s, %s, %s, %s)""",
           (me, staff_id, dept, (data.get("note") or "").strip() or None))
        journal(conn, me, "clock_in", "Started work")
        return clock_view(conn, me)


def clock_break(user: Dict[str, Any], resume: bool = False) -> Dict[str, Any]:
    me = _me(user)
    with tx() as conn:
        s = _session_row(conn, me, lock=True)
        if not s:
            raise WorkspaceError("You are not clocked in")
        if resume:
            if not s["break_started_at"]:
                raise WorkspaceError("You are not on a break")
            ex(conn, """UPDATE staff_time_sessions SET break_seconds = break_seconds + EXTRACT(EPOCH FROM now()-break_started_at)::int,
                               break_started_at=NULL WHERE id=%s""", (s["id"],))
            journal(conn, me, "resume", "Back from break")
        else:
            if s["break_started_at"]:
                raise WorkspaceError("You are already on a break")
            ex(conn, "UPDATE staff_time_sessions SET break_started_at=now(), breaks=breaks+1 WHERE id=%s", (s["id"],))
            journal(conn, me, "break", "Took a break")
        return clock_view(conn, me)


def _split_by_day(start: dt.datetime, end: dt.datetime, worked: float) -> List[tuple]:
    """(local date, hours, segment start, segment end) for a session, split at local
    midnight; breaks shared out pro rata. A night shift is two days' timesheets."""
    gross = (end - start).total_seconds()
    parts, cur = [], start
    while cur < end:
        nxt = min(end, local_midnight(cur.astimezone(TZ).date() + dt.timedelta(days=1)))
        parts.append((cur.astimezone(TZ).date(), (nxt - cur).total_seconds(), cur, nxt))
        cur = nxt
    ratio = worked / gross if gross else 0
    return [(d, round(sec * ratio / 3600, 2), a, b) for d, sec, a, b in parts if round(sec * ratio / 3600, 2) > 0]


def _shift_kind(started: dt.datetime) -> str:
    """royan_timesheets.shift (day / night), from when the work began - never asked of staff."""
    return "day" if 7 <= started.astimezone(TZ).hour < 19 else "night"


def clock_stop(user: Dict[str, Any], data: Dict[str, Any]) -> Dict[str, Any]:
    """Clock out: close the session and write it to the timesheet HR reviews."""
    me = _me(user)
    with tx() as conn:
        s = _session_row(conn, me, lock=True)
        if not s:
            raise WorkspaceError("You are not clocked in")
        end = _dt(data.get("ended_at")) or now()
        if end > now() + dt.timedelta(minutes=1) or end <= s["started_at"]:
            raise WorkspaceError("The finish time must be after you started and not in the future")
        if (end - s["started_at"]) > dt.timedelta(hours=16) and not data.get("ended_at"):
            raise WorkspaceError("NEEDS_END_TIME: This clock has been running for more than 16 hours. "
                                 "Enter the time you actually finished.")
        if s["break_started_at"]:
            s["break_seconds"] += max(0, int((end - s["break_started_at"]).total_seconds()))
            s["break_started_at"] = None
        worked = _worked_seconds(s, end)
        note = (data.get("note") or s["note"] or "").strip() or None
        staff_id = ensure_profile(conn, me)
        ids = []
        shift = _shift_kind(s["started_at"])
        for d, hours, a, b in _split_by_day(s["started_at"], end, worked):
            r = q1(conn, """INSERT INTO royan_timesheets (staff_id, user_id, date, shift, clock_in, clock_out, hours_worked,
                                                          department, notes, recorded_by, source, session_id, status)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'clock', %s, 'submitted') RETURNING id::text AS id""",
                   (staff_id, me, d, shift, a.astimezone(TZ).time().replace(microsecond=0),
                    b.astimezone(TZ).time().replace(microsecond=0), min(hours, 24), s["department"] or _my_dept(conn, me),
                    note, me, s["id"]))
            ids.append(r["id"])
        ex(conn, """UPDATE staff_time_sessions SET ended_at=%s, break_seconds=%s, break_started_at=NULL, note=%s, timesheet_id=%s
                    WHERE id=%s""", (end, s["break_seconds"], note, ids[0] if ids else None, s["id"]))
        journal(conn, me, "clock_out", f"Finished work · {fmt_hours(worked)} recorded" if ids else "Finished work (under a minute, nothing recorded)")
        view = clock_view(conn, me)
        view["recorded_hours"] = round(worked / 3600, 2) if ids else 0
        view["timesheet_ids"] = ids
    refresh_rules("hr.timesheets", "hr.long_clocks")
    return view


def clock_discard(user: Dict[str, Any]) -> Dict[str, Any]:
    """Throw away a running clock that should never have started. Nothing reaches the timesheet."""
    me = _me(user)
    with tx() as conn:
        s = _session_row(conn, me, lock=True)
        if not s:
            raise WorkspaceError("You are not clocked in")
        ex(conn, "DELETE FROM staff_time_sessions WHERE id=%s AND ended_at IS NULL", (s["id"],))
        journal(conn, me, "clock_cancelled", "Clock-in cancelled (no time recorded)")
        return clock_view(conn, me)


def my_time(user: Dict[str, Any]) -> Dict[str, Any]:
    me = _me(user)
    ws = week_start()
    with tx() as conn:
        view = clock_view(conn, me)
        rows = q(conn, """SELECT id::text AS id, date, hours_worked, department, notes AS activity_note, source, status, review_note
                          FROM royan_timesheets WHERE user_id=%s AND date >= %s ORDER BY date DESC, created_at DESC""",
                 (me, ws - dt.timedelta(days=28)))
        sessions = q(conn, """SELECT id::text AS id, started_at, ended_at, break_seconds, breaks, note FROM staff_time_sessions
                              WHERE user_id=%s ORDER BY started_at DESC LIMIT 15""", (me,))
    days = []
    for i in range(7):
        d = ws + dt.timedelta(days=i)
        h = sum(float(r["hours_worked"]) for r in rows if r["date"] == d and r["status"] != "rejected")
        if d == today() and view["session"]:
            h += view["today_seconds"] / 3600 - sum(float(r["hours_worked"]) for r in rows if r["date"] == d and r["status"] != "rejected")
        days.append({"date": d, "hours": round(h, 2), "today": d == today()})
    weeks = []
    for w in range(4, -1, -1):
        s0 = ws - dt.timedelta(days=7 * w)
        weeks.append({"week": s0, "hours": round(sum(float(r["hours_worked"]) for r in rows
                                                      if s0 <= r["date"] <= s0 + dt.timedelta(days=6) and r["status"] != "rejected"), 2)})
    weeks[-1]["hours"] = round(view["week_seconds"] / 3600, 2)
    for s in sessions:
        end = s["ended_at"] or now()
        s["worked_seconds"] = int(max(0, (end - s["started_at"]).total_seconds() - s["break_seconds"]))
    return {**view, "days": days, "weeks": weeks, "entries": rows[:40], "sessions": sessions}


# ---------------------------------------------------------------------------
# Tasks, reminders and notes
# ---------------------------------------------------------------------------

_TASK_COLS = """t.id::text AS id, t.title, t.description, t.kind, t.status, t.priority, t.due_date, t.reminder_at,
    t.assigned_to::text AS assigned_to, t.created_by::text AS created_by, t.source, t.source_ref, t.department,
    t.entity_type, t.entity_id, t.entity_label, t.link, t.checklist, t.waiting_on, t.started_at, t.completed_at,
    t.completed_by::text AS completed_by, t.created_at, t.updated_at, t.request_id::text AS request_id,
    t.recurrence, t.recurrence_until, t.series_id::text AS series_id, t.escalation_level, t.escalated_to, t.escalated_at,
    (SELECT COUNT(*) FROM staff_task_activity a WHERE a.task_id=t.id AND a.kind='comment') AS comments"""


def _decorate(rows: List[Dict[str, Any]], names: Dict[str, str]) -> List[Dict[str, Any]]:
    t0, t1 = local_midnight(today()), local_midnight(today() + dt.timedelta(days=1))
    for r in rows:
        when = r["due_date"] or r["reminder_at"]
        r["when"] = when
        open_ = r["status"] in OPEN_STATUSES
        r["overdue"] = bool(open_ and when and when < now())   # past its due time, not just its day
        r["due_today"] = bool(open_ and when and t0 <= when < t1)
        r["assigned_to_name"] = names.get(r["assigned_to"]) if r["assigned_to"] else None
        r["created_by_name"] = names.get(r["created_by"]) if r["created_by"] else None
        if "recurrence" in r:
            from src.services.workspace_automation import describe
            r["recurrence_label"] = describe(r["recurrence"])
            # escalated beyond the owner's own reminder
            r["escalated"] = bool(open_ and r.get("escalated_to") in ("giver", "management"))
        cl = r["checklist"] if isinstance(r["checklist"], list) else []
        r["checklist"] = cl
        r["checklist_done"] = sum(1 for c in cl if c.get("done"))
    return rows


def _task(conn, task_id: str) -> Dict[str, Any]:
    t = q1(conn, f"SELECT {_TASK_COLS} FROM royan_tasks t WHERE t.id=%s::uuid", (task_id,)) if _is_uuid(task_id) else None
    if not t:
        raise LookupError("Task not found")
    return t


def _can_see(user: Dict[str, Any], t: Dict[str, Any]) -> bool:
    me = str(user.get("sub"))
    return me in (t["assigned_to"], t["created_by"]) or bool(_roles(user) & MANAGER_ROLES)


def _activity(conn, task_id: str, actor: Optional[str], kind: str, body: Optional[str] = None) -> None:
    ex(conn, "INSERT INTO staff_task_activity (task_id, actor, kind, body) VALUES (%s, %s, %s, %s)", (task_id, actor, kind, body))


def list_tasks(user: Dict[str, Any]) -> Dict[str, Any]:
    me = _me(user)
    with tx() as conn:
        mine = q(conn, f"""SELECT {_TASK_COLS} FROM royan_tasks t
                           WHERE (t.assigned_to=%s OR (t.assigned_to IS NULL AND t.created_by=%s))
                             AND (t.status IN %s OR (t.status='completed' AND t.completed_at > now() - interval '30 days'))
                           ORDER BY t.completed_at DESC NULLS FIRST, COALESCE(t.due_date, t.reminder_at) NULLS LAST, t.created_at DESC""",
                 (me, me, OPEN_STATUSES))
        delegated = q(conn, f"""SELECT {_TASK_COLS} FROM royan_tasks t
                                WHERE t.created_by=%s AND t.assigned_to IS NOT NULL AND t.assigned_to<>%s
                                  AND (t.status IN %s OR t.completed_at > now() - interval '7 days')
                                ORDER BY t.created_at DESC""", (me, me, OPEN_STATUSES))
        names = _names(conn, [r["assigned_to"] for r in mine + delegated] + [r["created_by"] for r in mine + delegated])
    mine = _decorate(mine, names)
    return {"open": [t for t in mine if t["status"] in OPEN_STATUSES],
            "completed": [t for t in mine if t["status"] == "completed"],
            "delegated": _decorate(delegated, names)}


def _checklist(v: Any) -> List[Dict[str, Any]]:
    out = []
    for c in v or []:
        if isinstance(c, str) and c.strip():
            out.append({"text": c.strip()[:200], "done": False})
        elif isinstance(c, dict) and str(c.get("text") or "").strip():
            out.append({"text": str(c["text"]).strip()[:200], "done": bool(c.get("done"))})
    return out


def create_task(user: Dict[str, Any], data: Dict[str, Any], conn=None, source: Optional[str] = None) -> Dict[str, Any]:
    me = _me(user)
    title = (data.get("title") or "").strip()
    if not title:
        raise ValueError("Say what needs to be done")
    kind = data.get("kind") or "task"
    if kind not in ("task", "reminder", "note"):
        raise ValueError("Unknown kind")
    assignee = data.get("assigned_to") or me
    if not _is_uuid(assignee):
        raise ValueError("Choose who the task is for")
    priority = norm_priority(data.get("priority"))
    due = _dt(data.get("due_at") or data.get("due_date"))
    remind = _dt(data.get("reminder_at")) or (due if kind == "reminder" else None)
    src = source or ("assigned" if assignee != me else "manual")
    from src.services.workspace_automation import describe, validate_rule
    rule = validate_rule(data.get("recurrence"))
    if rule and kind == "note":
        raise ValueError("Notes do not repeat - make it a task or a reminder")
    if rule and not (due or remind):
        raise ValueError("A repeating task needs a first date")
    until = dt.date.fromisoformat(str(data["recurrence_until"])[:10]) if data.get("recurrence_until") else None

    def run(c):
        if not q1(c, "SELECT 1 FROM royan_users WHERE id=%s AND is_active", (assignee,)):
            raise ValueError("That person is not an active user")
        dept = data.get("department") or next((p["department"] for p in people(c) if p["user_id"] == assignee), None)
        t = q1(c, """INSERT INTO royan_tasks (title, description, kind, status, priority, due_date, reminder_at, assigned_to,
                                                   created_by, source, source_ref, department, entity_type, entity_id, entity_label,
                                                   link, checklist, request_id)
                     VALUES (%s, %s, %s, 'pending', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)
                     RETURNING id::text AS id""",
                 (title[:300], (data.get("description") or "").strip() or None, kind, priority, due, remind, assignee, me, src,
                  data.get("source_ref"), dept, data.get("entity_type"), data.get("entity_id"), data.get("entity_label"),
                  data.get("link"), json.dumps(_checklist(data.get("checklist"))), data.get("request_id")))
        if rule:
            ex(c, "UPDATE royan_tasks SET recurrence=%s, recurrence_until=%s, series_id=id WHERE id=%s::uuid", (rule, until, t["id"]))
        _activity(c, t["id"], me, "created", {"note": "Note added", "reminder": "Reminder set"}.get(kind, "Task created")
                  + (f" · repeats {describe(rule)}" if rule else ""))
        if assignee != me:
            who = _names(c, [me])[me]
            _activity(c, t["id"], me, "assigned", f"Assigned to {_names(c, [assignee])[assignee]}")
            notify(c, [assignee], "assigned", "action", f"{who} gave you a task: {title[:120]}",
                   (data.get("description") or "")[:300], "task", t["id"], me)
        journal(c, me, "task_created", f"{'Assigned' if assignee != me else 'Added'} {kind}: {title[:120]}", "task", t["id"])
        return _decorate([_task(c, t["id"])], _names(c, [assignee, me]))[0]

    if conn is not None:
        return run(conn)
    with tx() as c:
        return run(c)


def get_task(user: Dict[str, Any], task_id: str) -> Dict[str, Any]:
    with tx() as conn:
        t = _task(conn, task_id)
        if not _can_see(user, t):
            raise PermissionError("This task belongs to someone else")
        act = q(conn, """SELECT id, actor::text AS actor, kind, body, created_at FROM staff_task_activity
                         WHERE task_id=%s::uuid ORDER BY created_at, id""", (task_id,))
        req = q(conn, """SELECT id::text AS id, subject, kind, status, to_user::text AS to_user, to_department, response, created_at
                         FROM staff_requests WHERE task_id=%s::uuid OR work_task_id=%s::uuid ORDER BY created_at""", (task_id, task_id))
        names = _names(conn, [a["actor"] for a in act] + [t["assigned_to"], t["created_by"]] + [r["to_user"] for r in req])
    for a in act:
        a["actor_name"] = names.get(a["actor"]) if a["actor"] else "Synbot"
    for r in req:
        r["to"] = names.get(r["to_user"]) if r["to_user"] else f"{r['to_department']} team"
    t = _decorate([t], names)[0]
    return {**t, "activity": act, "requests": req, "transitions": sorted(TRANSITIONS.get(t["status"], set()))}


def update_task(user: Dict[str, Any], task_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    me = _me(user)
    with tx() as conn:
        t = _task(conn, task_id)
        if not _can_see(user, t):
            raise PermissionError("This task belongs to someone else")
        sets, vals, notes = [], [], []
        for f in ("title", "description", "priority", "department"):
            if f in data and data[f] != t[f]:
                if f == "title" and not str(data[f] or "").strip():
                    raise ValueError("A task needs a title")
                v = norm_priority(data[f]) if f == "priority" else data[f]
                sets.append(f"{f}=%s"); vals.append(v); notes.append(f)
        if "due_at" in data:
            sets.append("due_date=%s"); vals.append(_dt(data["due_at"]))
            notes.append("due date")
            if t["kind"] == "reminder":
                sets.append("reminder_at=%s"); vals.append(_dt(data["due_at"]))
            # a new due date starts the escalation chain again
            sets.append("escalation_level=0"); sets.append("escalated_to=NULL")
        if "recurrence" in data:
            from src.services.workspace_automation import describe, validate_rule
            rule = validate_rule(data["recurrence"])
            if rule and not (t["due_date"] or t["reminder_at"] or data.get("due_at")):
                raise ValueError("Give the task a date before making it repeat")
            sets.append("recurrence=%s"); vals.append(rule)
            sets.append("series_id=COALESCE(series_id, id)")
            _activity(conn, task_id, me, "recurrence", f"Repeats {describe(rule)}" if rule else "Stopped repeating")
        if "recurrence_until" in data:
            sets.append("recurrence_until=%s")
            vals.append(dt.date.fromisoformat(str(data["recurrence_until"])[:10]) if data["recurrence_until"] else None)
        if "checklist" in data:
            new = _checklist(data["checklist"])
            done_now = [c["text"] for c in new if c["done"] and not any(o.get("text") == c["text"] and o.get("done") for o in t["checklist"] or [])]
            sets.append("checklist=%s::jsonb"); vals.append(json.dumps(new))
            for d in done_now:
                _activity(conn, task_id, me, "checklist", f"Ticked: {d}")
        if data.get("assigned_to") and data["assigned_to"] != t["assigned_to"]:
            if not _is_uuid(data["assigned_to"]) or not q1(conn, "SELECT 1 FROM royan_users WHERE id=%s AND is_active", (data["assigned_to"],)):
                raise ValueError("That person is not an active user")
            sets.append("assigned_to=%s"); vals.append(data["assigned_to"])
            nm = _names(conn, [data["assigned_to"], me])
            _activity(conn, task_id, me, "assigned", f"Handed to {nm[data['assigned_to']]}")
            notify(conn, [data["assigned_to"]], "assigned", "action", f"{nm[me]} handed you a task: {t['title'][:120]}",
                   None, "task", task_id, me)
        if sets:
            ex(conn, f"UPDATE royan_tasks SET {', '.join(sets)}, updated_at=now() WHERE id=%s::uuid", (*vals, task_id))
            if notes:
                _activity(conn, task_id, me, "updated", "Changed " + ", ".join(dict.fromkeys(notes)))
    return get_task(user, task_id)


def set_status(user: Dict[str, Any], task_id: str, status: str, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    me = _me(user)
    data = data or {}
    with tx() as conn:
        t = _task(conn, task_id)
        if not _can_see(user, t):
            raise PermissionError("This task belongs to someone else")
        _apply_status(conn, t, status, me, data.get("note"), data.get("waiting_on"))
    return get_task(user, task_id)


def _apply_status(conn, t: Dict[str, Any], status: str, actor: str, note: Optional[str] = None,
                  waiting_on: Optional[str] = None, system: bool = False) -> None:
    cur = t["status"]
    if status == cur:
        return
    if status not in TRANSITIONS.get(cur, set()):
        raise WorkspaceError(f"A task that is {STATUS_LABEL.get(cur, cur)} cannot be moved to {STATUS_LABEL.get(status, status)}")
    if status == "waiting" and not (waiting_on or "").strip():
        raise ValueError("Say who or what you are waiting for")
    ex(conn, """UPDATE royan_tasks SET status=%s, updated_at=now(),
                       started_at = CASE WHEN %s='in_progress' THEN COALESCE(started_at, now()) ELSE started_at END,
                       completed_at = CASE WHEN %s='completed' THEN now() WHEN %s IN ('pending','in_progress') THEN NULL ELSE completed_at END,
                       completed_by = CASE WHEN %s='completed' THEN %s WHEN %s IN ('pending','in_progress') THEN NULL ELSE completed_by END,
                       waiting_on = CASE WHEN %s='waiting' THEN %s ELSE NULL END
                WHERE id=%s::uuid""",
       (status, status, status, status, status, t["assigned_to"] if system else actor, status, status, waiting_on, t["id"]))
    label = {"in_progress": "Started", "waiting": f"Waiting on {waiting_on}", "completed": "Completed",
             "cancelled": "Cancelled", "pending": "Reopened" if cur in ("completed", "cancelled") else "Back to to-do"}[status]
    _activity(conn, t["id"], None if system else actor, "resolved" if system else "status", label + (f" - {note}" if note else ""))
    if status == "pending" and cur in ("completed", "cancelled"):
        ex(conn, "UPDATE royan_tasks SET escalation_level=0, escalated_to=NULL WHERE id=%s::uuid", (t["id"],))
    if status in ("completed", "cancelled"):
        # a repeating task: finishing or skipping this one schedules the next
        from src.services.workspace_automation import schedule_next
        schedule_next(conn, t, actor)
    owner = t["assigned_to"] or t["created_by"]
    if status == "completed":
        journal(conn, owner, "task_completed", f"Completed: {t['title'][:150]}", "task", t["id"])
        if t["created_by"] and t["created_by"] != owner:
            who = _names(conn, [owner])[owner]
            notify(conn, [t["created_by"]], "completed", "info", f"{who} completed: {t['title'][:120]}", note, "task", t["id"], actor)
        if t["request_id"]:
            r = q1(conn, "SELECT id::text AS id, from_user::text AS from_user, status FROM staff_requests WHERE id=%s::uuid", (t["request_id"],))
            if r and r["status"] not in ("responded", "closed", "declined"):
                ex(conn, """UPDATE staff_requests SET status='responded', response=COALESCE(%s, 'Done'), responded_by=%s,
                                   responded_at=now(), updated_at=now() WHERE id=%s::uuid""", (note, owner, r["id"]))
                notify(conn, [r["from_user"]], "response", "action", f"Done: {t['title'][:120]}", note, "request", r["id"], owner)
    elif status == "in_progress" and not system:
        journal(conn, actor, "task_started", f"Started: {t['title'][:150]}", "task", t["id"])


def comment(user: Dict[str, Any], task_id: str, body: str) -> Dict[str, Any]:
    me = _me(user)
    body = (body or "").strip()
    if not body:
        raise ValueError("Write a comment")
    with tx() as conn:
        t = _task(conn, task_id)
        if not _can_see(user, t):
            raise PermissionError("This task belongs to someone else")
        _activity(conn, task_id, me, "comment", body[:2000])
        who = _names(conn, [me])[me]
        others = {t["assigned_to"], t["created_by"]} - {me, None}
        notify(conn, others, "comment", "social", f"{who} commented on: {t['title'][:100]}", body[:300], "task", task_id, me)
        mentioned = _mentions(conn, body) - others
        notify(conn, mentioned, "mention", "social", f"{who} mentioned you on: {t['title'][:100]}", body[:300], "task", task_id, me)
    return get_task(user, task_id)


def _mentions(conn, text: str) -> set:
    tags = {m.lower() for m in re.findall(r"@([A-Za-z][\w.-]{1,40})", text or "")}
    if not tags:
        return set()
    out = set()
    for p in people(conn):
        if not p["user_id"]:
            continue
        first = p["name"].split()[0].lower()
        local = (p["email"] or "").split("@")[0].lower()
        if first in tags or local in tags or p["name"].replace(" ", "").lower() in tags:
            out.add(p["user_id"])
    return out


# ---------------------------------------------------------------------------
# Operational items: business conditions that need a person, by role
# ---------------------------------------------------------------------------
# Each rule reads a module's live records and returns the items that need someone.
# Nothing is created until a person takes one ("Take it" -> a task linked to the
# record). A taken task closes itself once the record is dealt with in its module,
# so the work is counted where it was actually done.

# Hospital rules (study4: "Business Event -> Decision -> Human Action -> Escalation").
# Every rule reads native records only (external_source IS NULL): Hope's history
# holds tens of thousands of rows still marked 'ordered' or 'pending' from years
# ago, and surfacing them would bury the real work. Stock expiry is the exception
# - a batch on the shelf is real wherever its record came from.

CLINICIAN_ROLES = {"doctor"}
NURSE_ROLES = {"nurse"}
LAB_ROLES = {"lab"}
RADIOLOGY_ROLES = {"radiology"}
PHARMACY_ROLES = {"pharmacist"}
FRONTDESK_ROLES = {"receptionist", "admin"}
WARD_ROLES = {"nurse", "receptionist", "management", "admin"}
STOCK_ROLES = {"pharmacist", "ops", "management", "admin"}
OPS_ROLES = {"ops", "management", "admin"}
FINANCE_ROLES = {"finance", "management", "admin"}
BOOKS_ROLES = {"finance", "admin"}
HR_ROLES = {"hr", "admin"}
_CACHE: Dict[str, tuple] = {}
_CACHE_TTL = 60
_PATIENT = "concat_ws(' ', p.first_name, p.last_name)"


def _cached(key: str, fn: Callable[[], List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    hit = _CACHE.get(key)
    if hit and time.monotonic() - hit[0] < _CACHE_TTL:
        return hit[1]
    val = fn()
    _CACHE[key] = (time.monotonic(), val)
    return val


def refresh_rules(*keys: str) -> None:
    """Drop cached rule results after an action that changes what they read, so the
    person who acts next (HR approving leave, Finance paying payroll) sees it at once."""
    for k in keys:
        _CACHE.pop(k, None)


def _item(id_: Any, title: str, detail: str = "", due: Any = None, overdue: bool = False,
          link: str = "", entity_type: str = "") -> Dict[str, Any]:
    """`due` is a date (due that working day) or a datetime (due at that moment)."""
    return {"id": str(id_), "title": title, "detail": detail, "due": due, "overdue": overdue, "link": link,
            "entity_type": entity_type}


def _mins(since: Optional[dt.datetime]) -> int:
    return int((now() - since).total_seconds() // 60) if since else 0


def _waited(m: int) -> str:
    return f"{m} min" if m < 120 else f"{m // 60}h {m % 60:02d}m"


def _my_staff(user) -> Optional[Dict[str, Any]]:
    with tx() as conn:
        return q1(conn, """SELECT id::text AS id, full_name, department_id FROM royan_staff
                           WHERE user_id=%s AND quarantined_at IS NULL""", (str(user.get("sub")),))


# ---- clinical --------------------------------------------------------------------

def _r_my_patients(user) -> List[Dict[str, Any]]:
    """Patients in my queue who are ready for me (triaged / called) and not yet in consultation."""
    me = _my_staff(user)
    if not me:
        return []
    with tx() as conn:
        rows = q(conn, f"""SELECT e.id, e.queue_number, e.status, e.triage_level, {_PATIENT} AS patient, p.mrn,
                                  COALESCE(e.nurse_done_at, e.triage_at, e.created_at) AS ready_at
                           FROM royan_encounters e JOIN royan_patients p ON p.id=e.patient_id
                           WHERE e.external_source IS NULL AND e.doctor_id=%s::uuid
                             AND e.created_at > now() - interval '24 hours'
                             AND (e.status IN ('triaged','waiting','called')
                                  OR (e.status='nurse_assessment' AND e.nurse_done_at IS NOT NULL))
                           ORDER BY ready_at""", (me["id"],))
    out = []
    for r in rows:
        m = _mins(r["ready_at"])
        urgent = r["triage_level"] in ("immediate", "urgent")
        out.append(_item(r["id"], f"Patient waiting for you: {r['patient']}",
                         f"{r['mrn']} · queue {r['queue_number'] or '-'} · waiting {_waited(m)}"
                         + (f" · triage {r['triage_level'].replace('_', ' ')}" if r["triage_level"] else ""),
                         r["ready_at"], urgent or m > 30, "/hospital/doctor", "encounter"))
    return out


def _r_critical_results(user) -> List[Dict[str, Any]]:
    """Critical lab results of the last 3 days nobody has verified yet."""
    with tx() as conn:
        rows = q(conn, f"""SELECT r.id, o.test_name, r.result_summary, r.resulted_at, o.ordered_by, {_PATIENT} AS patient, p.mrn
                           FROM royan_lab_results r JOIN royan_lab_orders o ON o.id=r.lab_order_id
                           JOIN royan_patients p ON p.id=r.patient_id
                           WHERE r.external_source IS NULL AND (r.is_critical OR r.interpretation='critical')
                             AND r.verified_at IS NULL AND r.resulted_at > now() - interval '3 days'
                           ORDER BY r.resulted_at""")
    return [_item(r["id"], f"Critical result: {r['test_name']} - {r['patient']}",
                  f"{r['mrn']} · {(r['result_summary'] or '')[:80]}" + (f" · ordered by {r['ordered_by']}" if r["ordered_by"] else ""),
                  r["resulted_at"], True, "/hospital/lab", "lab_result") for r in rows]


def _r_triage(user) -> List[Dict[str, Any]]:
    """Patients registered today and not yet triaged."""
    with tx() as conn:
        rows = q(conn, f"""SELECT e.id, e.queue_number, e.created_at, {_PATIENT} AS patient, p.mrn
                           FROM royan_encounters e JOIN royan_patients p ON p.id=e.patient_id
                           WHERE e.external_source IS NULL AND e.status IN ('patient_registered','waiting','in_triage')
                             AND e.triage_at IS NULL AND e.created_at > now() - interval '24 hours'
                           ORDER BY e.created_at""")
    return [_item(r["id"], f"Awaiting triage: {r['patient']}",
                  f"{r['mrn']} · queue {r['queue_number'] or '-'} · waiting {_waited(_mins(r['created_at']))}",
                  r["created_at"], _mins(r["created_at"]) > 15, "/hospital/nurse", "encounter") for r in rows]


def _r_referrals(user) -> List[Dict[str, Any]]:
    """Referrals sent to my department or to me by name, not yet accepted."""
    me = _my_staff(user)
    if not me:
        return []
    with tx() as conn:
        rows = q(conn, f"""SELECT r.id, r.urgency, r.reason, r.referred_at, r.referred_by, {_PATIENT} AS patient, p.mrn
                           FROM royan_referrals r JOIN royan_patients p ON p.id=r.patient_id
                           WHERE r.status='sent' AND r.referral_type IN ('internal','specialist')
                             AND r.referred_at > now() - interval '14 days'
                             AND (r.referred_to_dept_id = %s OR r.referred_to_doctor ILIKE %s)
                           ORDER BY r.referred_at""", (me["department_id"], f"%{me['full_name']}%"))
    return [_item(r["id"], f"Referral to accept: {r['patient']}",
                  f"{r['mrn']} · from {r['referred_by'] or 'a colleague'} · {(r['reason'] or '')[:60]}",
                  r["referred_at"], r["urgency"] in ("urgent", "emergency") or _mins(r["referred_at"]) > 24 * 60,
                  "/hospital/specialist", "referral") for r in rows]


# ---- diagnostics + pharmacy --------------------------------------------------------

_TAT_MIN = {"stat": 30, "emergency": 30, "urgent": 60}


def _r_lab_backlog(user) -> List[Dict[str, Any]]:
    with tx() as conn:
        rows = q(conn, f"""SELECT o.id, o.test_name, o.urgency, o.status, o.ordered_at, {_PATIENT} AS patient, p.mrn
                           FROM royan_lab_orders o JOIN royan_patients p ON p.id=o.patient_id
                           WHERE o.external_source IS NULL AND o.status IN ('ordered','sample_collected','processing')
                             AND o.ordered_at > now() - interval '7 days'
                           ORDER BY (o.urgency='stat') DESC, (o.urgency='urgent') DESC, o.ordered_at""")
    return [_item(r["id"], f"Lab {r['status'].replace('_', ' ')}: {r['test_name']} - {r['patient']}",
                  f"{r['mrn']} · {r['urgency']} · ordered {_waited(_mins(r['ordered_at']))} ago",
                  r["ordered_at"], _mins(r["ordered_at"]) > _TAT_MIN.get(r["urgency"], 120), "/hospital/lab", "lab_order")
            for r in rows]


def _r_radiology_backlog(user) -> List[Dict[str, Any]]:
    with tx() as conn:
        rows = q(conn, f"""SELECT o.id, o.test_name, o.modality, o.urgency, o.status,
                                  COALESCE(o.ordered_at, o.created_at) AS ordered_at, {_PATIENT} AS patient, p.mrn
                           FROM royan_radiology_orders o JOIN royan_patients p ON p.id=o.patient_id
                           WHERE o.external_source IS NULL AND o.reported_at IS NULL
                             AND COALESCE(o.status, 'ordered') NOT IN ('completed','reported','verified','cancelled')
                             AND COALESCE(o.ordered_at, o.created_at) > now() - interval '7 days'
                           ORDER BY (o.urgency IN ('urgent','stat','emergency')) DESC, 6""")
    return [_item(r["id"], f"Imaging to report: {r['test_name']} - {r['patient']}",
                  f"{r['mrn']} · {r['modality'] or 'imaging'} · {r['urgency'] or 'routine'} · {_waited(_mins(r['ordered_at']))} ago",
                  r["ordered_at"], _mins(r["ordered_at"]) > _TAT_MIN.get(r["urgency"] or "", 240), "/hospital/radiology",
                  "radiology_order") for r in rows]


def _r_to_dispense(user) -> List[Dict[str, Any]]:
    with tx() as conn:
        rows = q(conn, f"""SELECT rx.id, rx.drug_name, rx.dosage, rx.quantity, rx.prescribed_at, {_PATIENT} AS patient, p.mrn
                           FROM royan_prescriptions rx JOIN royan_patients p ON p.id=rx.patient_id
                           WHERE rx.external_source IS NULL AND rx.status='pending'
                             AND rx.approval_status IN ('not_required','approved')
                             AND rx.prescribed_at > now() - interval '3 days'
                           ORDER BY rx.prescribed_at""")
    return [_item(r["id"], f"To dispense: {r['drug_name']} - {r['patient']}",
                  f"{r['mrn']} · {r['dosage'] or ''} × {float(r['quantity']):g} · waiting {_waited(_mins(r['prescribed_at']))}",
                  r["prescribed_at"], _mins(r["prescribed_at"]) > 30, "/hospital/pharmacy", "prescription") for r in rows]


def _r_rx_approval(user) -> List[Dict[str, Any]]:
    with tx() as conn:
        rows = q(conn, f"""SELECT rx.id, rx.drug_name, rx.approval_requested_at, rx.approval_requested_by, {_PATIENT} AS patient, p.mrn
                           FROM royan_prescriptions rx JOIN royan_patients p ON p.id=rx.patient_id
                           WHERE rx.external_source IS NULL AND rx.approval_status='pending' AND rx.status='pending'
                           ORDER BY rx.approval_requested_at NULLS LAST""")
    return [_item(r["id"], f"Prescription to approve: {r['drug_name']} - {r['patient']}",
                  f"{r['mrn']}" + (f" · requested by {r['approval_requested_by']}" if r["approval_requested_by"] else ""),
                  r["approval_requested_at"], _mins(r["approval_requested_at"]) > 30, "/hospital/front-desk", "prescription")
            for r in rows]


def _stock_rule(expired: bool):
    def rule(user) -> List[Dict[str, Any]]:
        t = today()
        with tx() as conn:
            rows = q(conn, """SELECT f.id, COALESCE(f.brand_name, f.generic_name) AS drug, SUM(b.quantity_on_hand) AS qty,
                                     SUM(b.quantity_on_hand * COALESCE(b.unit_cost, 0)) AS value, MIN(b.expiry_date) AS first_expiry,
                                     string_agg(DISTINCT b.batch_number, ', ') AS batches
                              FROM royan_inventory_batches b JOIN royan_drug_formulary f ON f.id=b.formulary_id
                              WHERE b.quantity_on_hand > 0 AND b.expiry_date IS NOT NULL
                                AND b.expiry_date """ + ("< %s" if expired else "BETWEEN %s AND %s") + """
                              GROUP BY f.id, 2 ORDER BY 5""", (t,) if expired else (t, t + dt.timedelta(days=60)))
        return [_item(r["id"], f"{'Expired stock on the shelf' if expired else 'Expiring within 60 days'}: {r['drug']}",
                      f"{float(r['qty']):g} units · ₦{float(r['value']):,.0f} · batches {(r['batches'] or '')[:60]}",
                      r["first_expiry"], expired, "/hospital/pharmacy/inventory", "drug") for r in rows]
    return rule


# ---- front desk, wards, facilities ---------------------------------------------------

def _r_admissions(user) -> List[Dict[str, Any]]:
    with tx() as conn:
        rows = q(conn, f"""SELECT a.id, a.urgency, a.ward_preference, a.requested_at, a.requested_by, {_PATIENT} AS patient, p.mrn
                           FROM royan_admission_requests a JOIN royan_patients p ON p.id=a.patient_id
                           WHERE a.status='pending' ORDER BY (a.urgency='immediate') DESC, a.requested_at""")
    return [_item(r["id"], f"Admission requested: {r['patient']}",
                  f"{r['mrn']} · {r['urgency']}" + (f" · {r['ward_preference']}" if r["ward_preference"] else "")
                  + (f" · by {r['requested_by']}" if r["requested_by"] else ""),
                  r["requested_at"], r["urgency"] != "routine" or _mins(r["requested_at"]) > 120, "/hospital/wards",
                  "admission_request") for r in rows]


def _r_maintenance(user) -> List[Dict[str, Any]]:
    t = today()
    with tx() as conn:
        tasks = q(conn, """SELECT id::text AS id, title, severity, due_at FROM royan_maintenance_tasks
                           WHERE COALESCE(status,'open') NOT IN ('completed','done','cancelled','closed')
                             AND due_at IS NOT NULL AND due_at < now() + interval '2 days' ORDER BY due_at""")
        equip = q(conn, """SELECT id::text AS id, equipment_name, maintenance_type, location, due_date
                           FROM royan_equipment_maintenance WHERE status='pending' AND due_date <= %s ORDER BY due_date""",
                  (t + dt.timedelta(days=7),))
    out = [_item(f"task:{r['id']}", f"Maintenance due: {r['title']}", r["severity"] or "", r["due_at"],
                 r["due_at"] < now(), "/hospital/audits-maintenance", "maintenance_task") for r in tasks]
    out += [_item(f"equip:{r['id']}", f"Equipment {r['maintenance_type']}: {r['equipment_name']}", r["location"] or "",
                  r["due_date"], r["due_date"] < t, "/hospital/audits-maintenance", "equipment") for r in equip]
    return out


# ---- finance + Roy Books ----------------------------------------------------------

def _r_payer_follow_ups(user) -> List[Dict[str, Any]]:
    """Patient Relations: follow-ups I set with an HMO / corporate payer that are due (personal)."""
    from src.services.payer_relations import follow_ups_due
    t = today()
    return [_item(r["id"], f"Follow up with {r['payer']}", (r["summary"] or "")[:90], r["follow_up_on"],
                  r["follow_up_on"] < t, f"/relations?payer={r['payer_id']}", "payer_contact")
            for r in follow_ups_due(_me(user))]


def _r_discounts(user) -> List[Dict[str, Any]]:
    with tx() as conn:
        rows = q(conn, f"""SELECT b.id, b.bill_number, b.discount, b.subtotal, b.discount_reason, b.discount_requested_by,
                                  b.discount_requested_at, {_PATIENT} AS patient
                           FROM royan_billing b JOIN royan_patients p ON p.id=b.patient_id
                           WHERE b.discount_status='pending' ORDER BY b.discount_requested_at NULLS LAST""")
    return [_item(r["id"], f"Discount to approve: {r['bill_number']} - {r['patient']}",
                  f"₦{float(r['discount'] or 0):,.0f} off ₦{float(r['subtotal'] or 0):,.0f}"
                  + (f" · {r['discount_reason'][:60]}" if r["discount_reason"] else "")
                  + (f" · asked by {r['discount_requested_by']}" if r["discount_requested_by"] else ""),
                  r["discount_requested_at"], _mins(r["discount_requested_at"]) > 60, "/hospital/billing", "bill") for r in rows]


def _r_books_failed(user) -> List[Dict[str, Any]]:
    with tx() as conn:
        rows = q(conn, """SELECT id::text AS id, source_type, source_ref, source_id, message, updated_at, doc_date
                          FROM fin_source_postings WHERE status='FAILED' ORDER BY updated_at""")
    return [_item(r["id"], f"Not in the books: {r['source_ref'] or r['source_type'] + ' ' + r['source_id']}",
                  (r["message"] or "")[:140], r["doc_date"], True, "/finance/books/close", "fin_posting") for r in rows]


def _r_payroll_to_pay(user) -> List[Dict[str, Any]]:
    with tx() as conn:
        rows = q(conn, """SELECT make_date(period_year, period_month, 1) AS period, COUNT(*) AS n, SUM(net_salary) AS net
                          FROM royan_payroll_records WHERE status='approved' GROUP BY 1 ORDER BY 1""")
    return [_item(f"{r['period']:%Y-%m}", f"Payroll to pay: {r['period']:%B %Y}",
                  f"{r['n']} staff · ₦{float(r['net'] or 0):,.0f} net", None, r["period"] < today().replace(day=1),
                  "/hr?tab=payroll", "payroll") for r in rows]


# ---- HR ------------------------------------------------------------------------

def _r_timesheets(user) -> List[Dict[str, Any]]:
    with tx() as conn:
        rows = q(conn, """SELECT COALESCE(user_id::text, 'staff:' || staff_id::text) AS who, COUNT(*) AS n, SUM(hours_worked) AS h,
                                 MIN(date) AS since
                          FROM royan_timesheets WHERE status='submitted' AND date >= %s GROUP BY 1""",
                 (today() - dt.timedelta(days=35),))
        pm = person_map(conn)
    return [_item(r["who"], f"Timesheets to approve: {pm.get(r['who'], {}).get('name', 'staff member')}",
                  f"{r['n']} entr{'y' if r['n'] == 1 else 'ies'} · {float(r['h']):g}h since {r['since']:%d %b}",
                  link="/hr?tab=timesheets", entity_type="timesheet") for r in rows]


def _r_long_clocks(user) -> List[Dict[str, Any]]:
    with tx() as conn:
        rows = q(conn, """SELECT id::text AS id, user_id::text AS user_id, started_at FROM staff_time_sessions
                          WHERE ended_at IS NULL AND started_at < now() - interval '14 hours'""")
        pm = person_map(conn)
    return [_item(r["id"], f"Still clocked in: {pm.get(r['user_id'], {}).get('name', 'staff member')}",
                  f"Since {r['started_at'].astimezone(TZ):%a %d %b %H:%M} - probably forgot to clock out",
                  overdue=True, link="/hr", entity_type="time_session") for r in rows]


def _r_leave(user) -> List[Dict[str, Any]]:
    with tx() as conn:
        rows = q(conn, """SELECT l.id::text AS id, l.leave_type, l.start_date, l.end_date, l.days_count, s.full_name
                          FROM royan_leave_requests l JOIN royan_staff s ON s.id=l.staff_id
                          WHERE l.status='pending' ORDER BY l.start_date""")
    t = today()
    return [_item(r["id"], f"Leave to decide: {r['full_name']}",
                  f"{r['leave_type']} · {r['start_date']:%d %b}–{r['end_date']:%d %b} · {float(r['days_count']):g} day(s)",
                  r["start_date"], r["start_date"] <= t + dt.timedelta(days=2), "/hr?tab=leave", "leave_request") for r in rows]


def _r_payroll_drafts(user) -> List[Dict[str, Any]]:
    with tx() as conn:
        rows = q(conn, """SELECT make_date(period_year, period_month, 1) AS period, COUNT(*) AS n, SUM(net_salary) AS net
                          FROM royan_payroll_records WHERE status='draft' GROUP BY 1 ORDER BY 1""")
    return [_item(f"{r['period']:%Y-%m}", f"Payroll to approve: {r['period']:%B %Y}",
                  f"{r['n']} draft record(s) · ₦{float(r['net'] or 0):,.0f} net", None,
                  r["period"] < today().replace(day=1), "/hr?tab=payroll", "payroll") for r in rows]


# key, label, team, level, roles (None = everyone; the rule itself is personal), personal (never cached)
RULES: List[Dict[str, Any]] = [
    {"key": "clinical.my_patients", "label": "Patients waiting for you", "dept": "Doctors", "level": "action", "roles": CLINICIAN_ROLES, "fn": _r_my_patients, "personal": True},
    {"key": "clinical.critical_results", "label": "Critical results to review", "dept": "Doctors", "level": "critical", "roles": CLINICIAN_ROLES | NURSE_ROLES, "fn": _r_critical_results},
    {"key": "clinical.referrals", "label": "Referrals to accept", "dept": "Doctors", "level": "action", "roles": CLINICIAN_ROLES, "fn": _r_referrals, "personal": True},
    {"key": "nursing.triage", "label": "Patients awaiting triage", "dept": "Nursing", "level": "action", "roles": NURSE_ROLES, "fn": _r_triage},
    {"key": "wards.admissions", "label": "Admissions requested", "dept": "Nursing", "level": "action", "roles": WARD_ROLES, "fn": _r_admissions},
    {"key": "lab.backlog", "label": "Lab orders in progress", "dept": "Laboratory", "level": "action", "roles": LAB_ROLES, "fn": _r_lab_backlog},
    {"key": "radiology.backlog", "label": "Imaging to report", "dept": "Radiology", "level": "action", "roles": RADIOLOGY_ROLES, "fn": _r_radiology_backlog},
    {"key": "pharmacy.dispense", "label": "Prescriptions to dispense", "dept": "Pharmacy", "level": "action", "roles": PHARMACY_ROLES, "fn": _r_to_dispense},
    {"key": "frontdesk.rx_approval", "label": "Prescriptions awaiting approval", "dept": "Front Desk", "level": "action", "roles": FRONTDESK_ROLES, "fn": _r_rx_approval},
    {"key": "stock.expired", "label": "Expired stock on the shelf", "dept": "Pharmacy", "level": "critical", "roles": STOCK_ROLES, "fn": _stock_rule(True)},
    {"key": "stock.expiring", "label": "Stock expiring within 60 days", "dept": "Pharmacy", "level": "info", "roles": STOCK_ROLES, "fn": _stock_rule(False)},
    {"key": "facilities.maintenance", "label": "Maintenance due", "dept": "Operations", "level": "action", "roles": OPS_ROLES, "fn": _r_maintenance},
    {"key": "relations.follow_ups", "label": "HMO / corporate follow-ups due", "dept": "Finance", "level": "action", "roles": FINANCE_ROLES, "fn": _r_payer_follow_ups, "personal": True},
    {"key": "finance.discounts", "label": "Discounts to approve", "dept": "Finance", "level": "action", "roles": FINANCE_ROLES, "fn": _r_discounts},
    {"key": "finance.books_failed", "label": "Operations not in Roy Books", "dept": "Finance", "level": "action", "roles": BOOKS_ROLES, "fn": _r_books_failed},
    {"key": "finance.payroll_pay", "label": "Approved payroll to pay", "dept": "Finance", "level": "action", "roles": FINANCE_ROLES, "fn": _r_payroll_to_pay},
    {"key": "hr.timesheets", "label": "Timesheets to approve", "dept": "HR", "level": "action", "roles": HR_ROLES, "fn": _r_timesheets},
    {"key": "hr.long_clocks", "label": "Clocks left running", "dept": "HR", "level": "action", "roles": HR_ROLES, "fn": _r_long_clocks},
    {"key": "hr.leave", "label": "Leave requests to decide", "dept": "HR", "level": "action", "roles": HR_ROLES | {"management"}, "fn": _r_leave},
    {"key": "hr.payroll", "label": "Payroll to approve", "dept": "HR", "level": "action", "roles": HR_ROLES | {"management"}, "fn": _r_payroll_drafts},
]
RULE_BY_KEY = {r["key"]: r for r in RULES}


def _rules_for(user: Dict[str, Any]) -> List[Dict[str, Any]]:
    rs = _roles(user)
    return [r for r in RULES if r["roles"] is None or rs & r["roles"]]


def _run_rule(rule: Dict[str, Any], user: Dict[str, Any], fresh: bool = False) -> List[Dict[str, Any]]:
    try:
        if rule.get("personal"):
            return rule["fn"](user)
        if fresh:
            _CACHE.pop(rule["key"], None)
        return _cached(rule["key"], lambda: rule["fn"](user))
    except Exception as exc:  # one module being unavailable must not take the workspace down
        import logging
        logging.getLogger(__name__).warning("workspace rule %s failed: %s", rule["key"], exc)
        return []


def signals(user: Dict[str, Any]) -> Dict[str, Any]:
    """Operational items for this person's roles, with who (if anyone) has taken each one."""
    me = _me(user)
    groups = []
    current: Dict[str, set] = {}
    for rule in _rules_for(user):
        items = _run_rule(rule, user)
        current[rule["key"]] = {i["id"] for i in items}
        if items:
            groups.append({"key": rule["key"], "label": rule["label"], "level": rule["level"], "dept": rule["dept"],
                           "count": len(items), "overdue": sum(1 for i in items if i["overdue"]), "items": items})
    with tx() as conn:
        taken = q(conn, """SELECT t.id::text AS id, t.source_ref, t.assigned_to::text AS assigned_to, t.status, t.title,
                                  t.created_by::text AS created_by, t.request_id::text AS request_id
                           FROM royan_tasks t WHERE t.source='operational' AND t.status IN %s""", (OPEN_STATUSES,))
        # an item dealt with in its module closes the task that was taken for it
        resolved = 0
        for t in taken:
            rule_key, _, ent = (t["source_ref"] or "").partition("|")
            if rule_key in current and ent not in current[rule_key]:
                _apply_status(conn, t, "completed", t["assigned_to"] or me,
                              f"resolved in {RULE_BY_KEY[rule_key]['label'].lower()}", system=True)
                resolved += 1
        names = _names(conn, [t["assigned_to"] for t in taken])
    by_ref = {t["source_ref"]: t for t in taken}
    for g in groups:
        for i in g["items"]:
            t = by_ref.get(f"{g['key']}|{i['id']}")
            if t and t["status"] in OPEN_STATUSES:
                i["task_id"] = t["id"]
                i["taken_by"] = t["assigned_to"]
                i["taken_by_name"] = "you" if t["assigned_to"] == me else names.get(t["assigned_to"])
    return {"groups": groups, "total": sum(g["count"] for g in groups), "resolved_now": resolved}


def take_signal(user: Dict[str, Any], rule_key: str, item_id: str, assign_to: Optional[str] = None) -> Dict[str, Any]:
    me = _me(user)
    rule = RULE_BY_KEY.get(rule_key)
    if not rule or rule not in _rules_for(user):
        raise PermissionError("This item is not in your area")
    item = next((i for i in _run_rule(rule, user, fresh=True) if i["id"] == str(item_id)), None)
    if not item:
        raise WorkspaceError("This has already been dealt with")
    ref = f"{rule_key}|{item['id']}"
    with tx() as conn:
        existing = q1(conn, """SELECT id::text AS id, assigned_to::text AS assigned_to FROM royan_tasks
                               WHERE source='operational' AND source_ref=%s AND status IN %s""", (ref, OPEN_STATUSES))
        if existing:
            who = _names(conn, [existing["assigned_to"]]).get(existing["assigned_to"], "someone")
            raise WorkspaceError(f"{'You have' if existing['assigned_to'] == me else who + ' has'} already taken this")
        return create_task(user, {
            "title": item["title"], "description": item["detail"], "assigned_to": assign_to or me,
            "priority": "high" if item["overdue"] or rule["level"] == "critical" else "medium",
            "due_at": (item["due"].isoformat() if isinstance(item["due"], dt.datetime)
                       else dt.datetime.combine(item["due"], dt.time(17, 0), TZ).isoformat() if item["due"] else None),
            "department": rule["dept"], "source_ref": ref, "entity_type": item["entity_type"], "entity_id": item["id"],
            "entity_label": rule["label"], "link": item["link"],
        }, conn=conn, source="operational")


# ---------------------------------------------------------------------------
# Requests (ask a person or a team for information or for work)
# ---------------------------------------------------------------------------

_REQ_COLS = """r.id::text AS id, r.from_user::text AS from_user, r.to_user::text AS to_user, r.to_department, r.kind, r.subject,
    r.body, r.task_id::text AS task_id, r.work_task_id::text AS work_task_id, r.due_at, r.status, r.response,
    r.responded_by::text AS responded_by, r.responded_at, r.closed_at, r.created_at, r.updated_at,
    (SELECT COUNT(*) FROM staff_request_messages m WHERE m.request_id=r.id) AS messages"""


def _my_dept(conn, me: str) -> str:
    return next((p["department"] for p in people(conn) if p["user_id"] == me), "Operations")


def _req_decorate(conn, rows: List[Dict[str, Any]], me: str) -> List[Dict[str, Any]]:
    names = _names(conn, [r["from_user"] for r in rows] + [r["to_user"] for r in rows] + [r["responded_by"] for r in rows])
    for r in rows:
        r["from_name"] = names.get(r["from_user"])
        r["to_name"] = names.get(r["to_user"]) if r["to_user"] else f"{r['to_department']} team"
        r["responded_by_name"] = names.get(r["responded_by"]) if r["responded_by"] else None
        r["mine_to_answer"] = r["from_user"] != me and r["status"] in ("sent", "acknowledged", "in_progress")
        r["overdue"] = bool(r["due_at"] and r["due_at"] < now() and r["status"] in ("sent", "acknowledged", "in_progress"))
    return rows


def list_requests(user: Dict[str, Any]) -> Dict[str, Any]:
    me = _me(user)
    with tx() as conn:
        dept = _my_dept(conn, me)
        incoming = q(conn, f"""SELECT {_REQ_COLS} FROM staff_requests r
                               WHERE r.from_user<>%s AND (r.to_user=%s OR (r.to_user IS NULL AND r.to_department=%s))
                                 AND (r.status NOT IN ('closed','declined','responded') OR r.updated_at > now() - interval '14 days')
                               ORDER BY (r.status IN ('sent','acknowledged','in_progress')) DESC, r.due_at NULLS LAST, r.created_at DESC""",
                     (me, me, dept))
        outgoing = q(conn, f"""SELECT {_REQ_COLS} FROM staff_requests r WHERE r.from_user=%s
                               AND (r.status NOT IN ('closed','declined') OR r.updated_at > now() - interval '14 days')
                               ORDER BY (r.status='responded') DESC, r.created_at DESC""", (me,))
        return {"incoming": _req_decorate(conn, incoming, me), "outgoing": _req_decorate(conn, outgoing, me), "department": dept}


def create_request(user: Dict[str, Any], data: Dict[str, Any]) -> Dict[str, Any]:
    me = _me(user)
    subject = (data.get("subject") or "").strip()
    if not subject:
        raise ValueError("Say what you need")
    kind = data.get("kind") or "info"
    if kind not in ("info", "work"):
        raise ValueError("Unknown request type")
    to_user = data.get("to_user") or None
    to_dept = data.get("to_department") or None
    if not to_user and not to_dept:
        raise ValueError("Choose a person or a team")
    if to_user and (not _is_uuid(to_user) or to_user == me):
        raise ValueError("Choose someone else")
    if to_dept and to_dept not in DEPARTMENTS:
        raise ValueError("Unknown team")
    due = _dt(data.get("due_at"))
    with tx() as conn:
        who = _names(conn, [me])[me]
        r = q1(conn, """INSERT INTO staff_requests (from_user, to_user, to_department, kind, subject, body, task_id, due_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id::text AS id""",
               (me, to_user, None if to_user else to_dept, kind, subject[:300], (data.get("body") or "").strip() or None,
                data.get("task_id") if _is_uuid(data.get("task_id")) else None, due))
        target = _names(conn, [to_user])[to_user] if to_user else f"{to_dept} team"
        if kind == "work" and to_user:
            t = create_task({"sub": me, "roles": user.get("roles")},
                            {"title": subject, "description": data.get("body"), "assigned_to": to_user,
                             "due_at": due.isoformat() if due else None, "priority": data.get("priority") or "medium",
                             "request_id": r["id"]}, conn=conn, source="request")
            ex(conn, "UPDATE staff_requests SET work_task_id=%s WHERE id=%s::uuid", (t["id"], r["id"]))
        else:
            recipients = [to_user] if to_user else _dept_members(conn, to_dept)
            notify(conn, recipients, "request", "action",
                   f"{who} {'asks' if kind == 'info' else 'needs'}{'' if to_user else ' ' + to_dept}: {subject[:120]}",
                   data.get("body"), "request", r["id"], me)
        if data.get("task_id") and _is_uuid(data["task_id"]):
            t = q1(conn, f"SELECT {_TASK_COLS} FROM royan_tasks t WHERE t.id=%s::uuid", (data["task_id"],))
            if t and t["status"] in ("pending", "in_progress") and _can_see(user, t):
                _apply_status(conn, t, "waiting", me, None, target)
        journal(conn, me, "request_sent", f"Asked {target}: {subject[:120]}", "request", r["id"])
        return _req_decorate(conn, [q1(conn, f"SELECT {_REQ_COLS} FROM staff_requests r WHERE r.id=%s::uuid", (r["id"],))], me)[0]


def get_request(user: Dict[str, Any], request_id: str) -> Dict[str, Any]:
    me = _me(user)
    with tx() as conn:
        r = q1(conn, f"SELECT {_REQ_COLS} FROM staff_requests r WHERE r.id=%s::uuid", (request_id,)) if _is_uuid(request_id) else None
        if not r:
            raise LookupError("Request not found")
        if me not in (r["from_user"], r["to_user"]) and r["to_department"] != _my_dept(conn, me) and not (_roles(user) & MANAGER_ROLES):
            raise PermissionError("This request is between other people")
        msgs = q(conn, """SELECT id, author::text AS author, body, created_at FROM staff_request_messages
                          WHERE request_id=%s::uuid ORDER BY created_at""", (request_id,))
        names = _names(conn, [m["author"] for m in msgs])
        for m in msgs:
            m["author_name"] = names.get(m["author"])
        r = _req_decorate(conn, [r], me)[0]
    return {**r, "thread": msgs}


def act_request(user: Dict[str, Any], request_id: str, action: str, data: Dict[str, Any]) -> Dict[str, Any]:
    me = _me(user)
    body = (data.get("body") or "").strip()
    with tx() as conn:
        if not _is_uuid(request_id) or not q1(conn, "SELECT 1 FROM staff_requests WHERE id=%s::uuid FOR UPDATE", (request_id,)):
            raise LookupError("Request not found")
        r = q1(conn, f"SELECT {_REQ_COLS} FROM staff_requests r WHERE r.id=%s::uuid", (request_id,))
        if not r:
            raise LookupError("Request not found")
        dept = _my_dept(conn, me)
        is_from = r["from_user"] == me
        is_to = r["to_user"] == me or (r["to_user"] is None and r["to_department"] == dept)
        if not (is_from or is_to):
            raise PermissionError("This request is between other people")
        who = _names(conn, [me])[me]
        open_ = r["status"] in ("sent", "acknowledged", "in_progress")
        if action == "reply":
            if not body:
                raise ValueError("Write a message")
            ex(conn, "INSERT INTO staff_request_messages (request_id, author, body) VALUES (%s::uuid, %s, %s)", (request_id, me, body[:2000]))
            ex(conn, "UPDATE staff_requests SET updated_at=now() WHERE id=%s::uuid", (request_id,))
            other = [r["to_user"]] if is_from and r["to_user"] else ([r["from_user"]] if not is_from else _dept_members(conn, r["to_department"]))
            notify(conn, other, "message", "social", f"{who} on “{r['subject'][:80]}”", body[:300], "request", request_id, me)
        elif action in ("acknowledge", "start"):
            if not is_to or not open_:
                raise WorkspaceError("Only the person asked can take this up while it is open")
            ex(conn, """UPDATE staff_requests SET status=%s, to_user=COALESCE(to_user, %s), updated_at=now() WHERE id=%s::uuid""",
               ("acknowledged" if action == "acknowledge" else "in_progress", me, request_id))
            notify(conn, [r["from_user"]], "response", "info",
                   f"{who} {'has seen' if action == 'acknowledge' else 'is working on'}: {r['subject'][:100]}", None, "request", request_id, me)
        elif action == "respond":
            if not is_to or not open_:
                raise WorkspaceError("Only the person asked can answer while it is open")
            if not body:
                raise ValueError("Write your answer")
            ex(conn, """UPDATE staff_requests SET status='responded', response=%s, responded_by=%s, responded_at=now(),
                               to_user=COALESCE(to_user, %s), updated_at=now() WHERE id=%s::uuid""", (body[:2000], me, me, request_id))
            ex(conn, "INSERT INTO staff_request_messages (request_id, author, body) VALUES (%s::uuid, %s, %s)", (request_id, me, body[:2000]))
            notify(conn, [r["from_user"]], "response", "action", f"{who} answered: {r['subject'][:100]}", body[:300], "request", request_id, me)
            journal(conn, me, "request_answered", f"Answered {_names(conn, [r['from_user']])[r['from_user']]}: {r['subject'][:120]}", "request", request_id)
            if r["task_id"]:
                t = q1(conn, f"SELECT {_TASK_COLS} FROM royan_tasks t WHERE t.id=%s::uuid", (r["task_id"],))
                if t and t["status"] == "waiting":
                    _apply_status(conn, t, "in_progress", r["from_user"], f"answer from {who}")
        elif action == "decline":
            if not is_to or not open_:
                raise WorkspaceError("Only the person asked can decline while it is open")
            ex(conn, """UPDATE staff_requests SET status='declined', response=%s, responded_by=%s, responded_at=now(),
                               updated_at=now() WHERE id=%s::uuid""", (body or None, me, request_id))
            notify(conn, [r["from_user"]], "response", "action", f"{who} declined: {r['subject'][:100]}", body or None, "request", request_id, me)
        elif action == "close":
            if not is_from:
                raise WorkspaceError("Only the person who asked can close it")
            ex(conn, "UPDATE staff_requests SET status='closed', closed_at=now(), updated_at=now() WHERE id=%s::uuid", (request_id,))
        else:
            raise ValueError("Unknown action")
    return get_request(user, request_id)


# ---------------------------------------------------------------------------
# Inbox (notifications)
# ---------------------------------------------------------------------------

_INBOX_FILTERS = {
    "action": "level IN ('critical','action')",
    "requests": "kind IN ('request','response')",
    "mentions": "kind IN ('mention','comment','message')",
    "updates": "level='info'",
}


def inbox(user: Dict[str, Any], flt: str = "all") -> Dict[str, Any]:
    me = _me(user)
    where = _INBOX_FILTERS.get(flt, "TRUE")
    with tx() as conn:
        rows = q(conn, f"""SELECT id, kind, level, title, body, link_type, link_id, actor::text AS actor, read_at, created_at
                           FROM staff_notifications WHERE user_id=%s AND {where} AND created_at > now() - interval '60 days'
                           ORDER BY created_at DESC LIMIT 200""", (me,))
        counts = q1(conn, f"""SELECT COUNT(*) FILTER (WHERE read_at IS NULL) AS unread,
                                     {', '.join(f"COUNT(*) FILTER (WHERE read_at IS NULL AND {w}) AS {k}" for k, w in _INBOX_FILTERS.items())}
                              FROM staff_notifications WHERE user_id=%s""", (me,))
        names = _names(conn, [r["actor"] for r in rows])
    for r in rows:
        r["actor_name"] = names.get(r["actor"]) if r["actor"] else "Synbot"
    return {"items": rows, "counts": {k: int(v or 0) for k, v in counts.items()}}


def mark_read(user: Dict[str, Any], ids: Optional[List[int]] = None) -> Dict[str, Any]:
    me = _me(user)
    with tx() as conn:
        if ids:
            ex(conn, "UPDATE staff_notifications SET read_at=now() WHERE user_id=%s AND id = ANY(%s) AND read_at IS NULL",
               (me, [int(i) for i in ids]))
        else:
            ex(conn, "UPDATE staff_notifications SET read_at=now() WHERE user_id=%s AND read_at IS NULL", (me,))
    return {"ok": True}


# ---------------------------------------------------------------------------
# Messages (one-to-one and the whole team) on the existing threads tables
# ---------------------------------------------------------------------------

TEAM_KEY = "team:all"


def _thread(conn, me: str, other: str) -> str:
    if other == "team":
        key, title, kind = TEAM_KEY, "Whole team", "team"
    else:
        if not _is_uuid(other) or other == me or not q1(conn, "SELECT 1 FROM royan_users WHERE id=%s", (other,)):
            raise ValueError("Choose someone to message")
        a, b = sorted([me, other])
        key, title, kind = f"dm:{a}:{b}", "Direct message", "direct"
    r = q1(conn, "SELECT id::text AS id FROM threads WHERE channel_key=%s", (key,))
    if not r:
        r = q1(conn, """INSERT INTO threads (title, created_by, thread_type, channel_key) VALUES (%s, %s, %s, %s)
                        ON CONFLICT (channel_key) WHERE channel_key IS NOT NULL DO UPDATE SET title=EXCLUDED.title
                        RETURNING id::text AS id""", (title, me, kind, key))
    for uid in ([me, other] if other != "team" else [me]):
        if not q1(conn, "SELECT 1 FROM thread_participants WHERE thread_id=%s::uuid AND user_id=%s", (r["id"], uid)):
            ex(conn, "INSERT INTO thread_participants (thread_id, user_id, role) VALUES (%s::uuid, %s, 'member')", (r["id"], uid))
    return r["id"]


def conversations(user: Dict[str, Any]) -> Dict[str, Any]:
    me = _me(user)
    with tx() as conn:
        _thread(conn, me, "team")
        rows = q(conn, """SELECT t.id::text AS id, t.thread_type, t.channel_key, t.last_activity_at,
                                 (SELECT content FROM thread_messages m WHERE m.thread_id=t.id ORDER BY created_at DESC LIMIT 1) AS last_message,
                                 (SELECT sender FROM thread_messages m WHERE m.thread_id=t.id ORDER BY created_at DESC LIMIT 1) AS last_sender,
                                 (SELECT COUNT(*) FROM thread_messages m WHERE m.thread_id=t.id AND m.sender<>%s
                                    AND m.created_at > COALESCE((SELECT last_read_at FROM thread_reads r WHERE r.thread_id=t.id AND r.user_id=%s),
                                                                '-infinity'::timestamptz)) AS unread
                          FROM threads t
                          WHERE t.channel_key=%s OR (t.thread_type='direct' AND t.channel_key LIKE %s)
                          ORDER BY t.last_activity_at DESC NULLS LAST""", (me, me, TEAM_KEY, f"%{me}%"))
        pm = person_map(conn)
    online = online_ids()
    out = []
    for r in rows:
        if r["channel_key"] == TEAM_KEY:
            other, name = "team", "Whole team"
        else:
            ids = r["channel_key"].split(":")[1:]
            other = next((i for i in ids if i != me), me)
            name = pm.get(other, {}).get("name", "Former colleague")
        out.append({"id": r["id"], "with": other, "name": name, "online": other in online,
                    "last_message": r["last_message"], "last_sender": pm.get(r["last_sender"] or "", {}).get("name"),
                    "last_activity_at": r["last_activity_at"], "unread": int(r["unread"] or 0)})
    return {"conversations": out, "unread": sum(c["unread"] for c in out)}


def messages(user: Dict[str, Any], other: str, limit: int = 200) -> Dict[str, Any]:
    me = _me(user)
    with tx() as conn:
        tid = _thread(conn, me, other)
        rows = q(conn, """SELECT id::text AS id, sender, content, created_at FROM
                            (SELECT * FROM thread_messages WHERE thread_id=%s::uuid ORDER BY created_at DESC LIMIT %s) m
                          ORDER BY created_at""", (tid, limit))
        ex(conn, """INSERT INTO thread_reads (thread_id, user_id, last_read_at) VALUES (%s::uuid, %s, now())
                    ON CONFLICT (thread_id, user_id) DO UPDATE SET last_read_at=now()""", (tid, me))
        names = _names(conn, [r["sender"] for r in rows if _is_uuid(r["sender"])])
    for r in rows:
        r["mine"] = r["sender"] == me
        r["sender_name"] = names.get(r["sender"], "Synbot")
    return {"thread_id": tid, "with": other, "messages": rows}


def send_message(user: Dict[str, Any], other: str, body: str) -> Dict[str, Any]:
    me = _me(user)
    body = (body or "").strip()
    if not body:
        raise ValueError("Write a message")
    with tx() as conn:
        tid = _thread(conn, me, other)
        m = q1(conn, """INSERT INTO thread_messages (thread_id, sender, content, metadata) VALUES (%s::uuid, %s, %s, '{}'::jsonb)
                        RETURNING id::text AS id, created_at""", (tid, me, body[:4000]))
        ex(conn, "UPDATE threads SET last_activity_at=now() WHERE id=%s::uuid", (tid,))
        ex(conn, """INSERT INTO thread_reads (thread_id, user_id, last_read_at) VALUES (%s::uuid, %s, now())
                    ON CONFLICT (thread_id, user_id) DO UPDATE SET last_read_at=now()""", (tid, me))
        mentioned = _mentions(conn, body) - {other}
        if mentioned:
            who = _names(conn, [me])[me]
            notify(conn, mentioned, "mention", "social", f"{who} mentioned you{' in the team chat' if other == 'team' else ''}",
                   body[:300], "message", other if other == "team" else me, me)
    return {"id": m["id"], "thread_id": tid, "created_at": m["created_at"]}


# ---------------------------------------------------------------------------
# Team
# ---------------------------------------------------------------------------

def team(user: Dict[str, Any]) -> Dict[str, Any]:
    me = _me(user)
    ws = week_start()
    with tx() as conn:
        ppl = [p for p in people(conn) if p["has_login"]]
        sessions = {r["user_id"]: r for r in q(conn, """SELECT user_id::text AS user_id, started_at, break_started_at, break_seconds
                                                          FROM staff_time_sessions WHERE ended_at IS NULL""")}
        load = {r["uid"]: r for r in q(conn, """SELECT assigned_to::text AS uid, COUNT(*) AS open,
                                                       COUNT(*) FILTER (WHERE status='in_progress') AS in_progress,
                                                       COUNT(*) FILTER (WHERE status='waiting') AS waiting,
                                                       COUNT(*) FILTER (WHERE COALESCE(due_date, reminder_at) < %s) AS due_today
                                                FROM royan_tasks WHERE status IN %s AND kind<>'note' GROUP BY 1""",
                                         (local_midnight(today() + dt.timedelta(days=1)), OPEN_STATUSES))}
        done = {r["uid"]: int(r["n"]) for r in q(conn, """SELECT completed_by::text AS uid, COUNT(*) AS n FROM royan_tasks
                                                           WHERE status='completed' AND completed_at >= %s GROUP BY 1""", (local_midnight(ws),))}
        hours = {r["uid"]: float(r["h"]) for r in q(conn, """SELECT user_id::text AS uid, SUM(hours_worked) AS h FROM royan_timesheets
                                                             WHERE date >= %s AND status<>'rejected' AND user_id IS NOT NULL GROUP BY 1""", (ws,))}
    online = online_ids() | {me}   # whoever is looking at the page is online
    out = []
    for p in ppl:
        uid = p["user_id"]
        s = sessions.get(uid)
        status = ("on_break" if s and s["break_started_at"] else "working" if s else "online" if uid in online else "offline")
        live = _worked_seconds(s) if s else 0
        l = load.get(uid) or {}
        if p["on_leave"] and status in ("online", "offline"):
            status = "on_leave"
        out.append({**{k: p[k] for k in ("user_id", "name", "email", "department", "unit", "job_title", "phone", "roles")},
                    "me": uid == me, "status": status, "online": uid in online, "clocked_in_at": s["started_at"] if s else None,
                    "open_tasks": int(l.get("open") or 0), "in_progress": int(l.get("in_progress") or 0),
                    "waiting": int(l.get("waiting") or 0), "due_today": int(l.get("due_today") or 0),
                    "done_this_week": done.get(uid, 0), "hours_week": round(hours.get(uid, 0) + live / 3600, 1)})
    rank = {"working": 0, "on_break": 1, "online": 2, "on_leave": 3, "offline": 4}
    out.sort(key=lambda p: (not p["me"], rank[p["status"]], p["name"].lower()))
    return {"people": out, "working": sum(1 for p in out if p["status"] in ("working", "on_break")),
            "online": sum(1 for p in out if p["online"]), "departments": sorted({p["department"] for p in out})}


# ---------------------------------------------------------------------------
# Progress + journal
# ---------------------------------------------------------------------------

def _range(rng: str) -> tuple:
    t = today()
    if rng == "month":
        start = t.replace(day=1)
        prev = (start - dt.timedelta(days=1)).replace(day=1)
        return start, t, prev, start - dt.timedelta(days=1)
    start = week_start(t)
    return start, t, start - dt.timedelta(days=7), start - dt.timedelta(days=1)


def progress(user: Dict[str, Any], rng: str = "week") -> Dict[str, Any]:
    me = _me(user)
    start, end, pstart, pend = _range(rng)
    a, b = local_midnight(start), local_midnight(end + dt.timedelta(days=1))
    with tx() as conn:
        done = q(conn, """SELECT id::text AS id, title, department, source, kind, due_date, completed_at, entity_label
                          FROM royan_tasks WHERE completed_by=%s AND status='completed' AND completed_at >= %s AND completed_at < %s
                          ORDER BY completed_at DESC""", (me, a, b))
        prev_done = q1(conn, """SELECT COUNT(*) AS n FROM royan_tasks WHERE completed_by=%s AND status='completed'
                                AND completed_at >= %s AND completed_at < %s""", (me, local_midnight(pstart), local_midnight(pend + dt.timedelta(days=1))))["n"]
        now_open = q1(conn, """SELECT COUNT(*) AS open, COUNT(*) FILTER (WHERE status='waiting') AS waiting,
                                      COUNT(*) FILTER (WHERE status='in_progress') AS in_progress,
                                      COUNT(*) FILTER (WHERE COALESCE(due_date, reminder_at) < %s) AS overdue
                               FROM royan_tasks WHERE assigned_to=%s AND status IN %s""", (now(), me, OPEN_STATUSES))
        req = q1(conn, """SELECT COUNT(*) FILTER (WHERE responded_by=%s AND responded_at >= %s AND responded_at < %s) AS answered,
                                 COUNT(*) FILTER (WHERE from_user=%s AND created_at >= %s AND created_at < %s) AS sent,
                                 AVG(EXTRACT(EPOCH FROM responded_at - created_at)/3600)
                                   FILTER (WHERE responded_by=%s AND responded_at >= %s AND responded_at < %s) AS avg_hours
                          FROM staff_requests""", (me, a, b, me, a, b, me, a, b))
        ts = q(conn, """SELECT date, SUM(hours_worked) AS h FROM royan_timesheets WHERE user_id=%s AND date BETWEEN %s AND %s
                        AND status<>'rejected' GROUP BY date""", (me, start, end))
        view = clock_view(conn, me)
    with_due = [t for t in done if t["due_date"]]
    on_time = [t for t in with_due if t["completed_at"] <= t["due_date"] + dt.timedelta(hours=7)]  # same working day counts
    hours_by_day = {r["date"]: float(r["h"]) for r in ts}
    live_today = view["today_seconds"] / 3600 - hours_by_day.get(today(), 0) if view["session"] else 0
    days = []
    d = start
    while d <= end:
        days.append({"date": d, "completed": sum(1 for t in done if t["completed_at"].astimezone(TZ).date() == d),
                     "hours": round(hours_by_day.get(d, 0) + (live_today if d == today() else 0), 2)})
        d += dt.timedelta(days=1)
    by_dept: Dict[str, int] = defaultdict(int)
    by_source: Dict[str, int] = defaultdict(int)
    for t in done:
        by_dept[t["department"] or "General"] += 1
        by_source[{"operational": "Operational items", "request": "Requests from colleagues", "assigned": "Given by colleagues"}
                  .get(t["source"], "My own tasks")] += 1
    return {
        "range": rng, "from": start, "to": end,
        "completed": len(done), "completed_prev": int(prev_done or 0),
        "on_time_pct": round(100 * len(on_time) / len(with_due)) if with_due else None, "with_due": len(with_due),
        "requests_answered": int(req["answered"] or 0), "requests_sent": int(req["sent"] or 0),
        "avg_answer_hours": round(float(req["avg_hours"]), 1) if req["avg_hours"] is not None else None,
        "open": int(now_open["open"] or 0), "waiting": int(now_open["waiting"] or 0),
        "in_progress": int(now_open["in_progress"] or 0), "overdue": int(now_open["overdue"] or 0),
        "hours": round(sum(x["hours"] for x in days), 2),
        "days": days,
        "by_department": sorted(({"name": k, "count": v} for k, v in by_dept.items()), key=lambda x: -x["count"]),
        "by_source": sorted(({"name": k, "count": v} for k, v in by_source.items()), key=lambda x: -x["count"]),
        "accomplishments": done[:12],
    }


def work_journal(user: Dict[str, Any], rng: str = "today") -> List[Dict[str, Any]]:
    me = _me(user)
    t = today()
    start = t if rng == "today" else (week_start(t) if rng == "week" else t.replace(day=1))
    with tx() as conn:
        return q(conn, """SELECT id, kind, summary, entity_type, entity_id, occurred_at FROM staff_work_events
                          WHERE user_id=%s AND occurred_at >= %s ORDER BY occurred_at DESC LIMIT 300""", (me, local_midnight(start)))


# ---------------------------------------------------------------------------
# My Day
# ---------------------------------------------------------------------------

def my_day(user: Dict[str, Any]) -> Dict[str, Any]:
    me = _me(user)
    t = today()
    t0, t1 = local_midnight(t), local_midnight(t + dt.timedelta(days=1))
    with tx() as conn:
        ensure_profile(conn, me)
        profile = next((p for p in people(conn) if p["user_id"] == me), None) or {}
        clock = clock_view(conn, me)
        # royan_calendar_events has no owner column: an event is mine when I am an attendee
        events = q(conn, """SELECT id::text AS id, title, event_type, start_time, end_time, location FROM royan_calendar_events
                            WHERE start_time >= %s AND start_time < %s
                              AND (attendees::text ILIKE %s OR metadata->>'created_by' = %s OR event_type IN ('holiday'))
                            ORDER BY start_time""", (t0, t1, f"%{me}%", me))
        # a doctor's booked clinic is part of their day
        if profile.get("staff_id"):
            events += q(conn, """SELECT 'appt:' || a.id AS id, concat_ws(' ', p.first_name, p.last_name) || ' · ' ||
                                        COALESCE(a.appointment_type, 'appointment') AS title, 'appointment' AS event_type,
                                        (s.slot_date + s.slot_time) AT TIME ZONE 'Africa/Lagos' AS start_time,
                                        (s.slot_date + s.slot_time + make_interval(mins => COALESCE(s.duration_mins, 15)))
                                          AT TIME ZONE 'Africa/Lagos' AS end_time, s.department AS location
                                 FROM royan_appointments a JOIN royan_appointment_slots s ON s.id=a.slot_id
                                 JOIN royan_patients p ON p.id=a.patient_id
                                 WHERE s.doctor_id=%s::uuid AND s.slot_date=%s AND a.status IN ('booked','confirmed','arrived')
                                 ORDER BY s.slot_time""", (profile["staff_id"], t))
        unread = q1(conn, """SELECT COUNT(*) AS n, COUNT(*) FILTER (WHERE level IN ('critical','action')) AS action
                             FROM staff_notifications WHERE user_id=%s AND read_at IS NULL""", (me,))
        attention = q(conn, """SELECT id, kind, level, title, body, link_type, link_id, created_at FROM staff_notifications
                               WHERE user_id=%s AND read_at IS NULL ORDER BY (level IN ('critical','action')) DESC, created_at DESC LIMIT 8""", (me,))
        journal_today = q(conn, """SELECT kind, summary, occurred_at FROM staff_work_events WHERE user_id=%s AND occurred_at >= %s
                                   ORDER BY occurred_at DESC LIMIT 12""", (me, t0))
    tasks = list_tasks(user)
    reqs = list_requests(user)
    sig = signals(user)
    msgs = conversations(user)
    open_ = tasks["open"]
    timeline = [{"type": "task", "at": x["when"], "task": x} for x in open_ if x["when"] and x["when"] < t1]
    timeline += [{"type": "event", "at": e["start_time"], "event": e} for e in events]
    timeline.sort(key=lambda i: i["at"])
    hour = now().astimezone(TZ).hour
    return {
        "greeting": "Good morning" if hour < 12 else "Good afternoon" if hour < 17 else "Good evening",
        "date": t, "me": {k: profile.get(k) for k in ("user_id", "staff_id", "name", "email", "department", "unit", "job_title", "roles")},
        "clock": clock,
        "counts": {"open": sum(1 for x in open_ if x["kind"] != "note"),
                   "due_today": sum(1 for x in open_ if x["due_today"] or x["overdue"]),
                   "overdue": sum(1 for x in open_ if x["overdue"]),
                   "in_progress": sum(1 for x in open_ if x["status"] == "in_progress"),
                   "waiting": sum(1 for x in open_ if x["status"] == "waiting")
                              + sum(1 for r in reqs["outgoing"] if r["status"] in ("sent", "acknowledged", "in_progress")),
                   "to_answer": sum(1 for r in reqs["incoming"] if r["mine_to_answer"]),
                   "done_today": sum(1 for x in tasks["completed"] if x["completed_at"] and x["completed_at"] >= t0),
                   "unread": int(unread["n"] or 0), "unread_action": int(unread["action"] or 0),
                   "unread_messages": msgs["unread"]},
        "timeline": timeline,
        "no_date": [x for x in open_ if not x["when"]][:12],
        "upcoming": [x for x in open_ if x["when"] and x["when"] >= t1][:8],
        "to_answer": [r for r in reqs["incoming"] if r["mine_to_answer"]][:6],
        "waiting_on_others": [r for r in reqs["outgoing"] if r["status"] in ("sent", "acknowledged", "in_progress")][:6],
        "answered": [r for r in reqs["outgoing"] if r["status"] == "responded"][:6],
        "attention": attention,
        "operational": sig,
        "journal": journal_today,
    }


# ---------------------------------------------------------------------------
# Preferences
# ---------------------------------------------------------------------------

DEFAULT_PREFS = {"show_operational": True, "show_team": True, "show_journal": True, "task_order": "due", "default_tab": "day"}


def get_prefs(user: Dict[str, Any]) -> Dict[str, Any]:
    me = _me(user)
    with tx() as conn:
        r = q1(conn, "SELECT prefs FROM staff_preferences WHERE user_id=%s", (me,))
    return {**DEFAULT_PREFS, **((r or {}).get("prefs") or {})}


def set_prefs(user: Dict[str, Any], data: Dict[str, Any]) -> Dict[str, Any]:
    me = _me(user)
    clean = {k: data[k] for k in DEFAULT_PREFS if k in data}
    with tx() as conn:
        ex(conn, """INSERT INTO staff_preferences (user_id, prefs) VALUES (%s, %s::jsonb)
                    ON CONFLICT (user_id) DO UPDATE SET prefs = staff_preferences.prefs || EXCLUDED.prefs, updated_at=now()""",
           (me, json.dumps(clean)))
    return get_prefs(user)


# ---------------------------------------------------------------------------
# Leave (self-service; HR decides on the HR page)
# ---------------------------------------------------------------------------
# The same royan_leave_requests HR has always used: a request made here is the
# one HR sees under Leave, and HR's decision lands back in this person's Inbox.

LEAVE_TYPES = ("annual", "sick", "maternity", "paternity", "emergency", "unpaid")


def my_leave(user: Dict[str, Any]) -> Dict[str, Any]:
    me = _me(user)
    with tx() as conn:
        staff_id = ensure_profile(conn, me)
        rows = q(conn, """SELECT id::text AS id, leave_type, start_date, end_date, days_count, status, reason, created_at
                          FROM royan_leave_requests WHERE staff_id=%s::uuid ORDER BY start_date DESC LIMIT 30""", (staff_id,))
    yr = today().year
    taken = sum(float(r["days_count"]) for r in rows if r["status"] == "approved" and r["leave_type"] == "annual"
                and r["start_date"].year == yr)
    return {"requests": rows, "annual_days_taken": taken, "types": LEAVE_TYPES}


def request_leave(user: Dict[str, Any], data: Dict[str, Any]) -> Dict[str, Any]:
    me = _me(user)
    kind = data.get("leave_type") or "annual"
    if kind not in LEAVE_TYPES:
        raise ValueError("Unknown leave type")
    try:
        start = dt.date.fromisoformat(str(data.get("start_date"))[:10])
        end = dt.date.fromisoformat(str(data.get("end_date") or data.get("start_date"))[:10])
    except ValueError:
        raise ValueError("Give the first and last day of your leave")
    if end < start:
        raise ValueError("The last day is before the first day")
    days = (end - start).days + 1
    with tx() as conn:
        staff_id = ensure_profile(conn, me)
        if q1(conn, """SELECT 1 FROM royan_leave_requests WHERE staff_id=%s::uuid AND status IN ('pending','approved')
                       AND start_date <= %s AND end_date >= %s""", (staff_id, end, start)):
            raise WorkspaceError("You already have leave requested for some of these days")
        r = q1(conn, """INSERT INTO royan_leave_requests (staff_id, leave_type, start_date, end_date, days_count, reason, status)
                        VALUES (%s::uuid, %s, %s, %s, %s, %s, 'pending') RETURNING id::text AS id""",
               (staff_id, kind, start, end, days, (data.get("reason") or "").strip() or None))
        who = _names(conn, [me])[me]
        notify(conn, _dept_members(conn, "HR"), "leave", "action", f"{who} asks for {days} day(s) {kind} leave",
               f"{start:%d %b} – {end:%d %b}" + (f": {data.get('reason')}" if data.get("reason") else ""), "page", "/hr?tab=leave", me)
        journal(conn, me, "leave_requested", f"Asked for {kind} leave {start:%d %b}–{end:%d %b}", "leave_request", r["id"])
    refresh_rules("hr.leave")
    return my_leave(user)
