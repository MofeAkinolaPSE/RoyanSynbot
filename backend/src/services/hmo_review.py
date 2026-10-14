"""The HMO team's check of an HMO patient's services, before the claims form goes out (migration 244).

An HMO patient can be given services their plan does not cover - a drug, a test, a scan. Each billed service on an
HMO visit is one of:

  unchecked     billed to the HMO as usual (Royan's default: the HMO pays in full unless the team says otherwise)
  covered       the HMO team confirmed the plan covers it
  not covered   the HMO team says the plan does not: the amount moves to the patient, the patient pays at the
                cashier before the service is given, and it leaves the claims form

A service that is not covered but the patient needs can be put to the HMO provider: the doctor, the cashier or the
HMO team requests approval (the service is held meanwhile), and the HMO team records the answer - approved, with the
provider's authorisation code, makes it covered again; declined leaves it for the patient to pay. The patient can
always pay instead of waiting.

Every change of who pays is a row in royan_hmo_service_reviews, posted to Roy Books as BILL_COVER (the router calls
post_to_books after the commit, like every other bill hook).
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Dict, List, Optional

from src.fin.db import q, q1, tx

DECIDERS = {"admin", "finance", "hmo"}          # who records the HMO's decision
CLAIM_SENT = ("submitted", "approved", "paid")


class ReviewError(ValueError):
    pass


def _who(user: Dict[str, Any]) -> str:
    return user.get("email") or user.get("sub") or "system"


def _can_decide(user: Dict[str, Any]) -> bool:
    return bool(DECIDERS & {str(r).lower() for r in (user.get("roles") or [])})


def _f(v: Any) -> float:
    return round(float(v or 0), 2)


def _item(conn, item_id: int) -> Dict[str, Any]:
    it = q1(conn, """SELECT i.*, b.bill_number, b.status AS bill_status, b.entity, b.hmo_id AS bill_hmo,
                            e.payer_type AS visit_payer
                     FROM royan_bill_items i JOIN royan_billing b ON b.id=i.billing_id
                     LEFT JOIN royan_encounters e ON e.id=b.encounter_id
                     WHERE i.id=%s FOR UPDATE OF i""", (item_id,))
    if not it:
        raise LookupError("Billed service not found")
    if it["bill_status"] in ("void", "waived", "written_off"):
        raise ReviewError(f"Bill {it['bill_number']} is {it['bill_status']} - nothing to review")
    return it


def _claim_sent(conn, billing_id: int) -> Optional[str]:
    c = q1(conn, "SELECT status FROM royan_insurance_claims WHERE billing_id=%s AND status = ANY(%s) ORDER BY id DESC LIMIT 1",
           (billing_id, list(CLAIM_SENT)))
    return c["status"] if c else None


def _paid(conn, billing_id: int) -> float:
    r = q1(conn, """SELECT COALESCE(SUM(amount),0) AS p FROM royan_payments
                    WHERE billing_id=%s AND COALESCE(status,'posted') <> 'void'""", (billing_id,))
    return _f(r["p"])


def _restatus(conn, billing_id: int) -> None:
    """The bill's status after the patient's share changed: owing, part-paid or paid."""
    b = q1(conn, "SELECT status, patient_balance FROM royan_billing WHERE id=%s", (billing_id,))
    if not b or b["status"] in ("disputed", "void", "waived", "written_off"):
        return
    paid, owed = _paid(conn, billing_id), _f(b["patient_balance"])
    status = "paid" if paid > 0 and paid + 0.009 >= owed else "partial" if paid > 0 else "pending"
    q(conn, """UPDATE royan_billing SET status=%s, paid_at=CASE WHEN %s='paid' THEN COALESCE(paid_at, now()) ELSE NULL END
               WHERE id=%s RETURNING id""", (status, status, billing_id))


def _move(conn, it: Dict[str, Any], decision: str, amount: float, note: Optional[str], user: Dict[str, Any]) -> int:
    """Shift `amount` between the HMO and the patient on one line and its bill; returns the review row (for the books)."""
    sign = -1 if decision == "not_covered" else 1           # HMO share goes down when not covered
    q(conn, """UPDATE royan_bill_items SET covered_amount = covered_amount + %s, patient_amount = patient_amount - %s,
                      payer_type = %s, hmo_decision=%s, hmo_decided_by=%s, hmo_decided_at=now(), hmo_decision_note=%s
               WHERE id=%s RETURNING id""",
      (sign * amount, sign * amount, "private" if decision == "not_covered" else "hmo", decision, _who(user), note, it["id"]))
    q(conn, "UPDATE royan_billing SET hmo_covered = GREATEST(hmo_covered + %s, 0) WHERE id=%s RETURNING id",
      (sign * amount, it["billing_id"]))
    _restatus(conn, it["billing_id"])
    r = q1(conn, """INSERT INTO royan_hmo_service_reviews (bill_item_id, billing_id, encounter_id, decision, amount, note, decided_by)
                    VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
           (it["id"], it["billing_id"], it["encounter_id"], decision, amount, note, _who(user)))
    return int(r["id"])


