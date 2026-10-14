"""Hospital operations -> Roy Books golden tests.

Each test drives the real posting handler for one hospital event against real
royan_* rows (a throwaway patient, HMO, encounter, bill, drug), inside one
rolled-back transaction, on a throwaway entity seeded with the same hospital
template as Royan's books (fin_seed_hospital_template). After every event the
books must still balance and every subledger must agree with its control.
"""
import datetime as dt
import uuid
from decimal import Decimal

import pytest

from src.fin import controls, hospital, integrations, inventory, reports, sales, setup
from src.fin.db import ex, q, q1

D = dt.date(2026, 8, 3)
T = dt.datetime(2026, 8, 3, 10, 0, tzinfo=dt.timezone.utc)


def _uid():
    return uuid.uuid4().hex[:8]


@pytest.fixture
def H(conn, ctx_for):
    code = "H" + _uid()
    ent = setup.ensure_entity(conn, org_code="ORG-" + code, org_name="Test Hospital Group", entity_code=code,
                              entity_name="Test Hospital " + code)
    ctx = ctx_for(ent["id"])
    ex(conn, "SELECT fin_seed_hospital_template(%s, 2026)", (ent["id"],))
    ex(conn, "UPDATE fin_settings SET cutover_date=%s WHERE legal_entity_id=%s", (dt.date(2026, 7, 1), ent["id"]))
    hmo = q1(conn, "INSERT INTO royan_hmos (name, code) VALUES (%s,%s) RETURNING id", ("Test HMO " + _uid(), "THMO" + _uid()))["id"]
    pat = q1(conn, "INSERT INTO royan_patients (mrn, first_name, last_name) VALUES (%s,'Ada','Testpatient') RETURNING id",
             ("TEST-" + _uid(),))["id"]
    ex(conn, "INSERT INTO royan_patient_insurance (patient_id, hmo_id, membership_id) VALUES (%s,%s,%s)", (pat, hmo, "M-" + _uid()))
    enc = q1(conn, "INSERT INTO royan_encounters (patient_id, encounter_type) VALUES (%s,'outpatient') RETURNING id", (pat,))["id"]
    acct = {a["code"]: a for a in q(conn, "SELECT id, code FROM fin_accounts WHERE legal_entity_id=%s", (ent["id"],))}
    return {"conn": conn, "ctx": ctx, "hmo": hmo, "patient": pat, "encounter": enc, "a": acct}


def _settings(H):
    return q1(H["conn"], "SELECT * FROM fin_settings WHERE legal_entity_id=%s", (H["ctx"].entity_id,))


def _handle(H, source_type, source_id, payload=None):
    return integrations._HANDLERS[source_type](H["conn"], H["ctx"], _settings(H), payload, source_id)


def _bill(H, items, discount=0, discount_status="none", external_source=None, billed_at=T):
    """items: (category, description, amount, covered_by_hmo)"""
    c = H["conn"]
    cols = {"consultation": "consultation_fee", "lab": "lab_charges", "pharmacy": "pharmacy_charges", "ward": "ward_charges",
            "procedure": "procedure_charges"}
    sums = {}
    for cat, _, amt, _ in items:
        col = cols.get(cat, "miscellaneous")
        sums[col] = sums.get(col, 0) + amt
    hmo_cov = sum(i[3] for i in items)
    b = q1(c, f"""INSERT INTO royan_billing (encounter_id, patient_id, bill_number, {', '.join(sums)}, discount, hmo_covered,
                   status, discount_status, billed_at, external_source, hmo_id)
                  VALUES (%s,%s,%s,{', '.join(['%s'] * len(sums))},%s,%s,'pending',%s,%s,%s,%s) RETURNING *""",
              [H["encounter"], H["patient"], "TB-" + _uid()] + list(sums.values()) +
              [discount, hmo_cov, discount_status, billed_at, external_source, H["hmo"] if hmo_cov else None])
    for cat, desc, amt, cov in items:
        ex(c, """INSERT INTO royan_bill_items (billing_id, encounter_id, patient_id, description, category, quantity, unit_price,
                 covered_amount, patient_amount) VALUES (%s,%s,%s,%s,%s,1,%s,%s,%s)""",
           (b["id"], H["encounter"], H["patient"], desc, cat, amt, cov, amt - cov))
    return b


