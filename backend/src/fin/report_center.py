"""Roy Books Report Center: the Sage 50 report set as tabular, downloadable reports.

Every report returns ``{"title", "columns", "rows", "totals"}``. Columns carry a
type (text/money/qty/date) and optionally a ``link`` naming the lineage target
(invoice, receipt, bill, payment, customer, supplier, product, batch, account,
journal, source) plus the row field holding its id. The React Report Center
turns those into clicks, so every figure opens the record behind it
(report -> summary -> transaction -> journal -> source document).

Structured statements (P&L, balance sheet, cash flow, ageing, TB, GL,
Sage-style journals, valuation, unit activity) live in ``reports.py``/``ledger.py``;
this module adds the list/register/analysis reports Sage offers around them.
"""
from __future__ import annotations

import re
from decimal import Decimal

import datetime as dt
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional

from src.fin import ledger, reports
from src.fin.db import ZERO, money, q, q1
from src.fin.errors import FinError, invalid

REPORTS: Dict[str, Callable[..., Dict[str, Any]]] = {}


def report(key: str):
    def deco(fn):
        REPORTS[key] = fn
        return fn
    return deco


def C(key: str, label: str, type_: str = "text", link: Optional[str] = None, id_field: Optional[str] = None) -> Dict[str, Any]:
    c = {"key": key, "label": label, "type": type_}
    if link:
        c["link"] = link
        c["id"] = id_field or key
    return c


def _tot(rows: List[Dict[str, Any]], *keys: str) -> Dict[str, Any]:
    return {k: sum((money(r.get(k)) for r in rows), ZERO) for k in keys}


def run(conn, entity_id: str, key: str, p: Dict[str, Any]) -> Dict[str, Any]:
    fn = REPORTS.get(key)
    if not fn:
        raise FinError("RESOURCE_NOT_FOUND", f"Unknown report {key}", {"available": sorted(REPORTS)})
    out = fn(conn, entity_id, p)
    out.setdefault("totals", {})
    out["key"] = key
    return out


# ---------------------------------------------------------------------------
# General ledger
# ---------------------------------------------------------------------------

@report("chart-of-accounts")
def chart_of_accounts(conn, e, p):
    rows = q(conn, """SELECT a.id AS account_id, a.code, a.name, a.account_type, a.subtype, a.normal_balance,
                             a.is_control, a.is_postable, a.status, a.legacy_code, a.legacy_type,
                             COALESCE((SELECT SUM(g.debit-g.credit) FROM fin_v_ledger g
                                       WHERE g.account_id=a.id AND g.journal_date <= %s),0) AS balance
                      FROM fin_accounts a WHERE a.legal_entity_id=%s ORDER BY a.code""", (p["as_of"], e))
    for r in rows:
        r["account_type"] = r["account_type"].title()
        r["subtype"] = r["subtype"].replace("_", " ").title()
        r["flags"] = ", ".join(x for x, on in (("control", r["is_control"]), ("header", not r["is_postable"])) if on)
    return {"title": "Chart of Accounts", "subtitle": f"Balances as of {p['as_of']}",
            "columns": [C("code", "Account ID", link="account", id_field="account_id"), C("name", "Description"),
                        C("account_type", "Type"), C("subtype", "Subtype"), C("normal_balance", "Normal"),
                        C("status", "Status"), C("flags", "Flags"), C("legacy_type", "Sage type"),
                        C("balance", "Balance", "money", link="account", id_field="account_id")],
            "rows": rows}


@report("gl-account-summary")
def gl_account_summary(conn, e, p):
    tb = ledger.trial_balance(conn, e, p["from"], p["to"])
    rows = [{**r, "debit": r["period_debit"], "credit": r["period_credit"]} for r in tb["rows"]]
    return {"title": "General Ledger Account Summary", "subtitle": f"{p['from']} to {p['to']}",
            "columns": [C("code", "Account ID", link="account", id_field="account_id"), C("name", "Description"),
                        C("opening", "Beginning balance", "money"), C("debit", "Debits", "money", link="account", id_field="account_id"),
                        C("credit", "Credits", "money", link="account", id_field="account_id"), C("closing", "Ending balance", "money")],
            "rows": rows, "totals": _tot(rows, "debit", "credit")}


@report("working-trial-balance")
def working_trial_balance(conn, e, p):
    tb = ledger.trial_balance(conn, e, p["from"], p["to"])
    rows = [{"account_id": r["account_id"], "code": r["code"], "name": r["name"], "closing_debit": r["closing_debit"],
             "closing_credit": r["closing_credit"], "adj_debit": None, "adj_credit": None, "final": None} for r in tb["rows"]]
    return {"title": "Working Trial Balance", "subtitle": f"As of {p['to']} - blank columns for the accountant's adjustments",
            "columns": [C("code", "Account ID", link="account", id_field="account_id"), C("name", "Description"),
                        C("closing_debit", "Debit", "money"), C("closing_credit", "Credit", "money"),
                        C("adj_debit", "Adjustment Dr", "money"), C("adj_credit", "Adjustment Cr", "money"), C("final", "Final balance", "money")],
            "rows": rows, "totals": _tot(rows, "closing_debit", "closing_credit")}


@report("account-register")
def account_register(conn, e, p):
    if not p.get("account_id"):
        raise invalid("Choose an account (e.g. a bank account) for the register")
    act = ledger.account_activity(conn, e, p["account_id"], p["from"], p["to"], limit=100000)
    rows = [{**r, "ref": r["source_ref"] or r["journal_number"]} for r in act["rows"]]
    a = act["account"]
    return {"title": f"Account Register - {a['code']} {a['name']}", "subtitle": f"{p['from']} to {p['to']} · opening {act['opening']:,.2f} · closing {act['closing']:,.2f}",
            "columns": [C("journal_date", "Date", "date"), C("ref", "Reference", link="source", id_field="source_id"),
                        C("description", "Description"), C("debit", "Increase (Dr)", "money"), C("credit", "Decrease (Cr)", "money"),
                        C("running_balance", "Balance", "money"), C("journal_number", "Journal", link="journal", id_field="journal_id")],
            "rows": rows, "totals": _tot(rows, "debit", "credit")}


# ---------------------------------------------------------------------------
# Revenue lineage: Revenue -> month -> customer -> invoice -> journal
# ---------------------------------------------------------------------------

@report("sales-analysis")
def sales_analysis(conn, e, p):
    """Drillable revenue: by month, then a month by customer, then a customer's invoices."""
    where, prm = ["i.legal_entity_id=%s", "i.status NOT IN ('DRAFT','VOID')", "NOT i.is_opening",
                  "i.invoice_date BETWEEN %s AND %s"], [e, p["from"], p["to"]]
    if p.get("month"):
        y, m = map(int, str(p["month"]).split("-"))
        start = dt.date(y, m, 1)
        end = (dt.date(y + (m == 12), m % 12 + 1, 1) - dt.timedelta(days=1))
        where.append("i.invoice_date BETWEEN %s AND %s")
        prm += [start, end]
    if p.get("customer_id"):
        where.append("i.customer_id=%s")
        prm.append(int(p["customer_id"]))
    w = " AND ".join(where)
    level = "invoice" if p.get("customer_id") else ("customer" if p.get("month") else "month")
    base = f"""FROM fin_sales_invoices i LEFT JOIN fin_v_customers c ON c.id=i.customer_id
               LEFT JOIN fin_journals j ON j.id=i.journal_id
               LEFT JOIN LATERAL (SELECT COALESCE(SUM(l.cost_amount),0) cost FROM fin_sales_invoice_lines l WHERE l.invoice_id=i.id) k ON TRUE
               WHERE {w}"""
    if level == "month":
        rows = q(conn, f"""SELECT to_char(i.invoice_date,'YYYY-MM') AS month, COUNT(*) AS invoices,
                                  COUNT(DISTINCT i.customer_id) AS customers, SUM(i.total) AS sales, SUM(k.cost) AS cost,
                                  SUM(i.total) - SUM(k.cost) AS margin {base} GROUP BY 1 ORDER BY 1""", prm)
        cols = [C("month", "Month", link="drill:month", id_field="month"), C("invoices", "Invoices", "qty"), C("customers", "Customers", "qty"),
                C("sales", "Sales", "money", link="drill:month", id_field="month"), C("cost", "Cost of sales", "money"), C("margin", "Gross margin", "money")]
        title = "Sales analysis - by month"
    elif level == "customer":
        rows = q(conn, f"""SELECT i.customer_id, c.name AS customer, c.customer_code, COUNT(*) AS invoices, SUM(i.total) AS sales,
                                  SUM(k.cost) AS cost, SUM(i.total) - SUM(k.cost) AS margin, %s AS month
                           {base} GROUP BY i.customer_id, c.name, c.customer_code ORDER BY lower(c.name)""", [p["month"]] + prm)
        cols = [C("customer", "Customer", link="drill:customer", id_field="customer_id"), C("customer_code", "Code"),
                C("invoices", "Invoices", "qty"), C("sales", "Sales", "money", link="drill:customer", id_field="customer_id"),
                C("cost", "Cost of sales", "money"), C("margin", "Gross margin", "money")]
        title = f"Sales analysis - {p['month']} by customer"
    else:
        rows = q(conn, f"""SELECT i.id AS invoice_id, i.invoice_number, i.invoice_date, i.customer_id, c.name AS customer, i.total AS sales,
                                  k.cost, i.total - k.cost AS margin, i.status, i.journal_id, j.journal_number
                           {base}
                           ORDER BY i.invoice_date, i.invoice_number""", prm)
        cols = [C("invoice_date", "Date", "date"), C("invoice_number", "Invoice", link="invoice", id_field="invoice_id"),
                C("customer", "Customer", link="customer", id_field="customer_id"), C("sales", "Sales", "money", link="invoice", id_field="invoice_id"),
                C("cost", "Cost of sales", "money"), C("margin", "Gross margin", "money"), C("status", "Status"),
                C("journal_number", "Journal", link="journal", id_field="journal_id")]
        title = "Sales analysis - invoices"
    return {"title": title, "subtitle": f"{p['from']} to {p['to']}", "level": level, "columns": cols, "rows": rows,
            "totals": _tot(rows, "sales", "cost", "margin")}


# ---------------------------------------------------------------------------
# Accounts receivable
# ---------------------------------------------------------------------------

