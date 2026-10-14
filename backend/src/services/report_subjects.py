"""Reports about one chosen record (reportGUide.md s12): pick the exact incident, audit, HMO,
patient account, drug, stock order, encounter or month - the system gathers everything it knows
about it from the module that owns it - the person reviews it - the report is written from that
record summary only, and the summary is attached as the appendix.

  REPORT_TYPES   what can be reported on, and which kinds of record each type accepts
  list_subjects  the records of a kind, searchable (what the person picks from)
  dossier        facts (label/value), long texts, tables, gaps (what is NOT recorded, so the report
                 says so instead of inventing it) and links back to the record
  sections_for   the sections of a report on that kind of record

Nothing here writes. Clinical documents (the encounter summary) are drafts until a clinician
approves them, and the writer is told: recorded facts only, no diagnosis of its own.
"""
from __future__ import annotations

import datetime as dt
import re
from typing import Any, Callable, Dict, List, Optional, Tuple

from src.fin.db import q, q1, tx

REPORT_TYPES: List[Dict[str, Any]] = [
    {"type": "incident", "name": "Incident report", "group": "Quality & safety", "kinds": ["incident"],
     "about": "One incident: what happened, severity, immediate action, investigation, root cause, corrective and preventive actions."},
    {"type": "audit", "name": "Audit report", "group": "Quality & safety", "kinds": ["audit"],
     "about": "One facility audit: scope, schedule, findings, score and recommendations."},
    {"type": "maintenance", "name": "Equipment maintenance report", "group": "Quality & safety", "kinds": ["maintenance"],
     "about": "One equipment service or calibration job and that equipment's history."},
    {"type": "hmo_account", "name": "HMO / corporate account report", "group": "Patient relations & finance", "kinds": ["payer"],
     "about": "One HMO or corporate payer: what was billed, for which services, what they owe and how late, contacts."},
    {"type": "patient_statement", "name": "Patient account statement", "group": "Patient relations & finance", "kinds": ["patient"],
     "about": "One patient's bills, payments and balance, with who paid (self or HMO)."},
    {"type": "drug", "name": "Drug stock report", "group": "Pharmacy & stores", "kinds": ["drug"],
     "about": "One drug: stock and batches, expiry, use over time, cover and open orders."},
    {"type": "stock_order", "name": "Stock order report", "group": "Pharmacy & stores", "kinds": ["stock_order"],
     "about": "One stock order from request to receipt, with supplier and timing."},
    {"type": "clinical_summary", "name": "Clinical summary (discharge / referral)", "group": "Clinical", "kinds": ["encounter"],
     "about": "One encounter written up from its record. A draft until the clinician approves it.", "needs_signoff": True},
    {"type": "monthly", "name": "Monthly hospital report", "group": "Management", "kinds": ["period"],
     "about": "A month: billing by payer and department, visits, admissions, pharmacy, incidents."},
    {"type": "executive", "name": "Executive report", "group": "Management", "kinds": ["current"],
     "about": "The hospital now: money, patients, pharmacy, quality, people and what needs attention."},
]
TYPE_BY_KEY = {t["type"]: t for t in REPORT_TYPES}
KIND_LABEL = {"incident": "an incident", "audit": "an audit", "maintenance": "a maintenance job", "payer": "an HMO / corporate payer",
              "patient": "a patient", "drug": "a drug", "stock_order": "a stock order", "encounter": "an encounter",
              "period": "a month", "current": "the hospital today"}
# who may write which kind (the record's own page decides who may see it; this mirrors that)
KIND_ROLES = {
    "incident": {"quality_assurance", "nurse", "doctor", "ops", "management", "admin"},
    "audit": {"quality_assurance", "ops", "management", "admin"},
    "maintenance": {"quality_assurance", "ops", "management", "admin"},
    "payer": {"finance", "management", "admin"},
    "patient": {"finance", "receptionist", "management", "admin"},
    "drug": {"pharmacist", "quality_assurance", "ops", "finance", "management", "admin"},
    "stock_order": {"pharmacist", "ops", "finance", "management", "admin"},
    "encounter": {"doctor", "nurse", "admin"},
    "period": {"finance", "management", "admin", "quality_assurance"},
    "current": {"finance", "management", "admin"},
}


def kinds_for(roles) -> List[str]:
    rs = {str(r).lower() for r in roles or []}
    return [k for k, allowed in KIND_ROLES.items() if rs & allowed]


def catalog(roles) -> Dict[str, Any]:
    ok = set(kinds_for(roles))
    return {"types": [t for t in REPORT_TYPES if set(t["kinds"]) & ok], "kind_labels": KIND_LABEL}


# ---------------------------------------------------------------------------

def _f(v: Any) -> float:
    return float(v or 0)


def _n(v: Any) -> str:
    return f"₦{_f(v):,.2f}"


def _d(v: Any) -> str:
    if v in (None, ""):
        return "not recorded"
    if isinstance(v, dt.datetime):
        return v.strftime("%d %b %Y %H:%M")
    if isinstance(v, dt.date):
        return v.strftime("%d %b %Y")
    return str(v)


def _txt(v: Any) -> str:
    if v in (None, "", [], {}):
        return "not recorded"
    if isinstance(v, (dt.date, dt.datetime)):
        return _d(v)
    return str(v)


def _like(s: str) -> str:
    return f"%{(s or '').strip()}%"


def _dossier(kind: str, id_: str, title: str, subtitle: str = "", facts: Optional[List[Tuple[str, Any]]] = None,
             texts: Optional[List[Tuple[str, Any]]] = None, tables: Optional[List[Dict[str, Any]]] = None,
             gaps: Optional[List[str]] = None, links: Optional[List[Tuple[str, str]]] = None) -> Dict[str, Any]:
    return {"kind": kind, "id": id_, "title": title, "subtitle": subtitle,
            "facts": [{"label": k, "value": _txt(v)} for k, v in (facts or [])],
            "texts": [{"label": k, "value": str(v)} for k, v in (texts or []) if v not in (None, "", [], {})],
            "tables": [t for t in (tables or []) if t.get("rows")],
            "gaps": gaps or [], "links": [{"label": k, "href": h} for k, h in (links or [])],
            "gathered_at": dt.datetime.now(dt.timezone.utc).isoformat()}


