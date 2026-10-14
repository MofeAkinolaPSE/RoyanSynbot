"""HR, read from what people actually do in Royan.

  Overview    who is online now, who is on the clock (live, before it is saved),
              hours this week per person (saved timesheets + the running clock),
              summed for the headline number; team split; exceptions.
  Directory   everyone registered on User Access (plus HR-only records), with
              their profile, status today and workload - not a separate list.
  Timesheets  entries written when people clock out (or HR adds one), reviewed
              and approved here, exportable per week.

  Payroll     drafted from each person's monthly gross on their HR record plus
              overtime from their approved timesheets; approved (salary cost
              into Roy Books) and paid (cleared against the bank) - see
              fin/integrations.py PAYROLL / PAYROLL_PAYMENT.

Same tables as the Staff Workspace (staff_workspace.py): nothing is copied.
"""
from __future__ import annotations

import csv
import datetime as dt
import io
from collections import defaultdict
from typing import Any, Dict, List, Optional

from src.fin.db import ex, q, q1, tx
from src.db import audit_event
from src.services.staff_workspace import (DEPARTMENTS, DEPT_ROLES, TZ, _dept_members, _is_uuid, _me, _worked_seconds,
                                          ensure_profile, local_midnight, notify, now, online_ids, people, person_map,
                                          refresh_rules, today, week_start, WorkspaceError, OPEN_STATUSES)

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _week(ws: Optional[str]) -> dt.date:
    return week_start(dt.date.fromisoformat(ws[:10])) if ws else week_start()


def _entries(conn, start: dt.date, end: dt.date) -> List[Dict[str, Any]]:
    # hours_worked can be NULL on a row written by the old clock that was never closed: it counts as 0
    return q(conn, """SELECT t.id::text AS id, COALESCE(t.user_id::text, 'staff:' || t.staff_id::text) AS person,
                             t.user_id::text AS user_id, t.staff_id::text AS staff_id, t.date, COALESCE(t.hours_worked, 0) AS hours_worked,
                             t.department, t.notes AS activity_note, t.shift, t.clock_in, t.clock_out, t.source, t.status,
                             t.recorded_by, t.approved_by::text AS approved_by, t.approved_at, t.review_note, t.created_at,
                             t.session_id::text AS session_id
                      FROM royan_timesheets t WHERE t.date BETWEEN %s AND %s AND NOT t.absent
                      ORDER BY t.date, t.created_at""", (start, end))


def _open_sessions(conn) -> Dict[str, Dict[str, Any]]:
    return {r["user_id"]: r for r in q(conn, """SELECT id::text AS id, user_id::text AS user_id, started_at, break_started_at,
                                                        break_seconds, department FROM staff_time_sessions WHERE ended_at IS NULL""")}


def _live_by_day(s: Dict[str, Any]) -> Dict[dt.date, float]:
    """Hours of a running clock per local day (so far)."""
    out: Dict[dt.date, float] = {}
    total = _worked_seconds(s)
    t0 = local_midnight(today())
    today_part = total if s["started_at"] >= t0 else max(0.0, total - _worked_seconds(s, t0))
    out[today()] = today_part / 3600
    if total - today_part > 0:
        out[(t0 - dt.timedelta(seconds=1)).astimezone(TZ).date()] = (total - today_part) / 3600
    return out


