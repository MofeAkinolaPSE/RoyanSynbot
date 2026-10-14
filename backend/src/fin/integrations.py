"""Hospital operations -> Roy Books: operations become accounting automatically.

The ACE Frontdesk pattern (ACE-Books.md s13), applied to every money- or
stock-affecting event in the hospital:

    event                         source_type          becomes
    ----------------------------  -------------------  ----------------------------------------------
    bill raised                   BILL                 invoice for the patient's share (+ HMO share)
    approved / direct discount    BILL_DISCOUNT        credit note to Discounts Allowed
    cashier payment               PAYMENT              receipt, allocated to the bill's invoice
      - method "waiver"                                credit note to Patient Waivers
      - method "hmo"                                   patient's share moved to their HMO
    bill waived                   BILL_WAIVER          credit note to Patient Waivers
    bill written off              BILL_WRITEOFF        credit note to Bad Debts
    correction pen                BILL_ADJUSTMENT      reduction -> credit note; reallocation -> moved
                                                       to the named payer; refund -> refund out of the
                                                       patient's credit; reversal of a reduction ->
                                                       the charge is raised again
    drug dispensed                DISPENSING           DR cost of drugs / CR pharmacy stock (FIFO batch)
    dispensed drug returned       DISPENSE_RETURN      the cost comes back into stock (restocked only)
    pharmacy receives stock       PHARMACY_RECEIPT     DR stock / CR goods received not invoiced
    pharmacy adjusts / disposes   PHARMACY_ADJUST      a DRAFT stock adjustment for Finance to approve
    payroll approved (HR)         PAYROLL              DR salaries expense / CR PAYE, pension, other
                                                       deductions and salaries payable (net), dated the
                                                       last day of the payroll month
    payroll paid (HR / Finance)   PAYROLL_PAYMENT      DR salaries payable / CR the bank it was paid from

Every posting:
  * runs in its OWN transaction after the operational change has committed, so
    a books problem (closed period, missing mapping, no stock) never blocks the
    ward, the cashier or the pharmacy;
  * is idempotent on its source (fin_source_postings + unique source indexes),
    so a retry or a backfill can never post twice;
  * records its outcome in fin_source_postings: FAILED items are listed in
    Close & Controls with Retry, and the OPERATIONS_POSTED control also catches
    items that were never attempted;
  * honours the auto-post pause and the cut-over date (anything dated before
    cut-over is already inside the Sage opening balances);
  * can be EXCLUDED for good (test bills, duplicates of Sage records).
"""
from __future__ import annotations

import datetime as dt
import logging
import uuid
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional

from src.fin import audit, inventory, posting, rules, sales
from src.fin.context import system_context
from src.fin.db import ZERO, ex, jsonb, money, q, q1, qty, tx
from src.fin.errors import FinError, invalid, not_found

log = logging.getLogger(__name__)

EXCLUDED_MARK = "EXCLUDED"
LAGOS = "Africa/Lagos"

SOURCE_LABELS = {
    "BILL": "Hospital bill", "BILL_DISCOUNT": "Bill discount", "PAYMENT": "Cashier payment",
    "BILL_WAIVER": "Bill waiver", "BILL_WRITEOFF": "Bill write-off", "BILL_ADJUSTMENT": "Bill correction",
    "DISPENSING": "Drug dispensed", "DISPENSE_RETURN": "Drug returned", "PHARMACY_RECEIPT": "Pharmacy stock received",
    "PHARMACY_ADJUST": "Pharmacy stock adjustment", "PAYROLL": "Payroll (salary cost)",
    "PAYROLL_PAYMENT": "Payroll paid", "PAYMENT_VOID": "Receipt voided", "CLAIM_PAYMENT": "HMO claim paid", "BILL_VOID": "Bill voided",
}

# Cashier payment method -> receipt method and the fin_settings.receipt_accounts key.
PAYMENT_METHOD = {"cash": ("CASH", "cash"), "pos": ("POS", "card"), "card": ("POS", "card"), "transfer": ("TRANSFER", "transfer"),
                  "other": ("OTHER", "other")}


# ---------------------------------------------------------------------------
# Bookkeeping of postings
# ---------------------------------------------------------------------------

def _record(conn, entity_id: str, source_type: str, source_id: str, source_ref: Optional[str], status: str, *,
            document_type: Optional[str] = None, document_id: Optional[str] = None, message: Optional[str] = None,
            payload: Optional[Dict[str, Any]] = None, doc_date: Optional[dt.date] = None) -> None:
    ex(conn, """INSERT INTO fin_source_postings (legal_entity_id, source_type, source_id, source_ref, status, document_type,
                document_id, message, payload, doc_date) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (legal_entity_id, source_type, source_id) DO UPDATE SET status=EXCLUDED.status,
                document_type=EXCLUDED.document_type, document_id=EXCLUDED.document_id, message=EXCLUDED.message,
                source_ref=COALESCE(EXCLUDED.source_ref, fin_source_postings.source_ref),
                payload=COALESCE(EXCLUDED.payload, fin_source_postings.payload),
                doc_date=COALESCE(EXCLUDED.doc_date, fin_source_postings.doc_date),
                attempts=fin_source_postings.attempts + 1, updated_at=now()""",
       (entity_id, source_type, str(source_id), source_ref, status, document_type, document_id, message,
        jsonb(payload) if payload is not None else None, doc_date))


def _settings(conn, entity_id: str) -> Dict[str, Any]:
    return q1(conn, "SELECT * FROM fin_settings WHERE legal_entity_id=%s", (entity_id,)) or {}


