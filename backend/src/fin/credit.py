"""Royan's finance read model for Credit Control, the executive dashboard and the KPI services.

Those screens were built on Sage snapshot tables (royan_gl_snapshot, an AR batch ...)
that this hospital never had, so they showed nothing - or Hope's ten years of closed
bills as "overdue". They now read what Roy Books knows:

  * Debtors  - what HMOs and corporate payers owe: their Hope lines less every receipt
               on their Sage accounts (payers.hmo_ageing). Once the books are live,
               HMO debt up to the day before go-live comes from there and everything
               after from the books' own open items (readmodel), so nothing is counted
               twice. Private patients pay at the till; Hope's line-level "unpaid"
               flags for them are unreliable (pharmacy sales are settled on the final
               bill), so they are not chased here.
  * P&L      - the ledger (Sage history 2010-2024 + the books): fin_v_ledger.
  * Revenue  - Hope's billed lines for the period the books do not cover yet.
  * Cash     - the ledger's cash and bank accounts.

"As of" is today once the books are live; before that it is the last day Hope data
reaches (the hospital's records stop with the January 2026 extract), and every result
says so.
"""
from __future__ import annotations

import datetime as dt
from collections import defaultdict
from decimal import Decimal
from typing import Any, Dict, List, Optional

from src.fin import payers, readmodel
from src.fin.context import resolve_entity
from src.fin.db import ZERO, money, q, q1, tx

BUCKETS = ("0_30", "31_60", "61_90", "91_plus")


def _f(v: Any) -> float:
    return float(money(v))


def _state(conn) -> Dict[str, Any]:
    e = resolve_entity(conn, None)
    s = q1(conn, "SELECT cutover_date FROM fin_settings WHERE legal_entity_id=%s", (e,)) or {}
    hope_to = q1(conn, "SELECT MAX(charge_date) d FROM fin_hope_charges")["d"]
    live = readmodel.live()
    on = dt.date.today() if live else (hope_to or dt.date.today())
    return {"entity": e, "live": live, "cutover": s.get("cutover_date"), "hope_to": hope_to, "as_of": on,
            "source": "Roy Books (books) + Hope HMO billing before go-live" if live else
                      f"Hope billing to {hope_to:%d %b %Y} less receipts in Sage" if hope_to else "Roy Books"}


def _bucket(days: int) -> str:
    return "0_30" if days <= 30 else "31_60" if days <= 60 else "61_90" if days <= 90 else "91_plus"


def debtors(conn) -> Dict[str, Any]:
    """Every debtor with an open balance, aged into the four Credit Control buckets."""
    st = _state(conn)
    e, on = st["entity"], st["as_of"]
    hope_on = min(on, st["cutover"] - dt.timedelta(days=1)) if st["live"] and st["cutover"] else on
    rows: List[Dict[str, Any]] = []
    for r in payers.hmo_ageing(conn, e, hope_on):
        if r["owed"] <= 0:
            continue
        b = r["buckets"]   # 0-30, 31-60, 61-90, 91-180, 181-365, 1y+
        bk = {"0_30": b[0], "31_60": b[1], "61_90": b[2], "91_plus": b[3] + b[4] + b[5]}
        days = (on - r["oldest_open"]).days if r["oldest_open"] else 0
        rows.append({"customer_id": (r["sage_code"] or f"HOPE-{r['payer_id']}").split(",")[0], "ace_customer_id": r["customer_id"],
                     "payer_id": r["payer_id"], "name": r["hmo"], "payer_type": r["payer_type"], "email": None, "phone": None,
                     "total_balance": r["owed"], "buckets": bk, "max_days_overdue": max(days, 0),
                     "earliest_due_date": r["oldest_open"], "open_months": sum(1 for x in b if x > 0),
                     "received_beyond_billed": r["unapplied"], "source": "Hope billing less Sage receipts"})
    if st["live"]:
        per: Dict[Any, Dict[str, Any]] = {}
        for it in readmodel.ar_rows(on):
            d = per.setdefault(it["ace_customer_id"], {
                "customer_id": it["customer_id"], "ace_customer_id": it["ace_customer_id"], "payer_id": None, "name": it["name"],
                "payer_type": it.get("party_type"), "email": it["email"], "phone": it["phone"], "total_balance": ZERO,
                "buckets": {k: ZERO for k in BUCKETS}, "max_days_overdue": 0, "earliest_due_date": None, "open_months": 0,
                "received_beyond_billed": ZERO, "source": "Roy Books open items"})
            amt = money(it["balance"])
            d["total_balance"] += amt
            d["buckets"][it["bucket"]] += amt
            d["max_days_overdue"] = max(d["max_days_overdue"], it["days_overdue"])
            d["open_months"] += 1
            if not d["earliest_due_date"] or it["due_date"] < d["earliest_due_date"]:
                d["earliest_due_date"] = it["due_date"]
        rows += [d for d in per.values() if abs(d["total_balance"]) >= Decimal("0.01")]
    rows.sort(key=lambda r: str(r["name"] or "").lower())   # A-Z, as the client asked
    return {**st, "rows": rows}


