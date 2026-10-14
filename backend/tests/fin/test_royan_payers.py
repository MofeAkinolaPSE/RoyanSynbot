"""Royan: HMO claims follow the HMO invoice; who-paid reports; Sage uploads recognise their files.

Same rules as the other hospital golden tests: real schema, throwaway rows, one rolled-back transaction.
"""
import datetime as dt
import os
from decimal import Decimal

import pytest

from src.fin import payers, sage_import, sales
from src.fin.db import ex, q1
from src.fin.hope_charges import payer_type
from tests.fin.test_hospital_flows import H, _bill, _handle, _hmo_acct, _uid  # noqa: F401  (H is a fixture)

EXPORTS = os.path.join(os.path.dirname(__file__), "..", "..", "docs", "Financial-engine", "sage-exports")


def _hmo_invoice(H, covered=30000):
    b = _bill(H, [("consultation", "Consultation", 10000, 0), ("lab", "Full blood count", 40000, covered)])
    _handle(H, "BILL", b["id"])
    inv = q1(H["conn"], "SELECT * FROM fin_sales_invoices WHERE legal_entity_id=%s AND source_type='BILLING_HMO'", (H["ctx"].entity_id,))
    return b, inv


def _bank(H):
    return q1(H["conn"], """SELECT b.id FROM fin_bank_accounts b WHERE b.legal_entity_id=%s AND b.status='ACTIVE'
                            ORDER BY b.created_at LIMIT 1""", (H["ctx"].entity_id,))["id"]


def _hmo_pays(H, inv, amount):
    return sales.create_receipt(H["conn"], H["ctx"], {
        "customer_id": inv["customer_id"], "receipt_date": dt.date(2026, 9, 1), "method": "TRANSFER", "bank_account_id": _bank(H),
        "amount": amount, "reference": "HMO-" + _uid(), "allocations": [{"invoice_id": inv["id"], "amount": amount}]})


def _claim(H, b):
    return q1(H["conn"], """INSERT INTO royan_insurance_claims (billing_id, patient_id, hmo_provider, hmo_id, claim_amount)
                            VALUES (%s,%s,'Test HMO','M-1',30000) RETURNING id""", (b["id"], H["patient"]))["id"]


def _claim_row(H, claim_id):
    return q1(H["conn"], "SELECT * FROM royan_insurance_claims WHERE id=%s", (claim_id,))


def test_hmo_payment_moves_the_claim_to_approved_then_paid(H):
    b, inv = _hmo_invoice(H)
    cid = _claim(H, b)
    r1 = _hmo_pays(H, inv, 10000)
    c = _claim_row(H, cid)
    assert c["status"] == "approved" and Decimal(str(c["approved_amount"])) == Decimal("30000.00")
    assert "received ₦10,000.00" in c["notes"]
    _hmo_pays(H, inv, 20000)
    c = _claim_row(H, cid)
    assert c["status"] == "paid" and c["settled_at"] is not None
    assert c["notes"].count("Roy Books") == 1                  # the books' note is replaced, not appended
    sales.void_receipt(H["conn"], H["ctx"], str(r1["id"]), "bounced")
    assert _claim_row(H, cid)["status"] == "approved"            # back to part paid


def test_hmo_payment_without_a_submitted_claim_records_one(H):
    b, inv = _hmo_invoice(H)
    _hmo_pays(H, inv, 30000)
    c = q1(H["conn"], "SELECT * FROM royan_insurance_claims WHERE billing_id=%s", (b["id"],))
    assert c and c["status"] == "paid" and c["external_source"] == "roy-books"
    assert c["hmo_provider_id"] == H["hmo"]


def test_disallowing_the_whole_hmo_share_rejects_the_claim(H):
    b, inv = _hmo_invoice(H)
    cid = _claim(H, b)
    sales.create_credit_note(H["conn"], H["ctx"], {
        "customer_id": inv["customer_id"], "invoice_id": inv["id"], "note_date": dt.date(2026, 9, 1), "reason": "HMO refused the claim",
        "debit_key": "HMO_DISALLOWANCE", "lines": [{"line_type": "SERVICE", "description": "Disallowed", "quantity": 1, "unit_price": 30000}]})
    assert _claim_row(H, cid)["status"] == "rejected"


