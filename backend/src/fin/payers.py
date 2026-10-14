"""Who paid: HMOs, private patients, staff schemes and corporates - Hope and Sage together.

Royan asked Finance to be able to "separate the HMO services so that we know what
services went to HMO and at what cost, what services went to private and at what
cost", to send each HMO its monthly bill, and to age what HMOs owe (the claims
ageing report). Neither system answers that alone:

  * Hope priced every charge line against the patient's payer (fin_hope_charges),
    so it knows the split, line by line, to January 2026.
  * Sage holds what was invoiced to and received from each HMO (fin_sage_invoices,
    fin_sage_receipts) and the revenue the books recognised, to December 2024.

The reports here put the two side by side. Hope figures are "billed" = gross less
discount at the till; Sage figures are the books. Where they differ the report
shows the difference instead of choosing one. Every row drills: a payer opens its
patients and lines, a line opens the Hope visit, an HMO opens its Roy Books account
(with its Sage invoices and receipts).
"""
from __future__ import annotations

import datetime as dt
from collections import defaultdict
from decimal import Decimal
from typing import Any, Dict, List, Optional

from src.fin.db import ZERO, money, q, q1
from src.fin.errors import not_found
from src.fin.report_center import C, _tot, report

TYPES = ("PRIVATE", "HMO", "STAFF", "CORPORATE", "INTERNAL")
TYPE_LABEL = {"PRIVATE": "Private patients", "HMO": "HMOs", "STAFF": "Staff schemes", "CORPORATE": "Corporate / retainership",
              "INTERNAL": "Paid by Royan (Scancare referrals)"}
BILLED = "(c.gross - c.discount)"


def _split_cols() -> List[Dict[str, Any]]:
    return [C(t.lower(), TYPE_LABEL[t], "money") for t in TYPES] + [C("total", "Total billed", "money"),
                                                                     C("hmo_share", "HMO & corporate share %", "qty")]


def _split_sql() -> str:
    return ", ".join(f"SUM({BILLED}) FILTER (WHERE c.payer_type='{t}') AS {t.lower()}" for t in TYPES) + f", SUM({BILLED}) AS total"


def _share(rows: List[Dict[str, Any]]) -> None:
    for r in rows:
        t = money(r.get("total"))
        r["hmo_share"] = round(float((money(r.get("hmo")) + money(r.get("corporate"))) / t * 100), 1) if t else None


def _hope_range() -> str:
    return "Hope charge lines (services, pharmacy, lab, radiology, ward) - billed = gross less discount"


# ---------------------------------------------------------------------------
# The split
# ---------------------------------------------------------------------------

@report("payer-mix")
def payer_mix(conn, e, p):
    """HMO vs private by month; a month opens its departments."""
    if p.get("month"):
        rows = q(conn, f"""SELECT COALESCE(NULLIF(upper(c.category), ''), c.source) AS department, COUNT(DISTINCT c.visit_id) AS visits,
                              {_split_sql()} FROM fin_v_hope_charges c
                          WHERE to_char(c.charge_date, 'YYYY-MM')=%s GROUP BY 1 ORDER BY total DESC""", (p["month"],))
        _share(rows)
        return {"title": f"HMO vs Private - {p['month']} by department", "subtitle": _hope_range(),
                "columns": [C("department", "Department / service"), C("visits", "Visits", "qty")] + _split_cols(),
                "rows": rows, "totals": _tot(rows, *[t.lower() for t in TYPES], "total")}
    rows = q(conn, f"""SELECT to_char(c.charge_date, 'YYYY-MM') AS month, COUNT(DISTINCT c.visit_id) AS visits,
                              COUNT(DISTINCT c.patient_id) FILTER (WHERE c.payer_type='HMO') AS hmo_patients,
                              COUNT(DISTINCT c.patient_id) FILTER (WHERE c.payer_type='PRIVATE') AS private_patients,
                              {_split_sql()} FROM fin_v_hope_charges c
                       WHERE c.charge_date BETWEEN %s AND %s GROUP BY 1 ORDER BY 1""", (p["from"], p["to"]))
    _share(rows)
    return {"title": "HMO vs Private by Month", "subtitle": f"{p['from']} to {p['to']} · {_hope_range()}. Click a month for its departments.",
            "columns": [C("month", "Month", link="drill:month"), C("visits", "Visits", "qty"),
                        C("private_patients", "Private patients", "qty"), C("hmo_patients", "HMO patients", "qty")] + _split_cols(),
            "rows": rows, "totals": _tot(rows, *[t.lower() for t in TYPES], "total")}