@report("invoice-register")
def invoice_register(conn, e, p):
    rows = q(conn, """SELECT i.id AS invoice_id, i.invoice_number, i.invoice_date, i.due_date, i.customer_id, c.name AS customer,
                             i.source_type, i.total, i.amount_settled, i.total - i.amount_settled AS balance, i.status,
                             i.journal_id, j.journal_number
                      FROM fin_sales_invoices i LEFT JOIN fin_v_customers c ON c.id=i.customer_id LEFT JOIN fin_journals j ON j.id=i.journal_id
                      WHERE i.legal_entity_id=%s AND i.invoice_date BETWEEN %s AND %s AND i.status <> 'DRAFT'
                      ORDER BY i.invoice_date, i.invoice_number""", (e, p["from"], p["to"]))
    return {"title": "Invoice Register", "subtitle": f"{p['from']} to {p['to']}",
            "columns": [C("invoice_date", "Date", "date"), C("invoice_number", "Invoice", link="invoice", id_field="invoice_id"),
                        C("customer", "Customer", link="customer", id_field="customer_id"), C("source_type", "Source"),
                        C("due_date", "Due", "date"), C("total", "Amount", "money", link="invoice", id_field="invoice_id"),
                        C("amount_settled", "Paid", "money"), C("balance", "Balance", "money"), C("status", "Status"),
                        C("journal_number", "Journal", link="journal", id_field="journal_id")],
            "rows": rows, "totals": _tot(rows, "total", "amount_settled", "balance")}


@report("receipts-register")
def receipts_register(conn, e, p):
    rows = q(conn, """SELECT r.id AS receipt_id, r.receipt_number, r.receipt_date, r.customer_id, c.name AS customer, r.method,
                             r.reference, b.name AS bank, r.amount, r.wht_amount, r.status, r.journal_id, j.journal_number
                      FROM fin_customer_receipts r LEFT JOIN fin_v_customers c ON c.id=r.customer_id
                      LEFT JOIN fin_bank_accounts b ON b.id=r.bank_account_id LEFT JOIN fin_journals j ON j.id=r.journal_id
                      WHERE r.legal_entity_id=%s AND r.receipt_date BETWEEN %s AND %s ORDER BY r.receipt_date, r.receipt_number""",
             (e, p["from"], p["to"]))
    return {"title": "Receipts Register / Bank Deposit Report", "subtitle": f"{p['from']} to {p['to']}",
            "columns": [C("receipt_date", "Date", "date"), C("receipt_number", "Receipt", link="receipt", id_field="receipt_id"),
                        C("customer", "Customer", link="customer", id_field="customer_id"), C("method", "Method"), C("reference", "Cheque / ref"),
                        C("bank", "Deposited to"), C("amount", "Amount", "money", link="receipt", id_field="receipt_id"),
                        C("wht_amount", "WHT", "money"), C("status", "Status"), C("journal_number", "Journal", link="journal", id_field="journal_id")],
            "rows": rows, "totals": _tot(rows, "amount", "wht_amount")}


def _party_ledger(conn, e, p, kind: str):
    """Customer / vendor ledgers: every party's opening, documents and running balance."""
    if kind == "customer":
        docs = """SELECT i.customer_id AS pid, i.invoice_date AS date, 'Invoice' AS type, i.invoice_number AS number, i.id::text AS doc_id,
                         'invoice' AS link, i.total AS debit, 0::numeric AS credit FROM fin_sales_invoices i
                  WHERE i.legal_entity_id=%(e)s AND i.status <> 'DRAFT'
                  UNION ALL SELECT i.customer_id, i.voided_at::date, 'Invoice void', i.invoice_number, i.id::text, 'invoice', 0, i.total
                  FROM fin_sales_invoices i WHERE i.legal_entity_id=%(e)s AND i.status='VOID' AND i.journal_id IS NOT NULL
                  UNION ALL SELECT r.customer_id, r.receipt_date, 'Receipt', r.receipt_number, r.id::text, 'receipt', 0, r.amount + r.wht_amount
                  FROM fin_customer_receipts r WHERE r.legal_entity_id=%(e)s
                  UNION ALL SELECT r.customer_id, r.receipt_date, 'Receipt reversed', r.receipt_number, r.id::text, 'receipt', r.amount + r.wht_amount, 0
                  FROM fin_customer_receipts r WHERE r.legal_entity_id=%(e)s AND r.status='VOID'
                  UNION ALL SELECT n.customer_id, n.note_date, 'Credit note', n.credit_note_number, n.id::text, 'creditnote', 0, n.total
                  FROM fin_credit_notes n WHERE n.legal_entity_id=%(e)s"""
        names = "SELECT id::text AS pid, name, customer_code AS code FROM fin_v_customers"
    else:
        docs = """SELECT b.supplier_id::text AS pid, b.bill_date AS date, 'Bill ' || b.supplier_invoice_number AS type, b.bill_number AS number,
                         b.id::text AS doc_id, 'bill' AS link, 0::numeric AS debit, b.total AS credit FROM fin_supplier_bills b
                  WHERE b.legal_entity_id=%(e)s
                  UNION ALL SELECT b.supplier_id::text, b.bill_date, 'Bill voided', b.bill_number, b.id::text, 'bill', b.total, 0
                  FROM fin_supplier_bills b WHERE b.legal_entity_id=%(e)s AND b.status='VOID' AND b.journal_id IS NOT NULL
                  UNION ALL SELECT p.supplier_id::text, p.payment_date, 'Payment', p.payment_number, p.id::text, 'payment', p.amount + p.wht_amount, 0
                  FROM fin_supplier_payments p WHERE p.legal_entity_id=%(e)s
                  UNION ALL SELECT p.supplier_id::text, p.payment_date, 'Payment reversed', p.payment_number, p.id::text, 'payment', 0, p.amount + p.wht_amount
                  FROM fin_supplier_payments p WHERE p.legal_entity_id=%(e)s AND p.status='VOID'
                  UNION ALL SELECT d.supplier_id::text, d.note_date, 'Debit note', d.debit_note_number, d.id::text, 'debitnote', d.total, 0
                  FROM fin_debit_notes d WHERE d.legal_entity_id=%(e)s"""
        names = "SELECT id::text AS pid, name, external_vendor_id AS code FROM suppliers"
    sign = "debit - credit" if kind == "customer" else "credit - debit"
    party_filter = " AND d.pid::text = %(pid)s" if p.get("party_id") else ""
    rows = q(conn, f"""
        WITH d AS ({docs}), n AS ({names}),
        o AS (SELECT pid::text pid, SUM({sign}) opening FROM d WHERE date < %(f)s GROUP BY 1),
        m AS (SELECT d.*, d.pid::text AS p2 FROM d WHERE date BETWEEN %(f)s AND %(t)s {party_filter})
        SELECT m.p2 AS party_id, n.name AS party, n.code, m.date, m.type, m.number, m.doc_id, m.link, m.debit, m.credit,
               COALESCE(o.opening,0) + SUM({sign.replace('debit', 'm.debit').replace('credit', 'm.credit')})
                   OVER (PARTITION BY m.p2 ORDER BY m.date, m.number ROWS UNBOUNDED PRECEDING) AS balance,
               COALESCE(o.opening,0) AS opening
        FROM m LEFT JOIN n ON n.pid=m.p2 LEFT JOIN o ON o.pid=m.p2
        ORDER BY n.name, m.date, m.number""", {"e": e, "f": p["from"], "t": p["to"], "pid": str(p.get("party_id") or "")})
    party_link = "customer" if kind == "customer" else "supplier"
    return rows, party_link


SAGE_COLS = lambda first, second, dr="Debit Amt", cr="Credit Amt": [
    C("account_id", first), C("account_description", second), C("date", "Date", "date"),
    C("reference", "Reference", link="journal", id_field="journal_id"), C("jrnl", "Jrnl"), C("trans_description", "Trans Description"),
    C("debit", dr, "money"), C("credit", cr, "money"), C("balance", "Balance", "money")]


@report("general-ledger")
def general_ledger_sage(conn, e, p):
    """The General Ledger exactly as Sage 50 prints it: by Account ID, month by month."""
    from src.fin import sage_gl
    d = sage_gl.general_ledger(conn, e, p["from"], p["to"], [p["account_id"]] if p.get("account_id") else None, p.get("search"))
    return {"title": "General Ledger", "subtitle": f"{p['from']} to {p['to']} · {d['accounts']} accounts · {d['lines']} transactions",
            "columns": SAGE_COLS("Account ID", "Account Description"), "rows": d["rows"], "layout": "sage"}


@report("customer-ledgers")
def customer_ledgers(conn, e, p):
    """Customer Ledgers as Sage prints them (customers A-Z): receivables lines from Sage's years and Roy Books."""
    from src.fin import sage_gl
    d = sage_gl.customer_ledger(conn, e, p["from"], p["to"], customer_id=p.get("customer_id"), search=p.get("search") or "")
    return {"title": "Customer Ledgers", "subtitle": f"{p['from']} to {p['to']} · {d['customers']} customers, A-Z",
            "columns": SAGE_COLS("Customer ID", "Customer"), "rows": d["rows"], "layout": "sage"}


@report("vendor-ledgers")
def vendor_ledgers(conn, e, p):
    """Vendor Ledgers as Sage prints them (vendors A-Z); balance = what is owed."""
    from src.fin import sage_gl
    d = sage_gl.vendor_ledger(conn, e, p["from"], p["to"], supplier_id=p.get("supplier_id"), search=p.get("search") or "")
    return {"title": "Vendor Ledgers", "subtitle": f"{p['from']} to {p['to']} · {d['vendors']} vendors, A-Z",
            "columns": SAGE_COLS("Vendor ID", "Vendor", "Billed", "Paid / returned"), "rows": d["rows"], "layout": "sage"}