def test_payer_types_from_hope_names():
    assert payer_type("7", "Private") == "PRIVATE"
    assert payer_type("102", "RELIANCE HMO") == "HMO"
    assert payer_type("95", "ROYAN STAFF") == "STAFF"
    assert payer_type("88", "RETAINERSHIP- NAMPAK") == "CORPORATE"
    assert payer_type("39", "MONTHLY BILLING PATIENT") == "CORPORATE"
    assert payer_type("136", "FOR SCANCARE ONLY- RELIANCE HMO PAID BY ROYAN") == "INTERNAL"
    assert payer_type("109", "SCANCARE RADIOLOGY AND LAB") == "PRIVATE"


def test_hmo_ageing_applies_receipts_to_the_oldest_month_first(H):
    c, e = H["conn"], H["ctx"].entity_id
    t = 900000 + int(_uid()[:4], 16)
    ex(c, "INSERT INTO fin_hope_payers (tariff_id, name, payer_type) VALUES (%s,%s,'HMO')", (t, "Ageing Test HMO " + _uid()))
    cust = _hmo_acct(H)
    ex(c, "INSERT INTO fin_hope_payer_accounts (customer_id, tariff_id, match_method) VALUES (%s,%s,'test')", (cust, t))
    base = 9_000_000_000 + t * 10
    for n, (d, amt) in enumerate([(dt.date(2025, 1, 10), 100), (dt.date(2025, 2, 10), 200), (dt.date(2025, 6, 10), 300)]):
        ex(c, """INSERT INTO fin_hope_charges (source, hope_id, charge_date, payer_tariff_id, gross) VALUES ('SERVICE',%s,%s,%s,%s)""",
           (base + n, d, t, amt))
    ex(c, """INSERT INTO fin_sage_receipts (legal_entity_id, reference, receipt_date, payer, customer_id, bank_account_code, amount,
             voucher, row_no) VALUES (%s,'T',%s,'Ageing Test',%s,'1090',150,'T',%s)""", (e, dt.date(2025, 3, 1), cust, t))
    row = next(r for r in payers.hmo_ageing(c, e, dt.date(2025, 6, 30)) if r["payer_id"] == t)
    assert row["billed"] == Decimal("600") and row["received"] == Decimal("150.00")
    # January (100) is cleared, February keeps 150 (over 90 days), June 300 is current.
    assert row["owed"] == Decimal("450.00")
    assert row["buckets"][0] == Decimal("300") and row["buckets"][3] == Decimal("150.00")
    assert row["oldest_open"] == dt.date(2025, 2, 1)


@pytest.mark.skipif(not os.path.isdir(EXPORTS), reason="Royan's Sage exports are not in this checkout")
def test_sage_exports_are_recognised_by_content_whatever_their_names():
    files = sage_import.resolve([os.path.join(EXPORTS, "new-exports"), EXPORTS])
    assert set(sage_import.REQUIRED) <= set(files)
    assert {"gj", "vendor_ledgers", "bs_budget", "recon", "ar", "items", "gls", "cf"} <= set(files)
    assert os.path.basename(files["gj"]) == "General Journal.xlsx"
    assert os.path.basename(files["tb"]) == "GL Trial Balance.xlsx"


def test_as_of_is_the_end_of_the_last_month_the_ledger_reaches():
    rows = [("Account ID",), ("1010", "Cash", dt.datetime(2025, 11, 3), "R", "CRJ"), ("1010", "Cash", dt.datetime(2025, 12, 9), "", "GENJ"),
            ("1010", "Cash", dt.datetime(2026, 1, 1), "Beginning Balance", "")]   # no journal: a balance line, not a posting
    assert sage_import.as_of_from_gl(rows) == dt.date(2025, 12, 31)
