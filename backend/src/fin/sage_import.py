"""Load Royan's Sage 50 exports into Roy Books.

    python -m src.fin.sage_import --dir ../backend/docs/Financial-engine/sage-exports [--dry-run]

Royan's Sage company was exported at its 2024 year end. The thirteen reports
become, in this order:

  1. Chart of Accounts            -> fin_accounts (via the audited Sage transfer:
                                     stage -> check -> load), posting rules re-pointed
                                     to Royan's own accounts, template accounts retired
  2. General Ledger Trial Balance -> the OPENING journal at 31 Dec 2024
  3. Customer List                -> debtor accounts (HMOs matched to royan_hmos)
  4. Vendor List                  -> suppliers (merged with the Hope suppliers by name)
  5. General Ledger (2009-2024)   -> fin_sage_gl_lines, line for line, grouped into
                                     vouchers and tagged with the customer
  6. Invoice Register             -> fin_sage_invoices
  7. Cash Receipts Journal        -> fin_sage_receipts + the invoices each one settled
  8. Balance Sheet, Cash Flow, GL Account Summary, Trial Balance, Aged
     Receivables, Items Sold to Customers, Account Reconciliation
                                  -> fin_sage_reports (as delivered) + the bank
                                     reconciliation's open items
  9. Tie-out: every account of the GL history must reproduce the trial balance;
     the computed balance sheet must equal Sage's. Only then is the history
     switched on in fin_v_ledger (history_replaces_opening).

History never posts. Loading the trial balance would normally set the go-live
date; Royan's Sage stops at 31 Dec 2024 while the hospital runs on, so the
cut-over is left for Finance to set (Setup > Settings) once 2025 onwards is
settled. Re-running replaces the history tables.

Later exports (Finance uploads them in Roy Books > Setup > Sage imports, see
api.py) work the same way. Files are recognised by their content, not their
name; a report not uploaded is taken from the last set that loaded. The "as at"
date is the last month the General Ledger reaches. A newer trial balance rolls
the opening journal forward (while the books are not live yet) and new Sage
accounts join the chart. Once live, history is only kept before the cut-over.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
from collections import defaultdict
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

import openpyxl

from src.fin import audit, migration, periods, posting, setup
from src.fin.accounts import SUBTYPE_TYPE
from src.fin.context import system_context
from src.fin.db import ZERO, ex, jsonb, money, q, q1, tx
from src.fin.errors import FinError

AS_OF = dt.date(2024, 12, 31)   # the first export; later ones carry their own date (as_of_from_gl)
FILES = {
    "coa": "Chart of Accounts.xlsx", "tb": "GL Trial Balance.xlsx", "customers": "Customer list.xlsx",
    "vendors": "Vendor list.xlsx", "gl": "General Ledger.xlsx", "invoices": "Invoice Register.xlsx",
    "crj": "Cash Receipts Journal.xlsx", "bs": "Balance Sheet.xlsx", "cf": "Cash flow.xlsx",
    "gls": "Gl account summary.xlsx", "ar": "AR.xlsx", "items": "items sold to customers.xlsx",
    "recon": "Account Reconciliation.xlsx",
    "gj": "General Journal.xlsx", "vendor_ledgers": "Vendor ledgers.xlsx", "bs_budget": "Balance Sheet-Budget.xlsx",
}
REQUIRED = ("coa", "tb", "customers", "vendors", "gl", "invoices", "crj", "bs")
# Sage names the worksheet after the report; the header row is the fallback.
SHEETS = {
    "chart of accounts": "coa", "general ledger trial balance": "tb", "customer list": "customers",
    "vendor list": "vendors", "general ledger": "gl", "invoice register": "invoices", "cash receipts journal": "crj",
    "balance sheet": "bs", "cash flow": "cf", "gl account summary": "gls", "aged receivables": "ar",
    "items sold to customers": "items", "account reconciliation": "recon", "general journal": "gj",
    "vendor ledgers": "vendor_ledgers", "balance sheet-budg.": "bs_budget", "balance sheet-budget": "bs_budget",
}
HEADERS = [  # (kind, words every one of which appears in the first rows)
    ("gl", ("account id", "jrnl", "trans description")), ("gj", ("reference", "trans description", "debit amt")),
    ("crj", ("transaction ref", "line description")), ("tb", ("account id", "debit amt", "credit amt")),
    ("coa", ("account id", "account type")), ("invoices", ("invoice/cm #", "quote no")),
    ("ar", ("invoice/cm #", "over 90")), ("items", ("item id", "cost of sales")), ("customers", ("customer id", "bill to contact")),
    ("vendor_ledgers", ("vendor id", "trans no")), ("vendors", ("vendor id", "tax id")), ("gls", ("beginnin", "net")),
    ("recon", ("beginning gl balance",)), ("bs_budget", ("assets", "budget")), ("cf", ("cash flows from operating",)),
    ("bs", ("assets", "liabilities")),
]
TITLES = {"coa": "Chart of Accounts", "tb": "General Ledger Trial Balance", "customers": "Customer List",
          "vendors": "Vendor List", "gl": "General Ledger", "invoices": "Invoice Register", "crj": "Cash Receipts Journal",
          "bs": "Balance Sheet", "cf": "Cash Flow", "gls": "GL Account Summary", "ar": "Aged Receivables",
          "items": "Items Sold to Customers", "recon": "Account Reconciliation", "gj": "General Journal",
          "vendor_ledgers": "Vendor Ledgers", "bs_budget": "Balance Sheet / Budget"}

# Posting rule -> Royan's own Sage account. Rules not listed keep the account the
# hospital template added (a head Royan's chart does not have yet).
ROYAN_MAPPINGS = {
    "AR_CONTROL": "1100", "AR_HMO": "1100", "AP_CONTROL": "2000",
    "REVENUE_CONSULTATION": "4100", "REVENUE_RADIOLOGY": "4100", "REVENUE_PHARMACY": "4100", "REVENUE_WARD": "4100",
    "REVENUE_NURSING": "4100", "REVENUE_PROCEDURE": "4100", "REVENUE_MATERNITY": "4100", "REVENUE_OTHER": "4100",
    "REVENUE_LAB": "4200", "REVENUE_IMMUNIZATION": "4000", "REVENUE_HMO": "4050",
    "SALES_DEFAULT": "4100", "SERVICE_INCOME": "4100", "OTHER_CHARGE_INCOME": "4300", "DELIVERY_INCOME": "4300",
    "SALES_DISCOUNT": "4900", "SALES_RETURNS": "4900", "HMO_DISALLOWANCE": "4900", "BAD_DEBTS": "7010",
    "INVENTORY_DEFAULT": "1200", "COGS_DEFAULT": "5000", "CONSUMABLES_EXPENSE": "6550",
    "PURCHASE_EXPENSE_DEFAULT": "6475", "WHT_SUFFERED": "6000", "WHT_PAYABLE": "2340", "BANK_CHARGES": "7200",
    "RETAINED_EARNINGS": "3910", "OPENING_BALANCE_EQUITY": "3909",
}
# Template heads kept because Royan's Sage chart has no equivalent (confirm with Finance).
KEEP_TEMPLATE = {"63000", "58500", "12990", "21100", "90000"}
ASSET_CATEGORIES = {  # template category -> Royan's (asset, accumulated depreciation, depreciation expense)
    "BUILD": ("1500", "1900", "7250"), "MV": ("1600", "1910", "7300"), "PM": ("1650", "1920", "7350"),
    "MEDEQ": ("1700", "1930", "7400"), "OFFEQ": ("1750", "1940", "7450"), "FURN": ("1800", "1950", "7500"),
}
GENERIC = {"limited", "ltd", "plc", "nigeria", "nig", "international", "internatinal", "healthcare", "health", "care",
           "hmo", "services", "service", "insurance", "company", "co", "the", "management", "of", "and", "managed"}


# ---------------------------------------------------------------------------
# File helpers
# ---------------------------------------------------------------------------

def rows_of(path: str) -> List[Tuple]:
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    return [r for r in wb.worksheets[0].iter_rows(values_only=True)]


_KINDS: Dict[Tuple[str, int, int], Optional[str]] = {}


def classify(path: str) -> Optional[str]:
    """Which Sage report a workbook is, from its worksheet name or, failing that, its first rows."""
    st = os.stat(path)
    key = (os.path.abspath(path), st.st_size, int(st.st_mtime))
    if key not in _KINDS:
        _KINDS[key] = _classify(path)
    return _KINDS[key]


def _classify(path: str) -> Optional[str]:
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.worksheets[0]
    kind = SHEETS.get(re.sub(r"\s+", " ", (ws.title or "").strip().lower()))
    if kind:
        return kind
    text = " ".join(_s(v).lower() for i, r in enumerate(ws.iter_rows(values_only=True)) if i < 6 for v in r if v is not None)
    return next((k for k, words in HEADERS if all(w in text for w in words)), None)


def describe(kind: str, rows: List[Tuple]) -> Dict[str, Any]:
    """Rows and date range of one export, for the upload screen."""
    dates = [d for d in (_date(v) for r in rows[1:] for v in r[:3]) if d]
    return {"kind": kind, "title": TITLES.get(kind, kind), "rows": max(len(rows) - 1, 0),
            "from": min(dates).isoformat() if dates else None, "to": max(dates).isoformat() if dates else None}


def resolve(dirs: List[str]) -> Dict[str, str]:
    """kind -> file, the first directory that has each report winning (the new upload, then the last set loaded)."""
    out: Dict[str, str] = {}
    for d in dirs:
        if not d or not os.path.isdir(d):
            continue
        for f in sorted(os.listdir(d)):
            p = os.path.join(d, f)
            if not f.lower().endswith((".xlsx", ".xlsm")) or f.startswith("~$"):
                continue
            k = classify(p)
            if k and k not in out:
                out[k] = p
    return out


def as_of_from_gl(gl_rows: List[Tuple]) -> dt.date:
    """Sage's General Ledger runs to the period end it was printed for: the last day of its last month."""
    last = max((d for d in (_date(r[2]) for r in gl_rows[1:] if len(r) > 4 and _s(r[4])) if d), default=AS_OF)
    nxt = dt.date(last.year + (last.month == 12), last.month % 12 + 1, 1)
    return nxt - dt.timedelta(days=1)


