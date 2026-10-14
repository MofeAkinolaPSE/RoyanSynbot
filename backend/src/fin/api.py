"""Roy Books HTTP API  (prefix /fin).

Thin layer: authenticate -> resolve company context -> call one domain
service inside one transaction -> JSON. Business errors are returned as
HTTP errors whose `detail` is {code, message, details} (Financial API spec
§60). No endpoint mutates financial tables directly; there is deliberately
no generic "post a journal line" or "edit a posted document" endpoint.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional

import psycopg2
from fastapi import APIRouter, Body, File, Form, HTTPException, Query, Request, UploadFile

from src.fin import (accounts, assets, audit, banking, closing, controls, dashboard, hospital, integrations, inventory,
                     journals, ledger, migration, periods, posting, purchases, report_center, reports, rules, sage_history,
                     sales, setup)
from src.fin.context import build_context
from src.fin.db import ex, plain, q, q1, tx
from src.fin import data_issues as data_issues_mod, payers, sage_uploads as sage_uploads_mod
from src.fin.errors import FinError, from_db_error, invalid, not_found

router = APIRouter(prefix="/fin", tags=["Roy Books"])

DATE_KEYS = {"journal_date", "invoice_date", "due_date", "receipt_date", "note_date", "bill_date", "payment_date",
             "voucher_date", "adjustment_date", "count_date", "loan_date", "expected_return_date", "return_date",
             "acquisition_date", "depreciation_start", "disposal_date", "statement_date", "start_date", "cutover_date",
             "refund_date",
             "expiry_date", "manufacture_date", "reversal_date", "as_of", "on"}


def _date(v: Any) -> Any:
    if v in (None, "") or isinstance(v, dt.date):
        return v or None
    try:
        return dt.date.fromisoformat(str(v)[:10])
    except ValueError:
        raise FinError("VALIDATION_FAILED", f"Not a valid date: {v!r} (use YYYY-MM-DD)")


def _dates(d: Any) -> Any:
    if isinstance(d, dict):
        return {k: (_date(v) if k in DATE_KEYS else _dates(v)) for k, v in d.items()}
    if isinstance(d, list):
        return [_dates(x) for x in d]
    return d


def _run(request: Request, fn: Callable, perm: Optional[str] = None) -> Any:
    try:
        with tx() as conn:
            ctx = build_context(request, conn)
            if perm:
                ctx.require(perm)
            return plain(fn(conn, ctx))
    except FinError as e:
        raise HTTPException(status_code=e.status, detail=e.to_detail())
    except psycopg2.Error as e:
        err = from_db_error(e)
        if err:
            raise HTTPException(status_code=err.status, detail=err.to_detail())
        raise


def _today() -> dt.date:
    return dt.date.today()


def _range(date_from: Optional[str], date_to: Optional[str]) -> tuple:
    t = _date(date_to) or _today()
    f = _date(date_from) or t.replace(day=1)
    if f > t:
        raise FinError("VALIDATION_FAILED", "'from' is after 'to'")
    return f, t


# ---------------------------------------------------------------------------
# Context & setup
# ---------------------------------------------------------------------------

@router.get("/context")
def get_context(request: Request):
    def fn(conn, ctx):
        ent = q1(conn, """SELECT e.id, e.code, e.name, e.base_currency, e.fiscal_year_start_month, o.name AS organization
                          FROM fin_legal_entities e JOIN fin_organizations o ON o.id=e.organization_id WHERE e.id=%s""", (ctx.entity_id,))
        return {"entity": ent, "entities": q(conn, "SELECT id, code, name FROM fin_legal_entities WHERE status='ACTIVE' ORDER BY name"),
                "user": {"id": ctx.actor_id, "name": ctx.actor_name, "roles": ctx.roles},
                "permissions": sorted(ctx.permissions), "period": periods.current_period(conn, ctx.entity_id),
                "settings": setup.get_settings(conn, ctx.entity_id),
                "setup": {"accounts": q1(conn, "SELECT COUNT(*) n FROM fin_accounts WHERE legal_entity_id=%s", (ctx.entity_id,))["n"],
                          "fiscal_years": q1(conn, "SELECT COUNT(*) n FROM fin_fiscal_years WHERE legal_entity_id=%s", (ctx.entity_id,))["n"],
                          "opening_posted": bool(q1(conn, "SELECT 1 FROM fin_journals WHERE legal_entity_id=%s AND journal_type='OPENING' AND status='POSTED'", (ctx.entity_id,))),
                          "products": q1(conn, "SELECT COUNT(*) n FROM fin_products WHERE legal_entity_id=%s", (ctx.entity_id,))["n"]}}
    return _run(request, fn)


@router.get("/settings")
def get_settings(request: Request):
    return _run(request, lambda c, x: setup.get_settings(c, x.entity_id), "accounting.view")


@router.put("/settings")
def put_settings(request: Request, payload: Dict[str, Any] = Body(...)):
    return _run(request, lambda c, x: setup.update_settings(c, x, _dates(payload)))


@router.get("/mappings")
def get_mappings(request: Request):
    def fn(conn, ctx):
        have = {m["mapping_key"]: m for m in setup.list_mappings(conn, ctx.entity_id)}
        return [{"mapping_key": k, "description": d, **({k2: v for k2, v in have[k].items() if k2 != "mapping_key"} if k in have else {})}
                for k, d in rules.MAPPING_KEYS.items()]
    return _run(request, fn, "accounting.view")


@router.put("/mappings/{key}")
def put_mapping(key: str, request: Request, payload: Dict[str, Any] = Body(...)):
    if key not in rules.MAPPING_KEYS:
        raise HTTPException(404, detail={"code": "RESOURCE_NOT_FOUND", "message": f"Unknown posting rule {key}"})
    return _run(request, lambda c, x: setup.set_mapping(c, x, key, payload["account_id"], payload.get("note")))


@router.get("/dashboard")
def get_dashboard(request: Request, as_of: Optional[str] = None):
    return _run(request, lambda c, x: dashboard.control_tower(c, x.entity_id, _date(as_of) or _today()), "reports.view")


# ---------------------------------------------------------------------------
# Periods
# ---------------------------------------------------------------------------

@router.get("/periods")
def list_periods(request: Request):
    return _run(request, lambda c, x: periods.list_years(c, x.entity_id), "accounting.view")


@router.post("/fiscal-years")
def create_year(request: Request, payload: Dict[str, Any] = Body(...)):
    def fn(conn, ctx):
        ctx.require("finance.period.close")
        return periods.create_fiscal_year(conn, ctx, _date(payload["start_date"]))
    return _run(request, fn)


@router.post("/fiscal-years/{fy_id}/close")
def close_year(fy_id: str, request: Request):
    return _run(request, lambda c, x: closing.close_fiscal_year(c, x, fy_id))


@router.get("/periods/{period_id}/checklist")
def period_checklist(period_id: str, request: Request):
    def fn(conn, ctx):
        p = q1(conn, "SELECT * FROM fin_periods WHERE id=%s AND legal_entity_id=%s", (period_id, ctx.entity_id))
        if not p:
            raise FinError("RESOURCE_NOT_FOUND", "Period not found")
        return {"period": p, "checklist": controls.close_checklist(conn, ctx, p)}
    return _run(request, fn, "accounting.view")


@router.post("/periods/{period_id}/close")
def close_period(period_id: str, request: Request, payload: Dict[str, Any] = Body(default={})):
    return _run(request, lambda c, x: periods.close_period(c, x, period_id, force_warnings=bool(payload.get("accept_warnings"))))


@router.post("/periods/{period_id}/reopen")
def reopen_period(period_id: str, request: Request, payload: Dict[str, Any] = Body(...)):
    return _run(request, lambda c, x: periods.reopen_period(c, x, period_id, payload.get("reason", "")))


# ---------------------------------------------------------------------------
# Chart of accounts
# ---------------------------------------------------------------------------

@router.get("/accounts")
def list_accounts(request: Request, search: Optional[str] = None, account_type: Optional[str] = None,
                  include_inactive: bool = True, history: bool = False, as_of: Optional[str] = None, used: Optional[str] = None):
    """history=true: every account with its whole-ledger balance at `as_of` (income and expense year to date),
    entries across all years and first / last entry - the chart of accounts with its history."""
    if history:
        return _run(request, lambda c, x: journals.chart_history(c, x.entity_id, _date(as_of) or _today(), search, used),
                    "accounting.view")
    return _run(request, lambda c, x: accounts.list_accounts(c, x.entity_id, search=search, account_type=account_type,
                                                              include_inactive=include_inactive), "accounting.view")


@router.post("/accounts")
def create_account(request: Request, payload: Dict[str, Any] = Body(...)):
    return _run(request, lambda c, x: accounts.create_account(c, x, payload))


@router.get("/accounts/{account_id}")
def get_account(account_id: str, request: Request):
    return _run(request, lambda c, x: accounts.get_account(c, x.entity_id, account_id), "accounting.view")


@router.patch("/accounts/{account_id}")
def patch_account(account_id: str, request: Request, payload: Dict[str, Any] = Body(...)):
    return _run(request, lambda c, x: accounts.update_account(c, x, account_id, payload))


@router.post("/accounts/{account_id}/deactivate")
def deactivate_account(account_id: str, request: Request, payload: Dict[str, Any] = Body(default={})):
    return _run(request, lambda c, x: accounts.set_status(c, x, account_id, False, payload.get("reason")))


@router.post("/accounts/{account_id}/activate")
def activate_account(account_id: str, request: Request):
    return _run(request, lambda c, x: accounts.set_status(c, x, account_id, True))


@router.get("/accounts/{account_id}/ledger")
def account_ledger(account_id: str, request: Request, date_from: Optional[str] = Query(None, alias="from"),
                   date_to: Optional[str] = Query(None, alias="to"), search: Optional[str] = None, include_voided: bool = False):
    """The account in Sage's General Ledger layout: monthly beginning balance, every line, period change."""
    def fn(conn, ctx):
        t = _date(date_to) or _today()
        f = _date(date_from) or t.replace(month=1, day=1)
        return journals.account_ledger(conn, ctx.entity_id, account_id, f, t, search, include_voided=include_voided)
    return _run(request, fn, "accounting.view")


@router.get("/ledger/journals")
def journals_by_type(request: Request):
    return _run(request, lambda c, x: journals.journal_list(), "accounting.view")


@router.get("/ledger/journal/{key}")
def journal_by_type(key: str, request: Request, date_from: Optional[str] = Query(None, alias="from"),
                    date_to: Optional[str] = Query(None, alias="to"), search: Optional[str] = None):
    def fn(conn, ctx):
        f, t = _range(date_from, date_to)
        return journals.journal(conn, ctx.entity_id, key, f, t, search)
    return _run(request, fn, "accounting.view")


