"""The General Ledger and the customer ledgers in Sage 50's layout (template: financemeetings/Gl.xlsx).

One flat table, the columns Sage prints:
    Account ID | Account Description | Date | Reference | Jrnl | Trans Description | Debit Amt | Credit Amt | Balance
Per account (by Account ID) or customer (A-Z), month by month: a "Beginning Balance" row on the 1st, the month's
transactions (no running balance - Sage prints the balance only on the beginning and ending rows), a "Current Period
Change" row with the month's debits, credits and net when the month had activity, and after the last month an
"Ending Balance" row. Receivables lines read the customer's name (sales) or "Customer - Invoice: N" (receipts).

`kind` on every row (BEGIN / LINE / CHANGE / END) lets the screen style it; the CSV keeps Sage's columns.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional, Tuple

from src.fin.db import ZERO, money, q, q1
from src.fin.journals import account_ledger


def _months(f: dt.date, t: dt.date) -> Iterable[Tuple[dt.date, dt.date]]:
    m = dt.date(f.year, f.month, 1)
    while m <= t:
        nxt = dt.date(m.year + (m.month == 12), m.month % 12 + 1, 1)
        yield max(m, f), min(nxt - dt.timedelta(days=1), t)
        m = nxt


def _row(kind: str, aid: Any, code: str, name: str, date: Optional[dt.date], reference: str = "", jrnl: str = "",
         description: str = "", debit: Any = None, credit: Any = None, balance: Any = None, **extra: Any) -> Dict[str, Any]:
    return {"kind": kind, "party_id": aid, "account_id": code, "account_description": name, "date": date, "reference": reference or "",
            "jrnl": jrnl or "", "trans_description": description or "", "debit": debit, "credit": credit, "balance": balance, **extra}


def _customer_names(conn, ids: List[Any]) -> Dict[int, str]:
    if not ids:
        return {}
    return {r["id"]: r["name"] for r in q(conn, "SELECT id, name FROM fin_v_customers WHERE id = ANY(%s)", (list(ids),))}


def general_ledger(conn, entity_id: str, f: dt.date, t: dt.date, account_ids: Optional[List[str]] = None,
                   search: Optional[str] = None) -> Dict[str, Any]:
    """Every account (by Account ID) with a balance or entries up to the end date, in Sage's General Ledger layout."""
    accts = q(conn, """SELECT a.id::text AS id, a.code, a.name, a.subtype FROM fin_accounts a
                       WHERE a.legal_entity_id=%s AND (%s::text[] IS NULL OR a.id::text = ANY(%s::text[]))
                         AND EXISTS (SELECT 1 FROM fin_v_ledger g WHERE g.account_id=a.id AND g.journal_date <= %s)
                       ORDER BY a.code""", (entity_id, account_ids, account_ids, t))
    rows: List[Dict[str, Any]] = []
    with_entries = 0
    s = (search or "").strip().lower()
    for a in accts:
        # the search box filters: an account whose code or name matches shows whole; otherwise only matching lines,
        # and accounts with none are left out
        whole = bool(s) and (s in str(a["code"]).lower() or s in str(a["name"] or "").lower())
        led = account_ledger(conn, entity_id, a["id"], f, t, None if whole or not s else search)
        acct = led["account"]
        lines = [l for m in led["months"] for l in m["lines"]]
        if s and not whole and not lines:
            continue
        # like Sage, every account ever used is printed - at nil, with its Beginning Balance rows, if it has no entries
        with_entries += bool(lines)
        names = _customer_names(conn, list({l["customer_id"] for l in lines if l.get("customer_id")})) if a["subtype"] == "RECEIVABLE" else {}
        for mo in led["months"]:
            first = dt.date.fromisoformat(mo["month"] + "-01")
            rows.append(_row("BEGIN", a["id"], acct["code"], acct["name"], max(first, f), description="Beginning Balance",
                             balance=mo["beginning"]))
            for l in mo["lines"]:
                desc = l["description"]
                if l.get("origin") != "SAGE" and l.get("customer_id") in names:   # Sage's receivables wording
                    desc = names[l["customer_id"]] if (l.get("jrnl") == "SJ" or money(l["debit"]) > 0) else f"{names[l['customer_id']]} - Invoice: {l['reference']}"
                ref = l["reference"] or ""
                if l.get("origin") == "SAGE" and ref.startswith("SAGE "):   # Sage printed no reference for this line
                    ref = ""
                rows.append(_row("LINE", a["id"], acct["code"], acct["name"], l["date"], ref, l.get("jrnl"), desc,
                                 l["debit"] if money(l["debit"]) else None, l["credit"] if money(l["credit"]) else None,
                                 journal_id=l.get("journal_id"), source_type=l.get("source_type"), source_id=l.get("source_id")))
            if mo["lines"]:
                rows.append(_row("CHANGE", a["id"], acct["code"], acct["name"], None, description="Current Period Change",
                                 debit=mo["debit"], credit=mo["credit"], balance=mo["change"]))
        rows.append(_row("END", a["id"], "", "", t, description="Ending Balance", balance=led["closing"]))
    return {"date_from": f, "date_to": t, "rows": rows, "accounts": len({r["party_id"] for r in rows}),
            "accounts_with_entries": with_entries, "lines": sum(1 for r in rows if r["kind"] == "LINE")}