def decide(item_id: int, decision: str, note: Optional[str], user: Dict[str, Any]) -> Dict[str, Any]:
    """The HMO team marks a billed service covered or not covered. Returns {review_id} when money moved."""
    if decision not in ("covered", "not_covered"):
        raise ReviewError("Decision must be 'covered' or 'not_covered'")
    if not _can_decide(user):
        raise PermissionError("Only the HMO team (or finance / admin) records what the HMO covers")
    with tx() as conn:
        it = _item(conn, item_id)
        if (it.get("visit_payer") or "") not in ("hmo", "staff") and not it.get("bill_hmo") and not it.get("hmo_decision"):
            raise ReviewError("This is not an HMO visit")
        sent = _claim_sent(conn, it["billing_id"])
        if sent:
            raise ReviewError(f"The claim for bill {it['bill_number']} is already {sent} - correct it with the HMO first")
        review_id = None
        if decision == "not_covered":
            if it.get("hmo_decision") == "not_covered":
                raise ReviewError("Already marked not covered")
            amount = _f(it["covered_amount"])
            if amount > 0:
                review_id = _move(conn, it, "not_covered", amount, note, user)
            else:
                q(conn, """UPDATE royan_bill_items SET hmo_decision='not_covered', hmo_decided_by=%s, hmo_decided_at=now(),
                                  hmo_decision_note=%s WHERE id=%s RETURNING id""", (_who(user), note, item_id))
        else:
            if it.get("hmo_decision") == "not_covered":
                last = q1(conn, """SELECT amount FROM royan_hmo_service_reviews WHERE bill_item_id=%s AND decision='not_covered'
                                   ORDER BY id DESC LIMIT 1""", (item_id,))
                amount = _f((last or {}).get("amount"))
                if amount > 0:
                    b = q1(conn, "SELECT patient_balance FROM royan_billing WHERE id=%s", (it["billing_id"],))
                    if _paid(conn, it["billing_id"]) > _f(b["patient_balance"]) - amount + 0.009:
                        raise ReviewError("The patient has already paid for this service - refund it through a bill "
                                          "correction before moving it back to the HMO")
                    review_id = _move(conn, it, "covered", amount, note, user)
                else:
                    q(conn, """UPDATE royan_bill_items SET hmo_decision='covered', hmo_decided_by=%s, hmo_decided_at=now(),
                                      hmo_decision_note=%s WHERE id=%s RETURNING id""", (_who(user), note, item_id))
            else:
                q(conn, """UPDATE royan_bill_items SET hmo_decision='covered', hmo_decided_by=%s, hmo_decided_at=now(),
                                  hmo_decision_note=%s WHERE id=%s RETURNING id""", (_who(user), note, item_id))
    return {"ok": True, "item_id": item_id, "decision": decision, "review_id": review_id}


def request_approval(item_id: int, reason: str, user: Dict[str, Any]) -> Dict[str, Any]:
    """The patient needs a service their HMO does not cover: ask the HMO provider (via the HMO team) to approve it."""
    if not (reason or "").strip():
        raise ReviewError("Say why the patient needs it - the HMO team sends this to the provider")
    with tx() as conn:
        it = _item(conn, item_id)
        if it.get("hmo_decision") != "not_covered":
            raise ReviewError("Only a service marked not covered needs the HMO's approval")
        if it.get("hmo_approval_status") == "requested":
            raise ReviewError("Approval has already been requested")
        q(conn, """UPDATE royan_bill_items SET hmo_approval_status='requested', hmo_approval_reason=%s,
                          hmo_approval_requested_by=%s, hmo_approval_requested_at=now(), hmo_approval_code=NULL,
                          hmo_approval_decided_by=NULL, hmo_approval_decided_at=NULL
                   WHERE id=%s RETURNING id""", (reason.strip(), _who(user), item_id))
    return {"ok": True, "item_id": item_id, "approval_status": "requested"}


def resolve_approval(item_id: int, approved: bool, code: Optional[str], note: Optional[str], user: Dict[str, Any]) -> Dict[str, Any]:
    """The HMO team records the provider's answer. Approved -> covered (back on the HMO's bill and claim)."""
    if not _can_decide(user):
        raise PermissionError("Only the HMO team (or finance / admin) records the HMO provider's answer")
    if approved and not (code or "").strip():
        raise ReviewError("Enter the HMO's authorisation code for the approval")
    with tx() as conn:
        it = _item(conn, item_id)
        if it.get("hmo_approval_status") != "requested":
            raise ReviewError("There is no open approval request on this service")
        q(conn, """UPDATE royan_bill_items SET hmo_approval_status=%s, hmo_approval_code=%s, hmo_approval_decided_by=%s,
                          hmo_approval_decided_at=now() WHERE id=%s RETURNING id""",
          ("approved" if approved else "declined", (code or "").strip() or None, _who(user), item_id))
    out = {"ok": True, "item_id": item_id, "approval_status": "approved" if approved else "declined", "review_id": None}
    if approved:
        out.update({k: v for k, v in decide(item_id, "covered", note or f"Approved by the HMO, code {code}", user).items()
                    if k == "review_id"})
    return out


