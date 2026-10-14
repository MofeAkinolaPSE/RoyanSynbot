"""Patient Relations: the hospital's HMO and corporate accounts (reportGUide.md s7, CRM translated).

  overview()        KPI cards: active payers, billed to payers, owed by payers, follow-ups due
  directory()       every HMO / corporate payer with segment, trend, what they owe and why they are at risk
  profile(id)       one payer: billing by month, services used, patients, account (Roy Books), contacts
  log_contact()     a call / visit / email / note, optionally with a follow-up date
  complete_follow_up()

Nothing about money is stored here. Billing is Hope's charge lines (fin_v_hope_charges), what a
payer owes is Credit Control's figure (fin/credit - billing less receipts until go-live, then the
books), and receipts are their Sage / Roy Books accounts (fin/payers). The payer key is Hope's
tariff id, the same key billing and debt already use.

Definitions (measured to the last day billing reaches, `as_of`):
  active    billed in the last 90 days          new     first bill in the last 90 days
  lapsing   last bill 3-12 months ago           lapsed  last bill over 12 months ago
  at risk   billing down 30%+ on the year before (and it was over N1m), or over half of what they
            owe is more than 90 days old
"""
from __future__ import annotations

import datetime as dt
import threading
import time
from typing import Any, Dict, List, Optional

from src.fin.db import money, q, q1, tx

KINDS = ("call", "visit", "email", "meeting", "note")


class RelationsError(ValueError):
    pass


def _f(v: Any) -> float:
    return float(money(v)) if v is not None else 0.0


def _as_of(conn) -> dt.date:
    return q1(conn, "SELECT MAX(charge_date) AS d FROM fin_hope_charges")["d"] or dt.date.today()


def _debts() -> Dict[int, Dict[str, Any]]:
    from src.fin import credit
    d = credit._debtors_cached()
    return {r["payer_id"]: r for r in d["rows"] if r.get("payer_id") is not None}


_BILLING: Dict[str, Any] = {}
_BILLING_LOCK = threading.Lock()
BILLING_TTL = 300   # Hope charges arrive in batches; five minutes old is fresh enough for account management


def _billing() -> tuple:
    """Per payer billing aggregated over two years of Hope charge lines - the expensive part of the
    directory (about a second), so it is computed once per five minutes per worker, one request at a time."""
    hit = _BILLING.get("v")
    if hit and time.monotonic() - hit[0] < BILLING_TTL:
        return hit[1]
    with _BILLING_LOCK:
        hit = _BILLING.get("v")
        if hit and time.monotonic() - hit[0] < BILLING_TTL:
            return hit[1]
        with tx() as conn:
            on = _as_of(conn)
            rows = q(conn, """
                SELECT p.tariff_id AS id, p.name, p.payer_type, p.hmo_id, p.customer_id,
                       MIN(c.charge_date) AS first_bill, MAX(c.charge_date) AS last_bill,
                       COALESCE(SUM(c.gross - c.discount) FILTER (WHERE c.charge_date > %(on)s::date - 365), 0) AS billed_12m,
                       COALESCE(SUM(c.gross - c.discount) FILTER (WHERE c.charge_date <= %(on)s::date - 365
                                                                    AND c.charge_date > %(on)s::date - 730), 0) AS billed_prior_12m,
                       COUNT(DISTINCT c.patient_id) FILTER (WHERE c.charge_date > %(on)s::date - 365) AS patients_12m,
                       COUNT(DISTINCT c.visit_id) FILTER (WHERE c.charge_date > %(on)s::date - 365) AS visits_12m
                FROM fin_hope_payers p LEFT JOIN fin_v_hope_charges c ON c.payer_tariff_id=p.tariff_id
                WHERE p.payer_type IN ('HMO','CORPORATE')
                GROUP BY p.tariff_id, p.name, p.payer_type, p.hmo_id, p.customer_id""", {"on": on})
        _BILLING["v"] = (time.monotonic(), (on, rows))
        return on, rows


