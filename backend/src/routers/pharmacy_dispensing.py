"""
Pharmacy Dispensing Router — RoyanHealth / Royan Hospital
============================================================
Manages prescriptions and dispensing records.

Endpoints:
  POST /pharmacy/prescriptions                         – Create prescription (doctor)
  GET  /pharmacy/prescriptions                         – List prescriptions (filter by encounter/patient/status)
  GET  /pharmacy/prescriptions/{id}                    – Get prescription with dispensing history
  POST /pharmacy/prescriptions/{id}/dispense           – Dispense a prescription
  POST /pharmacy/prescriptions/{id}/cancel             – Cancel a prescription
"""
from __future__ import annotations

import datetime as dt
import logging
import os
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator

from src.db import db, audit_event
from src.middleware import verify_jwt, require_role
from src.services.event_service import emit_clinical_event
from src.services.clinical_shared import get_patient_allergies
from src.constants import (
    PRESCRIPTION_ROUTES_ALLOWED, PRESCRIPTION_STATUS_ALLOWED,
    TABLE_PRESCRIPTIONS, TABLE_DISPENSING,
    TABLE_DRUG_INVENTORY, TABLE_DRUG_INTERACTIONS, TABLE_ALLERGIES,
    TABLE_REPLENISHMENT_REQUESTS, TABLE_MAR_ENTRIES,
    TABLE_MEDICATION_ADMIN, MEDICATION_ADMIN_STATUS,
    TABLE_SALES_RETURNS,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/pharmacy", tags=["Pharmacy"])

PRESCRIPTION_STATUSES = PRESCRIPTION_STATUS_ALLOWED
ROUTES = PRESCRIPTION_ROUTES_ALLOWED


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class PrescriptionCreate(BaseModel):
    encounter_id: int
    patient_id: int
    drug_name: str = Field(..., min_length=1, max_length=200)
    drug_code: Optional[str] = None
    dosage: Optional[str] = None
    dose: Optional[str] = None
    frequency: str = Field(..., min_length=1)
    duration: Optional[str] = None
    route: str = "oral"
    quantity: float = Field(1.0, gt=0)
    unit: str = "tablet"
    special_instructions: Optional[str] = None
    notes: Optional[str] = None
    override_duplicate: bool = False   # prescriber must explicitly acknowledge an existing active rx for this drug

    model_config = {"extra": "ignore"}


class DispenseRequest(BaseModel):
    quantity_dispensed: float = Field(..., gt=0)
    unit: Optional[str] = None
    batch_number: Optional[str] = None
    expiry_date: Optional[str] = None   # ISO date string
    unit_cost: float = Field(0.0, ge=0)
    counselling_given: bool = False
    counselled: Optional[bool] = None
    counselling_notes: Optional[str] = None
    notes: Optional[str] = None
    override_allergy: bool = False      # pharmacist must explicitly acknowledge allergy
    acknowledge_ddi: bool = False       # pharmacist acknowledges DDI warnings

    model_config = {"extra": "ignore"}

    @field_validator("quantity_dispensed", mode="before")
    @classmethod
    def _coerce_quantity(cls, value):
        if isinstance(value, str):
            token = value.strip().split(" ")[0]
            return float(token)
        return value


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_prescription(prescription_id: int) -> dict:
    result = db.table(TABLE_PRESCRIPTIONS).select("*").eq("id", prescription_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail=f"Prescription {prescription_id} not found")
    return result.data[0]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/prescriptions", status_code=201)
async def create_prescription(payload: PrescriptionCreate, user=Depends(verify_jwt)):
    """Write a new prescription (called by doctor or system)."""
    if payload.route not in ROUTES:
        raise HTTPException(status_code=422, detail=f"route must be one of {ROUTES}")

    if not payload.override_duplicate:
        existing = (
            db.table(TABLE_PRESCRIPTIONS)
            .select("id,drug_name,status,prescribed_at")
            .eq("patient_id", payload.patient_id)
            .ilike("drug_name", payload.drug_name.strip())
            .not_.in_("status", ["cancelled", "returned"])
            .execute()
        )
        if existing.data:
            return {
                "ok": False,
                "duplicate_alert": True,
                "existing_prescriptions": existing.data,
                "message": f"Patient already has an active prescription for '{payload.drug_name}'. Set override_duplicate=true to proceed anyway.",
            }

    data = payload.model_dump(exclude_none=True)
    data.pop("override_duplicate", None)
    if data.get("dose") and not data.get("dosage"):
        data["dosage"] = data.pop("dose")
    data.pop("dose", None)
    if not data.get("dosage"):
        raise HTTPException(status_code=422, detail="dosage is required")
    data["prescribed_by"] = user.get("sub") or "system"
    data["status"] = "pending"

    try:
        result = db.table(TABLE_PRESCRIPTIONS).insert(data).execute()
    except Exception as exc:
        logger.error("Prescription creation failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to create prescription")

    rx = result.data[0] if result.data else data
    audit_event(
        "prescription_created",
        {"drug": payload.drug_name, "encounter_id": payload.encounter_id},
        actor_id=user.get("sub"),
        subject_type="prescription",
        subject_id=str(rx.get("id") or ""),
    )
    return {"ok": True, "prescription": rx}


@router.get("/prescriptions")
async def list_prescriptions(
    encounter_id: Optional[int] = Query(None),
    patient_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    user=Depends(verify_jwt),
):
    # Exclude Hope-imported placeholder rows (drug_name "Imported prescription",
    # external_source "hope") from every live prescriptions view — same convention
    # as list_encounters. These are low-fidelity historical import rows with no
    # real drug data, left in "pending" status forever; they were drowning out
    # actual current prescriptions in the pharmacy queue.
    query = (
        db.table(TABLE_PRESCRIPTIONS)
        .select("*")
        .is_("external_source", None)
        .order("prescribed_at", desc=True)
        .limit(limit)
    )
    if encounter_id:
        query = query.eq("encounter_id", encounter_id)
    if patient_id:
        query = query.eq("patient_id", patient_id)
    if status:
        if status not in PRESCRIPTION_STATUSES:
            raise HTTPException(status_code=422, detail=f"Unknown status '{status}'")
        query = query.eq("status", status)
    result = query.execute()
    return {"prescriptions": result.data, "count": len(result.data)}


@router.get("/prescriptions/{prescription_id}")
async def get_prescription(prescription_id: int, user=Depends(verify_jwt)):
    rx = _get_prescription(prescription_id)
    dispensing = db.table(TABLE_DISPENSING).select("*").eq("prescription_id", prescription_id).execute()
    return {"prescription": rx, "dispensing_records": dispensing.data}


@router.post("/prescriptions/{prescription_id}/dispense")
async def dispense_prescription(prescription_id: int, payload: DispenseRequest, user=Depends(verify_jwt)):
    """Record dispensing of a prescription by a pharmacist."""
    rx = _get_prescription(prescription_id)

    if rx["status"] in ("cancelled", "returned"):
        raise HTTPException(status_code=409, detail=f"Prescription is '{rx['status']}'; cannot dispense")

    drug_name_lower = rx["drug_name"].lower()
    patient_id = rx["patient_id"]

    # ── Allergy check ────────────────────────────────────────────────────────
    allergies = get_patient_allergies(patient_id)
    allergy_hits = [
        a for a in allergies
        if a.get("allergen", "").lower() in drug_name_lower or drug_name_lower in a.get("allergen", "").lower()
    ]
    if allergy_hits and not payload.override_allergy:
        return {
            "ok": False,
            "allergy_alert": True,
            "allergies": allergy_hits,
            "message": "Patient has a documented allergy to this drug. Set override_allergy=true to proceed.",
        }

    # ── DDI check ────────────────────────────────────────────────────────────
    active_rxs = db.table(TABLE_PRESCRIPTIONS).select("drug_name").eq("patient_id", patient_id).in_("status", ["pending", "partially_dispensed"]).execute()
    concurrent_drugs = [r["drug_name"].lower() for r in (active_rxs.data or []) if r.get("drug_name")]
    other_drugs = [d for d in concurrent_drugs if d != drug_name_lower]
    ddi_warnings: list[dict] = []
    if other_drugs:
        # Single query for all interactions involving the dispensed drug (not one per concurrent drug)
        interactions = db.table(TABLE_DRUG_INTERACTIONS).select("severity,description,drug_a,drug_b").or_(
            f"drug_a.ilike.%{drug_name_lower}%,drug_b.ilike.%{drug_name_lower}%"
        ).execute()
        for ix in (interactions.data or []):
            other_side = (ix.get("drug_b") or "").lower() if drug_name_lower in (ix.get("drug_a") or "").lower() else (ix.get("drug_a") or "").lower()
            matched = next((d for d in other_drugs if d in other_side or other_side in d), other_drugs[0])
            ddi_warnings.append({"drug": matched, "severity": ix.get("severity"), "description": ix.get("description")})

    critical_ddi = [w for w in ddi_warnings if w.get("severity") == "contraindicated"]
    if critical_ddi and not payload.acknowledge_ddi:
        return {
            "ok": False,
            "ddi_alert": True,
            "interactions": critical_ddi,
            "message": "Contraindicated drug interaction detected. Set acknowledge_ddi=true to proceed.",
        }

    data = {
        "prescription_id": prescription_id,
        "patient_id": patient_id,
        "drug_name": rx["drug_name"],
        "quantity_dispensed": payload.quantity_dispensed,
        "unit": payload.unit or rx.get("unit", "tablet"),
        "unit_cost": payload.unit_cost,
        "batch_number": payload.batch_number,
        "expiry_date": payload.expiry_date,
        "counselling_given": payload.counselling_given or bool(payload.counselled),
        "dispensed_by": user.get("sub") or "system",
        "notes": payload.notes or payload.counselling_notes,
    }

    try:
        disp_result = db.table(TABLE_DISPENSING).insert(data).execute()
    except Exception as exc:
        logger.error("Dispensing insert failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to record dispensing")

    # Determine new prescription status
    dispensed_qty = payload.quantity_dispensed
    ordered_qty   = float(rx.get("quantity") or 1)
    new_status = "dispensed" if dispensed_qty >= ordered_qty else "partially_dispensed"
    db.table(TABLE_PRESCRIPTIONS).update({
        "status": new_status,
        "dispensed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }).eq("id", prescription_id).execute()

    # Deduct from inventory if stock record exists
    inv_row = db.table(TABLE_DRUG_INVENTORY).select("id,stock_quantity").ilike("drug_name", f"%{rx['drug_name']}%").limit(1).execute()
    if inv_row.data:
        inv = inv_row.data[0]
        new_stock = max(0, float(inv.get("stock_quantity") or 0) - dispensed_qty)
        db.table(TABLE_DRUG_INVENTORY).update({"stock_quantity": new_stock}).eq("id", inv["id"]).execute()

    disp = disp_result.data[0] if disp_result.data else data
    audit_event(
        "prescription_dispensed",
        {"qty": dispensed_qty, "status": new_status},
        actor_id=user.get("sub"),
        subject_type="prescription",
        subject_id=str(prescription_id),
    )

    # Auto-create MAR entry when drug is dispensed
    try:
        db.table(TABLE_MAR_ENTRIES).insert({
            "encounter_id": rx.get("encounter_id"),
            "patient_id": patient_id,
            "prescription_id": prescription_id,
            "drug_name": rx["drug_name"],
            "dose": rx.get("dosage") or rx.get("dose"),
            "route": rx.get("route"),
            "status": "administered",
            "administered_by": user.get("sub") or "system",
        }).execute()
    except Exception:
        pass  # MAR creation is best-effort; dispense already succeeded

    return {
        "ok": True,
        "dispensing": disp,
        "prescription_status": new_status,
        "ddi_warnings": ddi_warnings,
    }


@router.post("/prescriptions/{prescription_id}/cancel")
async def cancel_prescription(prescription_id: int, user=Depends(verify_jwt)):
    rx = _get_prescription(prescription_id)
    if rx["status"] in ("dispensed", "cancelled"):
        raise HTTPException(status_code=409, detail=f"Cannot cancel prescription with status '{rx['status']}'")

    db.table(TABLE_PRESCRIPTIONS).update({"status": "cancelled"}).eq("id", prescription_id).execute()
    audit_event("prescription_cancelled", {}, actor_id=user.get("sub"), subject_type="prescription", subject_id=str(prescription_id))
    return {"ok": True, "prescription_id": prescription_id, "status": "cancelled"}


# ─── Medication Administration Record (MAR) ──────────────────────────────────

class MARAdminRequest(BaseModel):
    dose_given: Optional[str] = None
    route: Optional[str] = None
    site: Optional[str] = None           # injection site, e.g. "left deltoid"
    admin_time: Optional[str] = None     # ISO datetime; defaults to now()
    status: str = "given"                # given|refused|held|not_available|omitted
    omission_reason: Optional[str] = None
    witnessed_by_id: Optional[int] = None
    notes: Optional[str] = None

    model_config = {"extra": "ignore"}


@router.post("/prescriptions/{prescription_id}/administer", status_code=201,
             dependencies=[Depends(require_role("nurse", "doctor", "pharmacist", "admin"))])
async def administer_medication(
    prescription_id: int,
    payload: MARAdminRequest,
    user=Depends(verify_jwt),
):
    """Record a medication administration event on the MAR (Blueprint Ch 3.5)."""
    if payload.status not in MEDICATION_ADMIN_STATUS:
        raise HTTPException(status_code=422, detail=f"status must be one of {MEDICATION_ADMIN_STATUS}")

    rx = _get_prescription(prescription_id)
    if rx["status"] not in ("dispensed", "partially_dispensed"):
        raise HTTPException(
            status_code=409,
            detail=f"Cannot administer: prescription status is '{rx['status']}' (must be dispensed).",
        )

    data: dict = {
        "prescription_id": prescription_id,
        "patient_id": rx["patient_id"],
        "encounter_id": rx.get("encounter_id"),
        "drug_name": rx["drug_name"],
        "dose_given": payload.dose_given or rx.get("dosage"),
        "route": payload.route or rx.get("route"),
        "site": payload.site,
        "status": payload.status,
        "omission_reason": payload.omission_reason,
        "administered_by": user.get("sub") or "system",
        "notes": payload.notes,
    }
    if payload.witnessed_by_id:
        data["witnessed_by_id"] = payload.witnessed_by_id
    if payload.admin_time:
        data["admin_time"] = payload.admin_time

    try:
        result = db.table(TABLE_MEDICATION_ADMIN).insert(data).execute()
    except Exception as exc:
        logger.error("MAR administration insert failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to record administration")

    mar_row = (result.data or [data])[0]

    if payload.status == "given":
        db.table(TABLE_PRESCRIPTIONS).update({"status": "administered"}).eq("id", prescription_id).execute()

    audit_event(
        "medication_administered",
        {"drug": rx["drug_name"], "status": payload.status, "route": data.get("route")},
        actor_id=user.get("sub"),
        subject_type="prescription",
        subject_id=str(prescription_id),
    )
    emit_clinical_event(
        event_type="MEDICATION_ADMINISTERED",
        encounter_id=rx.get("encounter_id"),
        patient_id=rx.get("patient_id"),
        entity_type="prescription",
        entity_id=prescription_id,
        performed_by=user.get("sub"),
        event_data={"drug_name": rx["drug_name"], "status": payload.status, "route": data.get("route")},
    )

    return {"ok": True, "mar_entry": mar_row}


@router.get("/prescriptions/{prescription_id}/mar")
async def get_prescription_mar(prescription_id: int, user=Depends(verify_jwt)):
    """Return the full administration history for a single prescription."""
    _get_prescription(prescription_id)   # 404 guard
    result = (
        db.table(TABLE_MEDICATION_ADMIN)
        .select("*")
        .eq("prescription_id", prescription_id)
        .order("admin_time", desc=True)
        .execute()
    )
    return {"prescription_id": prescription_id, "mar_entries": result.data, "count": len(result.data)}


@router.get("/encounters/{encounter_id}/mar")
async def get_encounter_mar(encounter_id: int, user=Depends(verify_jwt)):
    """Full MAR for all prescriptions in an encounter (nursing ward view)."""
    rxs = (
        db.table(TABLE_PRESCRIPTIONS)
        .select("id,drug_name,dosage,route,frequency,status,prescribed_by,prescribed_at")
        .eq("encounter_id", encounter_id)
        .execute()
    )
    rx_ids = [r["id"] for r in (rxs.data or [])]
    mar_rows: list = []
    if rx_ids:
        mar_result = (
            db.table(TABLE_MEDICATION_ADMIN)
            .select("*")
            .in_("prescription_id", rx_ids)
            .order("admin_time", desc=True)
            .execute()
        )
        mar_rows = mar_result.data or []

    mar_by_rx: dict = {}
    for row in mar_rows:
        rx_id = row.get("prescription_id")
        mar_by_rx.setdefault(rx_id, []).append(row)

    mar_sheet = [
        {**rx, "administrations": mar_by_rx.get(rx["id"], [])}
        for rx in (rxs.data or [])
    ]
    return {"encounter_id": encounter_id, "mar": mar_sheet, "total_prescriptions": len(mar_sheet)}


# ─── Patient Allergies ────────────────────────────────────────────────────────

class AllergyCreate(BaseModel):
    allergen: str = Field(..., min_length=1, max_length=200)
    severity: str = "moderate"   # mild | moderate | severe | unknown
    reaction: Optional[str] = None

    model_config = {"extra": "ignore"}


@router.get("/allergies/{patient_id}")
async def list_allergies(patient_id: int, user=Depends(verify_jwt)):
    """List documented allergies for a patient."""
    result = db.table(TABLE_ALLERGIES).select("*").eq("patient_id", patient_id).eq("status", "active").order("created_at", desc=True).execute()
    return {"allergies": result.data or [], "count": len(result.data or [])}


@router.post("/allergies/{patient_id}", status_code=201)
async def add_allergy(patient_id: int, payload: AllergyCreate, user=Depends(verify_jwt)):
    """Record a new allergy for a patient."""
    data = {
        "patient_id": patient_id,
        "allergen": payload.allergen,
        "severity": payload.severity,
        "reaction": payload.reaction,
        "recorded_by": user.get("sub") or "system",
        "status": "active",
    }
    try:
        result = db.table(TABLE_ALLERGIES).insert(data).execute()
    except Exception as exc:
        logger.error("Allergy insert failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to save allergy")
    allergy = (result.data or [data])[0]
    audit_event("allergy_recorded", {"allergen": payload.allergen}, actor_id=user.get("sub"), subject_type="allergy", subject_id=str(allergy.get("id") or ""))
    return {"ok": True, "allergy": allergy}


@router.delete("/allergies/record/{allergy_id}")
async def remove_allergy(allergy_id: int, user=Depends(verify_jwt)):
    r = db.table(TABLE_ALLERGIES).select("id").eq("id", allergy_id).execute()
    if not r.data:
        raise HTTPException(status_code=404, detail=f"Allergy record {allergy_id} not found")
    db.table(TABLE_ALLERGIES).update({"status": "resolved"}).eq("id", allergy_id).execute()
    audit_event("allergy_removed", {}, actor_id=user.get("sub"), subject_type="allergy", subject_id=str(allergy_id))
    return {"ok": True, "allergy_id": allergy_id}


# ─── Drug Inventory ───────────────────────────────────────────────────────────

class DrugInventoryCreate(BaseModel):
    drug_name: str = Field(..., min_length=1, max_length=200)
    drug_code: Optional[str] = None
    generic_name: Optional[str] = None
    formulation: Optional[str] = None        # tablet | capsule | syrup | injection | etc.
    strength: Optional[str] = None
    unit: str = "tablet"
    stock_quantity: float = Field(0.0, ge=0)
    reorder_level: float = Field(0.0, ge=0)
    unit_cost: float = Field(0.0, ge=0)
    supplier: Optional[str] = None
    location: Optional[str] = None
    expiry_date: Optional[str] = None
    batch_number: Optional[str] = None
    notes: Optional[str] = None

    model_config = {"extra": "ignore"}


class StockAdjustRequest(BaseModel):
    adjustment: float      # positive = stock in, negative = stock out
    reason: str = "manual_adjustment"
    notes: Optional[str] = None


def _tag_stock_status(item: dict) -> dict:
    """Derive an is_out_of_stock flag at read time (zero quantity or already
    expired) rather than storing it — the underlying numbers are the source
    of truth, this is just a UI signal to prompt a manual correction via
    POST /inventory/{id}/adjust."""
    qty = float(item.get("stock_quantity") or 0)
    expiry = item.get("expiry_date")
    is_expired = False
    if expiry:
        expiry_date = expiry if isinstance(expiry, dt.date) else dt.date.fromisoformat(str(expiry)[:10])
        is_expired = expiry_date < dt.date.today()
    return {**item, "is_out_of_stock": qty <= 0 or is_expired, "is_expired": is_expired}


@router.get("/inventory")
async def list_inventory(
    drug_name: Optional[str] = Query(None),
    low_stock: bool = Query(False),
    limit: int = Query(100, ge=1, le=500),
    user=Depends(verify_jwt),
):
    """List drug inventory, optionally filtered by name or low-stock flag."""
    query = db.table(TABLE_DRUG_INVENTORY).select("*").order("drug_name").limit(limit)
    if drug_name:
        query = query.ilike("drug_name", f"%{drug_name.strip()}%")
    result = query.execute()
    items = [_tag_stock_status(i) for i in (result.data or [])]
    if low_stock:
        items = [i for i in items if float(i.get("stock_quantity") or 0) <= float(i.get("reorder_level") or 0)]
    return {"inventory": items, "count": len(items)}


@router.get("/inventory/expiring")
async def list_expiring_inventory(
    within_days: int = Query(30, ge=1, le=365),
    user=Depends(verify_jwt),
):
    """Drugs expiring within N days (not yet expired)."""
    today = dt.date.today()
    cutoff = (today + dt.timedelta(days=within_days)).isoformat()
    result = (
        db.table(TABLE_DRUG_INVENTORY)
        .select("*")
        .gte("expiry_date", today.isoformat())
        .lte("expiry_date", cutoff)
        .order("expiry_date")
        .execute()
    )
    items = [_tag_stock_status(i) for i in (result.data or [])]
    return {"inventory": items, "count": len(items), "within_days": within_days}


@router.get("/inventory/expired")
async def list_expired_inventory(user=Depends(verify_jwt)):
    """Drugs whose expiry_date has already passed."""
    today = dt.date.today().isoformat()
    result = (
        db.table(TABLE_DRUG_INVENTORY)
        .select("*")
        .lt("expiry_date", today)
        .order("expiry_date", desc=True)
        .execute()
    )
    items = [_tag_stock_status(i) for i in (result.data or [])]
    return {"inventory": items, "count": len(items)}


@router.post("/inventory", status_code=201)
async def create_inventory_item(payload: DrugInventoryCreate, user=Depends(verify_jwt)):
    """Add a new drug to inventory."""
    data = payload.model_dump(exclude_none=True)
    data["created_by"] = user.get("sub") or "system"
    try:
        result = db.table(TABLE_DRUG_INVENTORY).insert(data).execute()
    except Exception as exc:
        logger.error("Inventory insert failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to add inventory item")
    item = (result.data or [data])[0]
    audit_event("drug_inventory_added", {"drug": payload.drug_name}, actor_id=user.get("sub"), subject_type="drug_inventory", subject_id=str(item.get("id") or ""))
    return {"ok": True, "item": item}


@router.patch("/inventory/{item_id}")
async def update_inventory_item(item_id: int, payload: DrugInventoryCreate, user=Depends(verify_jwt)):
    r = db.table(TABLE_DRUG_INVENTORY).select("id").eq("id", item_id).execute()
    if not r.data:
        raise HTTPException(status_code=404, detail=f"Inventory item {item_id} not found")
    updates = payload.model_dump(exclude_none=True)
    db.table(TABLE_DRUG_INVENTORY).update(updates).eq("id", item_id).execute()
    return {"ok": True, "item_id": item_id}


@router.post("/inventory/{item_id}/adjust")
async def adjust_stock(item_id: int, payload: StockAdjustRequest, user=Depends(verify_jwt)):
    """Adjust stock quantity (positive = receipt, negative = issue/loss)."""
    r = db.table(TABLE_DRUG_INVENTORY).select("id,stock_quantity,drug_name").eq("id", item_id).execute()
    if not r.data:
        raise HTTPException(status_code=404, detail=f"Inventory item {item_id} not found")
    item = r.data[0]
    current = float(item.get("stock_quantity") or 0)
    new_qty = max(0, current + payload.adjustment)
    db.table(TABLE_DRUG_INVENTORY).update({"stock_quantity": new_qty}).eq("id", item_id).execute()
    audit_event(
        "stock_adjusted",
        {"drug": item.get("drug_name"), "adjustment": payload.adjustment, "reason": payload.reason},
        actor_id=user.get("sub"),
        subject_type="drug_inventory",
        subject_id=str(item_id),
    )
    return {"ok": True, "item_id": item_id, "previous_qty": current, "new_qty": new_qty}


# ─── Sales on Return (SOR) ─────────────────────────────────────────────────────

class SalesReturnCreate(BaseModel):
    dispensing_id: int
    quantity_returned: float = Field(..., gt=0)
    reason: Optional[str] = None
    restock: bool = False

    model_config = {"extra": "ignore"}


@router.post("/returns", status_code=201)
async def create_sales_return(payload: SalesReturnCreate, user=Depends(verify_jwt)):
    """Record a drug return. If restock is set, the quantity is added back
    to the matching royan_drug_inventory row (matched by drug_name)."""
    dispensing = db.table(TABLE_DISPENSING).select("id,patient_id,drug_name,quantity_dispensed").eq("id", payload.dispensing_id).execute()
    if not dispensing.data:
        raise HTTPException(status_code=404, detail=f"Dispensing record {payload.dispensing_id} not found")
    disp = dispensing.data[0]
    if payload.quantity_returned > float(disp.get("quantity_dispensed") or 0):
        raise HTTPException(status_code=422, detail="quantity_returned cannot exceed the quantity originally dispensed")

    data = {
        "dispensing_id": payload.dispensing_id,
        "patient_id": disp["patient_id"],
        "quantity_returned": payload.quantity_returned,
        "reason": payload.reason,
        "restocked": payload.restock,
        "processed_by": user.get("sub") or "system",
    }
    try:
        result = db.table(TABLE_SALES_RETURNS).insert(data).execute()
    except Exception as exc:
        logger.error("Sales return insert failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to record sales return")

    if payload.restock:
        inv = db.table(TABLE_DRUG_INVENTORY).select("id,stock_quantity").ilike("drug_name", disp["drug_name"]).limit(1).execute()
        if inv.data:
            item = inv.data[0]
            new_qty = float(item.get("stock_quantity") or 0) + payload.quantity_returned
            db.table(TABLE_DRUG_INVENTORY).update({"stock_quantity": new_qty}).eq("id", item["id"]).execute()

    ret = result.data[0] if result.data else data
    audit_event(
        "sales_return_recorded",
        {"dispensing_id": payload.dispensing_id, "quantity": payload.quantity_returned, "restocked": payload.restock},
        actor_id=user.get("sub"),
        subject_type="sales_return",
        subject_id=str(ret.get("id") or ""),
    )
    return {"ok": True, "return": ret}


@router.get("/returns")
async def list_sales_returns(
    patient_id: Optional[int] = Query(None),
    dispensing_id: Optional[int] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    user=Depends(verify_jwt),
):
    query = db.table(TABLE_SALES_RETURNS).select("*").order("processed_at", desc=True).limit(limit)
    if patient_id:
        query = query.eq("patient_id", patient_id)
    if dispensing_id:
        query = query.eq("dispensing_id", dispensing_id)
    result = query.execute()
    return {"returns": result.data or [], "count": len(result.data or [])}


# ─── Drug-Collection Signature Capture ─────────────────────────────────────────
# Confirms a patient actually collected their prescribed drugs. Assumes the
# signature-pad tablet's own companion app handles the hardware/SDK and just
# POSTs the resulting image here — same file-storage pattern as lab.py's
# report-upload endpoint.

SIGNATURES_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "signatures")
ALLOWED_SIGNATURE_TYPES = {"image/png", "image/jpeg", "image/webp"}


@router.post("/dispensing/{dispensing_id}/signature")
async def upload_dispensing_signature(
    dispensing_id: int,
    file: UploadFile = File(...),
    user=Depends(verify_jwt),
):
    """Attach a captured signature image to a dispensing record."""
    dispensing = db.table(TABLE_DISPENSING).select("id").eq("id", dispensing_id).execute()
    if not dispensing.data:
        raise HTTPException(status_code=404, detail=f"Dispensing record {dispensing_id} not found")

    if file.content_type not in ALLOWED_SIGNATURE_TYPES:
        raise HTTPException(status_code=422, detail=f"File type '{file.content_type}' not allowed. Use PNG/JPEG/WEBP.")

    contents = await file.read()
    if len(contents) > 5 * 1024 * 1024:  # 5 MB limit — a signature image is small
        raise HTTPException(status_code=413, detail="File too large (max 5 MB)")

    os.makedirs(SIGNATURES_DIR, exist_ok=True)
    safe_name = f"{dispensing_id}_{uuid.uuid4().hex[:8]}_{file.filename or 'signature'}"
    safe_name = safe_name.replace("/", "_").replace("\\", "_")
    storage_path = os.path.join(SIGNATURES_DIR, safe_name)
    with open(storage_path, "wb") as fh:
        fh.write(contents)

    signature_url = f"/pharmacy/signatures/{safe_name}"
    db.table(TABLE_DISPENSING).update({"signature_url": signature_url}).eq("id", dispensing_id).execute()

    audit_event(
        "dispensing_signature_captured",
        {"dispensing_id": dispensing_id},
        actor_id=user.get("sub"),
        subject_type="dispensing",
        subject_id=str(dispensing_id),
    )
    return {"ok": True, "signature_url": signature_url}


@router.get("/signatures/{filename}")
async def serve_signature(filename: str, user=Depends(verify_jwt)):
    """Serve a stored signature image to authenticated users."""
    safe_filename = os.path.basename(filename)
    file_path = os.path.join(SIGNATURES_DIR, safe_filename)
    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="Signature file not found")
    return FileResponse(file_path)


# ─── Ward Replenishment Requests ──────────────────────────────────────────────

class ReplenishmentRequest(BaseModel):
    ward: str = Field(..., min_length=1)
    drug_name: str = Field(..., min_length=1)
    quantity_requested: float = Field(..., gt=0)
    unit: str = "tablet"
    urgency: str = "routine"   # routine | urgent | stat
    notes: Optional[str] = None

    model_config = {"extra": "ignore"}


@router.post("/replenishment-request", status_code=201)
async def create_replenishment_request(payload: ReplenishmentRequest, user=Depends(verify_jwt)):
    """Submit a ward drug replenishment request."""
    data = payload.model_dump(exclude_none=True)
    data["requested_by"] = user.get("sub") or "system"
    data["status"] = "pending"
    try:
        result = db.table(TABLE_REPLENISHMENT_REQUESTS).insert(data).execute()
    except Exception as exc:
        logger.error("Replenishment request failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to submit replenishment request")
    req = (result.data or [data])[0]
    audit_event("replenishment_requested", {"ward": payload.ward, "drug": payload.drug_name}, actor_id=user.get("sub"), subject_type="replenishment_request", subject_id=str(req.get("id") or ""))
    return {"ok": True, "request": req}


@router.get("/replenishment-requests")
async def list_replenishment_requests(
    ward: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    user=Depends(verify_jwt),
):
    """List ward replenishment requests."""
    query = db.table(TABLE_REPLENISHMENT_REQUESTS).select("*").order("created_at", desc=True).limit(limit)
    if ward:
        query = query.eq("ward", ward)
    if status:
        query = query.eq("status", status)
    result = query.execute()
    return {"requests": result.data or [], "count": len(result.data or [])}


@router.patch("/replenishment-requests/{req_id}/status")
async def update_replenishment_status(req_id: int, status: str = Query(...), user=Depends(verify_jwt)):
    """Approve, fulfil, or reject a replenishment request (pharmacy staff)."""
    ALLOWED = {"pending", "approved", "fulfilled", "rejected"}
    if status not in ALLOWED:
        raise HTTPException(status_code=422, detail=f"status must be one of {ALLOWED}")
    r = db.table(TABLE_REPLENISHMENT_REQUESTS).select("id").eq("id", req_id).execute()
    if not r.data:
        raise HTTPException(status_code=404, detail=f"Request {req_id} not found")
    db.table(TABLE_REPLENISHMENT_REQUESTS).update({"status": status, "actioned_by": user.get("sub")}).eq("id", req_id).execute()
    audit_event("replenishment_status_updated", {"status": status}, actor_id=user.get("sub"), subject_type="replenishment_request", subject_id=str(req_id))
    return {"ok": True, "req_id": req_id, "status": status}
