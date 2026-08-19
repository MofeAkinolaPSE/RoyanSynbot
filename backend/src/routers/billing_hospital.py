"""Hospital billing, payments, HMO claims, and coverage-aware bill creation."""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.constants import (
    BILL_STATUS_ALLOWED,
    CLAIM_STATUS_ALLOWED,
    PAYMENT_METHODS_ALLOWED,
    TABLE_BILL_ITEMS,
    TABLE_BILLING,
    TABLE_DISPENSING,
    TABLE_ENCOUNTERS,
    TABLE_INPATIENT_BILL_LINES,
    TABLE_INSURANCE_CLAIMS,
    TABLE_LAB_CATALOG,
    TABLE_LAB_ORDERS,
    TABLE_PATIENTS,
    TABLE_PAYMENTS,
    TABLE_PRESCRIPTIONS,
)
from src.db import audit_event, db
from src.services.amount_in_words import naira_in_words
from src.services.event_service import emit_clinical_event
from src.middleware import require_role, verify_jwt
from src.services.coverage import CoverageInput, billing_breakdown_from_quotes, calculate_coverage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/billing_hospital", tags=["Hospital Billing"])


class BillCreate(BaseModel):
    encounter_id: int
    patient_id: int
    consultation_fee: float = Field(0.0, ge=0)
    lab_charges: float = Field(0.0, ge=0)
    pharmacy_charges: float = Field(0.0, ge=0)
    ward_charges: float = Field(0.0, ge=0)
    procedure_charges: float = Field(0.0, ge=0)
    miscellaneous: float = Field(0.0, ge=0)
    discount: float = Field(0.0, ge=0)
    hmo_covered: float = Field(0.0, ge=0)
    payment_method: Optional[str] = None
    notes: Optional[str] = None


class BillItemInput(BaseModel):
    service_id: Optional[int] = None
    service_code: Optional[str] = None
    description: str = Field(..., min_length=1)
    category: str = "misc"
    quantity: float = Field(1.0, gt=0)
    unit_price: float = Field(0.0, ge=0)
    # payer_type is normally auto-derived from the coverage quote (hmo vs
    # private); pass "staff" explicitly since nothing in the schema
    # identifies a patient as hospital staff today.
    payer_type: Optional[str] = Field(None, pattern="^(hmo|staff|private)$")


class BillFromEncounterRequest(BaseModel):
    encounter_id: int
    patient_id: Optional[int] = None
    items: list[BillItemInput] = Field(default_factory=list)
    discount: float = Field(0.0, ge=0)
    notes: Optional[str] = None


class PaymentCreate(BaseModel):
    amount: float = Field(..., gt=0)
    payment_method: str
    reference: Optional[str] = None
    reference_number: Optional[str] = None
    notes: Optional[str] = None

    model_config = {"extra": "ignore"}


class ClaimCreate(BaseModel):
    billing_id: Optional[int] = None
    bill_id: Optional[int] = None
    patient_id: Optional[int] = None
    hmo_provider: Optional[str] = None
    insurer_name: Optional[str] = None
    hmo_id: Optional[str] = None
    claim_amount: float = Field(..., gt=0)
    notes: Optional[str] = None

    model_config = {"extra": "ignore"}


class ClaimStatusUpdate(BaseModel):
    status: str
    authorisation_code: Optional[str] = None
    approved_amount: Optional[float] = None
    notes: Optional[str] = None


# Maps royan_service_catalog.category -> the department the MD's finance
# toggle groups by. Only Lab/Pharmacy/Radiology are "their own business" per
# the client; everything else (consultation/ward/procedure/misc) rolls up
# under General rather than inventing departments nobody asked for.
_DEPARTMENT_BY_CATEGORY = {
    "lab": "Lab",
    "pharmacy": "Pharmacy",
    "imaging": "Radiology",
}


def _department_for_category(category: Optional[str]) -> str:
    return _DEPARTMENT_BY_CATEGORY.get((category or "").lower(), "General")


def _num(value, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _generate_bill_number() -> str:
    result = db.rpc("generate_bill_number", {}).execute()
    if result.data:
        row = result.data[0]
        return row.get("generate_bill_number") if isinstance(row, dict) else str(row)
    raise RuntimeError("Bill number generation failed")


def _get_bill(bill_id: int) -> dict:
    result = db.table(TABLE_BILLING).select("*").eq("id", bill_id).limit(1).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail=f"Bill {bill_id} not found")
    return result.data[0]