def _pay(H, bill, amount, method="cash"):
    return q1(H["conn"], """INSERT INTO royan_payments (billing_id, patient_id, amount, payment_method, received_by, received_at,
                            receipt_number) VALUES (%s,%s,%s,%s,'cashier',%s,%s) RETURNING *""",
              (bill["id"] if bill else None, H["patient"], amount, method, T, "TR-" + _uid()))


def _bal(H, code):
    r = q1(H["conn"], """SELECT COALESCE(SUM(debit-credit),0) b FROM fin_v_general_ledger
                         WHERE legal_entity_id=%s AND account_code=%s""", (H["ctx"].entity_id, code))
    return Decimal(str(r["b"]))


def _open(H, customer_id):
    return sum((Decimal(str(i["open_amount"])) for i in reports.ar_open_items(H["conn"], H["ctx"].entity_id,
                                                                              dt.date(2026, 12, 31), customer_id)), Decimal("0"))


def _reconciled(H):
    on = dt.date(2026, 12, 31)
    bs = reports.balance_sheet(H["conn"], H["ctx"].entity_id, on)
    assert bs["balanced"], bs["difference"]
    res = {r["code"]: r for r in controls.run_checks(H["conn"], H["ctx"].entity_id, on)}
    for code in ("LEDGER_BALANCED", "JOURNALS_BALANCED", "AR_RECONCILES", "AP_RECONCILES", "INVENTORY_RECONCILES"):
        assert res[code]["status"] == "PASS", res[code]


def _patient_acct(H):
    return sales.ensure_patient_customer(H["conn"], H["patient"])


def _hmo_acct(H):
    return sales.ensure_hmo_customer(H["conn"], H["hmo"])


# ---------------------------------------------------------------------------

def test_bill_splits_patient_and_hmo_share_by_service_line(H):
    b = _bill(H, [("consultation", "Consultation", 10000, 0), ("lab", "Full blood count", 40000, 30000)])
    out = _handle(H, "BILL", b["id"])
    assert out[0] == "POSTED"
    assert _bal(H, "11000") == Decimal("20000.00")        # patient owes their share
    assert _bal(H, "11100") == Decimal("30000.00")        # the HMO owes its share
    assert _bal(H, "40100") == Decimal("-10000.00")       # consultation revenue
    assert _bal(H, "40200") == Decimal("-40000.00")       # all lab revenue, whoever pays
    inv = q1(H["conn"], "SELECT * FROM fin_sales_invoices WHERE legal_entity_id=%s AND source_type='BILLING'", (H["ctx"].entity_id,))
    assert inv["invoice_number"] == b["bill_number"]      # the books quote the hospital's bill number
    hmo_inv = q1(H["conn"], "SELECT * FROM fin_sales_invoices WHERE legal_entity_id=%s AND source_type='BILLING_HMO'", (H["ctx"].entity_id,))
    assert hmo_inv["due_date"] == D + dt.timedelta(days=60)
    lab_dept = q1(H["conn"], """SELECT d.code FROM fin_v_general_ledger g JOIN fin_departments d ON d.id=g.department_id
                                WHERE g.legal_entity_id=%s AND g.account_code='40200' LIMIT 1""", (H["ctx"].entity_id,))
    assert lab_dept["code"] == "LAB"
    _reconciled(H)


def test_posting_a_bill_twice_creates_one_set_of_invoices(H):
    b = _bill(H, [("consultation", "Consultation", 5000, 0)])
    _handle(H, "BILL", b["id"])
    _handle(H, "BILL", b["id"])
    n = q1(H["conn"], "SELECT COUNT(*) n FROM fin_sales_invoices WHERE legal_entity_id=%s", (H["ctx"].entity_id,))["n"]
    assert n == 1
    assert _bal(H, "11000") == Decimal("5000.00")


def test_payment_allocates_to_the_bill_and_overpayment_stays_as_credit(H):
    b = _bill(H, [("consultation", "Consultation", 20000, 0)])
    _handle(H, "BILL", b["id"])
    p = _pay(H, b, 25000, "cash")
    out = _handle(H, "PAYMENT", p["id"])
    assert out[0] == "POSTED"
    assert _bal(H, "10100") == Decimal("25000.00")        # cash till
    r = q1(H["conn"], "SELECT * FROM fin_customer_receipts WHERE legal_entity_id=%s", (H["ctx"].entity_id,))
    assert r["receipt_number"] == p["receipt_number"]      # the printed RHR number is the books' receipt number
    assert Decimal(str(r["amount_allocated"])) == Decimal("20000.00")
    inv = q1(H["conn"], "SELECT status FROM fin_sales_invoices WHERE legal_entity_id=%s", (H["ctx"].entity_id,))
    assert inv["status"] == "PAID"
    assert _open(H, _patient_acct(H)) == Decimal("-5000.00")  # a deposit / credit on account
    _reconciled(H)