def _table(title: str, columns: List[str], rows: List[List[Any]]) -> Dict[str, Any]:
    return {"title": title, "columns": columns, "rows": [[_txt(c) for c in r] for r in rows]}


def _gaps(pairs: List[Tuple[str, Any]]) -> List[str]:
    return [label for label, v in pairs if v in (None, "", [], {})]


def _names(conn, ids) -> Dict[str, str]:
    ids = [str(i) for i in {x for x in ids if x}]
    if not ids:
        return {}
    rows = q(conn, """SELECT u.id::text AS id, COALESCE(s.full_name, u.email) AS name FROM royan_users u
                      LEFT JOIN royan_staff s ON s.user_id=u.id WHERE u.id::text = ANY(%s)
                      UNION SELECT s.id::text, s.full_name FROM royan_staff s WHERE s.id::text = ANY(%s)""", (ids, ids))
    return {r["id"]: r["name"] for r in rows}


def _who(names: Dict[str, str], v: Any) -> Any:
    return names.get(str(v), v) if v else None


# ---------------------------------------------------------------------------
# Quality & safety
# ---------------------------------------------------------------------------

def _list_incidents(search: str):
    with tx() as c:
        return q(c, """SELECT id::text AS id, concat_ws(' - ', initcap(replace(category, '_', ' ')), left(description, 60)) AS title,
                              concat_ws(' · ', severity, ward) AS subtitle, COALESCE(incident_date, created_at::date) AS date, status
                       FROM royan_incident_reports WHERE (%s='' OR description ILIKE %s OR category ILIKE %s OR ward ILIKE %s)
                       ORDER BY created_at DESC LIMIT 80""", (search, _like(search), _like(search), _like(search)))


def _dossier_incident(id_: str):
    with tx() as c:
        r = q1(c, "SELECT * FROM royan_incident_reports WHERE id::text=%s", (id_,))
        if not r:
            raise LookupError("Incident not found")
        names = _names(c, [r["reported_by"], r["investigated_by"]])
    fields = [("Category", r["category"]), ("Severity", r["severity"]), ("Status", r["status"]), ("Ward / area", r["ward"]),
              ("Date of incident", r["incident_date"]), ("Time", r["incident_time"]), ("Reported by", _who(names, r["reported_by"])),
              ("Reported on", r["created_at"]), ("Investigated by", _who(names, r["investigated_by"])),
              ("Investigation completed", r["investigation_completed_at"]), ("Closed", r["closed_at"]),
              ("Patient involved", "yes (record linked)" if r["patient_id"] else None), ("Equipment involved", r["equipment_involved"])]
    texts = [("Description", r["description"]), ("Immediate action taken", r["immediate_action_taken"]),
             ("Witnesses", r["witnesses"]), ("Contributing factors", r["contributing_factors"] or r["investigation_contributing_factors"]),
             ("Investigation notes", r["investigation_notes"]), ("Root cause", r["root_cause"]),
             ("Corrective actions", r["corrective_actions"]), ("Preventive actions", r["preventive_actions"]),
             ("Outcome", r["outcome"]), ("Status notes", r["status_notes"])]
    gaps = _gaps([("Immediate action taken", r["immediate_action_taken"]), ("Root cause", r["root_cause"]),
                  ("Corrective actions", r["corrective_actions"]), ("Preventive actions", r["preventive_actions"]),
                  ("Who investigated", r["investigated_by"])])
    return _dossier("incident", id_, f"{(r['category'] or 'Incident').replace('_', ' ').capitalize()} incident, {_d(r['incident_date'] or r['created_at'])}",
                    f"{r['severity'] or ''} · {r['status'] or ''}", fields, texts, gaps=gaps,
                    links=[("Quality & safety", "/hospital/quality")])


def _list_audits(search: str):
    with tx() as c:
        return q(c, """SELECT id::text AS id, audit_title AS title, concat_ws(' · ', department, risk_level) AS subtitle,
                              scheduled_date AS date, status FROM royan_facility_audits
                       WHERE (%s='' OR audit_title ILIKE %s OR department ILIKE %s) ORDER BY scheduled_date DESC LIMIT 80""",
                 (search, _like(search), _like(search)))


def _dossier_audit(id_: str):
    with tx() as c:
        r = q1(c, "SELECT * FROM royan_facility_audits WHERE id::text=%s", (id_,))
        if not r:
            raise LookupError("Audit not found")
        hist = q(c, """SELECT scheduled_date, status, score FROM royan_facility_audits WHERE department IS NOT DISTINCT FROM %s
                       AND id::text<>%s ORDER BY scheduled_date DESC LIMIT 10""", (r["department"], id_))
        names = _names(c, [r["created_by"]])
    t = dt.date.today()
    overdue = r["status"] in ("scheduled", "in_progress") and r["scheduled_date"] and r["scheduled_date"] < t
    return _dossier("audit", id_, r["audit_title"], f"{r['department'] or ''} · {r['status']}",
                    [("Department", r["department"]), ("Risk level", r["risk_level"]), ("Scheduled for", r["scheduled_date"]),
                     ("Status", f"{r['status']}{' - OVERDUE' if overdue else ''}"), ("Started", r["started_at"]),
                     ("Completed", r["completed_at"]), ("Score", r["score"]), ("Scheduled by", _who(names, r["created_by"]))],
                    [("Findings", r["findings"]), ("Recommendations", r["recommendations"])],
                    [_table("Earlier audits of this department", ["Date", "Status", "Score"],
                            [[h["scheduled_date"], h["status"], h["score"]] for h in hist])],
                    _gaps([("Findings", r["findings"]), ("Recommendations", r["recommendations"]), ("Score", r["score"])]),
                    [("Audits & maintenance", "/hospital/audits-maintenance")])