@report("customer-sales-history")
def customer_sales_history(conn, e, p):
    rows = q(conn, """SELECT i.customer_id, c.name AS customer, c.customer_code, COUNT(DISTINCT i.id) AS invoices,
                             COALESCE(SUM(l.quantity) FILTER (WHERE l.line_type='ITEM'),0) AS units, SUM(l.line_total) AS sales,
                             COALESCE(SUM(l.cost_amount),0) AS cost, SUM(l.line_total) - COALESCE(SUM(l.cost_amount),0) AS margin,
                             MAX(i.invoice_date) AS last_sale
                      FROM fin_sales_invoices i JOIN fin_sales_invoice_lines l ON l.invoice_id=i.id LEFT JOIN fin_v_customers c ON c.id=i.customer_id
                      WHERE i.legal_entity_id=%s AND i.status NOT IN ('DRAFT','VOID') AND NOT i.is_opening AND i.invoice_date BETWEEN %s AND %s
                      GROUP BY i.customer_id, c.name, c.customer_code ORDER BY lower(c.name)""", (e, p["from"], p["to"]))
    return {"title": "Customer Sales History", "subtitle": f"{p['from']} to {p['to']}",
            "columns": [C("customer", "Customer", link="customer", id_field="customer_id"), C("customer_code", "Code"),
                        C("invoices", "Invoices", "qty"), C("units", "Units", "qty"), C("sales", "Sales", "money"),
                        C("cost", "Cost", "money"), C("margin", "Margin", "money"), C("last_sale", "Last sale", "date")],
            "rows": rows, "totals": _tot(rows, "sales", "cost", "margin")}


@report("items-sold-to-customers")
def items_sold(conn, e, p):
    rows = q(conn, """SELECT l.sku, p.name AS product, i.customer_id, c.name AS customer, SUM(l.quantity) AS quantity,
                             SUM(l.line_total) AS amount, COALESCE(SUM(l.cost_amount),0) AS cost,
                             SUM(l.line_total) - COALESCE(SUM(l.cost_amount),0) AS margin,
                             string_agg(DISTINCT i.invoice_number, ', ') AS invoices, MIN(i.id::text) AS invoice_id
                      FROM fin_sales_invoice_lines l JOIN fin_sales_invoices i ON i.id=l.invoice_id
                      LEFT JOIN fin_products p ON p.legal_entity_id=i.legal_entity_id AND p.sku=l.sku LEFT JOIN fin_v_customers c ON c.id=i.customer_id
                      WHERE i.legal_entity_id=%s AND l.sku IS NOT NULL AND i.status NOT IN ('DRAFT','VOID') AND NOT i.is_opening
                        AND i.invoice_date BETWEEN %s AND %s
                      GROUP BY l.sku, p.name, i.customer_id, c.name ORDER BY lower(p.name), lower(c.name)""", (e, p["from"], p["to"]))
    return {"title": "Items Sold to Customers", "subtitle": f"{p['from']} to {p['to']} - who bought what",
            "columns": [C("sku", "Item ID", link="product", id_field="sku"), C("product", "Description"),
                        C("customer", "Customer", link="customer", id_field="customer_id"), C("quantity", "Qty", "qty"),
                        C("amount", "Amount", "money"), C("cost", "Cost", "money"), C("margin", "Margin", "money"), C("invoices", "Invoices")],
            "rows": rows, "totals": _tot(rows, "amount", "cost", "margin")}


@report("customer-list")
def customer_list(conn, e, p):
    open_ = {}
    for it in reports.ar_open_items(conn, e, p["as_of"]):
        open_[it["customer_id"]] = open_.get(it["customer_id"], ZERO) + money(it["open_amount"])
    rows = q(conn, """SELECT id AS customer_id, customer_code, name, initcap(party_type) AS party_type, credit_limit, payment_terms_days,
                             contact_details->>'phone' AS phone, contact_details->>'email' AS email, contact_details->>'address' AS address
                      FROM fin_v_customers ORDER BY party_type, lower(name)""")
    for r in rows:
        r["balance"] = open_.get(r["customer_id"], ZERO)
    if p.get("with_balance"):
        rows = [r for r in rows if r["balance"] != 0]
    return {"title": "Patient & Payer Accounts", "subtitle": f"Every debtor account (patients, HMOs, corporates), balances as of {p['as_of']}",
            "columns": [C("customer_code", "Code / MRN"), C("name", "Name", link="customer", id_field="customer_id"), C("party_type", "Type"),
                        C("phone", "Phone"), C("email", "Email"), C("address", "Address"), C("payment_terms_days", "Terms (days)", "qty"),
                        C("credit_limit", "Credit limit", "money"), C("balance", "Balance", "money", link="customer", id_field="customer_id")],
            "rows": rows, "totals": _tot(rows, "balance")}


# ---------------------------------------------------------------------------
# Hospital reports (Royan): service lines, HMO debt, the cashier's day
# ---------------------------------------------------------------------------

@report("revenue-by-service-line")
def revenue_by_service_line(conn, e, p):
    """Net revenue per revenue account (service line) and month, from the ledger - the
    same figures as the income statement, broken down the way the hospital is run."""
    rows = q(conn, """SELECT g.account_id, g.account_code, g.account_name AS service_line,
                             to_char(date_trunc('month', g.journal_date), 'YYYY-MM') AS month,
                             SUM(g.credit - g.debit) AS revenue
                      FROM fin_v_ledger g WHERE g.legal_entity_id=%s AND g.subtype='SALES'
                        AND g.journal_type NOT IN ('CLOSING','OPENING') AND g.journal_date BETWEEN %s AND %s
                      GROUP BY 1,2,3,4 ORDER BY 4, 2""", (e, p["from"], p["to"]))
    return {"title": "Revenue by Service Line", "subtitle": f"{p['from']} to {p['to']} (net of discounts and returns)",
            "columns": [C("month", "Month"), C("account_code", "Account", link="account", id_field="account_id"),
                        C("service_line", "Service line", link="account", id_field="account_id"), C("revenue", "Revenue", "money")],
            "rows": rows, "totals": _tot(rows, "revenue")}


@report("hmo-receivables")
def hmo_receivables(conn, e, p):
    """What each HMO owes, aged by due date (the payer's share of bills)."""
    ag = reports.aged_receivables(conn, e, p["as_of"], party_type="HMO")
    rows = []
    for r in ag["rows"]:
        row = {"customer_id": r["customer_id"], "customer": r["customer_name"], "code": r["customer_code"], "total": r["total"],
               "invoices": len(r["items"]), "source": "Roy Books"}
        for i, label in enumerate(ag["buckets"]):
            row[f"b{i}"] = r["buckets"][i]
        rows.append(row)
    # Before go-live: what Hope billed each HMO / company less what Sage recorded as received (FIFO-aged) - the balances
    # Credit Control works from. Shown as one figure per payer, labelled by source, never added into the books' buckets.
    from src.fin import ledgers as _ledgers
    hist = _ledgers.payer_aging(conn, e, p["as_of"])
    for r in hist["rows"]:
        rows.append({"customer_id": r["customer_id"], "customer": r["hmo"], "code": r.get("sage_code"), "total": r["owed"],
                     "invoices": None, "source": f"Before go-live (to {hist['as_of']:%d %b %Y}): Hope billing less Sage receipts"})
    cols = [C("customer", "HMO", link="customer", id_field="customer_id"), C("code", "Code"), C("source", "Source"),
            C("invoices", "Open items", "qty")]
    cols += [C(f"b{i}", label, "money") for i, label in enumerate(ag["buckets"])]
    cols.append(C("total", "Total owed", "money", link="customer", id_field="customer_id"))
    return {"title": "HMO Receivables (aged)", "subtitle": f"As of {p['as_of']}", "columns": cols, "rows": rows,
            "totals": _tot(rows, "total", *[f"b{i}" for i in range(len(ag["buckets"]))])}


@report("cashier-collections")
def cashier_collections(conn, e, p):
    """Money received per day and method (cash, POS, transfer ...) - the cashier's daily close."""
    rows = q(conn, """SELECT * FROM (
                          SELECT r.receipt_date AS date, r.method, b.name AS account, COUNT(*) AS receipts, SUM(r.amount) AS amount,
                                 COUNT(*) FILTER (WHERE r.source_type='PAYMENT') AS from_billing, 'Roy Books' AS source
                          FROM fin_customer_receipts r JOIN fin_bank_accounts b ON b.id=r.bank_account_id
                          WHERE r.legal_entity_id=%s AND r.status='POSTED' AND r.receipt_date BETWEEN %s AND %s
                          GROUP BY 1,2,3
                          UNION ALL
                          -- before go-live: what Hope's cashiers took (history; Sage booked the money)
                          SELECT p.received_at::date, upper(p.payment_method), 'Hope cashier', COUNT(*), SUM(p.amount), COUNT(*), 'Hope (history)'
                          FROM royan_payments p
                          WHERE p.external_source='hope' AND p.amount <= 50000000 AND p.received_at::date BETWEEN %s AND %s
                            AND p.received_at::date < COALESCE((SELECT cutover_date FROM fin_settings WHERE legal_entity_id=%s), '2100-01-01')
                            AND (SELECT code FROM fin_legal_entities WHERE id=%s)='RHL'   -- Hope is Royan Hospital's history
                          GROUP BY 1,2,3) x ORDER BY 1 DESC, 2""", (e, p["from"], p["to"], p["from"], p["to"], e, e))
    return {"title": "Cashier Collections", "subtitle": f"{p['from']} to {p['to']}",
            "columns": [C("date", "Date"), C("method", "Method"), C("account", "Received into"), C("source", "Source"),
                        C("receipts", "Receipts", "qty"), C("from_billing", "From billing", "qty"), C("amount", "Amount", "money")],
            "rows": rows, "totals": _tot(rows, "amount")}


# ---------------------------------------------------------------------------
# Accounts payable
# ---------------------------------------------------------------------------