def _total_from_bill(bill: dict) -> float:
    if bill.get("subtotal") is not None:
        return _num(bill.get("subtotal"))
    return sum(
        _num(bill.get(field))
        for field in ("consultation_fee", "lab_charges", "pharmacy_charges", "ward_charges", "procedure_charges", "miscellaneous")
    )


def _bill_with_amounts(bill: dict) -> dict:
    payments = db.table(TABLE_PAYMENTS).select("amount").eq("billing_id", bill["id"]).execute().data or []
    amount_paid = round(sum(_num(row.get("amount")) for row in payments), 2)
    patient_balance = _num(bill.get("patient_balance"), _total_from_bill(bill) - _num(bill.get("discount")) - _num(bill.get("hmo_covered")))
    total_amount = _total_from_bill(bill)
    return {
        **bill,
        "total_amount": round(total_amount, 2),
        "amount_paid": amount_paid,
        "outstanding": round(max(patient_balance - amount_paid, 0.0), 2),
        "patient_due": round(patient_balance, 2),
        "created_at": bill.get("billed_at"),
    }


def _audit(event_type: str, details: dict, user: dict, subject_type: str, subject_id: str | int | None) -> None:
    audit_event(event_type, details, actor_id=user.get("sub"), subject_type=subject_type, subject_id=str(subject_id or ""))


@router.post("/bills", status_code=201)
async def create_bill(payload: BillCreate, user=Depends(verify_jwt)):
    if payload.payment_method and payload.payment_method not in PAYMENT_METHODS_ALLOWED | {"mixed"}:
        raise HTTPException(status_code=422, detail="Invalid payment_method")

    bill_number = _generate_bill_number()
    data = payload.model_dump(exclude_none=True)
    data["bill_number"] = bill_number
    data["status"] = "pending"
    data["billed_by"] = user.get("sub") or "system"

    try:
        result = db.table(TABLE_BILLING).insert(data).execute()
    except Exception as exc:
        logger.error("Bill creation failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to create bill")

    bill = (result.data or [data])[0]
    _audit("bill_created", {"bill_number": bill_number, "encounter_id": payload.encounter_id}, user, "bill", bill.get("id"))
    emit_clinical_event(
        event_type="BILL_GENERATED",
        encounter_id=payload.encounter_id,
        patient_id=payload.patient_id,
        entity_type="bill", entity_id=bill.get("id"),
        performed_by=user.get("sub"),
        event_data={"bill_number": bill_number},
    )
    return {"ok": True, "bill": _bill_with_amounts(bill)}


@router.post("/bills/from-encounter", status_code=201)
async def create_bill_from_encounter(payload: BillFromEncounterRequest, user=Depends(verify_jwt)):
    encounter = db.table(TABLE_ENCOUNTERS).select("*").eq("id", payload.encounter_id).limit(1).execute()
    if not encounter.data:
        raise HTTPException(status_code=404, detail=f"Encounter {payload.encounter_id} not found")
    enc = encounter.data[0]
    patient_id = payload.patient_id or enc.get("patient_id")
    if not patient_id:
        raise HTTPException(status_code=422, detail="patient_id is required")
    if not payload.items:
        raise HTTPException(status_code=422, detail="At least one bill item is required")

    quotes = [
        calculate_coverage(
            CoverageInput(
                patient_id=int(patient_id),
                encounter_id=payload.encounter_id,
                service_id=item.service_id,
                service_code=item.service_code,
                service_name=item.description,
                category=item.category,
                quantity=item.quantity,
                unit_price=item.unit_price,
            )
        )
        for item in payload.items
    ]
    breakdown = billing_breakdown_from_quotes(quotes)
    bill_number = _generate_bill_number()
    bill_data = {
        "encounter_id": payload.encounter_id,
        "patient_id": patient_id,
        "bill_number": bill_number,
        **breakdown,
        "discount": payload.discount,
        "status": "pending",
        "billed_by": user.get("sub") or "system",
        "notes": payload.notes,
    }

    try:
        result = db.table(TABLE_BILLING).insert(bill_data).execute()
    except Exception as exc:
        logger.error("Coverage bill creation failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to create coverage-aware bill")
    bill = (result.data or [bill_data])[0]
    bill_id = bill.get("id")

    item_rows = []
    for item, quote in zip(payload.items, quotes):
        service = quote.get("service") or {}
        category = service.get("category") or item.category
        payer_type = item.payer_type or ("hmo" if (quote.get("insurance") or {}).get("active") else "private")
        item_rows.append({
            "billing_id": bill_id,
            "encounter_id": payload.encounter_id,
            "patient_id": patient_id,
            "service_id": service.get("id"),
            "service_code": service.get("service_code") or item.service_code,
            "description": item.description,
            "category": category,
            "department": _department_for_category(category),
            "payer_type": payer_type,
            "quantity": item.quantity,
            "unit_price": item.unit_price,
            "covered_amount": quote.get("covered_amount") or 0,
            "patient_amount": quote.get("patient_amount") or 0,
            "requires_approval": bool(quote.get("requires_approval")),
            "approval_required_reason": quote.get("approval_required_reason"),
            "coverage_rule_id": quote.get("coverage_rule_id"),
            "coverage_snapshot": quote,
        })
    if item_rows:
        db.table(TABLE_BILL_ITEMS).insert(item_rows).execute()

    if any(q.get("requires_approval") for q in quotes):
        db.table(TABLE_BILLING).update({"status": "disputed"}).eq("id", bill_id).execute()
        bill["status"] = "disputed"

    _audit("coverage_bill_created", {"bill_number": bill_number, "items": len(item_rows), "hmo_covered": breakdown["hmo_covered"]}, user, "bill", bill_id)
    return {"ok": True, "bill": _bill_with_amounts(bill), "items": item_rows, "coverage_quotes": quotes}