def overview(week: Optional[str] = None) -> Dict[str, Any]:
    ws = _week(week)
    we = ws + dt.timedelta(days=6)
    is_current = ws == week_start()
    with tx() as conn:
        ppl = people(conn)
        entries = _entries(conn, ws, we)
        sessions = _open_sessions(conn) if is_current else {}
        trend_rows = q(conn, """SELECT date_trunc('week', date)::date AS wk, SUM(hours_worked) AS h,
                                       COUNT(DISTINCT COALESCE(user_id::text, staff_id::text)) AS people
                                FROM royan_timesheets WHERE status<>'rejected' AND date >= %s AND date <= %s GROUP BY 1""",
                           (ws - dt.timedelta(weeks=7), we))
        pending = q1(conn, """SELECT COUNT(*) AS n, COALESCE(SUM(hours_worked),0) AS h FROM royan_timesheets WHERE status='submitted'""")
    online = online_ids()
    grid = []
    dept_hours: Dict[str, float] = defaultdict(float)
    saved_total = live_total = 0.0
    for p in ppl:
        days = {d: 0.0 for d in DAYS}
        saved = 0.0
        for e in entries:
            if e["person"] == p["key"] and e["status"] != "rejected":
                h = float(e["hours_worked"])
                days[DAYS[e["date"].weekday()]] += h
                saved += h
                dept_hours[e["department"] or p["department"]] += h
        s = sessions.get(p["user_id"]) if p["user_id"] else None
        live = 0.0
        if s:
            for d, h in _live_by_day(s).items():
                if ws <= d <= we:
                    days[DAYS[d.weekday()]] += h
                    live += h
            dept_hours[s["department"] or p["department"]] += live
        saved_total += saved
        live_total += live
        status = ("on_break" if s and s["break_started_at"] else "working" if s else
                  "online" if p["user_id"] in online else "offline")
        total = saved + live
        grid.append({"key": p["key"], "user_id": p["user_id"], "name": p["name"], "department": p["department"],
                     "job_title": p["job_title"], "has_login": p["has_login"], "status": status,
                     "clocked_in_at": s["started_at"] if s else None, "days": {d: round(v, 2) for d, v in days.items()},
                     "saved": round(saved, 2), "live": round(live, 2), "total": round(total, 2),
                     "target": p["weekly_hours"], "pct": round(100 * total / p["weekly_hours"]) if p["weekly_hours"] else None,
                     "pending": sum(1 for e in entries if e["person"] == p["key"] and e["status"] == "submitted")})
    grid.sort(key=lambda r: (-r["total"], r["name"].lower()))
    on_clock = [r for r in grid if r["status"] in ("working", "on_break")]
    long_clocks = [r for r in on_clock if r["clocked_in_at"] and now() - r["clocked_in_at"] > dt.timedelta(hours=12)]
    trend = {r["wk"]: r for r in trend_rows}
    weeks = []
    for i in range(7, -1, -1):
        w = ws - dt.timedelta(weeks=i)
        r = trend.get(w)
        h = float(r["h"]) if r else 0.0
        if w == ws:
            h += live_total
        weeks.append({"week": w, "hours": round(h, 1), "people": int(r["people"]) if r else 0})
    worked_days = defaultdict(float)
    for r in grid:
        for d, h in r["days"].items():
            worked_days[d] += h
    return {
        "week": ws, "week_end": we, "is_current": is_current, "as_of": now(),
        "headcount": len(ppl), "with_login": sum(1 for p in ppl if p["has_login"]),
        "online": [{"user_id": r["user_id"], "name": r["name"], "department": r["department"], "status": r["status"]}
                   for r in grid if r["user_id"] in online],
        "on_clock": [{k: r[k] for k in ("key", "name", "department", "status", "clocked_in_at")} for r in on_clock],
        "hours_total": round(saved_total + live_total, 2), "hours_saved": round(saved_total, 2), "hours_live": round(live_total, 2),
        "people_with_hours": sum(1 for r in grid if r["total"] > 0),
        "avg_per_person": round((saved_total + live_total) / max(1, sum(1 for r in grid if r["total"] > 0)), 1),
        "pending_approval": {"entries": int(pending["n"] or 0), "hours": float(pending["h"] or 0)},
        "long_clocks": [{k: r[k] for k in ("key", "name", "clocked_in_at")} for r in long_clocks],
        "grid": grid,
        "by_day": [{"day": d, "hours": round(worked_days[d], 2)} for d in DAYS],
        "by_department": sorted(({"department": k, "hours": round(v, 2)} for k, v in dept_hours.items() if v > 0),
                                key=lambda x: -x["hours"]),
        "weeks": weeks,
    }


def directory() -> Dict[str, Any]:
    ws = week_start()
    with tx() as conn:
        ppl = people(conn, include_inactive=True)
        sessions = _open_sessions(conn)
        hours = {r["person"]: float(r["h"]) for r in q(conn, """SELECT COALESCE(user_id::text, 'staff:' || staff_id::text) AS person,
                                                                        SUM(hours_worked) AS h FROM royan_timesheets
                                                                 WHERE date >= %s AND status<>'rejected' GROUP BY 1""", (ws,))}
        load = {r["uid"]: r for r in q(conn, """SELECT assigned_to::text AS uid, COUNT(*) AS open,
                                                       COUNT(*) FILTER (WHERE COALESCE(due_date, reminder_at) < %s) AS overdue
                                                FROM royan_tasks WHERE status IN %s AND kind<>'note' GROUP BY 1""",
                                         (now(), OPEN_STATUSES))}
        last = {r["uid"]: r["at"] for r in q(conn, """SELECT user_id::text AS uid, MAX(started_at) AS at FROM staff_time_sessions GROUP BY 1""")}
    online = online_ids()
    out = []
    for p in ppl:
        s = sessions.get(p["user_id"]) if p["user_id"] else None
        live = _worked_seconds(s) / 3600 if s else 0
        l = load.get(p["user_id"]) or {}
        out.append({**p, "status": ("on_break" if s and s["break_started_at"] else "working" if s else
                                    "online" if p["user_id"] in online else "offline") if p["active"] else "inactive",
                    "hours_week": round(hours.get(p["key"], 0) + live, 1), "open_tasks": int(l.get("open") or 0),
                    "overdue_tasks": int(l.get("overdue") or 0), "last_clock_in": last.get(p["user_id"])})
    depts = defaultdict(int)
    for p in out:
        if p["active"]:
            depts[p["department"]] += 1
    return {"people": out, "departments": DEPARTMENTS,
            "by_department": sorted(({"department": k, "count": v} for k, v in depts.items()), key=lambda x: -x["count"]),
            "counts": {"active": sum(1 for p in out if p["active"]), "inactive": sum(1 for p in out if not p["active"]),
                       "no_login": sum(1 for p in out if not p["has_login"]),
                       "working": sum(1 for p in out if p["status"] in ("working", "on_break")),
                       "online": sum(1 for p in out if p["status"] != "offline" and p["status"] != "inactive")}}


def _resolve(conn, key: str) -> Dict[str, Any]:
    pm = person_map(conn)
    p = pm.get(key)
    if not p:
        raise LookupError("Staff member not found")
    return p