def test_card_and_transfer_land_in_their_own_accounts(H):
    b = _bill(H, [("lab", "Malaria test", 6000, 0)])
    _handle(H, "BILL", b["id"])
    _handle(H, "PAYMENT", _pay(H, b, 2500, "card")["id"])
    _handle(H, "PAYMENT", _pay(H, b, 3500, "transfer")["id"])
    assert _bal(H, "10200") == Decimal("2500.00")
    assert _bal(H, "10300") == Decimal("3500.00")
    assert _open(H, _patient_acct(H)) == Decimal("0")
    _reconciled(H)


def test_discount_given_at_billing_and_discount_approved_later_go_to_discounts_allowed(H):
    b1 = _bill(H, [("consultation", "Consultation", 10000, 0)], discount=1000, discount_status="none")
    _handle(H, "BILL", b1["id"])
    b2 = _bill(H, [("lab", "Scan", 10000, 0)])
    _handle(H, "BILL", b2["id"])
    ex(H["conn"], """UPDATE royan_billing SET discount=2000, discount_status='approved', discount_reason='Staff relative',
                     discount_decided_at=%s WHERE id=%s""", (T, b2["id"]))
    assert _handle(H, "BILL_DISCOUNT", b2["id"])[0] == "POSTED"
    assert _handle(H, "BILL_DISCOUNT", b2["id"])[0] == "POSTED"   # idempotent
    assert _bal(H, "49000") == Decimal("3000.00")
    assert _open(H, _patient_acct(H)) == Decimal("17000.00")
    _reconciled(H)


def test_pending_discount_is_not_booked_until_approved(H):
    b = _bill(H, [("consultation", "Consultation", 10000, 0)], discount=4000, discount_status="pending")
    _handle(H, "BILL", b["id"])
    assert _bal(H, "49000") == Decimal("0")
    assert _open(H, _patient_acct(H)) == Decimal("10000.00")


def test_waiver_and_write_off_charge_their_own_heads(H):
    b1 = _bill(H, [("ward", "Ward stay", 30000, 0)])
    b2 = _bill(H, [("procedure", "Dressing", 8000, 0)])
    _handle(H, "BILL", b1["id"])
    _handle(H, "BILL", b2["id"])
    _handle(H, "PAYMENT", _pay(H, b1, 10000)["id"])
    assert _handle(H, "BILL_WAIVER", b1["id"])[0] == "POSTED"
    assert _handle(H, "BILL_WRITEOFF", b2["id"])[0] == "POSTED"
    assert _bal(H, "63000") == Decimal("20000.00")        # only what was still owed is waived
    assert _bal(H, "63100") == Decimal("8000.00")
    assert _open(H, _patient_acct(H)) == Decimal("0")
    _reconciled(H)


def test_hmo_payment_method_moves_the_patients_share_to_their_hmo(H):
    b = _bill(H, [("consultation", "Consultation", 15000, 0)])
    _handle(H, "BILL", b["id"])
    out = _handle(H, "PAYMENT", _pay(H, b, 15000, "hmo")["id"])
    assert out[0] == "POSTED", out
    assert _open(H, _patient_acct(H)) == Decimal("0")
    assert _open(H, _hmo_acct(H)) == Decimal("15000.00")
    assert _bal(H, "11000") == Decimal("0")
    assert _bal(H, "11100") == Decimal("15000.00")
    assert _bal(H, "48000") == Decimal("0")               # the move nets to nil in returns & allowances
    _reconciled(H)


