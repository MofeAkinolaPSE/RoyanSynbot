"""Quality & safety in one place: incidents, infection control, HEFAMAA self-assessment,
facility audits and equipment maintenance.

The Executive overview and the attention list read these figures from here rather than
from the tables, so "overdue" means the same thing on every page (reportGUide.md s1.2).
The Quality & Safety and Audits & Maintenance pages keep their own detailed endpoints.

Compliance score: 100 less a deduction for each thing overdue today - 8 per overdue
audit, 4 per overdue maintenance job, 3 per open incident and 3 more if it has been
open over 14 days, 5 per open serious incident. It measures what is late, not quality
of care, and the page says so.
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Dict

from src.fin.db import q, q1, tx

OPEN_INCIDENT = "COALESCE(status,'reported') NOT IN ('closed','completed','resolved')"
SERIOUS = "lower(COALESCE(severity,'')) IN ('major','severe','critical','catastrophic','sentinel')"
AUDIT_OPEN = "COALESCE(status,'scheduled') IN ('scheduled','in_progress')"
MAINT_TASK_OPEN = "COALESCE(status,'open') NOT IN ('completed','done','cancelled','closed')"


def overview() -> Dict[str, Any]:
    t = dt.date.today()
    with tx() as conn:
        inc = q1(conn, f"""SELECT COUNT(*) AS total,
                                  COUNT(*) FILTER (WHERE {OPEN_INCIDENT}) AS open,
                                  COUNT(*) FILTER (WHERE {OPEN_INCIDENT} AND {SERIOUS}) AS open_serious,
                                  COUNT(*) FILTER (WHERE {OPEN_INCIDENT} AND created_at < now() - interval '14 days') AS open_over_14d,
                                  COUNT(*) FILTER (WHERE created_at > now() - interval '30 days') AS reported_30d
                           FROM royan_incident_reports""")
        aud = q1(conn, f"""SELECT COUNT(*) FILTER (WHERE {AUDIT_OPEN} AND scheduled_date < %(t)s) AS overdue,
                                  COUNT(*) FILTER (WHERE {AUDIT_OPEN} AND scheduled_date BETWEEN %(t)s AND %(t)s::date + 30) AS due_30,
                                  COUNT(*) FILTER (WHERE status='completed') AS completed,
                                  ROUND(AVG(score) FILTER (WHERE status='completed' AND score IS NOT NULL), 1) AS avg_score
                           FROM royan_facility_audits""", {"t": t})
        equip = q1(conn, """SELECT COUNT(*) FILTER (WHERE status='pending' AND due_date < %s) AS overdue,
                                   COUNT(*) FILTER (WHERE status='pending' AND due_date BETWEEN %s AND %s::date + 30) AS due_30
                            FROM royan_equipment_maintenance""", (t, t, t))
        tasks = q1(conn, f"""SELECT COUNT(*) FILTER (WHERE {MAINT_TASK_OPEN} AND due_at < now()) AS overdue,
                                    COUNT(*) FILTER (WHERE {MAINT_TASK_OPEN}) AS open
                             FROM royan_maintenance_tasks""")
        hai = q1(conn, """SELECT COUNT(*) FILTER (WHERE healthcare_associated) AS total,
                                 COUNT(*) FILTER (WHERE healthcare_associated AND created_at > now() - interval '30 days') AS last_30d
                          FROM royan_infection_control""")
        hef = q1(conn, """SELECT COUNT(*) AS n, ROUND(AVG(overall_score), 1) AS avg_score, MAX(assessment_date) AS last
                          FROM royan_hefamaa_checklist""")
    n = lambda v: int(v or 0)
    incidents = {"total": n(inc["total"]), "open": n(inc["open"]), "open_serious": n(inc["open_serious"]),
                 "open_over_14d": n(inc["open_over_14d"]), "reported_30d": n(inc["reported_30d"])}
    audits = {"overdue": n(aud["overdue"]), "due_30": n(aud["due_30"]), "completed": n(aud["completed"]),
              "avg_score": float(aud["avg_score"]) if aud["avg_score"] is not None else None}
    maintenance = {"overdue": n(equip["overdue"]) + n(tasks["overdue"]), "due_30": n(equip["due_30"]),
                   "open_tasks": n(tasks["open"])}
    score = 100 - (8 * audits["overdue"] + 4 * maintenance["overdue"] + 3 * incidents["open"]
                   + 3 * incidents["open_over_14d"] + 5 * incidents["open_serious"])
    return {
        "as_of": t,
        "compliance_score": max(0, score),
        "incidents": incidents, "audits": audits, "maintenance": maintenance,
        "infection": {"hai_total": n(hai["total"]), "hai_30d": n(hai["last_30d"])},
        "hefamaa": {"assessments": n(hef["n"]), "avg_score": float(hef["avg_score"]) if hef["avg_score"] is not None else None,
                    "last": hef["last"]},
    }


def compliance() -> Dict[str, Any]:
    """The Compliance page: the score and exactly what is pulling it down, HEFAMAA self-assessments,
    audits due or overdue, and whether the audit trail is intact (NDPA accountability)."""
    o = overview()
    i, a, m = o["incidents"], o["audits"], o["maintenance"]
    deductions = [
        {"item": "Audits overdue", "count": a["overdue"], "each": 8, "link": "/hospital/audits-maintenance"},
        {"item": "Maintenance jobs overdue", "count": m["overdue"], "each": 4, "link": "/hospital/audits-maintenance"},
        {"item": "Incidents open", "count": i["open"], "each": 3, "link": "/hospital/quality"},
        {"item": "Incidents open more than 14 days", "count": i["open_over_14d"], "each": 3, "link": "/hospital/quality"},
        {"item": "Serious incidents open", "count": i["open_serious"], "each": 5, "link": "/hospital/quality"},
    ]
    for d in deductions:
        d["points"] = d["count"] * d["each"]
    t = dt.date.today()
    with tx() as conn:
        hef = q(conn, """SELECT id::text AS id, assessment_date, department, overall_score, assessor, follow_up_date
                         FROM royan_hefamaa_checklist ORDER BY assessment_date DESC NULLS LAST LIMIT 20""")
        log = q1(conn, """SELECT COUNT(*) FILTER (WHERE created_at > now() - interval '7 days') AS week,
                                 COUNT(DISTINCT actor_id) FILTER (WHERE created_at > now() - interval '7 days') AS actors,
                                 MAX(created_at) AS last FROM royan_audit_logs""")
        audits = q(conn, """SELECT id::text AS id, audit_title, department, scheduled_date, risk_level, status, score
                            FROM royan_facility_audits
                            WHERE status IN ('scheduled','in_progress') OR completed_at > now() - interval '180 days'
                            ORDER BY (status IN ('scheduled','in_progress')) DESC, scheduled_date LIMIT 40""")
    for x in audits:
        x["overdue"] = x["status"] in ("scheduled", "in_progress") and x["scheduled_date"] is not None and x["scheduled_date"] < t
    return {**o, "deductions": deductions, "hefamaa_list": hef, "audit_list": audits,
            "audit_log": {"actions_7d": int(log["week"] or 0), "people_7d": int(log["actors"] or 0), "last": log["last"]}}


def pharmacy_qc() -> Dict[str, Any]:
    """Pharmacy quality control on the live batches: what is expired or about to be, which batches are
    missing the facts QC needs (expiry, cost), and medication incidents."""
    t = dt.date.today()
    with tx() as conn:
        s = q1(conn, """SELECT COUNT(*) FILTER (WHERE expiry_date < %(t)s) AS expired_batches,
                               COALESCE(SUM(quantity_on_hand*unit_cost) FILTER (WHERE expiry_date < %(t)s),0) AS expired_value,
                               COUNT(DISTINCT formulary_id) FILTER (WHERE expiry_date < %(t)s) AS expired_products,
                               COUNT(*) FILTER (WHERE expiry_date BETWEEN %(t)s AND %(t)s::date + 90) AS expiring_batches,
                               COALESCE(SUM(quantity_on_hand*unit_cost) FILTER (WHERE expiry_date BETWEEN %(t)s AND %(t)s::date + 90),0) AS expiring_value,
                               COUNT(*) FILTER (WHERE expiry_date IS NULL) AS no_expiry,
                               COUNT(*) FILTER (WHERE unit_cost IS NULL OR unit_cost <= 0) AS no_cost
                        FROM royan_inventory_batches WHERE quantity_on_hand > 0""", {"t": t})
        expiring = q(conn, """SELECT b.id, COALESCE(f.generic_name, f.brand_name) AS drug, b.batch_number, b.quantity_on_hand,
                                     b.unit_cost, b.expiry_date, b.supplier, (b.expiry_date - %(t)s) AS days_left
                              FROM royan_inventory_batches b JOIN royan_drug_formulary f ON f.id=b.formulary_id
                              WHERE b.quantity_on_hand > 0 AND b.expiry_date BETWEEN %(t)s AND %(t)s::date + 90
                              ORDER BY b.expiry_date LIMIT 300""", {"t": t})
        missing = q(conn, """SELECT b.id, COALESCE(f.generic_name, f.brand_name) AS drug, b.batch_number, b.quantity_on_hand,
                                    b.unit_cost, b.expiry_date, b.received_at,
                                    (b.expiry_date IS NULL) AS no_expiry, (b.unit_cost IS NULL OR b.unit_cost <= 0) AS no_cost
                             FROM royan_inventory_batches b JOIN royan_drug_formulary f ON f.id=b.formulary_id
                             WHERE b.quantity_on_hand > 0 AND (b.expiry_date IS NULL OR b.unit_cost IS NULL OR b.unit_cost <= 0)
                             ORDER BY 2 LIMIT 300""")
        incidents = q(conn, """SELECT id::text AS id, severity, status, ward, left(description, 160) AS description,
                                      COALESCE(incident_date, created_at::date) AS date
                               FROM royan_incident_reports WHERE category='medication_error'
                               ORDER BY created_at DESC LIMIT 50""")
    f = lambda v: float(v or 0)
    return {"as_of": t,
            "expired": {"batches": int(s["expired_batches"] or 0), "value": f(s["expired_value"]), "products": int(s["expired_products"] or 0)},
            "expiring_90": {"batches": int(s["expiring_batches"] or 0), "value": f(s["expiring_value"])},
            "missing": {"no_expiry": int(s["no_expiry"] or 0), "no_cost": int(s["no_cost"] or 0)},
            "expiring": [{**r, "quantity_on_hand": f(r["quantity_on_hand"]), "unit_cost": f(r["unit_cost"]),
                          "value": round(f(r["quantity_on_hand"]) * f(r["unit_cost"]), 2)} for r in expiring],
            "missing_list": [{**r, "quantity_on_hand": f(r["quantity_on_hand"])} for r in missing],
            "medication_incidents": incidents,
            "medication_incidents_open": sum(1 for x in incidents if x["status"] not in ("closed", "completed", "resolved"))}