def _s(v: Any) -> str:
    return "" if v is None else str(v).strip()


def _d(v: Any) -> Decimal:
    if v in (None, ""):
        return ZERO
    try:
        return money(v)
    except ValueError:
        return ZERO


def _date(v: Any) -> Optional[dt.date]:
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    return None


def norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def sig_words(name: str) -> List[str]:
    return [w for w in re.findall(r"[a-z0-9]+", (name or "").lower()) if w not in GENERIC]


def key_word(name: str) -> str:
    words = [w for w in re.findall(r"[a-z0-9]+", (name or "").lower()) if w not in GENERIC]
    return words[0] if words else ""


def _plain(v: Any) -> Any:
    if isinstance(v, (dt.date, dt.datetime)):
        return v.isoformat()[:10]
    if isinstance(v, Decimal):
        return str(v)
    if isinstance(v, float):
        return str(money(v))
    return v


# ---------------------------------------------------------------------------
# 1-2. Chart of accounts and opening trial balance (the audited transfer path)
# ---------------------------------------------------------------------------

def ensure_years(conn, ctx, as_of: dt.date = AS_OF) -> None:
    for y in range(2024, as_of.year + 2):
        if not q1(conn, "SELECT 1 FROM fin_fiscal_years WHERE legal_entity_id=%s AND start_date=%s", (ctx.entity_id, dt.date(y, 1, 1))):
            periods.create_fiscal_year(conn, ctx, dt.date(y, 1, 1))