def _list_maintenance(search: str):
    with tx() as c:
        return q(c, """SELECT id::text AS id, concat_ws(': ', initcap(maintenance_type), equipment_name) AS title,
                              location AS subtitle, due_date AS date, status FROM royan_equipment_maintenance
                       WHERE (%s='' OR equipment_name ILIKE %s OR location ILIKE %s) ORDER BY due_date DESC LIMIT 80""",
                 (search, _like(search), _like(search)))


def _dossier_maintenance(id_: str):
    with tx() as c:
        r = q1(c, "SELECT * FROM royan_equipment_maintenance WHERE id::text=%s", (id_,))
        if not r:
            raise LookupError("Maintenance job not found")
        hist = q(c, """SELECT due_date, maintenance_type, status, completed_at, completion_notes FROM royan_equipment_maintenance
                       WHERE equipment_name=%s AND id::text<>%s ORDER BY due_date DESC LIMIT 12""", (r["equipment_name"], id_))
        names = _names(c, [r["completed_by"], r["created_by"]])
    return _dossier("maintenance", id_, f"{(r['maintenance_type'] or 'Service').capitalize()}: {r['equipment_name']}",
                    f"{r['location'] or ''} · {r['status']}",
                    [("Equipment", r["equipment_name"]), ("Type", r["equipment_type"]), ("Location", r["location"]),
                     ("Maintenance type", r["maintenance_type"]), ("Due", r["due_date"]), ("Status", r["status"]),
                     ("Completed", r["completed_at"]), ("Completed by", _who(names, r["completed_by"])), ("Next due", r["next_due_date"])],
                    [("Description", r["description"]), ("Completion notes", r["completion_notes"])],
                    [_table("This equipment's other jobs", ["Due", "Type", "Status", "Completed", "Notes"],
                            [[h["due_date"], h["maintenance_type"], h["status"], h["completed_at"], (h["completion_notes"] or "")[:80]] for h in hist])],
                    _gaps([("Completion notes", r["completion_notes"]) if r["status"] != "pending" else ("", "x"),
                           ("Next due date", r["next_due_date"])]),
                    [("Audits & maintenance", "/hospital/audits-maintenance")])


# ---------------------------------------------------------------------------
# Patient relations & finance
# ---------------------------------------------------------------------------

def _list_payers(search: str):
    from src.services.payer_relations import directory
    d = directory()
    s = search.lower()
    return [{"id": str(p["id"]), "title": p["name"], "subtitle": f"{p['payer_type'].title()} · billed {_n(p['billed_12m'])} in 12 months",
             "date": p["last_bill"], "status": p["segment"]} for p in d["payers"] if not s or s in (p["name"] or "").lower()][:80]


def _dossier_payer(id_: str):
    from src.services.payer_relations import directory, profile
    p = profile(int(id_))
    row = next((x for x in directory()["payers"] if x["id"] == int(id_)), {})
    pay, acc, tot = p["payer"], p["account"], p["totals"]
    b = acc["buckets"] or {}
    return _dossier("payer", id_, pay["name"], f"{pay['payer_type'].title()} · billing to {_d(p['as_of'])}",
                    [("Payer type", pay["payer_type"]), ("Billing data reaches", p["as_of"]), ("Segment", row.get("segment")),
                     ("Billed, last 12 months", _n(row.get("billed_12m"))), ("Billed, 12 months before", _n(row.get("billed_prior_12m"))),
                     ("Change", f"{row['change_pct']}%" if row.get("change_pct") is not None else None),
                     ("Patients, last 12 months", row.get("patients_12m")), ("Visits, last 12 months", row.get("visits_12m")),
                     ("Billed since first bill", _n(tot["billed_all"])), ("First bill", tot["first_bill"]), ("Last bill", tot["last_bill"]),
                     ("Received on their accounts", _n(tot["received"])), ("Owed now", _n(acc["owed"])),
                     ("Owed 0-30 / 31-60 / 61-90 / 90+ days", " / ".join(_n(b.get(k)) for k in ("0_30", "31_60", "61_90", "91_plus"))),
                     ("Oldest unpaid month", acc["oldest_open"]), ("Basis of what is owed", acc["source"]),
                     ("At risk", "; ".join(row.get("risk_reasons") or []) or "no"),
                     ("Contact phone", pay["contact_phone"]), ("Contact email", pay["contact_email"])],
                    [("Notes on the payer", pay["hmo_notes"])],
                    [_table("Billing by month", ["Month", "Billed", "Patients", "Visits"],
                            [[m["period"], _n(m["billed"]), m["patients"], m["visits"]] for m in p["months"][-24:]]),
                     _table("Billing by department, last 12 months", ["Department", "Billed", "Lines", "Patients"],
                            [[d["department"], _n(d["billed"]), d["lines"], d["patients"]] for d in p["departments"]]),
                     _table("Services billed most, last 12 months", ["Service", "Billed", "Quantity"],
                            [[s["service"], _n(s["billed"]), f"{s['quantity']:g}"] for s in p["top_services"]]),
                     _table("Contacts", ["Date", "Kind", "Summary", "Follow-up"],
                            [[c["created_at"], c["kind"], c["summary"][:120], c["follow_up_on"]] for c in p["contacts"][:15]])],
                    p["gaps"], [("Patient relations", f"/relations?payer={id_}"), ("Credit control", "/finance/ar")])


def _list_patients(search: str):
    if len((search or "").strip()) < 2:
        return []
    with tx() as c:
        return q(c, """SELECT id::text AS id, concat_ws(' ', first_name, last_name) AS title, concat_ws(' · ', mrn, hmo_provider) AS subtitle,
                              registered_at::date AS date, CASE WHEN is_active THEN 'active' ELSE 'inactive' END AS status
                       FROM royan_patients WHERE mrn ILIKE %s OR concat_ws(' ', first_name, last_name) ILIKE %s
                       ORDER BY registered_at DESC NULLS LAST LIMIT 40""", (_like(search), _like(search)))


