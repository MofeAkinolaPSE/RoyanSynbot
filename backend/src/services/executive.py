"""Executive overview: the hospital on one page, read from the modules that own each figure.

  Finance    Roy Books - income statement, cash by account, books & controls (fin/reports, fin/controls)
  Debtors    what HMOs and corporate payers owe, aged (fin/credit - Hope billing less receipts until go-live)
  Billing    HMO vs private by month and the payers billed most (fin/payers over Hope's charge lines)
  Stock      the pharmacy's shelves beside the books (fin/reports.stock_position), risk tiers (pharmacy service)
  Patients   today's flow, appointments, beds, admissions (services/hospital_ops)
  Quality    incidents, audits, maintenance, compliance score (services/quality_hub)
  People     headcount, on the clock, hours, open work, leave, payroll (services/hr_hub)

Nothing is stored or estimated here (reportGUide.md s11). Each block says the date its data
reaches, because the sources do not all reach today: until Roy Books goes live the ledger ends
at the last Sage year end and billing at the last Hope extract, and the page says so rather
than letting a gap in loaded data look like a collapse in trade. Every figure carries the link
to the page that owns it.
"""
from __future__ import annotations

import datetime as dt
import logging
import time
from typing import Any, Callable, Dict, List, Optional

from src.fin.db import money, q, q1, tx

log = logging.getLogger(__name__)
_CACHE: Dict[str, Any] = {}
TTL = 300


def _f(v: Any) -> float:
    return float(money(v)) if v is not None else 0.0


def _safe(name: str, fn: Callable[[], Any], default: Any = None) -> Any:
    """One module being unavailable must not blank the whole page; the block shows as unavailable."""
    try:
        return fn()
    except Exception as exc:
        log.warning("executive: %s unavailable: %s", name, exc)
        return default


def _pct(a: float, b: float) -> Optional[float]:
    return round((a - b) / b * 100, 1) if b else None


def _months_between(a: dt.date, b: dt.date) -> int:
    """Whole calendar months after a's month up to and including b's month."""
    return max(0, (b.year - a.year) * 12 + b.month - a.month)


# ---------------------------------------------------------------------------