def person(key: str) -> Dict[str, Any]:
    ws = week_start()
    with tx() as conn:
        p = _resolve(conn, key)
        entries = q(conn, """SELECT id::text AS id, date, COALESCE(hours_worked, 0) AS hours_worked, department,
                                    notes AS activity_note, source, status, review_note, approved_at
                             FROM royan_timesheets WHERE (user_id::text=%s OR ('staff:' || staff_id::text)=%s)
                               AND date >= %s AND NOT absent ORDER BY date DESC, created_at DESC""",
                    (p["user_id"] or "", key, ws - dt.timedelta(weeks=8)))
        pay = q(conn, """SELECT id::text AS id, period_year, period_month, gross_salary, net_salary, status, payment_date
                         FROM royan_payroll_records WHERE staff_id::text=%s ORDER BY period_year DESC, period_month DESC LIMIT 12""",
                (p["staff_id"] or "",))
        leave = q(conn, """SELECT id::text AS id, leave_type, start_date, end_date, days_count, status FROM royan_leave_requests
                           WHERE staff_id::text=%s ORDER BY start_date DESC LIMIT 12""", (p["staff_id"] or "",))
        sessions = q(conn, """SELECT id::text AS id, started_at, ended_at, break_seconds, breaks, note FROM staff_time_sessions
                              WHERE user_id::text=%s ORDER BY started_at DESC LIMIT 20""", (p["user_id"] or "",))
        work = q1(conn, """SELECT COUNT(*) FILTER (WHERE status IN %s AND kind<>'note') AS open,
                                  COUNT(*) FILTER (WHERE status='completed' AND completed_by::text=%s AND completed_at >= %s) AS done_week,
                                  COUNT(*) FILTER (WHERE status='completed' AND completed_by::text=%s AND completed_at >= now() - interval '30 days') AS done_30d
                           FROM royan_tasks WHERE assigned_to::text=%s OR completed_by::text=%s""",
                   (OPEN_STATUSES, p["user_id"] or "", local_midnight(ws), p["user_id"] or "", p["user_id"] or "", p["user_id"] or ""))
        reqs = q1(conn, """SELECT COUNT(*) FILTER (WHERE responded_by::text=%s AND responded_at > now() - interval '30 days') AS answered
                           FROM staff_requests""", (p["user_id"] or "",))
        open_s = _open_sessions(conn).get(p["user_id"]) if p["user_id"] else None
    weeks = []
    for i in range(7, -1, -1):
        w = ws - dt.timedelta(weeks=i)
        h = sum(float(e["hours_worked"]) for e in entries if w <= e["date"] <= w + dt.timedelta(days=6) and e["status"] != "rejected")
        weeks.append({"week": w, "hours": round(h, 2)})
    live = _live_by_day(open_s) if open_s else {}
    days = []
    for i in range(7):
        d = ws + dt.timedelta(days=i)
        h = sum(float(e["hours_worked"]) for e in entries if e["date"] == d and e["status"] != "rejected") + live.get(d, 0)
        days.append({"day": DAYS[i], "date": d, "hours": round(h, 2)})
    weeks[-1]["hours"] = round(weeks[-1]["hours"] + sum(v for d, v in live.items() if d >= ws), 2)
    for s in sessions:
        end = s["ended_at"] or now()
        s["worked_seconds"] = int(max(0, (end - s["started_at"]).total_seconds() - s["break_seconds"]))
    return {**p, "clock": None if not open_s else {"started_at": open_s["started_at"], "on_break": bool(open_s["break_started_at"]),
                                                   "worked_seconds": int(_worked_seconds(open_s))},
            "status": "working" if open_s else ("online" if p["user_id"] in online_ids() else "offline"),
            "week_days": days, "weeks": weeks, "entries": entries[:40], "sessions": sessions, "payroll": pay, "leave": leave,
            "work": {"open_tasks": int(work["open"] or 0), "done_week": int(work["done_week"] or 0),
                     "done_30d": int(work["done_30d"] or 0), "requests_answered_30d": int(reqs["answered"] or 0)}}


def update_person(user: Dict[str, Any], key: str, data: Dict[str, Any]) -> Dict[str, Any]:
    with tx() as conn:
        p = _resolve(conn, key)
        staff_id = p["staff_id"] or ensure_profile(conn, p["user_id"])
        sets, vals = [], []
        # `department` is the team (derived from the HR record's role); `unit` is royan_staff.department
        fields = {"name": "full_name", "unit": "department", "job_title": "designation", "phone": "phone",
                  "start_date": "joined_at", "weekly_hours": "weekly_hours", "monthly_gross": "monthly_gross",
                  "employment_type": "employment_type"}
        for k, col in fields.items():
            if k in data:
                v = data[k]
                if isinstance(v, str):
                    v = v.strip() or None
                if k == "name" and not v:
                    raise ValueError("A name is required")
                if k in ("unit", "job_title") and not v:
                    raise ValueError("A unit and a job title are required on the HR record")
                if k == "weekly_hours" and (v is None or not 0 < float(v) <= 80):
                    raise ValueError("Weekly hours must be between 1 and 80")
                if k == "monthly_gross" and (v is None or float(v) < 0):
                    raise ValueError("Monthly gross pay cannot be negative")
                if k == "employment_type" and v not in ("full_time", "part_time", "contract", "locum"):
                    raise ValueError("Unknown employment type")
                sets.append(f"{col}=%s"); vals.append(v)
        if data.get("department"):
            if data["department"] not in DEPARTMENTS:
                raise ValueError("Unknown team")
            sets.append("role=%s"); vals.append(next(iter(DEPT_ROLES[data["department"]])))
        if "active" in data and not p["has_login"]:
            sets.append("is_active=%s"); vals.append(bool(data["active"]))
        if sets:
            ex(conn, f"UPDATE royan_staff SET {', '.join(sets)}, updated_at=now() WHERE id=%s::uuid", (*vals, staff_id))
    if sets:
        audit_event("hr_profile_updated", {k: str(data[k]) for k in data if k in fields or k in ("department", "active")},
                    actor_id=str(user.get("sub")), subject_type="staff", subject_id=staff_id)
    return person(key)


