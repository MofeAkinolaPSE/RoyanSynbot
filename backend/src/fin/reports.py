"""Reporting engine - every figure derived from posted journals / subledger
documents, nothing stored (Workflow Map §38). Each row carries the ids the UI
needs to drill down: statement -> account -> GL lines -> journal -> source.

Sign convention for presentation: amounts are shown "natural" -
revenue/liabilities/equity as positive credits, assets/expenses as positive debits.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any, Dict, List, Optional

from src.fin.db import ZERO, money, q, q1, qty

CURRENT_ASSETS = ("CASH", "RECEIVABLE", "INVENTORY", "OTHER_CURRENT_ASSET")
NONCURRENT_ASSETS = ("FIXED_ASSET", "ACCUMULATED_DEPRECIATION", "OTHER_ASSET")
CURRENT_LIABS = ("PAYABLE", "OTHER_CURRENT_LIABILITY")
EQUITY_SUBTYPES = ("EQUITY", "EQUITY_CLOSING", "RETAINED_EARNINGS")


def _balances(conn, entity_id: str, *, date_from: Optional[dt.date] = None, date_to: dt.date,
              exclude_types: tuple = (), extra: str = "", params: Optional[list] = None) -> List[Dict[str, Any]]:
    where = ["g.legal_entity_id=%s", "g.journal_date <= %s"]
    p: List[Any] = [entity_id, date_to]
    if date_from:
        where.append("g.journal_date >= %s")
        p.append(date_from)
    if exclude_types:
        where.append("g.journal_type <> ALL(%s)")
        p.append(list(exclude_types))
    return q(conn, f"""SELECT g.account_id, g.account_code AS code, g.account_name AS name, g.account_type, g.subtype,
                              COALESCE(SUM(g.debit),0) AS debit, COALESCE(SUM(g.credit),0) AS credit
                       FROM fin_v_ledger g WHERE {' AND '.join(where)} {extra}
                       GROUP BY g.account_id, g.account_code, g.account_name, g.account_type, g.subtype
                       ORDER BY g.account_code""", p + (params or []))


def _natural(row: Dict[str, Any]) -> Decimal:
    d, c = money(row["debit"]), money(row["credit"])
    return d - c if row["account_type"] in ("ASSET", "EXPENSE") else c - d


def _section(rows, subtypes, title) -> Dict[str, Any]:
    lines = [{"account_id": r["account_id"], "code": r["code"], "name": r["name"], "subtype": r["subtype"],
              "amount": _natural(r)} for r in rows if r["subtype"] in subtypes and _natural(r) != 0]
    return {"title": title, "lines": lines, "total": sum((l["amount"] for l in lines), ZERO)}


def _fy_start(conn, entity_id: str, on: dt.date) -> dt.date:
    fy = q1(conn, "SELECT start_date FROM fin_fiscal_years WHERE legal_entity_id=%s AND %s BETWEEN start_date AND end_date",
            (entity_id, on))
    return fy["start_date"] if fy else dt.date(on.year, 1, 1)


# ---------------------------------------------------------------------------
# Income statement
# ---------------------------------------------------------------------------

def income_statement(conn, entity_id: str, date_from: dt.date, date_to: dt.date,
                     compare_from: Optional[dt.date] = None, compare_to: Optional[dt.date] = None,
                     budget_id: Optional[str] = None) -> Dict[str, Any]:
    def build(f, t):
        # Migrated opening balances carry the year's result up to cut-over as one
        # journal; they belong in a statement only when it spans the whole
        # fiscal year-to-date, never in a single month's figures.
        excl = ("CLOSING",) if f <= _fy_start(conn, entity_id, t) else ("CLOSING", "OPENING")
        rows = [r for r in _balances(conn, entity_id, date_from=f, date_to=t, exclude_types=excl)
                if r["account_type"] in ("REVENUE", "EXPENSE")]
        sales = _section(rows, ("SALES",), "Revenue")
        cogs = _section(rows, ("COST_OF_SALES",), "Cost of sales")
        opex = _section(rows, ("OPERATING_EXPENSE",), "Operating expenses")
        oinc = _section(rows, ("OTHER_INCOME",), "Other income")
        oexp = _section(rows, ("OTHER_EXPENSE",), "Other expenses")
        gross = sales["total"] - cogs["total"]
        operating = gross - opex["total"]
        net = operating + oinc["total"] - oexp["total"]
        return {"sections": [sales, cogs, opex, oinc, oexp], "revenue": sales["total"], "cost_of_sales": cogs["total"],
                "gross_profit": gross, "gross_margin_pct": (gross / sales["total"] * 100).quantize(Decimal("0.01")) if sales["total"] else None,
                "operating_profit": operating, "net_profit": net}
    out = {"date_from": date_from, "date_to": date_to, **build(date_from, date_to)}
    ytd_from = _fy_start(conn, entity_id, date_to)
    if ytd_from != date_from:
        y = build(ytd_from, date_to)
        out["year_to_date"] = {"date_from": ytd_from, "net_profit": y["net_profit"], "revenue": y["revenue"],
                               "gross_profit": y["gross_profit"]}
    if compare_from and compare_to:
        out["comparison"] = {"date_from": compare_from, "date_to": compare_to, **build(compare_from, compare_to)}
    if budget_id:
        out["budget"] = budget_totals(conn, budget_id, date_from, date_to)
    return out


# ---------------------------------------------------------------------------
# Balance sheet
# ---------------------------------------------------------------------------

def balance_sheet(conn, entity_id: str, as_of: dt.date) -> Dict[str, Any]:
    rows = _balances(conn, entity_id, date_to=as_of)
    ca = _section(rows, CURRENT_ASSETS, "Current assets")
    nca = _section(rows, NONCURRENT_ASSETS, "Non-current assets")
    cl = _section(rows, CURRENT_LIABS, "Current liabilities")
    ltl = _section(rows, ("LONG_TERM_LIABILITY",), "Long-term liabilities")
    eq = _section(rows, EQUITY_SUBTYPES, "Equity")
    # Profit not yet closed to retained earnings is still part of equity. Profit of earlier
    # years that the ledger never closed (Sage closes its years internally, without journal
    # lines) is shown as brought-forward retained earnings, this year's as current earnings.
    fy = _fy_start(conn, entity_id, as_of)
    prior_rows = _balances(conn, entity_id, date_to=fy - dt.timedelta(days=1))

    def _pl(rs):
        return sum((_natural(r) if r["account_type"] == "REVENUE" else -_natural(r)
                    for r in rs if r["account_type"] in ("REVENUE", "EXPENSE")), ZERO)
    total_pl, prior_pl = _pl(rows), _pl(prior_rows)
    # "Equity - gets closed" (Sage): earlier years' balance was closed to retained earnings
    prior_closing = {r["account_id"]: _natural(r) for r in prior_rows if r["subtype"] == "EQUITY_CLOSING"}
    if prior_closing:
        for l in eq["lines"]:
            if l.get("subtype") == "EQUITY_CLOSING":
                l["amount"] -= prior_closing.get(l["account_id"], ZERO)
        eq["lines"] = [l for l in eq["lines"] if l["amount"] != 0]
        prior_pl += sum(prior_closing.values(), ZERO)
        total_pl += sum(prior_closing.values(), ZERO)
        eq["total"] -= sum(prior_closing.values(), ZERO)
    if prior_pl:
        eq["lines"].append({"account_id": None, "code": "", "name": "Retained earnings brought forward (prior years not closed in the ledger)",
                            "amount": prior_pl})
    eq["lines"].append({"account_id": None, "code": "", "name": "Current year earnings (not yet closed)", "amount": total_pl - prior_pl})
    eq["total"] += total_pl
    assets = ca["total"] + nca["total"]
    liab = cl["total"] + ltl["total"]
    return {"as_of": as_of, "assets": [ca, nca], "total_assets": assets, "liabilities": [cl, ltl],
            "total_liabilities": liab, "equity": eq, "total_equity": eq["total"],
            "total_liabilities_and_equity": liab + eq["total"], "balanced": assets == liab + eq["total"],
            "difference": assets - liab - eq["total"]}


# ---------------------------------------------------------------------------
# Cash flow (indirect) and retained earnings
# ---------------------------------------------------------------------------

def cash_flow(conn, entity_id: str, date_from: dt.date, date_to: dt.date) -> Dict[str, Any]:
    """Indirect method. Movements exclude migration (OPENING) and year-end (CLOSING)
    journals, which move balances but not cash. Operating+Investing+Financing
    always equals the change in cash because every journal balances."""
    mv = _balances(conn, entity_id, date_from=date_from, date_to=date_to, exclude_types=("OPENING", "CLOSING"))

    def credit_move(r):  # increase in a credit-natured balance / decrease in a debit one
        return money(r["credit"]) - money(r["debit"])
    net = sum((credit_move(r) for r in mv if r["account_type"] in ("REVENUE", "EXPENSE")), ZERO)

    def group(subtypes, label_prefix):
        lines = [{"account_id": r["account_id"], "code": r["code"], "name": f"{label_prefix}{r['name']}",
                  "amount": credit_move(r)} for r in mv if r["subtype"] in subtypes and credit_move(r) != 0]
        return lines, sum((l["amount"] for l in lines), ZERO)
    dep_lines, dep = group(("ACCUMULATED_DEPRECIATION",), "Depreciation - ")
    wc_lines, wc = group(("RECEIVABLE", "INVENTORY", "OTHER_CURRENT_ASSET", "PAYABLE", "OTHER_CURRENT_LIABILITY"), "Change in ")
    inv_lines, inv = group(("FIXED_ASSET", "OTHER_ASSET"), "")
    fin_lines, fin = group(("LONG_TERM_LIABILITY", "EQUITY", "EQUITY_CLOSING", "RETAINED_EARNINGS"), "")
    operating = net + dep + wc
    change = operating + inv + fin
    cash_open = money(q1(conn, """SELECT COALESCE(SUM(debit-credit),0) b FROM fin_v_ledger
                                  WHERE legal_entity_id=%s AND subtype='CASH'
                                  AND (journal_date < %s OR (journal_type='OPENING' AND journal_date <= %s))""",
                         (entity_id, date_from, date_to))["b"])
    cash_close = money(q1(conn, """SELECT COALESCE(SUM(debit-credit),0) b FROM fin_v_ledger
                                   WHERE legal_entity_id=%s AND subtype='CASH' AND journal_date <= %s""",
                          (entity_id, date_to))["b"])
    return {"date_from": date_from, "date_to": date_to,
            "operating": {"net_profit": net, "adjustments": dep_lines, "working_capital": wc_lines, "total": operating},
            "investing": {"lines": inv_lines, "total": inv}, "financing": {"lines": fin_lines, "total": fin},
            "net_change": change, "opening_cash": cash_open, "closing_cash": cash_close,
            "reconciles": cash_open + change == cash_close}


def retained_earnings(conn, entity_id: str, date_from: dt.date, date_to: dt.date) -> Dict[str, Any]:
    re_rows = q(conn, """SELECT COALESCE(SUM(credit-debit),0) b FROM fin_v_ledger
                         WHERE legal_entity_id=%s AND subtype='RETAINED_EARNINGS' AND journal_date < %s""", (entity_id, date_from))
    # Profit of earlier years still sitting in P&L accounts (never closed in this ledger, e.g. the
    # Sage history) is part of the opening retained earnings.
    unclosed_prior = money(q1(conn, """SELECT COALESCE(SUM(credit-debit),0) b FROM fin_v_ledger WHERE legal_entity_id=%s
                                       AND (account_type IN ('REVENUE','EXPENSE') OR subtype='EQUITY_CLOSING')
                                       AND journal_date < %s""", (entity_id, date_from))["b"])
    opening = money(re_rows[0]["b"]) + unclosed_prior
    closing_entries = money(q1(conn, """SELECT COALESCE(SUM(credit-debit),0) b FROM fin_v_ledger WHERE legal_entity_id=%s
                                        AND subtype='RETAINED_EARNINGS' AND journal_date BETWEEN %s AND %s AND journal_type='CLOSING'""",
                                   (entity_id, date_from, date_to))["b"])
    adjustments = money(q1(conn, """SELECT COALESCE(SUM(credit-debit),0) b FROM fin_v_ledger WHERE legal_entity_id=%s
                                    AND subtype='RETAINED_EARNINGS' AND journal_date BETWEEN %s AND %s AND journal_type<>'CLOSING'""",
                               (entity_id, date_from, date_to))["b"])
    net = income_statement(conn, entity_id, date_from, date_to)["net_profit"]
    # Before the year is closed, the period's profit sits in P&L accounts, not yet in RE.
    unclosed = net - closing_entries if closing_entries == 0 else ZERO
    return {"date_from": date_from, "date_to": date_to, "opening": opening, "adjustments": adjustments,
            "net_profit": net, "closed_to_retained_earnings": closing_entries,
            "closing": opening + adjustments + closing_entries + unclosed}


# ---------------------------------------------------------------------------
# AR / AP aging and statements (open-item subledgers)
# ---------------------------------------------------------------------------

def _buckets(conn, entity_id: str) -> List[int]:
    s = q1(conn, "SELECT aging_buckets FROM fin_settings WHERE legal_entity_id=%s", (entity_id,))
    return list(s["aging_buckets"]) if s else [30, 60, 90, 120]


def _bucket_labels(b: List[int]) -> List[str]:
    labels, lo = [], 0
    for x in b:
        labels.append(f"{lo}-{x}" if lo == 0 else f"{lo + 1}-{x}")
        lo = x
    labels.append(f"Over {b[-1]}")
    return labels


def _age(days: int, b: List[int]) -> int:
    for i, x in enumerate(b):
        if days <= x:
            return i
    return len(b)


def ar_open_items(conn, entity_id: str, as_of: dt.date, customer_id: Optional[int] = None) -> List[Dict[str, Any]]:
    cf = " AND x.customer_id=%s" if customer_id else ""
    p: List[Any] = [as_of, entity_id, as_of, as_of, as_of, as_of, entity_id, as_of, as_of, as_of, entity_id, as_of]
    if customer_id:
        p.append(int(customer_id))
    return q(conn, f"""
        SELECT x.* FROM (
          SELECT 'INVOICE' AS doc_type, i.id AS doc_id, i.invoice_number AS doc_number, i.customer_id, i.invoice_date AS doc_date,
                 i.due_date, i.total - COALESCE((SELECT SUM(a.amount) FROM fin_ar_allocations a WHERE a.invoice_id=i.id
                                                 AND NOT a.reversed AND a.allocation_date <= %s),0) AS open_amount
          FROM fin_sales_invoices i WHERE i.legal_entity_id=%s AND i.invoice_date <= %s AND i.status <> 'DRAFT'
            AND NOT (i.status='VOID' AND COALESCE(i.voided_at::date, i.invoice_date) <= %s)
          UNION ALL
          SELECT 'RECEIPT', r.id, r.receipt_number, r.customer_id, r.receipt_date, r.receipt_date,
                 -(r.amount + r.wht_amount - COALESCE((SELECT SUM(a.amount) FROM fin_ar_allocations a WHERE a.source_type='RECEIPT'
                   AND a.source_id=r.id AND NOT a.reversed AND a.allocation_date <= %s),0)
                   - COALESCE((SELECT SUM(f.amount) FROM fin_customer_refunds f WHERE f.credit_type='RECEIPT'
                   AND f.credit_id=r.id AND f.status='POSTED' AND f.refund_date <= %s),0))
          FROM fin_customer_receipts r WHERE r.legal_entity_id=%s AND r.receipt_date <= %s AND r.status='POSTED'
          UNION ALL
          SELECT 'CREDIT_NOTE', n.id, n.credit_note_number, n.customer_id, n.note_date, n.note_date,
                 -(n.total - COALESCE((SELECT SUM(a.amount) FROM fin_ar_allocations a WHERE a.source_type='CREDIT_NOTE'
                   AND a.source_id=n.id AND NOT a.reversed AND a.allocation_date <= %s),0)
                   - COALESCE((SELECT SUM(f.amount) FROM fin_customer_refunds f WHERE f.credit_type='CREDIT_NOTE'
                   AND f.credit_id=n.id AND f.status='POSTED' AND f.refund_date <= %s),0))
          FROM fin_credit_notes n WHERE n.legal_entity_id=%s AND n.note_date <= %s AND n.status='POSTED'
        ) x WHERE x.open_amount <> 0 {cf}""", p)


def aged_receivables(conn, entity_id: str, as_of: dt.date, basis: str = "due_date",
                     party_type: Optional[str] = None) -> Dict[str, Any]:
    """Aged receivables; `party_type` (PATIENT / HMO / CORPORATE / OTHER) narrows it to one kind of debtor."""
    b = _buckets(conn, entity_id)
    labels = _bucket_labels(b)
    names = {r["id"]: r for r in q(conn, "SELECT id, name, customer_code, credit_limit, party_type FROM fin_v_customers")}
    per: Dict[int, Dict[str, Any]] = {}
    for it in ar_open_items(conn, entity_id, as_of):
        if party_type and names.get(it["customer_id"], {}).get("party_type") != party_type.upper():
            continue
        ref = it["doc_date"] if basis == "invoice_date" else it["due_date"]
        idx = _age(max((as_of - ref).days, 0), b)
        c = per.setdefault(it["customer_id"], {"customer_id": it["customer_id"],
                                               "customer_name": names.get(it["customer_id"], {}).get("name"),
                                               "customer_code": names.get(it["customer_id"], {}).get("customer_code"),
                                               "credit_limit": names.get(it["customer_id"], {}).get("credit_limit"),
                                               "party_type": names.get(it["customer_id"], {}).get("party_type"),
                                               "buckets": [ZERO] * len(labels), "total": ZERO, "items": []})
        amt = money(it["open_amount"])
        c["buckets"][idx] += amt
        c["total"] += amt
        c["items"].append({**it, "bucket": labels[idx], "days": (as_of - ref).days})
    rows = sorted(per.values(), key=lambda r: str(r.get("customer_name") or r.get("supplier_name") or r.get("name") or "").lower())   # A-Z (client, meeting 2)
    totals = [sum((r["buckets"][i] for r in rows), ZERO) for i in range(len(labels))]
    return {"as_of": as_of, "basis": basis, "buckets": labels, "rows": rows, "bucket_totals": totals,
            "total": sum(totals, ZERO)}


def ap_open_items(conn, entity_id: str, as_of: dt.date, supplier_id: Optional[str] = None) -> List[Dict[str, Any]]:
    sf = " AND x.supplier_id=%s" if supplier_id else ""
    p: List[Any] = [as_of, entity_id, as_of, as_of, entity_id, as_of, as_of, entity_id, as_of]
    if supplier_id:
        p.append(str(supplier_id))
    return q(conn, f"""
        SELECT x.* FROM (
          SELECT 'BILL' AS doc_type, b.id AS doc_id, b.bill_number AS doc_number, b.supplier_invoice_number AS supplier_ref,
                 b.supplier_id, b.bill_date AS doc_date, b.due_date,
                 b.total - COALESCE((SELECT SUM(a.amount) FROM fin_ap_allocations a WHERE a.bill_id=b.id AND NOT a.reversed
                                     AND a.allocation_date <= %s),0) AS open_amount
          FROM fin_supplier_bills b WHERE b.legal_entity_id=%s AND b.bill_date <= %s AND b.status <> 'VOID'
          UNION ALL
          SELECT 'PAYMENT', p.id, p.payment_number, p.reference, p.supplier_id, p.payment_date, p.payment_date,
                 -(p.amount + p.wht_amount - COALESCE((SELECT SUM(a.amount) FROM fin_ap_allocations a WHERE a.source_type='PAYMENT'
                   AND a.source_id=p.id AND NOT a.reversed AND a.allocation_date <= %s),0))
          FROM fin_supplier_payments p WHERE p.legal_entity_id=%s AND p.payment_date <= %s AND p.status='POSTED'
          UNION ALL
          SELECT 'DEBIT_NOTE', d.id, d.debit_note_number, NULL, d.supplier_id, d.note_date, d.note_date,
                 -(d.total - COALESCE((SELECT SUM(a.amount) FROM fin_ap_allocations a WHERE a.source_type='DEBIT_NOTE'
                   AND a.source_id=d.id AND NOT a.reversed AND a.allocation_date <= %s),0))
          FROM fin_debit_notes d WHERE d.legal_entity_id=%s AND d.note_date <= %s AND d.status='POSTED'
        ) x WHERE x.open_amount <> 0 {sf}""", p)


def aged_payables(conn, entity_id: str, as_of: dt.date, basis: str = "due_date") -> Dict[str, Any]:
    b = _buckets(conn, entity_id)
    labels = _bucket_labels(b)
    names = {str(r["id"]): r for r in q(conn, "SELECT id, name, external_vendor_id FROM suppliers")}
    per: Dict[str, Dict[str, Any]] = {}
    for it in ap_open_items(conn, entity_id, as_of):
        ref = it["doc_date"] if basis == "invoice_date" else it["due_date"]
        idx = _age(max((as_of - ref).days, 0), b)
        sid = str(it["supplier_id"])
        s = per.setdefault(sid, {"supplier_id": sid, "supplier_name": names.get(sid, {}).get("name"),
                                 "buckets": [ZERO] * len(labels), "total": ZERO, "items": []})
        amt = money(it["open_amount"])
        s["buckets"][idx] += amt
        s["total"] += amt
        s["items"].append({**it, "bucket": labels[idx], "days": (as_of - ref).days})
    rows = sorted(per.values(), key=lambda r: str(r.get("customer_name") or r.get("supplier_name") or r.get("name") or "").lower())   # A-Z (client, meeting 2)
    totals = [sum((r["buckets"][i] for r in rows), ZERO) for i in range(len(labels))]
    return {"as_of": as_of, "basis": basis, "buckets": labels, "rows": rows, "bucket_totals": totals,
            "total": sum(totals, ZERO)}


def customer_statement(conn, entity_id: str, customer_id: int, date_from: dt.date, date_to: dt.date) -> Dict[str, Any]:
    c = q1(conn, "SELECT id, name, customer_code, contact_details, credit_limit FROM fin_v_customers WHERE id=%s", (customer_id,))
    docs = q(conn, """
        SELECT * FROM (
          SELECT i.invoice_date AS date, 'Invoice' AS type, i.invoice_number AS number, i.id AS doc_id, i.total AS debit,
                 0::numeric AS credit, i.is_opening, i.status FROM fin_sales_invoices i
          WHERE i.legal_entity_id=%s AND i.customer_id=%s AND i.status <> 'DRAFT'
          UNION ALL
          SELECT i.voided_at::date, 'Invoice void', i.invoice_number, i.id, 0, i.total, FALSE, i.status FROM fin_sales_invoices i
          WHERE i.legal_entity_id=%s AND i.customer_id=%s AND i.status='VOID' AND i.journal_id IS NOT NULL
          UNION ALL
          SELECT r.receipt_date, 'Receipt' || COALESCE(' ' || r.reference, ''), r.receipt_number, r.id, 0, r.amount + r.wht_amount,
                 FALSE, r.status FROM fin_customer_receipts r WHERE r.legal_entity_id=%s AND r.customer_id=%s
          UNION ALL
          SELECT r.receipt_date, 'Receipt reversed', r.receipt_number, r.id, r.amount + r.wht_amount, 0, FALSE, r.status
          FROM fin_customer_receipts r WHERE r.legal_entity_id=%s AND r.customer_id=%s AND r.status='VOID'
          UNION ALL
          SELECT n.note_date, 'Credit note', n.credit_note_number, n.id, 0, n.total, n.journal_id IS NULL, n.status
          FROM fin_credit_notes n WHERE n.legal_entity_id=%s AND n.customer_id=%s
          UNION ALL
          SELECT f.refund_date, 'Refund paid', f.refund_number, f.id, f.amount, 0, FALSE, f.status
          FROM fin_customer_refunds f WHERE f.legal_entity_id=%s AND f.customer_id=%s AND f.status='POSTED'
        ) d ORDER BY d.date, d.number""", (entity_id, customer_id) * 6)
    opening = sum((money(d["debit"]) - money(d["credit"]) for d in docs if d["date"] < date_from), ZERO)
    bal, rows = opening, []
    for d in docs:
        if date_from <= d["date"] <= date_to:
            bal += money(d["debit"]) - money(d["credit"])
            rows.append({**d, "balance": bal})
    return {"customer": c, "date_from": date_from, "date_to": date_to, "opening_balance": opening,
            "rows": rows, "closing_balance": bal,
            "aging": aged_customer(conn, entity_id, customer_id, date_to)}


def aged_customer(conn, entity_id: str, customer_id: int, as_of: dt.date) -> Dict[str, Any]:
    b = _buckets(conn, entity_id)
    labels = _bucket_labels(b)
    buckets = [ZERO] * len(labels)
    for it in ar_open_items(conn, entity_id, as_of, customer_id):
        buckets[_age(max((as_of - it["doc_date"]).days, 0), b)] += money(it["open_amount"])
    return {"buckets": labels, "amounts": buckets, "total": sum(buckets, ZERO)}


def supplier_statement(conn, entity_id: str, supplier_id: str, date_from: dt.date, date_to: dt.date) -> Dict[str, Any]:
    s = q1(conn, "SELECT id, name, external_vendor_id FROM suppliers WHERE id=%s", (supplier_id,))
    docs = q(conn, """
        SELECT * FROM (
          SELECT b.bill_date AS date, 'Bill ' || b.supplier_invoice_number AS type, b.bill_number AS number, b.id AS doc_id,
                 0::numeric AS debit, b.total AS credit, b.status FROM fin_supplier_bills b
          WHERE b.legal_entity_id=%s AND b.supplier_id=%s
          UNION ALL
          SELECT b.bill_date, 'Bill voided', b.bill_number, b.id, b.total, 0, b.status FROM fin_supplier_bills b
          WHERE b.legal_entity_id=%s AND b.supplier_id=%s AND b.status='VOID' AND b.journal_id IS NOT NULL
          UNION ALL
          SELECT p.payment_date, 'Payment' || COALESCE(' ' || p.reference, ''), p.payment_number, p.id,
                 p.amount + p.wht_amount, 0, p.status FROM fin_supplier_payments p WHERE p.legal_entity_id=%s AND p.supplier_id=%s
          UNION ALL
          SELECT p.payment_date, 'Payment reversed', p.payment_number, p.id, 0, p.amount + p.wht_amount, p.status
          FROM fin_supplier_payments p WHERE p.legal_entity_id=%s AND p.supplier_id=%s AND p.status='VOID'
          UNION ALL
          SELECT d.note_date, 'Debit note', d.debit_note_number, d.id, d.total, 0, d.status FROM fin_debit_notes d
          WHERE d.legal_entity_id=%s AND d.supplier_id=%s
        ) d ORDER BY d.date, d.number""", (entity_id, supplier_id) * 5)
    opening = sum((money(d["credit"]) - money(d["debit"]) for d in docs if d["date"] < date_from), ZERO)
    bal, rows = opening, []
    for d in docs:
        if date_from <= d["date"] <= date_to:
            bal += money(d["credit"]) - money(d["debit"])
            rows.append({**d, "balance": bal})
    return {"supplier": s, "date_from": date_from, "date_to": date_to, "opening_balance": opening, "rows": rows,
            "closing_balance": bal}


def subledger_balances(conn, entity_id: str, as_of: dt.date) -> Dict[str, Decimal]:
    ar = sum((money(i["open_amount"]) for i in ar_open_items(conn, entity_id, as_of)), ZERO)
    ap = sum((money(i["open_amount"]) for i in ap_open_items(conn, entity_id, as_of)), ZERO)
    return {"ar": ar, "ap": ap}


# ---------------------------------------------------------------------------
# Sage-style journals (Sales, Cash Receipts, Purchases, Cash Disbursements,
# COGS, Inventory Adjustment, General) - all views over the GL by source.
# ---------------------------------------------------------------------------

# Sage journal codes carried by the history lines (fin_sage_gl_lines.jrnl) for each journal.
SAGE_JOURNALS = {"sales": "SJ", "cash-receipts": "CRJ", "cash-disbursements": "CDJ", "general": "GENJ"}

JOURNAL_SOURCES = {
    "sales": ("SALES_INVOICE", "CREDIT_NOTE"),
    "cash-receipts": ("CUSTOMER_RECEIPT",),
    "refunds": ("CUSTOMER_REFUND",),
    "purchases": ("SUPPLIER_BILL", "DEBIT_NOTE"),
    "cash-disbursements": ("SUPPLIER_PAYMENT", "CASH_VOUCHER", "CUSTOMER_REFUND"),
    "inventory-adjustments": ("STOCK_ADJUSTMENT", "STOCK_LOAN", "STOCK_LOAN_RETURN", "STOCK_LOAN_WRITEOFF"),
    "general": ("MANUAL_JOURNAL",),
    "assets": ("FIXED_ASSET", "DEPRECIATION_RUN", "FIXED_ASSET_DISPOSAL"),
}


def journal_report(conn, entity_id: str, kind: str, date_from: dt.date, date_to: dt.date) -> Dict[str, Any]:
    if kind == "cogs":
        rows = q(conn, """SELECT g.journal_date AS date, g.account_code, g.account_name, g.source_ref AS reference,
                                 g.product_sku, g.description, g.debit, g.credit, g.journal_id, g.journal_number, g.source_type, g.source_id
                          FROM fin_v_ledger g WHERE g.legal_entity_id=%s AND g.journal_date BETWEEN %s AND %s
                          AND g.product_sku IS NOT NULL AND g.subtype IN ('COST_OF_SALES','INVENTORY')
                          AND g.source_type IN ('SALES_INVOICE','CREDIT_NOTE','DISPENSING','STOCK_CONSUMPTION')
                          ORDER BY g.journal_date, g.journal_number, g.line_no""", (entity_id, date_from, date_to))
    else:
        sources = JOURNAL_SOURCES.get(kind)
        if not sources:
            from src.fin.errors import invalid
            raise invalid(f"Unknown journal {kind}", allowed=sorted(list(JOURNAL_SOURCES) + ["cogs"]))
        sage = SAGE_JOURNALS.get(kind)
        rows = q(conn, """SELECT g.journal_date AS date, g.account_code, g.account_name, g.source_ref AS reference,
                                 g.product_sku, COALESCE(g.description, g.journal_description) AS description,
                                 g.debit, g.credit, g.journal_id, g.journal_number, g.source_type, g.source_id, g.account_id,
                                 g.customer_id, g.origin
                          FROM fin_v_ledger g WHERE g.legal_entity_id=%s AND g.journal_date BETWEEN %s AND %s
                          AND (g.source_type = ANY(%s) OR (g.origin='SAGE' AND g.journal_number LIKE %s))
                          ORDER BY g.journal_date, g.journal_number, g.line_no""",
                 (entity_id, date_from, date_to, list(sources), f"SAGE {sage} %" if sage else "-"))
        if sage:  # 'SAGE CRJ' with no reference has no trailing space
            rows += q(conn, """SELECT g.journal_date AS date, g.account_code, g.account_name, g.source_ref AS reference,
                                      g.product_sku, g.description, g.debit, g.credit, g.journal_id, g.journal_number,
                                      g.source_type, g.source_id, g.account_id, g.customer_id, g.origin
                               FROM fin_v_ledger g WHERE g.legal_entity_id=%s AND g.journal_date BETWEEN %s AND %s
                               AND g.origin='SAGE' AND g.journal_number=%s""", (entity_id, date_from, date_to, f"SAGE {sage}"))
            rows.sort(key=lambda x: (x["date"], x["journal_number"]))
    return {"kind": kind, "date_from": date_from, "date_to": date_to, "rows": rows,
            "total_debit": sum((money(r["debit"]) for r in rows), ZERO),
            "total_credit": sum((money(r["credit"]) for r in rows), ZERO)}


# ---------------------------------------------------------------------------
# Inventory reports
# ---------------------------------------------------------------------------

def inventory_valuation(conn, entity_id: str, as_of: dt.date, department: Optional[str] = None) -> Dict[str, Any]:
    rows = q(conn, """SELECT t.sku, p.name, p.department, p.inventory_account_id, a.code AS inventory_account,
                             SUM(t.quantity) AS quantity, SUM(t.total_cost) AS value
                      FROM fin_inventory_transactions t JOIN fin_products p ON p.legal_entity_id=t.legal_entity_id AND p.sku=t.sku
                      LEFT JOIN fin_accounts a ON a.id=p.inventory_account_id
                      WHERE t.legal_entity_id=%s AND t.txn_date <= %s
                        AND t.txn_type NOT IN ('LOAN_OUT','LOAN_RETURN') AND (%s::text IS NULL OR p.department=%s)
                      GROUP BY t.sku, p.name, p.department, p.inventory_account_id, a.code
                      HAVING SUM(t.quantity) <> 0 OR SUM(t.total_cost) <> 0 ORDER BY t.sku""", (entity_id, as_of, department, department))
    # Loans are shown separately: still owned, but not in the warehouse.
    for r in rows:
        r["avg_cost"] = (Decimal(str(r["value"])) / Decimal(str(r["quantity"]))).quantize(Decimal("0.01")) if r["quantity"] else None
    loans = q(conn, """SELECT l.sku, SUM(l.quantity - l.quantity_returned) AS quantity,
                              SUM((l.quantity - l.quantity_returned) * l.unit_cost) AS value
                       FROM fin_stock_loans l WHERE l.legal_entity_id=%s AND l.status IN ('OPEN','PARTIALLY_RETURNED')
                       GROUP BY l.sku""", (entity_id,))
    total = sum((money(r["value"]) for r in rows), ZERO)
    return {"as_of": as_of, "rows": rows, "total_value": total, "on_loan": loans,
            "on_loan_value": sum((money(l["value"]) for l in loans), ZERO)}


def unit_activity(conn, entity_id: str, date_from: dt.date, date_to: dt.date, sku: Optional[str] = None,
                  department: Optional[str] = None) -> Dict[str, Any]:
    """Sage 'Inventory Unit Activity': opening + purchased - sold ± adjusted = closing, per item.
    (The report the accountant used in the meeting for Rotarix.)"""
    sf = " AND t.sku=%s" if sku else ""
    p: List[Any] = [date_from] * 1 + [date_from, date_to] * 6 + [date_to, entity_id]
    if sku:
        p.append(sku)
    if department:
        sf += " AND p.department=%s"
        p.append(department)
    rows = q(conn, f"""
        SELECT t.sku, p.name,
          SUM(CASE WHEN t.txn_date < %s THEN t.quantity ELSE 0 END) AS opening,
          SUM(CASE WHEN t.txn_date BETWEEN %s AND %s AND t.txn_type IN ('PURCHASE') THEN t.quantity ELSE 0 END) AS purchased,
          SUM(CASE WHEN t.txn_date BETWEEN %s AND %s AND t.txn_type IN ('SALE') THEN -t.quantity ELSE 0 END) AS sold,
          SUM(CASE WHEN t.txn_date BETWEEN %s AND %s AND t.txn_type IN ('RETURN_IN','RETURN_OUT') THEN t.quantity ELSE 0 END) AS returns,
          SUM(CASE WHEN t.txn_date BETWEEN %s AND %s AND t.txn_type IN ('LOAN_OUT','LOAN_RETURN') THEN t.quantity ELSE 0 END) AS loans,
          SUM(CASE WHEN t.txn_date BETWEEN %s AND %s AND t.txn_type IN ('ADJUSTMENT','DAMAGE','EXPIRY','STOCK_COUNT','RECALL',
                   'BATCH_REPLACEMENT','TRANSFER_IN','TRANSFER_OUT','OPENING_BALANCE') THEN t.quantity ELSE 0 END) AS adjusted,
          SUM(CASE WHEN t.txn_date BETWEEN %s AND %s AND t.txn_type='SALE' THEN -t.total_cost ELSE 0 END) AS cost_of_sales,
          SUM(CASE WHEN t.txn_date <= %s THEN t.quantity ELSE 0 END) AS closing
        FROM fin_inventory_transactions t JOIN fin_products p ON p.legal_entity_id=t.legal_entity_id AND p.sku=t.sku
        WHERE t.legal_entity_id=%s {sf}
        GROUP BY t.sku, p.name ORDER BY t.sku""", p)
    rows = [r for r in rows if any(Decimal(str(r[k] or 0)) != 0 for k in ("opening", "purchased", "sold", "returns",
                                                                          "loans", "adjusted", "closing"))]
    return {"date_from": date_from, "date_to": date_to, "rows": rows}


def stock_status(conn, entity_id: str, department: Optional[str] = None) -> List[Dict[str, Any]]:
    """Each product as the books hold it (FIFO cost layers) beside what is on the pharmacy's
    shelves (royan_inventory_batches - the pharmacy owns the physical count).

    Before go-live the books hold no stock - the shelves become the opening stock at cut-over
    (hospital.load_pharmacy_opening_stock) - so the shelf columns are the stock position. After
    go-live the two should agree; `difference` (books less shelves, at cost) is what to explain.

    A department store (lab, immunisation...) reads the same way: its shelf is royan_department_stock, its books the
    products of that department once the store has been counted and put in the books."""
    if department and department != "PHARMACY":
        return q(conn, """
            WITH shelf AS (SELECT item_name, MAX(fin_sku) AS sku, MAX(reorder_level) AS reorder_level, SUM(quantity) AS on_hand,
                                  SUM(quantity * COALESCE(unit_cost,0)) AS value, MIN(expiry_date) FILTER (WHERE quantity > 0) AS nearest_expiry,
                                  SUM(quantity) FILTER (WHERE expiry_date < current_date) AS expired_qty, COUNT(*) FILTER (WHERE quantity > 0) AS batches,
                                  COUNT(*) FILTER (WHERE quantity > 0 AND COALESCE(unit_cost,0) <= 0) AS uncosted, MIN(id) AS first_id
                           FROM royan_department_stock WHERE department=%s AND is_active GROUP BY item_name),
                 books AS (SELECT l.sku, SUM(l.qty_remaining) AS on_hand, SUM(l.qty_remaining*l.unit_cost) AS value
                           FROM fin_cost_layers l JOIN fin_products p ON p.legal_entity_id=l.legal_entity_id AND p.sku=l.sku
                           WHERE l.legal_entity_id=%s AND p.department=%s GROUP BY l.sku)
            SELECT COALESCE(s.sku, 'STORE-' || s.first_id) AS sku, s.item_name AS name, s.reorder_level, 'ACTIVE' AS status,
                   COALESCE(b.on_hand,0) AS on_hand, COALESCE(b.value,0) AS value, NULL::date AS nearest_expiry, 0 AS batches,
                   COALESCE(s.on_hand,0) AS shelf_on_hand, COALESCE(s.value,0) AS shelf_value, s.nearest_expiry AS shelf_nearest_expiry,
                   COALESCE(s.batches,0) AS shelf_batches, COALESCE(s.uncosted,0) AS shelf_uncosted_batches,
                   COALESCE(s.expired_qty,0) AS shelf_expired_qty, COALESCE(b.value,0) - COALESCE(s.value,0) AS difference,
                   %s AS department, s.first_id AS store_item_id
            FROM shelf s LEFT JOIN books b ON b.sku=s.sku ORDER BY s.item_name""", (department, entity_id, department, department))
    dept_filter = " AND p.department='PHARMACY'" if department == "PHARMACY" else ""
    rows = q(conn, """WITH books AS (
                          SELECT p.sku, p.name, p.reorder_level, p.status, p.formulary_id,
                                 COALESCE(SUM(l.qty_remaining),0) AS on_hand,
                                 COALESCE(SUM(l.qty_remaining * l.unit_cost),0) AS value,
                                 MIN(b.expiry_date) FILTER (WHERE l.qty_remaining > 0) AS nearest_expiry,
                                 COUNT(DISTINCT l.batch_id) FILTER (WHERE l.qty_remaining > 0) AS batches
                          FROM fin_products p
                          LEFT JOIN fin_cost_layers l ON l.legal_entity_id=p.legal_entity_id AND l.sku=p.sku
                          LEFT JOIN fin_batches b ON b.id=l.batch_id
                          WHERE p.legal_entity_id=%s AND p.product_type='INVENTORY' """ + dept_filter + """
                          GROUP BY p.sku, p.name, p.reorder_level, p.status, p.formulary_id),
                      shelf AS (
                          SELECT formulary_id, SUM(quantity_on_hand) AS on_hand,
                                 SUM(quantity_on_hand * unit_cost) AS value,
                                 COUNT(*) FILTER (WHERE unit_cost IS NULL OR unit_cost <= 0) AS uncosted,
                                 MIN(expiry_date) AS nearest_expiry,
                                 SUM(quantity_on_hand) FILTER (WHERE expiry_date < current_date) AS expired_qty,
                                 COUNT(*) AS batches
                          FROM royan_inventory_batches WHERE quantity_on_hand > 0 GROUP BY formulary_id)
                      SELECT b.sku, b.name, b.reorder_level, b.status, b.on_hand, b.value, b.nearest_expiry, b.batches,
                             COALESCE(s.on_hand,0) AS shelf_on_hand, COALESCE(s.value,0) AS shelf_value,
                             s.nearest_expiry AS shelf_nearest_expiry, COALESCE(s.batches,0) AS shelf_batches,
                             COALESCE(s.uncosted,0) AS shelf_uncosted_batches, COALESCE(s.expired_qty,0) AS shelf_expired_qty,
                             b.value - COALESCE(s.value,0) AS difference
                      FROM books b LEFT JOIN shelf s ON s.formulary_id=b.formulary_id
                      ORDER BY b.sku""", (entity_id,))
    return rows


def stock_position(conn, entity_id: str) -> Dict[str, Any]:
    """Totals for the Stock page header and the Executive overview: books vs pharmacy shelves."""
    books = q1(conn, """SELECT COALESCE(SUM(qty_remaining * unit_cost),0) AS value, COUNT(DISTINCT sku) FILTER (WHERE qty_remaining > 0) AS products
                        FROM fin_cost_layers WHERE legal_entity_id=%s""", (entity_id,))
    shelf = q1(conn, """SELECT COALESCE(SUM(quantity_on_hand * unit_cost),0) AS value, COUNT(DISTINCT formulary_id) AS products,
                               COUNT(*) AS batches,
                               COUNT(*) FILTER (WHERE unit_cost IS NULL OR unit_cost <= 0) AS uncosted_batches,
                               COALESCE(SUM(quantity_on_hand * unit_cost) FILTER (WHERE expiry_date < current_date),0) AS expired_value,
                               COUNT(DISTINCT formulary_id) FILTER (WHERE expiry_date < current_date) AS expired_products,
                               COALESCE(SUM(quantity_on_hand * unit_cost) FILTER (WHERE expiry_date BETWEEN current_date AND current_date + 90),0) AS expiring_90_value,
                               COUNT(*) FILTER (WHERE expiry_date IS NULL) AS no_expiry_batches
                        FROM royan_inventory_batches WHERE quantity_on_hand > 0""")
    s = q1(conn, "SELECT cutover_date FROM fin_settings WHERE legal_entity_id=%s", (entity_id,)) or {}
    opened = q1(conn, """SELECT MIN(txn_date) AS d FROM fin_inventory_transactions
                         WHERE legal_entity_id=%s AND source_type='PHARMACY_OPENING'""", (entity_id,))["d"]
    return {"books_value": money(books["value"]), "books_products": int(books["products"] or 0),
            "shelf_value": money(shelf["value"]), "shelf_products": int(shelf["products"] or 0),
            "shelf_batches": int(shelf["batches"] or 0), "shelf_uncosted_batches": int(shelf["uncosted_batches"] or 0),
            "shelf_no_expiry_batches": int(shelf["no_expiry_batches"] or 0),
            "expired_value": money(shelf["expired_value"]), "expired_products": int(shelf["expired_products"] or 0),
            "expiring_90_value": money(shelf["expiring_90_value"]),
            "difference": money(books["value"]) - money(shelf["value"]),
            "cutover": s.get("cutover_date"), "opening_loaded_on": opened,
            "in_books": opened is not None}


def stock_by_department(conn, entity_id: str) -> Dict[str, Any]:
    """Stock held in each department: the pharmacy's live batches (in the books since go-live) and the other
    department stores (lab, urology...) in royan_department_stock - on the shelves, not yet in the ledger until a
    stock count confirms them (Hope's department stock was last maintained in 2021)."""
    pharmacy = q1(conn, """SELECT COUNT(DISTINCT formulary_id) AS items, COUNT(*) AS batches,
                                  COALESCE(SUM(quantity_on_hand * unit_cost),0) AS value,
                                  COALESCE(SUM(quantity_on_hand * unit_cost) FILTER (WHERE expiry_date < current_date),0) AS expired_value,
                                  COUNT(*) FILTER (WHERE expiry_date < current_date) AS expired_batches,
                                  COUNT(*) FILTER (WHERE unit_cost IS NULL OR unit_cost <= 0) AS uncosted,
                                  MAX(updated_at) AS last_updated
                           FROM royan_inventory_batches WHERE quantity_on_hand > 0""")
    books = q1(conn, "SELECT COALESCE(SUM(qty_remaining*unit_cost),0) AS v FROM fin_cost_layers WHERE legal_entity_id=%s", (entity_id,))
    rows = [{"department": "PHARMACY", **pharmacy, "in_books": True, "books_value": books["v"], "source": "Pharmacy › Inventory"}]
    for d in q(conn, """SELECT department, COUNT(DISTINCT item_name) AS items, COUNT(*) AS batches,
                               COALESCE(SUM(quantity * unit_cost),0) AS value,
                               COALESCE(SUM(quantity * unit_cost) FILTER (WHERE expiry_date < current_date),0) AS expired_value,
                               COUNT(*) FILTER (WHERE expiry_date < current_date) AS expired_batches,
                               COUNT(*) FILTER (WHERE unit_cost IS NULL OR unit_cost <= 0) AS uncosted,
                               MAX(source_updated_at) AS last_updated, string_agg(DISTINCT source, ', ') AS source
                        FROM royan_department_stock WHERE quantity > 0 GROUP BY department ORDER BY department"""):
        rows.append({**d, "in_books": False, "books_value": 0,
                     "source": "Hope stores (to be counted)" if "HOPE" in (d.get("source") or "") else d.get("source")})
    items = q(conn, """SELECT department, item_name, item_code, batch_number, expiry_date, quantity, unit_cost,
                              quantity * COALESCE(unit_cost,0) AS value, (expiry_date < current_date) AS expired
                       FROM royan_department_stock WHERE quantity > 0 ORDER BY department, item_name, expiry_date""")
    total = sum((money(r["value"]) for r in rows), ZERO)
    return {"departments": rows, "items": items, "total_value": total}


def batch_list(conn, entity_id: str, sku: Optional[str] = None, expiring_within_days: Optional[int] = None,
               department: Optional[str] = None):
    p: List[Any] = [entity_id]
    extra = ""
    if department:
        extra += " AND p.department=%s"
        p.append(department)
    if sku:
        extra += " AND b.sku=%s"
        p.append(sku)
    if expiring_within_days is not None:
        extra += " AND b.expiry_date <= current_date + %s"
        p.append(int(expiring_within_days))
    return q(conn, f"""SELECT b.*, p.name AS product_name, p.department, COALESCE(SUM(l.qty_remaining),0) AS on_hand,
                              COALESCE(SUM(l.qty_remaining*l.unit_cost),0) AS value
                       FROM fin_batches b LEFT JOIN fin_products p ON p.legal_entity_id=b.legal_entity_id AND p.sku=b.sku
                       LEFT JOIN fin_cost_layers l ON l.batch_id=b.id
                       WHERE b.legal_entity_id=%s {extra}
                       GROUP BY b.id, p.name, p.department ORDER BY b.expiry_date NULLS LAST, b.sku""", p)


def item_movements(conn, entity_id: str, sku: str, date_from: dt.date, date_to: dt.date):
    return q(conn, """SELECT t.*, b.batch_number, c.name AS customer_name, s.name AS supplier_name, j.journal_number
                      FROM fin_inventory_transactions t LEFT JOIN fin_batches b ON b.id=t.batch_id
                      LEFT JOIN fin_v_customers c ON c.id=t.customer_id LEFT JOIN suppliers s ON s.id=t.supplier_id
                      LEFT JOIN fin_journals j ON j.id=t.journal_id
                      WHERE t.legal_entity_id=%s AND t.sku=%s AND t.txn_date BETWEEN %s AND %s
                      ORDER BY t.txn_date, t.created_at""", (entity_id, sku, date_from, date_to))


# ---------------------------------------------------------------------------
# Budgets
# ---------------------------------------------------------------------------

def budget_totals(conn, budget_id: str, date_from: dt.date, date_to: dt.date) -> List[Dict[str, Any]]:
    return q(conn, """SELECT bl.account_id, a.code, a.name, a.account_type, SUM(bl.amount) AS budget
                      FROM fin_budget_lines bl JOIN fin_periods p ON p.id=bl.period_id JOIN fin_accounts a ON a.id=bl.account_id
                      WHERE bl.budget_id=%s AND p.start_date >= %s AND p.end_date <= %s
                      GROUP BY bl.account_id, a.code, a.name, a.account_type ORDER BY a.code""", (budget_id, date_from, date_to))


def budget_vs_actual(conn, entity_id: str, budget_id: str, date_from: dt.date, date_to: dt.date) -> Dict[str, Any]:
    budget = {str(r["account_id"]): r for r in budget_totals(conn, budget_id, date_from, date_to)}
    actual = {str(r["account_id"]): r for r in _balances(conn, entity_id, date_from=date_from, date_to=date_to,
                                                          exclude_types=("CLOSING",))
              if r["account_type"] in ("REVENUE", "EXPENSE")}
    rows = []
    for aid in sorted(set(budget) | set(actual), key=lambda k: (budget.get(k) or actual.get(k))["code"]):
        b = budget.get(aid)
        a = actual.get(aid)
        ref = a or b
        act = _natural(a) if a else ZERO
        bud = money(b["budget"]) if b else ZERO
        var = act - bud
        favourable = var >= 0 if ref["account_type"] == "REVENUE" else var <= 0
        rows.append({"account_id": aid, "code": ref["code"], "name": ref["name"], "account_type": ref["account_type"],
                     "budget": bud, "actual": act, "variance": var,
                     "variance_pct": (var / bud * 100).quantize(Decimal("0.1")) if bud else None,
                     "favourable": favourable})
    return {"date_from": date_from, "date_to": date_to, "rows": rows}