@report("purchase-register")
def purchase_register(conn, e, p):
    rows = q(conn, """SELECT b.id AS bill_id, b.bill_number, b.supplier_invoice_number, b.bill_date, b.due_date, b.supplier_id::text AS supplier_id,
                             s.name AS supplier, b.total, b.amount_settled, b.total - b.amount_settled AS balance, b.status, b.journal_id, j.journal_number
                      FROM fin_supplier_bills b LEFT JOIN suppliers s ON s.id=b.supplier_id LEFT JOIN fin_journals j ON j.id=b.journal_id
                      WHERE b.legal_entity_id=%s AND b.bill_date BETWEEN %s AND %s ORDER BY b.bill_date, b.bill_number""", (e, p["from"], p["to"]))
    rows += q(conn, """SELECT NULL AS bill_id, h.po_number || COALESCE(' / ' || h.grn_number, '') AS bill_number, h.supplier_invoice AS supplier_invoice_number,
                              COALESCE(h.received_date, h.order_date) AS bill_date, NULL::date AS due_date, h.supplier_id::text AS supplier_id,
                              h.supplier_name AS supplier, h.net_amount AS total, NULL::numeric AS amount_settled, NULL::numeric AS balance,
                              'Hope (history)' AS status, NULL AS journal_id, NULL AS journal_number
                       FROM fin_hope_purchases h WHERE COALESCE(h.received_date, h.order_date) BETWEEN %s AND %s AND (SELECT code FROM fin_legal_entities WHERE id=%s)='RHL'
                       ORDER BY 4, 2""", (p["from"], p["to"], e))
    return {"title": "Purchase Register", "subtitle": f"{p['from']} to {p['to']} · Roy Books bills, and Hope's goods received before go-live",
            "columns": [C("bill_date", "Date", "date"), C("bill_number", "Bill", link="bill", id_field="bill_id"),
                        C("supplier_invoice_number", "Vendor invoice"), C("supplier", "Vendor", link="supplier", id_field="supplier_id"),
                        C("due_date", "Due", "date"), C("total", "Amount", "money"), C("amount_settled", "Paid", "money"),
                        C("balance", "Balance", "money"), C("status", "Status"), C("journal_number", "Journal", link="journal", id_field="journal_id")],
            "rows": rows, "totals": _tot(rows, "total", "amount_settled", "balance")}


@report("check-register")
def check_register(conn, e, p):
    rows = q(conn, """SELECT * FROM (
                        SELECT p.payment_date AS date, p.payment_number AS number, p.id::text AS doc_id, 'payment' AS link, p.method,
                               p.reference, s.name AS payee, b.name AS bank, p.amount, p.status, p.journal_id, j.journal_number
                        FROM fin_supplier_payments p LEFT JOIN suppliers s ON s.id=p.supplier_id
                        LEFT JOIN fin_bank_accounts b ON b.id=p.bank_account_id LEFT JOIN fin_journals j ON j.id=p.journal_id
                        WHERE p.legal_entity_id=%s AND p.payment_date BETWEEN %s AND %s
                        UNION ALL
                        SELECT v.voucher_date, v.voucher_number, v.id::text, 'voucher', 'VOUCHER', v.reference, COALESCE(v.payee, v.description),
                               b.name, v.amount, v.status, v.journal_id, j.journal_number
                        FROM fin_cash_vouchers v LEFT JOIN fin_bank_accounts b ON b.id=v.bank_account_id LEFT JOIN fin_journals j ON j.id=v.journal_id
                        WHERE v.legal_entity_id=%s AND v.kind='SPEND' AND v.voucher_date BETWEEN %s AND %s) x
                      ORDER BY date, number""", (e, p["from"], p["to"], e, p["from"], p["to"]))
    return {"title": "Check / Payment Register", "subtitle": f"{p['from']} to {p['to']} - supplier payments and payment vouchers",
            "columns": [C("date", "Date", "date"), C("number", "Number", link="doc", id_field="doc_id"), C("method", "Method"),
                        C("reference", "Cheque / ref"), C("payee", "Payee"), C("bank", "Paid from"), C("amount", "Amount", "money"),
                        C("status", "Status"), C("journal_number", "Journal", link="journal", id_field="journal_id")],
            "rows": rows, "totals": _tot(rows, "amount")}


@report("cash-requirements")
def cash_requirements(conn, e, p):
    names = {str(r["id"]): r["name"] for r in q(conn, "SELECT id, name FROM suppliers")}
    rows = []
    for it in reports.ap_open_items(conn, e, p["as_of"]):
        if it["doc_type"] != "BILL":
            continue
        days = (it["due_date"] - p["as_of"]).days
        rows.append({"supplier_id": str(it["supplier_id"]), "supplier": names.get(str(it["supplier_id"])), "bill_id": it["doc_id"],
                     "bill_number": it["doc_number"], "supplier_ref": it["supplier_ref"], "doc_date": it["doc_date"], "due_date": it["due_date"],
                     "days": days, "when": "Overdue" if days < 0 else ("Due within 7 days" if days <= 7 else ("Within 30 days" if days <= 30 else "Later")),
                     "amount": it["open_amount"]})
    rows.sort(key=lambda r: r["due_date"])
    return {"title": "Cash Requirements", "subtitle": f"Unpaid supplier bills by due date, as of {p['as_of']}",
            "columns": [C("due_date", "Due", "date"), C("when", "When"), C("supplier", "Vendor", link="supplier", id_field="supplier_id"),
                        C("bill_number", "Bill", link="bill", id_field="bill_id"), C("supplier_ref", "Vendor invoice"),
                        C("doc_date", "Invoice date", "date"), C("amount", "Amount due", "money")],
            "rows": rows, "totals": _tot(rows, "amount")}


@report("items-purchased-from-vendors")
def items_purchased(conn, e, p):
    rows = q(conn, """SELECT l.sku, pr.name AS product, b.supplier_id::text AS supplier_id, s.name AS supplier, SUM(l.quantity) AS quantity,
                             SUM(l.line_total) AS amount, ROUND(SUM(l.line_total)/NULLIF(SUM(l.quantity),0), 2) AS avg_cost,
                             string_agg(DISTINCT b.bill_number, ', ') AS bills
                      FROM fin_supplier_bill_lines l JOIN fin_supplier_bills b ON b.id=l.bill_id
                      LEFT JOIN fin_products pr ON pr.legal_entity_id=b.legal_entity_id AND pr.sku=l.sku LEFT JOIN suppliers s ON s.id=b.supplier_id
                      WHERE b.legal_entity_id=%s AND l.sku IS NOT NULL AND b.status <> 'VOID' AND b.bill_date BETWEEN %s AND %s
                      GROUP BY l.sku, pr.name, b.supplier_id, s.name ORDER BY lower(pr.name), lower(s.name)""", (e, p["from"], p["to"]))
    # before go-live: Hope's goods received (history - Sage paid suppliers from the cash book without a purchases journal)
    rows += q(conn, """SELECT NULL AS sku, i.product_name AS product, h.supplier_id::text AS supplier_id, h.supplier_name AS supplier,
                              SUM(i.quantity) AS quantity, SUM(i.amount) AS amount, ROUND(SUM(i.amount)/NULLIF(SUM(i.quantity),0), 2) AS avg_cost,
                              'Hope: ' || string_agg(DISTINCT h.po_number, ', ') AS bills
                       FROM fin_hope_purchase_items i JOIN fin_hope_purchases h ON h.hope_id=i.purchase_id
                       WHERE COALESCE(h.received_date, h.order_date) BETWEEN %s AND %s AND (SELECT code FROM fin_legal_entities WHERE id=%s)='RHL'
                       GROUP BY i.product_name, h.supplier_id, h.supplier_name ORDER BY lower(i.product_name), lower(h.supplier_name)""",
              (p["from"], p["to"], e))
    return {"title": "Items Purchased from Vendors", "subtitle": f"{p['from']} to {p['to']}",
            "columns": [C("sku", "Item ID", link="product", id_field="sku"), C("product", "Description"),
                        C("supplier", "Vendor", link="supplier", id_field="supplier_id"), C("quantity", "Qty", "qty"),
                        C("avg_cost", "Avg unit cost", "money"), C("amount", "Amount", "money"), C("bills", "Bills")],
            "rows": rows, "totals": _tot(rows, "amount")}


@report("vendor-list")
def vendor_list(conn, e, p):
    owed: Dict[str, Decimal] = {}
    for it in reports.ap_open_items(conn, e, p["as_of"]):
        owed[str(it["supplier_id"])] = owed.get(str(it["supplier_id"]), ZERO) + money(it["open_amount"])
    rows = q(conn, """SELECT id::text AS supplier_id, external_vendor_id AS code, name, category, contact_name, phone, contact_email,
                             address, payment_terms, tax_id, status FROM suppliers ORDER BY lower(name)""")
    for r in rows:
        r["balance"] = owed.get(r["supplier_id"], ZERO)
    return {"title": "Vendor List / Master File", "subtitle": f"Balances as of {p['as_of']}",
            "columns": [C("code", "Vendor ID"), C("name", "Name", link="supplier", id_field="supplier_id"), C("category", "Category"),
                        C("contact_name", "Contact"), C("phone", "Phone"), C("contact_email", "Email"), C("payment_terms", "Terms"),
                        C("tax_id", "TIN"), C("balance", "Balance owed", "money", link="supplier", id_field="supplier_id")],
            "rows": rows, "totals": _tot(rows, "balance")}


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------

@report("item-costing")
def item_costing(conn, e, p):
    sf = " AND t.sku=%s" if p.get("sku") else ""
    prm: List[Any] = [e, p["from"], p["to"]] + ([p["sku"]] if p.get("sku") else [])
    rows = q(conn, f"""SELECT t.id, t.txn_date, t.sku, pr.name AS product, t.txn_type, t.reference, t.source_type, t.source_id,
                              b.id AS batch_id, b.batch_number, t.quantity, t.unit_cost, t.total_cost,
                              COALESCE(c.name, s.name) AS party, t.customer_id, t.supplier_id::text AS supplier_id, t.journal_id, j.journal_number
                       FROM fin_inventory_transactions t LEFT JOIN fin_batches b ON b.id=t.batch_id
                       LEFT JOIN fin_products pr ON pr.legal_entity_id=t.legal_entity_id AND pr.sku=t.sku
                       LEFT JOIN fin_v_customers c ON c.id=t.customer_id LEFT JOIN suppliers s ON s.id=t.supplier_id
                       LEFT JOIN fin_journals j ON j.id=t.journal_id
                       WHERE t.legal_entity_id=%s AND t.txn_date BETWEEN %s AND %s {sf}
                       ORDER BY t.sku, t.txn_date, t.created_at""", prm)
    for r in rows:
        r["txn_type"] = r["txn_type"].replace("_", " ").title()
    return {"title": "Item Costing Report", "subtitle": f"{p['from']} to {p['to']} - every stock movement at cost",
            "columns": [C("txn_date", "Date", "date"), C("sku", "Item ID", link="product", id_field="sku"), C("txn_type", "Type"),
                        C("reference", "Reference", link="source", id_field="source_id"), C("party", "Customer / vendor"),
                        C("batch_number", "Batch", link="batch", id_field="batch_id"), C("quantity", "Qty", "qty"),
                        C("unit_cost", "Unit cost", "money"), C("total_cost", "Cost", "money"),
                        C("journal_number", "Journal", link="journal", id_field="journal_id")],
            "rows": rows, "totals": _tot(rows, "total_cost")}


