"""The hospital calendar: one view over the real records, never a diary of its own (reportGUide.md s10).

Every entry is a record owned by its module - an appointment, a theatre case, an audit, an
equipment service, a maintenance job, a drug batch expiring, staff leave, a stock delivery
expected, a follow-up with an HMO. Moving an entry moves the record itself (reschedule), so the
calendar and the module's own page can never disagree.

Each source states the roles that see it; a person sees only what their roles open.
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Callable, Dict, List, Optional

from src.fin.db import ex, q, q1, tx

CLINICAL = {"doctor", "nurse", "receptionist", "physiotherapist", "ops", "management", "admin"}
FACILITY = {"ops", "quality_assurance", "management", "admin"}
STOCK = {"pharmacist", "quality_assurance", "ops", "management", "admin"}
ORDERS = {"pharmacist", "ops", "finance", "management", "admin"}
PEOPLE = {"hr", "management", "admin"}
RELATIONS = {"finance", "management", "admin"}


def _ev(source: str, id_: Any, date: dt.date, title: str, detail: str = "", status: str = "", link: str = "",
        tone: str = "", movable: bool = False, end: Optional[dt.date] = None, time: Optional[str] = None) -> Dict[str, Any]:
    return {"key": f"{source}:{id_}", "source": source, "id": str(id_), "date": date, "end": end, "time": time,
            "title": title, "detail": detail, "status": status, "link": link, "tone": tone, "movable": movable}


def _appointments(conn, a, b):
    rows = q(conn, """SELECT ap.id, COALESCE(s.slot_date, ap.booked_at::date) AS d, s.slot_time, ap.status, ap.reason,
                             s.doctor_name, s.department, concat_ws(' ', p.first_name, p.last_name) AS patient
                      FROM royan_appointments ap LEFT JOIN royan_appointment_slots s ON s.id=ap.slot_id
                      LEFT JOIN royan_patients p ON p.id=ap.patient_id
                      WHERE COALESCE(s.slot_date, ap.booked_at::date) BETWEEN %s AND %s
                        AND COALESCE(ap.status,'') NOT IN ('cancelled')""", (a, b))
    return [_ev("appointment", r["id"], r["d"], f"{r['patient'] or 'Patient'}" + (f" - {r['doctor_name']}" if r["doctor_name"] else ""),
                " · ".join(x for x in (r["department"], r["reason"]) if x), r["status"] or "", "/hospital/appointments",
                time=str(r["slot_time"])[:5] if r["slot_time"] else None) for r in rows]


def _theatre(conn, a, b):
    rows = q(conn, """SELECT t.id, t.scheduled_date AS d, t.start_time, t.procedure_name, t.theatre_name, t.status, t.urgency,
                             concat_ws(' ', p.first_name, p.last_name) AS patient
                      FROM royan_theatre_cases t LEFT JOIN royan_patients p ON p.id=t.patient_id
                      WHERE t.scheduled_date BETWEEN %s AND %s AND COALESCE(t.status,'') NOT IN ('cancelled')""", (a, b))
    return [_ev("theatre", r["id"], r["d"], f"Theatre: {r['procedure_name'] or 'case'}",
                " · ".join(x for x in (r["patient"], r["theatre_name"], r["urgency"]) if x), r["status"] or "",
                "/hospital/theatre", "warning" if r["urgency"] in ("emergency", "urgent") else "",
                time=str(r["start_time"])[:5] if r["start_time"] else None) for r in rows]


def _audits(conn, a, b):
    t = dt.date.today()
    rows = q(conn, """SELECT id, scheduled_date AS d, audit_title, department, risk_level, status FROM royan_facility_audits
                      WHERE scheduled_date BETWEEN %s AND %s""", (a, b))
    return [_ev("audit", r["id"], r["d"], f"Audit: {r['audit_title']}", " · ".join(x for x in (r["department"], r["risk_level"]) if x),
                r["status"] or "", "/hospital/audits-maintenance",
                "danger" if r["status"] in ("scheduled", "in_progress") and r["d"] < t else "",
                movable=r["status"] in ("scheduled", "in_progress")) for r in rows]


def _equipment(conn, a, b):
    t = dt.date.today()
    rows = q(conn, """SELECT id, due_date AS d, equipment_name, maintenance_type, location, status FROM royan_equipment_maintenance
                      WHERE due_date BETWEEN %s AND %s""", (a, b))
    return [_ev("equipment", r["id"], r["d"], f"{(r['maintenance_type'] or 'Service').capitalize()}: {r['equipment_name']}",
                r["location"] or "", r["status"] or "", "/hospital/audits-maintenance",
                "danger" if r["status"] == "pending" and r["d"] < t else "", movable=r["status"] == "pending") for r in rows]


def _maintenance(conn, a, b):
    rows = q(conn, """SELECT id::text AS id, due_at, title, severity, status FROM royan_maintenance_tasks
                      WHERE due_at::date BETWEEN %s AND %s""", (a, b))
    done = ("completed", "done", "cancelled", "closed")
    return [_ev("maintenance", r["id"], r["due_at"].date(), f"Maintenance: {r['title']}", r["severity"] or "", r["status"] or "",
                "/hospital/audits-maintenance", "danger" if r["status"] not in done and r["due_at"] < dt.datetime.now(r["due_at"].tzinfo) else "",
                movable=(r["status"] or "open") not in done, time=r["due_at"].strftime("%H:%M")) for r in rows]


def _expiry(conn, a, b):
    rows = q(conn, """SELECT b.expiry_date AS d, f.id AS fid, COALESCE(f.generic_name, f.brand_name) AS drug,
                             SUM(b.quantity_on_hand) AS qty, SUM(b.quantity_on_hand * COALESCE(b.unit_cost,0)) AS value,
                             string_agg(DISTINCT b.batch_number, ', ') AS batches
                      FROM royan_inventory_batches b JOIN royan_drug_formulary f ON f.id=b.formulary_id
                      WHERE b.quantity_on_hand > 0 AND b.expiry_date BETWEEN %s AND %s GROUP BY 1,2,3""", (a, b))
    return [_ev("expiry", f"{r['fid']}:{r['d']}", r["d"], f"Expires: {r['drug']}",
                f"{float(r['qty']):g} units · ₦{float(r['value']):,.0f} · batch {(r['batches'] or '')[:40]}", "",
                "/hospital/pharmacy/inventory", "warning") for r in rows]


def _leave(conn, a, b):
    rows = q(conn, """SELECT l.id, l.start_date, l.end_date, l.leave_type, l.status, s.full_name
                      FROM royan_leave_requests l LEFT JOIN royan_staff s ON s.id=l.staff_id
                      WHERE l.status IN ('approved','pending') AND l.start_date <= %s AND l.end_date >= %s""", (b, a))
    return [_ev("leave", r["id"], r["start_date"], f"Leave: {r['full_name'] or 'staff'}", (r["leave_type"] or "").replace("_", " "),
                r["status"], "/hr?tab=leave", "" if r["status"] == "approved" else "warning", end=r["end_date"]) for r in rows]


def _deliveries(conn, a, b):
    t = dt.date.today()
    rows = q(conn, """SELECT r.id, r.expected_date AS d, r.requested_qty, COALESCE(f.generic_name, r.sku) AS drug, s.name AS supplier
                      FROM royan_replenishment_requests r LEFT JOIN royan_drug_formulary f ON f.id=r.formulary_id
                      LEFT JOIN suppliers s ON s.id=r.supplier_id
                      WHERE r.status='ordered' AND r.expected_date BETWEEN %s AND %s""", (a, b))
    return [_ev("delivery", r["id"], r["d"], f"Delivery: {r['drug']}", f"{float(r['requested_qty'] or 0):g} from {r['supplier'] or 'supplier'}",
                "ordered", "/procurement?tab=orders", "danger" if r["d"] < t else "", movable=True) for r in rows]


def _follow_ups(conn, a, b):
    t = dt.date.today()
    rows = q(conn, """SELECT c.id::text AS id, c.follow_up_on AS d, c.summary, p.name, c.payer_id
                      FROM royan_payer_contacts c JOIN fin_hope_payers p ON p.tariff_id=c.payer_id
                      WHERE c.follow_up_done_at IS NULL AND c.follow_up_on BETWEEN %s AND %s""", (a, b))
    return [_ev("follow_up", r["id"], r["d"], f"Follow up: {r['name']}", (r["summary"] or "")[:80], "open",
                f"/relations?payer={r['payer_id']}", "danger" if r["d"] < t else "", movable=True) for r in rows]


SOURCES: Dict[str, Dict[str, Any]] = {
    "appointment": {"label": "Appointments", "roles": CLINICAL, "fn": _appointments},
    "theatre": {"label": "Theatre", "roles": CLINICAL, "fn": _theatre},
    "audit": {"label": "Audits", "roles": FACILITY, "fn": _audits},
    "equipment": {"label": "Equipment servicing", "roles": FACILITY, "fn": _equipment},
    "maintenance": {"label": "Maintenance jobs", "roles": FACILITY, "fn": _maintenance},
    "expiry": {"label": "Drugs expiring", "roles": STOCK, "fn": _expiry},
    "delivery": {"label": "Stock deliveries", "roles": ORDERS, "fn": _deliveries},
    "leave": {"label": "Staff leave", "roles": PEOPLE, "fn": _leave},
    "follow_up": {"label": "HMO follow-ups", "roles": RELATIONS, "fn": _follow_ups},
}

# what moving an entry changes, on the record itself
_MOVE: Dict[str, Callable[[Any, str, dt.date], int]] = {
    "audit": lambda c, i, d: ex(c, """UPDATE royan_facility_audits SET scheduled_date=%s, updated_at=now()
                                       WHERE id::text=%s AND status IN ('scheduled','in_progress')""", (d, i)),
    "equipment": lambda c, i, d: ex(c, """UPDATE royan_equipment_maintenance SET due_date=%s, updated_at=now()
                                           WHERE id::text=%s AND status='pending'""", (d, i)),
    "maintenance": lambda c, i, d: ex(c, """UPDATE royan_maintenance_tasks SET due_at = %s::date + (due_at - due_at::date), updated_at=now()
                                             WHERE id::text=%s AND COALESCE(status,'open') NOT IN ('completed','done','cancelled','closed')""", (d, i)),
    "delivery": lambda c, i, d: ex(c, "UPDATE royan_replenishment_requests SET expected_date=%s WHERE id::text=%s AND status='ordered'", (d, i)),
    "follow_up": lambda c, i, d: ex(c, """UPDATE royan_payer_contacts SET follow_up_on=%s
                                           WHERE id::text=%s AND follow_up_done_at IS NULL""", (d, i)),
}


def _allowed(roles) -> List[str]:
    rs = {str(r).lower() for r in roles or []}
    return [k for k, s in SOURCES.items() if rs & s["roles"]]


def feed(user: Dict[str, Any], start: dt.date, end: dt.date, sources: Optional[List[str]] = None) -> Dict[str, Any]:
    if (end - start).days > 92:
        raise ValueError("Show at most three months at a time")
    allowed = _allowed(user.get("roles"))
    want = [s for s in (sources or allowed) if s in allowed]
    events: List[Dict[str, Any]] = []
    with tx() as conn:
        for s in want:
            events += SOURCES[s]["fn"](conn, start, end)
    events.sort(key=lambda e: (e["date"], e["time"] or "", e["source"]))
    return {"from": start, "to": end, "events": events,
            "sources": [{"key": k, "label": SOURCES[k]["label"], "movable": k in _MOVE} for k in allowed]}


def reschedule(user: Dict[str, Any], source: str, id_: str, new_date: dt.date) -> Dict[str, Any]:
    if source not in _allowed(user.get("roles")):
        raise PermissionError("You cannot change this kind of entry")
    if source not in _MOVE:
        raise ValueError("This entry is moved on its own page")
    if new_date < dt.date.today():
        raise ValueError("Move it to today or later")
    with tx() as conn:
        n = _MOVE[source](conn, id_, new_date)
    if not n:
        raise LookupError("Entry not found, or it is already done")
    from src.db import audit_event
    audit_event("calendar_rescheduled", {"source": source, "id": id_, "date": str(new_date)}, actor_id=str(user.get("sub")),
                subject_type=source, subject_id=str(id_))
    return {"source": source, "id": id_, "date": new_date}