def _blocks(rows: List[Dict[str, Any]], parties: List[Dict[str, Any]], lines_by: Dict[Any, List[Dict[str, Any]]],
            opening_by: Dict[Any, Decimal], f: dt.date, t: dt.date) -> None:
    """Sage blocks for each party: monthly Beginning Balance / lines / Current Period Change, then Ending Balance."""
    for p in parties:
        pid, code, name = p["id"], p["code"], p["name"]
        bal = opening_by.get(pid, ZERO)
        mine = lines_by.get(pid, [])
        for start, end in _months(f, t):
            rows.append(_row("BEGIN", pid, code, name, start, description="Beginning Balance", balance=bal))
            month = [l for l in mine if start <= l["date"] <= end]
            dr = sum((money(l["debit"] or 0) for l in month), ZERO)
            cr = sum((money(l["credit"] or 0) for l in month), ZERO)
            for l in month:
                ref = l["reference"] or ""
                if l.get("origin") == "SAGE" and ref.startswith("SAGE "):
                    ref = ""
                rows.append(_row("LINE", pid, code, name, l["date"], ref, l["jrnl"], l["description"],
                                 l["debit"] or None, l["credit"] or None, **{k: l.get(k) for k in ("journal_id", "source_type", "source_id", "void")}))
            if month:
                rows.append(_row("CHANGE", pid, code, name, None, description="Current Period Change", debit=dr, credit=cr, balance=dr - cr))
            bal += dr - cr
        rows.append(_row("END", pid, "", "", t, description="Ending Balance", balance=bal))