@report("services-by-payer")
def services_by_payer(conn, e, p):
    """What services went to HMOs and at what cost, and what went to private patients - per department / service."""
    by = "c.service" if p.get("name") else "COALESCE(NULLIF(upper(c.category), ''), c.source)"
    where = "AND COALESCE(NULLIF(upper(c.category), ''), c.source)=%s" if p.get("name") else ""
    args = (p["from"], p["to"]) + ((p["name"],) if p.get("name") else ())
    rows = q(conn, f"""SELECT {by} AS line, COUNT(*) AS lines, SUM(c.quantity) AS quantity, {_split_sql()}
                       FROM fin_v_hope_charges c WHERE c.charge_date BETWEEN %s AND %s {where}
                       GROUP BY 1 ORDER BY total DESC NULLS LAST LIMIT 1000""", args)
    _share(rows)
    title = f"Services by Payer - {p['name']}" if p.get("name") else "Services by Payer (HMO vs private, by department)"
    return {"title": title, "subtitle": f"{p['from']} to {p['to']} · {_hope_range()}",
            "columns": [C("line", "Service" if p.get("name") else "Department", link=None if p.get("name") else "drill:name"),
                        C("lines", "Lines", "qty"), C("quantity", "Quantity", "qty")] + _split_cols(),
            "rows": rows, "totals": _tot(rows, *[t.lower() for t in TYPES], "total")}


# ---------------------------------------------------------------------------
# The HMO's monthly bill
# ---------------------------------------------------------------------------

@report("hmo-monthly-bill")
def hmo_monthly_bill(conn, e, p):
    """Every HMO / corporate payer for the period; a payer opens its bill - patients, visits and every line."""
    if p.get("payer"):
        payer = q1(conn, "SELECT * FROM fin_hope_payers WHERE tariff_id=%s", (p["payer"],))
        if not payer:
            raise not_found("Payer", p["payer"])
        rows = q(conn, f"""SELECT c.charge_date AS date, c.visit_id, c.mrn, c.patient_id,
                                  NULLIF(trim(concat_ws(' ', pt.first_name, pt.last_name)), '') AS patient,
                                  ins.membership_id AS member_no, c.source, c.service, c.quantity, c.gross, c.discount,
                                  {BILLED} AS billed, c.paid AS paid_at_till, c.outstanding AS due_from_payer, c.reference
                           FROM fin_v_hope_charges c
                           LEFT JOIN royan_patients pt ON pt.id=c.patient_id
                           LEFT JOIN LATERAL (SELECT membership_id FROM royan_patient_insurance i WHERE i.patient_id=c.patient_id
                                              AND i.hmo_id=%s ORDER BY i.is_primary DESC NULLS LAST LIMIT 1) ins ON TRUE
                           WHERE c.payer_tariff_id=%s AND c.charge_date BETWEEN %s AND %s
                           ORDER BY patient NULLS LAST, c.charge_date, c.visit_id, c.source""",
                 (payer["hmo_id"], p["payer"], p["from"], p["to"]))
        pats = len({r["patient_id"] or r["mrn"] for r in rows})
        return {"title": f"{payer['name']} - bill {p['from']} to {p['to']}",
                "subtitle": f"{pats} patients · {len({r['visit_id'] for r in rows})} visits · {TYPE_LABEL[payer['payer_type']]}"
                            + (f" · Sage account {payer['sage_code']}" if payer.get("sage_code") else ""),
                "columns": [C("date", "Date", "date"), C("patient", "Patient"), C("mrn", "MRN"), C("member_no", "Member no."),
                            C("visit_id", "Visit", link="visit"), C("source", "Dept"), C("service", "Service"),
                            C("quantity", "Qty", "qty"), C("gross", "Gross", "money"), C("discount", "Discount", "money"),
                            C("billed", "Billed", "money"), C("paid_at_till", "Paid at till", "money"),
                            C("due_from_payer", "Due from payer", "money")],
                "rows": rows, "totals": _tot(rows, "gross", "discount", "billed", "paid_at_till", "due_from_payer")}
    kinds = ("HMO", "CORPORATE", "STAFF") if p.get("payer_type") in (None, "", "ALL") else (p["payer_type"],)
    rows = q(conn, f"""SELECT c.payer_tariff_id AS payer_id, c.payer, c.payer_type, c.customer_id, py.sage_code,
                              COUNT(DISTINCT COALESCE(c.patient_id::text, c.mrn)) AS patients, COUNT(DISTINCT c.visit_id) AS visits,
                              COUNT(*) AS lines, SUM({BILLED}) AS billed, SUM(c.paid) AS paid_at_till, SUM(c.outstanding) AS due_from_payer
                       FROM fin_v_hope_charges c LEFT JOIN fin_hope_payers py ON py.tariff_id=c.payer_tariff_id
                       WHERE c.payer_type = ANY(%s) AND c.charge_date BETWEEN %s AND %s
                       GROUP BY 1,2,3,4,5 ORDER BY billed DESC""", (list(kinds), p["from"], p["to"]))
    for r in rows:
        r["type"] = TYPE_LABEL[r["payer_type"]]
    return {"title": "HMO Monthly Bills", "subtitle": f"{p['from']} to {p['to']} · click a payer for its bill (patients and every line)",
            "columns": [C("payer", "Payer", link="drill:payer", id_field="payer_id"), C("type", "Type"),
                        C("sage_code", "Roy Books account", link="customer", id_field="customer_id"),
                        C("patients", "Patients", "qty"), C("visits", "Visits", "qty"), C("lines", "Lines", "qty"),
                        C("billed", "Billed", "money"), C("paid_at_till", "Paid at till (co-pay)", "money"),
                        C("due_from_payer", "Due from payer", "money")],
            "rows": rows, "totals": _tot(rows, "billed", "paid_at_till", "due_from_payer")}