def create_person(user: Dict[str, Any], data: Dict[str, Any]) -> Dict[str, Any]:
    """HR-only record (someone without a login yet). Linked automatically when a login with that email is created."""
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    if not name or "@" not in email:
        raise ValueError("Name and email are required")
    if data.get("department") not in DEPARTMENTS:
        raise ValueError("Choose a team")
    role = next(iter(DEPT_ROLES[data["department"]]))
    with tx() as conn:
        if q1(conn, "SELECT 1 FROM royan_staff WHERE lower(email)=%s AND quarantined_at IS NULL", (email,)):
            raise ValueError("A staff record with this email already exists")
        u = q1(conn, "SELECT id::text AS id FROM royan_users WHERE lower(email)=%s", (email,))
        n = q1(conn, "SELECT COUNT(*) + 1 AS n FROM royan_staff WHERE staff_number LIKE 'HR-%%'")["n"]
        r = q1(conn, """INSERT INTO royan_staff (staff_number, full_name, email, department, designation, role, phone,
                                                 monthly_gross, user_id)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id::text AS staff_id""",
               (f"HR-{int(n):05d}", name, email, (data.get("unit") or "").strip() or data["department"],
                (data.get("job_title") or "").strip() or "Staff", role, (data.get("phone") or "").strip() or None,
                float(data.get("monthly_gross") or 0), u["id"] if u else None))
    audit_event("hr_staff_created", {"name": name, "team": data["department"]}, actor_id=str(user.get("sub")),
                subject_type="staff", subject_id=r["staff_id"])
    return person(u["id"] if u else f"staff:{r['staff_id']}")


# ---------------------------------------------------------------------------
# Timesheets
# ---------------------------------------------------------------------------

def timesheets(week: Optional[str] = None, person_key: Optional[str] = None, status: Optional[str] = None) -> Dict[str, Any]:
    ws = _week(week)
    we = ws + dt.timedelta(days=6)
    with tx() as conn:
        rows = _entries(conn, ws, we)
        pm = person_map(conn)
        sessions = _open_sessions(conn) if ws == week_start() else {}
    approver_names = {k: v["name"] for k, v in pm.items()}
    out = []
    for r in rows:
        if person_key and r["person"] != person_key:
            continue
        if status and r["status"] != status:
            continue
        p = pm.get(r["person"], {})
        r["name"] = p.get("name", "Unknown")
        r["person_department"] = p.get("department")
        r["approved_by_name"] = approver_names.get(r["approved_by"]) if r["approved_by"] else None
        r["recorded_by_name"] = approver_names.get(r["recorded_by"] or "", None)
        out.append(r)
    live = []
    for uid, s in sessions.items():
        if person_key and person_key != uid:
            continue
        live.append({"person": uid, "name": pm.get(uid, {}).get("name", "Unknown"), "started_at": s["started_at"],
                     "on_break": bool(s["break_started_at"]), "hours_so_far": round(_worked_seconds(s) / 3600, 2),
                     "department": s["department"]})
    per: Dict[str, Dict[str, Any]] = {}
    for r in out:
        g = per.setdefault(r["person"], {"person": r["person"], "name": r["name"], "hours": 0.0, "approved": 0.0,
                                         "submitted": 0.0, "rejected": 0.0, "entries": 0})
        g["entries"] += 1
        g[r["status"]] += float(r["hours_worked"])
        if r["status"] != "rejected":
            g["hours"] += float(r["hours_worked"])
    for l in live:
        g = per.setdefault(l["person"], {"person": l["person"], "name": l["name"], "hours": 0.0, "approved": 0.0,
                                         "submitted": 0.0, "rejected": 0.0, "entries": 0})
        g["live"] = l["hours_so_far"]
    return {"week": ws, "week_end": we, "entries": out, "live": live,
            "people": sorted(per.values(), key=lambda g: -(g["hours"] + g.get("live", 0))),
            "totals": {"hours": round(sum(g["hours"] for g in per.values()), 2),
                       "live": round(sum(l["hours_so_far"] for l in live), 2),
                       "submitted": round(sum(g["submitted"] for g in per.values()), 2),
                       "approved": round(sum(g["approved"] for g in per.values()), 2)}}


def add_entry(user: Dict[str, Any], data: Dict[str, Any]) -> Dict[str, Any]:
    """HR records hours for someone (e.g. a missed clock-in). Approved as it is entered by HR."""
    me = _me(user)
    hours = float(data.get("hours") or 0)
    if not 0 < hours <= 24:
        raise ValueError("Hours must be more than 0 and at most 24")
    d = dt.date.fromisoformat(str(data.get("date"))[:10])
    if d > today():
        raise ValueError("Hours cannot be recorded for a future date")
    with tx() as conn:
        p = _resolve(conn, str(data.get("person") or ""))
        staff_id = p["staff_id"] or ensure_profile(conn, p["user_id"])
        r = q1(conn, """INSERT INTO royan_timesheets (staff_id, user_id, date, shift, hours_worked, department, notes, recorded_by,
                                                      source, status, approved, approved_by, approved_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'hr', 'approved', TRUE, %s, now()) RETURNING id::text AS id""",
               (staff_id, p["user_id"], d, data.get("shift") if data.get("shift") in ("day", "night", "on_call") else "day",
                round(hours, 2), data.get("department") or p["department"],
                (data.get("note") or "").strip() or "Recorded by HR", me, me))
    return {"id": r["id"]}