def _dossier_patient(id_: str):
    with tx() as c:
        p = q1(c, "SELECT id, mrn, first_name, last_name, hmo_provider, hmo_id, phone FROM royan_patients WHERE id::text=%s", (id_,))
        if not p:
            raise LookupError("Patient not found")
        bills = q(c, """SELECT bill_number, billed_at, subtotal, discount, hmo_covered, patient_balance, status, paid_at, payment_method
                        FROM royan_billing WHERE patient_id=%s ORDER BY billed_at DESC NULLS LAST LIMIT 40""", (p["id"],))
        hope = q(c, """SELECT to_char(c.charge_date,'YYYY-MM') AS m, c.payer_type, SUM(c.gross - c.discount) AS billed,
                              SUM(c.paid) AS paid, SUM(c.outstanding) AS outstanding
                       FROM fin_v_hope_charges c WHERE c.patient_id=%s GROUP BY 1,2 ORDER BY 1 DESC LIMIT 36""", (p["id"],))
    bal = sum(_f(b["patient_balance"]) for b in bills if b["status"] not in ("paid", "cancelled", "void"))
    name = f"{p['first_name'] or ''} {p['last_name'] or ''}".strip()
    return _dossier("patient", id_, f"{name} ({p['mrn']})", "patient account",
                    [("MRN", p["mrn"]), ("HMO", p["hmo_provider"]), ("Bills in this system", len(bills)),
                     ("Balance on open bills in this system", _n(bal)),
                     ("Hope history months", len(hope))],
                    tables=[_table("Bills in this system", ["Bill", "Date", "Total", "Discount", "HMO covers", "Patient owes", "Status", "Paid"],
                                   [[b["bill_number"], b["billed_at"], _n(b["subtotal"]), _n(b["discount"]), _n(b["hmo_covered"]),
                                     _n(b["patient_balance"]), b["status"], b["paid_at"]] for b in bills]),
                            _table("Billing in Hope by month and payer", ["Month", "Payer", "Billed", "Paid", "Outstanding"],
                                   [[h["m"], h["payer_type"], _n(h["billed"]), _n(h["paid"]), _n(h["outstanding"])] for h in hope])],
                    gaps=(["Hope's 'paid' flag for private pharmacy lines is unreliable (settled on the final bill) - "
                           "do not treat Hope 'outstanding' as money the patient owes"] if hope else []),
                    links=[("Patient record", f"/hospital/patients/{p['mrn']}")])


# ---------------------------------------------------------------------------
# Pharmacy & stores
# ---------------------------------------------------------------------------

def _list_drugs(search: str):
    with tx() as c:
        return q(c, """SELECT f.id::text AS id, COALESCE(f.generic_name, f.brand_name) AS title, concat_ws(' · ', f.code, f.strength, f.form) AS subtitle,
                              NULL::date AS date, CASE WHEN EXISTS (SELECT 1 FROM royan_inventory_batches b WHERE b.formulary_id=f.id
                                                                    AND b.quantity_on_hand > 0) THEN 'in stock' ELSE 'none in stock' END AS status
                       FROM royan_drug_formulary f WHERE f.deprecated_at IS NULL AND (%s='' OR f.generic_name ILIKE %s OR f.brand_name ILIKE %s OR f.code ILIKE %s)
                       ORDER BY 2 LIMIT 60""", (search, _like(search), _like(search), _like(search)))


def _dossier_drug(id_: str):
    from src.services.stock_orders import reorder_plan
    plan = next((i for i in reorder_plan()["items"] if str(i["formulary_id"]) == id_), None)
    with tx() as c:
        f = q1(c, "SELECT * FROM royan_drug_formulary WHERE id::text=%s", (id_,))
        if not f:
            raise LookupError("Drug not found")
        batches = q(c, """SELECT batch_number, quantity_on_hand, unit_cost, expiry_date, supplier, received_at FROM royan_inventory_batches
                          WHERE formulary_id=%s AND quantity_on_hand > 0 ORDER BY expiry_date NULLS LAST""", (f["id"],))
        use = q(c, """SELECT to_char(dispensed_at,'YYYY-MM') AS m, SUM(quantity_dispensed) AS qty, COUNT(*) AS n
                      FROM royan_dispensing WHERE formulary_id=%s AND dispensed_at > now() - interval '24 months' GROUP BY 1 ORDER BY 1""", (f["id"],))
        buys = q(c, """SELECT h.received_date, h.supplier_name, h.quantity, h.unit_cost, h.batch_number FROM fin_hist_purchase_lines h
                       JOIN fin_products p ON p.sku=h.sku AND p.legal_entity_id=h.legal_entity_id WHERE p.formulary_id=%s
                       ORDER BY h.received_date DESC LIMIT 12""", (f["id"],))
        orders = q(c, """SELECT id, status, requested_qty, created_at, expected_date FROM royan_replenishment_requests
                         WHERE formulary_id=%s ORDER BY created_at DESC LIMIT 10""", (f["id"],))
    pl = plan or {}
    return _dossier("drug", id_, f"{f['generic_name'] or f['brand_name']} {f['strength'] or ''}".strip(), f"{f['code']} · {f['form'] or ''}",
                    [("Code", f["code"]), ("Brand", f["brand_name"]), ("Form / strength", f"{f['form'] or ''} {f['strength'] or ''}".strip()),
                     ("On the shelf (usable)", pl.get("on_hand")), ("Expired, still on the shelf", pl.get("expired")),
                     ("Stock value at cost", _n(pl.get("value"))), ("Used, last 180 days of data", pl.get("used_180d")),
                     ("Use per day", pl.get("per_day")), ("Days of cover", pl.get("cover_days")),
                     ("Reorder status", (pl.get("status") or "").replace("_", " ")), ("Suggested order", pl.get("suggested_qty")),
                     ("On order", pl.get("on_order")), ("Last supplier", pl.get("last_supplier")), ("Last price", _n(pl.get("last_cost")) if pl.get("last_cost") else None),
                     ("Lead time used (days)", pl.get("lead_days")), ("Reorder level", f["reorder_level"])],
                    tables=[_table("Batches on the shelf", ["Batch", "Quantity", "Unit cost", "Expiry", "Supplier", "Received"],
                                   [[b["batch_number"], f"{_f(b['quantity_on_hand']):g}", _n(b["unit_cost"]), b["expiry_date"], b["supplier"], b["received_at"]] for b in batches]),
                            _table("Use by month", ["Month", "Quantity", "Dispensings"], [[u["m"], f"{_f(u['qty']):g}", u["n"]] for u in use]),
                            _table("Recent purchases", ["Received", "Supplier", "Quantity", "Unit cost", "Batch"],
                                   [[b["received_date"], b["supplier_name"], f"{_f(b['quantity']):g}", _n(b["unit_cost"]), b["batch_number"]] for b in buys]),
                            _table("Stock orders", ["Order", "Status", "Quantity", "Raised", "Expected"],
                                   [[o["id"], o["status"], f"{_f(o['requested_qty']):g}", o["created_at"], o["expected_date"]] for o in orders])],
                    gaps=(["Batches with no expiry date recorded"] if any(not b["expiry_date"] for b in batches) else [])
                    + (["Batches with no unit cost recorded"] if any(not b["unit_cost"] for b in batches) else []),
                    links=[("Pharmacy inventory", "/hospital/pharmacy/inventory"), ("Procurement", "/procurement")])