def test_correction_pen_reduction_refund_and_reversal(H):
    """The meeting's example: a 90k bag of blood the patient did not use."""
    b = _bill(H, [("procedure", "Blood transfusion (1 unit)", 90000, 0)])
    _handle(H, "BILL", b["id"])
    _handle(H, "PAYMENT", _pay(H, b, 90000)["id"])
    red = q1(H["conn"], """INSERT INTO royan_bill_adjustments (billing_id, patient_id, adjustment_type, amount, reason, adjusted_at)
                           VALUES (%s,%s,'reduction',50000,'Blood not used',%s) RETURNING id""", (b["id"], H["patient"], T))
    assert _handle(H, "BILL_ADJUSTMENT", red["id"])[0] == "POSTED"
    assert _open(H, _patient_acct(H)) == Decimal("-50000.00")   # the patient is now in credit
    ref = q1(H["conn"], """INSERT INTO royan_bill_adjustments (billing_id, patient_id, adjustment_type, amount, reason, adjusted_at)
                           VALUES (%s,%s,'refund',50000,'Refund for unused blood',%s) RETURNING id""", (b["id"], H["patient"], T))
    out = _handle(H, "BILL_ADJUSTMENT", ref["id"])
    assert out[0] == "POSTED", out
    assert _bal(H, "10100") == Decimal("40000.00")        # 90k in, 50k back out
    assert _open(H, _patient_acct(H)) == Decimal("0")
    _reconciled(H)


def test_reallocation_moves_the_amount_to_the_named_payer(H):
    b = _bill(H, [("ward", "Room 102 x2", 80000, 0)])
    _handle(H, "BILL", b["id"])
    adj = q1(H["conn"], """INSERT INTO royan_bill_adjustments (billing_id, patient_id, adjustment_type, amount, reason,
                           reallocated_to, adjusted_at) VALUES (%s,%s,'reallocation',30000,'Employer covers room',
                           'Acme Staff Scheme',%s) RETURNING id""", (b["id"], H["patient"], T))
    assert _handle(H, "BILL_ADJUSTMENT", adj["id"])[0] == "POSTED"
    corp = q1(H["conn"], "SELECT id FROM fin_customers WHERE party_type='CORPORATE' AND name='Acme Staff Scheme'")["id"]
    assert _open(H, corp) == Decimal("30000.00")
    assert _open(H, _patient_acct(H)) == Decimal("50000.00")
    _reconciled(H)


def test_dispensing_posts_cost_from_the_batch_and_recall_names_the_patient(H):
    c = H["conn"]
    f = q1(c, "INSERT INTO royan_drug_formulary (code, generic_name, strength) VALUES (%s,'Amoxicillin','500mg') RETURNING id",
           ("TST" + _uid(),))["id"]
    ob = q1(c, """INSERT INTO royan_inventory_batches (formulary_id, batch_number, quantity_on_hand, quantity_received, unit_cost,
                  expiry_date) VALUES (%s,'AMX-01',100,100,150,'2028-01-31') RETURNING id""", (f,))["id"]
    sku = hospital.ensure_product(c, H["ctx"].entity_id, f)
    bid = hospital.fin_batch_for_ops(c, H["ctx"].entity_id, sku, ob, None)
    inventory.receive(c, H["ctx"], sku=sku, quantity=100, unit_cost=150, txn_type="OPENING_BALANCE", txn_date=dt.date(2026, 6, 30),
                      batch_id=bid, source_type="PHARMACY_OPENING", source_id=str(ob), mirror=False)
    # the opening stock is behind the (here: absent) trial balance - give it its GL side for the test
    from src.fin import posting
    posting.post_system(c, H["ctx"], event_type="TEST_OPENING", journal_date=dt.date(2026, 7, 1), lines=[
        {"account_code": "12000", "debit": 15000}, {"account_code": "39004", "credit": 15000}],
        description="test opening stock", source_type="TEST", source_id="open")
    d = q1(c, """INSERT INTO royan_dispensing (patient_id, drug_name, quantity_dispensed, dispensed_by, dispensed_at, formulary_id,
                 batch_id, batch_number) VALUES (%s,'Amoxicillin 500mg',21,'pharm',%s,%s,%s,'AMX-01') RETURNING id""",
           (H["patient"], T, f, ob))["id"]
    out = _handle(H, "DISPENSING", d)
    assert out[0] == "POSTED", out
    assert _bal(H, "50000") == Decimal("3150.00")          # 21 x 150
    assert _bal(H, "12000") == Decimal("11850.00")
    trace = inventory.trace_batch(c, H["ctx"].entity_id, bid)
    assert [x["customer_id"] for x in trace["customers"]] == [_patient_acct(H)]
    # pharmacy's live stock was already moved by the pharmacy - the books never move it again
    assert Decimal(str(q1(c, "SELECT quantity_on_hand q FROM royan_inventory_batches WHERE id=%s", (ob,))["q"])) == Decimal("100")
    ret = q1(c, """INSERT INTO royan_sales_returns (dispensing_id, patient_id, quantity_returned, reason, restocked, processed_by,
                   processed_at) VALUES (%s,%s,5,'Unopened',TRUE,'pharm',%s) RETURNING id""", (d, H["patient"], T))["id"]
    assert _handle(H, "DISPENSE_RETURN", ret)[0] == "POSTED"
    assert _bal(H, "50000") == Decimal("2400.00")          # 16 x 150
    _reconciled(H)