_CACHE: Dict[str, Any] = {}


def _debtors_cached(ttl: int = 120) -> Dict[str, Any]:
    """Credit Control asks for the same debtor list several times per screen; compute it once a couple of minutes."""
    import time
    hit = _CACHE.get("debtors")
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    with tx() as conn:
        d = debtors(conn)
    _CACHE["debtors"] = (time.time(), d)
    return d


def aging_buckets() -> Dict[str, Any]:
    d = _debtors_cached()
    tot = {k: sum((r["buckets"][k] for r in d["rows"]), ZERO) for k in BUCKETS}
    out = {k: _f(v) for k, v in tot.items()}
    out.update({"1_30": out["0_30"], "current": out["0_30"], "over_90": out["91_plus"],
                "as_of": d["as_of"].isoformat(), "source": d["source"]})
    return out


def aging_customers(bucket: Optional[str]) -> List[Dict[str, Any]]:
    raw = (bucket or "").strip().lower().replace("_", "-")
    key = ("0_30" if raw.startswith("0-30") else "31_60" if raw.startswith("31-60") else
           "61_90" if raw.startswith("61-90") else "91_plus" if raw.startswith(("90+", "91+", "over")) else None)
    d = _debtors_cached()
    out = []
    for r in d["rows"]:
        amt = r["buckets"][key] if key else r["total_balance"]
        if amt <= 0:
            continue
        out.append({"customer_id": r["customer_id"], "ace_customer_id": r["ace_customer_id"], "payer_id": r["payer_id"],
                    "name": r["name"], "email": r["email"], "phone": r["phone"], "total_balance": _f(amt),
                    "total_amount": _f(r["total_balance"]), "invoices_count": r["open_months"],
                    "max_days_overdue": r["max_days_overdue"], "earliest_due_date": r["earliest_due_date"],
                    "bucket": key or _bucket(r["max_days_overdue"]), "source": r["source"]})
    return out


def _revenue_window(conn, e, end: dt.date, months: int = 12) -> Dict[str, Any]:
    start = (end.replace(day=1) - dt.timedelta(days=1)).replace(day=1)
    for _ in range(months - 2):
        start = (start - dt.timedelta(days=1)).replace(day=1)
    hope = q1(conn, """SELECT COALESCE(SUM(gross - discount),0) v FROM fin_v_hope_charges
                       WHERE payer_type <> 'INTERNAL' AND charge_date BETWEEN %s AND %s""", (start, end))["v"]
    return {"from": start, "to": end, "billed": money(hope)}