def review(user: Dict[str, Any], entry_id: str, action: str, data: Dict[str, Any]) -> Dict[str, Any]:
    me = _me(user)
    note = (data.get("note") or "").strip() or None
    with tx() as conn:
        e = q1(conn, """SELECT id, status, COALESCE(hours_worked, 0) AS hours_worked, user_id::text AS user_id
                        FROM royan_timesheets WHERE id=%s::uuid FOR UPDATE""", (entry_id,)) if _is_uuid(entry_id) else None
        if not e:
            raise LookupError("Timesheet entry not found")
        if action == "approve":
            ex(conn, """UPDATE royan_timesheets SET status='approved', approved=TRUE, approved_by=%s, approved_at=now(),
                               review_note=COALESCE(%s, review_note), updated_at=now() WHERE id=%s::uuid""", (me, note, entry_id))
        elif action == "reject":
            if not note:
                raise ValueError("Say why the entry is rejected")
            ex(conn, """UPDATE royan_timesheets SET status='rejected', approved=FALSE, approved_by=%s, approved_at=now(),
                               review_note=%s, updated_at=now() WHERE id=%s::uuid""", (me, note, entry_id))
        elif action == "adjust":
            hours = float(data.get("hours") or 0)
            if not 0 < hours <= 24:
                raise ValueError("Hours must be more than 0 and at most 24")
            if not note:
                raise ValueError("Say why the hours are changed")
            ex(conn, """UPDATE royan_timesheets SET hours_worked=%s, status='approved', approved=TRUE, approved_by=%s,
                               approved_at=now(), review_note=%s, updated_at=now() WHERE id=%s::uuid""",
               (round(hours, 2), me, f"{float(e['hours_worked']):g}h → {hours:g}h: {note}", entry_id))
        else:
            raise ValueError("Unknown action")
        if e["user_id"] and action in ("reject", "adjust"):
            notify(conn, [e["user_id"]], "hr", "action" if action == "reject" else "info",
                   f"Your timesheet was {'rejected' if action == 'reject' else 'adjusted'} by HR", note, "page", "/workspace?tab=progress", me)
    refresh_rules("hr.timesheets")
    return {"ok": True}


def approve_week(user: Dict[str, Any], person_key: Optional[str], week: Optional[str]) -> Dict[str, Any]:
    me = _me(user)
    ws = _week(week)
    with tx() as conn:
        r = q1(conn, """WITH u AS (UPDATE royan_timesheets SET status='approved', approved=TRUE, approved_by=%s, approved_at=now()
                                   WHERE status='submitted' AND date BETWEEN %s AND %s
                                     AND (%s::text IS NULL OR COALESCE(user_id::text, 'staff:' || staff_id::text)=%s)
                                   RETURNING 1) SELECT COUNT(*) AS n FROM u""",
               (me, ws, ws + dt.timedelta(days=6), person_key, person_key))
    refresh_rules("hr.timesheets")
    return {"approved": int(r["n"])}


def timesheets_csv(week: Optional[str] = None) -> str:
    data = timesheets(week)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Name", "Department", "Date", "Hours", "Source", "Status", "Note", "Reviewed by", "Review note"])
    for e in data["entries"]:
        w.writerow([e["name"], e["department"], e["date"], f"{float(e['hours_worked']):g}", e["source"], e["status"],
                    e["activity_note"] or "", e["approved_by_name"] or "", e["review_note"] or ""])
    for l in data["live"]:
        w.writerow([l["name"], l["department"] or "", today(), f"{l['hours_so_far']:g}", "clock (running)", "not yet saved", "", "", ""])
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Payroll: HR record + approved timesheets -> draft -> approved -> paid (Roy Books)
# ---------------------------------------------------------------------------
# The draft is a starting point HR completes, not a computed truth: PAYE and
# pension depend on reliefs only HR knows, so they start at 0 and are entered
# per person before approval. Overtime is a fact from the clock - approved hours
# above the person's contracted hours for the month - paid at their base hourly
# rate unless HR changes the rate.

PAYROLL_FIELDS = ("gross_salary", "overtime_hours", "overtime_rate", "allowances", "deductions", "tax", "pension", "notes")