# ---------------------------------------------------------------------------
# Hope against Sage
# ---------------------------------------------------------------------------

def _payer_received(conn, e, upto: dt.date) -> Dict[int, Decimal]:
    """Per Hope payer: everything received on any of its Sage accounts (and in Roy Books) up to a date."""
    out: Dict[int, Decimal] = defaultdict(lambda: ZERO)
    for r in q(conn, """SELECT a.tariff_id, SUM(x.amount) v FROM fin_hope_payer_accounts a JOIN (
                            SELECT customer_id, amount FROM fin_sage_receipts WHERE legal_entity_id=%s AND receipt_date <= %s
                              AND receipt_date >= (SELECT MIN(charge_date) FROM fin_hope_charges)   -- before Hope: pre-Hope bills
                            UNION ALL SELECT customer_id, amount + wht_amount FROM fin_customer_receipts
                            WHERE legal_entity_id=%s AND status='POSTED' AND receipt_date <= %s) x ON x.customer_id=a.customer_id
                        GROUP BY 1""", (e, upto, e, upto)):
        out[r["tariff_id"]] += money(r["v"])
    return out


@report("hmo-billing-reconciliation")
def hmo_billing_reconciliation(conn, e, p):
    """Per HMO and year: what Hope billed the HMO, what Sage invoiced it, what Sage received - and the gaps."""
    rows = q(conn, """WITH h AS (SELECT c.payer_tariff_id AS t, extract(year FROM c.charge_date)::int AS year, SUM(c.outstanding) AS hope_billed
                                 FROM fin_v_hope_charges c WHERE c.payer_type IN ('HMO','CORPORATE')
                                   AND c.charge_date BETWEEN %s AND %s GROUP BY 1,2),
                           i AS (SELECT a.tariff_id AS t, extract(year FROM s.invoice_date)::int AS year, SUM(s.amount) AS sage_invoiced
                                 FROM fin_sage_invoices s JOIN fin_hope_payer_accounts a ON a.customer_id=s.customer_id
                                 WHERE s.legal_entity_id=%s AND s.invoice_date BETWEEN %s AND %s GROUP BY 1,2),
                           r AS (SELECT a.tariff_id AS t, extract(year FROM s.receipt_date)::int AS year, SUM(s.amount) AS sage_received
                                 FROM fin_sage_receipts s JOIN fin_hope_payer_accounts a ON a.customer_id=s.customer_id
                                 WHERE s.legal_entity_id=%s AND s.receipt_date BETWEEN %s AND %s GROUP BY 1,2)
                      SELECT py.tariff_id AS payer_id, py.name AS hmo, py.customer_id, py.sage_code,
                             COALESCE(h.year, i.year, r.year) AS year, h.hope_billed, i.sage_invoiced, r.sage_received,
                             COALESCE(h.hope_billed,0) - COALESCE(i.sage_invoiced,0) AS billed_not_invoiced,
                             COALESCE(i.sage_invoiced,0) - COALESCE(r.sage_received,0) AS invoiced_not_received
                      FROM h FULL JOIN i ON i.t=h.t AND i.year=h.year
                      FULL JOIN r ON r.t=COALESCE(h.t, i.t) AND r.year=COALESCE(h.year, i.year)
                      JOIN fin_hope_payers py ON py.tariff_id=COALESCE(h.t, i.t, r.t)
                      ORDER BY py.name, year""", (p["from"], p["to"], e, p["from"], p["to"], e, p["from"], p["to"]))
    return {"title": "HMO Billing: Hope vs Sage", "subtitle":
            f"{p['from']} to {p['to']} · Hope = what each HMO was left to pay on its members' lines; Sage = invoices to and "
            "receipts from all of that HMO's Sage accounts (Sage runs to 31 Dec 2024). 'Billed, not invoiced' is care given "
            "to the HMO's members that never reached a Sage invoice. Payers without a Sage account show Hope only.",
            "columns": [C("hmo", "HMO / payer", link="drill:payer", id_field="payer_id"),
                        C("sage_code", "Sage account(s)", link="customer", id_field="customer_id"), C("year", "Year"),
                        C("hope_billed", "Hope: billed to HMO", "money"), C("sage_invoiced", "Sage: invoiced", "money"),
                        C("sage_received", "Sage: received", "money"), C("billed_not_invoiced", "Billed, not invoiced", "money"),
                        C("invoiced_not_received", "Invoiced, not received", "money")],
            "rows": rows, "totals": _tot(rows, "hope_billed", "sage_invoiced", "sage_received", "billed_not_invoiced",
                                         "invoiced_not_received")}