@router.get("/bills")
async def list_bills(
    patient_id: Optional[int] = Query(None),
    encounter_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    user=Depends(verify_jwt),
):
    # Live worklist = native bills only (external_source IS NULL). Hope's
    # historical import (259k+ rows, confirmed) must never crowd out or
    # masquerade as an actionable bill — same filter queue_clinical.py's
    # list_encounters already applies for the identical reason.
    query = db.table(TABLE_BILLING).select("*").is_("external_source", None).order("billed_at", desc=True).limit(limit)
    if patient_id:
        query = query.eq("patient_id", patient_id)
    if encounter_id:
        query = query.eq("encounter_id", encounter_id)
    if status:
        if status not in BILL_STATUS_ALLOWED:
            raise HTTPException(status_code=422, detail=f"Unknown status '{status}'")
        query = query.eq("status", status)
    result = query.execute()
    bills = [_bill_with_amounts(row) for row in (result.data or [])]

    # Attach patient name/MRN so the frontend can show who a bill actually
    # belongs to instead of a bare numeric id — a mismatch here was previously
    # invisible at a glance (see the "wrong patient's billing" bug).
    patient_ids = {b.get("patient_id") for b in bills if b.get("patient_id")}
    if patient_ids:
        patients = (
            db.table(TABLE_PATIENTS)
            .select("id,first_name,last_name,mrn")
            .in_("id", list(patient_ids))
            .execute()
        )
        by_id = {p["id"]: p for p in (patients.data or [])}
        for b in bills:
            p = by_id.get(b.get("patient_id"))
            if p:
                b["patient_name"] = f"{p.get('first_name', '')} {p.get('last_name', '')}".strip()
                b["patient_mrn"] = p.get("mrn")

    return {"bills": bills, "count": len(bills)}


@router.get("/bills/{bill_id}")
async def get_bill(bill_id: int, user=Depends(verify_jwt)):
    bill = _bill_with_amounts(_get_bill(bill_id))
    payments = db.table(TABLE_PAYMENTS).select("*").eq("billing_id", bill_id).order("received_at", desc=True).execute()
    claims = db.table(TABLE_INSURANCE_CLAIMS).select("*").eq("billing_id", bill_id).execute()
    items = db.table(TABLE_BILL_ITEMS).select("*").eq("billing_id", bill_id).execute()
    return {"bill": bill, "items": items.data or [], "payments": payments.data or [], "claims": claims.data or []}