@router.get("/accounts/{account_id}/activity")
def account_activity(account_id: str, request: Request, date_from: Optional[str] = Query(None, alias="from"),
                     date_to: Optional[str] = Query(None, alias="to"), limit: int = 500, offset: int = 0,
                     customer_id: Optional[int] = None, supplier_id: Optional[str] = None, product_sku: Optional[str] = None):
    def fn(conn, ctx):
        f, t = _range(date_from, date_to)
        return ledger.account_activity(conn, ctx.entity_id, account_id, f, t, limit=limit, offset=offset,
                                       customer_id=customer_id, supplier_id=supplier_id, product_sku=product_sku)
    return _run(request, fn, "accounting.view")


# ---------------------------------------------------------------------------
# Journals, GL, TB
# ---------------------------------------------------------------------------

@router.get("/journals")
def list_journals(request: Request, status: Optional[str] = None, search: Optional[str] = None,
                  date_from: Optional[str] = Query(None, alias="from"), date_to: Optional[str] = Query(None, alias="to"),
                  journal_type: Optional[str] = None, source_type: Optional[str] = None, limit: int = 100, offset: int = 0):
    return _run(request, lambda c, x: posting.list_journals(c, x.entity_id, status=status, search=search,
                                                             date_from=_date(date_from), date_to=_date(date_to),
                                                             journal_type=journal_type, source_type=source_type,
                                                             limit=limit, offset=offset), "accounting.view")


@router.post("/journals")
def create_journal(request: Request, payload: Dict[str, Any] = Body(...)):
    p = payload
    return _run(request, lambda c, x: posting.create_manual(c, x, journal_date=_date(p["journal_date"]),
                                                             description=p.get("description", ""), lines=p.get("lines") or [],
                                                             journal_type=p.get("journal_type", "MANUAL"),
                                                             idempotency_key=request.headers.get("Idempotency-Key")))


@router.get("/journals/{journal_id}")
def get_journal(journal_id: str, request: Request):
    def fn(conn, ctx):
        j = posting.get_journal(conn, ctx.entity_id, journal_id)
        j["audit"] = q(conn, """SELECT action, actor_name, reason, created_at, metadata FROM fin_audit_events
                                WHERE entity_type='journal' AND entity_id=%s ORDER BY id""", (journal_id,))
        return j
    return _run(request, fn, "accounting.view")


@router.put("/journals/{journal_id}")
def update_journal(journal_id: str, request: Request, payload: Dict[str, Any] = Body(...)):
    return _run(request, lambda c, x: posting.update_manual(c, x, journal_id, journal_date=_date(payload["journal_date"]),
                                                             description=payload.get("description", ""), lines=payload.get("lines") or []))


@router.delete("/journals/{journal_id}")
def delete_journal(journal_id: str, request: Request):
    return _run(request, lambda c, x: posting.delete_draft(c, x, journal_id) or {"deleted": journal_id})


@router.post("/journals/{journal_id}/{action}")
def journal_action(journal_id: str, action: str, request: Request, payload: Dict[str, Any] = Body(default={})):
    acts = {
        "validate": lambda c, x: posting.validate_journal(c, x, journal_id),
        "submit": lambda c, x: posting.submit(c, x, journal_id),
        "approve": lambda c, x: posting.approve(c, x, journal_id, payload.get("comment")),
        "reject": lambda c, x: posting.reject(c, x, journal_id, payload.get("reason", "")),
        "post": lambda c, x: posting.post_manual(c, x, journal_id),
        "reverse": lambda c, x: posting.reverse(c, x, journal_id, reversal_date=_date(payload.get("reversal_date")),
                                                reason=payload.get("reason", "")),
        # Delete entry: the exact reversal on the entry's own date; the pair drops out of ledger detail.
        "delete": lambda c, x: posting.reverse(c, x, journal_id, reversal_date=None,
                                               reason=f"Deleted: {payload.get('reason', '')}".strip() if payload.get("reason") else ""),
    }
    if action not in acts:
        raise HTTPException(404, detail={"code": "RESOURCE_NOT_FOUND", "message": f"Unknown action {action}"})
    return _run(request, acts[action])


@router.get("/trial-balance")
def trial_balance(request: Request, date_from: Optional[str] = Query(None, alias="from"),
                  date_to: Optional[str] = Query(None, alias="to"), include_zero: bool = False):
    def fn(conn, ctx):
        t = _date(date_to) or _today()
        f = _date(date_from) or reports._fy_start(conn, ctx.entity_id, t)
        return ledger.trial_balance(conn, ctx.entity_id, f, t, include_zero=include_zero)
    return _run(request, fn, "reports.view")


@router.get("/general-ledger")
def general_ledger(request: Request, date_from: Optional[str] = Query(None, alias="from"),
                   date_to: Optional[str] = Query(None, alias="to"), account_ids: Optional[str] = None):
    def fn(conn, ctx):
        f, t = _range(date_from, date_to)
        return ledger.general_ledger(conn, ctx.entity_id, f, t, account_ids.split(",") if account_ids else None)
    return _run(request, fn, "reports.view")


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------

@router.get("/reports/{name}")
def report(name: str, request: Request, date_from: Optional[str] = Query(None, alias="from"),
           date_to: Optional[str] = Query(None, alias="to"), as_of: Optional[str] = None,
           compare_from: Optional[str] = None, compare_to: Optional[str] = None, budget_id: Optional[str] = None,
           basis: str = "due_date", sku: Optional[str] = None, kind: Optional[str] = None,
           expiring_within_days: Optional[int] = None, party_type: Optional[str] = None, department: Optional[str] = None):
    dept = (department or "").upper() or None   # stock reports: one department (PHARMACY, LAB, IMMUNISATION...)
    def fn(conn, ctx):
        f, t = _range(date_from, date_to)
        on = _date(as_of) or t
        if name == "income-statement":
            fy = reports._fy_start(conn, ctx.entity_id, t) if not date_from else f
            return reports.income_statement(conn, ctx.entity_id, fy, t, _date(compare_from), _date(compare_to), budget_id)
        if name == "balance-sheet":
            return reports.balance_sheet(conn, ctx.entity_id, on)
        if name == "cash-flow":
            return reports.cash_flow(conn, ctx.entity_id, f, t)
        if name == "retained-earnings":
            fy = reports._fy_start(conn, ctx.entity_id, t) if not date_from else f
            return reports.retained_earnings(conn, ctx.entity_id, fy, t)
        if name == "aged-receivables":
            return reports.aged_receivables(conn, ctx.entity_id, on, basis, party_type)
        if name == "aged-payables":
            return reports.aged_payables(conn, ctx.entity_id, on, basis)
        if name == "journal":
            return reports.journal_report(conn, ctx.entity_id, kind or "sales", f, t)
        if name == "inventory-valuation":
            return reports.inventory_valuation(conn, ctx.entity_id, on, dept)
        if name == "unit-activity":
            return reports.unit_activity(conn, ctx.entity_id, f, t, sku, dept)
        if name == "stock-status":
            return reports.stock_status(conn, ctx.entity_id, dept)
        if name == "stock-position":
            return reports.stock_position(conn, ctx.entity_id)
        if name == "stock-by-department":
            return reports.stock_by_department(conn, ctx.entity_id)
        if name == "batches":
            return reports.batch_list(conn, ctx.entity_id, sku, expiring_within_days, dept)
        if name == "budget-vs-actual":
            if not budget_id:
                raise invalid("Choose a budget")
            fy = reports._fy_start(conn, ctx.entity_id, t) if not date_from else f
            return reports.budget_vs_actual(conn, ctx.entity_id, budget_id, fy, t)
        raise FinError("RESOURCE_NOT_FOUND", f"Unknown report {name}")
    return _run(request, fn, "reports.view")


@router.get("/reports/customer-statement/{customer_id}")
def customer_statement(customer_id: int, request: Request, date_from: Optional[str] = Query(None, alias="from"),
                       date_to: Optional[str] = Query(None, alias="to")):
    def fn(conn, ctx):
        t = _date(date_to) or _today()
        f = _date(date_from) or dt.date(t.year, 1, 1)
        return reports.customer_statement(conn, ctx.entity_id, customer_id, f, t)
    return _run(request, fn, "receivables.view")


@router.get("/reports/supplier-statement/{supplier_id}")
def supplier_statement(supplier_id: str, request: Request, date_from: Optional[str] = Query(None, alias="from"),
                       date_to: Optional[str] = Query(None, alias="to")):
    def fn(conn, ctx):
        t = _date(date_to) or _today()
        f = _date(date_from) or dt.date(t.year, 1, 1)
        return reports.supplier_statement(conn, ctx.entity_id, supplier_id, f, t)
    return _run(request, fn, "payables.view")


# ---------------------------------------------------------------------------
# Report Center (Sage report set) and lineage overviews
# ---------------------------------------------------------------------------

@router.get("/report-center/{key}")
def report_center_run(key: str, request: Request, date_from: Optional[str] = Query(None, alias="from"),
                      date_to: Optional[str] = Query(None, alias="to"), as_of: Optional[str] = None,
                      account_id: Optional[str] = None, customer_id: Optional[int] = None, supplier_id: Optional[str] = None,
                      sku: Optional[str] = None, bank_account_id: Optional[str] = None, month: Optional[str] = None,
                      with_balance: bool = False, name: Optional[str] = None, search: Optional[str] = None,
                      jrnl: Optional[str] = None, year: Optional[int] = None, payer: Optional[int] = None,
                      payer_type: Optional[str] = None):
    def fn(conn, ctx):
        t = _date(date_to) or _today()
        f = _date(date_from) or reports._fy_start(conn, ctx.entity_id, t)
        if f > t:
            raise FinError("VALIDATION_FAILED", "'from' is after 'to'")
        return report_center.run(conn, ctx.entity_id, key, {
            "from": f, "to": t, "as_of": _date(as_of) or t, "account_id": account_id, "customer_id": customer_id,
            "supplier_id": supplier_id, "sku": sku, "bank_account_id": bank_account_id, "month": month,
            "with_balance": with_balance, "name": name, "search": search, "jrnl": jrnl, "year": year, "payer": payer,
            "payer_type": payer_type})
    return _run(request, fn, "reports.view")