def test_pharmacy_receipt_uses_goods_received_not_invoiced_and_adjustments_wait_for_finance(H):
    c = H["conn"]
    f = q1(c, "INSERT INTO royan_drug_formulary (code, generic_name) VALUES (%s,'Paracetamol') RETURNING id", ("TST" + _uid(),))["id"]
    ob = q1(c, """INSERT INTO royan_inventory_batches (formulary_id, batch_number, quantity_on_hand, quantity_received, unit_cost)
                  VALUES (%s,'PCM-9',200,200,20) RETURNING id""", (f,))["id"]
    rec = _handle(H, "PHARMACY_RECEIPT", "evt1", {"formulary_id": f, "ops_batch_id": ob, "batch_number": "PCM-9", "quantity": 200,
                                                   "unit_cost": 20, "supplier": "Emzor", "date": "2026-08-03"})
    assert rec[0] == "POSTED", rec
    assert _bal(H, "12000") == Decimal("4000.00")
    assert _bal(H, "21100") == Decimal("-4000.00")
    adj = _handle(H, "PHARMACY_ADJUST", "evt2", {"formulary_id": f, "ops_batch_id": ob, "quantity": -10, "reason_code": "DAMAGE",
                                                 "reason": "Broken bottles", "date": "2026-08-03", "actor": "pharm1"})
    assert adj[0] == "POSTED"
    draft = q1(c, "SELECT * FROM fin_stock_adjustments WHERE id=%s", (adj[4],))
    assert draft["status"] == "DRAFT" and draft["created_by"] == "pharm1"
    assert _bal(H, "58500") == Decimal("0")                 # nothing booked until Finance approves
    posted = inventory.post_adjustment(c, H["ctx"], adj[4])
    assert posted["status"] == "POSTED"
    assert _bal(H, "58500") == Decimal("200.00")
    # approving a pharmacy adjustment never moves the pharmacy's stock a second time
    assert Decimal(str(q1(c, "SELECT quantity_on_hand q FROM royan_inventory_batches WHERE id=%s", (ob,))["q"])) == Decimal("200")
    _reconciled(H)


def test_hope_history_and_bills_before_cutover_never_post(H):
    old = _bill(H, [("consultation", "Consultation", 7000, 0)], billed_at=dt.datetime(2026, 6, 15, tzinfo=dt.timezone.utc))
    hope = _bill(H, [("consultation", "Consultation", 7000, 0)], external_source="hope")
    assert _handle(H, "BILL", old["id"])[0] == "SKIPPED"
    assert _handle(H, "BILL", hope["id"])[0] == "SKIPPED"
    assert _bal(H, "11000") == Decimal("0")


def test_opening_pharmacy_stock_values_every_costed_live_batch(conn, ctx_for):
    code = "P" + _uid()
    ent = setup.ensure_entity(conn, org_code="ORG-" + code, org_name="Stock Test", entity_code=code, entity_name="Stock Test")
    ctx = ctx_for(ent["id"])
    ex(conn, "SELECT fin_seed_hospital_template(%s, 2026)", (ent["id"],))
    expect = q1(conn, """SELECT COUNT(*) n, COALESCE(SUM(round(quantity_on_hand*unit_cost, 2)),0) v FROM royan_inventory_batches
                         WHERE quantity_on_hand > 0 AND unit_cost > 0""")
    out = hospital.load_pharmacy_opening_stock(conn, ctx, dt.date(2026, 6, 30))
    assert out["batches"] == expect["n"]
    assert Decimal(out["value"]) == Decimal(str(expect["v"]))
    val = reports.inventory_valuation(conn, ctx.entity_id, dt.date(2026, 6, 30))
    assert Decimal(str(val["total_value"])) == Decimal(str(expect["v"]))