@router.post("/bills/{bill_id}/payment")
async def record_payment(bill_id: int, payload: PaymentCreate, user=Depends(verify_jwt)):
    bill = _get_bill(bill_id)
    if bill["status"] in ("paid", "waived", "written_off"):
        raise HTTPException(status_code=409, detail=f"Bill is already '{bill['status']}'")
    if payload.payment_method not in PAYMENT_METHODS_ALLOWED:
        raise HTTPException(status_code=422, detail=f"payment_method must be one of {sorted(PAYMENT_METHODS_ALLOWED)}")

    data = {
        "billing_id": bill_id,
        "patient_id": bill["patient_id"],
        "amount": payload.amount,
        "payment_method": payload.payment_method,
        "reference": payload.reference or payload.reference_number,
        "notes": payload.notes,
        "received_by": user.get("sub") or "system",
    }
    try:
        result = db.table(TABLE_PAYMENTS).insert(data).execute()
    except Exception as exc:
        logger.error("Payment insert failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to record payment")

    all_payments = db.table(TABLE_PAYMENTS).select("amount").eq("billing_id", bill_id).execute()
    total_paid = sum(_num(p.get("amount")) for p in all_payments.data or [])
    balance = _num(bill.get("patient_balance"))
    new_status = "paid" if total_paid >= balance else "partial"
    update: dict = {"status": new_status}
    if new_status == "paid":
        from datetime import datetime, timezone
        update["paid_at"] = datetime.now(timezone.utc).isoformat()
    db.table(TABLE_BILLING).update(update).eq("id", bill_id).execute()

    _audit("payment_recorded", {"amount": payload.amount, "method": payload.payment_method, "bill_status": new_status}, user, "bill", bill_id)
    emit_clinical_event(
        event_type="PAYMENT_RECEIVED",
        encounter_id=bill.get("encounter_id"),
        patient_id=bill.get("patient_id"),
        entity_type="bill", entity_id=bill_id,
        performed_by=user.get("sub"),
        event_data={"amount": payload.amount, "method": payload.payment_method, "bill_status": new_status},
    )
    return {"ok": True, "payment": (result.data or [data])[0], "bill_status": new_status}


@router.post("/bills/{bill_id}/waive")
async def waive_bill(bill_id: int, user=Depends(require_role("admin"))):
    bill = _get_bill(bill_id)
    if bill["status"] in ("paid", "waived"):
        raise HTTPException(status_code=409, detail=f"Bill already '{bill['status']}'")
    db.table(TABLE_BILLING).update({"status": "waived"}).eq("id", bill_id).execute()
    _audit("bill_waived", {}, user, "bill", bill_id)
    return {"ok": True, "bill_id": bill_id, "status": "waived"}


@router.post("/claims", status_code=201)
async def submit_claim(payload: ClaimCreate, user=Depends(verify_jwt)):
    billing_id = payload.billing_id or payload.bill_id
    if not billing_id:
        raise HTTPException(status_code=422, detail="billing_id is required")
    bill = _get_bill(int(billing_id))
    patient = db.table(TABLE_PATIENTS).select("id,hmo_provider,hmo_id").eq("id", payload.patient_id or bill["patient_id"]).limit(1).execute()
    patient_row = (patient.data or [{}])[0]
    hmo_provider = payload.hmo_provider or payload.insurer_name or patient_row.get("hmo_provider")
    hmo_id = payload.hmo_id or patient_row.get("hmo_id") or "unknown"
    if not hmo_provider:
        raise HTTPException(status_code=422, detail="hmo_provider is required")

    data = {
        "billing_id": billing_id,
        "patient_id": payload.patient_id or bill["patient_id"],
        "hmo_provider": hmo_provider,
        "hmo_id": hmo_id,
        "claim_amount": payload.claim_amount,
        "status": "submitted",
        "notes": payload.notes,
    }
    try:
        result = db.table(TABLE_INSURANCE_CLAIMS).insert(data).execute()
    except Exception as exc:
        logger.error("Claim submission failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to submit claim")
    claim = (result.data or [data])[0]
    _audit("hmo_claim_submitted", {"hmo": hmo_provider, "amount": payload.claim_amount}, user, "bill", billing_id)
    emit_clinical_event(
        event_type="INSURANCE_CLAIM_SUBMITTED",
        encounter_id=bill.get("encounter_id"),
        patient_id=data["patient_id"],
        entity_type="insurance_claim", entity_id=claim.get("id"),
        performed_by=user.get("sub"),
        event_data={"hmo_provider": hmo_provider, "claim_amount": payload.claim_amount},
    )
    return {"ok": True, "claim": {**claim, "insurer_name": hmo_provider, "bill_id": billing_id}}