def _stage_load(conn, ctx, kind: str, path: str, as_of: Optional[dt.date]) -> Dict[str, Any]:
    b = migration.stage(conn, ctx, kind, os.path.basename(path), open(path, "rb").read(), as_of)
    if b["issues"]:
        raise FinError("VALIDATION_FAILED", f"The {kind.replace('_', ' ').lower()} has problems: {b['issues'][:3]}",
                       {"issues": b["issues"][:20]})
    return migration.load(conn, ctx, str(b["id"]))["result"]


def add_new_accounts(conn, ctx, rows: List[Tuple]) -> Dict[str, Any]:
    """Accounts Finance opened in Sage after the chart was first loaded."""
    parsed = migration.parse("COA", [list(r) for r in rows])
    have = {r["code"] for r in q(conn, "SELECT code FROM fin_accounts WHERE legal_entity_id=%s", (ctx.entity_id,))}
    added = []
    for a in parsed["rows"]:
        if a["code"] in have:
            continue
        ex(conn, """INSERT INTO fin_accounts (legal_entity_id, code, name, account_type, subtype, normal_balance, status,
                    legacy_code, legacy_type, created_by) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
           (ctx.entity_id, a["code"], a["name"], SUBTYPE_TYPE[a["subtype"]], a["subtype"], a["normal_balance"],
            "ACTIVE" if a["active"] else "INACTIVE", a["code"], a["legacy_type"], ctx.actor_id))
        added.append(a["code"])
    return {"accounts_added": added, "issues": parsed["issues"]}


def load_chart_and_tb(conn, ctx, files: Dict[str, str], as_of: dt.date) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    cut_before = q1(conn, "SELECT cutover_date FROM fin_settings WHERE legal_entity_id=%s", (ctx.entity_id,))["cutover_date"]
    if q1(conn, "SELECT 1 FROM fin_migration_batches WHERE legal_entity_id=%s AND kind='COA' AND status='LOADED'", (ctx.entity_id,)):
        out["COA"] = add_new_accounts(conn, ctx, rows_of(files["coa"]))
    else:
        out["COA"] = _stage_load(conn, ctx, "COA", files["coa"], None)
    opening = q1(conn, """SELECT id, journal_number, journal_date FROM fin_journals WHERE legal_entity_id=%s
                          AND journal_type='OPENING' AND source_ref='SAGE-TB' AND status='POSTED'""", (ctx.entity_id,))
    if opening and opening["journal_date"] >= as_of:
        out["TRIAL_BALANCE"] = f"opening balances already at {opening['journal_date']:%d %b %Y}"
    elif opening and cut_before:
        # The books are live: their opening stays; the newer Sage history is kept only up to the cut-over.
        out["TRIAL_BALANCE"] = f"books live since {cut_before:%d %b %Y} - opening at {opening['journal_date']:%d %b %Y} kept"
    else:
        if opening:   # roll the opening forward to the newer trial balance (nothing else has posted yet)
            posting.reverse(conn, ctx, str(opening["id"]), reason=f"Opening rolled forward to the Sage trial balance at {as_of:%d %b %Y}",
                            allow_system=True)
        out["TRIAL_BALANCE"] = _stage_load(conn, ctx, "TRIAL_BALANCE", files["tb"], as_of)
        if opening:
            out["TRIAL_BALANCE"]["replaced"] = opening["journal_number"]
    # Go-live is Finance's decision (see module doc): loading a trial balance must not set it.
    if not cut_before and q1(conn, "SELECT cutover_date FROM fin_settings WHERE legal_entity_id=%s", (ctx.entity_id,))["cutover_date"]:
        setup.update_settings(conn, ctx, {"cutover_date": None})
        audit.record(conn, ctx, "CUTOVER_LEFT_OPEN", "settings", ctx.entity_id,
                     reason=f"Sage history loaded to {as_of:%d %b %Y}; Finance sets the go-live date")
    return out


def repoint_rules(conn, ctx) -> Dict[str, Any]:
    acct = {a["code"]: a for a in q(conn, "SELECT id, code, status FROM fin_accounts WHERE legal_entity_id=%s", (ctx.entity_id,))}
    mapped = []
    for key, code in ROYAN_MAPPINGS.items():
        if code in acct:
            setup.set_mapping(conn, ctx, key, str(acct[code]["id"]), note="Royan's Sage chart")
            mapped.append(key)
    for key in ("AR_CONTROL", "AP_CONTROL"):
        ex(conn, """UPDATE fin_accounts SET is_control=TRUE WHERE id=(SELECT account_id FROM fin_account_mappings
                    WHERE legal_entity_id=%s AND mapping_key=%s)""", (ctx.entity_id, key))
    # Asset categories follow Royan's fixed-asset accounts.
    for cat, (a, acc, exp) in ASSET_CATEGORIES.items():
        if all(c in acct for c in (a, acc, exp)):
            ex(conn, """UPDATE fin_asset_categories SET asset_account_id=%s, accum_dep_account_id=%s, dep_expense_account_id=%s
                        WHERE legal_entity_id=%s AND code=%s""", (acct[a]["id"], acct[acc]["id"], acct[exp]["id"], ctx.entity_id, cat))
    # Retire the template's bank/cash fronts and every template account nothing uses.
    ex(conn, """UPDATE fin_bank_accounts b SET status='INACTIVE' FROM fin_accounts a
                WHERE a.id=b.gl_account_id AND b.legal_entity_id=%s AND a.created_by='migration-221'""", (ctx.entity_id,))
    retired = q(conn, """UPDATE fin_accounts a SET status='INACTIVE'
                         WHERE a.legal_entity_id=%s AND a.created_by='migration-221' AND NOT (a.code = ANY(%s))
                           AND NOT EXISTS (SELECT 1 FROM fin_journal_lines l WHERE l.account_id=a.id)
                           AND NOT EXISTS (SELECT 1 FROM fin_account_mappings m WHERE m.account_id=a.id)
                         RETURNING a.code""", (ctx.entity_id, list(KEEP_TEMPLATE)))
    ex(conn, """UPDATE fin_accounts SET description='Added by Roy Books (no equivalent in Royan''s Sage chart) - confirm with Finance'
                WHERE legal_entity_id=%s AND created_by='migration-221' AND status='ACTIVE'""", (ctx.entity_id,))
    return {"rules_mapped": len(mapped), "template_accounts_retired": len(retired)}


def set_receipt_accounts(conn, ctx, crj_rows: List[Tuple], year: int = AS_OF.year) -> Dict[str, Any]:
    """Cash at the till lands in Cash on Hand; card and transfer in the bank Royan used most in the last year."""
    banks = {r["code"]: str(r["bank_id"]) for r in q(conn, """SELECT a.code, b.id AS bank_id FROM fin_bank_accounts b
                JOIN fin_accounts a ON a.id=b.gl_account_id WHERE b.legal_entity_id=%s AND b.status='ACTIVE'""", (ctx.entity_id,))}
    use = defaultdict(int)
    for r in crj_rows:
        if _date(r[0]) and _date(r[0]).year == year and _s(r[1]) in banks and _s(r[1]) != "1010" and _d(r[4]) > 0:
            use[_s(r[1])] += 1
    main = max(use, key=use.get) if use else None
    ra = {"cash": banks.get("1010"), "card": banks.get(main), "transfer": banks.get(main), "other": banks.get(main)}
    ra = {k: v for k, v in ra.items() if v}
    setup.update_settings(conn, ctx, {"receipt_accounts": ra})
    return {"cash": "1010", "card/transfer/other": main}


# ---------------------------------------------------------------------------
# 3-4. Parties
# ---------------------------------------------------------------------------

def load_customers(conn, ctx, rows: List[Tuple]) -> Dict[str, Any]:
    from src.fin import sales
    hmos = q(conn, "SELECT id, name, code FROM royan_hmos WHERE is_active")
    by_norm = defaultdict(list)
    by_word = defaultdict(list)
    for h in hmos:
        by_norm[norm(h["name"])].append(h)
        if key_word(h["name"]):
            by_word[key_word(h["name"])].append(h)
    stats = defaultdict(int)
    for r in rows[1:]:
        code, name = _s(r[0]), _s(r[1])
        if not code or not name:
            continue
        contact, phone = _s(r[2]) if len(r) > 2 else "", _s(r[3]) if len(r) > 3 else ""
        cid, method = None, None
        is_hmo = code.upper().startswith("HMO/") or "/4050/" in code.upper()
        if is_hmo:
            cands = by_norm.get(norm(name)) or []
            if len(cands) == 1:
                method = "HMO exact name"
            else:
                # Same first distinctive word, and - when both names have two or more - the same second word
                # ("Life Care Partner" is not "Life Action Plus").
                mine = sig_words(name)
                cands = [h for h in (by_word.get(key_word(name)) or [])
                         if len(mine) < 2 or len(sig_words(h["name"])) < 2 or sig_words(h["name"])[1] == mine[1]]
                method = "HMO name" if len(cands) == 1 else None
            if method:
                cid = sales.ensure_hmo_customer(conn, cands[0]["id"], "sage-import")
        if not cid:
            existing = q1(conn, """SELECT s.customer_id FROM fin_sage_customers s JOIN fin_customers c ON c.id=s.customer_id
                                   WHERE s.legal_entity_id=%s AND s.sage_code=%s AND c.party_type <> 'HMO'""",
                          (ctx.entity_id, code))
            if existing:
                cid, method = existing["customer_id"], "existing"
            else:
                kind = "CORPORATE" if is_hmo or any(w in name.lower() for w in ("limited", "ltd", "plc", "insurance",
                        "health", "paystack", "bank", "company", "school", "church")) else "OTHER"
                note = ("HMO in Sage not found in the hospital's HMO list" if is_hmo else
                        "Sundry / walk-in income account in Sage" if code.upper().startswith("SD/") else
                        "Private customer in Sage" if kind == "OTHER" else "Corporate customer in Sage")
                cid = q1(conn, """INSERT INTO fin_customers (party_type, name, customer_code, payment_terms_days, notes, created_by)
                                  VALUES (%s,%s,%s,%s,%s,'sage-import')
                                  ON CONFLICT (customer_code) DO UPDATE SET name=EXCLUDED.name RETURNING id""",
                         (kind, name, code, 60 if is_hmo else 0, note))["id"]
                method = f"new {kind.lower()}"
        ex(conn, """UPDATE fin_customers SET customer_code=%s WHERE id=%s AND customer_code IS NULL
                    AND NOT EXISTS (SELECT 1 FROM fin_customers WHERE customer_code=%s)""", (code, cid, code))
        ex(conn, """INSERT INTO fin_sage_customers (legal_entity_id, sage_code, name, contact, phone, customer_id, match_method)
                    VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (legal_entity_id, sage_code) DO UPDATE SET name=EXCLUDED.name,
                    contact=EXCLUDED.contact, phone=EXCLUDED.phone, customer_id=EXCLUDED.customer_id, match_method=EXCLUDED.match_method""",
           (ctx.entity_id, code, name, contact or None, phone or None, cid, method))
        stats[method] += 1
    return dict(stats)


def load_vendors(conn, ctx, rows: List[Tuple]) -> Dict[str, Any]:
    sup = q(conn, "SELECT id, name FROM suppliers")
    by_norm = {norm(s["name"]): s for s in sup}
    by_word = defaultdict(list)
    for s in sup:
        if key_word(s["name"]):
            by_word[key_word(s["name"])].append(s)
    merged = created = 0
    for r in rows[1:]:
        code, name = _s(r[0]), _s(r[1])
        if not code or not name:
            continue
        contact, phone, tax = (_s(r[i]) if len(r) > i else "" for i in (2, 3, 4))
        match = by_norm.get(norm(name)) or (by_word[key_word(name)][0] if len(by_word.get(key_word(name), [])) == 1 else None)
        if match and not q1(conn, "SELECT 1 FROM suppliers WHERE sage_vendor_id=%s AND id<>%s", (code, match["id"])):
            ex(conn, """UPDATE suppliers SET sage_vendor_id=COALESCE(sage_vendor_id, %s), tax_id=COALESCE(tax_id, %s),
                        phone=COALESCE(phone, %s), contact_name=COALESCE(contact_name, %s) WHERE id=%s""",
               (code, tax or None, phone or None, contact or None, match["id"]))
            merged += 1
        else:
            ex(conn, """INSERT INTO suppliers (name, external_vendor_id, sage_vendor_id, tax_id, phone, contact_name, status)
                        VALUES (%s,%s,%s,%s,%s,%s,'active') ON CONFLICT (external_vendor_id) DO NOTHING""",
               (name, f"SAGE:{code}", code, tax or None, phone or None, contact or None))
            created += 1
    return {"merged_with_existing": merged, "created": created}


# ---------------------------------------------------------------------------
# 5. General ledger history
# ---------------------------------------------------------------------------

def customer_lookup(conn, ctx) -> Dict[str, int]:
    out = {}
    for r in q(conn, "SELECT name, customer_id FROM fin_sage_customers WHERE legal_entity_id=%s", (ctx.entity_id,)):
        out.setdefault(norm(r["name"]), r["customer_id"])
    return out


def party_prefix(desc: str) -> str:
    """'Mrs Odubeko - Invoice: 1002 - memo' -> 'Mrs Odubeko' (every SJ / CRJ leg starts with the customer)."""
    return re.split(r"\s+-\s+", (desc or "").strip())[0]


def _vouchers(lines: List[List[Any]]) -> None:
    """Group Sage lines into the entries Sage posted together (index 9 = voucher key).

    Sales and cash receipts: journal + date + reference + customer - every such
    voucher balances. Disbursements and general journals often carry no
    reference in Sage's export, so their legs are paired by date and equal
    amount (bank credit <-> expense debit); anything left over on that day forms
    one entry. The key says which ('#' = paired by amount)."""
    groups: Dict[Tuple, List[List[Any]]] = defaultdict(list)
    for l in lines:
        jrnl, d, ref, desc = l[4], l[3], l[5], l[6]
        if jrnl in ("SJ", "CRJ"):
            l[9] = f"{jrnl}|{d.isoformat()}|{ref}|{party_prefix(desc)}"
        else:
            groups[(jrnl, d, ref)].append(l)
    for (jrnl, d, ref), ls in groups.items():
        base = f"{jrnl}|{d.isoformat()}|{ref}"
        if ref and sum((l[7] for l in ls), ZERO) == sum((l[8] for l in ls), ZERO):
            for l in ls:
                l[9] = base
            continue
        debits = [l for l in ls if l[7] > 0]
        credits = [l for l in ls if l[8] > 0]
        used, n = set(), 0
        for dl in debits:
            for cl in credits:
                if id(cl) not in used and cl[8] == dl[7]:
                    used.add(id(cl))
                    used.add(id(dl))
                    n += 1
                    dl[9] = cl[9] = f"{base}|#{n}"
                    break
        for l in ls:
            if id(l) not in used:
                l[9] = f"{base}|rest"


def load_gl(conn, ctx, rows: List[Tuple], cust: Dict[str, int]) -> Dict[str, Any]:
    acct = {a["code"]: str(a["id"]) for a in q(conn, "SELECT id, code FROM fin_accounts WHERE legal_entity_id=%s", (ctx.entity_id,))}
    cut = q1(conn, "SELECT cutover_date FROM fin_settings WHERE legal_entity_id=%s", (ctx.entity_id,))["cutover_date"]
    ex(conn, "DELETE FROM fin_sage_gl_lines WHERE legal_entity_id=%s", (ctx.entity_id,))
    lines: List[List[Any]] = []
    after_cutover = 0
    for i, r in enumerate(rows[1:], start=2):
        jrnl = _s(r[4]) if len(r) > 4 else ""
        d = _date(r[2])
        if jrnl not in ("CRJ", "SJ", "CDJ", "GENJ") or not d:
            continue
        if cut and d >= cut:   # from the cut-over the books themselves are the record
            after_cutover += 1
            continue
        code, ref, desc = _s(r[0]), _s(r[3]), _s(r[5])
        c = cust.get(norm(party_prefix(desc))) if jrnl in ("SJ", "CRJ") else None
        lines.append([i, code, acct.get(code), d, jrnl, ref, desc, _d(r[6]), _d(r[7]), "", c])
    _vouchers(lines)
    missing = sorted({l[1] for l in lines if not l[2]})
    with conn.cursor() as cur:
        from psycopg2.extras import execute_values
        execute_values(cur, """INSERT INTO fin_sage_gl_lines (legal_entity_id, row_no, account_code, account_id, txn_date, jrnl,
                               reference, description, debit, credit, voucher, customer_id) VALUES %s""",
                       [(ctx.entity_id, *l) for l in lines], page_size=5000)
    by_j: Dict[str, int] = defaultdict(int)
    for l in lines:
        by_j[l[4]] += 1
    return {"lines": len(lines), "by_journal": dict(by_j), "accounts_missing_from_chart": missing,
            "vouchers": len({l[9] for l in lines}), "lines_with_customer": sum(1 for l in lines if l[10]),
            "lines_paired_by_amount": sum(1 for l in lines if "|#" in l[9]), "lines_after_cutover_skipped": after_cutover}


# ---------------------------------------------------------------------------
# 6-7. Invoices and receipts
# ---------------------------------------------------------------------------

def load_invoices(conn, ctx, rows: List[Tuple], cust: Dict[str, int]) -> Dict[str, Any]:
    ex(conn, "DELETE FROM fin_sage_receipt_invoices WHERE receipt_id IN (SELECT id FROM fin_sage_receipts WHERE legal_entity_id=%s)", (ctx.entity_id,))
    ex(conn, "DELETE FROM fin_sage_invoices WHERE legal_entity_id=%s", (ctx.entity_id,))
    out, unmatched = [], set()
    for i, r in enumerate(rows[1:], start=2):
        no, d, quote, name, amt = _s(r[0]), _date(r[1]), _s(r[2]), _s(r[3]), _d(r[4])
        if not name or not d:
            continue
        c = cust.get(norm(name))
        if not c:
            unmatched.add(name)
        out.append((ctx.entity_id, i, no or None, d, quote or None, name, c, amt,
                    f"SJ|{d.isoformat()}|{no}|{name}" if no else None))
    with conn.cursor() as cur:
        from psycopg2.extras import execute_values
        execute_values(cur, """INSERT INTO fin_sage_invoices (legal_entity_id, row_no, invoice_number, invoice_date, quote_number,
                               customer_name, customer_id, amount, voucher) VALUES %s""", out, page_size=5000)
    # keep only vouchers that really exist in the GL
    ex(conn, """UPDATE fin_sage_invoices i SET voucher=NULL WHERE i.legal_entity_id=%s AND i.voucher IS NOT NULL
                AND NOT EXISTS (SELECT 1 FROM fin_sage_gl_lines l WHERE l.legal_entity_id=i.legal_entity_id AND l.voucher=i.voucher)""",
       (ctx.entity_id,))
    total = sum((o[7] for o in out), ZERO)
    return {"invoices": len(out), "total": str(total), "customers_not_found": sorted(unmatched)[:20],
            "with_gl_voucher": q1(conn, "SELECT COUNT(*) n FROM fin_sage_invoices WHERE legal_entity_id=%s AND voucher IS NOT NULL",
                                  (ctx.entity_id,))["n"]}


def load_receipts(conn, ctx, rows: List[Tuple], cust: Dict[str, int]) -> Dict[str, Any]:
    acct = {a["code"]: (str(a["id"]), a["subtype"]) for a in q(conn, "SELECT id, code, subtype FROM fin_accounts WHERE legal_entity_id=%s", (ctx.entity_id,))}
    ex(conn, "DELETE FROM fin_sage_receipts WHERE legal_entity_id=%s", (ctx.entity_id,))
    inv_index: Dict[Tuple[str, Optional[int]], List[Dict[str, Any]]] = defaultdict(list)
    for i in q(conn, """SELECT id, invoice_number, customer_id, invoice_date, amount FROM fin_sage_invoices
                        WHERE legal_entity_id=%s AND invoice_number IS NOT NULL ORDER BY invoice_date""", (ctx.entity_id,)):
        i["left"] = money(i["amount"])
        inv_index[(i["invoice_number"].lower(), i["customer_id"])].append(i)
    pending: List[Tuple[str, Decimal]] = []   # AR legs waiting for their bank leg
    receipts = allocated = 0
    total = ZERO
    for n, r in enumerate(rows[1:], start=2):
        d = _date(r[0])
        if not d:
            continue
        code, ref, desc, dr, cr = _s(r[1]), _s(r[2]), _s(r[3]), _d(r[4]), _d(r[5])
        m = re.match(r"(?i)^invoice:\s*(.*)$", desc)
        if m and code == "1100":
            pending.append((m.group(1).strip(), cr - dr))
            continue
        if acct.get(code, (None, None))[1] != "CASH":
            continue
        c = cust.get(norm(desc))
        rid = q1(conn, """INSERT INTO fin_sage_receipts (legal_entity_id, reference, receipt_date, payer, customer_id, bank_account_code,
                          bank_account_id, amount, voucher, row_no) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                 (ctx.entity_id, ref or "-", d, desc, c, code, acct[code][0], dr - cr, f"CRJ|{d.isoformat()}|{ref}|{desc}", n))["id"]
        receipts += 1
        total += dr - cr
        for inv_no, amt in pending:
            match = None
            for cand in inv_index.get((inv_no.lower(), c), []):
                if cand["invoice_date"] <= d and cand["left"] > 0:
                    match = cand
            if match:
                match["left"] -= amt
                allocated += 1
            ex(conn, "INSERT INTO fin_sage_receipt_invoices (receipt_id, invoice_number, invoice_id, amount) VALUES (%s,%s,%s,%s)",
               (rid, inv_no, match["id"] if match else None, amt))
        pending = []
    ex(conn, """UPDATE fin_sage_invoices i SET amount_received = COALESCE((SELECT SUM(ri.amount) FROM fin_sage_receipt_invoices ri
                WHERE ri.invoice_id=i.id), 0) WHERE i.legal_entity_id=%s""", (ctx.entity_id,))
    return {"receipts": receipts, "total": str(total), "invoice_lines_linked": allocated}