def directory() -> Dict[str, Any]:
    on, rows = _billing()
    with tx() as conn:
        fu = {r["payer_id"]: r for r in q(conn, """
            SELECT payer_id, COUNT(*) FILTER (WHERE follow_up_on <= current_date) AS due,
                   MIN(follow_up_on) AS next_follow_up, MAX(created_at) AS last_contact
            FROM royan_payer_contacts WHERE follow_up_done_at IS NULL OR follow_up_on IS NULL GROUP BY payer_id""")}
        last_contact = {r["payer_id"]: r["d"] for r in q(conn, "SELECT payer_id, MAX(created_at) AS d FROM royan_payer_contacts GROUP BY 1")}
    debts = _debts()
    out = []
    for r in rows:
        billed, prior = _f(r["billed_12m"]), _f(r["billed_prior_12m"])
        last, first = r["last_bill"], r["first_bill"]
        days = (on - last).days if last else None
        if not last:
            seg = "never_billed"
        elif first and (on - first).days <= 90:
            seg = "new"
        elif days <= 90:
            seg = "active"
        elif days <= 365:
            seg = "lapsing"
        else:
            seg = "lapsed"
        d = debts.get(r["id"]) or {}
        owed = _f(d.get("total_balance"))
        over_90 = _f((d.get("buckets") or {}).get("91_plus"))
        reasons = []
        if prior >= 1_000_000 and billed <= prior * 0.7:
            reasons.append(f"billing down {round((1 - billed / prior) * 100)}% on the year before")
        if owed > 0 and over_90 >= owed * 0.5:
            reasons.append(f"owes ₦{over_90:,.0f} over 90 days old")
        f = fu.get(r["id"]) or {}
        out.append({"id": r["id"], "name": r["name"], "payer_type": r["payer_type"], "hmo_id": r["hmo_id"],
                    "customer_id": r["customer_id"], "segment": seg, "first_bill": first, "last_bill": last,
                    "days_since_bill": days, "billed_12m": round(billed, 2), "billed_prior_12m": round(prior, 2),
                    "change_pct": round((billed - prior) / prior * 100, 1) if prior else None,
                    "patients_12m": int(r["patients_12m"] or 0), "visits_12m": int(r["visits_12m"] or 0),
                    "owed": round(owed, 2), "owed_over_90": round(over_90, 2), "oldest_open": d.get("earliest_due_date"),
                    "at_risk": bool(reasons), "risk_reasons": reasons, "follow_ups_due": int(f.get("due") or 0),
                    "next_follow_up": f.get("next_follow_up"), "last_contact": last_contact.get(r["id"])})
    out.sort(key=lambda x: (-x["billed_12m"], x["name"] or ""))
    segs = ("active", "new", "lapsing", "lapsed", "never_billed")
    return {"as_of": on, "payers": out, "counts": {s: sum(1 for p in out if p["segment"] == s) for s in segs},
            "at_risk": sum(1 for p in out if p["at_risk"])}


def overview() -> Dict[str, Any]:
    d = directory()
    ps = d["payers"]
    with tx() as conn:
        due = q1(conn, """SELECT COUNT(*) AS n FROM royan_payer_contacts
                          WHERE follow_up_on <= current_date AND follow_up_done_at IS NULL""")["n"]
        week = q1(conn, "SELECT COUNT(*) AS n FROM royan_payer_contacts WHERE created_at > now() - interval '7 days'")["n"]
    billed = sum(p["billed_12m"] for p in ps)
    owed = sum(p["owed"] for p in ps)
    top10 = sum(p["billed_12m"] for p in ps[:10])
    return {"as_of": d["as_of"], "active": d["counts"]["active"] + d["counts"]["new"], "counts": d["counts"],
            "billed_12m": round(billed, 2), "owed": round(owed, 2),
            "owed_over_90": round(sum(p["owed_over_90"] for p in ps), 2), "at_risk": d["at_risk"],
            "follow_ups_due": int(due or 0), "contacts_7d": int(week or 0),
            "top10_share_pct": round(top10 / billed * 100, 1) if billed else None}