AGE = ((30, "0-30 days"), (60, "31-60"), (90, "61-90"), (180, "91-180"), (365, "181-365"), (10 ** 6, "Over 1 year"))


@report("hmo-claims-ageing")
def hmo_claims_ageing(conn, e, p):
    """What each HMO still owes, aged: Hope's monthly bills to the HMO less everything received from it (all its Sage
    accounts and Roy Books), oldest month first. Hope keeps no payment against an HMO line, so this is the hospital's
    position per HMO, not a line-by-line remittance match."""
    as_of = p["as_of"]
    rows = []
    for r in hmo_ageing(conn, e, as_of):
        row = {k: r[k] for k in ("payer_id", "hmo", "customer_id", "sage_code", "billed", "received", "unapplied", "owed")}
        for i, b in enumerate(r["buckets"]):
            row[f"b{i}"] = b
        rows.append(row)
    last_receipt = q1(conn, "SELECT MAX(receipt_date) d FROM fin_sage_receipts WHERE legal_entity_id=%s", (e,))["d"]
    return {"title": "HMO Claims Ageing", "subtitle":
            f"As of {as_of} · billed (Hope, since May 2016) less received (Sage to {last_receipt or '-'} and Roy Books), applied "
            "to the oldest month first. Payments made after Sage's last export are not in yet - upload the 2025/2026 Sage "
            "exports to bring this up to date. HMOs with no Sage account show everything billed as owed.",
            "columns": [C("hmo", "HMO / payer", link="drill:payer", id_field="payer_id"),
                        C("sage_code", "Sage account(s)", link="customer", id_field="customer_id"),
                        C("billed", "Billed (Hope)", "money"), C("received", "Received", "money")]
                       + [C(f"b{i}", label, "money") for i, (_, label) in enumerate(AGE)]
                       + [C("unapplied", "Received beyond billed (capitation / advances)", "money"), C("owed", "Owed", "money")],
            "rows": rows, "totals": _tot(rows, "billed", "received", "unapplied", "owed", *[f"b{i}" for i in range(len(AGE))])}