@router.get("/claims")
async def list_claims(
    status: Optional[str] = Query(None),
    hmo_provider: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    user=Depends(verify_jwt),
):
    query = db.table(TABLE_INSURANCE_CLAIMS).select("*").order("submitted_at", desc=True).limit(limit)
    if status:
        if status not in CLAIM_STATUS_ALLOWED:
            raise HTTPException(status_code=422, detail=f"Unknown claim status '{status}'")
        query = query.eq("status", status)
    if hmo_provider:
        query = query.eq("hmo_provider", hmo_provider)
    result = query.execute()
    claims = [{**row, "insurer_name": row.get("hmo_provider"), "bill_id": row.get("billing_id")} for row in (result.data or [])]
    return {"claims": claims, "count": len(claims)}


@router.patch("/claims/{claim_id}")
async def update_claim_status(claim_id: int, payload: ClaimStatusUpdate, user=Depends(verify_jwt)):
    if payload.status not in CLAIM_STATUS_ALLOWED:
        raise HTTPException(status_code=422, detail=f"status must be one of {sorted(CLAIM_STATUS_ALLOWED)}")
    claim = db.table(TABLE_INSURANCE_CLAIMS).select("id").eq("id", claim_id).limit(1).execute()
    if not claim.data:
        raise HTTPException(status_code=404, detail=f"Claim {claim_id} not found")
    updates: dict = {"status": payload.status}
    if payload.authorisation_code:
        updates["authorisation_code"] = payload.authorisation_code
    if payload.approved_amount is not None:
        updates["approved_amount"] = payload.approved_amount
    if payload.notes:
        updates["notes"] = payload.notes
    if payload.status == "paid":
        from datetime import datetime, timezone
        updates["settled_at"] = datetime.now(timezone.utc).isoformat()
    db.table(TABLE_INSURANCE_CLAIMS).update(updates).eq("id", claim_id).execute()
    _audit("hmo_claim_updated", {"status": payload.status}, user, "insurance_claim", claim_id)
    return {"ok": True, "claim_id": claim_id, "status": payload.status}


@router.get("/stats")
async def billing_stats(user=Depends(verify_jwt)):
    """Server-computed KPI snapshot across ALL bills/claims — not capped by
    list_bills' limit, and not scoped to whatever bill-status filter pill or
    tab the frontend currently has active (the two client-side aggregation
    bugs this replaces)."""
    open_bills = (
        db.table(TABLE_BILLING)
        .select("id,status,patient_balance,consultation_fee,lab_charges,pharmacy_charges,"
                "ward_charges,procedure_charges,miscellaneous,discount,hmo_covered,subtotal")
        .is_("external_source", None)
        .in_("status", ["pending", "partial", "disputed"])
        .execute().data or []
    )
    pending_count  = sum(1 for b in open_bills if b["status"] == "pending")
    partial_count  = sum(1 for b in open_bills if b["status"] == "partial")
    disputed_count = sum(1 for b in open_bills if b["status"] == "disputed")

    # record_payment always flips status to "paid"/"partial" the instant any
    # payment is recorded — a "pending" or "disputed" bill is therefore
    # guaranteed to have zero payments, so only "partial" bills need a
    # payments lookup. One batched query, not N+1.
    partial_ids = [b["id"] for b in open_bills if b["status"] == "partial"]
    paid_by_bill: dict[int, float] = {}
    if partial_ids:
        for p in (db.table(TABLE_PAYMENTS).select("billing_id,amount").in_("billing_id", partial_ids).execute().data or []):
            paid_by_bill[p["billing_id"]] = paid_by_bill.get(p["billing_id"], 0.0) + _num(p.get("amount"))

    total_outstanding = 0.0
    for b in open_bills:
        balance = _num(b.get("patient_balance"), _total_from_bill(b) - _num(b.get("discount")) - _num(b.get("hmo_covered")))
        total_outstanding += max(balance - paid_by_bill.get(b["id"], 0.0), 0.0)

    hmo_pending_count = (
        db.table(TABLE_INSURANCE_CLAIMS).select("id", count="exact")
        .in_("status", ["submitted", "pre_authorised"]).execute().count
    )
    return {
        "pending_count": pending_count,
        "partial_count": partial_count,
        "disputed_count": disputed_count,
        "total_outstanding": round(total_outstanding, 2),
        "hmo_pending_count": hmo_pending_count,
    }