def _finance() -> Dict[str, Any]:
    from src.fin import controls, readmodel, reports
    from src.fin.context import resolve_entity
    today = dt.date.today()
    live = readmodel.live()
    with tx() as conn:
        e = resolve_entity(conn, None)
        books_to = q1(conn, """SELECT MAX(journal_date) AS d FROM fin_v_ledger WHERE legal_entity_id=%s
                               AND journal_type NOT IN ('OPENING','CLOSING')""", (e,))["d"]
        # The year shown is this year once the books are live; before that, the last year the ledger holds.
        on = today if live or not books_to else books_to
        fy0 = reports._fy_start(conn, e, on)
        inc = reports.income_statement(conn, e, fy0, on)
        prior_to = on.replace(year=on.year - 1) if not (on.month == 2 and on.day == 29) else on.replace(year=on.year - 1, day=28)
        prior = reports.income_statement(conn, e, reports._fy_start(conn, e, prior_to), prior_to)
        banks = q(conn, """SELECT account_code AS code, account_name AS name, SUM(debit-credit) AS balance
                           FROM fin_v_ledger WHERE legal_entity_id=%s AND subtype='CASH' AND journal_date <= %s
                           GROUP BY 1,2 HAVING ABS(SUM(debit-credit)) > 0.005 ORDER BY 3 DESC""", (e, on))
        ctl = q1(conn, """SELECT
              (SELECT cutover_date FROM fin_settings WHERE legal_entity_id=%(e)s) AS cutover,
              (SELECT COUNT(DISTINCT bank_account_id) FROM fin_reconciliations WHERE legal_entity_id=%(e)s AND status='COMPLETED') AS reconciled,
              (SELECT MAX(as_of) FROM fin_reconciliations WHERE legal_entity_id=%(e)s AND status='COMPLETED') AS last_reconciled,
              (SELECT COUNT(*) FROM fin_sales_invoices WHERE legal_entity_id=%(e)s AND status='DRAFT') AS draft_invoices,
              (SELECT COUNT(*) FROM fin_supplier_bills WHERE legal_entity_id=%(e)s AND status='DRAFT') AS draft_bills,
              (SELECT COUNT(*) FROM fin_journals WHERE legal_entity_id=%(e)s AND status IN ('DRAFT','SUBMITTED')) AS draft_journals,
              -- months since go-live left open; the months before are Sage history
              (SELECT COUNT(*) FROM fin_periods p WHERE p.legal_entity_id=%(e)s AND p.status='OPEN' AND p.end_date < %(t)s
                 AND p.end_date >= COALESCE((SELECT cutover_date FROM fin_settings WHERE legal_entity_id=%(e)s), %(t)s)) AS past_periods_open,
              (SELECT MAX(charge_date) FROM fin_hope_charges) AS hope_to""", {"e": e, "t": today})
        failed = _safe("operations postings", lambda: (lambda d: len(d["failed"]) + len(d["not_posted"]))(
            controls._operations(conn, e, today)[2]), None) if live else 0
        stock = reports.stock_position(conn, e)
        ap = readmodel.ap_rows(today) if live else []
    rev, net = _f(inc["revenue"]), _f(inc["net_profit"])
    ap_owed = sum(r["balance"] for r in ap if r["balance"] > 0)
    ap_overdue = sum(r["balance"] for r in ap if r["balance"] > 0 and r["due_date"] and r["due_date"] < today)
    ap_due_30 = sum(r["balance"] for r in ap if r["balance"] > 0 and r["due_date"] and today <= r["due_date"] <= today + dt.timedelta(days=30))
    return {
        "live": live, "cutover": ctl["cutover"], "books_to": books_to, "hope_to": ctl["hope_to"],
        # months with no books at all: after the ledger's last day, up to this month (0 once live)
        "missing_months": 0 if live or not books_to else _months_between(books_to, today),
        "period": {"from": fy0, "to": on, "label": f"{'This year' if live else f'FY{fy0.year}'} to {on:%d %b %Y}"},
        "revenue": rev, "revenue_prior": _f(prior["revenue"]), "revenue_growth_pct": _pct(rev, _f(prior["revenue"])),
        "cost_of_sales": _f(inc["cost_of_sales"]), "gross_profit": _f(inc["gross_profit"]),
        "gross_margin_pct": float(inc["gross_margin_pct"]) if inc["gross_margin_pct"] is not None else None,
        "operating_profit": _f(inc["operating_profit"]), "net_profit": net,
        "net_margin_pct": round(net / rev * 100, 1) if rev else None,
        "cash": round(sum(_f(b["balance"]) for b in banks), 2), "cash_on": on,
        "banks": [{"code": b["code"], "name": b["name"], "balance": _f(b["balance"])} for b in banks],
        "payables": {"tracked": live, "total": round(ap_owed, 2), "overdue": round(ap_overdue, 2), "due_30": round(ap_due_30, 2)},
        "stock": {k: (_f(v) if k in ("books_value", "shelf_value", "expired_value", "expiring_90_value", "difference") else v)
                  for k, v in stock.items()},
        "controls": {"bank_accounts_holding": len(banks), "reconciled": int(ctl["reconciled"] or 0),
                     "last_reconciled": ctl["last_reconciled"], "drafts": int((ctl["draft_invoices"] or 0) + (ctl["draft_bills"] or 0)
                                                                               + (ctl["draft_journals"] or 0)),
                     "past_periods_open": int(ctl["past_periods_open"] or 0), "failed_postings": failed},
    }