# ---------------------------------------------------------------------------
# 8. Reports as delivered, and the bank reconciliation baseline
# ---------------------------------------------------------------------------

SNAPSHOTS = [("balance-sheet", "bs", "Balance Sheet"), ("cash-flow", "cf", "Cash Flow"),
             ("gl-account-summary", "gls", "GL Account Summary"), ("trial-balance", "tb", "General Ledger Trial Balance"),
             ("aged-receivables", "ar", "Aged Receivables"), ("items-sold", "items", "Items Sold to Customers"),
             ("account-reconciliation", "recon", "Account Reconciliation"), ("chart-of-accounts", "coa", "Chart of Accounts"),
             ("customer-list", "customers", "Customer List"), ("vendor-list", "vendors", "Vendor List"),
             ("general-journal", "gj", "General Journal"), ("vendor-ledgers", "vendor_ledgers", "Vendor Ledgers"),
             ("balance-sheet-budget", "bs_budget", "Balance Sheet / Budget")]


def load_snapshots(conn, ctx, files: Dict[str, str], cache: Dict[str, List[Tuple]], as_of: dt.date) -> int:
    n = 0
    for key, f, title in SNAPSHOTS:
        if f not in files:
            continue
        n += 1
        rows = cache.get(f) or rows_of(files[f])
        body = [[_plain(v) for v in r] for r in rows if any(v not in (None, "") for v in r)]
        cols = [str(c).replace("\n", " ") if c is not None else "" for c in body[0]] if body else []
        ex(conn, """INSERT INTO fin_sage_reports (legal_entity_id, report_key, title, as_of, file_name, columns, rows)
                    VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (legal_entity_id, report_key) DO UPDATE SET title=EXCLUDED.title,
                    as_of=EXCLUDED.as_of, file_name=EXCLUDED.file_name, columns=EXCLUDED.columns, rows=EXCLUDED.rows, loaded_at=now()""",
           (ctx.entity_id, key, title, as_of, os.path.basename(files[f]), jsonb(cols),
            jsonb(body[1:] if key not in ("balance-sheet", "cash-flow", "account-reconciliation", "balance-sheet-budget") else body)))
    return n