def customer_ledger(conn, entity_id: str, f: dt.date, t: dt.date, *, customer_id: Optional[int] = None, search: str = "",
                    party_type: str = "", only_active: bool = True, limit: int = 300) -> Dict[str, Any]:
    """Customer Ledgers in Sage's layout from the receivables control lines (Sage history + Roy Books), customers A-Z."""
    like = f"%{search}%"
    parties = q(conn, """SELECT c.id, COALESCE(c.customer_code, c.mrn, 'C' || c.id) AS code, c.name
                         FROM fin_v_customers c
                         WHERE c.id IS NOT NULL AND (%s::int IS NULL OR c.id=%s)
                           AND (%s = '' OR c.name ILIKE %s OR c.customer_code ILIKE %s OR c.mrn ILIKE %s)
                           AND (%s = '' OR c.party_type=%s)
                           AND EXISTS (SELECT 1 FROM fin_v_ledger g JOIN fin_accounts a ON a.id=g.account_id
                                       WHERE g.legal_entity_id=%s AND g.customer_id=c.id AND a.subtype='RECEIVABLE'
                                         AND g.journal_date <= %s)
                         ORDER BY lower(c.name) LIMIT %s""",
                 (customer_id, customer_id, search, like, like, like, party_type, party_type, entity_id, t, limit))
    ids = [p["id"] for p in parties]
    if not ids:
        return {"date_from": f, "date_to": t, "rows": [], "customers": 0}
    opening = {r["customer_id"]: money(r["b"]) for r in q(conn, """
        SELECT g.customer_id, SUM(g.debit - g.credit) AS b FROM fin_v_ledger g JOIN fin_accounts a ON a.id=g.account_id
        WHERE g.legal_entity_id=%s AND a.subtype='RECEIVABLE' AND g.customer_id = ANY(%s) AND g.journal_date < %s AND NOT g.hidden
        GROUP BY 1""", (entity_id, ids, f))}
    lines: Dict[Any, List[Dict[str, Any]]] = {}
    for l in q(conn, """SELECT g.customer_id, g.journal_date AS date, COALESCE(g.source_ref, g.journal_number) AS reference, g.jrnl,
                               COALESCE(g.description, g.journal_description) AS description, g.debit, g.credit, g.journal_id,
                               g.source_type, g.source_id, g.origin
                        FROM fin_v_ledger g JOIN fin_accounts a ON a.id=g.account_id
                        WHERE g.legal_entity_id=%s AND a.subtype='RECEIVABLE' AND g.customer_id = ANY(%s)
                          AND g.journal_date BETWEEN %s AND %s AND NOT g.hidden
                        ORDER BY g.journal_date, g.journal_number, g.line_no""", (entity_id, ids, f, t)):
        lines.setdefault(l["customer_id"], []).append(l)
    if only_active and not customer_id:   # A-Z of customers with a balance or activity in the period
        parties = [p for p in parties if lines.get(p["id"]) or opening.get(p["id"], ZERO) != 0]
    rows: List[Dict[str, Any]] = []
    _blocks(rows, parties, lines, opening, f, t)
    return {"date_from": f, "date_to": t, "rows": rows, "customers": len(parties)}


def patient_hope_ledger(conn, patient_id: int, f: dt.date, t: dt.date) -> Dict[str, Any]:
    """One patient's account from the hospital's own records (Hope history and the app), in the same Sage layout:
    bills as sales (SJ, debit), receipts as cash receipts (CRJ, credit). Voided documents are left out."""
    p = q1(conn, "SELECT id, mrn, trim(coalesce(first_name,'') || ' ' || coalesce(last_name,'')) AS name FROM royan_patients WHERE id=%s", (patient_id,))
    if not p:
        return {"rows": []}
    opening = money(q1(conn, """SELECT COALESCE((SELECT SUM(patient_balance) FROM royan_billing WHERE patient_id=%s AND status <> 'void'
                                                 AND billed_at::date < %s),0)
                                     - COALESCE((SELECT SUM(amount) FROM royan_payments WHERE patient_id=%s AND COALESCE(status,'posted') <> 'void'
                                                 AND amount <= 50000000 AND received_at::date < %s),0) AS b""",
                          (patient_id, f, patient_id, f))["b"])
    lines = q(conn, """SELECT billed_at::date AS date, bill_number AS reference, 'SJ' AS jrnl,
                              CASE WHEN COALESCE(entity,'ROYAN')='SCANCARE' THEN 'Scancare bill' ELSE 'Hospital bill' END
                                || CASE WHEN external_source='hope' THEN ' (Hope)' ELSE '' END AS description,
                              patient_balance AS debit, NULL::numeric AS credit
                       FROM royan_billing WHERE patient_id=%s AND status <> 'void' AND billed_at::date BETWEEN %s AND %s
                       UNION ALL
                       SELECT p.received_at::date, COALESCE(p.receipt_number, 'PAY-' || p.id), 'CRJ',
                              %s || ' - Invoice: ' || COALESCE(b.bill_number, '-') || ' (' || upper(p.payment_method) || ')', NULL, p.amount
                       FROM royan_payments p LEFT JOIN royan_billing b ON b.id=p.billing_id
                       WHERE p.patient_id=%s AND COALESCE(p.status,'posted') <> 'void' AND p.amount <= 50000000
                         AND p.received_at::date BETWEEN %s AND %s
                       ORDER BY 1, 3 DESC""", (patient_id, f, t, p["name"], patient_id, f, t))
    rows: List[Dict[str, Any]] = []
    _blocks(rows, [{"id": p["id"], "code": p["mrn"] or str(p["id"]), "name": p["name"]}], {p["id"]: lines}, {p["id"]: opening}, f, t)
    return {"date_from": f, "date_to": t, "rows": rows, "customers": 1}