def _list_stock_orders(search: str):
    with tx() as c:
        return q(c, """SELECT r.id::text AS id, COALESCE(f.generic_name, r.sku) AS title, concat_ws(' · ', r.requested_qty::text, s.name) AS subtitle,
                              r.created_at::date AS date, r.status FROM royan_replenishment_requests r
                       LEFT JOIN royan_drug_formulary f ON f.id=r.formulary_id LEFT JOIN suppliers s ON s.id=r.supplier_id
                       WHERE (%s='' OR f.generic_name ILIKE %s OR r.sku ILIKE %s) ORDER BY r.created_at DESC LIMIT 80""",
                 (search, _like(search), _like(search)))


def _dossier_stock_order(id_: str):
    with tx() as c:
        r = q1(c, """SELECT r.*, COALESCE(f.generic_name, r.sku) AS drug, s.name AS supplier_name FROM royan_replenishment_requests r
                     LEFT JOIN royan_drug_formulary f ON f.id=r.formulary_id LEFT JOIN suppliers s ON s.id=r.supplier_id
                     WHERE r.id::text=%s""", (id_,))
        if not r:
            raise LookupError("Stock order not found")
        names = _names(c, [r["created_by"], r["approved_by"], r.get("ordered_by")])
    lead = (r["fulfilled_at"].date() - r["ordered_at"].date()).days if r.get("ordered_at") and r.get("fulfilled_at") else None
    late = None
    if r.get("expected_date") and r.get("fulfilled_at"):
        late = (r["fulfilled_at"].date() - r["expected_date"]).days
    return _dossier("stock_order", id_, f"Stock order {id_}: {r['drug']}", r["status"],
                    [("Drug", r["drug"]), ("Quantity", r["requested_qty"]), ("Status", r["status"]), ("Urgency", r["urgency"]),
                     ("Raised", r["created_at"]), ("Raised by", _who(names, r["created_by"])), ("Approved", r["approved_at"]),
                     ("Approved by", _who(names, r["approved_by"])), ("Placed with supplier", r.get("ordered_at")),
                     ("Supplier", r["supplier_name"]), ("Expected", r.get("expected_date")), ("Received", r["fulfilled_at"]),
                     ("Quantity received", r.get("received_qty")), ("Received through", r.get("received_source")),
                     ("Lead time (days)", lead), ("Days late (+) / early (-)", late), ("Cancelled because", r.get("cancelled_reason"))],
                    [("Notes", r["notes"])], links=[("Procurement", "/procurement?tab=orders")])


# ---------------------------------------------------------------------------
# Clinical
# ---------------------------------------------------------------------------

def _list_encounters(search: str):
    if len((search or "").strip()) < 2:
        return []
    with tx() as c:
        return q(c, """SELECT e.id::text AS id, concat_ws(' ', p.first_name, p.last_name, '(' || p.mrn || ')') AS title,
                              concat_ws(' · ', e.encounter_type, e.department, left(e.chief_complaint, 50)) AS subtitle,
                              e.created_at::date AS date, e.status
                       FROM royan_encounters e JOIN royan_patients p ON p.id=e.patient_id
                       WHERE p.mrn ILIKE %s OR concat_ws(' ', p.first_name, p.last_name) ILIKE %s
                       ORDER BY e.created_at DESC LIMIT 40""", (_like(search), _like(search)))