def kpis() -> Dict[str, Any]:
    """The finance KPI block every dashboard and service reads (same keys as before)."""
    with tx() as conn:
        d = debtors(conn)
        e, on = d["entity"], d["as_of"]
        rev = _revenue_window(conn, e, on)
        cash = q1(conn, """SELECT COALESCE(SUM(debit-credit),0) v FROM fin_v_ledger WHERE legal_entity_id=%s
                           AND subtype='CASH' AND journal_date <= %s""", (e, on))["v"]
        ledger_to = q1(conn, "SELECT MAX(journal_date) d FROM fin_v_ledger WHERE legal_entity_id=%s", (e,))["d"]
        fy = ledger_to.replace(month=1, day=1) if ledger_to else on.replace(month=1, day=1)
        pl = q1(conn, """SELECT COALESCE(SUM(credit-debit) FILTER (WHERE subtype='SALES'),0) rev,
                                COALESCE(SUM(debit-credit) FILTER (WHERE subtype='COST_OF_SALES'),0) cogs
                         FROM fin_v_ledger WHERE legal_entity_id=%s AND journal_date BETWEEN %s AND %s
                           AND journal_type NOT IN ('OPENING','CLOSING')""", (e, fy, ledger_to or on))
        ap = readmodel.ap_rows(on) if d["live"] else []
    ar_total = sum((r["total_balance"] for r in d["rows"]), ZERO)
    overdue = sum((r["buckets"]["31_60"] + r["buckets"]["61_90"] + r["buckets"]["91_plus"] for r in d["rows"]), ZERO)
    n_over = sum(1 for r in d["rows"] if r["max_days_overdue"] > 30)
    ledger_rev, cogs = money(pl["rev"]), money(pl["cogs"])
    return {
        "total_revenue": _f(rev["billed"]),
        "revenue_window": {"from": rev["from"].isoformat(), "to": rev["to"].isoformat(), "basis": "Hope billed lines"},
        "ar_total": _f(ar_total), "ar_overdue": _f(overdue),
        "ar": {"total_balance": _f(ar_total), "total_amount": _f(ar_total), "count": len(d["rows"]),
               "overdue_amount": _f(overdue), "overdue_count": n_over},
        "ap": {"total_balance": float(sum(a["balance"] for a in ap)), "total_amount": float(sum(a["balance"] for a in ap)),
               "overdue_count": sum(1 for a in ap if a["due_date"] < on)},
        "total_cogs": _f(cogs), "gross_margin_pct": round(float((ledger_rev - cogs) / ledger_rev * 100), 1) if ledger_rev else 0.0,
        "ledger_year": {"from": fy.isoformat(), "to": (ledger_to or on).isoformat(), "revenue": _f(ledger_rev)},
        "ap_total": float(sum(a["balance"] for a in ap)), "inventory_value": 0.0,
        "cash_position": _f(cash), "cash": _f(cash), "cash_as_of": (ledger_to or on).isoformat(),
        "as_of": on.isoformat(), "source": d["source"], "books_live": d["live"],
    }


def trend(periods: int = 6) -> Dict[str, Any]:
    """Per month: billed (Hope / books) and what HMOs & corporates owed at month end."""
    with tx() as conn:
        st = _state(conn)
        e, on = st["entity"], st["as_of"]
        ends: List[dt.date] = []
        m = on
        for _ in range(max(1, periods)):
            ends.append(m)
            m = m.replace(day=1) - dt.timedelta(days=1)
        ends.reverse()
        billed = {r["m"]: money(r["v"]) for r in q(conn, """SELECT to_char(charge_date,'YYYY-MM') m, SUM(gross-discount) v
                     FROM fin_v_hope_charges WHERE payer_type <> 'INTERNAL' AND charge_date BETWEEN %s AND %s GROUP BY 1""",
                                                      (ends[0].replace(day=1), on))}
        out = []
        for end in ends:
            owed = sum((r["owed"] for r in payers.hmo_ageing(conn, e, end)), ZERO)
            k = f"{end:%Y-%m}"
            out.append({"period": k, "amount": _f(billed.get(k, ZERO)), "billed": _f(billed.get(k, ZERO)),
                        "balance": _f(owed), "outstanding": _f(owed)})
    return {"periods": out, "as_of": on.isoformat(), "source": st["source"]}


