"""The HMO team's service check (migration 244, services/hmo_review.py) -> Roy Books (BILL_COVER).

A service the HMO does not cover moves from the HMO's invoice to the patient's; an approval obtained later moves it
back. Who owes what must follow each decision, and the books must stay balanced and reconciled throughout.
Rolled back like every Roy Books test.
"""
from decimal import Decimal

import pytest

from src.fin.db import pinned, q, q1
from src.services import hmo_review
from .test_hospital_flows import H, _bill, _handle, _hmo_acct, _open, _pay, _patient_acct, _reconciled  # noqa: F401

HMO_OFFICER = {"sub": "hmo-officer", "email": "hmo@example.test", "roles": ["hmo"]}
DOCTOR = {"sub": "doctor", "email": "doc@example.test", "roles": ["doctor"]}


def _items(H, bill):
    return {r["description"]: r for r in q(H["conn"], "SELECT * FROM royan_bill_items WHERE billing_id=%s", (bill["id"],))}


def test_not_covered_moves_to_patient_and_approval_moves_it_back(H):
    c = H["conn"]
    b = _bill(H, [("consultation", "Consultation", 10000, 10000), ("lab", "Widal test", 40000, 40000)])
    assert _handle(H, "BILL", b["id"])[0] == "POSTED"
    assert _open(H, _hmo_acct(H)) == Decimal("50000")
    lab = _items(H, b)["Widal test"]

    with pinned(c):
        with pytest.raises(PermissionError):                 # only the HMO team decides cover
            hmo_review.decide(lab["id"], "not_covered", None, DOCTOR)
        out = hmo_review.decide(lab["id"], "not_covered", "not on the plan", HMO_OFFICER)
    bill = q1(c, "SELECT hmo_covered, patient_balance FROM royan_billing WHERE id=%s", (b["id"],))
    assert Decimal(str(bill["hmo_covered"])) == 10000 and Decimal(str(bill["patient_balance"])) == 40000
    item = _items(H, b)["Widal test"]
    assert item["hmo_decision"] == "not_covered" and Decimal(str(item["covered_amount"])) == 0 and item["payer_type"] == "private"
    assert hmo_review.hold(item, False)                      # held until paid or approved
    assert _handle(H, "BILL_COVER", out["review_id"])[0] == "POSTED"
    assert _open(H, _patient_acct(H)) == Decimal("40000")
    assert _open(H, _hmo_acct(H)) == Decimal("10000")
    _reconciled(H)

    # the doctor needs it anyway: ask the HMO; the HMO team records the approval
    with pinned(c):
        hmo_review.request_approval(lab["id"], "suspected typhoid", DOCTOR)
        assert "approval has been requested" in hmo_review.hold(_items(H, b)["Widal test"], False)
        with pytest.raises(PermissionError):
            hmo_review.resolve_approval(lab["id"], True, "AUTH-1", None, DOCTOR)
        with pytest.raises(hmo_review.ReviewError):          # an approval needs the HMO's code
            hmo_review.resolve_approval(lab["id"], True, "", None, HMO_OFFICER)
        back = hmo_review.resolve_approval(lab["id"], True, "AUTH-1", None, HMO_OFFICER)
    item = _items(H, b)["Widal test"]
    assert item["hmo_decision"] == "covered" and item["hmo_approval_code"] == "AUTH-1"
    assert Decimal(str(item["covered_amount"])) == 40000 and item["payer_type"] == "hmo"
    assert not hmo_review.hold(item, False)
    assert _handle(H, "BILL_COVER", back["review_id"])[0] == "POSTED"
    assert _open(H, _patient_acct(H)) == 0
    assert _open(H, _hmo_acct(H)) == Decimal("50000")
    _reconciled(H)


def test_declined_stays_with_patient_and_a_paid_service_cannot_move_back(H):
    c = H["conn"]
    b = _bill(H, [("pharmacy", "Artemether", 6000, 6000)])
    _handle(H, "BILL", b["id"])
    drug = _items(H, b)["Artemether"]
    with pinned(c):
        out = hmo_review.decide(drug["id"], "not_covered", None, HMO_OFFICER)
        hmo_review.request_approval(drug["id"], "first-line treatment", DOCTOR)
        declined = hmo_review.resolve_approval(drug["id"], False, None, "excluded", HMO_OFFICER)
    assert declined["review_id"] is None
    item = _items(H, b)["Artemether"]
    assert item["hmo_decision"] == "not_covered" and item["hmo_approval_status"] == "declined"
    _handle(H, "BILL_COVER", out["review_id"])
    _pay(H, b, 6000)
    with pinned(c):
        with pytest.raises(hmo_review.ReviewError):          # refund first, then move it back
            hmo_review.decide(drug["id"], "covered", None, HMO_OFFICER)
    _reconciled(H)