def hmo_ageing(conn, e, as_of: dt.date) -> List[Dict[str, Any]]:
    """Per HMO / corporate payer: billed, received, FIFO-aged balance. Shared by the report and Credit Control."""
    bills: Dict[int, List] = defaultdict(list)
    for r in q(conn, """SELECT c.payer_tariff_id AS t, date_trunc('month', c.charge_date)::date AS month, SUM(c.outstanding) AS billed
                        FROM fin_v_hope_charges c WHERE c.payer_type IN ('HMO','CORPORATE') AND c.charge_date <= %s
                        GROUP BY 1,2 ORDER BY 1,2""", (as_of,)):
        bills[r["t"]].append((r["month"], money(r["billed"])))
    received = _payer_received(conn, e, as_of)
    meta = {r["tariff_id"]: r for r in q(conn, "SELECT tariff_id, name, customer_id, sage_code, payer_type FROM fin_hope_payers")}
    out = []
    for t, months in bills.items():
        left = received.get(t, ZERO)
        buckets = [ZERO] * len(AGE)
        oldest = None
        for month, billed in months:
            take = min(left, billed)
            left -= take
            rest = billed - take
            if rest <= 0:
                continue
            oldest = oldest or month
            age = (as_of - month).days
            buckets[next(i for i, (d, _) in enumerate(AGE) if age <= d)] += rest
        m = meta.get(t, {})
        # What an HMO paid beyond its billed lines (NHIS capitation, advances, receipts for pre-Hope years) is shown,
        # not netted against what other months still owe.
        out.append({"payer_id": t, "hmo": m.get("name"), "customer_id": m.get("customer_id"), "sage_code": m.get("sage_code"),
                    "payer_type": m.get("payer_type"), "billed": sum((b for _, b in months), ZERO),
                    "received": received.get(t, ZERO), "unapplied": left, "buckets": buckets, "oldest_open": oldest,
                    "owed": sum(buckets, ZERO)})
    out.sort(key=lambda r: -r["owed"])
    return out