def load_recon(conn, ctx, rows: List[Tuple], tb_rows: List[Tuple]) -> Dict[str, Any]:
    ex(conn, "DELETE FROM fin_sage_recon_items WHERE legal_entity_id=%s", (ctx.entity_id,))
    ending = None
    for r in rows:
        if _s(r[0]).lower() == "ending gl balance":
            ending = _d(r[4] if len(r) > 4 else None)
            break
    code = None
    for r in tb_rows[1:]:
        if r and _s(r[0]) and ending is not None and _d(r[2]) - _d(r[3]) == ending:
            code = _s(r[0])
    section, n, total = None, 0, defaultdict(lambda: ZERO)
    for r in rows:
        label = _s(r[0]).lower()
        if "deposits in transit" in label:
            section = "DEPOSIT_IN_TRANSIT"; continue
        if "outstanding checks" in label or "outstanding cheques" in label:
            section = "OUTSTANDING_CHECK"; continue
        if "other" in label and "outstanding" in label:
            section = "OTHER"; continue
        if label.startswith("total") or label.startswith("unreconciled") or label.startswith("ending"):
            section = None if label.startswith("total") else section
            continue
        d = _date(r[1]) if len(r) > 1 else None
        if section and d:
            amt = _d(r[3] if len(r) > 3 else None) or _d(r[4] if len(r) > 4 else None)
            ex(conn, """INSERT INTO fin_sage_recon_items (legal_entity_id, account_code, section, item_date, reference, description, amount)
                        VALUES (%s,%s,%s,%s,%s,%s,%s)""", (ctx.entity_id, code or "?", section, d, _s(r[2]) or None, None, amt))
            n += 1
            total[section] += amt
    return {"bank_account": code, "ending_gl_balance": str(ending), "items": n, "by_section": {k: str(v) for k, v in total.items()}}