@report("item-master")
def item_master(conn, e, p):
    rows = q(conn, """SELECT p.sku, p.name, p.product_type, p.uom, p.standard_price, p.reorder_level, p.status, p.legacy_class,
                             ra.code AS sales_gl, ia.code AS inventory_gl, ca.code AS cogs_gl,
                             COALESCE(SUM(l.qty_remaining),0) AS on_hand, COALESCE(SUM(l.qty_remaining*l.unit_cost),0) AS value
                      FROM fin_products p LEFT JOIN fin_accounts ra ON ra.id=p.revenue_account_id
                      LEFT JOIN fin_accounts ia ON ia.id=p.inventory_account_id LEFT JOIN fin_accounts ca ON ca.id=p.cogs_account_id
                      LEFT JOIN fin_cost_layers l ON l.legal_entity_id=p.legal_entity_id AND l.sku=p.sku
                      WHERE p.legal_entity_id=%s GROUP BY p.id, ra.code, ia.code, ca.code ORDER BY p.sku""", (e,))
    return {"title": "Item Master List / Price List", "subtitle": "Products with their GL accounts, price and stock",
            "columns": [C("sku", "Item ID", link="product", id_field="sku"), C("name", "Description"), C("product_type", "Type"),
                        C("uom", "UoM"), C("standard_price", "Sales price", "money"), C("reorder_level", "Reorder at", "qty"),
                        C("on_hand", "On hand", "qty"), C("value", "Value", "money"), C("sales_gl", "Sales GL"),
                        C("inventory_gl", "Inventory GL"), C("cogs_gl", "COGS GL"), C("status", "Status")],
            "rows": rows, "totals": _tot(rows, "value")}


@report("inventory-profitability")
def inventory_profitability(conn, e, p):
    rows = q(conn, """SELECT l.sku, pr.name AS product, SUM(l.quantity) AS units, SUM(l.line_total) AS sales,
                             COALESCE(SUM(l.cost_amount),0) AS cost, SUM(l.line_total) - COALESCE(SUM(l.cost_amount),0) AS margin,
                             COUNT(DISTINCT i.customer_id) AS customers
                      FROM fin_sales_invoice_lines l JOIN fin_sales_invoices i ON i.id=l.invoice_id
                      LEFT JOIN fin_products pr ON pr.legal_entity_id=i.legal_entity_id AND pr.sku=l.sku
                      WHERE i.legal_entity_id=%s AND l.sku IS NOT NULL AND i.status NOT IN ('DRAFT','VOID') AND NOT i.is_opening
                        AND i.invoice_date BETWEEN %s AND %s GROUP BY l.sku, pr.name ORDER BY lower(pr.name)""", (e, p["from"], p["to"]))
    for r in rows:
        r["margin_pct"] = (money(r["margin"]) / money(r["sales"]) * 100).quantize(Decimal("0.1")) if money(r["sales"]) else None
    return {"title": "Inventory Profitability", "subtitle": f"{p['from']} to {p['to']} - margin per item",
            "columns": [C("sku", "Item ID", link="product", id_field="sku"), C("product", "Description"), C("units", "Units sold", "qty"),
                        C("customers", "Customers", "qty"), C("sales", "Sales", "money"), C("cost", "Cost", "money"),
                        C("margin", "Margin", "money"), C("margin_pct", "Margin %", "qty")],
            "rows": rows, "totals": _tot(rows, "sales", "cost", "margin")}


@report("reorder-worksheet")
def reorder_worksheet(conn, e, p):
    rows = [r for r in reports.stock_status(conn, e) if r["reorder_level"] is not None and money(r["on_hand"]) <= money(r["reorder_level"])]
    for r in rows:
        r["shortfall"] = money(r["reorder_level"]) - money(r["on_hand"])
    return {"title": "Inventory Reorder Worksheet", "subtitle": "Items at or below their reorder level",
            "columns": [C("sku", "Item ID", link="product", id_field="sku"), C("name", "Description"), C("on_hand", "On hand", "qty"),
                        C("reorder_level", "Reorder at", "qty"), C("shortfall", "Shortfall", "qty"), C("nearest_expiry", "Nearest expiry", "date")],
            "rows": rows}


@report("physical-inventory-list")
def physical_inventory_list(conn, e, p):
    rows = q(conn, """SELECT l.sku, pr.name AS product, b.id AS batch_id, b.batch_number, b.expiry_date, SUM(l.qty_remaining) AS system_qty
                      FROM fin_cost_layers l LEFT JOIN fin_batches b ON b.id=l.batch_id
                      LEFT JOIN fin_products pr ON pr.legal_entity_id=l.legal_entity_id AND pr.sku=l.sku
                      WHERE l.legal_entity_id=%s GROUP BY l.sku, pr.name, b.id HAVING SUM(l.qty_remaining) <> 0
                      ORDER BY l.sku, b.expiry_date""", (e,))
    for r in rows:
        r["counted"] = None
    return {"title": "Physical Inventory List", "subtitle": "Count sheet - print or download and fill in the counted column",
            "columns": [C("sku", "Item ID", link="product", id_field="sku"), C("product", "Description"),
                        C("batch_number", "Batch", link="batch", id_field="batch_id"), C("expiry_date", "Expiry", "date"),
                        C("system_qty", "System qty", "qty"), C("counted", "Counted", "qty")],
            "rows": rows}


# ---------------------------------------------------------------------------
# Account reconciliation
# ---------------------------------------------------------------------------

@report("outstanding-items")
def outstanding_items(conn, e, p):
    af = " AND b.id=%s" if p.get("bank_account_id") else ""
    prm: List[Any] = [e, p["as_of"]] + ([p["bank_account_id"]] if p.get("bank_account_id") else [])
    rows = q(conn, f"""SELECT b.name AS bank, g.journal_date, g.journal_number, g.journal_id, g.source_type, g.source_id, g.source_ref,
                              COALESCE(g.description, g.journal_description) AS description,
                              CASE WHEN g.debit > 0 THEN 'Deposit in transit' ELSE 'Outstanding payment' END AS kind,
                              g.debit - g.credit AS amount, (%s::date - g.journal_date) AS days
                       FROM fin_v_general_ledger g JOIN fin_bank_accounts b ON b.gl_account_id=g.account_id
                       WHERE g.legal_entity_id=%s AND g.journal_date <= %s AND g.journal_type <> 'OPENING' {af}
                         AND NOT EXISTS (SELECT 1 FROM fin_cleared_lines c WHERE c.journal_line_id=g.line_id)
                       ORDER BY b.name, g.journal_date""", [p["as_of"]] + prm)
    return {"title": "Outstanding Items (Deposits in Transit / Outstanding Payments)", "subtitle": f"Uncleared bank entries as of {p['as_of']}",
            "columns": [C("bank", "Bank account"), C("journal_date", "Date", "date"), C("kind", "Kind"),
                        C("source_ref", "Reference", link="source", id_field="source_id"), C("description", "Description"),
                        C("amount", "Amount", "money"), C("days", "Days outstanding", "qty"),
                        C("journal_number", "Journal", link="journal", id_field="journal_id")],
            "rows": rows, "totals": _tot(rows, "amount")}


@report("reconciliation-history")
def reconciliation_history(conn, e, p):
    rows = q(conn, """SELECT r.reconciliation_number, b.name AS bank, r.as_of, r.statement_balance, r.book_balance, r.cleared_balance,
                             r.difference, r.status, r.completed_by, r.completed_at::date AS completed
                      FROM fin_reconciliations r JOIN fin_bank_accounts b ON b.id=r.bank_account_id
                      WHERE r.legal_entity_id=%s ORDER BY r.as_of DESC""", (e,))
    return {"title": "Account Reconciliation History", "subtitle": "Completed bank reconciliations",
            "columns": [C("reconciliation_number", "Number"), C("bank", "Bank account"), C("as_of", "Statement date", "date"),
                        C("statement_balance", "Statement balance", "money"), C("book_balance", "Book balance", "money"),
                        C("difference", "Difference", "money"), C("completed_by", "By"), C("completed", "Completed", "date")],
            "rows": rows}


# ---------------------------------------------------------------------------
# Company
# ---------------------------------------------------------------------------

@report("audit-trail")
def audit_trail(conn, e, p):
    rows = q(conn, """SELECT created_at, actor_name, action, entity_type, entity_ref, entity_id, reason
                      FROM fin_audit_events WHERE legal_entity_id=%s AND created_at::date BETWEEN %s AND %s
                      ORDER BY id DESC LIMIT 20000""", (e, p["from"], p["to"]))
    for r in rows:
        r["action"] = r["action"].replace("_", " ").lower()
        r["entity_type"] = (r["entity_type"] or "").replace("_", " ")
        r["link_type"] = {"journal": "journal", "sales invoice": "invoice", "supplier bill": "bill"}.get(r["entity_type"])
    return {"title": "Audit Trail Report", "subtitle": f"{p['from']} to {p['to']} - who did what, when",
            "columns": [C("created_at", "When", "datetime"), C("actor_name", "User"), C("action", "Action"), C("entity_type", "Record"),
                        C("entity_ref", "Reference"), C("reason", "Reason")],
            "rows": rows}


# ---------------------------------------------------------------------------
# Financial statements (tabular variants)
# ---------------------------------------------------------------------------