@router.get("/customers/{customer_id}/overview")
def customer_overview(customer_id: int, request: Request):
    """Customer lineage hub: who they are, what they owe, what they bought, their documents."""
    def fn(conn, ctx):
        c = sales.customer(conn, customer_id)
        today = _today()
        items = reports.ar_open_items(conn, ctx.entity_id, today, customer_id)
        invoices = q(conn, """SELECT id, invoice_number, invoice_date, due_date, total, total - amount_settled AS balance, status, is_opening
                              FROM fin_sales_invoices WHERE legal_entity_id=%s AND customer_id=%s AND status <> 'DRAFT'
                              ORDER BY invoice_date DESC LIMIT 100""", (ctx.entity_id, customer_id))
        receipts = q(conn, """SELECT id, receipt_number, receipt_date, method, reference, amount, status FROM fin_customer_receipts
                              WHERE legal_entity_id=%s AND customer_id=%s ORDER BY receipt_date DESC LIMIT 50""", (ctx.entity_id, customer_id))
        products = q(conn, """SELECT l.sku, p.name, SUM(l.quantity) AS quantity, SUM(l.line_total) AS amount, MAX(i.invoice_date) AS last_date
                              FROM fin_sales_invoice_lines l JOIN fin_sales_invoices i ON i.id=l.invoice_id
                              LEFT JOIN fin_products p ON p.legal_entity_id=i.legal_entity_id AND p.sku=l.sku
                              WHERE i.legal_entity_id=%s AND i.customer_id=%s AND l.sku IS NOT NULL AND i.status NOT IN ('DRAFT','VOID')
                              GROUP BY l.sku, p.name ORDER BY amount DESC LIMIT 50""", (ctx.entity_id, customer_id))
        loans = q(conn, """SELECT id, loan_number, sku, loan_date, quantity - quantity_returned AS outstanding, status FROM fin_stock_loans
                           WHERE legal_entity_id=%s AND customer_id=%s AND status IN ('OPEN','PARTIALLY_RETURNED')""", (ctx.entity_id, customer_id))
        # Bills raised in the hospital that are not in the books yet (posting paused, failed or before go-live).
        bills = []
        if c.get("patient_id"):
            bills = q(conn, """SELECT b.id, b.bill_number, b.status, b.patient_balance AS total, b.billed_at::date AS date,
                                      p.status AS posting_status, p.message AS posting_message
                               FROM royan_billing b
                               LEFT JOIN fin_source_postings p ON p.legal_entity_id=%s AND p.source_type='BILL' AND p.source_id=b.id::text
                               WHERE b.patient_id=%s AND b.external_source IS NULL AND COALESCE(p.status,'') <> 'POSTED'
                               ORDER BY b.billed_at DESC LIMIT 20""", (ctx.entity_id, c["patient_id"]))
        refunds = q(conn, """SELECT id, refund_number, refund_date, amount, reason, status FROM fin_customer_refunds
                             WHERE legal_entity_id=%s AND customer_id=%s ORDER BY refund_date DESC LIMIT 50""", (ctx.entity_id, customer_id))
        return {"customer": c, "balance": sum((i["open_amount"] for i in items), 0),
                "exposure": sales.customer_exposure(conn, ctx.entity_id, customer_id),
                "bills_not_in_books": bills, "refunds": refunds,
                "sage": sage_history.customer_history(conn, ctx.entity_id, customer_id),
                "overdue": sum((i["open_amount"] for i in items if i["due_date"] < today), 0),
                "open_items": items, "invoices": invoices, "receipts": receipts, "products": products, "loans": loans}
    return _run(request, fn, "receivables.view")


@router.get("/suppliers/{supplier_id}/overview")
def supplier_overview(supplier_id: str, request: Request):
    def fn(conn, ctx):
        s = purchases.supplier(conn, supplier_id)
        today = _today()
        items = reports.ap_open_items(conn, ctx.entity_id, today, supplier_id)
        bills = q(conn, """SELECT id, bill_number, supplier_invoice_number, bill_date, due_date, total, total - amount_settled AS balance, status, is_opening
                           FROM fin_supplier_bills WHERE legal_entity_id=%s AND supplier_id=%s ORDER BY bill_date DESC LIMIT 100""",
                  (ctx.entity_id, supplier_id))
        payments = q(conn, """SELECT id, payment_number, payment_date, method, reference, amount, status FROM fin_supplier_payments
                              WHERE legal_entity_id=%s AND supplier_id=%s ORDER BY payment_date DESC LIMIT 50""", (ctx.entity_id, supplier_id))
        products = q(conn, """SELECT l.sku, p.name, SUM(l.quantity) AS quantity, SUM(l.line_total) AS amount, MAX(b.bill_date) AS last_date
                              FROM fin_supplier_bill_lines l JOIN fin_supplier_bills b ON b.id=l.bill_id
                              LEFT JOIN fin_products p ON p.legal_entity_id=b.legal_entity_id AND p.sku=l.sku
                              WHERE b.legal_entity_id=%s AND b.supplier_id=%s AND l.sku IS NOT NULL AND b.status <> 'VOID'
                              GROUP BY l.sku, p.name ORDER BY amount DESC LIMIT 50""", (ctx.entity_id, supplier_id))
        history = q(conn, """SELECT h.sku, COALESCE(pr.name, MAX(h.description)) AS name, SUM(h.quantity) AS quantity,
                                    SUM(h.amount) AS amount, MAX(h.received_date) AS last_date, COUNT(DISTINCT h.po_number) AS orders
                             FROM fin_hist_purchase_lines h LEFT JOIN fin_products pr ON pr.legal_entity_id=h.legal_entity_id AND pr.sku=h.sku
                             WHERE h.legal_entity_id=%s AND h.supplier_id=%s GROUP BY h.sku, pr.name ORDER BY amount DESC LIMIT 100""",
                    (ctx.entity_id, supplier_id))
        return {"supplier": s, "balance": sum((i["open_amount"] for i in items), 0), "history_products": history,
                "sage_payments": sage_history.payee_history(conn, ctx.entity_id, s["name"]),
                "overdue": sum((i["open_amount"] for i in items if i["due_date"] < today and i["doc_type"] == "BILL"), 0),
                "open_items": items, "bills": bills, "payments": payments, "products": products}
    return _run(request, fn, "payables.view")


# ---------------------------------------------------------------------------
# Parties & products
# ---------------------------------------------------------------------------

@router.get("/customers")
def find_customers(request: Request, search: str = "", limit: int = 20):
    """Patients (name / MRN), HMOs and other debtors. Rows with id NULL have no AR account yet."""
    return _run(request, lambda c, x: hospital.party_search(c, search, limit), "receivables.view")


@router.post("/parties/ensure")
def ensure_party(request: Request, payload: Dict[str, Any] = Body(...)):
    """The AR account for a patient / HMO (created on first use), or a new corporate debtor."""
    return _run(request, lambda c, x: hospital.ensure_party(c, x, payload), "receivables.view")


@router.patch("/customers/{customer_id}")
def update_customer_terms(customer_id: int, request: Request, payload: Dict[str, Any] = Body(...)):
    return _run(request, lambda c, x: hospital.update_party_terms(c, x, customer_id, payload))


@router.get("/customers/{customer_id}/credit")
def customer_credit(customer_id: int, request: Request, amount: float = 0):
    return _run(request, lambda c, x: sales.credit_check(c, x.entity_id, customer_id, sales.money(amount)), "receivables.view")


@router.get("/suppliers")
def find_suppliers(request: Request, search: str = "", limit: int = 20):
    return _run(request, lambda c, x: q(c, """SELECT id, name, external_vendor_id AS supplier_code, payment_terms FROM suppliers
                                               WHERE name ILIKE %s OR external_vendor_id ILIKE %s ORDER BY name LIMIT %s""",
                                         (f"%{search}%", f"%{search}%", limit)), "payables.view")


@router.get("/products")
def find_products(request: Request, search: str = "", limit: int = 30, customer_id: Optional[int] = None):
    """Product search with the prefills the invoice forms need: stock on hand, the
    batch to sell next (earliest expiry first), list price and the last price
    this customer paid (Roy Books first, then Sage history)."""
    def fn(conn, ctx):
        rows = q(conn, """SELECT p.id, p.sku, p.name, p.product_type, p.standard_price, p.status, p.uom,
                                 COALESCE((SELECT SUM(qty_remaining) FROM fin_cost_layers l
                                           WHERE l.legal_entity_id=p.legal_entity_id AND l.sku=p.sku),0) AS on_hand,
                                 fb.id AS next_batch_id, fb.batch_number AS next_batch, fb.expiry_date AS next_expiry, fb.available AS next_batch_qty
                          FROM fin_products p
                          LEFT JOIN LATERAL (SELECT b.id, b.batch_number, b.expiry_date, SUM(l.qty_remaining) AS available
                                             FROM fin_cost_layers l JOIN fin_batches b ON b.id=l.batch_id
                                             WHERE l.legal_entity_id=p.legal_entity_id AND l.sku=p.sku AND l.qty_remaining > 0
                                               AND b.status='AVAILABLE' AND (b.expiry_date IS NULL OR b.expiry_date >= current_date)
                                             GROUP BY b.id ORDER BY b.expiry_date NULLS LAST LIMIT 1) fb ON TRUE
                          WHERE p.legal_entity_id=%s AND p.status='ACTIVE' AND (p.sku ILIKE %s OR p.name ILIKE %s)
                          ORDER BY (COALESCE((SELECT SUM(qty_remaining) FROM fin_cost_layers l
                                              WHERE l.legal_entity_id=p.legal_entity_id AND l.sku=p.sku),0) > 0) DESC, p.sku
                          LIMIT %s""", (ctx.entity_id, f"%{search}%", f"%{search}%", limit))
        for r in rows:
            last = None
            if customer_id:
                last = q1(conn, """SELECT l.unit_price AS price, i.invoice_date AS date FROM fin_sales_invoice_lines l
                                   JOIN fin_sales_invoices i ON i.id=l.invoice_id
                                   WHERE i.legal_entity_id=%s AND i.customer_id=%s AND l.sku=%s AND i.status NOT IN ('DRAFT','VOID')
                                   ORDER BY i.invoice_date DESC LIMIT 1""", (ctx.entity_id, customer_id, r["sku"]))
            # List price: what the pharmacy charges today (royan_pharmacy_item_rates), else the last price billed.
            recent = q1(conn, """SELECT r.sale_price AS price, NULL::date AS date FROM royan_pharmacy_item_rates r
                                 JOIN fin_products p ON p.formulary_id=r.formulary_id
                                 WHERE p.legal_entity_id=%s AND p.sku=%s AND r.sale_price > 0
                                 ORDER BY r.id DESC LIMIT 1""", (ctx.entity_id, r["sku"])) if _has_rates(conn) else None
            r["customer_last_price"] = last["price"] if last else None
            r["customer_last_date"] = last["date"] if last else None
            r["recent_price"] = recent["price"] if recent else None
            r["suggested_price"] = (r["customer_last_price"] or r["standard_price"] or r["recent_price"])
            r["last_cost"] = inventory.last_unit_cost(conn, ctx.entity_id, r["sku"]) or None
        return rows
    return _run(request, fn, "inventory.view")


def _has_rates(conn) -> bool:
    return bool(q1(conn, """SELECT 1 FROM information_schema.columns WHERE table_name='royan_pharmacy_item_rates'
                            AND column_name='sale_price'"""))