def _dossier_encounter(id_: str):
    with tx() as c:
        e = q1(c, """SELECT e.*, p.mrn, concat_ws(' ', p.first_name, p.last_name) AS patient, p.date_of_birth, p.gender, p.allergies
                     FROM royan_encounters e JOIN royan_patients p ON p.id=e.patient_id WHERE e.id::text=%s""", (id_,))
        if not e:
            raise LookupError("Encounter not found")
        notes = q(c, """SELECT created_at, note_type, note_title, author_name, subjective, objective, assessment, plan, content, signed_at
                        FROM royan_encounter_notes WHERE encounter_id=%s ORDER BY created_at""", (e["id"],))
        vitals = q(c, """SELECT recorded_at, temperature, pulse, respiratory_rate, bp_systolic, bp_diastolic, spo2, weight
                         FROM royan_vitals WHERE encounter_id=%s ORDER BY recorded_at""", (e["id"],))
        labs = q(c, """SELECT o.test_name, o.status, o.ordered_at, r.result_summary, r.interpretation, r.is_critical, r.verified_at
                       FROM royan_lab_orders o LEFT JOIN royan_lab_results r ON r.lab_order_id=o.id WHERE o.encounter_id=%s
                       ORDER BY o.ordered_at""", (e["id"],))
        rx = q(c, """SELECT drug_name, dosage, frequency, duration, route, status FROM royan_prescriptions WHERE encounter_id=%s
                     ORDER BY prescribed_at""", (e["id"],))
    def note_text(n):
        parts = [f"{k}: {n[k]}" for k in ("subjective", "objective", "assessment", "plan") if n.get(k)]
        return " | ".join(parts) or (n.get("content") or "")
    age = None
    if e["date_of_birth"]:
        age = (dt.date.today() - e["date_of_birth"]).days // 365
    return _dossier("encounter", id_, f"{e['patient']} ({e['mrn']}), {_d(e['created_at'])}",
                    f"{e['encounter_type'] or ''} · {e['department'] or ''} · {e['status']}",
                    [("Patient", e["patient"]), ("MRN", e["mrn"]), ("Age", age), ("Sex", e["gender"]),
                     ("Allergies recorded", e["allergies"] or "none recorded (absence of a record is not absence of allergy)"),
                     ("Encounter type", e["encounter_type"]), ("Department", e["department"]), ("Opened", e["created_at"]),
                     ("Triage level", e["triage_level"]), ("Seen by", e["consulting_doctor"]), ("Diagnosis codes", e["diagnosis_codes"]),
                     ("Discharged", e["discharge_at"]), ("Payer", e["payer_type"])],
                    [("Chief complaint", e["chief_complaint"]), ("Triage notes", e["triage_notes"]),
                     ("Diagnosis notes", e["diagnosis_notes"]), ("Discharge summary on record", e["discharge_summary"])],
                    [_table("Clinical notes", ["When", "Type", "Author", "Note", "Signed"],
                            [[n["created_at"], n["note_title"] or n["note_type"], n["author_name"], note_text(n)[:600], n["signed_at"]] for n in notes]),
                     _table("Vital signs", ["When", "Temp", "Pulse", "RR", "BP", "SpO2", "Weight"],
                            [[v["recorded_at"], v["temperature"], v["pulse"], v["respiratory_rate"],
                              f"{v['bp_systolic']}/{v['bp_diastolic']}" if v["bp_systolic"] else None, v["spo2"], v["weight"]] for v in vitals]),
                     _table("Investigations", ["Test", "Status", "Ordered", "Result", "Interpretation", "Critical", "Verified"],
                            [[l["test_name"], l["status"], l["ordered_at"], (l["result_summary"] or "")[:200], l["interpretation"],
                              "yes" if l["is_critical"] else "", l["verified_at"]] for l in labs]),
                     _table("Medication", ["Drug", "Dose", "Frequency", "Duration", "Route", "Status"],
                            [[m["drug_name"], m["dosage"], m["frequency"], m["duration"], m["route"], m["status"]] for m in rx])],
                    _gaps([("Diagnosis (codes or notes)", e["diagnosis_codes"] or e["diagnosis_notes"]), ("Clinical notes", notes),
                           ("Vital signs", vitals)]) + (["Lab results not yet verified"] if any(l["status"] and not l["verified_at"] for l in labs) else []),
                    [("Patient record", f"/hospital/patients/{e['mrn']}")])


# ---------------------------------------------------------------------------
# Management
# ---------------------------------------------------------------------------

def _month(pid: str) -> Tuple[dt.date, dt.date]:
    if not re.fullmatch(r"\d{4}-\d{2}", pid or ""):
        raise ValueError("Choose a month (YYYY-MM)")
    a = dt.date(int(pid[:4]), int(pid[5:]), 1)
    b = (a.replace(day=28) + dt.timedelta(days=4)).replace(day=1) - dt.timedelta(days=1)
    return a, b


def _list_periods(search: str):
    with tx() as c:
        to = q1(c, "SELECT MAX(charge_date) AS d FROM fin_hope_charges")["d"] or dt.date.today()
    t = dt.date.today()
    out, m = [], t.replace(day=1)
    for _ in range(30):
        key = f"{m:%Y-%m}"
        status = "billing loaded" if m <= to else "no billing loaded yet"
        if not search or search in key or search.lower() in m.strftime("%B %Y").lower():
            out.append({"id": key, "title": m.strftime("%B %Y"), "subtitle": status, "date": m, "status": status})
        m = (m - dt.timedelta(days=1)).replace(day=1)
    return out