def profile(payer_id: int) -> Dict[str, Any]:
    from src.fin import payers as fin_payers
    from src.fin.context import resolve_entity
    with tx() as conn:
        p = q1(conn, """SELECT p.tariff_id AS id, p.name, p.payer_type, p.hmo_id, p.customer_id, p.sage_code,
                               h.contact_phone, h.contact_email, h.notes AS hmo_notes, h.code AS hmo_code
                        FROM fin_hope_payers p LEFT JOIN royan_hmos h ON h.id=p.hmo_id WHERE p.tariff_id=%s""", (payer_id,))
        if not p or p["payer_type"] not in ("HMO", "CORPORATE"):
            raise LookupError("HMO or corporate payer not found")
        on = _as_of(conn)
        e = resolve_entity(conn, None)
        months = q(conn, """SELECT to_char(charge_date,'YYYY-MM') AS period, SUM(gross - discount) AS billed,
                                   COUNT(DISTINCT patient_id) AS patients, COUNT(DISTINCT visit_id) AS visits
                            FROM fin_v_hope_charges WHERE payer_tariff_id=%s AND charge_date > %s::date - 730
                            GROUP BY 1 ORDER BY 1""", (payer_id, on))
        services = q(conn, """SELECT COALESCE(NULLIF(upper(category),''), source) AS department, SUM(gross - discount) AS billed,
                                     COUNT(*) AS lines, COUNT(DISTINCT patient_id) AS patients
                              FROM fin_v_hope_charges WHERE payer_tariff_id=%s AND charge_date > %s::date - 365
                              GROUP BY 1 ORDER BY 2 DESC LIMIT 12""", (payer_id, on))
        top_services = q(conn, """SELECT service, SUM(gross - discount) AS billed, SUM(quantity) AS quantity
                                  FROM fin_v_hope_charges WHERE payer_tariff_id=%s AND charge_date > %s::date - 365
                                  GROUP BY 1 ORDER BY 2 DESC LIMIT 15""", (payer_id, on))
        tot = q1(conn, """SELECT SUM(gross - discount) AS billed_all, COUNT(DISTINCT patient_id) AS patients_all,
                                 MIN(charge_date) AS first_bill, MAX(charge_date) AS last_bill
                          FROM fin_v_hope_charges WHERE payer_tariff_id=%s""", (payer_id,))
        received = fin_payers._payer_received(conn, e, on).get(payer_id)
        accounts = q(conn, """SELECT a.customer_id, c.name, c.customer_code FROM fin_hope_payer_accounts a
                              LEFT JOIN fin_v_customers c ON c.id=a.customer_id WHERE a.tariff_id=%s""", (payer_id,))
        contacts = q(conn, """SELECT c.id::text AS id, c.kind, c.summary, c.follow_up_on, c.follow_up_done_at, c.created_at,
                                     c.created_by, COALESCE(s.full_name, u.email) AS by_name
                              FROM royan_payer_contacts c LEFT JOIN royan_users u ON u.id::text=c.created_by
                              LEFT JOIN royan_staff s ON s.user_id=u.id
                              WHERE c.payer_id=%s ORDER BY c.created_at DESC LIMIT 100""", (payer_id,))
    d = _debts().get(payer_id) or {}
    gaps = []
    if not p["contact_phone"] and not p["contact_email"]:
        gaps.append("No contact phone or email recorded for this payer")
    if not accounts:
        gaps.append("Not linked to an account in Roy Books / Sage - receipts cannot be matched to it")
    return {
        "as_of": on, "payer": p,
        "months": [{"period": m["period"], "billed": _f(m["billed"]), "patients": m["patients"], "visits": m["visits"]} for m in months],
        "departments": [{**s, "billed": _f(s["billed"])} for s in services],
        "top_services": [{**s, "billed": _f(s["billed"]), "quantity": float(s["quantity"] or 0)} for s in top_services],
        "totals": {"billed_all": _f(tot["billed_all"]), "patients_all": int(tot["patients_all"] or 0),
                   "first_bill": tot["first_bill"], "last_bill": tot["last_bill"], "received": _f(received)},
        "account": {"owed": _f(d.get("total_balance")), "buckets": {k: _f(v) for k, v in (d.get("buckets") or {}).items()},
                    "oldest_open": d.get("earliest_due_date"), "source": d.get("source"), "accounts": accounts},
        "contacts": contacts, "gaps": gaps,
    }


def log_contact(user: Dict[str, Any], payer_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
    kind = (data.get("kind") or "note").lower()
    summary = (data.get("summary") or "").strip()
    if kind not in KINDS:
        raise RelationsError(f"Kind must be one of {', '.join(KINDS)}")
    if not summary:
        raise RelationsError("Say what was discussed")
    fu = data.get("follow_up_on") or None
    if fu and dt.date.fromisoformat(str(fu)[:10]) < dt.date.today():
        raise RelationsError("A follow-up date cannot be in the past")
    with tx() as conn:
        if not q1(conn, "SELECT 1 FROM fin_hope_payers WHERE tariff_id=%s AND payer_type IN ('HMO','CORPORATE')", (payer_id,)):
            raise LookupError("HMO or corporate payer not found")
        r = q1(conn, """INSERT INTO royan_payer_contacts (payer_id, kind, summary, follow_up_on, owner_id, created_by)
                        VALUES (%s,%s,%s,%s,%s,%s) RETURNING id::text AS id""",
               (payer_id, kind, summary, fu, str(user.get("sub")), str(user.get("sub"))))
    _refresh_rule()
    return {"id": r["id"]}


def complete_follow_up(user: Dict[str, Any], contact_id: str) -> Dict[str, Any]:
    with tx() as conn:
        n = q1(conn, """UPDATE royan_payer_contacts SET follow_up_done_at=now()
                        WHERE id::text=%s AND follow_up_on IS NOT NULL AND follow_up_done_at IS NULL RETURNING id""", (contact_id,))
        if not n:
            raise LookupError("Open follow-up not found")
    _refresh_rule()
    return {"id": contact_id, "done": True}


def follow_ups_due(owner_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """For My Day ("For your role"): follow-ups due today or overdue."""
    with tx() as conn:
        return q(conn, """SELECT c.id::text AS id, c.payer_id, p.name AS payer, c.summary, c.follow_up_on
                          FROM royan_payer_contacts c JOIN fin_hope_payers p ON p.tariff_id=c.payer_id
                          WHERE c.follow_up_on <= current_date AND c.follow_up_done_at IS NULL
                            AND (%s::text IS NULL OR c.owner_id=%s) ORDER BY c.follow_up_on""", (owner_id, owner_id))


def _refresh_rule() -> None:
    try:
        from src.services.staff_workspace import refresh_rules
        refresh_rules("relations.follow_ups")
    except Exception:
        pass