def profit_and_loss(period: Optional[str] = None) -> Dict[str, Any]:
    """Revenue and expenses by month from the ledger (Sage history + the books). Default: the last 12 months it has."""
    with tx() as conn:
        e = resolve_entity(conn, None)
        if period:
            cond, args = "to_char(journal_date, 'YYYY-MM') LIKE %s", (f"{period}%",)
        else:
            last = q1(conn, "SELECT MAX(journal_date) d FROM fin_v_ledger WHERE legal_entity_id=%s", (e,))["d"] or dt.date.today()
            start = (last.replace(day=1) - dt.timedelta(days=330)).replace(day=1)
            cond, args = "journal_date BETWEEN %s AND %s", (start, last)
        rows = q(conn, f"""SELECT to_char(journal_date, 'YYYY-MM') AS period,
                                  SUM(CASE WHEN account_type='REVENUE' THEN credit-debit ELSE 0 END) AS revenue,
                                  SUM(CASE WHEN account_type='EXPENSE' THEN debit-credit ELSE 0 END) AS expenses
                           FROM fin_v_ledger WHERE legal_entity_id=%s AND journal_type NOT IN ('OPENING','CLOSING')
                             AND account_type IN ('REVENUE','EXPENSE') AND {cond}
                           GROUP BY 1 ORDER BY 1""", (e, *args))
    series = []
    for r in rows:
        rev, exp = _f(r["revenue"]), _f(r["expenses"])
        series.append({"period": r["period"], "revenue": rev, "expenses": exp, "gross_profit": round(rev - exp, 2),
                       "margin_pct": round((rev - exp) / rev * 100, 2) if rev else 0.0})
    tr, te = sum(s["revenue"] for s in series), sum(s["expenses"] for s in series)
    return {"period_filter": period or "last 12 months in the ledger", "series": series,
            "totals": {"revenue": round(tr, 2), "expenses": round(te, 2), "net_profit": round(tr - te, 2),
                       "net_margin_pct": round((tr - te) / tr * 100, 2) if tr else 0.0},
            "source": "Roy Books ledger (Sage history 2010-2024 and the books)",
            "generated_at": dt.datetime.utcnow().isoformat()}


def cash_forecast(weeks: int = 12) -> Dict[str, Any]:
    """Run-rate forecast: cash in the ledger, weekly takings and weekly spending at the last 13 weeks' pace, plus
    HMO debt under 90 days expected in the first eight weeks."""
    with tx() as conn:
        d = debtors(conn)
        e, on = d["entity"], d["as_of"]
        last = q1(conn, "SELECT MAX(journal_date) d FROM fin_v_ledger WHERE legal_entity_id=%s", (e,))["d"] or on
        cash = money(q1(conn, """SELECT COALESCE(SUM(debit-credit),0) v FROM fin_v_ledger WHERE legal_entity_id=%s
                                 AND subtype='CASH'""", (e,))["v"])
        takings = money(q1(conn, """SELECT COALESCE(SUM(amount),0) v FROM royan_payments WHERE amount <= 50000000
                                    AND received_at::date BETWEEN %s AND %s""", (on - dt.timedelta(days=91), on))["v"]) / 13
        spend = money(q1(conn, """SELECT COALESCE(SUM(debit-credit),0) v FROM fin_v_ledger WHERE legal_entity_id=%s
                                  AND account_type='EXPENSE' AND account_name NOT ILIKE '%%depreciation%%'
                                  AND journal_type NOT IN ('OPENING','CLOSING') AND journal_date BETWEEN %s AND %s""",
                         (e, last - dt.timedelta(days=364), last))["v"]) / 52
    hmo_soon = sum((r["buckets"]["0_30"] + r["buckets"]["31_60"] + r["buckets"]["61_90"] for r in d["rows"]), ZERO)
    start = dt.date.today()
    rows, running = [], cash
    for w in range(weeks):
        inflow = takings + (hmo_soon / 8 if w < 8 else ZERO)
        running += inflow - spend
        rows.append({"week": w + 1, "start": (start + dt.timedelta(days=7 * w)).isoformat(),
                     "end": (start + dt.timedelta(days=7 * w + 6)).isoformat(), "inflow": _f(inflow), "outflow": _f(spend),
                     "net": _f(inflow - spend), "running_balance": _f(running)})
    ti, to = sum(r["inflow"] for r in rows), sum(r["outflow"] for r in rows)
    return {"weeks": weeks, "opening_balance": _f(cash), "forecast": rows,
            "totals": {"total_inflow": round(ti, 2), "total_outflow": round(to, 2), "net_position": round(ti - to, 2),
                       "closing_balance": round(_f(cash) + ti - to, 2)},
            "as_of": start.isoformat(),
            "note": (f"Opening = cash and bank in the ledger at {last:%d %b %Y}. Inflows = average weekly takings at the tills "
                     f"in the 13 weeks to {on:%d %b %Y} plus HMO debt under 90 days spread over 8 weeks; outflows = average "
                     f"weekly spending (excluding depreciation) in the ledger's last 52 weeks, to {last:%d %b %Y}. A run-rate "
                     f"guide, not a schedule of known payments; it sharpens once the 2025 Sage exports are loaded.")}