def hold(item: Dict[str, Any], bill_paid: bool) -> Optional[str]:
    """Why a not-covered HMO service may not be given yet (None = it may). Used by stage_billing.clearance."""
    if item.get("hmo_decision") != "not_covered" or bill_paid:
        return None
    if item.get("hmo_approval_status") == "requested":
        return "Not covered by the patient's HMO - approval has been requested from the HMO; wait for the HMO team, or the patient pays at the cashier."
    return "Not covered by the patient's HMO - the patient pays for it at the cashier first (or ask the HMO team to request approval)."


def visit_services(encounter_id: int) -> Dict[str, Any]:
    """Every billed service on a visit with who pays for it and where the HMO check stands."""
    with tx() as conn:
        enc = q1(conn, """SELECT e.payer_type, e.membership_id, h.name AS hmo_name FROM royan_encounters e
                          LEFT JOIN royan_patient_insurance i ON i.patient_id = e.patient_id AND i.status = 'active'
                          LEFT JOIN royan_hmos h ON h.id = i.hmo_id
                          WHERE e.id=%s ORDER BY i.is_primary DESC NULLS LAST LIMIT 1""", (encounter_id,)) or {}
        rows = q(conn, """SELECT i.id, i.billing_id, b.bill_number, b.entity, b.status AS bill_status, i.description, i.category,
                                 i.quantity, i.unit_price, i.gross_amount, i.covered_amount, i.patient_amount, i.source, i.source_id,
                                 i.hmo_decision, i.hmo_decided_by, i.hmo_decided_at, i.hmo_decision_note,
                                 i.hmo_approval_status, i.hmo_approval_reason, i.hmo_approval_requested_by,
                                 i.hmo_approval_requested_at, i.hmo_approval_code, i.hmo_approval_decided_by, i.hmo_approval_decided_at
                          FROM royan_bill_items i JOIN royan_billing b ON b.id=i.billing_id
                          WHERE b.encounter_id=%s AND b.status <> 'void' ORDER BY i.id""", (encounter_id,))
        paid = {r["billing_id"]: _f(r["p"]) for r in q(conn, """SELECT billing_id, SUM(amount) AS p FROM royan_payments
                     WHERE billing_id = ANY(%s) AND COALESCE(status,'posted') <> 'void' GROUP BY 1""",
                                                        (list({r["billing_id"] for r in rows}) or [0],))}
    out: List[Dict[str, Any]] = []
    for r in rows:
        state = ("approval_requested" if r["hmo_approval_status"] == "requested" else
                 r["hmo_decision"] or "unchecked")
        out.append({**{k: (_f(v) if k in ("unit_price", "gross_amount", "covered_amount", "patient_amount", "quantity") else v)
                       for k, v in r.items()},
                    "state": state, "bill_paid": r["bill_status"] == "paid",
                    "held": hold(r, r["bill_status"] == "paid") is not None})
    return {
        "encounter_id": encounter_id,
        "payer_type": enc.get("payer_type"),
        "hmo_name": enc.get("hmo_name"),
        "membership_id": enc.get("membership_id"),
        "is_hmo": (enc.get("payer_type") or "") in ("hmo", "staff") or any(s["hmo_decision"] for s in out),
        "services": out,
        "summary": {
            "unchecked": sum(1 for s in out if s["state"] == "unchecked"),
            "covered": sum(1 for s in out if s["state"] == "covered"),
            "not_covered": sum(1 for s in out if s["hmo_decision"] == "not_covered"),
            "approval_requested": sum(1 for s in out if s["state"] == "approval_requested"),
            "hmo_total": round(sum(s["covered_amount"] for s in out), 2),
            "patient_total": round(sum(s["patient_amount"] for s in out), 2),
        },
    }


def open_requests() -> List[Dict[str, Any]]:
    """Approval requests waiting for the HMO team, oldest first."""
    with tx() as conn:
        return q(conn, """SELECT i.id, i.description, i.category, i.gross_amount, i.hmo_approval_reason AS reason,
                                 i.hmo_approval_requested_by AS requested_by, i.hmo_approval_requested_at AS requested_at,
                                 b.encounter_id, b.bill_number, p.mrn, concat_ws(' ', p.first_name, p.last_name) AS patient,
                                 h.name AS hmo_name
                          FROM royan_bill_items i JOIN royan_billing b ON b.id=i.billing_id
                          JOIN royan_patients p ON p.id=b.patient_id
                          LEFT JOIN royan_hmos h ON h.id::text = b.hmo_id::text
                          WHERE i.hmo_approval_status='requested' ORDER BY i.hmo_approval_requested_at""")