def _debtors() -> Dict[str, Any]:
    """Who owes the hospital, in two parts that must not be added together (Oct 2026):

    live    - Roy Books open items since go-live: HMOs and corporates (the HMO pays the whole bill; the patient only
              signs the claims form, so the HMO owes Royan until it settles its monthly claim) and patients (unpaid
              bills).
    legacy  - HMO billing in Hope before go-live less the HMO receipts in Sage. Hope billing reaches Jan 2026 but
              Sage receipts are loaded only to 31 Dec 2024, so every 2025 payment is missing and the whole balance
              looks unpaid and over 90 days. It is a figure to reconcile, not money known to be overdue."""
    from src.fin import credit
    d = credit._debtors_cached()
    live = [r for r in d["rows"] if r.get("source") == "Roy Books open items"]
    legacy = [r for r in d["rows"] if r.get("source") != "Roy Books open items"]

    def bucketed(rows):
        b = {k: 0.0 for k in ("0_30", "31_60", "61_90", "91_plus")}
        for r in rows:
            for k in b:
                b[k] += _f((r.get("buckets") or {}).get(k))
        return {k: round(v, 2) for k, v in b.items()}

    payer = [r for r in live if (r.get("payer_type") or "").upper() in ("HMO", "CORPORATE")]
    patient = [r for r in live if r not in payer]
    pb = bucketed(payer)
    payer_total = round(sum(_f(r["total_balance"]) for r in payer), 2)
    with tx() as conn:
        # the last day of loaded Sage trading (receipts included); the go-live opening-balance adjustment is not trading
        receipts_to = q1(conn, """SELECT MAX(journal_date) AS d FROM fin_v_ledger WHERE journal_type NOT IN ('OPENING','CLOSING','ADJUSTMENT')
                                  AND journal_date < (SELECT MIN(cutover_date) FROM fin_settings WHERE cutover_date IS NOT NULL)""")["d"]
    legacy_total = round(sum(_f(r["total_balance"]) for r in legacy), 2)
    top = sorted(payer, key=lambda r: -_f(r["total_balance"]))[:8]
    return {"as_of": d["as_of"], "source": "Roy Books since go-live",
            # HMOs and corporates since go-live (the card and the age bar)
            "total": payer_total, "payers": len(payer), "buckets": pb, "over_90": pb["91_plus"],
            "over_90_pct": round(pb["91_plus"] / payer_total * 100, 1) if payer_total else None,
            "patients_owe": round(sum(_f(r["total_balance"]) for r in patient), 2), "patients": len(patient),
            "legacy": {"total": legacy_total, "payers": len(legacy), "billed_to": d.get("hope_to"), "receipts_to": receipts_to,
                       "top": [{"name": r["name"], "owed": _f(r["total_balance"])} for r in
                               sorted(legacy, key=lambda r: -_f(r["total_balance"]))[:5]]},
            "top": [{"name": r["name"], "owed": _f(r["total_balance"]), "payer_type": r.get("payer_type"),
                     "oldest": r["earliest_due_date"], "payer_id": r.get("payer_id")} for r in top]}