@report("hope-sage-reconciliation")
def hope_sage_reconciliation(conn, e, p):
    """Month by month: revenue Hope billed against revenue Sage booked, for private patients and for HMOs."""
    rows = q(conn, f"""WITH h AS (SELECT date_trunc('month', c.charge_date)::date AS m,
                                         SUM({BILLED}) FILTER (WHERE c.payer_type IN ('PRIVATE','STAFF')) AS hope_private,
                                         SUM({BILLED}) FILTER (WHERE c.payer_type='PRIVATE' AND c.payer ILIKE 'scancare%%') AS scancare,
                                         SUM({BILLED}) FILTER (WHERE c.payer_type IN ('HMO','CORPORATE')) AS hope_hmo
                                  FROM fin_v_hope_charges c WHERE c.charge_date BETWEEN %s AND %s GROUP BY 1),
                            pay AS (SELECT date_trunc('month', received_at)::date AS m, SUM(amount) AS hope_collected
                                    FROM royan_payments WHERE external_source='hope' AND amount <= 50000000
                                      AND received_at::date BETWEEN %s AND %s GROUP BY 1),
                            s AS (SELECT date_trunc('month', journal_date)::date AS m,
                                         SUM(credit-debit) FILTER (WHERE account_code <> '4050') AS sage_private,
                                         SUM(credit-debit) FILTER (WHERE account_code = '4050') AS sage_hmo
                                  FROM fin_v_ledger WHERE legal_entity_id=%s AND subtype='SALES'
                                    AND journal_type NOT IN ('OPENING','CLOSING') AND journal_date BETWEEN %s AND %s GROUP BY 1)
                       SELECT to_char(COALESCE(h.m, s.m, pay.m), 'YYYY-MM') AS month, h.hope_private, h.scancare, s.sage_private,
                              COALESCE(s.sage_private,0) - COALESCE(h.hope_private,0) AS private_diff,
                              h.hope_hmo, s.sage_hmo, COALESCE(s.sage_hmo,0) - COALESCE(h.hope_hmo,0) AS hmo_diff,
                              pay.hope_collected
                       FROM h FULL JOIN s ON s.m=h.m FULL JOIN pay ON pay.m=COALESCE(h.m, s.m)
                       ORDER BY 1""", (p["from"], p["to"], p["from"], p["to"], e, p["from"], p["to"]))
    return {"title": "Hope vs Sage - Revenue Reconciliation", "subtitle":
            f"{p['from']} to {p['to']} · Hope: billed lines (private + staff, HMO + corporate). Sage/Roy Books: revenue booked "
            "(4050 HMO; every other income head as private). Hope collected = money taken at Hope's tills. Scancare walk-in "
            "customers were billed through Hope - check with Finance whether that income is Royan's or Scancare's. Sage runs to "
            "Dec 2024; Hope to Jan 2026.",
            "columns": [C("month", "Month"), C("hope_private", "Hope: private billed", "money"),
                        C("scancare", "of which Scancare walk-in", "money"),
                        C("sage_private", "Sage: private revenue", "money"), C("private_diff", "Difference (private)", "money"),
                        C("hope_hmo", "Hope: HMO billed", "money"), C("sage_hmo", "Sage: HMO revenue", "money"),
                        C("hmo_diff", "Difference (HMO)", "money"), C("hope_collected", "Hope: collected", "money")],
            "rows": rows, "totals": _tot(rows, "hope_private", "scancare", "sage_private", "private_diff", "hope_hmo", "sage_hmo",
                                         "hmo_diff", "hope_collected")}


# ---------------------------------------------------------------------------
# The day's takings, discounts and claims
# ---------------------------------------------------------------------------

@report("daily-revenue")
def daily_revenue(conn, e, p):
    """Per day: what was billed by payer type and what was collected by method (Hope tills and Roy Books receipts)."""
    rows = q(conn, f"""WITH b AS (SELECT c.charge_date AS d, {_split_sql()} FROM fin_v_hope_charges c
                                  WHERE c.charge_date BETWEEN %s AND %s GROUP BY 1),
                            m AS (SELECT received_at::date AS d,
                                         SUM(amount) FILTER (WHERE payment_method='cash') AS cash,
                                         SUM(amount) FILTER (WHERE payment_method='card') AS card,
                                         SUM(amount) FILTER (WHERE payment_method='transfer') AS transfer,
                                         SUM(amount) FILTER (WHERE payment_method NOT IN ('cash','card','transfer')) AS other
                                  FROM royan_payments WHERE amount <= 50000000 AND received_at::date BETWEEN %s AND %s GROUP BY 1),
                            r AS (SELECT receipt_date AS d, SUM(amount) AS books FROM fin_customer_receipts
                                  WHERE legal_entity_id=%s AND status='POSTED' AND receipt_date BETWEEN %s AND %s
                                    AND COALESCE(source_type,'') <> 'PAYMENT' GROUP BY 1)
                       SELECT COALESCE(b.d, m.d, r.d) AS date, b.private, b.hmo, b.staff, b.corporate, b.total AS billed,
                              m.cash, m.card, m.transfer, m.other, r.books AS other_receipts,
                              COALESCE(m.cash,0)+COALESCE(m.card,0)+COALESCE(m.transfer,0)+COALESCE(m.other,0)+COALESCE(r.books,0) AS collected
                       FROM b FULL JOIN m ON m.d=b.d FULL JOIN r ON r.d=COALESCE(b.d, m.d)
                       ORDER BY 1 DESC""", (p["from"], p["to"], p["from"], p["to"], e, p["from"], p["to"]))
    return {"title": "Daily Revenue & Collections", "subtitle": f"{p['from']} to {p['to']} · billed by payer (Hope lines), "
            "collected by method (cashier payments) plus other receipts entered in Roy Books",
            "columns": [C("date", "Date", "date"), C("private", "Private", "money"), C("hmo", "HMO", "money"),
                        C("staff", "Staff", "money"), C("corporate", "Corporate", "money"), C("billed", "Billed", "money"),
                        C("cash", "Cash", "money"), C("card", "Card / POS", "money"), C("transfer", "Transfer", "money"),
                        C("other", "Other", "money"), C("other_receipts", "Other receipts", "money"), C("collected", "Collected", "money")],
            "rows": rows, "totals": _tot(rows, "private", "hmo", "staff", "corporate", "billed", "cash", "card", "transfer",
                                         "other", "other_receipts", "collected")}