def _run(source_type: str, source_id: Any, fn: Callable, *, actor: str, automatic: bool,
         payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Post one operational event. Raises nothing: returns the outcome and records it.

    `fn(conn, ctx, settings)` returns (status, ref, doc_date, document_type, document_id, message).
    """
    sid = str(source_id)
    ref: Optional[str] = None
    doc_date: Optional[dt.date] = None
    try:
        with tx() as conn:
            ctx = system_context(conn, entity_id=entity_for(conn, source_type, sid), actor=actor)
            s = _settings(conn, ctx.entity_id)
            prior = q1(conn, """SELECT status, document_type, payload FROM fin_source_postings WHERE legal_entity_id=%s
                                AND source_type=%s AND source_id=%s""", (ctx.entity_id, source_type, sid))
            if prior and prior["document_type"] == EXCLUDED_MARK:
                return {"status": "SKIPPED", "message": "Excluded from the books"}
            if prior and prior["status"] == "POSTED":
                return {"status": "POSTED", "message": "Already in the books"}
            if payload is None and prior and prior.get("payload"):
                payload = prior["payload"]
            if automatic and not s.get("auto_post_operations", True):
                return {"status": "SKIPPED", "message": "Automatic posting to Roy Books is paused (Setup > Settings)"}
            if not s.get("cutover_date"):
                return {"status": "SKIPPED", "message": "Roy Books is not live yet (no cut-over date)"}
            status, ref, doc_date, doc_type, doc_id, message = fn(conn, ctx, s, payload)
            if status == "SKIPPED" and doc_date and doc_date < s["cutover_date"]:
                message = message or f"Dated before the Roy Books cut-over ({s['cutover_date']}) - in the opening balances"
            if status != "IGNORED":
                _record(conn, ctx.entity_id, source_type, sid, ref, status, document_type=doc_type, document_id=doc_id,
                        message=message, payload=payload, doc_date=doc_date)
            return {"status": status, "document_type": doc_type, "document_id": doc_id, "reference": ref,
                    "message": message}
    except FinError as e:
        message = e.message
    except Exception as e:  # never break the operational workflow
        log.exception("Roy Books posting failed for %s %s", source_type, sid)
        message = f"Unexpected error: {e}"
    try:
        with tx() as conn:
            ctx = system_context(conn, entity_id=entity_for(conn, source_type, sid), actor=actor)
            _record(conn, ctx.entity_id, source_type, sid, ref, "FAILED", message=message, payload=payload,
                    doc_date=doc_date)
    except Exception:
        log.exception("Could not record failed posting for %s %s", source_type, sid)
    return {"status": "FAILED", "message": message}


# Which company's books an operational record belongs to. Scancare (imaging) is a separate business with its own
# books; a hospital bill carries its company (royan_billing.entity), and a payment / discount / waiver follows its bill.
ENTITY_CODES = {"ROYAN": None, "SCANCARE": "SCN"}
_BILL_SOURCES = ("BILL", "BILL_DISCOUNT", "BILL_WAIVER", "BILL_WRITEOFF", "BILL_VOID")
_PAYMENT_SOURCES = ("PAYMENT", "PAYMENT_VOID")


def entity_for(conn, source_type: str, source_id: Any) -> Optional[str]:
    company = None
    try:
        if source_type in _BILL_SOURCES and str(source_id).isdigit():
            r = q1(conn, "SELECT entity FROM royan_billing WHERE id=%s", (int(source_id),))
            company = (r or {}).get("entity")
        elif source_type in _PAYMENT_SOURCES and str(source_id).isdigit():
            r = q1(conn, "SELECT b.entity FROM royan_payments p JOIN royan_billing b ON b.id=p.billing_id WHERE p.id=%s", (int(source_id),))
            company = (r or {}).get("entity")
        elif source_type == "CLAIM_PAYMENT" and str(source_id).isdigit():
            r = q1(conn, "SELECT b.entity FROM royan_insurance_claims c JOIN royan_billing b ON b.id=c.billing_id WHERE c.id=%s", (int(source_id),))
            company = (r or {}).get("entity")
        elif source_type == "BILL_ADJUSTMENT" and str(source_id).isdigit():
            r = q1(conn, "SELECT b.entity FROM royan_bill_adjustments a JOIN royan_billing b ON b.id=a.billing_id WHERE a.id=%s", (int(source_id),))
            company = (r or {}).get("entity")
    except Exception:
        company = None
    code = ENTITY_CODES.get(company or "ROYAN")
    if not code:
        return None   # the default company (Royan Hospital)
    e = q1(conn, "SELECT id FROM fin_legal_entities WHERE code=%s AND status='ACTIVE'", (code,))
    if not e:
        raise FinError("MAPPING_MISSING", f"{company.title()} books are not set up yet (Setup › Companies)")
    return str(e["id"])


def _void_payment(conn, ctx, s, payload, payment_id):
    """The cashier voided a receipt: Roy Books voids its receipt (reversal on the same date, unapplied from the
    invoice, its number given back when it was the last one). A waiver / HMO transfer is reversed by its credit note."""
    p = q1(conn, "SELECT * FROM royan_payments WHERE id=%s", (int(payment_id),))
    if not p:
        raise not_found("Payment", payment_id)
    ref = p.get("receipt_number") or f"PAY-{p['id']}"
    d = _local_date(p["received_at"])
    if _before_cutover(s, d):
        return _skip(ref, d)
    reason = p.get("void_reason") or "voided at the cashier"
    r = q1(conn, """SELECT id, receipt_number FROM fin_customer_receipts WHERE legal_entity_id=%s AND source_type='PAYMENT'
                    AND source_id=%s AND status <> 'VOID'""", (ctx.entity_id, str(p["id"])))
    if r:
        sales.void_receipt(conn, ctx, str(r["id"]), reason)
        return ("POSTED", ref, d, "RECEIPT", str(r["id"]), f"Receipt {r['receipt_number']} voided")
    cn = q1(conn, """SELECT id, credit_note_number FROM fin_credit_notes WHERE legal_entity_id=%s
                     AND source_type IN ('PAYMENT_WAIVER','PAYMENT_HMO') AND source_id=%s AND status <> 'VOID'""",
            (ctx.entity_id, str(p["id"])))
    if cn and hasattr(sales, "void_credit_note"):
        sales.void_credit_note(conn, ctx, str(cn["id"]), reason)
        return ("POSTED", ref, d, "CREDIT_NOTE", str(cn["id"]), f"Credit {cn['credit_note_number']} voided")
    return ("SKIPPED", ref, d, None, None, "Nothing in the books to void for this payment")


def _post_claim_payment(conn, ctx, s, payload, claim_id):
    """The HMO paid a claim (marked paid in Billing › Claims): Roy Books receives the money against the HMO's invoice
    for that bill, into the transfer account (HMOs pay by transfer). Recorded in Roy Books first? Then nothing is left
    open and this posts nothing."""
    c = q1(conn, "SELECT * FROM royan_insurance_claims WHERE id=%s", (int(claim_id),))
    if not c:
        raise not_found("Claim", claim_id)
    ref = f"CLAIM-{c['id']}"
    d = _local_date(c.get("settled_at") or dt.datetime.now(dt.timezone.utc))
    if c.get("external_source"):
        return _skip(ref, d, "Imported claim - legacy history, not the books")
    if _before_cutover(s, d) or not c.get("billing_id"):
        return _skip(ref, d)
    _ensure_bill(conn, ctx, s, c["billing_id"])
    inv = _invoice_for_bill(conn, ctx.entity_id, c["billing_id"], "BILLING_HMO")
    if not inv:
        return ("SKIPPED", ref, d, None, None, "The bill has no HMO share in the books")
    open_amt = money(inv["total"]) - money(inv["amount_settled"])
    amount = min(money(c.get("approved_amount") or c.get("claim_amount") or 0) or open_amt, open_amt)
    if amount <= 0:
        return ("SKIPPED", ref, d, None, None, "The HMO invoice is already settled")
    bank_id = (s.get("receipt_accounts") or {}).get("transfer")
    if not bank_id:
        raise FinError("MAPPING_MISSING", "No bank account is set for transfers (Setup > Settings)")
    r = sales.create_receipt(conn, ctx, {
        "customer_id": inv["customer_id"], "receipt_date": d, "method": "TRANSFER", "bank_account_id": bank_id, "amount": amount,
        "reference": c.get("authorisation_code"), "notes": f"HMO claim {ref} paid ({c.get('hmo_provider') or 'HMO'})",
        # the hospital's receipt series (RHR- / Scancare SCR-), not a separate Roy Books series
        "receipt_number": q1(conn, "SELECT generate_scancare_receipt_number() AS n" if _bill(conn, c["billing_id"]).get("entity") == "SCANCARE"
                             else "SELECT generate_receipt_number() AS n")["n"],
        "allocations": [{"invoice_id": str(inv["id"]), "amount": amount}], "confirm_duplicate": True,
        "source_type": "CLAIM_PAYMENT", "source_id": str(c["id"])})
    return ("POSTED", ref, d, "RECEIPT", str(r["id"]), f"Receipt {r['receipt_number']} from the HMO")


def _void_bill(conn, ctx, s, payload, bill_id):
    """A bill raised wrongly was voided: Roy Books voids its invoice(s) - the patient's share and the HMO's -
    reversing revenue and the receivable on the bill's own date."""
    b = _bill(conn, bill_id)
    d = _local_date(b["billed_at"])
    if _before_cutover(s, d):
        return _skip(b["bill_number"], d)
    done = []
    for inv in q(conn, """SELECT id, invoice_number FROM fin_sales_invoices WHERE legal_entity_id=%s
                          AND source_type IN ('BILLING','BILLING_HMO') AND source_id=%s AND status <> 'VOID'""",
                 (ctx.entity_id, str(b["id"]))):
        sales.void_invoice(conn, ctx, str(inv["id"]), b.get("void_reason") or "bill voided at the cashier")
        done.append(inv["invoice_number"])
    return ("POSTED", b["bill_number"], d, "SALES_INVOICE", None,
            f"Voided {', '.join(done)}" if done else "Bill was not in the books")


def _local_date(ts: Any) -> dt.date:
    if isinstance(ts, dt.datetime):
        try:
            from zoneinfo import ZoneInfo
            return ts.astimezone(ZoneInfo(LAGOS)).date()
        except Exception:
            return ts.date()
    if isinstance(ts, dt.date):
        return ts
    return dt.date.fromisoformat(str(ts)[:10])


def _before_cutover(s: Dict[str, Any], d: dt.date) -> bool:
    return bool(s.get("cutover_date") and d < s["cutover_date"])


def _skip(ref, d, message=None):
    return ("SKIPPED", ref, d, None, None, message)


# ---------------------------------------------------------------------------
# Bills -> invoices
# ---------------------------------------------------------------------------

_BILL_COLUMNS = (("consultation_fee", "consultation", "Consultation"), ("lab_charges", "lab", "Laboratory"),
                 ("pharmacy_charges", "pharmacy", "Pharmacy"), ("ward_charges", "ward", "Ward & accommodation"),
                 ("procedure_charges", "procedure", "Procedures"), ("miscellaneous", "misc", "Other services"))


def _bill(conn, bill_id: Any) -> Dict[str, Any]:
    b = q1(conn, "SELECT * FROM royan_billing WHERE id=%s", (int(bill_id),))
    if not b:
        raise not_found("Hospital bill", bill_id)
    return b


def _bill_hmo(conn, b: Dict[str, Any]) -> Optional[int]:
    if b.get("hmo_id"):
        return int(b["hmo_id"])
    ins = q1(conn, """SELECT hmo_id FROM royan_patient_insurance WHERE patient_id=%s AND status='active'
                      ORDER BY is_primary DESC, id LIMIT 1""", (b["patient_id"],))
    return int(ins["hmo_id"]) if ins else None


def _split_lines(conn, b: Dict[str, Any]) -> tuple:
    """Service lines of a bill, split into the patient's share and the payer's share."""
    items = q(conn, """SELECT description, category, quantity, unit_price, gross_amount, covered_amount, patient_amount
                       FROM royan_bill_items WHERE billing_id=%s ORDER BY id""", (b["id"],))
    subtotal = money(b["subtotal"])
    hmo = money(b["hmo_covered"])
    patient_lines: List[Dict[str, Any]] = []
    payer_lines: List[Dict[str, Any]] = []
    if items and sum((money(i["gross_amount"]) for i in items), ZERO) == subtotal and \
            sum((money(i["covered_amount"]) for i in items), ZERO) == hmo:
        for i in items:
            gross, cov = money(i["gross_amount"]), money(i["covered_amount"])
            if gross - cov > 0:
                patient_lines.append({"line_type": "SERVICE", "category": i["category"], "description": i["description"],
                                      "quantity": 1, "unit_price": gross - cov})
            if cov > 0:
                payer_lines.append({"line_type": "SERVICE", "category": i["category"], "description": i["description"],
                                    "quantity": 1, "unit_price": cov})
        return patient_lines, payer_lines
    # No itemisation that agrees with the bill: use its category columns and
    # share the HMO cover proportionally (remainder on the largest line).
    parts = [(money(b[col]), cat, label) for col, cat, label in _BILL_COLUMNS if money(b[col]) > 0]
    shares, given = [], ZERO
    for amt, cat, label in parts:
        cov = money(hmo * amt / subtotal) if subtotal > 0 else ZERO
        shares.append([amt, cat, label, cov])
        given += cov
    if shares and given != hmo:
        biggest = max(shares, key=lambda x: x[0])
        biggest[3] += hmo - given
    for amt, cat, label, cov in shares:
        if amt - cov > 0:
            patient_lines.append({"line_type": "SERVICE", "category": cat, "description": label, "quantity": 1,
                                  "unit_price": amt - cov})
        if cov > 0:
            payer_lines.append({"line_type": "SERVICE", "category": cat, "description": label, "quantity": 1,
                                "unit_price": cov})
    return patient_lines, payer_lines


def _invoice_for_bill(conn, entity_id: str, bill_id: Any, source_type: str = "BILLING") -> Optional[Dict[str, Any]]:
    return q1(conn, """SELECT * FROM fin_sales_invoices WHERE legal_entity_id=%s AND source_type=%s AND source_id=%s
                       AND status <> 'VOID'""", (entity_id, source_type, str(bill_id)))


def _post_bill(conn, ctx, s, payload, bill_id):
    b = _bill(conn, bill_id)
    d = _local_date(b["billed_at"])
    if b.get("external_source"):
        return _skip(b["bill_number"], d, f"Imported from {b['external_source']} - part of the legacy history, not the books")
    if _before_cutover(s, d):
        return _skip(b["bill_number"], d)
    if money(b["subtotal"]) <= 0:
        return _skip(b["bill_number"], d, "Bill has no value")
    patient_lines, payer_lines = _split_lines(conn, b)
    docs = []
    common = {"invoice_date": d, "terms_days": 0, "reference": b["bill_number"]}
    if patient_lines and not _invoice_for_bill(conn, ctx.entity_id, b["id"]):
        cid = sales.ensure_patient_customer(conn, b["patient_id"])
        inv = sales.create_invoice(conn, ctx, {**common, "customer_id": cid, "lines": patient_lines,
                                               "notes": f"Hospital bill {b['bill_number']} (encounter {b['encounter_id']})"},
                                   source_type="BILLING", source_id=str(b["id"]), number=b["bill_number"])
        inv = sales.post_invoice(conn, ctx, str(inv["id"]), override_credit=True,
                                 override_reason="Raised by hospital billing")
        docs.append(inv["invoice_number"])
    if payer_lines and not _invoice_for_bill(conn, ctx.entity_id, b["id"], "BILLING_HMO"):
        # Royan's chart books what HMOs owe to its own income head (Sage 4050) when that rule is set;
        # otherwise the payer's share follows the service line like the patient's.
        hmo_rev = rules.optional(conn, ctx.entity_id, "REVENUE_HMO")
        if hmo_rev:
            payer_lines = [{**l, "account_id": str(hmo_rev["id"])} for l in payer_lines]
        hmo_id = _bill_hmo(conn, b)
        if not hmo_id:
            raise FinError("MAPPING_MISSING", f"Bill {b['bill_number']} has an HMO share of ₦{money(b['hmo_covered']):,.2f} "
                                              "but the patient has no active HMO on file")
        cid = sales.ensure_hmo_customer(conn, hmo_id)
        terms = q1(conn, "SELECT payment_terms_days FROM fin_customers WHERE id=%s", (cid,))["payment_terms_days"]
        inv = sales.create_invoice(conn, ctx, {**common, "customer_id": cid, "lines": payer_lines, "terms_days": terms,
                                               "notes": f"HMO share of hospital bill {b['bill_number']}"},
                                   source_type="BILLING_HMO", source_id=str(b["id"]), number=f"{b['bill_number']}-HMO")
        inv = sales.post_invoice(conn, ctx, str(inv["id"]), override_credit=True,
                                 override_reason="HMO share of a hospital bill")
        docs.append(inv["invoice_number"])
    # A discount given when the bill was raised (or already approved) goes to its own head.
    if money(b["discount"]) > 0 and b.get("discount_status") in ("none", "approved"):
        _discount_credit(conn, ctx, b)
    return ("POSTED", b["bill_number"], d, "SALES_INVOICE", None,
            f"Posted as {', '.join(docs)}" if docs else "Already posted")


def _ensure_bill(conn, ctx, s, bill_id) -> None:
    """Post the bill behind a payment / discount / correction first, and record that it is in the books."""
    status, ref, d, doc_type, doc_id, message = _post_bill(conn, ctx, s, None, bill_id)
    if status in ("POSTED", "SKIPPED"):
        _record(conn, ctx.entity_id, "BILL", str(bill_id), ref, status, document_type=doc_type, message=message, doc_date=d)


def _credit(conn, ctx, *, invoice: Dict[str, Any], amount: Decimal, reason: str, debit_key: str, on: dt.date,
            source_type: str, source_id: str, category: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Operational credit note against one invoice (idempotent on its source)."""
    done = q1(conn, """SELECT id FROM fin_credit_notes WHERE legal_entity_id=%s AND source_type=%s AND source_id=%s
                       AND status <> 'VOID'""", (ctx.entity_id, source_type, source_id))
    if done:
        return sales.get_credit_note(conn, ctx.entity_id, done["id"])
    amount = money(amount)
    if amount <= 0:
        return None
    on = max(on, invoice["invoice_date"])
    return sales.create_credit_note(conn, ctx, {
        "customer_id": invoice["customer_id"], "invoice_id": invoice["id"], "note_date": on, "reason": reason,
        "debit_key": debit_key, "source_type": source_type, "source_id": source_id,
        "lines": [{"line_type": "SERVICE", "category": category, "description": reason, "quantity": 1,
                   "unit_price": amount}]})


def _discount_credit(conn, ctx, b):
    inv = _invoice_for_bill(conn, ctx.entity_id, b["id"])
    if not inv:
        raise FinError("INVALID_STATE_TRANSITION", f"Bill {b['bill_number']} is not in the books yet")
    d = _local_date(b.get("discount_decided_at") or b["billed_at"])
    reason = f"Discount on {b['bill_number']}" + (f": {b['discount_reason']}" if b.get("discount_reason") else "")
    return _credit(conn, ctx, invoice=inv, amount=min(money(b["discount"]), money(inv["total"])), reason=reason,
                   debit_key="SALES_DISCOUNT", on=d, source_type="BILL_DISCOUNT", source_id=str(b["id"]))


def _post_discount(conn, ctx, s, payload, bill_id):
    b = _bill(conn, bill_id)
    d = _local_date(b.get("discount_decided_at") or b["billed_at"])
    if b.get("external_source") or _before_cutover(s, _local_date(b["billed_at"])):
        return _skip(b["bill_number"], d)
    if b.get("discount_status") != "approved" or money(b["discount"]) <= 0:
        return ("IGNORED", b["bill_number"], d, None, None, "No approved discount")
    _ensure_bill(conn, ctx, s, bill_id)  # the bill itself must be in the books first
    cn = _discount_credit(conn, ctx, b)
    return ("POSTED", b["bill_number"], d, "CREDIT_NOTE", str(cn["id"]) if cn else None,
            f"Credit note {cn['credit_note_number']}" if cn else "Nothing to credit")


def _outstanding_credit(conn, ctx, s, bill_id, *, source_type, debit_key, label):
    b = _bill(conn, bill_id)
    d = _local_date(b["billed_at"])
    if b.get("external_source") or _before_cutover(s, d):
        return _skip(b["bill_number"], d)
    _ensure_bill(conn, ctx, s, bill_id)
    inv = _invoice_for_bill(conn, ctx.entity_id, b["id"])
    if not inv:
        return ("IGNORED", b["bill_number"], d, None, None, "Nothing billed to the patient")
    open_amt = money(inv["total"]) - money(inv["amount_settled"])
    cn = _credit(conn, ctx, invoice=inv, amount=open_amt, reason=f"{label}: bill {b['bill_number']}", debit_key=debit_key,
                 on=dt.date.today(), source_type=source_type, source_id=str(b["id"]))
    return ("POSTED", b["bill_number"], dt.date.today(), "CREDIT_NOTE", str(cn["id"]) if cn else None,
            f"Credit note {cn['credit_note_number']}" if cn else "Nothing outstanding")


def _move_to_payer(conn, ctx, *, invoice, amount: Decimal, payer_customer_id: int, reason: str, on: dt.date,
                   source_type: str, source_id: str) -> str:
    """Move part of a patient's invoice to another debtor (their HMO, an employer ...).

    Two documents, so both subledgers stay true: a credit note on the patient's
    invoice and an invoice to the payer, both through Returns & Allowances,
    which therefore nets to nil. Net effect: DR payer AR / CR patient AR.
    """
    cn = _credit(conn, ctx, invoice=invoice, amount=amount, reason=reason, debit_key="SALES_RETURNS", on=on,
                 source_type=source_type, source_id=source_id)
    returns_acct = rules.account(conn, ctx.entity_id, "SALES_RETURNS")
    number = f"{invoice['invoice_number']}-R{str(source_id)[-6:]}"
    existing = q1(conn, "SELECT id, invoice_number FROM fin_sales_invoices WHERE legal_entity_id=%s AND invoice_number=%s",
                  (ctx.entity_id, number))
    if not existing:
        terms = q1(conn, "SELECT payment_terms_days FROM fin_customers WHERE id=%s", (payer_customer_id,))["payment_terms_days"]
        inv = sales.create_invoice(conn, ctx, {"customer_id": payer_customer_id, "invoice_date": max(on, invoice["invoice_date"]),
                                               "terms_days": terms, "reference": invoice["invoice_number"], "notes": reason,
                                               "lines": [{"line_type": "SERVICE", "description": reason, "quantity": 1,
                                                          "unit_price": money(amount), "account_id": returns_acct["id"]}]},
                                   source_type="MANUAL", number=number)
        existing = sales.post_invoice(conn, ctx, str(inv["id"]), override_credit=True, override_reason=reason)
    return f"credit note {cn['credit_note_number'] if cn else '-'} + invoice {existing['invoice_number']}"


# ---------------------------------------------------------------------------
# Cashier payments -> receipts
# ---------------------------------------------------------------------------

def _post_payment(conn, ctx, s, payload, payment_id):
    p = q1(conn, "SELECT * FROM royan_payments WHERE id=%s", (int(payment_id),))
    if not p:
        raise not_found("Payment", payment_id)
    d = _local_date(p["received_at"])
    ref = p.get("receipt_number") or f"PAY-{p['id']}"
    if p.get("external_source"):
        return _skip(ref, d, f"Imported from {p['external_source']} - legacy history, not the books")
    if _before_cutover(s, d):
        return _skip(ref, d)
    b = _bill(conn, p["billing_id"]) if p.get("billing_id") else None
    inv = None
    if b:
        _ensure_bill(conn, ctx, s, b["id"])
        inv = _invoice_for_bill(conn, ctx.entity_id, b["id"])
    method = (p["payment_method"] or "").lower()
    amount = money(p["amount"])
    if method == "waiver":
        if not inv:
            raise FinError("INVALID_STATE_TRANSITION", "A waiver must be recorded against a bill")
        cn = _credit(conn, ctx, invoice=inv, amount=min(amount, money(inv["total"]) - money(inv["amount_settled"])),
                     reason=f"Waived at the till ({ref})", debit_key="PATIENT_WAIVERS", on=d,
                     source_type="PAYMENT_WAIVER", source_id=str(p["id"]))
        return ("POSTED", ref, d, "CREDIT_NOTE", str(cn["id"]) if cn else None, "Waiver credited")
    if method == "hmo":
        if not inv:
            raise FinError("INVALID_STATE_TRANSITION", "An HMO settlement must be recorded against a bill")
        hmo_id = _bill_hmo(conn, b)
        if not hmo_id:
            raise FinError("MAPPING_MISSING", f"Payment {ref} is marked HMO but the patient has no active HMO on file")
        msg = _move_to_payer(conn, ctx, invoice=inv, amount=min(amount, money(inv["total"]) - money(inv["amount_settled"])),
                             payer_customer_id=sales.ensure_hmo_customer(conn, hmo_id),
                             reason=f"Charged to HMO at the till ({ref})", on=d, source_type="PAYMENT_HMO",
                             source_id=str(p["id"]))
        return ("POSTED", ref, d, "CREDIT_NOTE", None, f"Moved to the HMO: {msg}")
    rec_method, acct_key = PAYMENT_METHOD.get(method, ("OTHER", "other"))
    bank_id = (s.get("receipt_accounts") or {}).get(acct_key)
    if not bank_id:
        raise FinError("MAPPING_MISSING", f"No bank/cash account is set for {method} payments (Setup > Settings)")
    done = q1(conn, """SELECT id, receipt_number FROM fin_customer_receipts WHERE legal_entity_id=%s AND source_type='PAYMENT'
                       AND source_id=%s AND status <> 'VOID'""", (ctx.entity_id, str(p["id"])))
    if done:
        return ("POSTED", ref, d, "RECEIPT", str(done["id"]), f"Receipt {done['receipt_number']}")
    cid = inv["customer_id"] if inv else sales.ensure_patient_customer(conn, p["patient_id"])
    allocations = []
    if inv:
        open_amt = money(inv["total"]) - money(inv["amount_settled"])
        if open_amt > 0:
            allocations.append({"invoice_id": str(inv["id"]), "amount": min(amount, open_amt)})
    number = p.get("receipt_number")
    if number and q1(conn, "SELECT 1 FROM fin_customer_receipts WHERE legal_entity_id=%s AND receipt_number=%s",
                     (ctx.entity_id, number)):
        number = None
    r = sales.create_receipt(conn, ctx, {
        "customer_id": cid, "receipt_date": d, "method": rec_method, "bank_account_id": bank_id, "amount": amount,
        "reference": p.get("reference"), "notes": (f"Cashier payment on bill {b['bill_number']}" if b else "Cashier payment / deposit"),
        "allocations": allocations, "confirm_duplicate": True, "receipt_number": number,
        "source_type": "PAYMENT", "source_id": str(p["id"])})
    return ("POSTED", ref, d, "RECEIPT", str(r["id"]), f"Receipt {r['receipt_number']}")


# ---------------------------------------------------------------------------
# Correction pen (royan_bill_adjustments)
# ---------------------------------------------------------------------------

def _payer_for(conn, name: str, patient_id: Any) -> int:
    """The debtor a reallocation names: the patient's HMO, a known HMO, or a corporate account."""
    n = (name or "").strip()
    if n.lower() in ("hmo", "insurance", "insurer", "the hmo"):
        ins = q1(conn, """SELECT hmo_id FROM royan_patient_insurance WHERE patient_id=%s AND status='active'
                          ORDER BY is_primary DESC LIMIT 1""", (patient_id,))
        if ins:
            return sales.ensure_hmo_customer(conn, ins["hmo_id"])
    h = q1(conn, "SELECT id FROM royan_hmos WHERE lower(name)=lower(%s) OR lower(code)=lower(%s) LIMIT 1", (n, n))
    if h:
        return sales.ensure_hmo_customer(conn, h["id"])
    c = q1(conn, "SELECT id FROM fin_customers WHERE party_type='CORPORATE' AND lower(name)=lower(%s)", (n,))
    if c:
        return int(c["id"])
    return int(q1(conn, """INSERT INTO fin_customers (party_type, name, payment_terms_days, notes, created_by)
                           VALUES ('CORPORATE', %s, 30, 'Created from a bill reallocation', 'system') RETURNING id""",
                  (n or "Unnamed payer",))["id"])


def _post_adjustment(conn, ctx, s, payload, adjustment_id):
    a = q1(conn, "SELECT * FROM royan_bill_adjustments WHERE id=%s", (int(adjustment_id),))
    if not a:
        raise not_found("Bill adjustment", adjustment_id)
    b = _bill(conn, a["billing_id"])
    d = _local_date(a["adjusted_at"])
    ref = f"{b['bill_number']}/ADJ{a['id']}"
    if b.get("external_source") or _before_cutover(s, _local_date(b["billed_at"])):
        return _skip(ref, d)
    _ensure_bill(conn, ctx, s, b["id"])
    inv = _invoice_for_bill(conn, ctx.entity_id, b["id"])
    amount = money(a["amount"])
    reason = f"{a['adjustment_type'].title()} on {b['bill_number']}: {a['reason']}"
    kind = a["adjustment_type"]
    if kind == "reduction":
        if not inv:
            raise FinError("INVALID_STATE_TRANSITION", "Nothing was billed to the patient on this bill")
        cn = _credit(conn, ctx, invoice=inv, amount=amount, reason=reason, debit_key="SALES_RETURNS", on=d,
                     source_type="BILL_ADJUSTMENT", source_id=str(a["id"]))
        return ("POSTED", ref, d, "CREDIT_NOTE", str(cn["id"]) if cn else None, f"Credit note {cn['credit_note_number']}")
    if kind == "reallocation":
        if not inv:
            raise FinError("INVALID_STATE_TRANSITION", "Nothing was billed to the patient on this bill")
        msg = _move_to_payer(conn, ctx, invoice=inv, amount=amount, payer_customer_id=_payer_for(conn, a["reallocated_to"], b["patient_id"]),
                             reason=reason, on=d, source_type="BILL_ADJUSTMENT", source_id=str(a["id"]))
        return ("POSTED", ref, d, "CREDIT_NOTE", None, f"Reallocated: {msg}")
    if kind == "refund":
        cid = inv["customer_id"] if inv else sales.ensure_patient_customer(conn, b["patient_id"])
        credit = q1(conn, """SELECT 'CREDIT_NOTE' AS t, id FROM fin_credit_notes WHERE legal_entity_id=%s AND customer_id=%s
                             AND status='POSTED' AND total - amount_settled >= %s
                             UNION ALL
                             SELECT 'RECEIPT', id FROM fin_customer_receipts WHERE legal_entity_id=%s AND customer_id=%s
                             AND status='POSTED' AND amount + wht_amount - amount_allocated >= %s LIMIT 1""",
                    (ctx.entity_id, cid, amount, ctx.entity_id, cid, amount))
        if not credit:
            raise FinError("OVER_ALLOCATION", f"The patient has no unapplied credit of ₦{amount:,.2f} in the books to refund "
                                              "(record the reduction first)")
        bank_id = (s.get("receipt_accounts") or {}).get("cash")
        if not bank_id:
            raise FinError("MAPPING_MISSING", "No cash account is set for refunds (Setup > Settings)")
        r = sales.create_refund(conn, ctx, {"customer_id": cid, "amount": amount, "reason": reason, "bank_account_id": bank_id,
                                            "credit_type": credit["t"], "credit_id": credit["id"], "refund_date": d,
                                            "source_type": "BILL_ADJUSTMENT", "source_id": str(a["id"])})
        return ("POSTED", ref, d, "REFUND", str(r["id"]), f"Refund {r['refund_number']}")
    if kind == "reversal":
        orig = q1(conn, "SELECT * FROM royan_bill_adjustments WHERE id=%s", (a["reverses_id"],))
        if not orig or orig["adjustment_type"] != "reduction":
            raise FinError("INVALID_STATE_TRANSITION",
                           "Only a reversed reduction is re-charged automatically; reverse other corrections in Roy Books")
        cid = inv["customer_id"] if inv else sales.ensure_patient_customer(conn, b["patient_id"])
        number = f"{b['bill_number']}-RC{a['id']}"
        existing = q1(conn, "SELECT id, invoice_number FROM fin_sales_invoices WHERE legal_entity_id=%s AND invoice_number=%s",
                      (ctx.entity_id, number))
        if not existing:
            returns_acct = rules.account(conn, ctx.entity_id, "SALES_RETURNS")
            new = sales.create_invoice(conn, ctx, {"customer_id": cid, "invoice_date": d, "terms_days": 0,
                                                   "reference": b["bill_number"], "notes": reason,
                                                   "lines": [{"line_type": "SERVICE", "description": reason, "quantity": 1,
                                                              "unit_price": amount, "account_id": returns_acct["id"]}]},
                                       source_type="MANUAL", number=number)
            existing = sales.post_invoice(conn, ctx, str(new["id"]), override_credit=True, override_reason=reason)
        return ("POSTED", ref, d, "SALES_INVOICE", str(existing["id"]), f"Re-charged as {existing['invoice_number']}")
    return ("IGNORED", ref, d, None, None, f"Unknown adjustment {kind}")


# ---------------------------------------------------------------------------
# Pharmacy
# ---------------------------------------------------------------------------

def _post_dispensing(conn, ctx, s, payload, dispensing_id):
    from src.fin import hospital
    r = q1(conn, "SELECT * FROM royan_dispensing WHERE id=%s", (int(dispensing_id),))
    if not r:
        raise not_found("Dispensing record", dispensing_id)
    d = _local_date(r["dispensed_at"])
    ref = f"DISP-{r['id']}"
    if r.get("external_source"):
        return _skip(ref, d, f"Imported from {r['external_source']} - legacy history")
    if _before_cutover(s, d):
        return _skip(ref, d)
    if not r.get("formulary_id"):
        raise FinError("RESOURCE_NOT_FOUND", f"'{r['drug_name']}' is not linked to a formulary item, so its cost is unknown")
    sku = hospital.ensure_product(conn, ctx.entity_id, r["formulary_id"])
    batch_id = hospital.fin_batch_for_ops(conn, ctx.entity_id, sku, r.get("batch_id"), r.get("batch_number"), r.get("expiry_date"))
    if batch_id:
        b = q1(conn, "SELECT batch_number, status, expiry_date FROM fin_batches WHERE id=%s", (batch_id,))
        if b and (b["status"] != "AVAILABLE" or (b["expiry_date"] and b["expiry_date"] < d)):
            ex(conn, """INSERT INTO fin_validation_events (legal_entity_id, entity_type, entity_id, entity_ref, check_code, severity,
                        message, status, created_by) VALUES (%s,'dispensing',%s,%s,'UNSELLABLE_BATCH_DISPENSED','CRITICAL',%s,'OPEN',%s)""",
               (ctx.entity_id, str(r["id"]), ref, f"{r['drug_name']} dispensed from batch {b['batch_number']} which is "
                f"{'expired' if b['expiry_date'] and b['expiry_date'] < d else b['status'].lower()}", ctx.actor_id))
    cid = sales.ensure_patient_customer(conn, r["patient_id"])
    t = inventory.issue(conn, ctx, sku=sku, quantity=r["quantity_dispensed"], txn_type="SALE", txn_date=d, batch_id=batch_id,
                        source_type="DISPENSING", source_id=str(r["id"]), reference=ref, customer_id=cid,
                        reason=f"Dispensed to patient (prescription {r.get('prescription_id')})", mirror=False)
    j = None
    if t["cost"] > 0:
        acc = rules.product_accounts(conn, ctx.entity_id, sku)
        dept = rules.department_id(conn, ctx.entity_id, "pharmacy")
        j = posting.post_system(conn, ctx, event_type="DRUG_DISPENSED", journal_date=d, lines=[
            {"account_id": acc["cogs_account_id"], "debit": t["cost"], "product_sku": sku, "customer_id": cid,
             "department_id": dept, "description": f"{r['drug_name']} x{qty(r['quantity_dispensed']):g}"},
            {"account_id": acc["inventory_account_id"], "credit": t["cost"], "product_sku": sku, "department_id": dept}],
            description=f"Cost of {r['drug_name']} dispensed ({ref})", source_type="DISPENSING", source_id=r["id"],
            source_ref=ref)
        inventory.link_journal(conn, [str(t["id"])], j["id"])
    return ("POSTED", ref, d, "INVENTORY_TXN", str(t["id"]), f"Cost ₦{t['cost']:,.2f}" + (f" ({j['journal_number']})" if j else ""))


def _post_dispense_return(conn, ctx, s, payload, return_id):
    r = q1(conn, "SELECT * FROM royan_sales_returns WHERE id=%s", (int(return_id),))
    if not r:
        raise not_found("Drug return", return_id)
    d = _local_date(r["processed_at"])
    ref = f"RET-{r['id']}"
    if _before_cutover(s, d):
        return _skip(ref, d)
    if not r.get("restocked"):
        return ("IGNORED", ref, d, None, None, "Not restocked: the cost stays in cost of drugs")
    orig = q1(conn, """SELECT * FROM fin_inventory_transactions WHERE legal_entity_id=%s AND source_type='DISPENSING'
                       AND source_id=%s ORDER BY created_at LIMIT 1""", (ctx.entity_id, str(r["dispensing_id"])))
    if not orig:
        raise FinError("INVALID_STATE_TRANSITION", f"The original dispense DISP-{r['dispensing_id']} is not in the books")
    t = inventory.restore(conn, ctx, original_txn_id=str(orig["id"]), quantity=r["quantity_returned"], txn_type="RETURN_IN",
                          txn_date=d, source_type="DISPENSE_RETURN", source_id=str(r["id"]), reference=ref,
                          customer_id=orig["customer_id"], reason=r.get("reason") or "Returned to pharmacy")
    value = money(t["total_cost"])
    if value > 0:
        acc = rules.product_accounts(conn, ctx.entity_id, orig["sku"])
        j = posting.post_system(conn, ctx, event_type="DRUG_RETURNED", journal_date=d, lines=[
            {"account_id": acc["inventory_account_id"], "debit": value, "product_sku": orig["sku"]},
            {"account_id": acc["cogs_account_id"], "credit": value, "product_sku": orig["sku"], "customer_id": orig["customer_id"],
             "description": f"Returned: {ref}"}],
            description=f"Drug returned to stock ({ref})", source_type="DISPENSE_RETURN", source_id=r["id"], source_ref=ref)
        inventory.link_journal(conn, [str(t["id"])], j["id"])
    return ("POSTED", ref, d, "INVENTORY_TXN", str(t["id"]), f"₦{value:,.2f} back in stock")


def _post_pharmacy_receipt(conn, ctx, s, payload, event_id):
    """Stock the pharmacy received: DR stock / CR goods received not invoiced."""
    from src.fin import hospital
    if not payload:
        raise invalid("Nothing to post: the receipt details were not captured")
    d = _local_date(payload.get("date") or dt.date.today())
    ref = f"GRN-{payload['batch_number']}"
    if _before_cutover(s, d):
        return _skip(ref, d)
    sku = hospital.ensure_product(conn, ctx.entity_id, payload["formulary_id"])
    batch_id = hospital.fin_batch_for_ops(conn, ctx.entity_id, sku, payload.get("ops_batch_id"), payload["batch_number"],
                                          payload.get("expiry_date"))
    unit = Decimal(str(payload.get("unit_cost") or 0))
    if unit <= 0:
        raise invalid(f"{ref}: the pharmacy recorded no unit cost, so the stock cannot be valued - enter the cost and retry")
    t = inventory.receive(conn, ctx, sku=sku, quantity=payload["quantity"], unit_cost=unit, txn_type="PURCHASE", txn_date=d,
                          batch_id=batch_id, source_type="PHARMACY_RECEIPT", source_id=str(event_id), reference=ref,
                          reason=f"Received by pharmacy{(' from ' + payload['supplier']) if payload.get('supplier') else ''}",
                          mirror=False)
    acc = rules.product_accounts(conn, ctx.entity_id, sku)
    grni = rules.account(conn, ctx.entity_id, "GOODS_RECEIVED_NOT_INVOICED")
    j = posting.post_system(conn, ctx, event_type="STOCK_RECEIVED", journal_date=d, lines=[
        {"account_id": acc["inventory_account_id"], "debit": money(t["total_cost"]), "product_sku": sku},
        {"account_id": grni["id"], "credit": money(t["total_cost"]), "product_sku": sku,
         "description": f"{ref} awaiting supplier invoice{(' (' + payload['supplier'] + ')') if payload.get('supplier') else ''}"}],
        description=f"Pharmacy received {sku} batch {payload['batch_number']}", source_type="PHARMACY_RECEIPT",
        source_id=str(event_id), source_ref=ref)
    inventory.link_journal(conn, [str(t["id"])], j["id"])
    return ("POSTED", ref, d, "INVENTORY_TXN", str(t["id"]), f"₦{money(t['total_cost']):,.2f} to stock ({j['journal_number']})")


def _post_pharmacy_adjust(conn, ctx, s, payload, event_id):
    """A pharmacy batch adjustment or disposal becomes a DRAFT for Finance to approve."""
    from src.fin import hospital
    if not payload:
        raise invalid("Nothing to post: the adjustment details were not captured")
    d = _local_date(payload.get("date") or dt.date.today())
    ref = f"PADJ-{payload['ops_batch_id']}"
    if _before_cutover(s, d):
        return _skip(ref, d)
    done = q1(conn, """SELECT id, adjustment_number FROM fin_stock_adjustments WHERE legal_entity_id=%s
                       AND source_type='PHARMACY_ADJUST' AND source_id=%s""", (ctx.entity_id, str(event_id)))
    if done:
        return ("POSTED", ref, d, "STOCK_ADJUSTMENT", str(done["id"]), f"Draft {done['adjustment_number']}")
    sku = hospital.ensure_product(conn, ctx.entity_id, payload["formulary_id"])
    batch_id = hospital.fin_batch_for_ops(conn, ctx.entity_id, sku, payload["ops_batch_id"], payload.get("batch_number"),
                                          payload.get("expiry_date"))
    q_ = qty(payload["quantity"])
    reason = str(payload.get("reason_code") or ("EXCESS" if q_ > 0 else "SHORTAGE")).upper()
    adj = inventory.create_adjustment(conn, ctx, {
        "adjustment_date": d, "reason_code": reason, "source_type": "PHARMACY_ADJUST", "source_id": str(event_id),
        "created_by": payload.get("actor") or ctx.actor_id,
        "notes": f"Raised in Pharmacy by {payload.get('actor') or 'pharmacy'}: {payload.get('reason') or reason.lower()}",
        "lines": [{"sku": sku, "batch_id": batch_id, "quantity": q_, "reason": payload.get("reason"),
                   "unit_cost": payload.get("unit_cost") if q_ > 0 else None}]})
    return ("POSTED", ref, d, "STOCK_ADJUSTMENT", str(adj["id"]), f"Draft {adj['adjustment_number']} awaits Finance approval")


# ---------------------------------------------------------------------------
# Payroll (HR) -> salary cost and payment
# ---------------------------------------------------------------------------

def _payroll(conn, rec_id: Any) -> Dict[str, Any]:
    r = q1(conn, """SELECT p.*, s.full_name, s.staff_number FROM royan_payroll_records p
                    JOIN royan_staff s ON s.id=p.staff_id WHERE p.id=%s::uuid""", (str(rec_id),))
    if not r:
        raise not_found("Payroll record", rec_id)
    return r


def _payroll_ref(r: Dict[str, Any]) -> str:
    return f"PAY-{r['period_year']}{r['period_month']:02d}-{r['staff_number']}"


def _payroll_amounts(r: Dict[str, Any]) -> Dict[str, Decimal]:
    """Gross cost and its split, checked against the net HR recorded."""
    tax, pension, other, net = money(r["tax"]), money(r["pension"]), money(r["deductions"]), money(r["net_salary"])
    gross = (money(r["gross_salary"]) + money(r["allowances"])
             + money(Decimal(str(r["overtime_hours"] or 0)) * Decimal(str(r["overtime_rate"] or 0))))
    diff = gross - tax - pension - other - net
    if abs(diff) > Decimal("0.05"):
        raise invalid(f"{_payroll_ref(r)}: net pay ₦{net:,.2f} is not gross ₦{gross:,.2f} less PAYE, pension and "
                      "deductions - correct the record in HR")
    # the record's own net was rounded when it was saved: the cost follows it to the kobo
    return {"gross": gross - diff, "tax": tax, "pension": pension, "other": other, "net": net}


def _post_payroll(conn, ctx, s, payload, rec_id):
    """Approved payroll: the month's salary cost and what is now owed to staff and the tax authorities."""
    r = _payroll(conn, rec_id)
    y, m = r["period_year"], r["period_month"]
    d = dt.date(y + m // 12, m % 12 + 1, 1) - dt.timedelta(days=1)
    ref = _payroll_ref(r)
    if r["status"] not in ("approved", "paid"):
        return ("IGNORED", ref, d, None, None, "Not approved yet")
    if _before_cutover(s, d):
        return _skip(ref, d)
    a = _payroll_amounts(r)
    who = f"{r['full_name']} {d:%b %Y}"
    lines = [{"account_id": rules.account(conn, ctx.entity_id, "SALARIES_EXPENSE")["id"], "debit": a["gross"],
              "description": f"Salary cost: {who}"}]
    for key, amt, label in (("PAYE_PAYABLE", a["tax"], "PAYE"), ("PENSION_PAYABLE", a["pension"], "Pension"),
                            ("PAYROLL_DEDUCTIONS", a["other"], "Other deductions")):
        if amt > 0:
            lines.append({"account_id": rules.account(conn, ctx.entity_id, key)["id"], "credit": amt,
                          "description": f"{label}: {who}"})
    lines.append({"account_id": rules.account(conn, ctx.entity_id, "SALARIES_PAYABLE")["id"], "credit": a["net"],
                  "description": f"Net pay owed: {who}"})
    j = posting.post_system(conn, ctx, event_type="PAYROLL_ACCRUED", journal_date=d, lines=lines,
                            description=f"Payroll {d:%B %Y}: {r['full_name']}", source_type="PAYROLL",
                            source_id=str(r["id"]), source_ref=ref)
    return ("POSTED", ref, d, "JOURNAL", str(j["id"]),
            f"₦{a['gross']:,.2f} salary cost, ₦{a['net']:,.2f} owed ({j['journal_number']})")


def _post_payroll_payment(conn, ctx, s, payload, rec_id):
    """Salaries paid: clears what was owed against the bank it was paid from."""
    r = _payroll(conn, rec_id)
    ref = _payroll_ref(r) + "-PAID"
    d = r["payment_date"] or _local_date(r.get("updated_at") or dt.date.today())
    if r["status"] != "paid":
        return ("IGNORED", ref, d, None, None, "Not paid yet")
    if _before_cutover(s, d):
        return _skip(ref, d)
    accrual = q1(conn, """SELECT status FROM fin_source_postings WHERE legal_entity_id=%s AND source_type='PAYROLL'
                          AND source_id=%s""", (ctx.entity_id, str(r["id"])))
    # an accrual skipped because its month is before cut-over is in the Sage opening balances
    if not accrual or accrual["status"] not in ("POSTED", "SKIPPED"):
        raise FinError("INVALID_STATE_TRANSITION", f"{ref}: the salary cost for this record is not in the books yet - "
                                                    "retry the PAYROLL item first")
    bank_id = r.get("bank_account_id") or (s.get("receipt_accounts") or {}).get("transfer")
    bank = q1(conn, "SELECT gl_account_id, name FROM fin_bank_accounts WHERE id=%s AND legal_entity_id=%s",
              (str(bank_id), ctx.entity_id)) if bank_id else None
    if not bank:
        raise FinError("MAPPING_MISSING", f"{ref}: choose the bank account salaries were paid from")
    net = money(r["net_salary"])
    j = posting.post_system(conn, ctx, event_type="PAYROLL_PAID", journal_date=d, lines=[
        {"account_id": rules.account(conn, ctx.entity_id, "SALARIES_PAYABLE")["id"], "debit": net,
         "description": f"Net pay: {r['full_name']}"},
        {"account_id": bank["gl_account_id"], "credit": net, "description": f"Salary paid: {r['full_name']}"}],
        description=f"Salary paid {d:%d %b %Y}: {r['full_name']} from {bank['name']}", source_type="PAYROLL_PAYMENT",
        source_id=str(r["id"]), source_ref=ref)
    return ("POSTED", ref, d, "JOURNAL", str(j["id"]), f"₦{net:,.2f} paid from {bank['name']} ({j['journal_number']})")


# ---------------------------------------------------------------------------
# Public hooks (called by the operational routers, after their own commit)
# ---------------------------------------------------------------------------

_HANDLERS: Dict[str, Callable] = {
    "BILL": _post_bill,
    "BILL_DISCOUNT": _post_discount,
    "PAYMENT": _post_payment,
    "PAYMENT_VOID": _void_payment,
    "CLAIM_PAYMENT": _post_claim_payment,
    "BILL_VOID": _void_bill,
    "BILL_WAIVER": lambda c, x, s, p, i: _outstanding_credit(c, x, s, i, source_type="BILL_WAIVER",
                                                               debit_key="PATIENT_WAIVERS", label="Waived"),
    "BILL_WRITEOFF": lambda c, x, s, p, i: _outstanding_credit(c, x, s, i, source_type="BILL_WRITEOFF",
                                                                 debit_key="BAD_DEBTS", label="Written off"),
    "BILL_ADJUSTMENT": _post_adjustment,
    "DISPENSING": _post_dispensing,
    "DISPENSE_RETURN": _post_dispense_return,
    "PHARMACY_RECEIPT": _post_pharmacy_receipt,
    "PHARMACY_ADJUST": _post_pharmacy_adjust,
    "PAYROLL": _post_payroll,
    "PAYROLL_PAYMENT": _post_payroll_payment,
}


def post(source_type: str, source_id: Any, *, actor: str = "system", automatic: bool = True,
         payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    fn = _HANDLERS.get(source_type)
    if not fn:
        return {"status": "FAILED", "message": f"Unknown source {source_type}"}
    return _run(source_type, source_id, lambda c, x, s, p: fn(c, x, s, p, source_id), actor=actor, automatic=automatic,
                payload=payload)


def post_event(source_type: str, payload: Dict[str, Any], *, actor: str = "system") -> Dict[str, Any]:
    """Events that are not rows of their own (a receipt or adjustment on a batch row)."""
    return post(source_type, uuid.uuid4().hex, actor=actor, payload={**payload, "actor": actor})


def after_commit(source_type: str, source_id: Any, actor: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Hook for routers: posts the record and returns the outcome (also kept in fin_source_postings). Never raises."""
    try:
        return post(source_type, source_id, actor=actor or "system")
    except Exception:  # the hook must never surface in the operational response
        log.exception("Roy Books hook failed for %s %s", source_type, source_id)
        return None


def exclude(conn, ctx, source_type: str, source_id: str, reason: str) -> Dict[str, Any]:
    """Keep an operational record out of the books for good (tests, duplicates of Sage records)."""
    ctx.require("sales.invoice.post")
    if not (reason or "").strip():
        raise invalid("Give a reason for excluding this record from the books")
    done = q1(conn, """SELECT status, source_ref FROM fin_source_postings WHERE legal_entity_id=%s AND source_type=%s
                       AND source_id=%s""", (ctx.entity_id, source_type, str(source_id)))
    if done and done["status"] == "POSTED":
        raise FinError("INVALID_STATE_TRANSITION", f"{done['source_ref']} is already in the books - void or credit it instead")
    _record(conn, ctx.entity_id, source_type, str(source_id), done["source_ref"] if done else None, "SKIPPED",
            message=f"Excluded from the books: {reason.strip()}", document_type=EXCLUDED_MARK)
    audit.record(conn, ctx, "OPERATION_EXCLUDED", source_type.lower(), str(source_id), reason=reason)
    return {"source_type": source_type, "source_id": str(source_id), "status": "SKIPPED"}


# Operational rows that should be in the books: raised on/after cut-over, native (not Hope),
# and never attempted. Pharmacy receipts/adjustments are events and are only ever attempted.
_UNPOSTED_SQL = {
    "BILL": """SELECT b.id::text AS source_id, b.bill_number AS source_ref, (b.billed_at AT TIME ZONE 'Africa/Lagos')::date AS doc_date,
                      b.subtotal AS amount FROM royan_billing b
               WHERE b.external_source IS NULL AND b.subtotal > 0""",
    "PAYMENT": """SELECT p.id::text, COALESCE(p.receipt_number, 'PAY-' || p.id), (p.received_at AT TIME ZONE 'Africa/Lagos')::date,
                         p.amount FROM royan_payments p WHERE p.external_source IS NULL""",
    "DISPENSING": """SELECT d.id::text, 'DISP-' || d.id, (d.dispensed_at AT TIME ZONE 'Africa/Lagos')::date,
                            d.total_cost FROM royan_dispensing d WHERE d.external_source IS NULL""",
    "PAYROLL": """SELECT p.id::text, 'PAY-' || p.period_year || lpad(p.period_month::text, 2, '0') || '-' || s.staff_number,
                         (make_date(p.period_year, p.period_month, 1) + interval '1 month - 1 day')::date,
                         p.gross_salary + p.allowances + p.overtime_hours * p.overtime_rate
                  FROM royan_payroll_records p JOIN royan_staff s ON s.id=p.staff_id WHERE p.status IN ('approved','paid')""",
    "PAYROLL_PAYMENT": """SELECT p.id::text, 'PAY-' || p.period_year || lpad(p.period_month::text, 2, '0') || '-' || s.staff_number || '-PAID',
                                 p.payment_date, p.net_salary
                          FROM royan_payroll_records p JOIN royan_staff s ON s.id=p.staff_id
                          WHERE p.status='paid' AND p.payment_date IS NOT NULL""",
}


def unposted(conn, entity_id: str) -> List[Dict[str, Any]]:
    s = _settings(conn, entity_id)
    if not s.get("cutover_date"):
        return []
    out: List[Dict[str, Any]] = []
    for st, sql in _UNPOSTED_SQL.items():
        # Posted in either company counts: a Scancare bill / receipt posts to Scancare's books (SCN), and must not
        # show as "not posted" when Royan's books (RHL) are checked (it raised a false alarm on the exec overview).
        rows = q(conn, f"""SELECT x.* FROM ({sql}) x(source_id, source_ref, doc_date, amount)
                          WHERE x.doc_date >= %s AND NOT EXISTS (SELECT 1 FROM fin_source_postings p
                                WHERE p.source_type=%s AND p.source_id=x.source_id)
                          ORDER BY x.doc_date LIMIT 500""", (s["cutover_date"], st))
        out += [{**r, "source_type": st, "label": SOURCE_LABELS[st]} for r in rows]
    return out


# same day: bills before their payments, salary cost before the salary payment
_BACKFILL_ORDER = ["BILL", "PAYMENT", "DISPENSING", "PAYROLL", "PAYROLL_PAYMENT"]


def backfill(date_from: dt.date, date_to: dt.date, actor: str) -> Dict[str, Any]:
    """Post every native bill, payment, dispense and payroll in the range, in that order (bills before their payments).

    Records skipped while Roy Books was not live are picked up here too: posting skips
    only what is already POSTED or EXCLUDED."""
    with tx() as conn:
        work = []
        for st, sql in _UNPOSTED_SQL.items():
            for r in q(conn, f"""SELECT x.source_id, x.doc_date FROM ({sql}) x(source_id, source_ref, doc_date, amount)
                                 WHERE x.doc_date BETWEEN %s AND %s""", (date_from, date_to)):
                work.append((r["doc_date"], _BACKFILL_ORDER.index(st), st, r["source_id"]))
    work.sort()
    results = [post(st, sid, actor=actor, automatic=False) for _, _, st, sid in work]
    summary: Dict[str, int] = {}
    for r in results:
        summary[r["status"]] = summary.get(r["status"], 0) + 1
    return {"processed": len(work), "summary": summary,
            "failed": [{"source": f"{w[2]} {w[3]}", "message": r["message"]} for w, r in zip(work, results) if r["status"] == "FAILED"][:100]}


def retry(source_type: str, source_id: str, actor: str) -> Dict[str, Any]:
    return post(source_type, source_id, actor=actor, automatic=False)