def _period(period: Optional[str]) -> tuple:
    if period:
        y, m = (int(x) for x in str(period)[:7].split("-"))
    else:
        t = today().replace(day=1) - dt.timedelta(days=1)       # last month by default
        y, m = t.year, t.month
    if not (1 <= m <= 12 and 2000 <= y <= 2100):
        raise ValueError("Give the payroll month as YYYY-MM")
    first = dt.date(y, m, 1)
    last = dt.date(y + m // 12, m % 12 + 1, 1) - dt.timedelta(days=1)
    return y, m, first, last


def _weekdays(a: dt.date, b: dt.date) -> int:
    return sum(1 for i in range((b - a).days + 1) if (a + dt.timedelta(days=i)).weekday() < 5)


def _net(r: Dict[str, Any]) -> float:
    return round(float(r["gross_salary"] or 0) + float(r["overtime_hours"] or 0) * float(r["overtime_rate"] or 0)
                 + float(r["allowances"] or 0) - float(r["deductions"] or 0) - float(r["tax"] or 0) - float(r["pension"] or 0), 2)


def payroll_run(period: Optional[str] = None) -> Dict[str, Any]:
    y, m, first, last = _period(period)
    with tx() as conn:
        rows = q(conn, """SELECT p.id::text AS id, p.staff_id::text AS staff_id, s.full_name, s.staff_number, s.role, s.department AS unit,
                                 s.designation, p.gross_salary, p.overtime_hours, p.overtime_rate, p.allowances, p.deductions,
                                 p.tax, p.pension, p.net_salary, p.status, p.payment_date, p.payment_method, p.notes,
                                 p.approved_by, p.approved_at, p.paid_by, p.bank_account_id::text AS bank_account_id, p.source
                          FROM royan_payroll_records p JOIN royan_staff s ON s.id=p.staff_id
                          WHERE p.period_year=%s AND p.period_month=%s ORDER BY s.full_name""", (y, m))
        books = {(r["source_type"], r["source_id"]): r for r in q(conn, """
                    SELECT source_type, source_id, status, message, source_ref FROM fin_source_postings
                    WHERE source_type IN ('PAYROLL','PAYROLL_PAYMENT') AND source_id = ANY(%s)""", ([r["id"] for r in rows],))}
        missing = q1(conn, """SELECT COUNT(*) AS n FROM royan_staff s WHERE s.is_active AND s.quarantined_at IS NULL
                              AND s.monthly_gross > 0 AND NOT EXISTS (SELECT 1 FROM royan_payroll_records p WHERE p.staff_id=s.id
                              AND p.period_year=%s AND p.period_month=%s)""", (y, m))["n"]
        no_pay = q1(conn, """SELECT COUNT(*) AS n FROM royan_staff WHERE is_active AND quarantined_at IS NULL
                             AND COALESCE(monthly_gross, 0) = 0""")["n"]
        banks = q(conn, "SELECT id::text AS id, name FROM fin_bank_accounts ORDER BY name")
        live = q1(conn, "SELECT cutover_date FROM fin_settings LIMIT 1")
    for r in rows:
        for st in ("PAYROLL", "PAYROLL_PAYMENT"):
            b = books.get((st, r["id"]))
            r["books_" + ("cost" if st == "PAYROLL" else "payment")] = (
                {"status": b["status"], "message": b["message"], "ref": b["source_ref"]} if b else None)
        r["team"] = next((d for d, rs in DEPT_ROLES.items() if r["role"] in rs), None)
    tot = lambda k: round(sum(float(r[k] or 0) for r in rows), 2)
    return {"period": f"{y}-{m:02d}", "from": first, "to": last, "records": rows,
            "totals": {"gross": tot("gross_salary"), "net": tot("net_salary"), "tax": tot("tax"), "pension": tot("pension"),
                       "overtime": round(sum(float(r["overtime_hours"] or 0) * float(r["overtime_rate"] or 0) for r in rows), 2),
                       "draft": sum(1 for r in rows if r["status"] == "draft"),
                       "approved": sum(1 for r in rows if r["status"] == "approved"),
                       "paid": sum(1 for r in rows if r["status"] == "paid")},
            "not_prepared": int(missing or 0), "staff_without_pay": int(no_pay or 0), "banks": banks,
            "books_live": bool(live and live["cutover_date"]),
            "books_cutover": live["cutover_date"] if live else None}


def prepare_payroll(user: Dict[str, Any], period: Optional[str] = None) -> Dict[str, Any]:
    """Draft a record for everyone active with a monthly gross who has none for the month yet."""
    me = _me(user)
    y, m, first, last = _period(period)
    if first > today():
        raise ValueError("That month has not started yet")
    made = 0
    with tx() as conn:
        staff = q(conn, """SELECT s.id::text AS id, s.full_name, s.monthly_gross, s.weekly_hours FROM royan_staff s
                           WHERE s.is_active AND s.quarantined_at IS NULL AND s.monthly_gross > 0
                             AND NOT EXISTS (SELECT 1 FROM royan_payroll_records p WHERE p.staff_id=s.id
                                             AND p.period_year=%s AND p.period_month=%s)""", (y, m))
        hours = {r["staff_id"]: float(r["h"]) for r in q(conn, """
                    SELECT staff_id::text AS staff_id, SUM(hours_worked) AS h FROM royan_timesheets
                    WHERE status='approved' AND date BETWEEN %s AND %s AND NOT absent GROUP BY 1""", (first, last))}
        weekdays = _weekdays(first, last)
        for st in staff:
            gross = float(st["monthly_gross"])
            weekly = float(st["weekly_hours"] or 40)
            contracted = weekly * weekdays / 5
            worked = hours.get(st["id"], 0.0)
            ot = round(max(0.0, worked - contracted), 2) if worked else 0.0
            rate = round(gross / (weekly * 52 / 12), 2) if weekly else 0.0
            rec = {"gross_salary": gross, "overtime_hours": ot, "overtime_rate": rate if ot else 0.0, "allowances": 0,
                   "deductions": 0, "tax": 0, "pension": 0}
            note = (f"Prepared from the HR record. {worked:g}h approved against {contracted:g}h contracted"
                    + (f" -> {ot:g}h overtime at the base hourly rate" if ot else "") if worked
                    else "Prepared from the HR record. No approved timesheets this month, so no overtime.")
            ex(conn, """INSERT INTO royan_payroll_records (staff_id, period_month, period_year, gross_salary, overtime_hours,
                                                           overtime_rate, allowances, deductions, tax, pension, net_salary,
                                                           status, notes, source)
                        VALUES (%s::uuid, %s, %s, %s, %s, %s, 0, 0, 0, 0, %s, 'draft', %s, 'prepared')""",
               (st["id"], m, y, gross, ot, rec["overtime_rate"], _net(rec), note))
            made += 1
    refresh_rules("hr.payroll")
    audit_event("payroll_prepared", {"period": f"{y}-{m:02d}", "records": made}, actor_id=me,
                subject_type="payroll", subject_id=f"{y}-{m:02d}")
    return {**payroll_run(f"{y}-{m:02d}"), "prepared": made}


def _payroll_record(conn, rec_id: str, lock: bool = True) -> Dict[str, Any]:
    r = q1(conn, f"""SELECT p.*, p.id::text AS id, p.staff_id::text AS staff_id, s.full_name, s.user_id::text AS user_id
                     FROM royan_payroll_records p JOIN royan_staff s ON s.id=p.staff_id
                     WHERE p.id=%s::uuid {'FOR UPDATE OF p' if lock else ''}""", (rec_id,)) if _is_uuid(rec_id) else None
    if not r:
        raise LookupError("Payroll record not found")
    return r


def update_payroll(user: Dict[str, Any], rec_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    me = _me(user)
    with tx() as conn:
        r = _payroll_record(conn, rec_id)
        if r["status"] != "draft":
            raise WorkspaceError("Only a draft can be changed - an approved payroll is already in the books")
        for k in PAYROLL_FIELDS:
            if k in data:
                if k == "notes":
                    r[k] = (data[k] or "").strip() or None
                    continue
                v = float(data[k] or 0)
                if v < 0:
                    raise ValueError(f"{k.replace('_', ' ')} cannot be negative")
                r[k] = v
        net = _net(r)
        if net < 0:
            raise ValueError("Deductions are more than the pay")
        ex(conn, """UPDATE royan_payroll_records SET gross_salary=%s, overtime_hours=%s, overtime_rate=%s, allowances=%s,
                           deductions=%s, tax=%s, pension=%s, net_salary=%s, notes=%s, updated_at=now() WHERE id=%s::uuid""",
           (r["gross_salary"], r["overtime_hours"], r["overtime_rate"], r["allowances"], r["deductions"], r["tax"],
            r["pension"], net, r["notes"], rec_id))
    audit_event("payroll_updated", {k: data[k] for k in PAYROLL_FIELDS if k in data}, actor_id=me,
                subject_type="payroll", subject_id=rec_id)
    return {"ok": True, "net_salary": net}


def payroll_action(user: Dict[str, Any], rec_id: str, action: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """approve (HR/management) -> salary cost in the books; pay (HR/finance) -> cleared against the bank."""
    me = _me(user)
    roles = {str(x).lower() for x in user.get("roles") or []}
    hook = None
    with tx() as conn:
        r = _payroll_record(conn, rec_id)
        if action == "approve":
            if not roles & {"admin", "hr", "management"}:
                raise PermissionError("HR or management approves payroll")
            if r["status"] != "draft":
                raise WorkspaceError(f"This record is already {r['status']}")
            ex(conn, """UPDATE royan_payroll_records SET status='approved', approved_by=%s, approved_at=now(), updated_at=now()
                        WHERE id=%s::uuid""", (me, rec_id))
            hook = "PAYROLL"
        elif action == "pay":
            if not roles & {"admin", "hr", "finance"}:
                raise PermissionError("HR or finance marks payroll paid")
            if r["status"] != "approved":
                raise WorkspaceError("Approve the record before paying it")
            bank = data.get("bank_account_id")
            if bank and not (_is_uuid(bank) and q1(conn, "SELECT 1 FROM fin_bank_accounts WHERE id=%s::uuid", (bank,))):
                raise ValueError("Unknown bank account")
            pay_date = dt.date.fromisoformat(str(data.get("payment_date"))[:10]) if data.get("payment_date") else today()
            if pay_date > today():
                raise ValueError("A payment date cannot be in the future")
            method = data.get("payment_method") or "bank_transfer"
            if method not in ("bank_transfer", "cash", "cheque"):
                raise ValueError("Unknown payment method")
            ex(conn, """UPDATE royan_payroll_records SET status='paid', paid_by=%s, payment_date=%s, payment_method=%s,
                               bank_account_id=%s, updated_at=now() WHERE id=%s::uuid""",
               (me, pay_date, method, bank or None, rec_id))
            hook = "PAYROLL_PAYMENT"
            if r["user_id"]:
                notify(conn, [r["user_id"]], "payroll", "info",
                       f"Your {dt.date(r['period_year'], r['period_month'], 1):%B %Y} salary has been paid",
                       f"Net ₦{float(r['net_salary']):,.2f}", "page", "/workspace?tab=progress", me)
        elif action == "delete":
            if not roles & {"admin", "hr"}:
                raise PermissionError("HR removes payroll drafts")
            if r["status"] != "draft":
                raise WorkspaceError("Only a draft can be removed")
            ex(conn, "DELETE FROM royan_payroll_records WHERE id=%s::uuid", (rec_id,))
        else:
            raise ValueError("Unknown action")
    audit_event(f"payroll_{action}", {"staff": r["full_name"], "period": f"{r['period_year']}-{r['period_month']:02d}",
                                      "net": float(r["net_salary"])}, actor_id=me, subject_type="payroll", subject_id=rec_id)
    refresh_rules("hr.payroll", "finance.payroll_pay", "finance.books_failed")
    books = None
    if hook:
        # after our own commit, in the books' own transaction: a books problem never blocks HR
        from src.fin import integrations
        books = integrations.post(hook, rec_id, actor=me)
    return {"ok": True, "books": books}


def payroll_bulk(user: Dict[str, Any], period: Optional[str], action: str, data: Dict[str, Any]) -> Dict[str, Any]:
    y, m, _, _ = _period(period)
    want = {"approve": "draft", "pay": "approved"}.get(action)
    if not want:
        raise ValueError("Unknown action")
    with tx() as conn:
        ids = [r["id"] for r in q(conn, """SELECT id::text AS id FROM royan_payroll_records WHERE period_year=%s
                                          AND period_month=%s AND status=%s""", (y, m, want))]
    out = {"done": 0, "books": {}}
    for i in ids:
        r = payroll_action(user, i, action, data)
        out["done"] += 1
        st = (r.get("books") or {}).get("status") or "NONE"
        out["books"][st] = out["books"].get(st, 0) + 1
    return out


# ---------------------------------------------------------------------------
# One line on the workforce, for the executive dashboard
# ---------------------------------------------------------------------------

def people_summary() -> Dict[str, Any]:
    """People & work for management: who is here, hours, open work, HR items waiting, payroll cost."""
    h = overview()
    t = today()
    last_m = t.replace(day=1) - dt.timedelta(days=1)
    with tx() as conn:
        w = q1(conn, """SELECT COUNT(*) FILTER (WHERE status IN %s AND kind<>'note') AS open,
                               COUNT(*) FILTER (WHERE status IN %s AND kind<>'note' AND COALESCE(due_date, reminder_at) < now()) AS overdue,
                               COUNT(*) FILTER (WHERE status='completed' AND completed_at > now() - interval '7 days') AS done_7d,
                               COUNT(*) FILTER (WHERE status IN %s AND escalated_to='management') AS escalated
                        FROM royan_tasks""", (OPEN_STATUSES, OPEN_STATUSES, OPEN_STATUSES))
        r = q1(conn, """SELECT COUNT(*) FILTER (WHERE status IN ('sent','acknowledged','in_progress')) AS open,
                               COUNT(*) FILTER (WHERE status IN ('sent','acknowledged','in_progress') AND due_at < now()) AS overdue
                        FROM staff_requests""")
        leave = q1(conn, """SELECT COUNT(*) FILTER (WHERE status='pending') AS pending,
                                   COUNT(DISTINCT staff_id) FILTER (WHERE status='approved' AND %s BETWEEN start_date AND end_date) AS today
                            FROM royan_leave_requests""", (t,))
        pay = q(conn, """SELECT period_year AS y, period_month AS m, status, COUNT(*) AS n,
                                SUM(gross_salary + allowances + overtime_hours * overtime_rate) AS cost, SUM(net_salary) AS net
                         FROM royan_payroll_records WHERE make_date(period_year, period_month, 1) >= %s
                         GROUP BY 1, 2, 3""", ((t.replace(day=1) - dt.timedelta(days=200)).replace(day=1),))
        roster = q1(conn, """SELECT COUNT(*) AS n FROM royan_staff_shifts WHERE shift_date=%s AND status='scheduled'""", (t,))
        # staff payroll cannot be prepared for (no monthly salary on their HR record)
        no_salary = sum(1 for p in people(conn) if p["profile"] and not p["monthly_gross"])
    months: Dict[str, Dict[str, Any]] = {}
    for p in pay:
        k = f"{p['y']}-{p['m']:02d}"
        g = months.setdefault(k, {"period": k, "cost": 0.0, "net": 0.0, "records": 0, "draft": 0, "approved": 0, "paid": 0})
        g["cost"] += float(p["cost"] or 0); g["net"] += float(p["net"] or 0); g["records"] += int(p["n"]); g[p["status"]] += int(p["n"])
    last_key = f"{last_m.year}-{last_m.month:02d}"
    return {
        "as_of": now(), "headcount": h["headcount"], "with_login": h["with_login"], "online": len(h["online"]),
        "on_clock": len(h["on_clock"]), "on_leave_today": int(leave["today"] or 0), "rostered_today": int(roster["n"] or 0),
        "hours_week": h["hours_total"], "hours_week_saved": h["hours_saved"], "hours_week_live": h["hours_live"],
        "people_with_hours": h["people_with_hours"], "by_department": h["by_department"], "weeks": h["weeks"],
        "pending_timesheets": h["pending_approval"]["entries"], "long_clocks": len(h["long_clocks"]),
        "pending_leave": int(leave["pending"] or 0), "no_salary": no_salary,
        "open_tasks": int(w["open"] or 0), "overdue_tasks": int(w["overdue"] or 0), "done_7d": int(w["done_7d"] or 0),
        "escalated_to_management": int(w["escalated"] or 0),
        "open_requests": int(r["open"] or 0), "overdue_requests": int(r["overdue"] or 0),
        "payroll": sorted(months.values(), key=lambda g: g["period"]),
        "payroll_last_month": months.get(last_key),
    }