# ---------------------------------------------------------------------------
# 9. Tie-out
# ---------------------------------------------------------------------------

def tie_out(conn, ctx, tb_rows: List[Tuple], bs_rows: List[Tuple], as_of: dt.date = AS_OF) -> Dict[str, Any]:
    tb = {_s(r[0]): _d(r[2]) - _d(r[3]) for r in tb_rows[1:] if r and _s(r[0]) and re.match(r"^[\w.\-]+$", _s(r[0]))}
    hist = {r["code"]: (money(r["bal"]), money(r["y24"]), r["account_type"], r["subtype"]) for r in q(conn, """
        SELECT a.code, a.account_type, a.subtype, COALESCE(SUM(l.debit-l.credit),0) bal,
               COALESCE(SUM(l.debit-l.credit) FILTER (WHERE l.txn_date >= %s),0) y24
        FROM fin_accounts a LEFT JOIN fin_sage_gl_lines l ON l.account_id=a.id AND l.txn_date <= %s
        WHERE a.legal_entity_id=%s GROUP BY a.code, a.account_type, a.subtype""", (dt.date(as_of.year, 1, 1), as_of, ctx.entity_id))}
    issues = []
    prior_pl = ZERO
    for code, (bal, y24, atype, sub) in hist.items():
        if atype in ("REVENUE", "EXPENSE"):
            prior_pl += bal - y24
            if y24 != tb.get(code, ZERO):
                issues.append({"account": code, "sage_tb": str(tb.get(code, ZERO)), f"history_{as_of.year}": str(y24)})
        elif sub in ("RETAINED_EARNINGS", "EQUITY_CLOSING"):
            continue
        elif bal != tb.get(code, ZERO):
            issues.append({"account": code, "sage_tb": str(tb.get(code, ZERO)), "history": str(bal)})
    # Equity: Sage closes each year's profit (and the 'gets closed' equity) into retained earnings
    # without journal lines, so retained earnings = its own lines + every prior year's result + closing equity.
    re_codes = [c for c, v in hist.items() if v[3] in ("RETAINED_EARNINGS", "EQUITY_CLOSING")]
    re_hist = sum((hist[c][0] for c in re_codes), ZERO) + prior_pl
    re_tb = sum((tb.get(c, ZERO) for c in re_codes), ZERO)
    if re_hist != re_tb:
        issues.append({"account": "retained earnings", "sage_tb": str(re_tb), "history": str(re_hist)})
    sage_ta = next((_d(r[2]) for r in bs_rows if r and _s(r[0]).lower() == "total assets"), None)
    sage_tlc = next((_d(r[2]) for r in bs_rows if r and _s(r[0]).lower().startswith("total liabilities & capital")), None)
    return {"as_of": as_of.isoformat(), "accounts_checked": len(hist), "issues": issues, "ties": not issues,
            "sage_total_assets": str(sage_ta), "sage_total_liabilities_and_capital": str(sage_tlc)}