def _dossier_period(pid: str):
    from src.fin import payers
    from src.fin.context import resolve_entity
    a, b = _month(pid)
    with tx() as c:
        e = resolve_entity(c, None)
        to = q1(c, "SELECT MAX(charge_date) AS d FROM fin_hope_charges")["d"]
        mix = payers.payer_mix(c, e, {"month": pid})["rows"]
        totals = q1(c, """SELECT SUM(gross - discount) FILTER (WHERE payer_type<>'INTERNAL') AS billed,
                                 SUM(gross - discount) FILTER (WHERE payer_type IN ('HMO','CORPORATE')) AS hmo,
                                 SUM(gross - discount) FILTER (WHERE payer_type='PRIVATE') AS private,
                                 SUM(discount) AS discounts, COUNT(DISTINCT visit_id) AS visits, COUNT(DISTINCT patient_id) AS patients
                          FROM fin_v_hope_charges WHERE charge_date BETWEEN %s AND %s""", (a, b))
        prev_a = (a - dt.timedelta(days=1)).replace(day=1)
        prev = q1(c, "SELECT SUM(gross - discount) FILTER (WHERE payer_type<>'INTERNAL') AS billed FROM fin_v_hope_charges WHERE charge_date BETWEEN %s AND %s",
                  (prev_a, a - dt.timedelta(days=1)))
        ly = q1(c, "SELECT SUM(gross - discount) FILTER (WHERE payer_type<>'INTERNAL') AS billed FROM fin_v_hope_charges WHERE charge_date BETWEEN %s AND %s",
                (a.replace(year=a.year - 1), b.replace(year=b.year - 1, day=min(b.day, 28)) if b.month == 2 else b.replace(year=b.year - 1)))
        disp = q1(c, "SELECT COUNT(*) AS n, SUM(quantity_dispensed) AS qty FROM royan_dispensing WHERE dispensed_at::date BETWEEN %s AND %s", (a, b))
        inc = q(c, """SELECT category, severity, COUNT(*) AS n FROM royan_incident_reports
                      WHERE COALESCE(incident_date, created_at::date) BETWEEN %s AND %s GROUP BY 1,2 ORDER BY 3 DESC""", (a, b))
        adm = q1(c, "SELECT COUNT(*) AS n FROM royan_ward_stay_history WHERE admitted_at::date BETWEEN %s AND %s", (a, b)) \
            if q1(c, "SELECT 1 FROM information_schema.columns WHERE table_name='royan_ward_stay_history' AND column_name='admitted_at'") else None
    gaps = []
    if to and b > to:
        gaps.append(f"Hope billing is loaded only to {_d(to)} - this month is {'partly' if a <= to else 'not'} covered")
    if adm is None:
        gaps.append("Admissions for the month could not be counted from the ward history")
    return _dossier("period", pid, f"Monthly hospital report - {a:%B %Y}", f"{_d(a)} to {_d(b)}",
                    [("Billed (excluding internal)", _n(totals["billed"])), ("To HMOs & corporates", _n(totals["hmo"])),
                     ("To private patients", _n(totals["private"])), ("Discounts given", _n(totals["discounts"])),
                     ("Visits billed", totals["visits"]), ("Patients billed", totals["patients"]),
                     ("Billed the month before", _n(prev["billed"])), ("Billed the same month last year", _n(ly["billed"])),
                     ("Dispensings / units dispensed", f"{disp['n'] or 0} / {_f(disp['qty']):,.0f}"),
                     ("Admissions", adm["n"] if adm else None), ("Incidents reported", sum(i["n"] for i in inc))],
                    tables=[_table("Billing by department and payer", ["Department", "Visits", "Private", "HMO", "Corporate", "Staff", "Total"],
                                   [[r["department"], r["visits"], _n(r.get("private")), _n(r.get("hmo")), _n(r.get("corporate")),
                                     _n(r.get("staff")), _n(r.get("total"))] for r in mix]),
                            _table("Incidents", ["Category", "Severity", "Count"], [[i["category"], i["severity"], i["n"]] for i in inc])],
                    gaps=gaps, links=[("HMO vs private report", "/finance/books/reports?r=payer-mix")])


def _dossier_current():
    from src.services import executive
    d = executive.overview()
    f, debt, bill, pat, ql, p = (d.get(k) or {} for k in ("finance", "debtors", "billing", "patients", "quality", "people"))
    st = f.get("stock") or {}
    return _dossier("current", "now", f"Executive report - {dt.date.today():%d %B %Y}", "the hospital today",
                    [("Books live", "yes" if f.get("live") else f"no - ledger ends {_d(f.get('books_to'))}"),
                     ("Billed, 12 months to " + _d(bill.get("as_of")), _n(bill.get("billed_12m"))),
                     ("HMO & corporate share", f"{bill.get('hmo_share_pct')}%"),
                     (f"Revenue in the books, {(f.get('period') or {}).get('label', '')}", _n(f.get("revenue"))),
                     ("Net profit, same period", _n(f.get("net_profit"))), ("Cash & bank at " + _d(f.get("cash_on")), _n(f.get("cash"))),
                     ("HMOs & corporates owe", _n(debt.get("total"))), ("Of which over 90 days", _n(debt.get("over_90"))),
                     ("Pharmacy stock at cost", _n(st.get("shelf_value"))), ("Expired stock on the shelf", _n(st.get("expired_value"))),
                     ("Beds occupied", f"{pat.get('beds_occupied')} of {pat.get('beds_total')}"),
                     ("Patients waiting now", pat.get("patients_waiting")), ("Compliance score", ql.get("compliance_score")),
                     ("Open incidents (serious)", f"{(ql.get('incidents') or {}).get('open')} ({(ql.get('incidents') or {}).get('open_serious')})"),
                     ("Staff", p.get("headcount")), ("Staff with no salary recorded", p.get("no_salary"))],
                    tables=[_table("Needs attention", ["Level", "Item", "Detail"],
                                   [[a["level"], a["title"], a["detail"]] for a in d.get("attention") or []]),
                            _table("Billing by month", ["Month", "Private", "HMO", "Corporate", "Total"],
                                   [[m["period"], _n(m["private"]), _n(m["hmo"]), _n(m["corporate"]), _n(m["total"])] for m in bill.get("months") or []])],
                    gaps=[f"Not available when gathered: {', '.join(d['unavailable'])}"] if d.get("unavailable") else [],
                    links=[("Executive overview", "/executive")])


LISTERS: Dict[str, Callable[[str], List[Dict[str, Any]]]] = {
    "incident": _list_incidents, "audit": _list_audits, "maintenance": _list_maintenance, "payer": _list_payers,
    "patient": _list_patients, "drug": _list_drugs, "stock_order": _list_stock_orders, "encounter": _list_encounters,
    "period": _list_periods,
    "current": lambda s: [{"id": "now", "title": "The hospital today", "subtitle": "all departments", "date": dt.date.today(), "status": ""}],
}
DOSSIERS: Dict[str, Callable[[str], Dict[str, Any]]] = {
    "incident": _dossier_incident, "audit": _dossier_audit, "maintenance": _dossier_maintenance, "payer": _dossier_payer,
    "patient": _dossier_patient, "drug": _dossier_drug, "stock_order": _dossier_stock_order, "encounter": _dossier_encounter,
    "period": _dossier_period, "current": lambda _id: _dossier_current(),
}


def _check(roles, kind: str) -> None:
    if kind not in KIND_ROLES:
        raise ValueError("Unknown record type")
    if kind not in kinds_for(roles):
        raise PermissionError(f"Your role cannot write reports about {KIND_LABEL[kind]}")


def list_subjects(roles, kind: str, search: str = "") -> List[Dict[str, Any]]:
    _check(roles, kind)
    return LISTERS[kind]((search or "").strip())