@report("income-12-period")
def income_12_period(conn, e, p):
    """Income statement month by month (Sage 'Income - 12 Period')."""
    rows = q(conn, """SELECT a.id AS account_id, a.code, a.name, a.account_type, a.subtype, to_char(g.journal_date,'YYYY-MM') AS m,
                             SUM(CASE WHEN a.account_type='REVENUE' THEN g.credit-g.debit ELSE g.debit-g.credit END) AS v
                      FROM fin_v_ledger g JOIN fin_accounts a ON a.id=g.account_id
                      WHERE g.legal_entity_id=%s AND g.journal_date BETWEEN %s AND %s AND a.account_type IN ('REVENUE','EXPENSE')
                        AND g.journal_type NOT IN ('OPENING','CLOSING')
                      GROUP BY a.id, a.code, a.name, a.account_type, a.subtype, m ORDER BY a.code""",
             (e, p["from"], p["to"]))
    months: List[str] = []
    d = p["from"].replace(day=1)
    while d <= p["to"]:
        months.append(d.strftime("%Y-%m"))
        d = dt.date(d.year + (d.month == 12), d.month % 12 + 1, 1)
    order = {"SALES": 0, "OTHER_INCOME": 1, "COST_OF_SALES": 2, "OPERATING_EXPENSE": 3, "OTHER_EXPENSE": 4}
    acc: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        a = acc.setdefault(str(r["account_id"]), {"account_id": r["account_id"], "code": r["code"], "name": r["name"],
                                                    "section": r["subtype"].replace("_", " ").title(), "_o": order.get(r["subtype"], 9), "total": ZERO})
        a[r["m"]] = money(r["v"])
        a["total"] += money(r["v"])
    out = sorted(acc.values(), key=lambda x: (x["_o"], x["code"]))
    net = {"code": "", "name": "NET INCOME", "section": "", "total": ZERO}
    for a in out:
        sign = 1 if a["_o"] <= 1 else -1
        for m in months + ["total"]:
            net[m] = net.get(m, ZERO) + sign * money(a.get(m))
    out.append(net)
    return {"title": "Income Statement - 12 Period", "subtitle": f"{p['from']} to {p['to']} month by month (excludes the migrated opening balance)",
            "columns": [C("section", "Section"), C("code", "Account", link="account", id_field="account_id"), C("name", "Description")]
            + [C(m, dt.date(int(m[:4]), int(m[5:]), 1).strftime("%b %Y"), "money", link="account", id_field="account_id") for m in months]
            + [C("total", "Total", "money")],
            "rows": out}


@report("financial-position")
def financial_position(conn, e, p):
    bs = reports.balance_sheet(conn, e, p["as_of"])
    rows = []
    for s in bs["assets"]:
        rows.append({"line": s["title"], "amount": s["total"]})
    rows.append({"line": "TOTAL ASSETS", "amount": bs["total_assets"]})
    for s in bs["liabilities"]:
        rows.append({"line": s["title"], "amount": s["total"]})
    rows.append({"line": "Equity", "amount": bs["total_equity"]})
    rows.append({"line": "TOTAL LIABILITIES & EQUITY", "amount": bs["total_liabilities_and_equity"]})
    return {"title": "Statement of Financial Position (condensed)", "subtitle": f"As of {p['as_of']}",
            "columns": [C("line", "Line"), C("amount", "Amount", "money")], "rows": rows}


# ---------------------------------------------------------------------------
# History-aware reports: Royan's Sage 50 years (2009 -> 2024) and Roy Books
# side by side. Sage rows open their Sage record (voucher / invoice / receipt),
# Roy Books rows their document - one register, full lineage both ways.
# ---------------------------------------------------------------------------

def _years(p) -> List[int]:
    return list(range(p["from"].year, p["to"].year + 1))


@report("sales-history-by-customer")
def sales_history_by_customer(conn, e, p):
    """Every debtor's invoicing and receipts, Sage and Roy Books together (Sage 'Customer Sales History')."""
    cf = " AND x.customer_id=%s" if p.get("customer_id") else ""
    prm = [e, p["from"], p["to"], e, p["from"], p["to"], e, p["from"], p["to"], e, p["from"], p["to"]]
    rows = q(conn, f"""
        SELECT x.customer_id, c.name AS customer, c.party_type, COALESCE(c.customer_code, c.mrn) AS code,
               SUM(x.n_inv) AS invoices, SUM(x.invoiced) AS invoiced, SUM(x.received) AS received,
               MIN(x.d) AS first_date, MAX(x.d) AS last_date
        FROM (
          SELECT customer_id, 1 n_inv, amount invoiced, 0 received, invoice_date d FROM fin_sage_invoices
          WHERE legal_entity_id=%s AND invoice_date BETWEEN %s AND %s
          UNION ALL
          SELECT customer_id, 0, 0, amount, receipt_date FROM fin_sage_receipts WHERE legal_entity_id=%s AND receipt_date BETWEEN %s AND %s
          UNION ALL
          SELECT customer_id, 1, total, 0, invoice_date FROM fin_sales_invoices WHERE legal_entity_id=%s AND NOT is_opening
            AND status NOT IN ('DRAFT','VOID') AND invoice_date BETWEEN %s AND %s
          UNION ALL
          SELECT customer_id, 0, 0, amount + wht_amount, receipt_date FROM fin_customer_receipts WHERE legal_entity_id=%s
            AND status='POSTED' AND receipt_date BETWEEN %s AND %s
        ) x LEFT JOIN fin_v_customers c ON c.id=x.customer_id
        WHERE TRUE {cf}
        GROUP BY x.customer_id, c.name, c.party_type, c.customer_code, c.mrn ORDER BY lower(c.name)""",
             prm + ([int(p["customer_id"])] if p.get("customer_id") else []))
    for r in rows:
        r["customer"] = r["customer"] or "(no debtor matched)"
        r["party_type"] = (r["party_type"] or "").title()
    return {"title": "Sales History by Patient / Payer (Sage + Roy Books)", "subtitle": f"{p['from']} to {p['to']}",
            "columns": [C("customer", "Patient / payer", link="customer", id_field="customer_id"), C("party_type", "Type"), C("code", "Code"),
                        C("invoices", "Invoices", "qty"), C("invoiced", "Invoiced", "money"), C("received", "Received", "money"),
                        C("first_date", "First", "date"), C("last_date", "Last", "date")],
            "rows": rows, "totals": _tot(rows, "invoiced", "received")}


@report("customer-transaction-history")
def customer_transaction_history(conn, e, p):
    """Every invoice, receipt and credit for a debtor, oldest first (Sage 'Customer Transaction History' / 'Customer Ledgers')."""
    if not p.get("customer_id"):
        raise invalid("Choose a patient / payer")
    cid = int(p["customer_id"])
    rows = q(conn, """
        SELECT * FROM (
          SELECT invoice_date AS date, 'Sage invoice' AS type, invoice_number AS number, id::text AS doc_id, 'sageinvoice' AS link,
                 amount AS debit, 0::numeric AS credit FROM fin_sage_invoices WHERE legal_entity_id=%s AND customer_id=%s
          UNION ALL
          SELECT receipt_date, 'Sage receipt', reference, id::text, 'sagereceipt', 0, amount FROM fin_sage_receipts
          WHERE legal_entity_id=%s AND customer_id=%s
          UNION ALL
          SELECT invoice_date, 'Invoice', invoice_number, id::text, 'invoice', total, 0 FROM fin_sales_invoices
          WHERE legal_entity_id=%s AND customer_id=%s AND status <> 'DRAFT'
          UNION ALL
          SELECT receipt_date, 'Receipt', receipt_number, id::text, 'receipt', 0, amount + wht_amount FROM fin_customer_receipts
          WHERE legal_entity_id=%s AND customer_id=%s AND status='POSTED'
          UNION ALL
          SELECT note_date, 'Credit note', credit_note_number, id::text, 'creditnote', 0, total FROM fin_credit_notes
          WHERE legal_entity_id=%s AND customer_id=%s AND status='POSTED'
          UNION ALL
          SELECT refund_date, 'Refund', refund_number, id::text, 'refund', amount, 0 FROM fin_customer_refunds
          WHERE legal_entity_id=%s AND customer_id=%s AND status='POSTED'
        ) x WHERE x.date BETWEEN %s AND %s ORDER BY x.date, x.number""", (e, cid) * 6 + (p["from"], p["to"]))
    bal = ZERO
    for r in rows:
        bal += money(r["debit"]) - money(r["credit"])
        r["balance"] = bal
    c = q1(conn, "SELECT name FROM fin_v_customers WHERE id=%s", (cid,))
    return {"title": f"Transaction History — {c['name'] if c else cid}", "subtitle": f"{p['from']} to {p['to']} · Sage history and Roy Books",
            "columns": [C("date", "Date", "date"), C("type", "Type"), C("number", "Document", link="doc", id_field="doc_id"),
                        C("debit", "Charged", "money"), C("credit", "Paid / credited", "money"), C("balance", "Running balance", "money")],
            "rows": rows, "totals": _tot(rows, "debit", "credit")}


@report("sage-invoice-register")
def sage_invoice_register(conn, e, p):
    cf = " AND i.customer_id=%s" if p.get("customer_id") else ""
    rows = q(conn, f"""SELECT i.id, i.invoice_number, i.invoice_date, i.customer_name, i.customer_id, i.amount, i.amount_received,
                              i.amount - i.amount_received AS unmatched
                       FROM fin_sage_invoices i WHERE i.legal_entity_id=%s AND i.invoice_date BETWEEN %s AND %s {cf}
                       ORDER BY i.invoice_date, i.row_no""", [e, p["from"], p["to"]] + ([int(p["customer_id"])] if p.get("customer_id") else []))
    return {"title": "Invoice Register (Sage 2010–2024)", "subtitle": f"{p['from']} to {p['to']} · received = matched in Sage's cash receipts",
            "columns": [C("invoice_number", "Invoice/CM #", link="sageinvoice", id_field="id"), C("invoice_date", "Date", "date"),
                        C("customer_name", "Name", link="customer", id_field="customer_id"), C("amount", "Amount", "money"),
                        C("amount_received", "Received", "money"), C("unmatched", "Not matched to a receipt", "money")],
            "rows": rows, "totals": _tot(rows, "amount", "amount_received", "unmatched")}


