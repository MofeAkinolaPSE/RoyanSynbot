"""Roy's live lookups over the hub services (reportGUide.md s13).

Each tool is a narrow read over the same service the page uses, so Roy and the screen can never
disagree, and returns a small, already-summarised answer with the date its data reaches. Access
follows the screens: the tool registry checks the caller's roles before any of these run.

Every result carries a `status` - "ok", "not_found" or "none" - so Roy says "I couldn't find that
drug" or "nothing is due" instead of guessing.
"""
from __future__ import annotations

import datetime as dt
import re
from typing import Any, Dict, List, Optional


def _words(text: Optional[str]) -> List[str]:
    stop = {"what", "which", "when", "where", "much", "many", "have", "does", "with", "from", "that", "this", "there",
            "stock", "order", "reorder", "drug", "drugs", "left", "shelf", "level", "levels", "about", "tell", "show",
            "status", "please", "pharmacy", "expiry", "expire", "expiring", "running", "out", "need", "should", "account",
            "owe", "owes", "billed", "bill", "hmo", "hmos", "payer", "insurance", "company", "corporate", "how", "the", "for"}
    return [w for w in re.findall(r"[a-z0-9]+", (text or "").lower()) if len(w) >= 4 and w not in stop]


_DRUG_WORDS: Dict[str, Any] = {}


def mentions_drug(question: Optional[str]) -> bool:
    """True when the question names a drug in the formulary ("how much amoxicillin is left?"), so Roy
    looks at stock even when the word "stock" is never said. The word list is cached for an hour."""
    import time
    hit = _DRUG_WORDS.get("w")
    if not hit or time.monotonic() - hit[0] > 3600:
        from src.fin.db import q, tx
        with tx() as conn:
            rows = q(conn, "SELECT generic_name, brand_name FROM royan_drug_formulary WHERE deprecated_at IS NULL")
        words = {w for r in rows for n in (r["generic_name"], r["brand_name"]) for w in re.findall(r"[a-z]{6,}", (n or "").lower())}
        hit = _DRUG_WORDS["w"] = (time.monotonic(), words)
    return any(w in hit[1] for w in re.findall(r"[a-z]{6,}", (question or "").lower()))


def hospital_overview() -> Dict[str, Any]:
    from src.services import executive
    d = executive.overview()
    f, debt, bill, pat, ql, ppl = (d.get(k) or {} for k in ("finance", "debtors", "billing", "patients", "quality", "people"))
    st = f.get("stock") or {}
    return {
        "status": "ok",
        "books": "live" if f.get("live") else f"not live - the ledger ends {f.get('books_to')}, hospital billing ends {f.get('hope_to')}",
        "billed_12_months": {"to": bill.get("as_of"), "total": bill.get("billed_12m"), "hmo_and_corporate_share_pct": bill.get("hmo_share_pct")},
        "books_period": (f.get("period") or {}).get("label"),
        "revenue_in_books": f.get("revenue"), "net_profit_in_books": f.get("net_profit"),
        "cash": {"amount": f.get("cash"), "at": f.get("cash_on")},
        "hmos_and_corporates_owe": {"total": debt.get("total"), "over_90_days": debt.get("over_90"), "at": debt.get("as_of")},
        "pharmacy_stock_at_cost": st.get("shelf_value"), "expired_on_shelf": st.get("expired_value"),
        "patients_now": {"waiting": pat.get("patients_waiting"), "with_doctor": pat.get("active_consultations"),
                         "beds": f"{pat.get('beds_occupied')} of {pat.get('beds_total')} occupied"},
        "compliance_score": ql.get("compliance_score"),
        "staff": {"headcount": ppl.get("headcount"), "on_clock": ppl.get("on_clock"), "no_salary_recorded": ppl.get("no_salary")},
        "needs_attention": [f"[{a['level']}] {a['title']}" + (f" - {a['detail']}" if a.get("detail") else "") for a in d.get("attention") or []][:10],
        "page": "/executive",
    }


def stock_status(query: Optional[str] = None) -> Dict[str, Any]:
    from src.services import stock_orders
    plan = stock_orders.reorder_plan()
    words = _words(query)
    keep = ("drug", "on_hand", "expired", "per_day", "cover_days", "status", "suggested_qty", "on_order",
            "next_expiry", "expiry_risk_qty", "last_supplier", "last_cost", "last_bought")
    if words:
        hits = [i for i in plan["items"] if any(w in (f"{i['drug']} {i.get('brand') or ''} {i['code']}").lower() for w in words)]
        if not hits:
            return {"status": "not_found", "searched_for": words, "note": "No drug in the formulary matches that name.",
                    "use_measured_to": plan["demand_to"]}
        return {"status": "ok", "use_measured_to": plan["demand_to"], "use_window_days": plan["demand_days"],
                "drugs": [{k: i.get(k) for k in keep} for i in hits[:8]], "page": "/procurement"}
    now = [i for i in plan["items"] if i["status"] in ("out_of_stock", "reorder_now")]
    return {"status": "ok", "use_measured_to": plan["demand_to"], "counts": plan["counts"],
            "value_to_order_now": plan["to_order_value"], "drugs_that_may_expire_unused": plan["expiry_risk"],
            "order_now": [{k: i.get(k) for k in ("drug", "on_hand", "per_day", "suggested_qty", "last_supplier")} for i in now[:12]],
            "page": "/procurement"}


