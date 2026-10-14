"""The books of original entry and the account ledger, in Sage's layouts, across Sage's years and Roy Books.

Everything reads fin_v_ledger, so one date range can start in 2010 (Sage) and end today (Roy Books)
in one table. Each line already carries its journal code (`jrnl`, from journal_map / fin_journal_code)
and whether it is half of a deleted entry (`hidden`).

  journal(key)        Sales, Cash Receipts, Cash Disbursements, Purchases, Cost of Goods Sold, General
                      (with corrections), Inventory Adjustments and Fixed Assets - the columns Sage prints.
  account_ledger      One account the way Sage prints its General Ledger: per month the beginning balance,
                      every transaction with a running balance, the month's change; searchable.
  chart_history       Every account with its whole-ledger balance at a date, how many entries it has and
                      when it was first and last used.
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Dict, List, Optional

from src.fin import journal_map
from src.fin.db import ZERO, money, q, q1
from src.fin.errors import invalid, not_found


def _c(key: str, label: str, type_: str = "text", link: Optional[str] = None) -> Dict[str, Any]:
    c: Dict[str, Any] = {"key": key, "label": label, "type": type_}
    if link:
        c["link"] = link
    return c


ACCT = _c("account", "Account ID", link="account")
LAYOUT = {
    "SJ": [_c("date", "Date", "date"), ACCT, _c("reference", "Invoice/CM #", link="line"), _c("description", "Line Description"),
           _c("debit", "Debit Amnt", "money"), _c("credit", "Credit Amnt", "money")],
    "CRJ": [_c("date", "Date", "date"), ACCT, _c("reference", "Transaction Ref", link="line"), _c("description", "Line Description"),
            _c("debit", "Debit Amnt", "money"), _c("credit", "Credit Amnt", "money")],
    "CDJ": [_c("date", "Date", "date"), _c("reference", "Check #", link="line"), ACCT, _c("description", "Line Description"),
            _c("debit", "Debit Amount", "money"), _c("credit", "Credit Amount", "money")],
    "PJ": [_c("date", "Date", "date"), ACCT, _c("account_name", "Account Description"), _c("reference", "Invoice/CM #", link="line"),
           _c("description", "Line Description"), _c("debit", "Debit Amount", "money"), _c("credit", "Credit Amount", "money")],
    "COGS": [_c("date", "Date", "date"), ACCT, _c("reference", "Reference", link="line"), _c("product", "Item"),
             _c("description", "Line Description"), _c("debit", "Debit Amount", "money"), _c("credit", "Credit Amount", "money")],
    "GENJ": [_c("date", "Date", "date"), ACCT, _c("reference", "Reference", link="line"), _c("description", "Trans Description"),
             _c("debit", "Debit Amt", "money"), _c("credit", "Credit Amt", "money")],
    "INAJ": [_c("date", "Date", "date"), ACCT, _c("reference", "Reference", link="line"), _c("description", "Trans Description"),
             _c("debit", "Debit Amt", "money"), _c("credit", "Credit Amt", "money")],
    "FA": [_c("date", "Date", "date"), ACCT, _c("account_name", "Account Description"), _c("reference", "Reference", link="line"),
           _c("jrnl", "Jrnl"), _c("description", "Trans Description"), _c("debit", "Debit Amt", "money"), _c("credit", "Credit Amt", "money")],
}

LINE_COLS = """g.line_id, g.journal_date AS date, g.account_id, g.account_code AS account, g.account_name, g.jrnl, g.origin,
               COALESCE(g.source_ref, g.journal_number) AS reference, COALESCE(g.description, g.journal_description) AS description,
               g.debit, g.credit, g.journal_id, g.journal_number, g.source_type, g.source_id, g.customer_id, g.supplier_id,
               g.product_sku AS product"""


def _search(search: Optional[str], params: List[Any]) -> str:
    if not search:
        return ""
    s = search.strip()
    params += [f"%{s}%"] * 4
    sql = """ AND (g.description ILIKE %s OR g.journal_description ILIKE %s OR g.source_ref ILIKE %s OR g.journal_number ILIKE %s"""
    try:
        amt = money(s.replace(",", "").replace("₦", ""))
        params += [amt, amt]
        sql += " OR g.debit = %s OR g.credit = %s"
    except ValueError:
        pass
    return sql + ")"


def journal_list() -> List[Dict[str, str]]:
    """The journals the screen offers - always from here, never typed twice in the UI."""
    return [{"key": k, "code": c, "title": journal_map.KEY_TITLE[k]} for k, c in journal_map.KEY_CODE.items()]


def journal(conn, entity_id: str, key: str, f: dt.date, t: dt.date, search: Optional[str] = None,
            limit: int = 50000) -> Dict[str, Any]:
    code = journal_map.KEY_CODE.get(key)
    if not code:
        raise invalid(f"Unknown journal {key}", allowed=list(journal_map.KEY_CODE))
    params: List[Any] = [entity_id, f, t]
    if code == "FA":
        # Every entry on the fixed-asset and accumulated-depreciation accounts, whichever journal posted it.
        which = "g.subtype IN ('FIXED_ASSET', 'ACCUMULATED_DEPRECIATION')"
    elif code == "COGS":
        # Dispensing and stock-issue postings, plus the cost side of any sales invoice that carried stock.
        which = """(g.jrnl = 'COGS' OR (g.jrnl = 'SJ' AND g.product_sku IS NOT NULL AND g.subtype IN ('COST_OF_SALES','INVENTORY')))"""
    else:
        params.append(list(journal_map.report_codes(code)))
        which = "g.jrnl = ANY(%s)"
        if code == "SJ":   # the cost side belongs to the COGS journal
            which += " AND NOT (g.product_sku IS NOT NULL AND g.subtype IN ('COST_OF_SALES','INVENTORY'))"
    sf = _search(search, params)
    rows = q(conn, f"""SELECT {LINE_COLS} FROM fin_v_ledger g
                       WHERE g.legal_entity_id=%s AND g.journal_date BETWEEN %s AND %s AND {which} {sf}
                         AND NOT g.hidden AND (g.debit <> 0 OR g.credit <> 0)
                       ORDER BY g.journal_date, g.journal_number, g.line_no LIMIT %s""", params + [limit])
    return {"key": key, "code": code, "title": journal_map.KEY_TITLE[key], "columns": LAYOUT[code], "date_from": f, "date_to": t,
            "rows": rows, "truncated": len(rows) >= limit,
            "total_debit": sum((money(r["debit"]) for r in rows), ZERO),
            "total_credit": sum((money(r["credit"]) for r in rows), ZERO)}


def _opening(conn, entity_id: str, acct: Dict[str, Any], d: dt.date) -> Any:
    """Balance brought forward into day d. Income and expense restart each year (Sage closes them to retained
    earnings), so for them only this year's lines count."""
    closes = acct["account_type"] in ("REVENUE", "EXPENSE") or acct.get("subtype") == "EQUITY_CLOSING"
    start = dt.date(d.year, 1, 1) if closes else dt.date(1900, 1, 1)
    own = money(q1(conn, """SELECT COALESCE(SUM(debit-credit),0) b FROM fin_v_ledger
                            WHERE legal_entity_id=%s AND account_id=%s AND journal_date >= %s AND journal_date < %s
                              AND journal_type <> 'CLOSING'""", (entity_id, acct["id"], start, d))["b"])
    return own + _closed_into(conn, entity_id, acct, dt.date(d.year, 1, 1))


def _re_account_id(conn, entity_id: str) -> Optional[str]:
    """The retained-earnings account Sage closes each year into (the one in use, else the lowest code)."""
    r = q1(conn, """SELECT a.id::text AS id FROM fin_accounts a WHERE a.legal_entity_id=%s AND a.subtype='RETAINED_EARNINGS'
                    ORDER BY (EXISTS (SELECT 1 FROM fin_v_ledger g WHERE g.account_id=a.id)) DESC, a.code LIMIT 1""", (entity_id,))
    return r["id"] if r else None


def _closed_into(conn, entity_id: str, acct: Dict[str, Any], year_start: dt.date) -> Any:
    """For the retained-earnings account: what Sage's year-end closings put into it before year_start - every earlier
    year's income and expense and "Equity - gets closed" balances, which this ledger never closed with journal lines."""
    if acct.get("subtype") != "RETAINED_EARNINGS" or str(acct["id"]) != _re_account_id(conn, entity_id):
        return ZERO
    return money(q1(conn, """SELECT COALESCE(SUM(debit-credit),0) b FROM fin_v_ledger WHERE legal_entity_id=%s
                             AND (account_type IN ('REVENUE','EXPENSE') OR subtype='EQUITY_CLOSING') AND journal_date < %s
                             AND journal_type <> 'CLOSING'""", (entity_id, year_start))["b"])


def account_ledger(conn, entity_id: str, account_id: str, f: dt.date, t: dt.date, search: Optional[str] = None,
                   limit: int = 20000, include_voided: bool = False) -> Dict[str, Any]:
    """Sage's General Ledger for one account: per month a Beginning Balance, each transaction with its running
    balance, and the period's change; the ending balance last. A search shows only matching lines (the balances
    stay the account's own)."""
    acct = q1(conn, "SELECT * FROM fin_accounts WHERE id=%s AND legal_entity_id=%s", (account_id, entity_id))
    if not acct:
        raise not_found("Account", account_id)
    params: List[Any] = [entity_id, account_id, f, t]
    sf = _search(search, params)
    lines = q(conn, f"""SELECT {LINE_COLS}, g.hidden FROM fin_v_ledger g
                        WHERE g.legal_entity_id=%s AND g.account_id=%s AND g.journal_date BETWEEN %s AND %s
                          AND g.journal_type <> 'CLOSING'
                        ORDER BY g.journal_date, g.journal_number, g.line_no""", [entity_id, account_id, f, t])
    shown = None
    if search:
        shown = {r["line_id"] for r in q(conn, f"""SELECT g.line_id FROM fin_v_ledger g WHERE g.legal_entity_id=%s
                                                   AND g.account_id=%s AND g.journal_date BETWEEN %s AND %s {sf}""", params)}
    by_month: Dict[str, List[Dict[str, Any]]] = {}
    for r in lines:
        by_month.setdefault(f"{r['date']:%Y-%m}", []).append(r)
    pl = acct["account_type"] in ("REVENUE", "EXPENSE") or acct.get("subtype") == "EQUITY_CLOSING"
    is_re = acct.get("subtype") == "RETAINED_EARNINGS" and str(acct["id"]) == _re_account_id(conn, entity_id)
    first = bal = _opening(conn, entity_id, acct, f)
    out: List[Dict[str, Any]] = []
    count = 0
    voided_hidden = 0
    m = dt.date(f.year, f.month, 1)
    while m <= t:   # every month in the range appears, even with no transactions, as Sage prints it
        k = f"{m:%Y-%m}"
        if pl and m.month == 1 and m > f:
            bal = ZERO   # income and expense start each year at nil (Sage closes them to retained earnings)
        if is_re and m.month == 1 and m > f:   # ... and retained earnings takes in the year just closed
            bal += _closed_into(conn, entity_id, acct, m) - _closed_into(conn, entity_id, acct, dt.date(m.year - 1, 1, 1))
        mo = {"month": k, "beginning": bal, "lines": [], "debit": ZERO, "credit": ZERO}
        for r in by_month.get(k, []):
            dr, cr = money(r["debit"]), money(r["credit"])
            bal += dr - cr
            mo["debit"] += dr
            mo["credit"] += cr
            # a voided document and its reversal cancel out: shown (flagged) so a drill from the journal is never blank
            r["voided"] = bool(r.pop("hidden"))
            if r["voided"] and not include_voided:
                voided_hidden += 1
                continue
            if shown is not None and r["line_id"] not in shown:
                continue
            count += 1
            if count <= limit:
                r["balance"] = bal
                mo["lines"].append(r)
        mo["change"] = mo["debit"] - mo["credit"]
        mo["ending"] = bal
        if not (search and not mo["lines"]):
            out.append(mo)
        m = dt.date(m.year + (m.month == 12), m.month % 12 + 1, 1)
    running = bal
    return {"account": acct, "date_from": f, "date_to": t, "search": search, "opening": first, "closing": running,
            "months": out, "lines_shown": min(count, limit), "truncated": count > limit, "voided_hidden": voided_hidden}


def chart_history(conn, entity_id: str, as_of: dt.date, search: Optional[str] = None,
                  used: Optional[str] = None) -> List[Dict[str, Any]]:
    """Every account with its balance at a date from the whole ledger (income and expense as year to date),
    entries across all years, first and last entry. used = 'used' | 'unused' filters."""
    where, params = ["a.legal_entity_id = %s"], [as_of.replace(month=1, day=1), as_of, as_of, entity_id, entity_id]
    if search:
        where.append("(a.code ILIKE %s OR a.name ILIKE %s)")
        params += [f"%{search}%"] * 2
    rows = q(conn, f"""
        SELECT a.id, a.code, a.name, a.account_type, a.subtype, a.status, a.legacy_code, a.is_control, a.description,
               COALESCE(b.balance, 0) AS balance, COALESCE(b.entries, 0) AS entries, b.first_entry, b.last_entry
        FROM fin_accounts a
        LEFT JOIN (SELECT g.account_id,
                          SUM(CASE WHEN g.account_type IN ('REVENUE','EXPENSE') THEN
                                   CASE WHEN g.journal_date >= %s AND g.journal_date <= %s THEN g.debit - g.credit ELSE 0 END
                              ELSE CASE WHEN g.journal_date <= %s THEN g.debit - g.credit ELSE 0 END END) AS balance,
                          COUNT(*) FILTER (WHERE NOT g.hidden) AS entries, MIN(g.journal_date) AS first_entry,
                          MAX(g.journal_date) AS last_entry
                   FROM fin_v_ledger g WHERE g.legal_entity_id=%s AND g.journal_type <> 'CLOSING' GROUP BY g.account_id) b
               ON b.account_id = a.id
        WHERE {' AND '.join(where)} ORDER BY a.code""", params)
    for r in rows:
        r["warning"] = "Inactive but still carries a balance" if r["status"] != "ACTIVE" and money(r["balance"]) != 0 else None
    if used == "used":
        rows = [r for r in rows if r["entries"]]
    elif used == "unused":
        rows = [r for r in rows if not r["entries"]]
    return rows