def vendor_ledger(conn, entity_id: str, f: dt.date, t: dt.date, *, supplier_id: Optional[str] = None, search: str = "",
                  limit: int = 300) -> Dict[str, Any]:
    """Vendor Ledgers in the same Sage layout, from the payables control lines, suppliers A-Z (balance = owed)."""
    like = f"%{search}%"
    parties = q(conn, """SELECT s.id::text AS id, COALESCE(s.external_vendor_id, s.sage_vendor_id, left(s.id::text, 8)) AS code, s.name
                         FROM suppliers s
                         WHERE (%s::text IS NULL OR s.id::text=%s) AND (%s = '' OR s.name ILIKE %s)
                           AND EXISTS (SELECT 1 FROM fin_v_ledger g JOIN fin_accounts a ON a.id=g.account_id
                                       WHERE g.legal_entity_id=%s AND g.supplier_id=s.id AND a.subtype='PAYABLE' AND g.journal_date <= %s)
                         ORDER BY lower(s.name) LIMIT %s""", (supplier_id, supplier_id, search, like, entity_id, t, limit))
    ids = [p["id"] for p in parties]
    if not ids:
        return {"date_from": f, "date_to": t, "rows": [], "vendors": 0}
    # Sage shows a vendor's balance as what is owed: credits less debits
    opening = {r["sid"]: money(r["b"]) for r in q(conn, """
        SELECT g.supplier_id::text AS sid, SUM(g.credit - g.debit) AS b FROM fin_v_ledger g JOIN fin_accounts a ON a.id=g.account_id
        WHERE g.legal_entity_id=%s AND a.subtype='PAYABLE' AND g.supplier_id::text = ANY(%s) AND g.journal_date < %s AND NOT g.hidden
        GROUP BY 1""", (entity_id, ids, f))}
    lines: Dict[Any, List[Dict[str, Any]]] = {}
    for l in q(conn, """SELECT g.supplier_id::text AS sid, g.journal_date AS date, COALESCE(g.source_ref, g.journal_number) AS reference, g.jrnl,
                               COALESCE(g.description, g.journal_description) AS description, g.credit AS debit, g.debit AS credit,
                               g.journal_id, g.source_type, g.source_id, g.origin
                        FROM fin_v_ledger g JOIN fin_accounts a ON a.id=g.account_id
                        WHERE g.legal_entity_id=%s AND a.subtype='PAYABLE' AND g.supplier_id::text = ANY(%s)
                          AND g.journal_date BETWEEN %s AND %s AND NOT g.hidden
                        ORDER BY g.journal_date, g.journal_number, g.line_no""", (entity_id, ids, f, t)):
        lines.setdefault(l["sid"], []).append(l)   # billed (credit to AP) shown in the first amount column, paid in the second
    rows: List[Dict[str, Any]] = []
    _blocks(rows, parties, lines, opening, f, t)
    return {"date_from": f, "date_to": t, "rows": rows, "vendors": len(parties)}