def credit_risk() -> Dict[str, Any]:
    from src.routers.finance import _score_customer   # the scoring rules Credit Control already shows
    with tx() as conn:
        d = debtors(conn)
        alerts = defaultdict(int)
        for r in q(conn, "SELECT customer_id FROM fin_ar_alert_events WHERE NOT acknowledged"):
            alerts[str(r["customer_id"])] += 1
    total = float(sum((r["total_balance"] for r in d["rows"]), ZERO))
    scored, tiers = [], {"Critical": 0, "High": 0, "Medium": 0, "Low": 0}
    for r in d["rows"]:
        s = _score_customer(balance=_f(r["total_balance"]), days_overdue=r["max_days_overdue"],
                            alert_events=alerts.get(str(r["customer_id"]), 0), total_ar=total)
        tiers[s["tier"]] = tiers.get(s["tier"], 0) + 1
        scored.append({"customer_id": r["customer_id"], "name": r["name"], "outstanding_balance": _f(r["total_balance"]),
                       "max_days_overdue": r["max_days_overdue"], "alert_events": alerts.get(str(r["customer_id"]), 0),
                       "risk_score": s["score"], "risk_tier": s["tier"]})
    scored.sort(key=lambda x: -x["risk_score"])
    return {"customers": scored, "total_customers": len(scored), "total_ar_outstanding": round(total, 2),
            "tier_distribution": tiers, "scoring_date": d["as_of"].isoformat(), "source": d["source"]}


def invoice_match(period: Optional[str] = None) -> Dict[str, Any]:
    """Each invoice against the money applied to it: Sage's invoice register with the receipts that settled each one
    (fin_sage_receipt_invoices) and Roy Books' own invoices. Default: the last year that has invoices."""
    with tx() as conn:
        e = resolve_entity(conn, None)
        if not period:
            period = str(q1(conn, """SELECT MAX(d) d FROM (SELECT MAX(invoice_date) d FROM fin_sage_invoices WHERE legal_entity_id=%s
                                     UNION ALL SELECT MAX(invoice_date) FROM fin_sales_invoices WHERE legal_entity_id=%s) x""",
                                (e, e))["d"] or dt.date.today())[:4]
        sage = q(conn, """SELECT i.id, i.invoice_number AS number, i.customer_name AS customer, i.invoice_date AS date,
                                 i.amount, i.amount_received AS applied
                          FROM fin_sage_invoices i WHERE i.legal_entity_id=%s AND to_char(i.invoice_date,'YYYY-MM') LIKE %s
                          ORDER BY i.invoice_date LIMIT 5000""", (e, f"{period}%"))
        roy = q(conn, """SELECT s.id, s.invoice_number AS number, c.name AS customer, s.invoice_date AS date, s.total AS amount,
                                s.amount_settled AS applied
                         FROM fin_sales_invoices s JOIN fin_v_customers c ON c.id=s.customer_id
                         WHERE s.legal_entity_id=%s AND s.status NOT IN ('VOID','DRAFT') AND to_char(s.invoice_date,'YYYY-MM') LIKE %s
                         ORDER BY s.invoice_date LIMIT 5000""", (e, f"{period}%"))
    matched, unmatched, discrepancies = [], [], []
    for src, items in (("Sage", sage), ("Roy Books", roy)):
        for r in items:
            amount, applied = money(r["amount"]), money(r["applied"])
            rec = {"invoice_id": r["number"] or f"#{r['id']}", "record_id": str(r["id"]), "source": src, "customer_id": r["customer"],
                   "invoice_amount": _f(amount), "outstanding_balance": _f(amount - applied), "gl_payment_found": _f(applied),
                   "due_date": r["date"], "status": "paid" if applied >= amount else "partial" if applied > 0 else "open"}
            if applied == amount:
                matched.append(rec)
            elif applied == 0:
                unmatched.append(rec)
            else:
                discrepancies.append({**rec, "issue": "over_applied" if applied > amount else "part_paid",
                                      "difference": _f(amount - applied)})
    return {"period": period, "total_invoices": len(sage) + len(roy), "matched": matched, "unmatched": unmatched,
            "discrepancies": discrepancies,
            "summary": {"matched_count": len(matched), "unmatched_count": len(unmatched), "discrepancy_count": len(discrepancies)},
            "note": "Sage invoices are matched to the cash receipts that name them; Royan's Sage recorded most invoice and "
                    "receipt together, so an 'open' Sage invoice usually means its receipt named a different invoice number."}