def _billing() -> Dict[str, Any]:
    """HMO vs private by month for the 12 months to the last billed day, the same month a year earlier, top payers."""
    from src.fin import payers
    from src.fin.context import resolve_entity
    with tx() as conn:
        e = resolve_entity(conn, None)
        to = q1(conn, "SELECT MAX(charge_date) AS d FROM fin_hope_charges")["d"]
        if not to:
            return {"as_of": None}
        # 24 months, so each of the last 12 has its month a year earlier to compare with
        start = (to.replace(day=1) - dt.timedelta(days=731)).replace(day=1)
        rows = payers.payer_mix(conn, e, {"from": start, "to": to})["rows"]
        top = q(conn, """SELECT c.payer_tariff_id AS id, MAX(p.name) AS name, MAX(c.payer_type) AS payer_type,
                                SUM(c.gross - c.discount) AS billed, COUNT(DISTINCT c.patient_id) AS patients
                         FROM fin_v_hope_charges c LEFT JOIN fin_hope_payers p ON p.tariff_id=c.payer_tariff_id
                         WHERE c.payer_type IN ('HMO','CORPORATE') AND c.charge_date > %s::date - 365 AND c.charge_date <= %s
                         GROUP BY 1 ORDER BY 4 DESC LIMIT 8""", (to, to))
    by_m = {r["month"]: r for r in rows}
    trend = []
    for r in rows[-12:]:
        ly = by_m.get(f"{int(r['month'][:4]) - 1}{r['month'][4:]}")
        trend.append({"period": r["month"], "private": _f(r.get("private")), "hmo": _f(r.get("hmo")),
                      "corporate": _f(r.get("corporate")), "staff": _f(r.get("staff")),
                      "total": _f(r.get("total")) - _f(r.get("internal")), "visits": int(r.get("visits") or 0),
                      "hmo_share": r.get("hmo_share"), "last_year": (_f(ly.get("total")) - _f(ly.get("internal"))) if ly else None})
    tot = sum(t["total"] for t in trend)
    hmo = sum(t["hmo"] + t["corporate"] for t in trend)
    last = trend[-1] if trend else None
    return {
        "as_of": to, "months": trend, "billed_12m": round(tot, 2),
        "hmo_12m": round(hmo, 2), "private_12m": round(sum(t["private"] for t in trend), 2),
        "hmo_share_pct": round(hmo / tot * 100, 1) if tot else None,
        "visits_12m": sum(t["visits"] for t in trend),
        "last_month": last, "last_month_partial": bool(last and to.month == (to + dt.timedelta(days=1)).month),
        "top_payers": [{"id": r["id"], "name": r["name"], "payer_type": r["payer_type"], "billed": _f(r["billed"]),
                        "patients": int(r["patients"] or 0), "share_pct": round(_f(r["billed"]) / tot * 100, 1) if tot else None}
                       for r in top],
    }


def _patients() -> Dict[str, Any]:
    from src.services import hospital_ops
    flow = hospital_ops.get_patient_flow_kpis()
    clin = hospital_ops.get_daily_clinical_stats()
    with tx() as conn:
        beds = q1(conn, """SELECT COUNT(*) AS total, COUNT(*) FILTER (WHERE status='occupied') AS occupied,
                                  COUNT(*) FILTER (WHERE status NOT IN ('occupied','available')) AS other
                           FROM royan_beds""")
        adm = q1(conn, """SELECT COUNT(*) FILTER (WHERE status='pending') AS pending,
                                 COUNT(*) FILTER (WHERE status='admitted' AND decided_at > now() - interval '30 days') AS admitted_30d
                          FROM royan_admission_requests""")
        reg = q1(conn, """SELECT COUNT(*) AS total, COUNT(*) FILTER (WHERE registered_at > now() - interval '30 days'
                                                                     AND external_source IS NULL) AS new_30d
                          FROM royan_patients""")
        last_visit = q1(conn, "SELECT MAX(created_at) AS d FROM royan_encounters WHERE external_source IS NULL")["d"]
    total, occ = int(beds["total"] or 0), int(beds["occupied"] or 0)
    return {**flow, **clin, "beds_total": total, "beds_occupied": occ,
            "occupancy_pct": round(occ / total * 100, 1) if total else None,
            "admissions_pending": int(adm["pending"] or 0), "admitted_30d": int(adm["admitted_30d"] or 0),
            "patients_registered": int(reg["total"] or 0), "patients_new_30d": int(reg["new_30d"] or 0),
            "last_native_visit": last_visit}


def _pharmacy() -> Dict[str, Any]:
    from src.services import pharmacy_inventory_service as ph
    s = ph.get_workspace_summary()
    return {"products": s["total_skus"], "tiers": s["tier_counts"], "critical": s["tier_counts"].get("CRITICAL", 0),
            "expiring_soon": s["expiring_soon_count"], "expired_products": s["expired_in_stock_count"],
            "replenishment_open": s["pending_replenishment_count"]}


def _quality() -> Dict[str, Any]:
    from src.services import quality_hub
    return quality_hub.overview()