def check_statements(conn, ctx, bs_rows: List[Tuple], as_of: dt.date = AS_OF) -> Dict[str, Any]:
    from src.fin import reports
    bs = reports.balance_sheet(conn, ctx.entity_id, as_of)
    sage_ta = next((_d(r[2]) for r in bs_rows if r and _s(r[0]).lower() == "total assets"), None)
    pl = reports.income_statement(conn, ctx.entity_id, dt.date(as_of.year, 1, 1), as_of)
    sage_ni = next((_d(r[1]) for r in bs_rows if r and _s(r[0]).lower() == "net income"), None)
    return {"year": as_of.year, "roy_total_assets": str(bs["total_assets"]), "sage_total_assets": str(sage_ta),
            "assets_agree": sage_ta == bs["total_assets"], "balanced": bs["balanced"],
            "roy_net_income": str(pl["net_profit"]), "sage_net_income": str(sage_ni),
            "net_income_agrees": sage_ni == pl["net_profit"]}


# ---------------------------------------------------------------------------

def check_general_journal(gj_rows: List[Tuple], gl_rows: List[Tuple]) -> Dict[str, Any]:
    """Sage's General Journal report against the GENJ lines of its General Ledger: they must be the same lines."""
    def key(d, code, dr, cr):
        return (d, code, _d(dr), _d(cr))
    gl = defaultdict(int)
    for r in gl_rows[1:]:
        if len(r) > 7 and _s(r[4]) == "GENJ" and _date(r[2]):
            gl[key(_date(r[2]), _s(r[0]), r[6], r[7])] += 1
    gj = defaultdict(int)
    refs = 0
    for r in gj_rows[1:]:
        if r and _date(r[0]) and _s(r[1]) and (_d(r[4] if len(r) > 4 else None) or _d(r[5] if len(r) > 5 else None)):
            gj[key(_date(r[0]), _s(r[1]), r[4] if len(r) > 4 else None, r[5] if len(r) > 5 else None)] += 1
            refs += bool(_s(r[2]))
    only_gj = sum(max(n - gl.get(k, 0), 0) for k, n in gj.items())
    only_gl = sum(max(n - gj.get(k, 0), 0) for k, n in gl.items())
    return {"journal_lines": sum(gj.values()), "ledger_genj_lines": sum(gl.values()), "with_reference": refs,
            "only_in_journal": only_gj, "only_in_ledger": only_gl, "agrees": only_gj == 0 and only_gl == 0}


