"""Royan's Sage 50 history (2009 -> 31 Dec 2024) as records you can open.

Read-only. Every Sage GL line belongs to a voucher (the lines Sage posted
together); a sales voucher is an invoice, a cash-receipts voucher a receipt.
These functions give each of those a record view so a figure in any report
drills: account -> Sage line -> voucher -> invoice / receipt -> customer ->
every other invoice and receipt of that customer. Loaded by fin.sage_import.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.fin.db import ZERO, money, q, q1
from src.fin.errors import not_found

JOURNAL_NAMES = {"SJ": "Sales journal (invoice)", "CRJ": "Cash receipts journal", "CDJ": "Cash disbursements journal",
                 "GENJ": "General journal"}


def _lines(conn, entity_id: str, voucher: str) -> List[Dict[str, Any]]:
    return q(conn, """SELECT l.id, l.row_no, l.account_id, l.account_code, a.name AS account_name, l.txn_date, l.jrnl, l.reference,
                             l.description, l.debit, l.credit, l.customer_id, c.name AS customer_name
                      FROM fin_sage_gl_lines l LEFT JOIN fin_accounts a ON a.id=l.account_id
                      LEFT JOIN fin_v_customers c ON c.id=l.customer_id
                      WHERE l.legal_entity_id=%s AND l.voucher=%s ORDER BY l.debit DESC, l.row_no""", (entity_id, voucher))


def voucher(conn, entity_id: str, key: str) -> Dict[str, Any]:
    lines = _lines(conn, entity_id, key)
    if not lines:
        raise not_found("Sage voucher", key)
    jrnl = lines[0]["jrnl"]
    out: Dict[str, Any] = {"voucher": key, "jrnl": jrnl, "journal": JOURNAL_NAMES.get(jrnl, jrnl), "date": lines[0]["txn_date"],
                           "reference": lines[0]["reference"], "lines": lines,
                           "total_debit": sum((money(l["debit"]) for l in lines), ZERO),
                           "total_credit": sum((money(l["credit"]) for l in lines), ZERO),
                           "customer_id": next((l["customer_id"] for l in lines if l["customer_id"]), None)}
    out["customer_name"] = next((l["customer_name"] for l in lines if l["customer_id"]), None)
    out["invoices"] = q(conn, """SELECT id, invoice_number, invoice_date, customer_name, amount FROM fin_sage_invoices
                                 WHERE legal_entity_id=%s AND voucher=%s""", (entity_id, key))
    out["receipts"] = q(conn, """SELECT id, reference, receipt_date, payer, amount FROM fin_sage_receipts
                                 WHERE legal_entity_id=%s AND voucher=%s ORDER BY row_no""", (entity_id, key))
    return out


def invoice(conn, entity_id: str, invoice_id: int) -> Dict[str, Any]:
    i = q1(conn, """SELECT i.*, c.party_type, c.mrn FROM fin_sage_invoices i LEFT JOIN fin_v_customers c ON c.id=i.customer_id
                    WHERE i.id=%s AND i.legal_entity_id=%s""", (invoice_id, entity_id))
    if not i:
        raise not_found("Sage invoice", invoice_id)
    i["lines"] = _lines(conn, entity_id, i["voucher"]) if i["voucher"] else []
    i["receipts"] = q(conn, """SELECT r.id, r.reference, r.receipt_date, r.payer, r.bank_account_code, a.name AS bank_account_name,
                                      r.bank_account_id, ri.amount
                               FROM fin_sage_receipt_invoices ri JOIN fin_sage_receipts r ON r.id=ri.receipt_id
                               LEFT JOIN fin_accounts a ON a.id=r.bank_account_id
                               WHERE ri.invoice_id=%s ORDER BY r.receipt_date""", (invoice_id,))
    i["balance"] = money(i["amount"]) - money(i["amount_received"])
    return i


def receipt(conn, entity_id: str, receipt_id: int) -> Dict[str, Any]:
    r = q1(conn, """SELECT r.*, a.name AS bank_account_name, c.party_type FROM fin_sage_receipts r
                    LEFT JOIN fin_accounts a ON a.id=r.bank_account_id LEFT JOIN fin_v_customers c ON c.id=r.customer_id
                    WHERE r.id=%s AND r.legal_entity_id=%s""", (receipt_id, entity_id))
    if not r:
        raise not_found("Sage receipt", receipt_id)
    r["invoices"] = q(conn, """SELECT ri.invoice_number, ri.invoice_id, ri.amount, i.invoice_date, i.amount AS invoice_amount
                               FROM fin_sage_receipt_invoices ri LEFT JOIN fin_sage_invoices i ON i.id=ri.invoice_id
                               WHERE ri.receipt_id=%s""", (receipt_id,))
    r["lines"] = _lines(conn, entity_id, r["voucher"]) if r["voucher"] else []
    return r


def customer_history(conn, entity_id: str, customer_id: int) -> Dict[str, Any]:
    by_year = q(conn, """SELECT y, SUM(inv) AS invoiced, SUM(rec) AS received, SUM(n_inv) AS invoices, SUM(n_rec) AS receipts FROM (
                           SELECT extract(year FROM invoice_date)::int y, amount inv, 0 rec, 1 n_inv, 0 n_rec FROM fin_sage_invoices
                           WHERE legal_entity_id=%s AND customer_id=%s
                           UNION ALL
                           SELECT extract(year FROM receipt_date)::int, 0, amount, 0, 1 FROM fin_sage_receipts
                           WHERE legal_entity_id=%s AND customer_id=%s) x GROUP BY y ORDER BY y DESC""",
                 (entity_id, customer_id, entity_id, customer_id))
    return {
        "codes": q(conn, "SELECT sage_code, name, contact, phone, match_method FROM fin_sage_customers WHERE legal_entity_id=%s AND customer_id=%s",
                   (entity_id, customer_id)),
        "invoices": q(conn, """SELECT id, invoice_number, invoice_date, amount, amount_received FROM fin_sage_invoices
                               WHERE legal_entity_id=%s AND customer_id=%s ORDER BY invoice_date DESC, row_no DESC LIMIT 2000""",
                      (entity_id, customer_id)),
        "receipts": q(conn, """SELECT r.id, r.reference, r.receipt_date, r.amount, a.name AS bank_account_name FROM fin_sage_receipts r
                               LEFT JOIN fin_accounts a ON a.id=r.bank_account_id
                               WHERE r.legal_entity_id=%s AND r.customer_id=%s ORDER BY r.receipt_date DESC LIMIT 2000""",
                      (entity_id, customer_id)),
        "by_year": by_year,
        "invoiced_total": sum((money(y["invoiced"]) for y in by_year), ZERO),
        "received_total": sum((money(y["received"]) for y in by_year), ZERO),
    }


def payee_history(conn, entity_id: str, name: str, limit: int = 500) -> Dict[str, Any]:
    """Sage cash disbursements whose payee matches a supplier's name (Sage kept no AP for Royan)."""
    words = [w for w in name.lower().replace("(", " ").split() if len(w) > 3 and w not in
             ("limited", "pharmaceutical", "pharmaceuticals", "nigeria", "company")]
    if not words:
        return {"lines": [], "total": ZERO, "matched_on": None}
    lines = q(conn, """SELECT l.voucher, l.txn_date, l.description, l.account_id, l.account_code, a.name AS account_name, l.debit
                       FROM fin_sage_gl_lines l JOIN fin_accounts a ON a.id=l.account_id
                       WHERE l.legal_entity_id=%s AND l.jrnl='CDJ' AND l.debit > 0 AND l.description ILIKE %s
                       ORDER BY l.txn_date DESC LIMIT %s""", (entity_id, f"%{words[0]}%", limit))
    return {"lines": lines, "total": sum((money(l["debit"]) for l in lines), ZERO), "matched_on": words[0]}