@router.post("/bills/{bill_id}/write-off")
async def write_off_bill(bill_id: int, user=Depends(require_role("admin"))):
    """Administrative write-off for an uncollectable bill — distinct from
    `waive` (a deliberate no-charge decision). Same irreversible,
    finance-visible risk profile as waiving, so gated identically."""
    bill = _get_bill(bill_id)
    if bill["status"] in ("paid", "waived", "written_off"):
        raise HTTPException(status_code=409, detail=f"Bill already '{bill['status']}'")
    db.table(TABLE_BILLING).update({"status": "written_off"}).eq("id", bill_id).execute()
    _audit("bill_written_off", {}, user, "bill", bill_id)
    return {"ok": True, "bill_id": bill_id, "status": "written_off"}


@router.get("/unbilled-encounters")
async def unbilled_encounters(limit: int = Query(50, ge=1, le=200), user=Depends(verify_jwt)):
    """Encounters that reached billing_pending with no royan_billing row yet.
    royan_billing.encounter_id has an index but no UNIQUE constraint, so this
    is a two-query diff, mirroring pharmacy_dispensing.py's
    administration_queue (dispensed prescriptions with zero
    royan_medication_admin rows yet)."""
    encounters = (
        db.table(TABLE_ENCOUNTERS)
        .select("id,patient_id,queue_number,department,chief_complaint,status,created_at")
        .eq("status", "billing_pending")
        .is_("external_source", None)
        .order("created_at", desc=True)
        .limit(limit)
        .execute().data or []
    )
    if not encounters:
        return {"encounters": [], "count": 0}

    enc_ids = [e["id"] for e in encounters]
    billed_ids = {
        r["encounter_id"] for r in
        (db.table(TABLE_BILLING).select("encounter_id").in_("encounter_id", enc_ids).execute().data or [])
    }
    unbilled = [e for e in encounters if e["id"] not in billed_ids]

    if unbilled:
        patient_ids = list({e["patient_id"] for e in unbilled if e.get("patient_id") is not None})
        patients = db.table(TABLE_PATIENTS).select("id,first_name,last_name,mrn").in_("id", patient_ids).execute().data or []
        by_id = {p["id"]: p for p in patients}
        for e in unbilled:
            p = by_id.get(e.get("patient_id"))
            if p:
                e["patient_name"] = f"{p.get('first_name','')} {p.get('last_name','')}".strip()
                e["patient_mrn"] = p.get("mrn")

    return {"encounters": unbilled, "count": len(unbilled)}


def _encounter_admitted(enc: dict) -> bool:
    """A patient counts as in-house/admitted if their encounter_type isn't
    plain outpatient, OR they've actually been assigned a bed — the OR guards
    both an emergency/maternity encounter that never got a bed, and an
    outpatient encounter that unexpectedly did."""
    return (enc.get("encounter_type") or "outpatient") != "outpatient" or bool(enc.get("bed_id"))


def _match_lab_catalog(test_name: str, test_code: Optional[str]) -> Optional[dict]:
    """Best-effort match of a free-text lab order onto the priced catalog.
    royan_lab_orders.catalog_id exists but is never populated by the order-
    creation flow today, so this fuzzy match is the only path to a real price."""
    if test_code:
        exact = db.table(TABLE_LAB_CATALOG).select("*").eq("is_active", True).eq("code", test_code).limit(1).execute()
        if exact.data:
            return exact.data[0]
    if not test_name:
        return None
    term = test_name.strip()
    for column in ("name", "abbreviation"):
        match = (
            db.table(TABLE_LAB_CATALOG)
            .select("*")
            .eq("is_active", True)
            .ilike(column, term)
            .limit(1)
            .execute()
        )
        if match.data:
            return match.data[0]
    return None


