"""Hospital billing, payments, HMO claims, and coverage-aware bill creation."""
from __future__ import annotations

import logging
from typing import Optional

import psycopg2.extras

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
    TABLE_BEDS,
    TABLE_LAB_CATALOG,
    TABLE_RADIOLOGY_ORDERS,
    TABLE_RADIOLOGY_CATALOG,
    TABLE_SERVICE_CATALOG,
    TABLE_WARDS,
    TABLE_LAB_ORDERS,
    TABLE_PATIENTS,
    TABLE_PAYMENTS,
    TABLE_PRESCRIPTIONS,
)
import datetime as dt

from src.cache import invalidate_cache_tags
from src.db import audit_event, db
from src.services.amount_in_words import naira_in_words
from src.services.event_service import emit_clinical_event
from src.middleware import require_role, verify_jwt
from src.services.coverage import CoverageInput, billing_breakdown_from_quotes, calculate_coverage
# Roy Books: every bill, payment and correction posts itself to the books after
# it is saved - in its own transaction, never blocking the cashier (fin.integrations).
from src.fin.integrations import after_commit as post_to_books

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
    # the order this line charges (lab_order / prescription / radiology_order / consultation ...), so it is billed once
    source: Optional[str] = None
    source_id: Optional[str] = None


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


def _generate_bill_number(entity: str = "ROYAN") -> str:
    """Royan bills RHB-YYYY-nnnnnn; Scancare (its own company) SCB-YYYY-nnnnnn, so neither sequence has gaps."""
    fn = "generate_scancare_bill_number" if entity == "SCANCARE" else "generate_bill_number"
    result = db.rpc(fn, {}).execute()
    if result.data:
        row = result.data[0]
        return row.get(fn) if isinstance(row, dict) else str(row)
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
    payments = db.table(TABLE_PAYMENTS).select("amount,status").eq("billing_id", bill["id"]).execute().data or []
    amount_paid = round(sum(_num(row.get("amount")) for row in payments if (row.get("status") or "posted") != "void"), 2)
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
def create_bill(payload: BillCreate, user=Depends(verify_jwt)):
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
    if bill.get("id"):
        post_to_books("BILL", bill["id"], user.get("sub"))
    emit_clinical_event(
        event_type="BILL_GENERATED",
        encounter_id=payload.encounter_id,
        patient_id=payload.patient_id,
        entity_type="bill", entity_id=bill.get("id"),
        performed_by=user.get("sub"),
        event_data={"bill_number": bill_number},
    )
    return {"ok": True, "bill": _bill_with_amounts(bill)}


def create_coverage_bill(encounter_id: int, patient_id: int, items: list[dict], user: dict, *, discount: float = 0.0,
                         notes: Optional[str] = None, entity: str = "ROYAN", stage: Optional[str] = None) -> dict:
    """Create one hospital bill from priced items, each run through the patient's HMO cover, and post it to the
    books of its company (Royan or Scancare). Every bill in the system is created here: at the front desk
    (registration + consultation), when the doctor sends the patient to the cashier (what was ordered), and by the
    cashier. An item's `source` / `source_id` names the order it charges, so nothing is billed twice."""
    quotes = [
        calculate_coverage(
            CoverageInput(
                patient_id=int(patient_id),
                encounter_id=encounter_id,
                service_id=item.get("service_id"),
                service_code=item.get("service_code"),
                service_name=item["description"],
                category=item.get("category") or "misc",
                quantity=float(item.get("quantity") or 1),
                unit_price=float(item.get("unit_price") or 0),
            )
        )
        for item in items
    ]
    breakdown = billing_breakdown_from_quotes(quotes)
    bill_number = _generate_bill_number(entity)
    bill_data = {
        "encounter_id": encounter_id,
        "patient_id": patient_id,
        "bill_number": bill_number,
        **breakdown,
        "discount": discount,
        "status": "pending",
        "billed_by": user.get("sub") or "system",
        "notes": notes,
        "entity": entity,
        "stage": stage,
    }
    try:
        result = db.table(TABLE_BILLING).insert(bill_data).execute()
    except Exception as exc:
        logger.error("Coverage bill creation failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to create coverage-aware bill")
    bill = (result.data or [bill_data])[0]
    bill_id = bill.get("id")

    item_rows = []
    for item, quote in zip(items, quotes):
        service = quote.get("service") or {}
        category = service.get("category") or item.get("category") or "misc"
        payer_type = item.get("payer_type") or ("hmo" if (quote.get("insurance") or {}).get("active") else "private")
        item_rows.append({
            "billing_id": bill_id,
            "encounter_id": encounter_id,
            "patient_id": patient_id,
            "service_id": service.get("id"),
            "service_code": service.get("service_code") or item.get("service_code"),
            "description": item["description"],
            "category": category,
            "department": _department_for_category(category),
            "payer_type": payer_type,
            "quantity": item.get("quantity") or 1,
            "unit_price": item.get("unit_price") or 0,
            "covered_amount": quote.get("covered_amount") or 0,
            "patient_amount": quote.get("patient_amount") or 0,
            "requires_approval": bool(quote.get("requires_approval")),
            "approval_required_reason": quote.get("approval_required_reason"),
            "coverage_rule_id": quote.get("coverage_rule_id"),
            "coverage_snapshot": quote,
            "source": item.get("source"),
            "source_id": str(item["source_id"]) if item.get("source_id") is not None else None,
        })
    if item_rows:
        db.table(TABLE_BILL_ITEMS).insert(item_rows).execute()

    if any(q.get("requires_approval") for q in quotes):
        db.table(TABLE_BILLING).update({"status": "disputed"}).eq("id", bill_id).execute()
        bill["status"] = "disputed"

    _audit("coverage_bill_created", {"bill_number": bill_number, "items": len(item_rows), "hmo_covered": breakdown["hmo_covered"],
                                     "entity": entity, "stage": stage}, user, "bill", bill_id)
    if bill_id:
        post_to_books("BILL", bill_id, user.get("sub"))
    return {"ok": True, "bill": _bill_with_amounts(bill), "items": item_rows, "coverage_quotes": quotes}


@router.post("/bills/from-encounter", status_code=201)
def create_bill_from_encounter(payload: BillFromEncounterRequest, user=Depends(verify_jwt)):
    encounter = db.table(TABLE_ENCOUNTERS).select("*").eq("id", payload.encounter_id).limit(1).execute()
    if not encounter.data:
        raise HTTPException(status_code=404, detail=f"Encounter {payload.encounter_id} not found")
    enc = encounter.data[0]
    patient_id = payload.patient_id or enc.get("patient_id")
    if not patient_id:
        raise HTTPException(status_code=422, detail="patient_id is required")
    if not payload.items:
        raise HTTPException(status_code=422, detail="At least one bill item is required")
    return create_coverage_bill(payload.encounter_id, int(patient_id), [i.model_dump() for i in payload.items], user,
                                discount=payload.discount, notes=payload.notes)


@router.get("/bills")
def list_bills(
    patient_id: Optional[int] = Query(None),
    encounter_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    entity: Optional[str] = Query(None, description="ROYAN or SCANCARE - each company's own bills"),
    payer: Optional[str] = Query(None, description="hmo or private - the HMO desk's billing queue reads payer=hmo"),
    limit: int = Query(50, ge=1, le=200),
    user=Depends(verify_jwt),
):
    # Live worklist = native bills only (external_source IS NULL). Hope's
    # historical import (259k+ rows, confirmed) must never crowd out or
    # masquerade as an actionable bill — same filter queue_clinical.py's
    # list_encounters already applies for the identical reason.
    query = db.table(TABLE_BILLING).select("*").is_("external_source", None).order("billed_at", desc=True).limit(min(limit * 4, 400) if payer else limit)
    if patient_id:
        query = query.eq("patient_id", patient_id)
    if encounter_id:
        query = query.eq("encounter_id", encounter_id)
    if entity:
        query = query.eq("entity", entity.upper())
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
    _attach_payer(bills)
    if payer in ("hmo", "private"):
        bills = [b for b in bills if b.get("payer_type") == payer]

    return {"bills": bills, "count": len(bills)}


def _attach_payer(bills: list[dict]) -> None:
    """Who pays each bill: the visit's payer (HMO or private) and the patient's HMO and card number, so a bill
    shows at a glance that it is an HMO patient's - the HMO desk and the cashier both need that."""
    if not bills:
        return
    from src.fin.db import q as _q, tx as _tx
    enc_ids = list({b["encounter_id"] for b in bills if b.get("encounter_id")})
    pat_ids = list({b["patient_id"] for b in bills if b.get("patient_id")})
    with _tx() as conn:
        encs = {r["id"]: r for r in _q(conn, "SELECT id, payer_type, membership_id FROM royan_encounters WHERE id = ANY(%s)",
                                         (enc_ids,))} if enc_ids else {}
        ins = {r["patient_id"]: r for r in _q(conn, """
            SELECT DISTINCT ON (p.id) p.id AS patient_id, COALESCE(h.name, NULLIF(trim(p.hmo_provider), '')) AS hmo_name,
                   COALESCE(i.membership_id, p.hmo_id::text) AS membership_id, (i.id IS NOT NULL) AS has_policy
            FROM royan_patients p
            LEFT JOIN royan_patient_insurance i ON i.patient_id = p.id AND i.status = 'active'
            LEFT JOIN royan_hmos h ON h.id = i.hmo_id
            WHERE p.id = ANY(%s) ORDER BY p.id, i.is_primary DESC NULLS LAST, i.id""", (pat_ids,))} if pat_ids else {}
    for b in bills:
        e = encs.get(b.get("encounter_id")) or {}
        i = ins.get(b.get("patient_id")) or {}
        payer = e.get("payer_type") or ("hmo" if (_num(b.get("hmo_covered"), 0.0) > 0 or i.get("has_policy")) else "private")
        b["payer_type"] = payer
        b["hmo_name"] = i.get("hmo_name") if payer == "hmo" else None
        b["membership_id"] = (e.get("membership_id") or i.get("membership_id")) if payer == "hmo" else None