@router.post("/products")
def create_product(request: Request, payload: Dict[str, Any] = Body(...)):
    def fn(conn, ctx):
        ctx.require("inventory.product.create")
        sku = str(payload.get("sku") or "").strip()
        if not sku or not payload.get("name"):
            raise invalid("SKU and name are required")
        if q1(conn, "SELECT 1 FROM fin_products WHERE legal_entity_id=%s AND sku=%s", (ctx.entity_id, sku)):
            raise FinError("DUPLICATE_RESOURCE", f"Product {sku} already exists")
        p = q1(conn, """INSERT INTO fin_products (legal_entity_id, sku, name, product_type, uom, revenue_account_id,
                        inventory_account_id, cogs_account_id, standard_price, reorder_level)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
               (ctx.entity_id, sku, payload["name"], payload.get("product_type", "INVENTORY"), payload.get("uom", "Each"),
                payload.get("revenue_account_id"), payload.get("inventory_account_id"), payload.get("cogs_account_id"),
                payload.get("standard_price"), payload.get("reorder_level")))
        audit.record(conn, ctx, "PRODUCT_CREATED", "product", p["id"], ref=sku, after=p)
        return p
    return _run(request, fn)


@router.get("/products/{sku:path}/movements")
def product_movements(sku: str, request: Request, date_from: Optional[str] = Query(None, alias="from"),
                      date_to: Optional[str] = Query(None, alias="to")):
    def fn(conn, ctx):
        t = _date(date_to) or _today()
        f = _date(date_from) or dt.date(t.year - 1, 1, 1)
        return {"product": rules.product(conn, ctx.entity_id, sku), "on_hand": inventory.on_hand(conn, ctx.entity_id, sku),
                "movements": reports.item_movements(conn, ctx.entity_id, sku, f, t),
                "batches": reports.batch_list(conn, ctx.entity_id, sku),
                "purchase_history": q(conn, """SELECT received_date, supplier_id, supplier_name, po_number, grn_number, batch_number,
                                                     expiry_date, quantity, unit_cost, amount FROM fin_hist_purchase_lines
                                              WHERE legal_entity_id=%s AND sku=%s ORDER BY received_date DESC LIMIT 200""",
                                           (ctx.entity_id, sku))}
    return _run(request, fn, "inventory.view")


# ---------------------------------------------------------------------------
# Sales & receivables
# ---------------------------------------------------------------------------

@router.get("/sales/invoices")
def list_invoices(request: Request, customer_id: Optional[int] = None, status: Optional[str] = None, search: Optional[str] = None,
                  date_from: Optional[str] = Query(None, alias="from"), date_to: Optional[str] = Query(None, alias="to"),
                  open_only: bool = False, limit: int = 100, offset: int = 0):
    return _run(request, lambda c, x: sales.list_invoices(c, x.entity_id, customer_id=customer_id, status=status, search=search,
                                                           date_from=_date(date_from), date_to=_date(date_to),
                                                           open_only=open_only, limit=limit, offset=offset), "receivables.view")


@router.post("/sales/invoices")
def create_invoice(request: Request, payload: Dict[str, Any] = Body(...)):
    def fn(conn, ctx):
        p = _dates(payload)
        inv = sales.create_invoice(conn, ctx, p)
        if p.get("post"):
            inv = sales.post_invoice(conn, ctx, str(inv["id"]), override_credit=bool(p.get("override_credit")),
                                     override_reason=p.get("override_reason"))
        return inv
    return _run(request, fn)


@router.get("/sales/invoices/{invoice_id}")
def get_invoice(invoice_id: str, request: Request):
    return _run(request, lambda c, x: sales.get_invoice(c, x.entity_id, invoice_id), "receivables.view")


@router.post("/sales/invoices/{invoice_id}/post")
def post_invoice(invoice_id: str, request: Request, payload: Dict[str, Any] = Body(default={})):
    return _run(request, lambda c, x: sales.post_invoice(c, x, invoice_id, override_credit=bool(payload.get("override_credit")),
                                                          override_reason=payload.get("override_reason")))


@router.post("/sales/invoices/{invoice_id}/void")
def void_invoice(invoice_id: str, request: Request, payload: Dict[str, Any] = Body(...)):
    return _run(request, lambda c, x: sales.void_invoice(c, x, invoice_id, payload.get("reason", ""), _date(payload.get("on"))))


@router.get("/sales/credit-notes")
def list_credit_notes(request: Request, limit: int = 100, offset: int = 0):
    return _run(request, lambda c, x: sales.list_credit_notes(c, x.entity_id, limit, offset), "receivables.view")


@router.post("/sales/credit-notes")
def create_credit_note(request: Request, payload: Dict[str, Any] = Body(...)):
    return _run(request, lambda c, x: sales.create_credit_note(c, x, _dates(payload)))


@router.get("/sales/credit-notes/{cn_id}")
def get_credit_note(cn_id: str, request: Request):
    return _run(request, lambda c, x: sales.get_credit_note(c, x.entity_id, cn_id), "receivables.view")


@router.post("/sales/credit-notes/{cn_id}/allocate")
def allocate_credit_note(cn_id: str, request: Request, payload: Dict[str, Any] = Body(...)):
    return _run(request, lambda c, x: sales.allocate_credit_note(c, x, cn_id, payload.get("allocations") or []))


@router.get("/receivables/open-items")
def ar_open_items(request: Request, customer_id: int, as_of: Optional[str] = None):
    return _run(request, lambda c, x: reports.ar_open_items(c, x.entity_id, _date(as_of) or _today(), customer_id), "receivables.view")


@router.get("/receivables/receipts")
def list_receipts(request: Request, customer_id: Optional[int] = None, search: Optional[str] = None,
                  date_from: Optional[str] = Query(None, alias="from"), date_to: Optional[str] = Query(None, alias="to"),
                  limit: int = 100, offset: int = 0):
    return _run(request, lambda c, x: sales.list_receipts(c, x.entity_id, customer_id=customer_id, search=search,
                                                           date_from=_date(date_from), date_to=_date(date_to),
                                                           limit=limit, offset=offset), "receivables.view")


@router.post("/receivables/receipts")
def create_receipt(request: Request, payload: Dict[str, Any] = Body(...)):
    return _run(request, lambda c, x: sales.create_receipt(c, x, _dates(payload)))


@router.get("/receivables/receipts/{receipt_id}")
def get_receipt(receipt_id: str, request: Request):
    return _run(request, lambda c, x: sales.get_receipt(c, x.entity_id, receipt_id), "receivables.view")


@router.post("/receivables/receipts/{receipt_id}/allocate")
def allocate_receipt(receipt_id: str, request: Request, payload: Dict[str, Any] = Body(...)):
    return _run(request, lambda c, x: sales.allocate_receipt(c, x, receipt_id, payload.get("allocations") or []))


@router.post("/receivables/receipts/{receipt_id}/void")
def void_receipt(receipt_id: str, request: Request, payload: Dict[str, Any] = Body(...)):
    return _run(request, lambda c, x: sales.void_receipt(c, x, receipt_id, payload.get("reason", ""), _date(payload.get("on"))))


@router.get("/receivables/refunds")
def list_refunds(request: Request, limit: int = 100, offset: int = 0):
    return _run(request, lambda c, x: sales.list_refunds(c, x.entity_id, limit, offset), "receivables.view")


@router.post("/receivables/refunds")
def create_refund(request: Request, payload: Dict[str, Any] = Body(...)):
    return _run(request, lambda c, x: sales.create_refund(c, x, _dates(payload)))


@router.get("/receivables/refunds/{refund_id}")
def get_refund(refund_id: str, request: Request):
    return _run(request, lambda c, x: sales.get_refund(c, x.entity_id, refund_id), "receivables.view")


# ---------------------------------------------------------------------------
# Payables
# ---------------------------------------------------------------------------

@router.get("/payables/bills")
def list_bills(request: Request, supplier_id: Optional[str] = None, search: Optional[str] = None, open_only: bool = False,
               date_from: Optional[str] = Query(None, alias="from"), date_to: Optional[str] = Query(None, alias="to"),
               limit: int = 100, offset: int = 0):
    return _run(request, lambda c, x: purchases.list_bills(c, x.entity_id, supplier_id=supplier_id, search=search,
                                                            open_only=open_only, date_from=_date(date_from), date_to=_date(date_to),
                                                            limit=limit, offset=offset), "payables.view")


@router.post("/payables/bills")
def create_bill(request: Request, payload: Dict[str, Any] = Body(...)):
    return _run(request, lambda c, x: purchases.create_bill(c, x, _dates(payload)))


@router.get("/payables/bills/{bill_id}")
def get_bill(bill_id: str, request: Request):
    return _run(request, lambda c, x: purchases.get_bill(c, x.entity_id, bill_id), "payables.view")


@router.post("/payables/bills/{bill_id}/void")
def void_bill(bill_id: str, request: Request, payload: Dict[str, Any] = Body(...)):
    return _run(request, lambda c, x: purchases.void_bill(c, x, bill_id, payload.get("reason", "")))


@router.get("/payables/open-items")
def ap_open_items(request: Request, supplier_id: str, as_of: Optional[str] = None):
    return _run(request, lambda c, x: reports.ap_open_items(c, x.entity_id, _date(as_of) or _today(), supplier_id), "payables.view")


@router.get("/payables/payments")
def list_payments(request: Request, supplier_id: Optional[str] = None, search: Optional[str] = None,
                  date_from: Optional[str] = Query(None, alias="from"), date_to: Optional[str] = Query(None, alias="to"),
                  limit: int = 100, offset: int = 0):
    return _run(request, lambda c, x: purchases.list_payments(c, x.entity_id, supplier_id=supplier_id, search=search,
                                                               date_from=_date(date_from), date_to=_date(date_to),
                                                               limit=limit, offset=offset), "payables.view")


@router.post("/payables/payments")
def create_payment(request: Request, payload: Dict[str, Any] = Body(...)):
    return _run(request, lambda c, x: purchases.create_payment(c, x, _dates(payload)))


@router.get("/payables/payments/{payment_id}")
def get_payment(payment_id: str, request: Request):
    return _run(request, lambda c, x: purchases.get_payment(c, x.entity_id, payment_id), "payables.view")


@router.post("/payables/payments/{payment_id}/allocate")
def allocate_payment(payment_id: str, request: Request, payload: Dict[str, Any] = Body(...)):
    return _run(request, lambda c, x: purchases.allocate_payment(c, x, payment_id, payload.get("allocations") or []))


@router.post("/payables/payments/{payment_id}/void")
def void_payment(payment_id: str, request: Request, payload: Dict[str, Any] = Body(...)):
    return _run(request, lambda c, x: purchases.void_payment(c, x, payment_id, payload.get("reason", "")))


@router.get("/payables/debit-notes")
def list_debit_notes(request: Request, limit: int = 100, offset: int = 0):
    return _run(request, lambda c, x: purchases.list_debit_notes(c, x.entity_id, limit, offset), "payables.view")


@router.post("/payables/debit-notes")
def create_debit_note(request: Request, payload: Dict[str, Any] = Body(...)):
    return _run(request, lambda c, x: purchases.create_debit_note(c, x, _dates(payload)))


@router.get("/payables/debit-notes/{dn_id}")
def get_debit_note(dn_id: str, request: Request):
    return _run(request, lambda c, x: purchases.get_debit_note(c, x.entity_id, dn_id), "payables.view")


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------

@router.get("/inventory/departments")
def department_stock_overview(request: Request):
    """Stock by department: the pharmacy (in the books) and every other department store."""
    from src.fin import dept_stock
    return _run(request, lambda c, x: {"departments": dept_stock.overview(c, x.entity_id),
                                       "pharmacy": reports.stock_position(c, x.entity_id)}, "inventory.view")


@router.get("/inventory/departments/{department}/usage")
def department_stock_usage(department: str, request: Request):
    """What the department used (Immunisation: the vaccines given)."""
    from src.fin import dept_stock
    return _run(request, lambda c, x: dept_stock.usage(c, department.upper()), "inventory.view")


@router.get("/inventory/departments/{department}")
def department_stock_items(department: str, request: Request, include_empty: bool = False):
    from src.fin import dept_stock
    return _run(request, lambda c, x: dept_stock.items(c, department.upper(), include_empty), "inventory.view")


@router.post("/inventory/departments/{department}/items")
def department_stock_add(department: str, request: Request, payload: Dict[str, Any] = Body(...)):
    from src.fin import dept_stock
    return _run(request, lambda c, x: dept_stock.add_item(c, x, {**_dates(payload), "department": department}))


@router.post("/inventory/departments/{department}/confirm")
def department_stock_confirm(department: str, request: Request, payload: Dict[str, Any] = Body(default={})):
    from src.fin import dept_stock
    return _run(request, lambda c, x: dept_stock.confirm(c, x, department, _date(payload.get("date"))))


@router.get("/inventory/department-stock/{stock_id}")
def department_stock_item(stock_id: int, request: Request):
    """One batch on a department store's shelf, with the other batches of the same item."""
    def fn(conn, ctx):
        r = q1(conn, """SELECT s.*, s.quantity * COALESCE(s.unit_cost,0) AS value, (s.expiry_date < current_date) AS expired
                        FROM royan_department_stock s WHERE s.id=%s""", (stock_id,))
        if not r:
            raise not_found("Department stock", stock_id)
        r["batches"] = q(conn, """SELECT id, batch_number, expiry_date, quantity, unit_cost, quantity * COALESCE(unit_cost,0) AS value
                                  FROM royan_department_stock WHERE department=%s AND item_name=%s AND is_active
                                  ORDER BY expiry_date NULLS LAST""", (r["department"], r["item_name"]))
        return r
    return _run(request, fn, "inventory.view")


@router.get("/inventory/department-stock/{stock_id}/moves")
def department_stock_moves(stock_id: int, request: Request):
    from src.fin import dept_stock
    return _run(request, lambda c, x: dept_stock.moves(c, stock_id), "inventory.view")


@router.post("/inventory/department-stock/{stock_id}/adjust")
def department_stock_adjust(stock_id: int, request: Request, payload: Dict[str, Any] = Body(...)):
    from src.fin import dept_stock
    return _run(request, lambda c, x: dept_stock.adjust(c, x, stock_id, _dates(payload)))


@router.get("/inventory/adjustments")
def list_adjustments(request: Request, limit: int = 100):
    return _run(request, lambda c, x: q(c, """SELECT a.*, (SELECT COUNT(*) FROM fin_stock_adjustment_lines l WHERE l.adjustment_id=a.id) AS lines
                                               FROM fin_stock_adjustments a WHERE a.legal_entity_id=%s
                                               ORDER BY a.adjustment_date DESC, a.adjustment_number DESC LIMIT %s""",
                                         (x.entity_id, limit)), "inventory.view")


@router.post("/inventory/adjustments")
def create_adjustment(request: Request, payload: Dict[str, Any] = Body(...)):
    def fn(conn, ctx):
        adj = inventory.create_adjustment(conn, ctx, _dates(payload))
        if payload.get("post"):
            adj = inventory.post_adjustment(conn, ctx, str(adj["id"]))
        return adj
    return _run(request, fn)


@router.get("/inventory/adjustments/{adj_id}")
def get_adjustment(adj_id: str, request: Request):
    return _run(request, lambda c, x: inventory.get_adjustment(c, x.entity_id, adj_id), "inventory.view")


@router.post("/inventory/adjustments/{adj_id}/post")
def post_adjustment(adj_id: str, request: Request):
    return _run(request, lambda c, x: inventory.post_adjustment(c, x, adj_id))


@router.get("/inventory/counts")
def list_counts(request: Request):
    return _run(request, lambda c, x: q(c, """SELECT s.*, (SELECT COUNT(*) FROM fin_stock_count_lines l WHERE l.count_id=s.id) AS lines
                                               FROM fin_stock_counts s WHERE s.legal_entity_id=%s ORDER BY s.count_date DESC""",
                                         (x.entity_id,)), "inventory.view")


@router.post("/inventory/counts")
def create_count(request: Request, payload: Dict[str, Any] = Body(...)):
    return _run(request, lambda c, x: inventory.create_count(c, x, _date(payload["count_date"]), payload.get("skus"), payload.get("notes")))


@router.get("/inventory/counts/overview")
def count_overview(request: Request):
    return _run(request, lambda c, x: hospital.count_overview(c, x.entity_id), "inventory.view")


@router.post("/inventory/batches/{ops_batch_id}/unit-cost")
def set_batch_unit_cost(ops_batch_id: int, request: Request, payload: Dict[str, Any] = Body(...)):
    """Enter a pharmacy batch's unit cost; a batch not yet in the books is brought in at that cost."""
    return _run(request, lambda c, x: hospital.set_batch_unit_cost(c, x, ops_batch_id, payload.get("unit_cost"), payload.get("reason")))


@router.get("/inventory/counts/{count_id}")
def get_count(count_id: str, request: Request):
    return _run(request, lambda c, x: inventory.get_count(c, x.entity_id, count_id), "inventory.view")


@router.put("/inventory/counts/{count_id}/lines")
def record_count(count_id: str, request: Request, payload: Dict[str, Any] = Body(...)):
    return _run(request, lambda c, x: inventory.record_count(c, x, count_id, payload.get("lines") or []))


@router.post("/inventory/counts/{count_id}/post")
def post_count(count_id: str, request: Request):
    return _run(request, lambda c, x: inventory.post_count(c, x, count_id))


@router.get("/inventory/loans")
def list_loans(request: Request, status: Optional[str] = None):
    def fn(conn, ctx):
        sf = " AND l.status = ANY(%s)" if status else ""
        p = [ctx.entity_id] + ([status.split(",")] if status else [])
        return q(conn, f"""SELECT l.*, c.name AS customer_name, b.batch_number, (l.quantity - l.quantity_returned) AS outstanding
                           FROM fin_stock_loans l LEFT JOIN fin_v_customers c ON c.id=l.customer_id LEFT JOIN fin_batches b ON b.id=l.batch_id
                           WHERE l.legal_entity_id=%s {sf} ORDER BY l.loan_date DESC""", p)
    return _run(request, fn, "inventory.view")


@router.post("/inventory/loans")
def create_loan(request: Request, payload: Dict[str, Any] = Body(...)):
    return _run(request, lambda c, x: inventory.create_loan(c, x, _dates(payload)))


@router.get("/inventory/loans/{loan_id}")
def get_loan(loan_id: str, request: Request):
    return _run(request, lambda c, x: inventory.get_loan(c, x.entity_id, loan_id), "inventory.view")


@router.post("/inventory/loans/{loan_id}/return")
def return_loan(loan_id: str, request: Request, payload: Dict[str, Any] = Body(...)):
    return _run(request, lambda c, x: inventory.return_loan(c, x, loan_id, _dates(payload)))


@router.post("/inventory/loans/{loan_id}/write-off")
def write_off_loan(loan_id: str, request: Request, payload: Dict[str, Any] = Body(...)):
    return _run(request, lambda c, x: inventory.write_off_loan(c, x, loan_id, payload.get("reason", ""), _date(payload.get("on")) or _today()))


@router.get("/inventory/batches/{batch_id}/trace")
def trace_batch(batch_id: str, request: Request):
    return _run(request, lambda c, x: inventory.trace_batch(c, x.entity_id, batch_id), "inventory.view")


@router.get("/inventory/batch-search")
def batch_search(request: Request, search: str = ""):
    return _run(request, lambda c, x: q(c, """SELECT b.id, b.sku, b.batch_number, b.expiry_date, b.status, p.name AS product_name
                                               FROM fin_batches b LEFT JOIN fin_products p ON p.legal_entity_id=b.legal_entity_id AND p.sku=b.sku
                                               WHERE b.legal_entity_id=%s AND (b.batch_number ILIKE %s OR b.sku ILIKE %s)
                                               ORDER BY b.expiry_date NULLS LAST LIMIT 30""", (x.entity_id, f"%{search}%", f"%{search}%")),
                "inventory.view")


@router.post("/inventory/batches/{batch_id}/status")
def batch_status(batch_id: str, request: Request, payload: Dict[str, Any] = Body(...)):
    return _run(request, lambda c, x: inventory.set_batch_status(c, x, batch_id, payload["status"], payload.get("reason", "")))


@router.get("/inventory/recalls")
def list_recalls(request: Request):
    return _run(request, lambda c, x: q(c, """SELECT r.*, b.batch_number, (SELECT COUNT(*) FROM fin_recall_items i WHERE i.recall_id=r.id) AS customers
                                               FROM fin_recalls r JOIN fin_batches b ON b.id=r.batch_id WHERE r.legal_entity_id=%s
                                               ORDER BY r.opened_at DESC""", (x.entity_id,)), "inventory.view")


@router.post("/inventory/recalls")
def open_recall(request: Request, payload: Dict[str, Any] = Body(...)):
    return _run(request, lambda c, x: inventory.open_recall(c, x, payload))


@router.get("/inventory/recalls/{recall_id}")
def get_recall(recall_id: str, request: Request):
    return _run(request, lambda c, x: inventory.get_recall(c, x.entity_id, recall_id), "inventory.view")


@router.patch("/inventory/recalls/{recall_id}/items/{item_id}")
def update_recall_item(recall_id: str, item_id: str, request: Request, payload: Dict[str, Any] = Body(...)):
    return _run(request, lambda c, x: inventory.update_recall_item(c, x, recall_id, item_id, payload))


@router.post("/inventory/recalls/{recall_id}/close")
def close_recall(recall_id: str, request: Request, payload: Dict[str, Any] = Body(default={})):
    return _run(request, lambda c, x: inventory.close_recall(c, x, recall_id, payload.get("notes")))


# ---------------------------------------------------------------------------
# Banking
# ---------------------------------------------------------------------------

@router.get("/banking/accounts")
def bank_accounts(request: Request):
    return _run(request, lambda c, x: banking.list_accounts(c, x.entity_id), "banking.view")


@router.delete("/banking/accounts/{bank_id}")
def remove_bank_account(bank_id: str, request: Request):
    """Remove a bank / cash account. One that has never been used is deleted; one with entries is closed instead
    (its history must stay for the audit) and stops appearing in the pick lists."""
    def fn(conn, ctx):
        ctx.require("banking.account.create")
        b = q1(conn, "SELECT * FROM fin_bank_accounts WHERE id=%s AND legal_entity_id=%s", (bank_id, ctx.entity_id))
        if not b:
            raise not_found("Bank account", bank_id)
        used = q1(conn, """SELECT (SELECT COUNT(*) FROM fin_journal_lines WHERE account_id=%s)
                                + (SELECT COUNT(*) FROM fin_customer_receipts WHERE bank_account_id=%s)
                                + (SELECT COUNT(*) FROM fin_supplier_payments WHERE bank_account_id=%s) AS n""",
                  (b["gl_account_id"], bank_id, bank_id))["n"]
        mapped = q1(conn, """SELECT 1 FROM fin_settings WHERE legal_entity_id=%s AND receipt_accounts::text LIKE %s""",
                    (ctx.entity_id, f"%{bank_id}%"))
        if mapped:
            raise invalid("This account receives the cashier's payments (Setup › Settings) - choose another account there first")
        if used:
            ex(conn, "UPDATE fin_bank_accounts SET status='INACTIVE' WHERE id=%s", (bank_id,))
            result = "closed"
        else:
            ex(conn, "DELETE FROM fin_bank_accounts WHERE id=%s", (bank_id,))
            result = "deleted"
        from src.fin import audit as _audit
        _audit.record(conn, ctx, "BANK_ACCOUNT_REMOVED", "bank_account", bank_id, metadata={"result": result, "name": b["name"]})
        return {"ok": True, "result": result}
    return _run(request, fn)


@router.post("/banking/accounts")
def create_bank_account(request: Request, payload: Dict[str, Any] = Body(...)):
    return _run(request, lambda c, x: banking.create_account(c, x, payload))


@router.get("/banking/vouchers")
def list_vouchers(request: Request, kind: Optional[str] = None, bank_account_id: Optional[str] = None, search: Optional[str] = None,
                  date_from: Optional[str] = Query(None, alias="from"), date_to: Optional[str] = Query(None, alias="to"),
                  limit: int = 100, offset: int = 0):
    return _run(request, lambda c, x: banking.list_vouchers(c, x.entity_id, kind=kind, bank_account_id=bank_account_id, search=search,
                                                             date_from=_date(date_from), date_to=_date(date_to),
                                                             limit=limit, offset=offset), "banking.view")


@router.post("/banking/vouchers")
def create_voucher(request: Request, payload: Dict[str, Any] = Body(...)):
    return _run(request, lambda c, x: banking.create_voucher(c, x, _dates(payload)))


@router.get("/banking/vouchers/{voucher_id}")
def get_voucher(voucher_id: str, request: Request):
    return _run(request, lambda c, x: banking.get_voucher(c, x.entity_id, voucher_id), "banking.view")


@router.post("/banking/vouchers/{voucher_id}/void")
def void_voucher(voucher_id: str, request: Request, payload: Dict[str, Any] = Body(...)):
    return _run(request, lambda c, x: banking.void_voucher(c, x, voucher_id, payload.get("reason", "")))


@router.get("/banking/statements")
def list_statements(request: Request, bank_account_id: Optional[str] = None):
    return _run(request, lambda c, x: banking.list_statements(c, x.entity_id, bank_account_id), "banking.view")


@router.post("/banking/statements")
async def import_statement(request: Request, bank_account_id: str = Form(...), statement_date: str = Form(...),
                           closing_balance: str = Form(...), opening_balance: Optional[str] = Form(None),
                           file: UploadFile = File(...)):
    raw = await file.read()

    def fn(conn, ctx):
        lines = banking.parse_statement_csv(raw.decode("utf-8-sig", errors="replace"))
        return banking.import_statement(conn, ctx, bank_account_id, statement_date=_date(statement_date),
                                        closing_balance=closing_balance, opening_balance=opening_balance, lines=lines,
                                        source_file=file.filename)
    return _run(request, fn)


@router.get("/banking/statements/{statement_id}")
def get_statement(statement_id: str, request: Request):
    return _run(request, lambda c, x: banking.get_statement(c, x.entity_id, statement_id), "banking.view")


@router.post("/banking/statements/{statement_id}/auto-match")
def auto_match(statement_id: str, request: Request):
    def fn(conn, ctx):
        ctx.require("banking.reconcile")
        banking.auto_match(conn, ctx, statement_id)
        return banking.get_statement(conn, ctx.entity_id, statement_id)
    return _run(request, fn)


@router.post("/banking/statement-lines/{line_id}/match")
def match_line(line_id: str, request: Request, payload: Dict[str, Any] = Body(...)):
    return _run(request, lambda c, x: banking.match_line(c, x, line_id, payload.get("journal_line_id"),
                                                          payload.get("status", "MATCHED"), payload.get("note")))


@router.post("/banking/statements/{statement_id}/complete")
def complete_reconciliation(statement_id: str, request: Request):
    return _run(request, lambda c, x: banking.complete_reconciliation(c, x, statement_id))


# ---------------------------------------------------------------------------
# Fixed assets
# ---------------------------------------------------------------------------

@router.get("/assets/categories")
def asset_categories(request: Request):
    return _run(request, lambda c, x: assets.list_categories(c, x.entity_id), "assets.view")


@router.post("/assets/categories")
def create_asset_category(request: Request, payload: Dict[str, Any] = Body(...)):
    return _run(request, lambda c, x: assets.create_category(c, x, payload))


@router.get("/assets")
def list_assets(request: Request):
    return _run(request, lambda c, x: assets.list_assets(c, x.entity_id), "assets.view")


@router.post("/assets")
def register_asset(request: Request, payload: Dict[str, Any] = Body(...)):
    return _run(request, lambda c, x: assets.register_asset(c, x, _dates(payload)))


@router.get("/assets/depreciation/preview")
def depreciation_preview(request: Request, period_id: str):
    return _run(request, lambda c, x: assets.preview_depreciation(c, x.entity_id, period_id), "assets.view")


@router.post("/assets/depreciation/run")
def depreciation_run(request: Request, payload: Dict[str, Any] = Body(...)):
    return _run(request, lambda c, x: assets.run_depreciation(c, x, payload["period_id"]))


@router.get("/assets/history")
def asset_history(request: Request, as_of: Optional[str] = None):
    """Assets in the books: every fixed-asset account from the ledger, with each purchase, disposal and depreciation."""
    return _run(request, lambda c, x: assets.asset_history(c, x.entity_id, _date(as_of) or _today()), "assets.view")


@router.get("/assets/{asset_id}")
def get_asset(asset_id: str, request: Request):
    return _run(request, lambda c, x: assets.get_asset(c, x.entity_id, asset_id), "assets.view")


@router.post("/assets/{asset_id}/dispose")
def dispose_asset(asset_id: str, request: Request, payload: Dict[str, Any] = Body(...)):
    return _run(request, lambda c, x: assets.dispose_asset(c, x, asset_id, _dates(payload)))


# ---------------------------------------------------------------------------
# Budgets
# ---------------------------------------------------------------------------

@router.get("/budgets")
def list_budgets(request: Request):
    return _run(request, lambda c, x: closing.list_budgets(c, x.entity_id), "budget.view")


@router.post("/budgets")
def create_budget(request: Request, payload: Dict[str, Any] = Body(...)):
    return _run(request, lambda c, x: closing.create_budget(c, x, payload["fiscal_year_id"], payload["name"]))


@router.get("/budgets/{budget_id}")
def get_budget(budget_id: str, request: Request):
    return _run(request, lambda c, x: closing.get_budget(c, x.entity_id, budget_id), "budget.view")


@router.put("/budgets/{budget_id}/lines")
def set_budget_lines(budget_id: str, request: Request, payload: Dict[str, Any] = Body(...)):
    return _run(request, lambda c, x: closing.set_budget_lines(c, x, budget_id, payload.get("lines") or []))


@router.post("/budgets/{budget_id}/approve")
def approve_budget(budget_id: str, request: Request):
    return _run(request, lambda c, x: closing.approve_budget(c, x, budget_id))


# ---------------------------------------------------------------------------
# Controls, audit, integrations
# ---------------------------------------------------------------------------

@router.get("/controls/run")
def run_controls(request: Request, as_of: Optional[str] = None):
    return _run(request, lambda c, x: controls.run_and_store(c, x, _date(as_of) or _today()), "controls.view")


@router.get("/controls/history")
def control_history(request: Request):
    return _run(request, lambda c, x: q(c, """SELECT id, as_of, fail_count, run_by, run_at FROM fin_control_runs
                                               WHERE legal_entity_id=%s ORDER BY run_at DESC LIMIT 30""", (x.entity_id,)),
                "controls.view")


@router.get("/ledgers/customers")
def customer_ledgers(request: Request, search: str = "", status: str = "", party_type: str = "", source: str = "books", limit: int = 300):
    """Every customer is a ledger (finance meeting): the books since go-live, each patient's Hope history, or HMOs and
    companies (Hope billing less Sage receipts) - see fin/ledgers.py."""
    from src.fin import ledgers
    return _run(request, lambda c, x: ledgers.customers(c, x.entity_id, source=source, search=search, status=status,
                                                        party_type=party_type, limit=limit), "receivables.view")


@router.get("/hope/purchases")
def hope_purchases(request: Request, date_from: Optional[str] = Query(None, alias="from"), date_to: Optional[str] = Query(None, alias="to"),
                   supplier_id: Optional[str] = None, search: str = "", limit: int = 500):
    """Hope's goods-received records (2016-2026): purchases by supplier before go-live - history, not the books."""
    from src.fin import ledgers
    def fn(conn, ctx):
        f, t = _range(date_from, date_to)
        return ledgers.hope_purchases(conn, date_from=f, date_to=t, supplier_id=supplier_id, search=search, limit=limit, entity_id=ctx.entity_id)
    return _run(request, fn, "payables.view")


@router.get("/hope/purchases/{hope_id}")
def hope_purchase(hope_id: int, request: Request):
    from src.fin import ledgers
    return _run(request, lambda c, x: ledgers.hope_purchase(c, hope_id), "payables.view")


@router.get("/ledgers/sage-gl")
def sage_general_ledger(request: Request, date_from: Optional[str] = Query(None, alias="from"), date_to: Optional[str] = Query(None, alias="to"),
                        account_ids: Optional[str] = None, search: Optional[str] = None):
    """The General Ledger in Sage 50's layout (financemeetings/Gl.xlsx): by Account ID, monthly Beginning Balance /
    transactions / Current Period Change, then Ending Balance."""
    from src.fin import sage_gl
    def fn(conn, ctx):
        f, t = _range(date_from, date_to)
        return sage_gl.general_ledger(conn, ctx.entity_id, f, t, account_ids.split(",") if account_ids else None, search)
    return _run(request, fn, "accounting.view")


@router.get("/ledgers/customer-gl")
def sage_customer_ledger(request: Request, date_from: Optional[str] = Query(None, alias="from"), date_to: Optional[str] = Query(None, alias="to"),
                         customer_id: Optional[int] = None, patient_id: Optional[int] = None, search: str = "", party_type: str = "",
                         limit: int = 300):
    """Customer Ledgers in the same Sage layout, customers A-Z: from the receivables lines (Sage history + Roy Books),
    or one patient's account from the hospital's records (patient_id)."""
    from src.fin import sage_gl
    def fn(conn, ctx):
        f, t = _range(date_from, date_to)
        if patient_id:
            return sage_gl.patient_hope_ledger(conn, patient_id, f, t)
        return sage_gl.customer_ledger(conn, ctx.entity_id, f, t, customer_id=customer_id, search=search, party_type=party_type, limit=limit)
    return _run(request, fn, "receivables.view")


@router.get("/ledgers/payer-aging")
def aged_receivables_history(request: Request, as_of: Optional[str] = None):
    """HMO and company balances before go-live, aged (Hope billing less Sage receipts)."""
    from src.fin import ledgers
    return _run(request, lambda c, x: ledgers.payer_aging(c, x.entity_id, _date(as_of)), "receivables.view")


@router.get("/ledgers/suppliers")
def supplier_ledgers(request: Request, search: str = "", status: str = "", limit: int = 300):
    """Every supplier is a ledger: billed, paid (and WHT withheld), returned, and what is still owed."""
    def fn(conn, ctx):
        rows = q(conn, """
            WITH b AS (SELECT supplier_id, SUM(total) AS billed, COUNT(*) AS bills, MAX(bill_date) AS last_bill
                       FROM fin_supplier_bills WHERE legal_entity_id=%s AND status NOT IN ('DRAFT','VOID') GROUP BY 1),
                 p AS (SELECT supplier_id, SUM(amount + wht_amount) AS paid, SUM(wht_amount) AS wht, MAX(payment_date) AS last_payment
                       FROM fin_supplier_payments WHERE legal_entity_id=%s AND status <> 'VOID' GROUP BY 1),
                 d AS (SELECT supplier_id, SUM(total) AS returned FROM fin_debit_notes
                       WHERE legal_entity_id=%s AND status <> 'VOID' GROUP BY 1),
                 h AS (SELECT supplier_id, SUM(net_amount) AS hope_purchased, COUNT(*) AS hope_grns, MAX(received_date) AS hope_last
                       FROM fin_hope_purchases WHERE supplier_id IS NOT NULL GROUP BY 1)
            SELECT s.id::text AS id, s.name, COALESCE(b.bills,0) AS bills, COALESCE(b.billed,0) AS billed, COALESCE(p.paid,0) AS paid,
                   COALESCE(p.wht,0) AS wht, COALESCE(d.returned,0) AS returned,
                   COALESCE(b.billed,0) - COALESCE(p.paid,0) - COALESCE(d.returned,0) AS balance,
                   GREATEST(b.last_bill, p.last_payment) AS last_activity,
                   COALESCE(h.hope_purchased,0) AS hope_purchased, COALESCE(h.hope_grns,0) AS hope_grns, h.hope_last
            FROM suppliers s LEFT JOIN b ON b.supplier_id=s.id LEFT JOIN p ON p.supplier_id=s.id LEFT JOIN d ON d.supplier_id=s.id
            LEFT JOIN h ON h.supplier_id=s.id
            WHERE (b.supplier_id IS NOT NULL OR p.supplier_id IS NOT NULL OR d.supplier_id IS NOT NULL OR h.supplier_id IS NOT NULL)
              AND (%s = '' OR s.name ILIKE %s)
            ORDER BY lower(s.name) LIMIT %s""", (ctx.entity_id,) * 3 + (search, f"%{search}%", limit))
        for r in rows:
            v = Decimal(str(r["balance"]))
            r["status"] = "OWED" if v > 0 else "IN_CREDIT" if v < 0 else "PAID"
        if status:
            rows = [r for r in rows if r["status"] == status.upper()]
        return {"rows": rows}
    return _run(request, fn, "payables.view")


@router.post("/validation-events/{event_id}/resolve")
def resolve_validation_event(event_id: str, request: Request, payload: Dict[str, Any] = Body(...)):
    """Close an exception once it has been looked into, with what was found."""
    def fn(conn, ctx):
        ctx.require("controls.resolve")
        note = (payload.get("note") or "").strip()
        if not note:
            raise invalid("Say how it was resolved")
        r = q1(conn, """UPDATE fin_validation_events SET status='RESOLVED', resolved_by=%s, resolved_at=now(), resolution_note=%s
                        WHERE id=%s AND legal_entity_id=%s AND status <> 'RESOLVED' RETURNING *""",
               (ctx.actor_id, note, event_id, ctx.entity_id))
        if not r:
            raise not_found("Exception", event_id)
        return r
    return _run(request, fn)


@router.get("/validation-events")
def validation_events(request: Request, status: Optional[str] = None):
    def fn(conn, ctx):
        sf = " AND status=%s" if status else ""
        return q(conn, f"SELECT * FROM fin_validation_events WHERE legal_entity_id=%s {sf} ORDER BY created_at DESC LIMIT 200",
                 [ctx.entity_id] + ([status] if status else []))
    return _run(request, fn, "controls.view")


@router.get("/audit")
def audit_trail(request: Request, entity_type: Optional[str] = None, entity_id: Optional[str] = None,
                actor: Optional[str] = None, action: Optional[str] = None, search: Optional[str] = None,
                date_from: Optional[str] = Query(None, alias="from"), date_to: Optional[str] = Query(None, alias="to"),
                limit: int = 200, offset: int = 0):
    def fn(conn, ctx):
        where, p = ["legal_entity_id=%s"], [ctx.entity_id]
        for col, v in (("entity_type", entity_type), ("entity_id", entity_id), ("action", action)):
            if v:
                where.append(f"{col}=%s")
                p.append(v)
        if actor:
            where.append("(actor_id ILIKE %s OR actor_name ILIKE %s)")
            p += [f"%{actor}%"] * 2
        if search:
            where.append("(entity_ref ILIKE %s OR reason ILIKE %s OR action ILIKE %s)")
            p += [f"%{search}%"] * 3
        if date_from:
            where.append("created_at >= %s")
            p.append(_date(date_from))
        if date_to:
            where.append("created_at < %s::date + 1")
            p.append(_date(date_to))
        w = " AND ".join(where)
        total = q1(conn, f"SELECT COUNT(*) n FROM fin_audit_events WHERE {w}", p)["n"]
        rows = q(conn, f"SELECT * FROM fin_audit_events WHERE {w} ORDER BY id DESC LIMIT %s OFFSET %s", p + [limit, offset])
        return {"items": rows, "total": total}
    return _run(request, fn, "controls.view")


@router.get("/integrations/source-postings")
def source_postings(request: Request, status: Optional[str] = None):
    def fn(conn, ctx):
        sf = " AND status=%s" if status else ""
        return q(conn, f"""SELECT * FROM fin_source_postings WHERE legal_entity_id=%s {sf} ORDER BY updated_at DESC LIMIT 200""",
                 [ctx.entity_id] + ([status] if status else []))
    return _run(request, fn, "accounting.view")


@router.get("/integrations/unposted")
def operations_unposted(request: Request):
    """Bills, payments and dispenses since go-live that were never attempted."""
    return _run(request, lambda c, x: integrations.unposted(c, x.entity_id), "accounting.view")


@router.post("/integrations/backfill")
def backfill_operations(request: Request, payload: Dict[str, Any] = Body(...)):
    _run(request, lambda c, x: x.require("sales.invoice.post"))
    return plain(integrations.backfill(_date(payload["from"]), _date(payload["to"]), request.state.user.get("sub", "user")))


@router.post("/integrations/{source_type}/{source_id}/post")
def retry_operation(source_type: str, source_id: str, request: Request):
    _run(request, lambda c, x: x.require("sales.invoice.post"))
    return plain(integrations.retry(source_type.upper(), source_id, request.state.user.get("sub", "user")))


@router.post("/integrations/{source_type}/{source_id}/exclude")
def exclude_operation(source_type: str, source_id: str, request: Request, payload: Dict[str, Any] = Body(...)):
    return _run(request, lambda c, x: integrations.exclude(c, x, source_type.upper(), source_id, payload.get("reason", "")))


# ---------------------------------------------------------------------------
# Royan's Sage 50 history 2009 -> 2024 (display and lineage only - never posts)
# ---------------------------------------------------------------------------

@router.get("/inventory/reconciliation")
def stock_reconciliation(request: Request, as_of: Optional[str] = None):
    """The inventory accounts in the ledger, the stock Roy Books values and the pharmacy's shelves, side by side."""
    return _run(request, lambda c, x: hospital.stock_reconciliation(c, x.entity_id, _date(as_of)), "inventory.view")


@router.patch("/budgets/{budget_id}")
def update_budget(budget_id: str, request: Request, payload: Dict[str, Any] = Body(...)):
    return _run(request, lambda c, x: closing.update_budget(c, x, budget_id, payload))


@router.delete("/budgets/{budget_id}")
def delete_budget(budget_id: str, request: Request):
    return _run(request, lambda c, x: closing.delete_budget(c, x, budget_id))


@router.post("/budgets/{budget_id}/copy")
def copy_budget(budget_id: str, request: Request, payload: Dict[str, Any] = Body(default={})):
    return _run(request, lambda c, x: closing.copy_budget(c, x, budget_id, payload.get("name")))


@router.post("/payables/debit-notes/{dn_id}/allocate")
def allocate_debit_note(dn_id: str, request: Request, payload: Dict[str, Any] = Body(...)):
    """Use a supplier credit (a return, or a credit brought forward) against that supplier's open bills."""
    return _run(request, lambda c, x: purchases.allocate_debit_note(c, x, dn_id, payload.get("allocations") or []))


@router.get("/data-issues")
def data_issues(request: Request, status: Optional[str] = None, kind: Optional[str] = None):
    def fn(conn, ctx):
        return {"summary": data_issues_mod.summary(conn, ctx.entity_id),
                "items": data_issues_mod.list_issues(conn, ctx.entity_id, status, kind)}
    return _run(request, fn, "controls.view")


@router.post("/data-issues/refresh")
def data_issues_refresh(request: Request):
    return _run(request, lambda c, x: data_issues_mod.refresh(c, x), "controls.run")


@router.get("/data-issues/{issue_id}")
def data_issue(issue_id: str, request: Request):
    return _run(request, lambda c, x: data_issues_mod.get(c, x.entity_id, issue_id), "controls.view")


@router.post("/data-issues/{issue_id}/{action}")
def data_issue_action(issue_id: str, action: str, request: Request, payload: Dict[str, Any] = Body(default={})):
    return _run(request, lambda c, x: data_issues_mod.resolve(c, x, issue_id, action, _dates(payload)))


@router.post("/setup/go-live")
def go_live(request: Request, payload: Dict[str, Any] = Body(default={})):
    """Switch the books on: opening pharmacy stock, its opening entry, and the cut-over date."""
    return _run(request, lambda c, x: hospital.go_live(c, x, _date(payload.get("cutover_date")) or _today()))


@router.get("/sales/invoice-register")
def invoice_register(request: Request, date_from: Optional[str] = Query(None, alias="from"),
                     date_to: Optional[str] = Query(None, alias="to"), search: Optional[str] = None,
                     customer_id: Optional[int] = None, status: Optional[str] = None, limit: int = 500, offset: int = 0):
    def fn(conn, ctx):
        t = _date(date_to) or _today()
        f = _date(date_from) or t.replace(day=1)
        return sales.invoice_register(conn, ctx.entity_id, f, t, search=search, customer_id=customer_id, status=status,
                                      limit=limit, offset=offset)
    return _run(request, fn, "receivables.view")


@router.get("/sage/summary")
def sage_summary(request: Request):
    return _run(request, lambda c, x: sage_history.summary(c, x.entity_id), "reports.view")


@router.get("/sage/vouchers")
def sage_voucher(request: Request, key: str):
    return _run(request, lambda c, x: sage_history.voucher(c, x.entity_id, key), "reports.view")


@router.get("/sage/invoices/{invoice_id}")
def sage_invoice(invoice_id: int, request: Request):
    return _run(request, lambda c, x: sage_history.invoice(c, x.entity_id, invoice_id), "receivables.view")


@router.get("/sage/receipts/{receipt_id}")
def sage_receipt(receipt_id: int, request: Request):
    return _run(request, lambda c, x: sage_history.receipt(c, x.entity_id, receipt_id), "receivables.view")


@router.get("/sage/reports/{key}")
def sage_delivered(key: str, request: Request):
    return _run(request, lambda c, x: sage_history.delivered(c, x.entity_id, key), "reports.view")


@router.get("/sage/reconciliation")
def sage_reconciliation(request: Request):
    return _run(request, lambda c, x: sage_history.reconciliation(c, x.entity_id), "banking.view")


# ---------------------------------------------------------------------------
# Legacy history from Hope (display only - never posts)
# ---------------------------------------------------------------------------

@router.get("/history/revenue")
def hope_revenue(request: Request, date_from: Optional[str] = Query(None, alias="from"), date_to: Optional[str] = Query(None, alias="to")):
    def fn(conn, ctx):
        t = _date(date_to) or _today()
        f = _date(date_from) or dt.date(t.year - 2, 1, 1)
        return q(conn, """SELECT month, service_line, lines, amount, discount, excluded_lines, excluded_amount
                          FROM fin_v_hope_revenue_monthly WHERE month BETWEEN %s AND %s ORDER BY month, amount DESC""", (f, t))
    return _run(request, fn, "reports.view")


@router.get("/history/receipts")
def hope_receipts(request: Request, date_from: Optional[str] = Query(None, alias="from"), date_to: Optional[str] = Query(None, alias="to")):
    def fn(conn, ctx):
        t = _date(date_to) or _today()
        f = _date(date_from) or dt.date(t.year - 2, 1, 1)
        return q(conn, "SELECT * FROM fin_v_hope_receipts_monthly WHERE month BETWEEN %s AND %s ORDER BY month, channel", (f, t))
    return _run(request, fn, "reports.view")


@router.get("/history/purchases")
def hope_purchases(request: Request, supplier_id: Optional[str] = None, sku: Optional[str] = None, search: Optional[str] = None,
                   limit: int = 200, offset: int = 0):
    def fn(conn, ctx):
        where, p = ["legal_entity_id=%s"], [ctx.entity_id]
        if supplier_id:
            where.append("supplier_id=%s"); p.append(supplier_id)
        if sku:
            where.append("sku=%s"); p.append(sku)
        if search:
            where.append("(description ILIKE %s OR supplier_name ILIKE %s OR po_number ILIKE %s OR batch_number ILIKE %s)")
            p += [f"%{search}%"] * 4
        w = " AND ".join(where)
        total = q1(conn, f"SELECT COUNT(*) n, COALESCE(SUM(amount),0) v FROM fin_hist_purchase_lines WHERE {w}", p)
        rows = q(conn, f"""SELECT * FROM fin_hist_purchase_lines WHERE {w} ORDER BY received_date DESC NULLS LAST, id DESC
                           LIMIT %s OFFSET %s""", p + [limit, offset])
        return {"items": rows, "total": total["n"], "value": total["v"]}
    return _run(request, fn, "payables.view")


# ---------------------------------------------------------------------------
# Migration (Sage 50 -> Roy Books)
# ---------------------------------------------------------------------------

@router.get("/migration/batches")
def migration_batches(request: Request):
    return _run(request, lambda c, x: migration.list_batches(c, x.entity_id), "migration.stage")


@router.post("/migration/stage")
async def migration_stage(request: Request, kind: str = Form(...), as_of: Optional[str] = Form(None),
                          file: UploadFile = File(...)):
    raw = await file.read()
    return _run(request, lambda c, x: migration.stage(c, x, kind, file.filename or "upload", raw, _date(as_of)))


@router.get("/migration/batches/{batch_id}")
def migration_batch(batch_id: str, request: Request):
    return _run(request, lambda c, x: migration.get_batch(c, x.entity_id, batch_id), "migration.stage")


@router.post("/migration/batches/{batch_id}/load")
def migration_load(batch_id: str, request: Request):
    return _run(request, lambda c, x: migration.load(c, x, batch_id))


@router.post("/migration/batches/{batch_id}/discard")
def migration_discard(batch_id: str, request: Request):
    return _run(request, lambda c, x: migration.discard(c, x, batch_id))


# Hope's payers and visits (HMO / private split; see payers.py)

@router.get("/hope/visits/{visit_id}")
def hope_visit(visit_id: int, request: Request):
    return _run(request, lambda c, x: payers.visit(c, visit_id), "receivables.view")


@router.get("/data-coverage")
def data_coverage(request: Request):
    """What is in the system, from where, for which dates - and the gaps."""
    return _run(request, lambda c, x: hospital.data_coverage(c, x.entity_id), "reports.view")


@router.get("/hope/coverage")
def hope_coverage(request: Request):
    """How far each source reaches, so reports open on a period that has data."""
    def fn(c, x):
        h = q1(c, "SELECT MIN(charge_date) AS from_date, MAX(charge_date) AS to_date FROM fin_hope_charges")
        s = q1(c, "SELECT MAX(txn_date) AS d FROM fin_sage_gl_lines WHERE legal_entity_id=%s", (x.entity_id,))
        return {"hope_from": h["from_date"], "hope_to": h["to_date"], "sage_to": s["d"]}
    return _run(request, fn, "reports.view")


@router.get("/hope/payers")
def hope_payers(request: Request):
    return _run(request, lambda c, x: payers.list_payers(c), "receivables.view")


@router.patch("/hope/payers/{tariff_id}")
def hope_payer_type(tariff_id: int, request: Request, payload: Dict[str, Any] = Body(...)):
    return _run(request, lambda c, x: payers.set_payer_type(c, x, tariff_id, str(payload.get("payer_type") or "").upper()))


# Sage exports Finance uploads after the first load (2025, 2026 ...): upload -> check (dry run) -> load.

@router.get("/sage/uploads")
def sage_uploads(request: Request):
    return _run(request, lambda c, x: sage_uploads_mod.list_uploads(c, x.entity_id), "migration.stage")


@router.post("/sage/uploads")
async def sage_upload(request: Request, files: List[UploadFile] = File(...), note: Optional[str] = Form(None)):
    got = [(f.filename or "upload.xlsx", await f.read()) for f in files]
    return _run(request, lambda c, x: sage_uploads_mod.create(c, x, got, note))


@router.get("/sage/uploads/{upload_id}")
def sage_upload_get(upload_id: str, request: Request):
    return _run(request, lambda c, x: sage_uploads_mod.get(c, x.entity_id, upload_id), "migration.stage")


def _sage_step(request: Request, upload_id: str, perm: str, step: Callable) -> Any:
    """The import runs in its own transaction, so the permission check and the step are separate."""
    who = _run(request, lambda c, x: (x.require(perm), {"entity": x.entity_id, "actor": x.actor_name or x.actor_id})[1])
    try:
        return plain(step(tx, who["entity"], upload_id, f"sage-upload:{who['actor']}"))
    except FinError as e:
        raise HTTPException(status_code=e.status, detail=e.to_detail())


@router.post("/sage/uploads/{upload_id}/check")
def sage_upload_check(upload_id: str, request: Request):
    return _sage_step(request, upload_id, "migration.stage", sage_uploads_mod.check)


@router.post("/sage/uploads/{upload_id}/load")
def sage_upload_load(upload_id: str, request: Request):
    return _sage_step(request, upload_id, "migration.load", sage_uploads_mod.load)


@router.delete("/sage/uploads/{upload_id}")
def sage_upload_discard(upload_id: str, request: Request):
    return _run(request, lambda c, x: sage_uploads_mod.discard(c, x, upload_id))


@router.post("/migration/opening-dates/refresh")
def migration_refresh_dates(request: Request):
    return _run(request, lambda c, x: (x.require("migration.load"), migration.refresh_opening_dates(c, x))[1])


@router.post("/migration/pharmacy-stock")
def migration_pharmacy_stock(request: Request, payload: Dict[str, Any] = Body(default={})):
    """Open the books' stock from the pharmacy's live batches (valued at their unit cost)."""
    def fn(conn, ctx):
        on = _date(payload.get("as_of"))
        if not on:
            s = setup.get_settings(conn, ctx.entity_id)
            if not s.get("cutover_date"):
                raise invalid("Give the stock date (as_of), or set the cut-over date first")
            on = s["cutover_date"] - dt.timedelta(days=1)
        return hospital.load_pharmacy_opening_stock(conn, ctx, on)
    return _run(request, fn)


@router.post("/migration/products/sync")
def migration_products(request: Request):
    return _run(request, lambda c, x: migration.sync_products(c, x))