@report("discounts-waivers")
def discounts_waivers(conn, e, p):
    """Every discount, waiver and write-off on a hospital bill, who asked and who approved; plus Hope's line discounts."""
    rows = q(conn, """SELECT b.billed_at::date AS date, b.bill_number, b.patient_id, p.mrn,
                             NULLIF(trim(concat_ws(' ', p.first_name, p.last_name)), '') AS patient, b.subtotal, b.discount,
                             b.status, b.discount_status, b.discount_reason, b.discount_requested_by, b.discount_decided_by,
                             b.discount_decided_at::date AS decided, inv.id AS invoice_id, inv.invoice_number,
                             CASE WHEN b.external_source='hope' THEN 'Hope' ELSE 'Roy Health' END AS origin
                      FROM royan_billing b LEFT JOIN royan_patients p ON p.id=b.patient_id
                      LEFT JOIN fin_sales_invoices inv ON inv.source_type='BILLING' AND inv.source_id=b.id::text
                      WHERE b.billed_at::date BETWEEN %s AND %s
                        AND (b.discount > 0 OR b.discount_status <> 'none' OR b.status IN ('waived','written_off'))
                      ORDER BY b.billed_at DESC""", (p["from"], p["to"]))
    hope = q1(conn, "SELECT COUNT(*) n, COALESCE(SUM(discount),0) v FROM fin_hope_charges WHERE discount > 0 AND charge_date BETWEEN %s AND %s",
              (p["from"], p["to"]))
    return {"title": "Discounts, Waivers & Write-offs", "subtitle":
            f"{p['from']} to {p['to']} · bills with a discount, waiver or write-off. Hope line discounts in the period: "
            f"{hope['n']:,} lines, ₦{money(hope['v']):,.2f}.",
            "columns": [C("date", "Date", "date"), C("bill_number", "Bill"), C("patient", "Patient"), C("mrn", "MRN"),
                        C("origin", "From"), C("subtotal", "Bill total", "money"), C("discount", "Discount", "money"),
                        C("status", "Bill status"), C("discount_status", "Discount"), C("discount_reason", "Reason"),
                        C("discount_requested_by", "Asked by"), C("discount_decided_by", "Decided by"),
                        C("invoice_number", "Roy Books invoice", link="invoice", id_field="invoice_id")],
            "rows": rows, "totals": _tot(rows, "subtotal", "discount")}