def _derive_room_charges(encounter_id: int, patient_id: int) -> list:
    """Nights in a bed, priced from the bed or its ward.

    DERIVED, not accrued by a nightly job. A cron that misses a night
    under-bills silently and one that double-runs over-bills; computing from
    admitted_at cannot drift from the real length of stay.

    An unpriced ward yields a line at zero with needs_rate set, so the stay is
    visible on the bill and obviously incomplete. Omitting it would hide the
    admission entirely, which is how a patient gets discharged without being
    charged for their bed.
    """
    try:
        beds = (
            db.table(TABLE_BEDS)
            .select("id,ward_id,room_id,bed_number,daily_rate,admitted_at,current_patient_id,current_encounter_id")
            .eq("current_patient_id", patient_id)
            .execute().data or []
        )
    except Exception as exc:
        logger.warning("Room charge lookup failed for patient %s: %s", patient_id, exc)
        return []

    # Prefer the bed tied to THIS encounter; fall back to any bed the patient
    # currently occupies, since older admissions predate encounter linkage.
    bed = next((b for b in beds if str(b.get("current_encounter_id")) == str(encounter_id)), None)
    if not bed and beds:
        bed = beds[0]
    if not bed or not bed.get("admitted_at"):
        return []

    ward = {}
    if bed.get("ward_id"):
        try:
            found = db.table(TABLE_WARDS).select("id,name,daily_rate").eq("id", bed["ward_id"]).limit(1).execute()
            ward = found.data[0] if found.data else {}
        except Exception:
            ward = {}

    room = {}
    if bed.get("room_id"):
        try:
            found = db.table("royan_rooms").select("id,name,daily_rate").eq("id", bed["room_id"]).limit(1).execute()
            room = found.data[0] if found.data else {}
        except Exception:
            room = {}

    # Most specific wins: a bed rate overrides its room, which overrides its
    # ward. Rooms carry the real Royan prices (Room102 = 40,000), so this is
    # normally where the number comes from.
    rate = (
        _num(bed.get("daily_rate"), 0.0)
        or _num(room.get("daily_rate"), 0.0)
        or _num(ward.get("daily_rate"), 0.0)
    )

    try:
        admitted = dt.datetime.fromisoformat(str(bed["admitted_at"]).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return []
    if admitted.tzinfo is None:
        admitted = admitted.replace(tzinfo=dt.timezone.utc)

    elapsed = dt.datetime.now(dt.timezone.utc) - admitted
    # A patient admitted at any point in a day occupies the bed for that night,
    # so the first night counts immediately rather than after 24 hours.
    nights = max(1, int(elapsed.total_seconds() // 86400) + (1 if elapsed.total_seconds() % 86400 else 0))

    # "First Floor · Room104 bed 2" rather than "First Floor bed 2".
    label = " · ".join(x for x in [ward.get("name"), room.get("name")] if x)
    label = "%s bed %s" % (label or "Ward", bed.get("bed_number") or "")
    return [{
        "id": None,
        "source": "room_charge",
        "source_id": bed["id"],
        "description": "%s — %d night%s" % (label.strip(), nights, "" if nights == 1 else "s"),
        "category": "ward",
        "quantity": nights,
        "unit_price": rate,
        "total": round(rate * nights, 2),
        "charged_at": bed["admitted_at"],
        "derived": True,
        "needs_rate": rate <= 0,
        "ward_name": ward.get("name"),
        "room_name": room.get("name"),
    }]


@router.get("/bills/pending-discounts")
def list_pending_discounts(user=Depends(verify_jwt)):
    """The admin approval queue."""
    try:
        rows = (
            db.table(TABLE_BILLING)
            .select("id,bill_number,patient_id,encounter_id,subtotal,discount,"
                    "discount_reason,discount_requested_by,discount_requested_at,status")
            .eq("discount_status", "pending")
            .order("discount_requested_at")
            .limit(100).execute().data or []
        )
    except Exception:
        return {"bills": [], "count": 0}

    pids = list({r["patient_id"] for r in rows if r.get("patient_id")})
    pmap = {}
    if pids:
        try:
            pts = db.table(TABLE_PATIENTS).select("id,mrn,first_name,last_name").in_("id", pids).execute()
            pmap = {
                x["id"]: {
                    "name": ("%s %s" % (x.get("first_name", ""), x.get("last_name", ""))).strip(),
                    "mrn": x.get("mrn"),
                }
                for x in pts.data or []
            }
        except Exception:
            pmap = {}
    for r in rows:
        info = pmap.get(r.get("patient_id")) or {}
        r["patient_name"] = info.get("name")
        r["patient_mrn"] = info.get("mrn")
        sub = _num(r.get("subtotal"), 0.0)
        disc = _num(r.get("discount"), 0.0)
        r["discount_pct"] = round(100.0 * disc / sub, 1) if sub > 0 else None

    return {"bills": rows, "count": len(rows)}


@router.get("/bills/{bill_id}")
def get_bill(bill_id: int, user=Depends(verify_jwt)):
    bill = _bill_with_amounts(_get_bill(bill_id))
    payments = db.table(TABLE_PAYMENTS).select("*").eq("billing_id", bill_id).order("received_at", desc=True).execute()
    claims = db.table(TABLE_INSURANCE_CLAIMS).select("*").eq("billing_id", bill_id).execute()
    items = db.table(TABLE_BILL_ITEMS).select("*").eq("billing_id", bill_id).execute()
    return {"bill": bill, "items": items.data or [], "payments": payments.data or [], "claims": claims.data or []}


@router.post("/bills/{bill_id}/payment")
def record_payment(bill_id: int, payload: PaymentCreate, user=Depends(verify_jwt)):
    bill = _get_bill(bill_id)
    if bill["status"] in ("paid", "waived", "written_off", "void"):
        raise HTTPException(status_code=409, detail=f"Bill is already '{bill['status']}'")
    if payload.payment_method not in PAYMENT_METHODS_ALLOWED:
        raise HTTPException(status_code=422, detail=f"payment_method must be one of {sorted(PAYMENT_METHODS_ALLOWED)}")
    # A discount still under review changes what the patient owes, so taking
    # money now means taking the wrong amount. Enforced here rather than by
    # hiding the button, since the bill is reachable from several screens.
    if bill.get("discount_status") == "pending":
        raise HTTPException(
            status_code=409,
            detail="This bill has a discount waiting for admin approval. It cannot be settled until that is decided.",
        )

    data = {
        "billing_id": bill_id,
        "patient_id": bill["patient_id"],
        "amount": payload.amount,
        "payment_method": payload.payment_method,
        "reference": payload.reference or payload.reference_number,
        "notes": payload.notes,
        "received_by": user.get("sub") or "system",
        # The hospital's own sequential record of money received. Distinct from
        # `reference`, which is the PAYER's number (transfer ref, POS slip) and
        # is neither unique nor ours to cite in an audit.
        "receipt_number": _generate_receipt_number(bill.get("entity") or "ROYAN"),
    }
    try:
        result = db.table(TABLE_PAYMENTS).insert(data).execute()
    except Exception as exc:
        logger.error("Payment insert failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to record payment")

    new_status = _refresh_bill_status(bill_id)

    _audit("payment_recorded", {"amount": payload.amount, "method": payload.payment_method, "bill_status": new_status}, user, "bill", bill_id)
    payment_row = (result.data or [{}])[0]
    if payment_row.get("id"):
        post_to_books("PAYMENT", payment_row["id"], user.get("sub"))
    emit_clinical_event(
        event_type="PAYMENT_RECEIVED",
        encounter_id=bill.get("encounter_id"),
        patient_id=bill.get("patient_id"),
        entity_type="bill", entity_id=bill_id,
        performed_by=user.get("sub"),
        event_data={"amount": payload.amount, "method": payload.payment_method, "bill_status": new_status},
    )
    return {"ok": True, "payment": (result.data or [data])[0], "bill_status": new_status}


def _refresh_bill_status(bill_id: int) -> str:
    """A bill's status from the receipts that stand (voided ones do not count): paid, partial or pending."""
    bill = _get_bill(bill_id)
    if bill["status"] in ("waived", "written_off", "void"):
        return bill["status"]
    rows = db.table(TABLE_PAYMENTS).select("amount,status").eq("billing_id", bill_id).execute().data or []
    total_paid = sum(_num(p.get("amount")) for p in rows if (p.get("status") or "posted") != "void")
    balance = _num(bill.get("patient_balance"))
    new_status = "paid" if total_paid >= balance and total_paid > 0 else "partial" if total_paid > 0 else (
        "disputed" if bill["status"] == "disputed" else "pending")
    update: dict = {"status": new_status, "paid_at": dt.datetime.now(dt.timezone.utc).isoformat() if new_status == "paid" else None}
    db.table(TABLE_BILLING).update(update).eq("id", bill_id).execute()
    return new_status


class VoidRequest(BaseModel):
    reason: str = Field(..., min_length=3)


@router.post("/payments/{payment_id}/void")
def void_payment(payment_id: int, payload: VoidRequest, user=Depends(require_role("admin", "finance", "management", "cashier"))):
    """Void a receipt keyed wrongly (wrong amount, method or patient). The bill goes back to what the remaining
    receipts cover, Roy Books voids its receipt, and the correct receipt can then be recorded."""
    rows = db.table(TABLE_PAYMENTS).select("*").eq("id", payment_id).limit(1).execute().data
    if not rows:
        raise HTTPException(status_code=404, detail="Payment not found")
    p = rows[0]
    if (p.get("status") or "posted") == "void":
        raise HTTPException(status_code=409, detail="This receipt is already void")
    if p.get("external_source"):
        raise HTTPException(status_code=409, detail="A receipt imported from Hope is history and cannot be voided here")
    if (p.get("payment_method") or "") in ("waiver", "hmo"):
        raise HTTPException(status_code=409, detail="A waiver or HMO transfer is corrected with the correction pen on the bill")
    db.table(TABLE_PAYMENTS).update({"status": "void", "voided_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                                     "voided_by": user.get("email") or user.get("sub"), "void_reason": payload.reason}).eq("id", payment_id).execute()
    status = _refresh_bill_status(int(p["billing_id"])) if p.get("billing_id") else None
    _audit("payment_voided", {"receipt": p.get("receipt_number"), "amount": p.get("amount"), "reason": payload.reason}, user,
           "bill", p.get("billing_id"))
    books = post_to_books("PAYMENT_VOID", payment_id, user.get("sub"))
    return {"ok": True, "payment_id": payment_id, "bill_status": status, "books": books}


@router.post("/bills/{bill_id}/void")
def void_bill(bill_id: int, payload: VoidRequest, user=Depends(require_role("admin", "finance", "management", "cashier"))):
    """Void a bill raised wrongly (nothing paid on it). Roy Books voids its invoice(s), and the orders it charged can
    be billed again (Send to cashier) - which is how a bill is corrected: void and re-raise."""
    bill = _get_bill(bill_id)
    if bill["status"] == "void":
        raise HTTPException(status_code=409, detail="This bill is already void")
    paid = [p for p in (db.table(TABLE_PAYMENTS).select("id,status").eq("billing_id", bill_id).execute().data or [])
            if (p.get("status") or "posted") != "void"]
    if paid:
        raise HTTPException(status_code=409, detail="Receipts are recorded on this bill - void them first, then void the bill")
    db.table(TABLE_BILLING).update({"status": "void", "voided_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                                    "voided_by": user.get("email") or user.get("sub"), "void_reason": payload.reason}).eq("id", bill_id).execute()
    # free the orders this bill charged so they can be billed again
    for it in db.table(TABLE_BILL_ITEMS).select("id,source,source_id").eq("billing_id", bill_id).execute().data or []:
        if it.get("source") and it.get("source_id") and ":void:" not in str(it["source_id"]):
            db.table(TABLE_BILL_ITEMS).update({"source_id": f"{it['source_id']}:void:{bill_id}"}).eq("id", it["id"]).execute()
    _audit("bill_voided", {"bill_number": bill.get("bill_number"), "reason": payload.reason}, user, "bill", bill_id)
    books = post_to_books("BILL_VOID", bill_id, user.get("sub"))
    return {"ok": True, "bill_id": bill_id, "books": books}


@router.post("/bills/{bill_id}/waive")
def waive_bill(bill_id: int, user=Depends(require_role("admin"))):
    bill = _get_bill(bill_id)
    if bill["status"] in ("paid", "waived"):
        raise HTTPException(status_code=409, detail=f"Bill already '{bill['status']}'")
    db.table(TABLE_BILLING).update({"status": "waived"}).eq("id", bill_id).execute()
    _audit("bill_waived", {}, user, "bill", bill_id)
    post_to_books("BILL_WAIVER", bill_id, user.get("sub"))
    return {"ok": True, "bill_id": bill_id, "status": "waived"}


@router.post("/claims", status_code=201)
def submit_claim(payload: ClaimCreate, user=Depends(verify_jwt)):
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


@router.get("/revenue-split")
def revenue_split(
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    user=Depends(verify_jwt),
):
    """What each service line earned, and how much came from payers.

    "we should also be able to separate the HMO services so that we know what
    services went to HMO and at what cost, what services went to private and at
    what cost."

    WHY NOT royan_billing
    ---------------------
    Its hmo_covered column is 0 on all 259,072 rows and the per-category columns
    are empty except on the five bills raised natively -- the migration never
    filled them. royan_billing_transactions carries the real money, and its
    payment_category holds Hope's service_categories.id (migration 214).

    HOW "HMO" IS DECIDED, AND THE CAVEAT
    ------------------------------------
    By whether the PATIENT holds active cover, not by mode_of_payment. The
    obvious reading of mode_of_payment='Credit' as "billed to a payer" is wrong:
    258,611 of those are pharmacy dispensing lines worth 0, settled on the parent
    bill instead.

    The caveat this leaves, and it is reported in the response rather than
    buried: cover is judged as it stands TODAY. A patient who joined an HMO last
    year has their older self-funded visits counted as HMO. The split is sound
    for recent periods and progressively less so the further back it reaches.
    """
    conn = db.pool.getconn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            where, params = ["t.amount > 0"], []
            if date_from:
                where.append("t.transaction_date >= %s"); params.append(date_from)
            if date_to:
                where.append("t.transaction_date <= %s"); params.append(date_to)

            cur.execute("""
                SELECT COALESCE(c.name, 'Uncategorised')      AS category,
                       COUNT(*) FILTER (WHERE i.patient_id IS NOT NULL)  AS hmo_count,
                       COALESCE(SUM(t.amount) FILTER (WHERE i.patient_id IS NOT NULL), 0) AS hmo_value,
                       COUNT(*) FILTER (WHERE i.patient_id IS NULL)      AS private_count,
                       COALESCE(SUM(t.amount) FILTER (WHERE i.patient_id IS NULL), 0)     AS private_value
                FROM public.royan_billing_transactions t
                JOIN public.royan_service_categories c
                  ON c.id::text = t.payment_category
                LEFT JOIN (
                    SELECT DISTINCT patient_id
                    FROM public.royan_patient_insurance WHERE status = 'active'
                ) i ON i.patient_id = t.patient_id
                WHERE """ + " AND ".join(where) + """
                GROUP BY c.name
                ORDER BY (COALESCE(SUM(t.amount) FILTER (WHERE i.patient_id IS NOT NULL), 0)
                        + COALESCE(SUM(t.amount) FILTER (WHERE i.patient_id IS NULL), 0)) DESC
            """, params)
            rows = [dict(r) for r in cur.fetchall()]
    except Exception as exc:
        logger.error("Revenue split failed: %s: %s", type(exc).__name__, exc)
        raise HTTPException(status_code=500, detail="Could not build the revenue split")
    finally:
        db.pool.putconn(conn)

    for r in rows:
        r["hmo_value"] = float(r["hmo_value"] or 0)
        r["private_value"] = float(r["private_value"] or 0)
        r["total_value"] = r["hmo_value"] + r["private_value"]
        r["total_count"] = (r["hmo_count"] or 0) + (r["private_count"] or 0)

    hmo_total = sum(r["hmo_value"] for r in rows)
    private_total = sum(r["private_value"] for r in rows)
    grand = hmo_total + private_total

    return {
        "categories": rows,
        "hmo_total": hmo_total,
        "private_total": private_total,
        "grand_total": grand,
        "hmo_share": round(100.0 * hmo_total / grand, 1) if grand else 0.0,
        "basis": ("Split by whether the patient holds active HMO cover today. "
                  "Visits made before a patient joined their HMO are counted as "
                  "HMO, so the split is most accurate for recent periods."),
    }


@router.get("/claims")
def list_claims(
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
def update_claim_status(claim_id: int, payload: ClaimStatusUpdate, user=Depends(verify_jwt)):
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
    books = post_to_books("CLAIM_PAYMENT", claim_id, user.get("sub")) if payload.status == "paid" else None
    return {"ok": True, "claim_id": claim_id, "status": payload.status, "books": books}


@router.get("/stats")
def billing_stats(user=Depends(verify_jwt)):
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
def write_off_bill(bill_id: int, user=Depends(require_role("admin"))):
    """Administrative write-off for an uncollectable bill — distinct from
    `waive` (a deliberate no-charge decision). Same irreversible,
    finance-visible risk profile as waiving, so gated identically."""
    bill = _get_bill(bill_id)
    if bill["status"] in ("paid", "waived", "written_off"):
        raise HTTPException(status_code=409, detail=f"Bill already '{bill['status']}'")
    db.table(TABLE_BILLING).update({"status": "written_off"}).eq("id", bill_id).execute()
    _audit("bill_written_off", {}, user, "bill", bill_id)
    post_to_books("BILL_WRITEOFF", bill_id, user.get("sub"))
    return {"ok": True, "bill_id": bill_id, "status": "written_off"}


@router.get("/unbilled-encounters")
def unbilled_encounters(limit: int = Query(50, ge=1, le=200), user=Depends(verify_jwt)):
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
def suggested_bill_items(encounter_id: int, user=Depends(verify_jwt)):
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

    # Radiology — was missing entirely, so every scan was typed in by hand.
    # The order carries the study name; migration 200 gave the catalog a
    # base_price (209 of 211), so this resolves as cleanly as lab does.
    radiology_orders = (
        db.table(TABLE_RADIOLOGY_ORDERS)
        .select("id,test_name,modality,status,radiology_catalog_id")
        .eq("encounter_id", encounter_id)
        .is_("external_source", "null")
        .execute()
    )
    for order in (radiology_orders.data or []):
        cat_row = None
        try:
            if order.get("radiology_catalog_id"):
                found = (
                    db.table(TABLE_RADIOLOGY_CATALOG).select("id,name,base_price")
                    .eq("id", order["radiology_catalog_id"]).limit(1).execute()
                )
                cat_row = found.data[0] if found.data else None
            if not cat_row and order.get("test_name"):
                found = (
                    db.table(TABLE_RADIOLOGY_CATALOG).select("id,name,base_price")
                    .ilike("name", order["test_name"]).limit(1).execute()
                )
                cat_row = found.data[0] if found.data else None
        except Exception:
            cat_row = None

        # Same ID-space caution as lab: royan_radiology_catalog ids are NOT
        # royan_service_catalog ids, so service_id stays null and the line is
        # priced from unit_price directly.
        suggested_items.append({
            "source": "radiology_order",
            "source_id": order["id"],
            "service_id": None,
            "service_code": None,
            "radiology_catalog_id": (cat_row or {}).get("id"),
            "description": order.get("test_name") or "Imaging Study",
            "category": "imaging",
            "quantity": 1,
            "unit_price": _num((cat_row or {}).get("base_price"), 0.0),
            "matched": cat_row is not None,
        })

    # Consultation — suggested only when a doctor actually saw the patient.
    # An encounter that never left the queue did not incur a consultation fee,
    # and billing one would be charging for a visit that did not happen.
    SEEN_STATUSES = ("consulting", "lab_ordered", "awaiting_results",
                     "pharmacy_dispensing", "billing_pending", "discharged")
    if enc.get("status") in SEEN_STATUSES:
        consult_row = None
        try:
            found = (
                db.table(TABLE_SERVICE_CATALOG)
                .select("id,name,base_price,category")
                .eq("category", "consultation")
                .ilike("name", "GENERAL CONSULTATION")
                .gt("base_price", 0)
                .limit(1).execute()
            )
            consult_row = found.data[0] if found.data else None
        except Exception:
            consult_row = None

        if consult_row:
            suggested_items.append({
                "source": "consultation",
                "source_id": encounter_id,
                # This one IS a royan_service_catalog row, so the id is safe to
                # pass through and coverage can price it per payer.
                "service_id": consult_row.get("id"),
                "service_code": None,
                "description": consult_row.get("name") or "Consultation",
                "category": "consultation",
                "quantity": 1,
                "unit_price": _num(consult_row.get("base_price"), 0.0),
                # Deliberately False. The catalog holds first-visit, follow-up
                # and result-review consultations at different prices and
                # nothing on the encounter says which this was, so a human
                # confirms the line rather than the system asserting it.
                "matched": False,
                "needs_review": "Confirm whether this was a first visit, follow-up or result review",
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
        # Stored ad-hoc charges plus the derived room charge, presented as one
        # list. `derived` distinguishes them for anyone who needs to know.
        inpatient_lines = (lines.data or []) + _derive_room_charges(encounter_id, patient_id)
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


SIGNATORY_KEYS = {"signatory_bill_manager": "Bill Manager", "signatory_med_supdt": "Med. Supdt.",
                  "signatory_authorised": "Authorised Signatory"}


def _people(ids: list) -> dict:
    """Staff credentials (name, designation, staff number) for user ids / emails / staff ids, for printed documents.
    Until signatures are on file, the person's name and role stand in for them."""
    ids = [str(i) for i in ids if i and str(i) not in ("system", "None")]
    if not ids:
        return {}
    from src.fin.db import q as _q, tx as _tx
    out: dict = {}
    with _tx() as conn:
        users = {str(r["id"]): r for r in _q(conn, """SELECT id, email, roles FROM royan_users
                                                     WHERE id::text = ANY(%s) OR email = ANY(%s)""", (ids, ids))}
        staff = _q(conn, """SELECT id, user_id, email, full_name, designation, role, staff_number FROM royan_staff
                            WHERE id::text = ANY(%s) OR user_id::text = ANY(%s) OR (email IS NOT NULL AND email = ANY(%s))""",
                   (ids, ids, ids + [u["email"] for u in users.values() if u.get("email")]))
    for i in ids:
        u = users.get(i) or next((x for x in users.values() if x.get("email") == i), None)
        st = next((x for x in staff if str(x["id"]) == i or str(x.get("user_id") or "") == (str(u["id"]) if u else i)
                   or (u and x.get("email") and x["email"] == u.get("email"))), None)
        if not st and not u:
            out[i] = {"name": i, "title": None, "staff_number": None}
            continue
        role = ((u or {}).get("roles") or [None])[0] if u else None
        out[i] = {"name": (st or {}).get("full_name") or (u or {}).get("email") or i,
                  "title": (st or {}).get("designation") or (st or {}).get("role") or (role or "").replace("_", " ").title() or None,
                  "staff_number": (st or {}).get("staff_number")}
    return out


def _signatories(bill: dict, payments: list, people: dict) -> dict:
    """Who signs Royan's invoice: the Bill Manager (set in billing settings, else whoever raised the bill), the
    Cashier (who took the latest payment), the Med. Supdt. and the Authorised Signatory (set in billing settings)."""
    from src.fin.db import q as _q, tx as _tx
    with _tx() as conn:
        cfg = {r["key"]: r["value"] for r in _q(conn, "SELECT key, value FROM royan_billing_settings WHERE key = ANY(%s)",
                                               (list(SIGNATORY_KEYS),))}
    def named(key):
        v = (cfg.get(key) or "").strip()
        if not v:
            return None
        name, _, title = v.partition(",")
        return {"name": name.strip(), "title": title.strip() or SIGNATORY_KEYS[key], "staff_number": None}
    live = [p for p in payments if (p.get("status") or "posted") != "void"]
    cashier = people.get(str(live[-1].get("received_by") or "")) if live else None
    billing = named("signatory_bill_manager") or people.get(str(bill.get("billed_by") or ""))
    # Until the Medical Superintendent and the authorised signatory are named in billing settings, whoever handled
    # the billing signs for them (decided Oct 2026).
    return {"bill_manager": billing, "cashier": cashier,
            "med_supdt": named("signatory_med_supdt") or billing,
            "authorised": named("signatory_authorised") or billing}


@router.get("/bills/{bill_id}/invoice")
def get_bill_invoice(bill_id: int, user=Depends(verify_jwt)):
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
                inpatient_lines = (lines.data or []) + _derive_room_charges(
                    bill["encounter_id"], bill.get("patient_id"),
                )

    people = _people([bill.get("billed_by")] + [p.get("received_by") for p in (payments.data or [])])
    return {
        "bill": bill,
        "items": items.data or [],
        "payments": payments.data or [],
        "patient": patient_row,
        "encounter": {**encounter_row, "admitted": admitted} if encounter_row else None,
        "inpatient_lines": inpatient_lines,
        "amount_in_words": naira_in_words(bill.get("patient_due") or 0.0),
        # Royan's printed invoice / receipt: who the patient saw, which company the bill belongs to (Royan or
        # Scancare), and each receipt's amount in words ("Received with thanks from ... the sum of ...").
        "company": bill.get("entity") or "ROYAN",
        "doctor": (encounter_row or {}).get("consulting_doctor"),
        "receipts": [{**p, "amount_in_words": naira_in_words(p.get("amount") or 0.0),
                      "received_by_person": people.get(str(p.get("received_by") or ""))} for p in (payments.data or [])],
        "signatories": _signatories(bill, payments.data or [], people),
    }


def visit_diagnoses(conn, encounter_id: int) -> list[dict]:
    """The visit's diagnoses: the coded diagnosis list, else the ICD-10 codes on the doctor's notes (the SOAP note
    keeps them there), described from the ICD-10 book - primary first."""
    from src.fin.db import q as _q
    rows = _q(conn, """SELECT icd_code, description, diagnosis_type FROM royan_clinical_diagnoses
                       WHERE encounter_id=%s ORDER BY diagnosed_at""", (encounter_id,))
    if rows:
        return rows
    codes: list[str] = []
    for n in _q(conn, """SELECT icd10_codes FROM royan_encounter_notes WHERE encounter_id=%s AND icd10_codes IS NOT NULL
                         ORDER BY created_at""", (encounter_id,)):
        for c in n["icd10_codes"] or []:
            if c and c not in codes:
                codes.append(c)
    if not codes:
        return []
    named = {r["code"]: r["description"] for r in _q(conn, """
        SELECT DISTINCT ON (code) code, description FROM (
            SELECT icd_code AS code, description, 0 AS pref FROM royan_diagnosis_catalog WHERE icd_code = ANY(%s)
            UNION ALL SELECT code, description, 1 FROM royan_icd10_codes WHERE code = ANY(%s)) x
        ORDER BY code, pref""", (codes, codes))}
    return [{"icd_code": c, "description": named.get(c) or c, "diagnosis_type": "primary" if i == 0 else "secondary"}
            for i, c in enumerate(codes)]


def _clinical_summary(enc: dict, note: dict) -> Optional[str]:
    """Complaint, then the doctor's assessment and plan, from the visit's latest note."""
    def text(v):
        if isinstance(v, dict):
            v = "; ".join(str(x) for x in v.values() if x)
        return str(v).strip() if v else ""
    parts = [enc.get("chief_complaint"), text(note.get("assessment")), text(note.get("plan"))]
    out = " | ".join(p for p in (text(x) for x in parts) if p)
    return out[:600] or enc.get("notes")


@router.get("/bills/{bill_id}/claims-form")
def get_claims_form(bill_id: int, user=Depends(verify_jwt)):
    """Royan's HMO claims form for the visit on this bill: HMO, card number, diagnoses, investigations, consultation,
    admission, and the drugs dispensed with dosage, duration and cost - with the patient's signature taken at the
    pharmacy tablet. Everything billed for the visit (same company) is gathered, not only this bill."""
    from src.fin.db import q as _q, q1 as _q1, tx as _tx
    bill = _get_bill(bill_id)
    company = bill.get("entity") or "ROYAN"
    with _tx() as conn:
        patient = _q1(conn, "SELECT * FROM royan_patients WHERE id=%s", (bill["patient_id"],)) or {}
        enc = _q1(conn, "SELECT * FROM royan_encounters WHERE id=%s", (bill["encounter_id"],)) if bill.get("encounter_id") else None
        ins = _q1(conn, """SELECT i.membership_id, h.name FROM royan_patient_insurance i LEFT JOIN royan_hmos h ON h.id=i.hmo_id
                           WHERE i.patient_id=%s AND i.status='active' ORDER BY i.is_primary DESC, i.id LIMIT 1""",
                  (bill["patient_id"],)) or {}
        hmo = None
        if bill.get("hmo_id"):
            hmo = _q1(conn, "SELECT name FROM royan_hmos WHERE id::text=%s::text", (bill["hmo_id"],))
        bill_ids = [bill_id]
        if enc:
            bill_ids = [r["id"] for r in _q(conn, """SELECT id FROM royan_billing WHERE encounter_id=%s AND status <> 'void'
                                                      AND COALESCE(entity,'ROYAN')=%s""", (enc["id"], company))] or [bill_id]
        all_items = _q(conn, """SELECT description, category, quantity, unit_price, gross_amount, covered_amount, patient_amount,
                                       source, source_id, hmo_decision, hmo_approval_code
                                FROM royan_bill_items WHERE billing_id = ANY(%s) ORDER BY id""", (bill_ids,))
        # services the HMO team marked not covered are the patient's, not the HMO's: they stay off the claim
        items = [i for i in all_items if i.get("hmo_decision") != "not_covered"]
        not_covered = [i for i in all_items if i.get("hmo_decision") == "not_covered"]
        diagnoses = visit_diagnoses(conn, enc["id"]) if enc else []
        note = _q1(conn, """SELECT subjective, assessment, plan FROM royan_encounter_notes WHERE encounter_id=%s
                            ORDER BY (signed_at IS NULL), created_at DESC LIMIT 1""", (enc["id"],)) if enc else None
        meds = _q(conn, """SELECT p.id, p.drug_name, p.dosage, p.frequency, p.duration, p.quantity,
                                  d.quantity_dispensed, d.total_cost, d.signature_url, d.dispensed_at
                           FROM royan_prescriptions p LEFT JOIN LATERAL (
                               SELECT * FROM royan_dispensing x WHERE x.prescription_id=p.id ORDER BY x.dispensed_at DESC LIMIT 1) d ON true
                           WHERE p.encounter_id=%s ORDER BY p.prescribed_at""", (enc["id"],)) if enc else []
        claim = _q1(conn, """SELECT * FROM royan_insurance_claims WHERE billing_id = ANY(%s) ORDER BY id DESC LIMIT 1""", (bill_ids,))
    priced = {str(i["source_id"]): float(i["gross_amount"] or 0) for i in items if i.get("source") == "prescription"}
    excluded_rx = {str(i["source_id"]) for i in not_covered if i.get("source") == "prescription"}
    medications = [{"name": m["drug_name"], "dosage": " ".join(x for x in (m.get("dosage"), m.get("frequency")) if x),
                    "duration": m.get("duration"), "quantity": m.get("quantity_dispensed") or m.get("quantity"),
                    "cost": priced.get(str(m["id"]), float(m.get("total_cost") or 0)), "dispensed": bool(m.get("dispensed_at"))}
                   for m in meds if str(m["id"]) not in excluded_rx]
    # the patient signs once for the visit (HMO desk or pharmacy pad); an older visit falls back to the drug-collection
    # signature. Embedded inline: the image route needs a token an <img> tag cannot send.
    from src.signatures import signature_data_url
    raw_signature = (enc or {}).get("claim_signature_url") or next((m["signature_url"] for m in meds if m.get("signature_url")), None)
    try:
        signature = signature_data_url(raw_signature)
    except OSError:
        signature = None

    def lines(*cats):
        return [{"description": i["description"], "cost": float(i["gross_amount"] or 0)} for i in items if (i.get("category") or "") in cats]

    primary = [d for d in diagnoses if (d.get("diagnosis_type") or "").lower() in ("primary", "principal", "final", "")]
    others = [d for d in diagnoses if d not in primary[:1]]
    total = round(sum(float(i["gross_amount"] or 0) for i in items), 2)
    born = patient.get("date_of_birth")
    age = None
    if born:
        today = dt.date.today()
        age = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
    return {
        "company": company,
        "bill_number": bill.get("bill_number"),
        "hmo_name": (hmo or {}).get("name") or (claim or {}).get("hmo_provider") or ins.get("name") or patient.get("hmo_provider"),
        "patient_name": " ".join(x for x in (patient.get("first_name"), patient.get("last_name")) if x),
        "health_card_no": ins.get("membership_id") or (enc or {}).get("membership_id") or patient.get("hmo_id"),
        "mrn": patient.get("mrn"),
        "age": age,
        "sex": patient.get("gender"),
        "date_of_attendance": (enc or {}).get("created_at") or bill.get("billed_at"),
        "primary_diagnosis": ", ".join(d["description"] or d["icd_code"] or "" for d in primary[:1]),
        "differential_diagnosis": ", ".join(d["description"] or d["icd_code"] or "" for d in others),
        "consultation": lines("consultation", "registration"),
        "investigations": lines("lab", "radiology", "imaging"),
        "procedures": lines("procedure", "surgery", "theatre"),
        "admission": lines("ward", "admission", "nursing"),
        "other": [l for l in lines(*{(i.get("category") or "") for i in items} - {
            "consultation", "registration", "lab", "radiology", "imaging", "procedure", "surgery", "theatre", "ward",
            "admission", "nursing", "pharmacy", "drug"})],
        "medications": medications,
        "total": total,
        "not_covered": [{"description": i["description"], "cost": float(i["gross_amount"] or 0)} for i in not_covered],
        "approval_codes": sorted({i["hmo_approval_code"] for i in items if i.get("hmo_approval_code")}),
        "authorisation_code": (claim or {}).get("authorisation_code"),
        "clinical_summary": _clinical_summary(enc or {}, note or {}),
        "patient_signature_url": signature,
        "signed_at": (enc or {}).get("claim_signed_at"),
        "verified_at": (enc or {}).get("hmo_verified_at"),
        "verified_by": (enc or {}).get("hmo_verified_by"),
        "encounter_id": (enc or {}).get("id"),
    }


# ─── Inpatient Running Bill ───────────────────────────────────────────────────

class InpatientLineCreate(BaseModel):
    service_name: str = Field(..., min_length=1)
    quantity: float = Field(1.0, gt=0)
    unit_price: float = Field(..., ge=0)
    notes: Optional[str] = None

    model_config = {"extra": "ignore"}


@router.post("/inpatient-bill/{encounter_id}/lines", status_code=201)
def add_inpatient_line(encounter_id: int, payload: InpatientLineCreate, user=Depends(verify_jwt)):
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
def get_inpatient_bill(encounter_id: int, user=Depends(verify_jwt)):
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


# -- Discount approval --------------------------------------------------------
#
# "the cashier can add a discount and then admin can then confirm or reject that
# discount. So admin will have a UI card in their dashboard that shows them that
# there is a new discount waiting for approval."
#
# The discount amount lives on the bill as before; what is new is that applying
# one now records who asked, why, and who agreed.

class DiscountRequest(BaseModel):
    amount: float = Field(..., ge=0)
    reason: Optional[str] = None


class DiscountDecision(BaseModel):
    approve: bool
    note: Optional[str] = None


def _generate_receipt_number(entity: str = "ROYAN") -> Optional[str]:
    """Hospital receipt number (Scancare's own SCR- series for Scancare bills). Best-effort: a payment must never fail
    because numbering did, but a missing number is visible rather than silently faked."""
    fn = "generate_scancare_receipt_number" if entity == "SCANCARE" else "generate_receipt_number"
    try:
        result = db.rpc(fn, {}).execute()
        if result.data:
            row = result.data[0]
            return row.get(fn) if isinstance(row, dict) else str(row)
    except Exception as exc:
        logger.warning("Receipt number generation failed: %s", exc)
    return None


@router.post("/bills/{bill_id}/request-discount")
def request_discount(bill_id: int, payload: DiscountRequest, user=Depends(verify_jwt)):
    """Cashier applies a discount, which goes to an admin for a decision."""
    bill = _get_bill(bill_id)
    if bill.get("status") == "paid":
        raise HTTPException(status_code=409, detail="This bill is already settled.")

    subtotal = _num(bill.get("subtotal"), 0.0)
    if payload.amount > subtotal:
        raise HTTPException(
            status_code=422,
            detail="A discount cannot exceed the bill subtotal (%s)." % subtotal,
        )

    now = dt.datetime.now(dt.timezone.utc).isoformat()
    db.table(TABLE_BILLING).update({
        "discount": payload.amount,
        "discount_status": "pending",
        "discount_reason": payload.reason,
        "discount_requested_by": user.get("sub"),
        "discount_requested_at": now,
    }).eq("id", bill_id).execute()

    audit_event(
        "bill_discount_requested",
        {"bill_id": bill_id, "amount": payload.amount, "reason": payload.reason},
        actor_id=user.get("sub"), subject_type="bill", subject_id=str(bill_id),
    )
    invalidate_cache_tags("billing", "hospital", "executive")
    return {"ok": True, "discount_status": "pending", "discount": payload.amount}


@router.post("/bills/{bill_id}/discount-decision")
def decide_discount(bill_id: int, payload: DiscountDecision, user=Depends(verify_jwt)):
    """Admin approves or rejects. Rejecting clears the discount rather than
    leaving it applied-but-unapproved, which would be indistinguishable from an
    approved one on every other screen."""
    # Maker-checker: approving was open to any login, including the cashier who applied the discount.
    if not {"admin", "management", "finance"} & set(user.get("roles") or []):
        raise HTTPException(status_code=403, detail="Discounts are approved by finance, management or an admin")
    bill = _get_bill(bill_id)
    if payload.approve and bill.get("discount_requested_by") and str(bill["discount_requested_by"]) == str(user.get("sub")):
        raise HTTPException(status_code=403, detail="Someone other than the person who applied the discount must approve it")
    if bill.get("discount_status") != "pending":
        raise HTTPException(
            status_code=409,
            detail="This bill has no discount awaiting approval (it is '%s')." % bill.get("discount_status"),
        )

    now = dt.datetime.now(dt.timezone.utc).isoformat()
    update = {
        "discount_status": "approved" if payload.approve else "rejected",
        "discount_decided_by": user.get("sub"),
        "discount_decided_at": now,
        "discount_decision_note": payload.note,
    }
    if not payload.approve:
        update["discount"] = 0

    db.table(TABLE_BILLING).update(update).eq("id", bill_id).execute()
    if payload.approve:
        post_to_books("BILL_DISCOUNT", bill_id, user.get("sub"))

    audit_event(
        "bill_discount_%s" % ("approved" if payload.approve else "rejected"),
        {"bill_id": bill_id, "amount": bill.get("discount"), "note": payload.note},
        actor_id=user.get("sub"), subject_type="bill", subject_id=str(bill_id),
    )
    invalidate_cache_tags("billing", "hospital", "executive")
    return {"ok": True, "discount_status": update["discount_status"]}


class WardRateUpdate(BaseModel):
    daily_rate: float = Field(..., ge=0)


@router.get("/ward-rates")
def list_ward_rates(user=Depends(verify_jwt)):
    """Nightly bed rates per ward, and which are still unpriced.

    Surfaced as its own listing because an unpriced ward silently bills every
    admission at zero, and nothing else in the app would show that.
    """
    try:
        wards = db.table(TABLE_WARDS).select("id,name,daily_rate").order("name").execute().data or []
    except Exception:
        return {"wards": [], "count": 0, "unpriced": 0}
    unpriced = sum(1 for w in wards if not _num(w.get("daily_rate"), 0.0))
    return {"wards": wards, "count": len(wards), "unpriced": unpriced}


@router.patch("/ward-rates/{ward_id}")
def set_ward_rate(ward_id: int, payload: WardRateUpdate, user=Depends(verify_jwt)):
    """Set a ward's nightly bed rate."""
    try:
        db.table(TABLE_WARDS).update({"daily_rate": payload.daily_rate}).eq("id", ward_id).execute()
    except Exception as exc:
        logger.error("Ward rate update failed: %s", exc)
        raise HTTPException(status_code=500, detail="Could not save the ward rate")
    audit_event(
        "ward_rate_set", {"ward_id": ward_id, "daily_rate": payload.daily_rate},
        actor_id=user.get("sub"), subject_type="ward", subject_id=str(ward_id),
    )
    invalidate_cache_tags("billing", "wards", "hospital")
    return {"ok": True, "ward_id": ward_id, "daily_rate": payload.daily_rate}


# -- Ad-hoc encounter charges -------------------------------------------------
#
# "Ambulance Service, if it was required for that patient... just make sure that
# anytime Ambulance Service is requested, it is added to the billing" and "we can
# add a new consultant, add a new lab, add a new scan, add drug, and every time
# you do that for an admitted patient, the bill must also keep track of that."
#
# One endpoint rather than one per charge type. Ambulance was the example given,
# but the underlying need is the same for every mid-stay charge, and six
# near-identical endpoints would be six places to fix the same bug.

class EncounterChargeCreate(BaseModel):
    description: str = Field(..., min_length=1, max_length=300)
    category: str = "misc"
    quantity: float = Field(1, gt=0)
    unit_price: float = Field(..., ge=0)
    service_id: Optional[int] = None
    notes: Optional[str] = None


ENCOUNTER_CHARGE_CATEGORIES = {
    "ward", "nursing", "consultation", "lab", "imaging",
    "pharmacy", "procedure", "consumable", "ambulance", "misc",
}


@router.get("/encounters/{encounter_id}/charges")
def list_encounter_charges(encounter_id: int, user=Depends(verify_jwt)):
    """Ad-hoc charges on this encounter, plus the derived room charge."""
    enc = db.table(TABLE_ENCOUNTERS).select("id,patient_id").eq("id", encounter_id).limit(1).execute()
    if not enc.data:
        raise HTTPException(status_code=404, detail="Encounter %s not found" % encounter_id)
    patient_id = enc.data[0].get("patient_id")

    try:
        rows = (
            db.table(TABLE_INPATIENT_BILL_LINES).select("*")
            .eq("encounter_id", encounter_id).order("charged_at").execute().data or []
        )
    except Exception:
        rows = []

    lines = rows + _derive_room_charges(encounter_id, patient_id)
    return {
        "charges": lines,
        "count": len(lines),
        "total": round(sum(_num(l.get("total")) for l in lines), 2),
    }


@router.post("/encounters/{encounter_id}/charges", status_code=201)
def add_encounter_charge(
    encounter_id: int, payload: EncounterChargeCreate, user=Depends(verify_jwt)
):
    """Add a charge to a running encounter."""
    if payload.category not in ENCOUNTER_CHARGE_CATEGORIES:
        raise HTTPException(
            status_code=422,
            detail="category must be one of %s" % sorted(ENCOUNTER_CHARGE_CATEGORIES),
        )

    enc = db.table(TABLE_ENCOUNTERS).select("id,patient_id,status").eq("id", encounter_id).limit(1).execute()
    if not enc.data:
        raise HTTPException(status_code=404, detail="Encounter %s not found" % encounter_id)

    row = {
        "encounter_id": encounter_id,
        "patient_id": enc.data[0].get("patient_id"),
        "description": payload.description.strip(),
        "category": payload.category,
        "quantity": payload.quantity,
        "unit_price": payload.unit_price,
        # Stored, not computed on read: a later price change must not rewrite
        # what this patient was charged today.
        "total": round(payload.quantity * payload.unit_price, 2),
        "source": "manual",
        "added_by": user.get("sub"),
        "notes": payload.notes,
    }
    try:
        created = db.table(TABLE_INPATIENT_BILL_LINES).insert(row).execute()
    except Exception as exc:
        logger.error("Encounter charge failed: %s", exc)
        raise HTTPException(status_code=500, detail="Could not add the charge")

    audit_event(
        "encounter_charge_added",
        {"encounter_id": encounter_id, "description": payload.description, "total": row["total"]},
        actor_id=user.get("sub"), subject_type="encounter", subject_id=str(encounter_id),
    )
    invalidate_cache_tags("billing", "hospital")
    return {"ok": True, "charge": (created.data or [row])[0]}


@router.delete("/encounters/{encounter_id}/charges/{charge_id}")
def remove_encounter_charge(encounter_id: int, charge_id: int, user=Depends(verify_jwt)):
    """Remove a charge added in error. Only ad-hoc lines can be removed — the
    room charge is derived from the admission and cannot be deleted without
    changing the stay itself."""
    try:
        db.table(TABLE_INPATIENT_BILL_LINES).delete().eq("id", charge_id).eq("encounter_id", encounter_id).execute()
    except Exception as exc:
        logger.error("Charge removal failed: %s", exc)
        raise HTTPException(status_code=500, detail="Could not remove the charge")
    audit_event(
        "encounter_charge_removed", {"encounter_id": encounter_id, "charge_id": charge_id},
        actor_id=user.get("sub"), subject_type="encounter", subject_id=str(encounter_id),
    )
    invalidate_cache_tags("billing", "hospital")
    return {"ok": True}


# -- The correction pen -------------------------------------------------------
#
# "the correction pen feature allows the admin to handle refunds, confirm
# discounts, and... if a patient requests a bag of blood which is about 90k and
# doesn't use it, they have to split the bill so the patient doesn't pay the
# full bill. Admin also needs to be able to track that."
#
# Every correction is an ADDED row, never an edit. The bill's own figures are
# left alone and the effective total is derived from the trail, so "it says 40k"
# always comes with "it said 90k until Tuesday, changed by X, because Y".
#
# Admin-only. These move money after the fact, which is exactly the operation
# that needs a name attached to it.

class BillAdjustmentCreate(BaseModel):
    adjustment_type: str = Field(..., description="reduction | reallocation | refund")
    amount: float = Field(..., gt=0)
    reason: str = Field(..., min_length=3, max_length=500)
    bill_item_id: Optional[int] = None
    line_label: Optional[str] = None
    reallocated_to: Optional[str] = None
    payment_id: Optional[int] = None


def _adjustment_totals(billing_id: int) -> dict:
    """What the trail has done to this bill so far."""
    try:
        rows = (
            db.table("royan_bill_adjustments").select("*")
            .eq("billing_id", billing_id).order("adjusted_at").execute().data or []
        )
    except Exception:
        return {"adjustments": [], "reduced": 0.0, "refunded": 0.0, "reallocated": 0.0}

    # A reversal cancels the row it points at, so neither counts toward the
    # effective total. Netting them out here keeps every caller consistent.
    reversed_ids = {r["reverses_id"] for r in rows if r.get("reverses_id")}
    live = [r for r in rows if r["id"] not in reversed_ids and r["adjustment_type"] != "reversal"]

    def total(kind):
        return round(sum(_num(r.get("amount")) for r in live if r["adjustment_type"] == kind), 2)

    return {
        "adjustments": rows,
        "reduced": total("reduction"),
        "refunded": total("refund"),
        "reallocated": total("reallocation"),
    }


@router.get("/bills/{bill_id}/adjustments")
def list_bill_adjustments(bill_id: int, user=Depends(verify_jwt)):
    """The correction trail for one bill, and what it nets to."""
    bill = _get_bill(bill_id)
    totals = _adjustment_totals(bill_id)
    subtotal = _num(bill.get("subtotal"), 0.0)
    # Reductions and reallocations both lower what THIS patient owes; a refund
    # returns money already taken and does not change the charge itself.
    effective = round(subtotal - totals["reduced"] - totals["reallocated"], 2)
    return {
        "bill_id": bill_id,
        **totals,
        "original_subtotal": subtotal,
        "effective_subtotal": max(effective, 0.0),
    }


@router.post("/bills/{bill_id}/adjust", status_code=201)
def adjust_bill(bill_id: int, payload: BillAdjustmentCreate, user=Depends(require_role("admin"))):
    """Reduce, reallocate or refund part of a bill."""
    if payload.adjustment_type not in ("reduction", "reallocation", "refund"):
        raise HTTPException(
            status_code=422,
            detail="adjustment_type must be reduction, reallocation or refund",
        )
    bill = _get_bill(bill_id)
    before = _adjustment_totals(bill_id)
    subtotal = _num(bill.get("subtotal"), 0.0)

    if payload.adjustment_type in ("reduction", "reallocation"):
        headroom = subtotal - before["reduced"] - before["reallocated"]
        if payload.amount > headroom + 0.001:
            raise HTTPException(
                status_code=422,
                detail="Adjustments would exceed the bill. %s remains adjustable." % round(headroom, 2),
            )
        amount_before = round(subtotal - before["reduced"] - before["reallocated"], 2)
        amount_after = round(amount_before - payload.amount, 2)
    else:
        # Refunds are bounded by what was actually taken, not by the bill.
        try:
            paid_rows = db.table(TABLE_PAYMENTS).select("amount").eq("billing_id", bill_id).execute().data or []
        except Exception:
            paid_rows = []
        paid = round(sum(_num(p.get("amount")) for p in paid_rows), 2)
        headroom = paid - before["refunded"]
        if payload.amount > headroom + 0.001:
            raise HTTPException(
                status_code=422,
                detail="Cannot refund more than was paid. %s remains refundable." % round(headroom, 2),
            )
        amount_before = headroom
        amount_after = round(headroom - payload.amount, 2)

    if payload.adjustment_type == "reallocation" and not (payload.reallocated_to or "").strip():
        raise HTTPException(
            status_code=422,
            detail="A reallocation must say who is carrying the amount instead.",
        )

    row = {
        "billing_id": bill_id,
        "patient_id": bill.get("patient_id"),
        "adjustment_type": payload.adjustment_type,
        "amount": payload.amount,
        "amount_before": amount_before,
        "amount_after": amount_after,
        "bill_item_id": payload.bill_item_id,
        "line_label": payload.line_label,
        "reallocated_to": payload.reallocated_to,
        "payment_id": payload.payment_id,
        "reason": payload.reason.strip(),
        "adjusted_by": user.get("sub"),
    }
    try:
        created = db.table("royan_bill_adjustments").insert(row).execute()
    except Exception as exc:
        logger.error("Bill adjustment failed: %s", exc)
        raise HTTPException(status_code=500, detail="Could not record the adjustment")

    _audit("bill_adjusted", {
        "type": payload.adjustment_type, "amount": payload.amount,
        "reason": payload.reason, "reallocated_to": payload.reallocated_to,
    }, user, "bill", bill_id)
    adj_row = (created.data or [{}])[0]
    if adj_row.get("id"):
        post_to_books("BILL_ADJUSTMENT", adj_row["id"], user.get("sub"))
    invalidate_cache_tags("billing", "hospital", "executive")
    return {"ok": True, "adjustment": (created.data or [row])[0], **_adjustment_totals(bill_id)}


@router.post("/bills/{bill_id}/adjustments/{adjustment_id}/reverse", status_code=201)
def reverse_adjustment(
    bill_id: int, adjustment_id: int, payload: BillAdjustmentCreate, user=Depends(require_role("admin"))
):
    """Undo an adjustment made in error — by adding a reversal, not deleting it.

    Deleting would leave no trace that the first correction ever happened, which
    is precisely what someone covering a mistake would want.
    """
    found = (
        db.table("royan_bill_adjustments").select("*")
        .eq("id", adjustment_id).eq("billing_id", bill_id).limit(1).execute().data
    )
    if not found:
        raise HTTPException(status_code=404, detail="Adjustment not found on this bill")
    original = found[0]

    already = (
        db.table("royan_bill_adjustments").select("id")
        .eq("reverses_id", adjustment_id).limit(1).execute().data
    )
    if already:
        raise HTTPException(status_code=409, detail="That adjustment has already been reversed.")

    row = {
        "billing_id": bill_id,
        "patient_id": original.get("patient_id"),
        "adjustment_type": "reversal",
        "amount": original["amount"],
        "reason": payload.reason.strip(),
        "reverses_id": adjustment_id,
        "adjusted_by": user.get("sub"),
        "line_label": original.get("line_label"),
    }
    try:
        created = db.table("royan_bill_adjustments").insert(row).execute()
    except Exception as exc:
        logger.error("Adjustment reversal failed: %s", exc)
        raise HTTPException(status_code=500, detail="Could not record the reversal")

    _audit("bill_adjustment_reversed",
           {"adjustment_id": adjustment_id, "reason": payload.reason}, user, "bill", bill_id)
    rev_row = (created.data or [{}])[0]
    if rev_row.get("id"):
        post_to_books("BILL_ADJUSTMENT", rev_row["id"], user.get("sub"))
    invalidate_cache_tags("billing", "hospital", "executive")
    return {"ok": True, "reversal": (created.data or [row])[0], **_adjustment_totals(bill_id)}



# ── Stage billing: front-desk quote, release, clearance, consultation fees ────────────────────────────

@router.get("/encounters/{encounter_id}/front-desk-quote")
def front_desk_quote(encounter_id: int, specialty: Optional[str] = None, kind: Optional[str] = None, user=Depends(verify_jwt)):
    """What the front desk will bill: registration (new patients) and the consultation, pre-filled."""
    from src.fin.db import q1 as _q1, tx as _tx
    from src.services import stage_billing as sb
    with _tx() as conn:
        enc = _q1(conn, "SELECT * FROM royan_encounters WHERE id=%s", (encounter_id,))
        if not enc:
            raise HTTPException(status_code=404, detail="Encounter not found")
        return {"items": sb.front_desk_items(conn, enc, specialty, kind), "consultation": sb.consultation_quote(conn, enc, specialty, kind),
                "new_patient": sb.is_new_patient(conn, enc["patient_id"], encounter_id)}


@router.get("/consultation-quote")
def consultation_quote_for(patient_id: int, department: Optional[str] = None, doctor_id: Optional[str] = None,
                           specialty: Optional[str] = None, kind: Optional[str] = None, user=Depends(verify_jwt)):
    """Before the encounter exists: what registration + consultation will cost for this patient, clinic and doctor."""
    from src.fin.db import tx as _tx
    from src.services import stage_billing as sb
    with _tx() as conn:
        fake = {"id": 0, "patient_id": patient_id, "department": department, "doctor_id": doctor_id}
        c = sb.consultation_quote(conn, fake, specialty, kind)
        new = sb.is_new_patient(conn, patient_id, 0)
        reg = None
        if new:
            from src.fin.db import q1 as _q1
            reg = _q1(conn, """SELECT s.name, s.base_price FROM royan_billing_settings k JOIN royan_service_catalog s ON s.id::text=k.value
                               WHERE k.key='registration_service_id'""")
        total = float(c["unit_price"]) + float((reg or {}).get("base_price") or 0)
        return {"consultation": c, "new_patient": new, "registration": reg, "total": total}


class ReleaseRequest(BaseModel):
    reason: str = Field(..., min_length=3)


@router.post("/bills/{bill_id}/release")
def release_bill(bill_id: int, payload: ReleaseRequest, user=Depends(verify_jwt)):
    """Cashier: a part-paid bill's services may go ahead (the balance stays on the patient's account)."""
    bill = _get_bill(bill_id)
    if bill["status"] not in ("partial", "pending"):
        raise HTTPException(status_code=409, detail=f"Bill is '{bill['status']}' - nothing to release")
    db.table(TABLE_BILLING).update({"released_at": dt.datetime.now(dt.timezone.utc).isoformat(), "released_by": user.get("sub"),
                                    "release_reason": payload.reason}).eq("id", bill_id).execute()
    _audit("bill_released", {"reason": payload.reason, "status": bill["status"]}, user, "bill", bill_id)
    return {"ok": True, "bill_id": bill_id}


class OrderRelease(BaseModel):
    source: str = Field(..., pattern="^(lab_order|radiology_order|prescription)$")
    source_id: str
    reason: str = Field(..., min_length=3)


@router.post("/releases")
def release_order(payload: OrderRelease, user=Depends(require_role("admin", "finance", "management"))):
    """Supervisor: let one order be served before payment (emergency, credit agreed...). Recorded with the reason."""
    from src.fin.db import ex as _ex, tx as _tx
    with _tx() as conn:
        _ex(conn, """INSERT INTO royan_service_releases (source, source_id, reason, released_by) VALUES (%s,%s,%s,%s)
                     ON CONFLICT (source, source_id) DO UPDATE SET reason=EXCLUDED.reason, released_by=EXCLUDED.released_by,
                     released_at=now()""", (payload.source, payload.source_id, payload.reason, user.get("email") or user.get("sub")))
    _audit("order_released_unpaid", payload.model_dump(), user, payload.source, payload.source_id)
    return {"ok": True}


@router.get("/clearance")
def order_clearance(source: str, source_id: str, user=Depends(verify_jwt)):
    """May lab / radiology / pharmacy serve this order yet?"""
    from src.services.stage_billing import clearance
    return clearance(source, source_id)


@router.get("/consultation-tariffs")
def list_consultation_tariffs(user=Depends(verify_jwt)):
    from src.fin.db import q as _q, tx as _tx
    with _tx() as conn:
        tariffs = _q(conn, """SELECT t.*, a.name AS initial_name, a.base_price AS initial_price, f.name AS follow_up_name,
                                     f.base_price AS follow_up_price, r.name AS review_name, r.base_price AS review_price
                              FROM royan_consultation_tariffs t
                              LEFT JOIN royan_service_catalog a ON a.id=t.initial_service_id
                              LEFT JOIN royan_service_catalog f ON f.id=t.follow_up_service_id
                              LEFT JOIN royan_service_catalog r ON r.id=t.review_service_id ORDER BY t.specialty""")
        doctors = _q(conn, """SELECT s.id::text AS doctor_id, s.full_name, s.specialty AS staff_specialty, s.department,
                                     d.tariff_id, d.initial_fee, d.follow_up_fee
                              FROM royan_staff s LEFT JOIN royan_doctor_consultation_fees d ON d.doctor_id=s.id
                              WHERE s.is_active AND lower(COALESCE(s.role,''))='doctor' ORDER BY s.full_name""")
        reg = _q(conn, """SELECT s.id, s.name, s.base_price FROM royan_billing_settings k JOIN royan_service_catalog s ON s.id::text=k.value
                          WHERE k.key='registration_service_id'""")
        mode = _q(conn, "SELECT value FROM royan_billing_settings WHERE key='pay_first'")
        sig = {r["key"]: r["value"] for r in _q(conn, "SELECT key, value FROM royan_billing_settings WHERE key = ANY(%s)",
                                               (list(SIGNATORY_KEYS),))}
    return {"tariffs": tariffs, "doctors": doctors, "registration": reg[0] if reg else None,
            "pay_first": mode[0]["value"] if mode else "off", "signatories": sig}


class TariffUpdate(BaseModel):
    specialty: Optional[str] = None
    department_code: Optional[str] = None
    initial_service_id: Optional[int] = None
    follow_up_service_id: Optional[int] = None
    review_service_id: Optional[int] = None
    follow_up_days: Optional[int] = None
    is_active: Optional[bool] = None
    # prices: set on the specialty's consultation items in the service catalogue (created when missing)
    initial_price: Optional[float] = Field(None, ge=0)
    follow_up_price: Optional[float] = Field(None, ge=0)


def _price_tariff(conn, tariff: dict, initial_price: Optional[float], follow_up_price: Optional[float], actor: Optional[str]) -> dict:
    """Put the consultation prices on the specialty's catalogue items, creating the items when the specialty has none."""
    from src.fin.db import q1 as _q1
    for col, price, label, code in (("initial_service_id", initial_price, "Consultation", "INIT"),
                                     ("follow_up_service_id", follow_up_price, "Follow-up Consultation", "FUP")):
        if price is None:
            continue
        sid = tariff.get(col)
        if sid:
            _q1(conn, "UPDATE royan_service_catalog SET base_price=%s WHERE id=%s RETURNING id", (price, sid))
        else:
            name = f"{tariff['specialty']} {label}"
            svc_code = f"CONS-{''.join(ch for ch in tariff['specialty'].upper() if ch.isalnum())[:12]}-{code}"
            row = _q1(conn, """INSERT INTO royan_service_catalog (service_code, name, category, base_price, is_active)
                               VALUES (%s,%s,'consultation',%s,true)
                               ON CONFLICT (service_code) DO UPDATE SET base_price=EXCLUDED.base_price RETURNING id""",
                      (svc_code, name, price))
            tariff = _q1(conn, f"UPDATE royan_consultation_tariffs SET {col}=%s, updated_by=%s, updated_at=now() WHERE id=%s RETURNING *",
                         (row["id"], actor, tariff["id"]))
    return tariff


class TariffImport(BaseModel):
    rows: list[dict]


@router.post("/consultation-tariffs/import")
def import_consultation_tariffs(payload: TariffImport, user=Depends(require_role("admin", "finance", "management"))):
    """Upload the consultation price list (CSV/Excel rows: specialty, initial_fee, follow_up_fee, follow_up_days).
    Known specialties are re-priced; new ones are added with their own catalogue items."""
    from src.fin.db import q1 as _q1, tx as _tx

    def num(v):
        try:
            return None if v in (None, "") else float(str(v).replace(",", "").replace("₦", "").strip())
        except ValueError:
            return None

    done, skipped = [], []
    with _tx() as conn:
        for r in payload.rows:
            k = {str(a).strip().lower().replace(" ", "_"): b for a, b in r.items()}
            spec = str(k.get("specialty") or k.get("clinic") or "").strip()
            if not spec:
                skipped.append({"row": r, "why": "no specialty"})
                continue
            t = _q1(conn, "SELECT * FROM royan_consultation_tariffs WHERE lower(specialty)=lower(%s)", (spec,))
            if not t:
                t = _q1(conn, "INSERT INTO royan_consultation_tariffs (specialty, updated_by) VALUES (%s,%s) RETURNING *", (spec, user.get("sub")))
            days = num(k.get("follow_up_days"))
            if days is not None:
                t = _q1(conn, "UPDATE royan_consultation_tariffs SET follow_up_days=%s WHERE id=%s RETURNING *", (int(days), t["id"]))
            _price_tariff(conn, t, num(k.get("initial_fee") or k.get("initial") or k.get("fee")),
                          num(k.get("follow_up_fee") or k.get("follow_up")), user.get("sub"))
            done.append(spec)
    _audit("consultation_tariffs_imported", {"count": len(done)}, user, "consultation_tariff", "import")
    return {"ok": True, "imported": done, "skipped": skipped}


@router.put("/consultation-tariffs/{tariff_id}")
def upsert_consultation_tariff(tariff_id: str, payload: TariffUpdate, user=Depends(require_role("admin", "finance", "management"))):
    """Edit a specialty's consultation items (or create one: tariff_id='new')."""
    from src.fin.db import q1 as _q1, tx as _tx
    prices = {"initial_price": payload.initial_price, "follow_up_price": payload.follow_up_price}
    data = {k: v for k, v in payload.model_dump(exclude=set(prices)).items() if v is not None}
    with _tx() as conn:
        if tariff_id == "new":
            if not data.get("specialty"):
                raise HTTPException(status_code=422, detail="Name the specialty")
            cols = list(data)
            row = _q1(conn, f"INSERT INTO royan_consultation_tariffs ({', '.join(cols)}, updated_by) VALUES ({', '.join(['%s'] * len(cols))}, %s) RETURNING *",
                      [data[c] for c in cols] + [user.get("sub")])
        elif data:
            sets = ", ".join(f"{k}=%s" for k in data)
            row = _q1(conn, f"UPDATE royan_consultation_tariffs SET {sets}, updated_by=%s, updated_at=now() WHERE id=%s RETURNING *",
                      list(data.values()) + [user.get("sub"), int(tariff_id)])
        else:
            row = _q1(conn, "SELECT * FROM royan_consultation_tariffs WHERE id=%s", (int(tariff_id),))
        if row and any(v is not None for v in prices.values()):
            row = _price_tariff(conn, row, prices["initial_price"], prices["follow_up_price"], user.get("sub"))
    if not row:
        raise HTTPException(status_code=404, detail="Specialty not found")
    _audit("consultation_tariff_saved", data, user, "consultation_tariff", row["id"])
    return row


class DoctorFee(BaseModel):
    tariff_id: Optional[int] = None
    initial_fee: Optional[float] = Field(None, ge=0)
    follow_up_fee: Optional[float] = Field(None, ge=0)


@router.put("/doctor-fees/{doctor_id}")
def set_doctor_fee(doctor_id: str, payload: DoctorFee, user=Depends(require_role("admin", "finance", "management"))):
    """A doctor's own specialty and consultation fee (blank fee = the specialty's tariff)."""
    from src.fin.db import q1 as _q1, tx as _tx
    with _tx() as conn:
        row = _q1(conn, """INSERT INTO royan_doctor_consultation_fees (doctor_id, tariff_id, initial_fee, follow_up_fee, updated_by)
                           VALUES (%s,%s,%s,%s,%s) ON CONFLICT (doctor_id) DO UPDATE SET tariff_id=EXCLUDED.tariff_id,
                           initial_fee=EXCLUDED.initial_fee, follow_up_fee=EXCLUDED.follow_up_fee, updated_by=EXCLUDED.updated_by,
                           updated_at=now() RETURNING *""", (doctor_id, payload.tariff_id, payload.initial_fee, payload.follow_up_fee, user.get("sub")))
    _audit("doctor_consultation_fee_saved", payload.model_dump(), user, "doctor", doctor_id)
    return row


class BillingSetting(BaseModel):
    registration_service_id: Optional[int] = None
    registration_price: Optional[float] = Field(None, ge=0)
    pay_first: Optional[str] = Field(None, pattern="^(off|private_outpatient|all_but_hmo)$")
    # "Name, title" printed on invoices and receipts until staff signatures are on file
    signatory_bill_manager: Optional[str] = Field(None, max_length=120)
    signatory_med_supdt: Optional[str] = Field(None, max_length=120)
    signatory_authorised: Optional[str] = Field(None, max_length=120)


@router.put("/billing-settings")
def set_billing_settings(payload: BillingSetting, user=Depends(require_role("admin", "finance", "management"))):
    from src.fin.db import ex as _ex, tx as _tx
    with _tx() as conn:
        if payload.registration_price is not None:
            _ex(conn, """UPDATE royan_service_catalog SET base_price=%s WHERE id::text=(SELECT value FROM royan_billing_settings
                         WHERE key='registration_service_id')""", (payload.registration_price,))
        for k, v in payload.model_dump(exclude={"registration_price"}).items():
            if v is not None:
                _ex(conn, """INSERT INTO royan_billing_settings (key, value) VALUES (%s,%s)
                             ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value""", (k, str(v)))
    _audit("billing_settings_saved", payload.model_dump(), user, "billing_settings", "1")
    return {"ok": True}



@router.get("/patients/{patient_id}/account")
def patient_account(patient_id: int, user=Depends(verify_jwt)):
    """The patient's account at the cashier: every bill (debit) and receipt (credit) with a running balance, per
    company (Royan / Scancare). Voided bills and receipts are listed but do not count. Hope history included."""
    from src.fin.db import q as _q, q1 as _q1, tx as _tx
    with _tx() as conn:
        patient = _q1(conn, "SELECT id, mrn, first_name, last_name, phone FROM royan_patients WHERE id=%s", (patient_id,))
        if not patient:
            raise HTTPException(status_code=404, detail="Patient not found")
        rows = _q(conn, """
            SELECT 'bill' AS kind, b.id, b.id AS bill_id, b.bill_number AS ref, b.billed_at AS at, COALESCE(b.entity,'ROYAN') AS company,
                   b.status, COALESCE(b.patient_balance,0) AS debit, 0::numeric AS credit, b.stage, b.void_reason,
                   NULL::text AS method
              FROM royan_billing b WHERE b.patient_id=%s
            UNION ALL
            SELECT 'receipt', p.id, p.billing_id, COALESCE(p.receipt_number, 'PAY-'||p.id), p.received_at, COALESCE(b.entity,'ROYAN'),
                   COALESCE(p.status,'posted'), 0, p.amount, NULL, p.void_reason, p.payment_method
              FROM royan_payments p LEFT JOIN royan_billing b ON b.id=p.billing_id WHERE p.patient_id=%s
            ORDER BY at, kind""", (patient_id, patient_id))
    balances: dict[str, float] = {}
    lines = []
    for r in rows:
        void = r["status"] == "void"
        if not void:
            balances[r["company"]] = round(balances.get(r["company"], 0.0) + float(r["debit"] or 0) - float(r["credit"] or 0), 2)
        lines.append({**r, "debit": float(r["debit"] or 0), "credit": float(r["credit"] or 0), "void": void,
                      "balance": balances.get(r["company"], 0.0)})
    return {"patient": patient, "lines": lines, "balances": balances, "balance": round(sum(balances.values()), 2)}