def dossier(roles, report_type: str, kind: str, id_: str) -> Dict[str, Any]:
    _check(roles, kind)
    t = TYPE_BY_KEY.get(report_type)
    if not t or kind not in t["kinds"]:
        raise ValueError(f"A {t['name'] if t else report_type} is not written about {KIND_LABEL.get(kind, kind)}")
    return DOSSIERS[kind](str(id_))


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------

def _S(id_: str, title: str, hint: str) -> Dict[str, str]:
    return {"id": id_, "title": title, "hint": hint}


SECTIONS: Dict[str, List[Dict[str, str]]] = {
    "incident": [
        _S("summary", "Summary", "Which incident, category, severity, where and when, and its current status - 3-4 sentences."),
        _S("event", "What Happened", "The recorded description, immediate action taken and witnesses, strictly from the record."),
        _S("investigation", "Investigation & Root Cause", "Recorded investigation notes, contributing factors and root cause. If not recorded, say so."),
        _S("actions", "Corrective & Preventive Actions", "Each recorded action; say plainly if none are recorded."),
        _S("next", "Status & Next Steps", "What is needed to close the incident, from the gaps and open items in the record."),
    ],
    "audit": [
        _S("summary", "Summary", "Audit, department, date, status, score."),
        _S("scope", "Scope & Schedule", "Risk level, schedule, who scheduled it; whether it is overdue."),
        _S("findings", "Findings", "The recorded findings; if none are recorded, say so."),
        _S("recommendations", "Recommendations & Follow-up", "Recorded recommendations and comparison with earlier audits of the department."),
    ],
    "maintenance": [
        _S("summary", "Summary", "Equipment, type of job, status, whether on schedule."),
        _S("work", "Work Done or Due", "Completion notes and who did it, or what is due."),
        _S("history", "Equipment History", "The equipment's earlier jobs and any pattern."),
        _S("next", "Next Steps", "Next due date and actions."),
    ],
    "payer": [
        _S("summary", "Summary", "Who the payer is, what was billed to them in 12 months and the trend, what they owe and how late."),
        _S("billing", "Billing", "Billing by month and by department; services billed most."),
        _S("account", "Account & Collections", "What is owed by age, what has been received, the oldest unpaid month, and the basis of the figure."),
        _S("relationship", "Relationship", "Recorded contacts and follow-ups; gaps such as missing contact details."),
        _S("actions", "Recommended Actions", "Specific next steps for this account from the facts above."),
    ],
    "patient": [
        _S("summary", "Summary", "The patient's account in brief: bills, what was paid, what is open, and who pays."),
        _S("bills", "Bills & Payments", "Each bill in this system with its status; Hope history by month and payer."),
        _S("balance", "Balance", "What is open now, and any caution about the data."),
    ],
    "drug": [
        _S("summary", "Summary", "Stock on the shelf, value, use per day, cover and reorder status."),
        _S("stock", "Stock & Expiry", "Batches with expiry; expired or near-expiry stock."),
        _S("use", "Use", "Use by month and trend."),
        _S("supply", "Supply", "Recent purchases, suppliers and prices, open orders, and whether cover is enough."),
    ],
    "stock_order": [
        _S("summary", "Summary", "Drug, quantity, supplier, status."),
        _S("timeline", "Timeline", "Raised, approved, placed, expected, received - with who."),
        _S("performance", "Supplier Performance", "Lead time and whether it arrived on time, from the record."),
    ],
    "encounter": [
        _S("presentation", "Presentation", "Who the patient is (age, sex), when and why they attended: the chief complaint and triage, from the record."),
        _S("assessment", "Clinical Assessment", "What the recorded notes say: findings, the clinician's recorded assessment and diagnosis. Never add a diagnosis of your own."),
        _S("investigations", "Investigations", "Tests ordered and recorded results; mark unverified results as unverified."),
        _S("treatment", "Treatment", "Medication and other treatment recorded."),
        _S("plan", "Outcome & Plan", "Discharge status and the recorded plan / follow-up. Say what is not recorded."),
    ],
    "period": [
        _S("summary", "Summary", "The month in one paragraph: billing, HMO vs private, visits, against the month before and a year earlier."),
        _S("billing", "Billing by Department and Payer", "Walk through the table: which departments and payers drove the month."),
        _S("activity", "Clinical & Pharmacy Activity", "Visits, admissions, dispensing."),
        _S("quality", "Quality & Safety", "Incidents reported by category and severity."),
        _S("notes", "Points to Note & Recommendations", "Gaps in the data, risks and specific actions."),
    ],
    "current": [
        _S("summary", "Summary", "The hospital today in one paragraph, stating the dates the data reaches."),
        _S("finance", "Finance", "Billing, revenue and profit in the books, cash, what HMOs owe."),
        _S("operations", "Patients, Pharmacy & Quality", "Today's flow and beds, pharmacy stock and expiry, compliance and incidents."),
        _S("attention", "What Needs Attention", "The attention list, most serious first."),
        _S("actions", "Recommendations", "Specific actions for management."),
    ],
}


def sections_for(report_type: str, kind: str) -> List[Dict[str, str]]:
    return SECTIONS.get(kind) or SECTIONS["period"]


def dossier_markdown(d: Dict[str, Any]) -> str:
    """The gathered record, as the report's appendix (exactly what the report was written from)."""
    out = ["## Appendix: Record details (as gathered from the system)", "", "| Item | Value |", "|---|---|"]
    out += [f"| {f['label']} | {str(f['value']).replace('|', '/')} |" for f in d["facts"]]
    for t in d["texts"]:
        out += ["", f"**{t['label']}:** {t['value']}"]
    for t in d["tables"]:
        out += ["", f"### {t['title']}", "", "| " + " | ".join(t["columns"]) + " |", "|" + "---|" * len(t["columns"])]
        out += ["| " + " | ".join(str(c).replace("|", "/").replace("\n", " ") for c in r) + " |" for r in t["rows"][:60]]
    if d["gaps"]:
        out += ["", "**Not recorded in the system:**"] + [f"- {g}" for g in d["gaps"]]
    out += ["", f"_Gathered {d['gathered_at'][:16].replace('T', ' ')} UTC._"]
    return "\n".join(out)