def payer_account(query: Optional[str] = None) -> Dict[str, Any]:
    from src.services import payer_relations
    d = payer_relations.directory()
    words = _words(query)
    if words:
        hits = [p for p in d["payers"] if any(w in (p["name"] or "").lower() for w in words)]
        if not hits:
            return {"status": "not_found", "searched_for": words, "note": "No HMO or corporate payer matches that name."}
        p = hits[0]
        prof = payer_relations.profile(p["id"])
        return {"status": "ok", "billing_to": d["as_of"], "payer": p["name"], "type": p["payer_type"], "segment": p["segment"],
                "billed_12_months": p["billed_12m"], "billed_year_before": p["billed_prior_12m"], "change_pct": p["change_pct"],
                "patients_12_months": p["patients_12m"], "owes": p["owed"], "owes_over_90_days": p["owed_over_90"],
                "oldest_unpaid_month": p["oldest_open"], "at_risk_because": p["risk_reasons"],
                "last_6_months": prof["months"][-6:], "top_departments": prof["departments"][:5],
                "recent_contacts": [{"date": c["created_at"], "kind": c["kind"], "summary": c["summary"][:160]} for c in prof["contacts"][:5]],
                "other_matches": [x["name"] for x in hits[1:5]], "page": f"/relations?payer={p['id']}"}
    top = d["payers"][:10]
    return {"status": "ok", "billing_to": d["as_of"], "counts": d["counts"], "at_risk": d["at_risk"],
            "top_by_billing": [{"payer": p["name"], "billed_12m": p["billed_12m"], "owes": p["owed"]} for p in top],
            "owe_most": [{"payer": p["name"], "owes": p["owed"], "over_90": p["owed_over_90"]}
                         for p in sorted(d["payers"], key=lambda x: -x["owed"])[:8] if p["owed"] > 0],
            "page": "/relations"}


def my_day(user_id: Optional[str] = None, roles: Optional[List[str]] = None) -> Dict[str, Any]:
    from src.services import staff_workspace
    if not user_id:
        return {"status": "none", "note": "Sign in with a staff account to see your day."}
    d = staff_workspace.my_day({"sub": user_id, "roles": roles or []})
    c = d["counts"]
    def item(x: Dict[str, Any]) -> Dict[str, Any]:
        inner = x.get("task") or x.get("event") or {}
        return {"what": inner.get("title"), "at": x.get("at"), "kind": x.get("type"), "overdue": bool(inner.get("overdue"))}
    return {"status": "ok", "date": d["date"], "counts": c, "work_clock": (d.get("clock") or {}).get("status"),
            "today": [item(x) for x in (d.get("timeline") or [])][:10],
            "requests_to_answer": [{"from": r.get("from_name"), "subject": r.get("subject")} for r in d.get("to_answer") or []],
            "for_your_role": [{"what": s.get("label"), "count": s.get("count")} for s in d.get("operational") or [] if s.get("count")][:8],
            "page": "/workspace"}


def hospital_calendar(days: int = 7, roles: Optional[List[str]] = None, user_id: Optional[str] = None) -> Dict[str, Any]:
    from src.services import hospital_calendar as cal
    t = dt.date.today()
    f = cal.feed({"sub": user_id, "roles": roles or []}, t, t + dt.timedelta(days=max(1, min(int(days or 7), 31))))
    ev = f["events"]
    if not ev:
        return {"status": "none", "note": "Nothing on the calendar you can see in that period.", "from": f["from"], "to": f["to"]}
    return {"status": "ok", "from": f["from"], "to": f["to"],
            "entries": [{"date": e["date"], "time": e["time"], "what": e["title"], "detail": e["detail"][:100], "kind": e["source"]} for e in ev[:30]],
            "total": len(ev), "page": "/calendar"}


def compliance_status() -> Dict[str, Any]:
    from src.services import quality_hub
    d = quality_hub.compliance()
    return {"status": "ok", "score": d["compliance_score"],
            "pulling_it_down": [f"{x['item']}: {x['count']} (-{x['points']})" for x in d["deductions"] if x["points"]],
            "incidents": d["incidents"], "audits": d["audits"], "maintenance": d["maintenance"],
            "hefamaa": d["hefamaa"], "page": "/compliance"}