def summary(conn, entity_id: str) -> Dict[str, Any]:
    s = q1(conn, """SELECT (SELECT COUNT(*) FROM fin_sage_gl_lines WHERE legal_entity_id=%s) lines,
                           (SELECT MIN(txn_date) FROM fin_sage_gl_lines WHERE legal_entity_id=%s) first_date,
                           (SELECT MAX(txn_date) FROM fin_sage_gl_lines WHERE legal_entity_id=%s) last_date,
                           (SELECT COUNT(*) FROM fin_sage_invoices WHERE legal_entity_id=%s) invoices,
                           (SELECT COUNT(*) FROM fin_sage_receipts WHERE legal_entity_id=%s) receipts,
                           (SELECT COUNT(*) FROM fin_sage_customers WHERE legal_entity_id=%s) customers,
                           (SELECT history_replaces_opening FROM fin_settings WHERE legal_entity_id=%s) live""", (entity_id,) * 7)
    log = q1(conn, "SELECT rows, loaded_at FROM fin_sage_reports WHERE legal_entity_id=%s AND report_key='import-log'", (entity_id,))
    s["import"] = (log["rows"] or [None])[0] if log else None
    s["loaded_at"] = log["loaded_at"] if log else None
    s["reports"] = q(conn, """SELECT report_key, title, as_of, file_name FROM fin_sage_reports WHERE legal_entity_id=%s
                              AND report_key <> 'import-log' ORDER BY title""", (entity_id,))
    return s


def delivered(conn, entity_id: str, key: str) -> Dict[str, Any]:
    r = q1(conn, "SELECT * FROM fin_sage_reports WHERE legal_entity_id=%s AND report_key=%s", (entity_id, key))
    if not r:
        raise not_found("Sage report", key)
    return r


def reconciliation(conn, entity_id: str) -> Dict[str, Any]:
    items = q(conn, """SELECT i.*, a.id AS account_id, a.name AS account_name FROM fin_sage_recon_items i
                       LEFT JOIN fin_accounts a ON a.legal_entity_id=i.legal_entity_id AND a.code=i.account_code
                       WHERE i.legal_entity_id=%s ORDER BY i.section, i.item_date""", (entity_id,))
    totals: Dict[str, Any] = {}
    for i in items:
        totals[i["section"]] = totals.get(i["section"], ZERO) + money(i["amount"])
    return {"items": items, "totals": totals}