class _Rollback(Exception):
    def __init__(self, out: Dict[str, Any]):
        super().__init__("dry run")
        self.out = out


def run(d: Any, dry_run: bool = False, actor: str = "sage-import") -> Dict[str, Any]:
    """Load a set of Sage exports. `d` is a directory, a list of directories (first wins per report), or kind -> file.
    A dry run does everything, reports the tie-out, and rolls back."""
    files = d if isinstance(d, dict) else resolve(d if isinstance(d, list) else [d])
    missing = [k for k in REQUIRED if k not in files]
    if missing:
        raise FinError("VALIDATION_FAILED", "Missing Sage reports: " + ", ".join(TITLES[k] for k in missing),
                       {"missing": missing})
    cache = {k: rows_of(p) for k, p in files.items()}
    as_of = as_of_from_gl(cache["gl"])
    out: Dict[str, Any] = {"as_of": as_of.isoformat(), "files": {k: os.path.basename(p) for k, p in files.items()}}
    try:
        with tx() as conn:
            ctx = system_context(conn, actor=actor)
            ensure_years(conn, ctx, as_of)
            out["chart_and_opening"] = load_chart_and_tb(conn, ctx, files, as_of)
            out["rules"] = repoint_rules(conn, ctx)
            out["receipt_accounts"] = set_receipt_accounts(conn, ctx, cache["crj"], as_of.year)
            out["customers"] = load_customers(conn, ctx, cache["customers"])
            out["vendors"] = load_vendors(conn, ctx, cache["vendors"])
            cust = customer_lookup(conn, ctx)
            out["general_ledger"] = load_gl(conn, ctx, cache["gl"], cust)
            out["invoices"] = load_invoices(conn, ctx, cache["invoices"], cust)
            out["receipts"] = load_receipts(conn, ctx, cache["crj"], cust)
            if "gj" in cache:
                out["general_journal_check"] = check_general_journal(cache["gj"], cache["gl"])
            out["reports_kept"] = load_snapshots(conn, ctx, files, cache, as_of)
            if "recon" in cache:
                out["bank_reconciliation"] = load_recon(conn, ctx, cache["recon"], cache["tb"])
            out["tie_out"] = tie_out(conn, ctx, cache["tb"], cache["bs"], as_of)
            ex(conn, "UPDATE fin_settings SET history_replaces_opening=%s WHERE legal_entity_id=%s",
               (out["tie_out"]["ties"], ctx.entity_id))
            if out["tie_out"]["ties"]:
                out["statements"] = check_statements(conn, ctx, cache["bs"], as_of)
            ex(conn, """INSERT INTO fin_sage_reports (legal_entity_id, report_key, title, as_of, rows)
                        VALUES (%s,'import-log','Sage import result',%s,%s)
                        ON CONFLICT (legal_entity_id, report_key) DO UPDATE SET rows=EXCLUDED.rows, as_of=EXCLUDED.as_of, loaded_at=now()""",
               (ctx.entity_id, as_of, jsonb([out])))
            audit.record(conn, ctx, "SAGE_HISTORY_LOADED", "history", ctx.entity_id, metadata=json.loads(json.dumps(out, default=str)))
            if dry_run:
                raise _Rollback(json.loads(json.dumps(out, default=str)))
    except _Rollback as r:
        return {**r.out, "dry_run": True}
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Load Royan's Sage 50 exports into Roy Books")
    ap.add_argument("--dir", required=True, action="append", help="folder of exports; repeat to fall back to older folders")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    print(json.dumps(run(a.dir, a.dry_run), indent=2, default=str))


if __name__ == "__main__":
    main()
