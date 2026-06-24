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
    TABLE_ENCOUNTERS,
    TABLE_INSURANCE_CLAIMS,
    TABLE_PATIENTS,
    TABLE_PAYMENTS,
)
from src.db import audit_event, db
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
        item_rows.append({
            "billing_id": bill_id,
            "encounter_id": payload.encounter_id,
            "patient_id": patient_id,
            "service_id": service.get("id"),
            "service_code": service.get("service_code") or item.service_code,
            "description": item.description,
            "category": service.get("category") or item.category,
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
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    user=Depends(verify_jwt),
):
    query = db.table(TABLE_BILLING).select("*").order("billed_at", desc=True).limit(limit)
    if patient_id:
        query = query.eq("patient_id", patient_id)
    if status:
        if status not in BILL_STATUS_ALLOWED:
            raise HTTPException(status_code=422, detail=f"Unknown status '{status}'")
        query = query.eq("status", status)
    result = query.execute()
    bills = [_bill_with_amounts(row) for row in (result.data or [])]
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
