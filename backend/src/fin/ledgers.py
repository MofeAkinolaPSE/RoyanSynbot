"""Customer and supplier ledgers ("every patient, every HMO, every supplier is a ledger" - finance meeting, Oct 2026).

Three sources, never mixed into one total:
  * books   - Roy Books since go-live: invoices, receipts, credit notes, refunds per customer (the audited figures);
  * hope    - each patient's Hope history: bills less receipts as Hope recorded them (not reconciled - Hope's receipts
              include deposits and HMO settlements, so a patient can look over-paid or owing);
  * payers  - HMOs and companies: Hope billing less the receipts Sage booked, aged (what Credit Control uses).
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any, Dict, List, Optional

from src.fin import payers
from src.fin.db import ZERO, money, q, q1

AGE_LABELS = ["0-30", "31-60", "61-90", "91-180", "181-365", "Over 1 year"]


def _status(balance: Decimal) -> str:
    return "OWING" if balance > Decimal("0.5") else "IN_CREDIT" if balance < Decimal("-0.5") else "PAID"


def _is_royan(conn, entity_id: str) -> bool:
    """Hope and the pre-go-live Sage balances are Royan Hospital's history; another company's books (Scancare) never show them."""
    e = q1(conn, "SELECT code FROM fin_legal_entities WHERE id=%s", (entity_id,))
    return not e or e["code"] == "RHL"


def customers(conn, entity_id: str, *, source: str = "books", search: str = "", status: str = "", party_type: str = "",
              limit: int = 300) -> Dict[str, Any]:
    like = f"%{search}%"
    if source in ("hope", "payers") and not _is_royan(conn, entity_id):
        return {"source": source, "rows": [], "note": "Hope history belongs to Royan Hospital's books."}
    if source == "hope":
        rows = q(conn, """
            WITH b AS (SELECT patient_id, SUM(patient_balance) AS invoiced, COUNT(*) AS invoices, MAX(billed_at)::date AS last_bill
                       FROM royan_billing WHERE external_source='hope' AND status <> 'void' GROUP BY 1),
                 p AS (SELECT patient_id, SUM(amount) AS received, MAX(received_at)::date AS last_receipt
                       FROM royan_payments WHERE external_source='hope' AND amount <= 50000000 GROUP BY 1)
            SELECT pt.id AS patient_id, trim(coalesce(pt.first_name,'') || ' ' || coalesce(pt.last_name,'')) AS name, 'PATIENT' AS party_type,
                   pt.mrn, b.invoices, b.invoiced, COALESCE(p.received,0) AS received, 0 AS credited, 0 AS refunded,
                   b.invoiced - COALESCE(p.received,0) AS balance, GREATEST(b.last_bill, p.last_receipt) AS last_activity
            FROM b JOIN royan_patients pt ON pt.id=b.patient_id LEFT JOIN p ON p.patient_id=b.patient_id
            WHERE (%s = '' OR pt.first_name ILIKE %s OR pt.last_name ILIKE %s OR pt.mrn ILIKE %s
                   OR (pt.first_name || ' ' || pt.last_name) ILIKE %s)
              AND (%s = '' OR (%s = 'OWING' AND b.invoiced - COALESCE(p.received,0) > 0.5)
                   OR (%s = 'IN_CREDIT' AND b.invoiced - COALESCE(p.received,0) < -0.5)
                   OR (%s = 'PAID' AND abs(b.invoiced - COALESCE(p.received,0)) <= 0.5))
            ORDER BY lower(trim(coalesce(pt.first_name,'') || ' ' || coalesce(pt.last_name,''))), pt.id
            LIMIT %s""", (search, like, like, like, like, status, status, status, status, limit))
        for r in rows:
            r["status"] = _status(Decimal(str(r["balance"])))
            r["source"] = "Hope (before go-live)"
        return {"source": "hope", "rows": rows, "note": "Hope's bills less Hope's receipts for each patient, as Hope recorded "
                "them. Not reconciled: Hope's receipts include deposits and HMO settlements, so treat these as history, not "
                "as debts in the books."}
    if source == "payers":
        s = q1(conn, "SELECT cutover_date FROM fin_settings WHERE legal_entity_id=%s", (entity_id,)) or {}
        on = (s.get("cutover_date") or dt.date.today()) - dt.timedelta(days=1)
        rows = []
        for r in payers.hmo_ageing(conn, entity_id, on):
            if search and search.lower() not in str(r["hmo"] or "").lower():
                continue
            if party_type and str(r["payer_type"] or "").upper() != party_type.upper():
                continue
            bal = money(r["billed"]) - money(r["received"])
            row = {"payer_id": r["payer_id"], "id": r["customer_id"], "name": r["hmo"], "party_type": r["payer_type"],
                   "invoiced": r["billed"], "received": r["received"], "credited": ZERO, "refunded": ZERO, "balance": bal,
                   "owed_aged": r["owed"], "unapplied": r["unapplied"], "buckets": r["buckets"], "oldest_open": r["oldest_open"],
                   "status": _status(bal), "source": "Hope billing less Sage receipts"}
            if not status or row["status"] == status.upper():
                rows.append(row)
        rows.sort(key=lambda r: str(r["name"] or "").lower())   # A-Z
        return {"source": "payers", "as_of": on, "rows": rows[:limit], "age_labels": AGE_LABELS,
                "note": f"HMOs and companies to {on:%d %b %Y}: what Hope billed them less what Sage recorded as received."}
    rows = q(conn, """
        WITH inv AS (SELECT customer_id, SUM(total) AS invoiced, MAX(invoice_date) AS last_invoice, COUNT(*) AS invoices
                     FROM fin_sales_invoices WHERE legal_entity_id=%s AND status NOT IN ('DRAFT','VOID') GROUP BY 1),
             rec AS (SELECT customer_id, SUM(amount + wht_amount) AS received, MAX(receipt_date) AS last_receipt
                     FROM fin_customer_receipts WHERE legal_entity_id=%s AND status <> 'VOID' GROUP BY 1),
             cn AS (SELECT customer_id, SUM(total) AS credited FROM fin_credit_notes
                    WHERE legal_entity_id=%s AND status NOT IN ('DRAFT','VOID') GROUP BY 1),
             ref AS (SELECT customer_id, SUM(amount) AS refunded FROM fin_customer_refunds
                     WHERE legal_entity_id=%s AND status <> 'VOID' GROUP BY 1)
        SELECT c.id, c.patient_id, c.name, c.party_type, c.customer_code, c.mrn, COALESCE(inv.invoices,0) AS invoices,
               COALESCE(inv.invoiced,0) AS invoiced, COALESCE(rec.received,0) AS received, COALESCE(cn.credited,0) AS credited,
               COALESCE(ref.refunded,0) AS refunded,
               COALESCE(inv.invoiced,0) + COALESCE(ref.refunded,0) - COALESCE(rec.received,0) - COALESCE(cn.credited,0) AS balance,
               GREATEST(inv.last_invoice, rec.last_receipt) AS last_activity
        FROM fin_v_customers c LEFT JOIN inv ON inv.customer_id=c.id LEFT JOIN rec ON rec.customer_id=c.id
        LEFT JOIN cn ON cn.customer_id=c.id LEFT JOIN ref ON ref.customer_id=c.id
        WHERE c.id IS NOT NULL AND (inv.customer_id IS NOT NULL OR rec.customer_id IS NOT NULL OR cn.customer_id IS NOT NULL)
          AND (%s = '' OR c.name ILIKE %s OR c.customer_code ILIKE %s OR c.mrn ILIKE %s)
          AND (%s = '' OR c.party_type = %s)
        ORDER BY lower(c.name) LIMIT %s""",
             (entity_id,) * 4 + (search, like, like, like, party_type, party_type, limit))
    for r in rows:
        r["status"] = _status(Decimal(str(r["balance"])))
        r["source"] = "Roy Books"
    if status:
        rows = [r for r in rows if r["status"] == status.upper()]
    owing = sum((Decimal(str(r["balance"])) for r in rows if r["status"] == "OWING"), ZERO)
    credit = sum((-Decimal(str(r["balance"])) for r in rows if r["status"] == "IN_CREDIT"), ZERO)
    return {"source": "books", "rows": rows, "owing": owing, "in_credit": credit}


def payer_aging(conn, entity_id: str, as_of: Optional[dt.date] = None) -> Dict[str, Any]:
    """HMO and company balances before go-live, FIFO-aged (Hope billing less Sage receipts)."""
    if not _is_royan(conn, entity_id):
        return {"as_of": as_of, "labels": AGE_LABELS, "rows": [], "totals": [], "total": ZERO, "source": "Royan Hospital only"}
    s = q1(conn, "SELECT cutover_date FROM fin_settings WHERE legal_entity_id=%s", (entity_id,)) or {}
    cut = s.get("cutover_date")
    on = as_of or ((cut - dt.timedelta(days=1)) if cut else dt.date.today())
    if cut and on >= cut:
        on = cut - dt.timedelta(days=1)
    rows = [r for r in payers.hmo_ageing(conn, entity_id, on) if r["owed"] > 0]
    totals = [sum((r["buckets"][i] for r in rows), ZERO) for i in range(len(AGE_LABELS))]
    return {"as_of": on, "labels": AGE_LABELS, "rows": rows, "totals": totals, "total": sum(totals, ZERO),
            "source": "Hope billing less Sage receipts (before go-live)"}


def hope_purchases(conn, *, date_from: dt.date, date_to: dt.date, supplier_id: Optional[str] = None, search: str = "",
                   limit: int = 500, entity_id: Optional[str] = None) -> Dict[str, Any]:
    """Hope's goods-received records: the purchase history by supplier before go-live (not in the books)."""
    if entity_id and not _is_royan(conn, entity_id):
        return {"rows": [], "count": 0, "value": ZERO}
    like = f"%{search}%"
    rows = q(conn, """SELECT hope_id, po_number, grn_number, supplier_name, supplier_id::text AS supplier_id, supplier_invoice,
                             order_date, received_date, status, store, total, vat, discount, net_amount,
                             (SELECT COUNT(*) FROM fin_hope_purchase_items i WHERE i.purchase_id=p.hope_id) AS items
                      FROM fin_hope_purchases p
                      WHERE COALESCE(received_date, order_date) BETWEEN %s AND %s
                        AND (%s::text IS NULL OR supplier_id::text = %s)
                        AND (%s = '' OR supplier_name ILIKE %s OR supplier_invoice ILIKE %s OR po_number ILIKE %s OR grn_number ILIKE %s)
                      ORDER BY COALESCE(received_date, order_date) DESC, hope_id DESC LIMIT %s""",
             (date_from, date_to, supplier_id, supplier_id, search, like, like, like, like, limit))
    tot = q1(conn, """SELECT COUNT(*) AS n, COALESCE(SUM(net_amount),0) AS value FROM fin_hope_purchases
                      WHERE COALESCE(received_date, order_date) BETWEEN %s AND %s AND (%s::text IS NULL OR supplier_id::text = %s)""",
             (date_from, date_to, supplier_id, supplier_id))
    return {"rows": rows, "count": tot["n"], "value": tot["value"]}


def hope_purchase(conn, hope_id: int) -> Dict[str, Any]:
    p = q1(conn, "SELECT * FROM fin_hope_purchases WHERE hope_id=%s", (hope_id,))
    if not p:
        from src.fin.errors import not_found
        raise not_found("Purchase", hope_id)
    p["lines"] = q(conn, "SELECT * FROM fin_hope_purchase_items WHERE purchase_id=%s ORDER BY hope_id", (hope_id,))
    return p