@report("sage-receipts-register")
def sage_receipts_register(conn, e, p):
    cf = " AND r.customer_id=%s" if p.get("customer_id") else ""
    bf = " AND b.id=%s" if p.get("bank_account_id") else ""
    prm: List[Any] = [e, p["from"], p["to"]] + ([int(p["customer_id"])] if p.get("customer_id") else []) + \
        ([p["bank_account_id"]] if p.get("bank_account_id") else [])
    rows = q(conn, f"""SELECT r.id, r.reference, r.receipt_date, r.payer, r.customer_id, a.id AS account_id, a.code || ' ' || a.name AS account,
                              r.amount, (SELECT string_agg(ri.invoice_number, ', ') FROM fin_sage_receipt_invoices ri WHERE ri.receipt_id=r.id) AS invoices
                       FROM fin_sage_receipts r LEFT JOIN fin_accounts a ON a.id=r.bank_account_id
                       LEFT JOIN fin_bank_accounts b ON b.gl_account_id=a.id
                       WHERE r.legal_entity_id=%s AND r.receipt_date BETWEEN %s AND %s {cf} {bf} ORDER BY r.receipt_date, r.row_no""", prm)
    return {"title": "Cash Receipts (Sage 2010–2024)", "subtitle": f"{p['from']} to {p['to']}",
            "columns": [C("reference", "Reference", link="sagereceipt", id_field="id"), C("receipt_date", "Date", "date"),
                        C("payer", "Received from", link="customer", id_field="customer_id"), C("account", "Into", link="account", id_field="account_id"),
                        C("invoices", "Invoices settled"), C("amount", "Amount", "money")],
            "rows": rows, "totals": _tot(rows, "amount")}


@report("collections-by-payer-type")
def collections_by_payer_type(conn, e, p):
    """Money received per month split by who paid: HMOs, private patients, sundries / walk-in, corporates."""
    rows = q(conn, """SELECT to_char(date_trunc('month', x.d), 'YYYY-MM') AS month,
                             SUM(x.amt) FILTER (WHERE c.party_type='HMO') AS hmo,
                             SUM(x.amt) FILTER (WHERE c.party_type='PATIENT' OR (c.party_type='OTHER' AND COALESCE(c.customer_code,'') NOT LIKE 'SD/%%')) AS private,
                             SUM(x.amt) FILTER (WHERE c.party_type='OTHER' AND c.customer_code LIKE 'SD/%%') AS sundries,
                             SUM(x.amt) FILTER (WHERE c.party_type='CORPORATE') AS corporate,
                             SUM(x.amt) FILTER (WHERE c.id IS NULL) AS unmatched, SUM(x.amt) AS total
                      FROM (SELECT customer_id, receipt_date d, amount amt FROM fin_sage_receipts WHERE legal_entity_id=%s
                            UNION ALL SELECT customer_id, receipt_date, amount + wht_amount FROM fin_customer_receipts
                            WHERE legal_entity_id=%s AND status='POSTED') x
                      LEFT JOIN fin_v_customers c ON c.id=x.customer_id
                      WHERE x.d BETWEEN %s AND %s GROUP BY 1 ORDER BY 1""", (e, e, p["from"], p["to"]))
    return {"title": "Collections by Payer Type", "subtitle": f"{p['from']} to {p['to']} · Sage history and Roy Books",
            "columns": [C("month", "Month"), C("hmo", "HMOs", "money"), C("private", "Private patients", "money"),
                        C("sundries", "Sundries / walk-in", "money"), C("corporate", "Corporates", "money"),
                        C("unmatched", "Unmatched", "money"), C("total", "Total", "money")],
            "rows": rows, "totals": _tot(rows, "hmo", "private", "sundries", "corporate", "unmatched", "total")}


@report("income-by-year")
def income_by_year(conn, e, p):
    """Income statement, one column per year (Sage 'Income 2 yrs' / 'Stmt Rev & Expenditure', any span)."""
    years = _years(p)
    rows = q(conn, """SELECT a.id AS account_id, a.code, a.name, a.account_type, a.subtype, extract(year FROM g.journal_date)::int AS y,
                             SUM(CASE WHEN a.account_type='REVENUE' THEN g.credit-g.debit ELSE g.debit-g.credit END) AS v
                      FROM fin_v_ledger g JOIN fin_accounts a ON a.id=g.account_id
                      WHERE g.legal_entity_id=%s AND g.journal_date BETWEEN %s AND %s AND a.account_type IN ('REVENUE','EXPENSE')
                        AND g.journal_type NOT IN ('CLOSING')
                      GROUP BY 1,2,3,4,5,6""", (e, p["from"], p["to"]))
    acc: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        a = acc.setdefault(str(r["account_id"]), {"account_id": r["account_id"], "code": r["code"], "name": r["name"],
                                                  "group": "Revenue" if r["account_type"] == "REVENUE" else
                                                  ("Cost of sales" if r["subtype"] == "COST_OF_SALES" else "Expenses")})
        a[f"y{r['y']}"] = money(r["v"])
    out = sorted(acc.values(), key=lambda a: ({"Revenue": 0, "Cost of sales": 1, "Expenses": 2}[a["group"]], a["code"]))
    for grp in ("Revenue", "Cost of sales", "Expenses"):
        out.append({"code": "", "name": f"Total {grp.lower()}", "group": grp,
                    **{f"y{y}": sum((a.get(f"y{y}", ZERO) for a in acc.values() if a["group"] == grp), ZERO) for y in years}})
    net = {"code": "", "name": "NET INCOME", "group": ""}
    for y in years:
        net[f"y{y}"] = sum((a.get(f"y{y}", ZERO) * (1 if a["group"] == "Revenue" else -1) for a in acc.values()), ZERO)
    out.append(net)
    return {"title": "Income Statement by Year", "subtitle": f"{years[0]}–{years[-1]} · Sage history and Roy Books",
            "columns": [C("code", "Account", link="account", id_field="account_id"), C("name", "Description"), C("group", "Section")]
                       + [C(f"y{y}", str(y), "money") for y in years],
            "rows": out}


@report("transaction-detail")
def transaction_detail(conn, e, p):
    """Find any ledger line - Sage or Roy Books - by text, reference or amount (Sage 'Transaction Detail Report')."""
    s = (p.get("search") or "").strip()
    if len(s) < 2:
        raise invalid("Type at least two characters to search (a name, reference, description or amount)")
    amt = None
    try:
        amt = money(s.replace(",", ""))
    except ValueError:
        pass
    rows = q(conn, """SELECT g.journal_date, g.journal_number, g.source_type, g.source_id, g.source_ref, g.account_id,
                             g.account_code || ' ' || g.account_name AS account, COALESCE(g.description, g.journal_description) AS description,
                             g.debit, g.credit, g.origin
                      FROM fin_v_ledger g WHERE g.legal_entity_id=%s AND g.journal_date BETWEEN %s AND %s
                        AND (g.description ILIKE %s OR g.source_ref ILIKE %s OR g.journal_description ILIKE %s
                             OR (%s::numeric IS NOT NULL AND (g.debit=%s::numeric OR g.credit=%s::numeric)))
                      ORDER BY g.journal_date DESC LIMIT 2000""",
             (e, p["from"], p["to"], f"%{s}%", f"%{s}%", f"%{s}%", amt, amt, amt))
    for r in rows:
        r["origin"] = "Sage" if r["origin"] == "SAGE" else "Roy Books"
    return {"title": "Transaction Detail", "subtitle": f"'{s}' · {p['from']} to {p['to']} · first 2,000 matches",
            "columns": [C("journal_date", "Date", "date"), C("origin", "Source"), C("journal_number", "Journal", link="source", id_field="source_id"),
                        C("account", "Account", link="account", id_field="account_id"), C("description", "Description"),
                        C("debit", "Debit", "money"), C("credit", "Credit", "money")],
            "rows": rows, "totals": _tot(rows, "debit", "credit")}


@report("payments-by-payee")
def payments_by_payee(conn, e, p):
    """Who the hospital paid, from the Sage cash disbursements journal and Roy Books payments / vouchers."""
    rows = q(conn, """SELECT payee, COUNT(*) AS payments, SUM(amt) AS total, MAX(d) AS last_date, MIN(d) AS first_date,
                             (array_agg(account ORDER BY amt DESC))[1] AS main_account
                      FROM (SELECT l.description AS payee, l.credit AS amt, l.txn_date d, NULL::text AS account
                            FROM fin_sage_gl_lines l JOIN fin_accounts a ON a.id=l.account_id
                            WHERE l.legal_entity_id=%s AND l.jrnl='CDJ' AND a.subtype='CASH' AND l.credit > 0
                            UNION ALL
                            SELECT s.name, p.amount, p.payment_date, NULL FROM fin_supplier_payments p JOIN suppliers s ON s.id=p.supplier_id
                            WHERE p.legal_entity_id=%s AND p.status='POSTED'
                            UNION ALL
                            SELECT COALESCE(v.payee, v.description), v.amount, v.voucher_date, NULL FROM fin_cash_vouchers v
                            WHERE v.legal_entity_id=%s AND v.status='POSTED' AND v.kind='SPEND') x
                      WHERE d BETWEEN %s AND %s AND payee IS NOT NULL AND payee <> ''
                      GROUP BY payee ORDER BY total DESC LIMIT 2000""", (e, e, e, p["from"], p["to"]))
    return {"title": "Payments by Payee (Cash Disbursements)", "subtitle": f"{p['from']} to {p['to']} · Sage CDJ and Roy Books",
            "columns": [C("payee", "Paid to"), C("payments", "Payments", "qty"), C("total", "Total paid", "money"),
                        C("first_date", "First", "date"), C("last_date", "Last", "date")],
            "rows": rows, "totals": _tot(rows, "total")}


@report("expense-analysis")
def expense_analysis(conn, e, p):
    """Expense and cost-of-sales accounts, one column per year, with the change on the prior year."""
    data = income_by_year(conn, e, p)
    rows = [r for r in data["rows"] if r.get("group") in ("Cost of sales", "Expenses")]
    years = _years(p)
    if len(years) >= 2:
        for r in rows:
            r["change"] = money(r.get(f"y{years[-1]}", ZERO)) - money(r.get(f"y{years[-2]}", ZERO))
    cols = data["columns"] + ([C("change", f"Change {years[-1]} vs {years[-2]}", "money")] if len(years) >= 2 else [])
    return {"title": "Expense Analysis by Year", "subtitle": data["subtitle"], "columns": cols, "rows": rows}