@router.get("/encounters/{encounter_id}/suggested-items")
async def suggested_bill_items(encounter_id: int, user=Depends(verify_jwt)):
    """Best-effort itemized suggestion for /bills/from-encounter, built from
    what this specific encounter actually incurred — the user's own framing
    ('only different activities that patient underwent'). Consultation/
    Procedure/Misc are deliberately NOT suggested here: royan_service_catalog
    has no per-encounter record of what was actually charged for a visit, so
    guessing would be worse than leaving it for manual entry."""
    encounter = db.table(TABLE_ENCOUNTERS).select("*").eq("id", encounter_id).limit(1).execute()
    if not encounter.data:
        raise HTTPException(status_code=404, detail=f"Encounter {encounter_id} not found")
    enc = encounter.data[0]
    patient_id = enc.get("patient_id")

    patient = db.table(TABLE_PATIENTS).select("*").eq("id", patient_id).limit(1).execute()
    patient_row = patient.data[0] if patient.data else {}

    suggested_items: list[dict] = []

    # Lab — fuzzy-matched against the priced catalog; unmatched tests are
    # still surfaced (unit_price 0, matched=False) so staff can price them
    # manually rather than the line silently vanishing.
    lab_orders = (
        db.table(TABLE_LAB_ORDERS)
        .select("id,test_name,test_code,catalog_id,status")
        .eq("encounter_id", encounter_id)
        .is_("external_source", "null")
        .execute()
    )
    for order in (lab_orders.data or []):
        catalog_row = None
        if order.get("catalog_id"):
            found = db.table(TABLE_LAB_CATALOG).select("*").eq("id", order["catalog_id"]).limit(1).execute()
            catalog_row = found.data[0] if found.data else None
        if not catalog_row:
            catalog_row = _match_lab_catalog(order.get("test_name") or "", order.get("test_code"))
        # NOTE: catalog_row.id/code are royan_lab_catalog's own IDs/codes — a
        # completely different ID space from royan_service_catalog (which is
        # what /bills/from-encounter's coverage lookup resolves service_id/
        # service_code against). Passing the lab catalog's id back as
        # "service_id" would silently collide with an unrelated
        # royan_service_catalog row. lab_catalog_id is informational only
        # (for the frontend to display what matched); service_id/service_code
        # stay null so the bill item is priced from unit_price directly.
        suggested_items.append({
            "source": "lab_order",
            "source_id": order["id"],
            "service_id": None,
            "service_code": None,
            "lab_catalog_id": (catalog_row or {}).get("id"),
            "description": order.get("test_name") or "Lab Test",
            "category": "lab",
            "quantity": 1,
            "unit_price": _num((catalog_row or {}).get("base_price"), 0.0),
            "matched": catalog_row is not None,
        })

    # Pharmacy — royan_dispensing has no encounter_id directly; join via the
    # prescription it was dispensed against. Cost is what the pharmacist
    # actually recorded, not a catalog lookup, so this is always reliable.
    prescriptions = (
        db.table(TABLE_PRESCRIPTIONS).select("id").eq("encounter_id", encounter_id).execute()
    )
    prescription_ids = [p["id"] for p in (prescriptions.data or [])]
    dispensed_rows: list[dict] = []
    if prescription_ids:
        dispensed = (
            db.table(TABLE_DISPENSING)
            .select("id,drug_name,quantity_dispensed,unit_cost,total_cost,prescription_id")
            .in_("prescription_id", prescription_ids)
            .execute()
        )
        dispensed_rows = dispensed.data or []
    for row in dispensed_rows:
        qty = _num(row.get("quantity_dispensed"), 1.0) or 1.0
        suggested_items.append({
            "source": "dispensing",
            "source_id": row["id"],
            "service_id": None,
            "service_code": None,
            "description": row.get("drug_name") or "Dispensed Medication",
            "category": "pharmacy",
            "quantity": qty,
            "unit_price": _num(row.get("unit_cost"), _num(row.get("total_cost")) / qty if qty else 0.0),
            "matched": True,
        })

    # Ward/Nursing — the running inpatient bill, only relevant when admitted.
    admitted = _encounter_admitted(enc)
    inpatient_lines: list[dict] = []
    inpatient_running_total = 0.0
    if admitted:
        lines = (
            db.table(TABLE_INPATIENT_BILL_LINES)
            .select("*")
            .eq("encounter_id", encounter_id)
            .order("charged_at")
            .execute()
        )
        inpatient_lines = lines.data or []
        inpatient_running_total = round(sum(_num(l.get("total")) for l in inpatient_lines), 2)

    return {
        "encounter": {**enc, "admitted": admitted},
        "patient": {
            "id": patient_row.get("id"),
            "mrn": patient_row.get("mrn"),
            "first_name": patient_row.get("first_name"),
            "last_name": patient_row.get("last_name"),
            "patient_type": patient_row.get("patient_type"),
            "hmo_provider": patient_row.get("hmo_provider"),
        },
        "suggested_items": suggested_items,
        "inpatient_lines": inpatient_lines,
        "inpatient_running_total": inpatient_running_total,
    }