def _people() -> Dict[str, Any]:
    from src.services import hr_hub
    return hr_hub.people_summary()


# ---------------------------------------------------------------------------

def _attention(fin, debt, bill, pat, ph, qual, ppl) -> List[Dict[str, Any]]:
    """Exceptions management should know about, most serious first; each links to where it is dealt with."""
    out: List[Dict[str, Any]] = []

    def add(level: str, title: str, detail: str, link: str) -> None:
        out.append({"level": level, "title": title, "detail": detail, "link": link})

    m = lambda v: f"₦{_f(v) / 1e6:,.1f}M" if abs(_f(v)) >= 1e6 else f"₦{_f(v):,.0f}"
    if fin:
        if not fin["live"]:
            to = fin["books_to"]
            add("critical", "Roy Books is not live yet" + (f": the books end {to:%d %b %Y}" if to else ""),
                f"{fin['missing_months']} months since then have no books. Load the later Sage years, then set the cut-over date "
                "so bills, payments and pharmacy stock start posting by themselves.", "/finance/books/setup")
        elif fin["controls"]["failed_postings"]:
            add("critical", f"{fin['controls']['failed_postings']} hospital transactions did not post to Roy Books",
                "Bills, receipts or dispensing missing from the ledger (Royan's or Scancare's). Close & controls lists them "
                "and posts them again.", "/finance/books/close")
        c = fin["controls"]
        if fin["live"] and c["bank_accounts_holding"] and c["reconciled"] < c["bank_accounts_holding"]:
            add("action", f"{c['bank_accounts_holding'] - c['reconciled']} of {c['bank_accounts_holding']} bank and cash accounts are not reconciled",
                "Reconcile each to its statement so the cash figure can be relied on.", "/finance/books/banking")
        if fin["live"] and c["past_periods_open"]:
            add("info", f"{c['past_periods_open']} months since go-live still open in the books", "Close each month once signed off.", "/finance/books/close")
        if c["drafts"]:
            add("info", f"{c['drafts']} finance documents in draft", "Drafts do not count in the figures until posted.", "/finance/books")
        if fin["payables"]["overdue"] > 0:
            add("action", f"Supplier bills past due: {m(fin['payables']['overdue'])}",
                f"{m(fin['payables']['due_30'])} more fall due in the next 30 days.", "/finance/books/purchases")
        st = fin["stock"]
        if st.get("expired_value"):
            add("critical", f"Expired drugs still on the shelf: {m(st['expired_value'])} ({st['expired_products']} products)",
                "Pharmacy QC > Expired stock lists each batch; dispose of them there (recorded for NAFDAC) so they cannot "
                "be dispensed.", "/quality-control?tab=expired")
        if st.get("shelf_uncosted_batches"):
            add("info", f"{st['shelf_uncosted_batches']} pharmacy batches have no unit cost",
                "They are left out of the stock value, and out of the books' opening stock.", "/finance/books/stock")
        if st.get("in_books") and abs(st.get("difference") or 0) >= 1:
            add("action", f"Stock in the books differs from the shelves by {m(st['difference'])}",
                "Count the difference and post an adjustment.", "/finance/books/stock?tab=status")
    if debt and debt.get("over_90_pct") and debt["over_90_pct"] >= 20:
        add("critical" if debt["over_90_pct"] >= 40 else "action",
            f"{debt['over_90_pct']}% of what HMOs and corporates owe since go-live is over 90 days",
            f"{m(debt['over_90'])} of {m(debt['total'])} at {debt['as_of']:%d %b %Y}. Chase the HMOs' monthly claims.", "/finance/ar")
    lg = (debt or {}).get("legacy") or {}
    if lg.get("total", 0) >= 1:
        rt, bt = lg.get("receipts_to"), lg.get("billed_to")
        span = (f"HMO billing in Hope (to {bt:%d %b %Y}) less the HMO payments in Sage, which are loaded only to {rt:%d %b %Y}. "
                if bt and rt else "HMO billing in Hope less the HMO payments loaded from Sage. ")
        add("action", f"Pre-go-live HMO balance to reconcile: {m(lg['total'])}",
            span + "Payments received after that are not loaded yet, so this is not money known to be overdue: load the "
                   "2025 Sage receipts (Setup > Migration) or agree each HMO's opening balance with Finance.",
            "/finance/books/setup")
    if ph:
        if ph["critical"]:
            add("action", f"{ph['critical']} drugs at critical stock", "Below their safety level for current demand.",
                "/hospital/pharmacy/inventory")
    if pat:
        if pat.get("admissions_pending"):
            add("action", f"{pat['admissions_pending']} admission requests waiting for a bed", "", "/hospital/nurse")
        if pat.get("avg_wait_minutes", 0) > 60:
            add("action", f"Average wait to triage today is {pat['avg_wait_minutes']:.0f} minutes",
                f"{pat['patients_waiting']} patients waiting now.", "/hospital/queue?status=waiting")
    if qual:
        i = qual["incidents"]
        if i["open_serious"]:
            add("critical", f"{i['open_serious']} serious incidents still open", "", "/hospital/quality")
        elif i["open"]:
            add("info", f"{i['open']} incidents open", f"{i['open_over_14d']} open for more than 14 days.", "/hospital/quality")
        if qual["audits"]["overdue"]:
            add("action", f"{qual['audits']['overdue']} facility audits overdue", "", "/hospital/audits-maintenance")
        if qual["maintenance"]["overdue"]:
            add("action", f"{qual['maintenance']['overdue']} maintenance jobs overdue", "", "/hospital/audits-maintenance")
    if ppl:
        if ppl.get("no_salary"):
            add("action", f"{ppl['no_salary']} staff have no monthly salary recorded",
                "Payroll cannot be prepared for them; HR sets it on each staff record.", "/hr?tab=directory")
        if ppl.get("pending_leave"):
            add("info", f"{ppl['pending_leave']} leave requests to decide", "", "/hr?tab=leave")
        if ppl.get("pending_timesheets"):
            add("info", f"{ppl['pending_timesheets']} timesheet entries awaiting approval", "", "/hr?tab=timesheets")
        if ppl.get("escalated_to_management"):
            add("action", f"{ppl['escalated_to_management']} overdue tasks escalated to management", "", "/workspace?tab=team")
        elif ppl.get("overdue_tasks"):
            add("info", f"{ppl['overdue_tasks']} team tasks overdue", f"{ppl['open_tasks']} open across the team.", "/workspace?tab=team")
    rank = {"critical": 0, "action": 1, "info": 2}
    return sorted(out, key=lambda a: rank[a["level"]])


def overview(refresh: bool = False) -> Dict[str, Any]:
    hit = _CACHE.get("ov")
    if hit and not refresh and time.monotonic() - hit[0] < TTL:
        return hit[1]
    t0 = time.monotonic()
    fin = _safe("finance", _finance)
    debt = _safe("debtors", _debtors)
    bill = _safe("billing", _billing)
    pat = _safe("patients", _patients)
    ph = _safe("pharmacy", _pharmacy)
    qual = _safe("quality", _quality)
    ppl = _safe("people", _people)
    out = {
        "generated_at": dt.datetime.now(dt.timezone.utc), "build_seconds": None,
        "finance": fin, "debtors": debt, "billing": bill, "patients": pat, "pharmacy": ph, "quality": qual, "people": ppl,
        "unavailable": [k for k, v in (("finance", fin), ("debtors", debt), ("billing", bill), ("patients", pat),
                                       ("pharmacy", ph), ("quality", qual), ("people", ppl)) if v is None],
        "attention": _attention(fin, debt, bill, pat, ph, qual, ppl),
    }
    out["build_seconds"] = round(time.monotonic() - t0, 2)
    _CACHE["ov"] = (time.monotonic(), out)
    return out