@report("bank-deposit-report")
def bank_deposit_report(conn, e, p):
    """Money lodged per bank / cash account per day (Sage 'Bank Deposit Report')."""
    rows = q(conn, """SELECT x.d AS date, a.id AS account_id, a.code || ' ' || a.name AS account, COUNT(*) AS receipts, SUM(x.amt) AS amount
                      FROM (SELECT bank_account_id AS acct, receipt_date d, amount amt FROM fin_sage_receipts WHERE legal_entity_id=%s
                            UNION ALL SELECT b.gl_account_id, r.receipt_date, r.amount FROM fin_customer_receipts r
                            JOIN fin_bank_accounts b ON b.id=r.bank_account_id WHERE r.legal_entity_id=%s AND r.status='POSTED') x
                      JOIN fin_accounts a ON a.id=x.acct WHERE x.d BETWEEN %s AND %s
                      GROUP BY 1,2,3 ORDER BY 1 DESC, 3""", (e, e, p["from"], p["to"]))
    return {"title": "Bank Deposit Report", "subtitle": f"{p['from']} to {p['to']} · Sage history and Roy Books",
            "columns": [C("date", "Date", "date"), C("account", "Account", link="account", id_field="account_id"),
                        C("receipts", "Receipts", "qty"), C("amount", "Deposited", "money")],
            "rows": rows, "totals": _tot(rows, "amount")}


@report("sage-reconciliation")
def sage_reconciliation(conn, e, p):
    """The open items of Royan's last Sage bank reconciliation - the baseline Roy Books reconciles from."""
    rows = q(conn, """SELECT i.item_date, i.section, i.reference, i.amount, a.id AS account_id, a.code || ' ' || a.name AS account
                      FROM fin_sage_recon_items i LEFT JOIN fin_accounts a ON a.legal_entity_id=i.legal_entity_id AND a.code=i.account_code
                      WHERE i.legal_entity_id=%s ORDER BY i.section, i.item_date""", (e,))
    label = {"DEPOSIT_IN_TRANSIT": "Deposit in transit", "OUTSTANDING_CHECK": "Outstanding cheque", "OTHER": "Other outstanding item"}
    for r in rows:
        r["section"] = label.get(r["section"], r["section"])
    return {"title": "Sage Bank Reconciliation — open items at 31 Dec 2024",
            "subtitle": "Deposits in transit, outstanding cheques and other items Sage never cleared",
            "columns": [C("account", "Bank account", link="account", id_field="account_id"), C("section", "Kind"),
                        C("item_date", "Date", "date"), C("reference", "Reference"), C("amount", "Amount", "money")],
            "rows": rows, "totals": _tot(rows, "amount")}


@report("sage-delivered")
def sage_delivered(conn, e, p):
    """A Sage report exactly as Royan's accountant exported it (for tie-out and audit)."""
    name = p.get("name") or "balance-sheet"
    r = q1(conn, "SELECT * FROM fin_sage_reports WHERE legal_entity_id=%s AND report_key=%s", (e, name))
    if not r:
        raise invalid(f"Sage report {name} is not loaded")
    cols = r["columns"] if r["columns"] and len(r["columns"]) >= max((len(x) for x in r["rows"]), default=0) else \
        [f"Column {i + 1}" for i in range(max((len(x) for x in r["rows"]), default=0))]
    rows = [{f"c{i}": v for i, v in enumerate(row)} for row in r["rows"]]
    return {"title": f"{r['title']} (Sage, as delivered)", "subtitle": f"{r['file_name']} · as at {r['as_of']}",
            "columns": [C(f"c{i}", str(c) or f"Column {i + 1}") for i, c in enumerate(cols)], "rows": rows}


@report("sage-tie-out")
def sage_tie_out(conn, e, p):
    """Every account: Sage's trial balance at 31 Dec 2024 against Roy Books (computed from the history)."""
    tb = q1(conn, "SELECT rows FROM fin_sage_reports WHERE legal_entity_id=%s AND report_key='trial-balance'", (e,))
    sage: Dict[str, Decimal] = {}
    for r in (tb["rows"] if tb else []):
        if r and r[0] and re.match(r"^[\w.\-]+$", str(r[0])):
            sage[str(r[0])] = money(r[2] or 0) - money(r[3] or 0)
    roy = {r["code"]: r for r in q(conn, """
        SELECT a.id AS account_id, a.code, a.name, a.account_type, a.subtype,
               COALESCE(SUM(g.debit-g.credit),0) AS cumulative,
               COALESCE(SUM(g.debit-g.credit) FILTER (WHERE g.journal_date >= '2024-01-01'),0) AS ytd
        FROM fin_accounts a LEFT JOIN fin_v_ledger g ON g.account_id=a.id AND g.journal_date <= '2024-12-31'
        WHERE a.legal_entity_id=%s GROUP BY a.id""", (e,))}
    prior_pl = sum((money(r["cumulative"]) - money(r["ytd"]) for r in roy.values() if r["account_type"] in ("REVENUE", "EXPENSE")), ZERO)
    rows = []
    for code in sorted(set(sage) | {c for c, r in roy.items() if money(r["cumulative"])}):
        r = roy.get(code)
        if not r:
            continue
        if r["account_type"] in ("REVENUE", "EXPENSE"):
            mine, basis = money(r["ytd"]), "2024 activity"
        elif r["subtype"] == "RETAINED_EARNINGS":
            mine, basis = money(r["cumulative"]) + prior_pl, "lines + prior years' profit (Sage closes it internally)"
        elif r["subtype"] == "EQUITY_CLOSING":
            mine, basis = ZERO, "closed into retained earnings at each year end"
        else:
            mine, basis = money(r["cumulative"]), "cumulative 2009–2024"
        if r["subtype"] == "RETAINED_EARNINGS":
            mine += sum((money(x["cumulative"]) for x in roy.values() if x["subtype"] == "EQUITY_CLOSING"), ZERO)
        s = sage.get(code, ZERO)
        rows.append({"account_id": r["account_id"], "code": code, "name": r["name"], "sage": s, "roy": mine, "difference": mine - s,
                     "basis": basis})
    return {"title": "Tie-out: Sage Trial Balance vs Roy Books (31 Dec 2024)",
            "subtitle": "Roy Books figures are computed from the 2009–2024 Sage history it holds; a zero difference means every kobo is accounted for",
            "columns": [C("code", "Account", link="account", id_field="account_id"), C("name", "Description"), C("sage", "Sage TB", "money"),
                        C("roy", "Roy Books", "money"), C("difference", "Difference", "money"), C("basis", "Basis")],
            "rows": rows, "totals": _tot(rows, "sage", "roy", "difference")}


@report("contact-list")
def contact_list(conn, e, p):
    rows = q(conn, """SELECT c.id AS customer_id, c.name, initcap(c.party_type) AS type, COALESCE(c.customer_code, c.mrn) AS code,
                             c.contact_details->>'phone' AS phone, c.contact_details->>'email' AS email,
                             (SELECT string_agg(DISTINCT s.contact, ', ') FROM fin_sage_customers s WHERE s.customer_id=c.id) AS contact,
                             (SELECT string_agg(DISTINCT s.sage_code, ', ') FROM fin_sage_customers s WHERE s.customer_id=c.id) AS sage_codes
                      FROM fin_v_customers c WHERE c.party_type <> 'PATIENT' OR EXISTS (SELECT 1 FROM fin_sales_invoices i WHERE i.customer_id=c.id)
                      ORDER BY c.party_type, lower(c.name)""")
    return {"title": "Contact List (patients, HMOs and corporates with accounts)", "subtitle": "Contacts from the hospital registers and Sage",
            "columns": [C("name", "Name", link="customer", id_field="customer_id"), C("type", "Type"), C("code", "Code"),
                        C("contact", "Contact"), C("phone", "Phone"), C("email", "Email"), C("sage_codes", "Sage IDs")],
            "rows": rows}


@report("customer-management-detail")
def customer_management_detail(conn, e, p):
    """Open invoices that are due, with each debtor's limit and balance (Sage 'Customer Management Detail')."""
    items = reports.ar_open_items(conn, e, p["as_of"])
    names = {r["id"]: r for r in q(conn, "SELECT id, name, party_type, credit_limit, payment_terms_days FROM fin_v_customers")}
    rows = []
    for it in items:
        c = names.get(it["customer_id"], {})
        rows.append({"customer_id": it["customer_id"], "customer": c.get("name"), "type": (c.get("party_type") or "").title(),
                     "doc": it["doc_number"], "doc_id": it["doc_id"], "link": {"INVOICE": "invoice", "RECEIPT": "receipt",
                                                                              "CREDIT_NOTE": "creditnote"}[it["doc_type"]],
                     "date": it["doc_date"], "due": it["due_date"], "days_overdue": max((p["as_of"] - it["due_date"]).days, 0),
                     "open": it["open_amount"], "credit_limit": c.get("credit_limit"), "terms": c.get("payment_terms_days")})
    rows.sort(key=lambda r: (str(r["customer"]), r["due"]))
    return {"title": "Customer Management Detail (open items)", "subtitle": f"As of {p['as_of']}",
            "columns": [C("customer", "Patient / payer", link="customer", id_field="customer_id"), C("type", "Type"),
                        C("doc", "Document", link="doc", id_field="doc_id"), C("date", "Date", "date"), C("due", "Due", "date"),
                        C("days_overdue", "Days overdue", "qty"), C("open", "Open", "money"), C("credit_limit", "Credit limit", "money"),
                        C("terms", "Terms (days)", "qty")],
            "rows": rows, "totals": _tot(rows, "open")}


@report("purchase-order-history")
def purchase_order_history(conn, e, p):
    """Goods received against purchase orders before Roy Books (Hope POs; Royan's Sage kept no purchase orders)."""
    sf = " AND h.supplier_id=%s" if p.get("supplier_id") else ""
    rows = q(conn, f"""SELECT h.po_number, MIN(h.received_date) AS received, h.supplier_id, MAX(h.supplier_name) AS supplier,
                              COUNT(*) AS lines, string_agg(DISTINCT h.grn_number, ', ') AS grn, SUM(h.amount) AS value
                       FROM fin_hist_purchase_lines h WHERE h.legal_entity_id=%s AND h.received_date BETWEEN %s AND %s {sf}
                       GROUP BY h.po_number, h.supplier_id ORDER BY received DESC""",
             [e, p["from"], p["to"]] + ([p["supplier_id"]] if p.get("supplier_id") else []))
    return {"title": "Purchase Order Register (Hope, before Roy Books)", "subtitle": f"{p['from']} to {p['to']}",
            "columns": [C("po_number", "PO"), C("received", "Received", "date"), C("supplier", "Supplier", link="supplier", id_field="supplier_id"),
                        C("grn", "GRN"), C("lines", "Lines", "qty"), C("value", "Value", "money")],
            "rows": rows, "totals": _tot(rows, "value")}