@router.get("/bills/{bill_id}/invoice")
async def get_bill_invoice(bill_id: int, user=Depends(verify_jwt)):
    """Single-call aggregate powering the printable invoice view — everything
    the print layout needs in one request rather than the frontend stitching
    together bill + patient + encounter + payments itself."""
    bill = _bill_with_amounts(_get_bill(bill_id))
    items = db.table(TABLE_BILL_ITEMS).select("*").eq("billing_id", bill_id).order("id").execute()
    payments = db.table(TABLE_PAYMENTS).select("*").eq("billing_id", bill_id).order("received_at").execute()

    patient = db.table(TABLE_PATIENTS).select("*").eq("id", bill.get("patient_id")).limit(1).execute()
    patient_row = patient.data[0] if patient.data else {}

    encounter_row: dict = {}
    admitted = False
    inpatient_lines: list[dict] = []
    if bill.get("encounter_id"):
        encounter = db.table(TABLE_ENCOUNTERS).select("*").eq("id", bill["encounter_id"]).limit(1).execute()
        if encounter.data:
            encounter_row = encounter.data[0]
            admitted = _encounter_admitted(encounter_row)
            if admitted:
                lines = (
                    db.table(TABLE_INPATIENT_BILL_LINES)
                    .select("*")
                    .eq("encounter_id", bill["encounter_id"])
                    .order("charged_at")
                    .execute()
                )
                inpatient_lines = lines.data or []

    return {
        "bill": bill,
        "items": items.data or [],
        "payments": payments.data or [],
        "patient": patient_row,
        "encounter": {**encounter_row, "admitted": admitted} if encounter_row else None,
        "inpatient_lines": inpatient_lines,
        "amount_in_words": naira_in_words(bill.get("patient_due") or 0.0),
    }


# ─── Inpatient Running Bill ───────────────────────────────────────────────────

class InpatientLineCreate(BaseModel):
    service_name: str = Field(..., min_length=1)
    quantity: float = Field(1.0, gt=0)
    unit_price: float = Field(..., ge=0)
    notes: Optional[str] = None

    model_config = {"extra": "ignore"}


@router.post("/inpatient-bill/{encounter_id}/lines", status_code=201)
async def add_inpatient_line(encounter_id: int, payload: InpatientLineCreate, user=Depends(verify_jwt)):
    """Append a charge line to an encounter's running inpatient bill."""
    enc = db.table(TABLE_ENCOUNTERS).select("id,patient_id").eq("id", encounter_id).execute()
    if not enc.data:
        raise HTTPException(status_code=404, detail=f"Encounter {encounter_id} not found")
    patient_id = enc.data[0]["patient_id"]

    from src.constants import TABLE_INPATIENT_BILL_LINES
    from datetime import datetime, timezone
    data = {
        "encounter_id": encounter_id,
        "patient_id": patient_id,
        "service_name": payload.service_name,
        "quantity": payload.quantity,
        "unit_price": payload.unit_price,
        "total": round(payload.quantity * payload.unit_price, 2),
        "charged_by": user.get("sub") or user.get("email"),
        "charged_at": datetime.now(timezone.utc).isoformat(),
        "notes": payload.notes,
    }
    try:
        result = db.table(TABLE_INPATIENT_BILL_LINES).insert(data).execute()
    except Exception as exc:
        logger.error("Inpatient bill line insert failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to add charge line")

    line = (result.data or [data])[0]
    audit_event(
        "inpatient_bill_line_added",
        {"service_name": payload.service_name, "total": data["total"]},
        actor_id=user.get("sub"),
        subject_type="encounter",
        subject_id=str(encounter_id),
    )
    return {"ok": True, "line": line}


@router.get("/inpatient-bill/{encounter_id}")
async def get_inpatient_bill(encounter_id: int, user=Depends(verify_jwt)):
    """Get all charge lines and running total for an inpatient encounter."""
    enc = db.table(TABLE_ENCOUNTERS).select("id,patient_id,status").eq("id", encounter_id).execute()
    if not enc.data:
        raise HTTPException(status_code=404, detail=f"Encounter {encounter_id} not found")

    from src.constants import TABLE_INPATIENT_BILL_LINES
    result = (
        db.table(TABLE_INPATIENT_BILL_LINES)
        .select("*")
        .eq("encounter_id", encounter_id)
        .order("charged_at")
        .execute()
    )
    lines = result.data or []
    running_total = sum(float(l.get("total") or 0) for l in lines)
    return {
        "encounter_id": encounter_id,
        "lines": lines,
        "line_count": len(lines),
        "running_total": round(running_total, 2),
    }
