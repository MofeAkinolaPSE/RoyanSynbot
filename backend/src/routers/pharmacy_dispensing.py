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

import asyncio
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
from src.services.realtime import realtime_hub
from src.services.clinical_shared import get_patient_allergies
from src.services import pharmacy_inventory_service as inv
from src.constants import (
    PRESCRIPTION_ROUTES_ALLOWED, PRESCRIPTION_STATUS_ALLOWED,
    TABLE_PRESCRIPTIONS, TABLE_DISPENSING,
    TABLE_DRUG_INVENTORY, TABLE_DRUG_INTERACTIONS, TABLE_ALLERGIES,
    TABLE_MEDICATION_ADMIN, MEDICATION_ADMIN_STATUS,
    TABLE_SALES_RETURNS, TABLE_PATIENTS,
)
# TABLE_MAR_ENTRIES import removed — dispense_prescription no longer writes to
# it (that write was clinically wrong; see the removed auto-insert below).
# nursing.py continues to own royan_mar_entries exclusively.

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
    formulary_id: Optional[int] = None  # optional FK to royan_drug_formulary once formulary data exists
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
    batch_id: Optional[int] = None      # explicit batch pick (FEFO used when omitted)
    batch_number: Optional[str] = None  # free-text fallback for uncatalogued drugs
    expiry_date: Optional[str] = None   # ISO date string, free-text fallback
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
    emit_clinical_event(
        event_type="PRESCRIPTION_ISSUED",
        encounter_id=payload.encounter_id,
        patient_id=payload.patient_id,
        entity_type="prescription", entity_id=rx.get("id"),
        performed_by=user.get("sub"),
        event_data={"drug_name": payload.drug_name, "dosage": data.get("dosage"), "route": payload.route},
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
    rxs: list = list(result.data or [])

    # Batch-enrich each prescription with basic patient demographics (1 extra query for all)
    if rxs:
        try:
            pid_set = list({r["patient_id"] for r in rxs if r.get("patient_id") is not None})
            if pid_set:
                pt_rows = db.table(TABLE_PATIENTS).select("id,mrn,first_name,last_name").in_("id", pid_set).execute()
                pt_map = {p["id"]: p for p in (pt_rows.data or [])}
                for r in rxs:
                    p = pt_map.get(r.get("patient_id"))
                    if p:
                        fn = (p.get("first_name") or "").strip()
                        ln = (p.get("last_name") or "").strip()
                        r["patient_name"] = f"{fn} {ln}".strip() or None
                        r["patient_mrn"] = p.get("mrn")
        except Exception as exc:
            logger.warning("prescription patient enrichment failed: %s", exc)

    return {"prescriptions": rxs, "count": len(rxs)}


@router.get("/stats")
async def pharmacy_stats(user=Depends(verify_jwt)):
    """Aggregate counts for the Dispensing KPI cards — server-computed so
    they're never capped by whatever status filter/pagination the worklist
    happens to have active. Inventory-specific counts (low stock, expiring,
    expired) now live on GET /pharmacy/inventory/summary, correctly scoped
    to live-stock batches only — the old fields here read the now-legacy
    royan_drug_inventory table (which counted qty=0 rows as "low stock" too)."""
    rx_rows = db.table(TABLE_PRESCRIPTIONS).select("status").is_("external_source", None).execute().data or []
    counts = {s: sum(1 for r in rx_rows if r.get("status") == s) for s in PRESCRIPTION_STATUSES}

    return {
        **counts,
        "active": counts["pending"] + counts["partially_dispensed"],
        "total": len(rx_rows),
    }


@router.get("/prescriptions/{prescription_id}")
async def get_prescription(prescription_id: int, user=Depends(verify_jwt)):
    """Enriched detail — patient info, dispensing history, MAR history,
    returns, and cumulative dispensed/remaining quantity. This is the
    PharmacyWorkspacePanel's single self-fetch source."""
    rx = _get_prescription(prescription_id)

    disp_rows = db.table(TABLE_DISPENSING).select("*").eq("prescription_id", prescription_id) \
        .order("dispensed_at", desc=True).execute().data or []
    mar_rows = db.table(TABLE_MEDICATION_ADMIN).select("*").eq("prescription_id", prescription_id) \
        .order("admin_time", desc=True).execute().data or []

    returns: list = []
    if disp_rows:
        disp_ids = [r["id"] for r in disp_rows]
        returns = db.table(TABLE_SALES_RETURNS).select("*").in_("dispensing_id", disp_ids) \
            .order("processed_at", desc=True).execute().data or []

    pt = db.table(TABLE_PATIENTS).select("id,mrn,first_name,last_name,gender,date_of_birth").eq("id", rx["patient_id"]).execute()
    if pt.data:
        p = pt.data[0]
        fn = (p.get("first_name") or "").strip()
        ln = (p.get("last_name") or "").strip()
        rx = {
            **rx,
            "patient_name": f"{fn} {ln}".strip() or None,
            "patient_mrn": p.get("mrn"),
            "patient_gender": p.get("gender"),
            "patient_dob": p.get("date_of_birth"),
        }

    total_dispensed = sum(float(r.get("quantity_dispensed") or 0) for r in disp_rows)
    ordered_qty = float(rx.get("quantity") or 1)

    resolved_formulary_id = inv.resolve_formulary_id(rx.get("drug_name"), rx.get("formulary_id"))
    available_batches = inv.list_live_batches(resolved_formulary_id) if resolved_formulary_id else []

    return {
        "prescription": rx,
        "dispensing_records": disp_rows,
        "mar_entries": mar_rows,
        "returns": returns,
        "total_dispensed": total_dispensed,
        "remaining_quantity": max(0.0, ordered_qty - total_dispensed),
        "resolved_formulary_id": resolved_formulary_id,
        "available_batches": available_batches,
    }


@router.post("/prescriptions/{prescription_id}/dispense")
async def dispense_prescription(prescription_id: int, payload: DispenseRequest, user=Depends(verify_jwt)):
    """Record dispensing of a prescription by a pharmacist."""
    rx = _get_prescription(prescription_id)

    if rx["status"] in ("cancelled", "returned"):
        raise HTTPException(status_code=409, detail=f"Prescription is '{rx['status']}'; cannot dispense")

    drug_name_lower = rx["drug_name"].lower()
    patient_id = rx["patient_id"]

    # ── Cumulative-quantity guard ────────────────────────────────────────────
    # The old check compared only this call's quantity against the full
    # ordered amount, never summing prior dispensing events — a prescription
    # could get stuck "partially_dispensed" forever, or be dispensed past
    # what was ordered, with no guard at all. Sum every prior dispensing row
    # for this prescription first.
    prior_disp = db.table(TABLE_DISPENSING).select("quantity_dispensed").eq("prescription_id", prescription_id).execute()
    already_dispensed = sum(float(r.get("quantity_dispensed") or 0) for r in (prior_disp.data or []))
    ordered_qty = float(rx.get("quantity") or 1)
    remaining = ordered_qty - already_dispensed
    if remaining <= 0:
        raise HTTPException(
            status_code=409,
            detail=f"Prescription is already fully dispensed ({already_dispensed}/{ordered_qty} {rx.get('unit')})",
        )
    if payload.quantity_dispensed > remaining:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Cannot dispense {payload.quantity_dispensed} {rx.get('unit')}; only {remaining} {rx.get('unit')} "
                f"remain on this prescription (already dispensed {already_dispensed}/{ordered_qty})."
            ),
        )

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

    # Determine new prescription status from the cumulative dispensed amount
    # (including this call), not just this call in isolation.
    dispensed_qty = payload.quantity_dispensed
    cumulative_dispensed = already_dispensed + dispensed_qty
    new_status = "dispensed" if cumulative_dispensed >= ordered_qty else "partially_dispensed"

    # FEFO batch deduction against the new catalog/batch model. Falls back to
    # today's exact free-text/no-op behavior when the drug isn't catalogued
    # yet — zero regression for uncatalogued drugs. A dispense that spans
    # more than one batch writes one royan_dispensing row per batch touched
    # (audit-correct — a single row can't honestly represent two lots).
    resolved_formulary_id = inv.resolve_formulary_id(rx["drug_name"], rx.get("formulary_id"))
    disp_rows_written: list = []

    if resolved_formulary_id:
        taken = inv.apply_fefo_deduction(resolved_formulary_id, dispensed_qty, batch_id=payload.batch_id)
        if taken:
            for t in taken:
                row_data = {
                    "prescription_id": prescription_id,
                    "patient_id": patient_id,
                    "drug_name": rx["drug_name"],
                    "quantity_dispensed": t["quantity_taken"],
                    "unit": payload.unit or rx.get("unit", "tablet"),
                    "unit_cost": payload.unit_cost,
                    "batch_number": t.get("batch_number"),
                    "expiry_date": t.get("expiry_date"),
                    "formulary_id": resolved_formulary_id,
                    "batch_id": t.get("batch_id"),
                    "counselling_given": payload.counselling_given or bool(payload.counselled),
                    "dispensed_by": user.get("sub") or "system",
                    "notes": payload.notes or payload.counselling_notes,
                }
                result = db.table(TABLE_DISPENSING).insert(row_data).execute()
                disp_rows_written.append(result.data[0] if result.data else row_data)

    if not disp_rows_written:
        # No catalog/batch match (or nothing available in any live batch) —
        # record the dispense using the caller-supplied free-text batch info,
        # exactly like the old flat-inventory behavior.
        row_data = {
            "prescription_id": prescription_id,
            "patient_id": patient_id,
            "drug_name": rx["drug_name"],
            "quantity_dispensed": dispensed_qty,
            "unit": payload.unit or rx.get("unit", "tablet"),
            "unit_cost": payload.unit_cost,
            "batch_number": payload.batch_number,
            "expiry_date": payload.expiry_date,
            "formulary_id": resolved_formulary_id,
            "counselling_given": payload.counselling_given or bool(payload.counselled),
            "dispensed_by": user.get("sub") or "system",
            "notes": payload.notes or payload.counselling_notes,
        }
        result = db.table(TABLE_DISPENSING).insert(row_data).execute()
        disp_rows_written.append(result.data[0] if result.data else row_data)

    db.table(TABLE_PRESCRIPTIONS).update({
        "status": new_status,
        "dispensed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }).eq("id", prescription_id).execute()

    disp = disp_rows_written[0]
    audit_event(
        "prescription_dispensed",
        {"qty": dispensed_qty, "cumulative": cumulative_dispensed, "status": new_status, "batches_touched": len(disp_rows_written)},
        actor_id=user.get("sub"),
        subject_type="prescription",
        subject_id=str(prescription_id),
    )

    # NOTE: this used to also auto-insert into royan_mar_entries tagged
    # status="administered" — removed. Dispensing a drug is not the same
    # clinical event as a nurse administering it, and nothing ever read that
    # write back (GET .../mar reads only royan_medication_admin). See
    # administer_medication for the real administration record.

    emit_clinical_event(
        event_type="MEDICATION_DISPENSED",
        encounter_id=rx.get("encounter_id"),
        patient_id=patient_id,
        entity_type="prescription", entity_id=prescription_id,
        performed_by=user.get("sub"),
        event_data={"drug_name": rx["drug_name"], "qty": dispensed_qty, "status": new_status},
    )
    if rx.get("encounter_id"):
        asyncio.create_task(realtime_hub.broadcast("encounter_updates", {
            "event": "prescription_dispensed",
            "encounter_id": rx.get("encounter_id"),
            "prescription_id": prescription_id,
            "drug_name": rx["drug_name"],
            "status": new_status,
        }))

    return {
        "ok": True,
        "dispensing": disp,
        "dispensing_records": disp_rows_written,
        "prescription_status": new_status,
        "remaining_quantity": max(0.0, ordered_qty - cumulative_dispensed),
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
    witnessed_by: Optional[str] = None   # free text; royan_medication_admin.witnessed_by_id (uuid) stays unpopulated, matching administered_by_id's existing pattern
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
        "witnessed_by": payload.witnessed_by,
        "notes": payload.notes,
    }
    if payload.admin_time:
        data["admin_time"] = payload.admin_time

    try:
        result = db.table(TABLE_MEDICATION_ADMIN).insert(data).execute()
    except Exception as exc:
        logger.error("MAR administration insert failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to record administration")

    mar_row = (result.data or [data])[0]

    # NOTE: royan_prescriptions.status is intentionally NOT advanced here.
    # It used to be set to "administered" — a value outside both
    # PRESCRIPTION_STATUS_ALLOWED and the table's own CHECK constraint,
    # so this crashed on every real call. A prescription can legitimately
    # be administered many times (e.g. a 5-day BD course), so a single
    # terminal order-level status can't model "administered" any more than
    # Lab/Radiology's verify step could be a new order-level status for a
    # result/report that might later be amended — royan_medication_admin
    # row existence is already the correct source of truth for "was this
    # dose given."

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


@router.get("/administration-queue")
async def administration_queue(
    encounter_id: Optional[int] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    user=Depends(verify_jwt),
):
    """'First dose never given' worklist for nurses. This schema has no
    scheduled-dose/eMAR-timing concept, so this can only flag dispensed
    prescriptions with zero royan_medication_admin rows yet — a prescription
    already given its first dose but due for a later one will not reappear
    here even though clinically it should."""
    query = (
        db.table(TABLE_PRESCRIPTIONS)
        .select("id,encounter_id,patient_id,drug_name,dosage,route,frequency,status,dispensed_at")
        .in_("status", ["dispensed", "partially_dispensed"])
        .is_("external_source", None)
        .order("dispensed_at", desc=True)
        .limit(limit)
    )
    if encounter_id:
        query = query.eq("encounter_id", encounter_id)
    rxs = query.execute().data or []
    if not rxs:
        return {"queue": [], "count": 0}

    rx_ids = [r["id"] for r in rxs]
    administered_ids = {
        r["prescription_id"] for r in
        (db.table(TABLE_MEDICATION_ADMIN).select("prescription_id").in_("prescription_id", rx_ids).execute().data or [])
    }
    pending = [r for r in rxs if r["id"] not in administered_ids]

    if pending:
        try:
            pid_set = list({r["patient_id"] for r in pending if r.get("patient_id") is not None})
            pt_map = {p["id"]: p for p in (db.table(TABLE_PATIENTS).select("id,mrn,first_name,last_name").in_("id", pid_set).execute().data or [])}
            for r in pending:
                p = pt_map.get(r.get("patient_id"))
                if p:
                    fn = (p.get("first_name") or "").strip()
                    ln = (p.get("last_name") or "").strip()
                    r["patient_name"] = f"{fn} {ln}".strip() or None
                    r["patient_mrn"] = p.get("mrn")
        except Exception as exc:
            logger.warning("administration queue patient enrichment failed: %s", exc)

    return {"queue": pending, "count": len(pending)}


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

    # Net against prior returns on this same dispensing record — the old
    # check only compared against the original quantity_dispensed, so the
    # same record could be over-returned indefinitely across multiple calls.
    prior_returns = db.table(TABLE_SALES_RETURNS).select("quantity_returned").eq("dispensing_id", payload.dispensing_id).execute()
    already_returned = sum(float(r.get("quantity_returned") or 0) for r in (prior_returns.data or []))
    returnable = float(disp.get("quantity_dispensed") or 0) - already_returned
    if payload.quantity_returned > returnable:
        raise HTTPException(
            status_code=422,
            detail=(
                f"quantity_returned cannot exceed the remaining returnable quantity ({returnable}); "
                f"{already_returned} of {disp.get('quantity_dispensed')} already returned"
            ),
        )

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
        # Substring match, matching dispense()'s own inventory lookup — was
        # previously an exact-match ilike, an inconsistency with no reason.
        inv = db.table(TABLE_DRUG_INVENTORY).select("id,stock_quantity").ilike("drug_name", f"%{disp['drug_name']}%").limit(1).execute()
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

# Ward Replenishment Requests moved to pharmacy_inventory.py — conceptually
# inventory, not dispensing, and now on real formulary_id/ward/urgency/unit
# columns instead of the old sku/notes-folding workaround.