@report("hmo-claims-register")
def hmo_claims_register(conn, e, p):
    """Every HMO claim the hospital recorded, with where its HMO invoice stands in the books."""
    rows = q(conn, """SELECT c.id, c.submitted_at::date AS submitted, c.hmo_provider AS hmo, c.hmo_id AS member_no,
                             NULLIF(trim(concat_ws(' ', p.first_name, p.last_name)), '') AS patient, p.mrn, b.bill_number,
                             c.claim_amount, c.approved_amount, c.status, c.settled_at::date AS settled,
                             inv.id AS invoice_id, inv.invoice_number, inv.status AS invoice_status,
                             inv.total - inv.amount_settled AS outstanding, cu.id AS customer_id
                      FROM royan_insurance_claims c LEFT JOIN royan_patients p ON p.id=c.patient_id
                      LEFT JOIN royan_billing b ON b.id=c.billing_id
                      LEFT JOIN fin_sales_invoices inv ON inv.source_type='BILLING_HMO' AND inv.source_id=c.billing_id::text
                      LEFT JOIN fin_customers cu ON cu.id=inv.customer_id
                      WHERE c.submitted_at::date BETWEEN %s AND %s ORDER BY c.submitted_at DESC""", (p["from"], p["to"]))
    return {"title": "HMO Claims Register", "subtitle":
            f"{p['from']} to {p['to']} · a claim moves to approved / paid / rejected as its HMO invoice is paid or disallowed in Roy Books",
            "columns": [C("submitted", "Submitted", "date"), C("hmo", "HMO", link="customer", id_field="customer_id"),
                        C("patient", "Patient"), C("mrn", "MRN"), C("member_no", "Member no."), C("bill_number", "Bill"),
                        C("claim_amount", "Claimed", "money"), C("approved_amount", "Approved", "money"), C("status", "Status"),
                        C("settled", "Settled", "date"), C("invoice_number", "HMO invoice", link="invoice", id_field="invoice_id"),
                        C("invoice_status", "Invoice status"), C("outstanding", "Outstanding", "money")],
            "rows": rows, "totals": _tot(rows, "claim_amount", "approved_amount", "outstanding")}


# ---------------------------------------------------------------------------
# A Hope visit (lineage target) and payers Finance can re-type
# ---------------------------------------------------------------------------

def visit(conn, visit_id: int) -> Dict[str, Any]:
    lines = q(conn, """SELECT c.source, c.hope_id, c.charge_date, c.service, c.category, c.quantity, c.gross, c.discount,
                              c.paid_cash, c.paid_card, c.paid, c.outstanding, c.reference, c.payer, c.payer_type, c.customer_id
                       FROM fin_v_hope_charges c WHERE c.visit_id=%s ORDER BY c.charge_date, c.source, c.hope_id""", (visit_id,))
    if not lines:
        raise not_found("Hope visit", visit_id)
    head = q1(conn, """SELECT c.mrn, c.patient_id, NULLIF(trim(concat_ws(' ', p.first_name, p.last_name)), '') AS patient,
                              p.gender, p.date_of_birth, p.phone
                       FROM fin_hope_charges c LEFT JOIN royan_patients p ON p.id=c.patient_id
                       WHERE c.visit_id=%s LIMIT 1""", (visit_id,))
    tot = {k: sum((money(l[k]) for l in lines), ZERO) for k in ("gross", "discount", "paid", "outstanding")}
    return {"visit_id": visit_id, **(head or {}), "payer": lines[0]["payer"], "payer_type": lines[0]["payer_type"],
            "customer_id": lines[0]["customer_id"], "from": min(l["charge_date"] for l in lines),
            "to": max(l["charge_date"] for l in lines), "lines": lines, "totals": tot}


def list_payers(conn) -> List[Dict[str, Any]]:
    return q(conn, """SELECT p.*, h.name AS hmo_name, cu.name AS customer_name,
                             (SELECT COUNT(*) FROM fin_hope_charges c WHERE c.payer_tariff_id=p.tariff_id) AS lines,
                             (SELECT MAX(charge_date) FROM fin_hope_charges c WHERE c.payer_tariff_id=p.tariff_id) AS last_used
                      FROM fin_hope_payers p LEFT JOIN royan_hmos h ON h.id=p.hmo_id LEFT JOIN fin_customers cu ON cu.id=p.customer_id
                      ORDER BY lines DESC, p.name""")


def set_payer_type(conn, ctx, tariff_id: int, payer_type: str) -> Dict[str, Any]:
    from src.fin import audit
    from src.fin.errors import invalid
    ctx.require("finance.settings.edit")
    if payer_type not in TYPES:
        raise invalid(f"Payer type must be one of {', '.join(TYPES)}")
    row = q1(conn, """UPDATE fin_hope_payers SET payer_type=%s, typed_by=%s, updated_at=now() WHERE tariff_id=%s
                      RETURNING tariff_id, name, payer_type""", (payer_type, ctx.actor_id, tariff_id))
    if not row:
        raise not_found("Payer", tariff_id)
    audit.record(conn, ctx, "PAYER_RETYPED", "hope_payer", str(tariff_id), ref=row["name"], metadata={"payer_type": payer_type})
    return row
