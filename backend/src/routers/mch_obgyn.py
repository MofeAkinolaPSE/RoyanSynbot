"""
MCH / OB-GYN Router — SynbotHealth / Royan Hospital
=====================================================
Antenatal care registration, visit records, partograph, delivery,
newborn assessment, and immunisation scheduling.
VistA Reference: Women's Health / Obstetrics module.

Endpoints:
  POST   /mch/anc                                  – Register ANC patient
  GET    /mch/anc                                  – List ANC registrations
  GET    /mch/anc/{anc_id}                         – ANC record detail
  PATCH  /mch/anc/{anc_id}                         – Update ANC record

  POST   /mch/anc/{anc_id}/visits                  – Log ANC visit
  GET    /mch/anc/{anc_id}/visits                  – List visits for ANC record

  POST   /mch/anc/{anc_id}/partograph              – Record partograph entry
  GET    /mch/anc/{anc_id}/partograph              – Get partograph entries

  POST   /mch/anc/{anc_id}/delivery                – Record delivery
  GET    /mch/anc/{anc_id}/delivery                – Get delivery record

  POST   /mch/delivery/{delivery_id}/newborn       – Newborn assessment
  GET    /mch/delivery/{delivery_id}/newborn       – Get newborn assessments

  POST   /mch/patients/{patient_id}/immunisation   – Log immunisation dose
  GET    /mch/patients/{patient_id}/immunisation   – Immunisation history
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.db import db, audit_event
from src.middleware import verify_jwt
from src.constants import (
    TABLE_ANC_RECORDS,
    TABLE_ANC_VISITS,
    TABLE_PARTOGRAPH,
    TABLE_DELIVERY_RECORDS,
    TABLE_NEWBORN_ASSESSMENT,
    TABLE_IMMUNISATION,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/mch", tags=["MCH / OB-GYN"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class ANCCreate(BaseModel):
    patient_id: int
    encounter_id: Optional[int] = None
    gravida: Optional[int] = None          # number of pregnancies
    para: Optional[int] = None             # number of deliveries
    lmp: Optional[str] = None             # last menstrual period (ISO date)
    edd: Optional[str] = None             # expected delivery date (ISO date)
    gestational_age_weeks: Optional[int] = None
    blood_group: Optional[str] = None
    rhesus: Optional[str] = None           # positive | negative
    hiv_status: Optional[str] = None       # negative | positive | unknown
    hbsag: Optional[str] = None            # negative | positive | unknown
    syphilis: Optional[str] = None         # negative | positive | unknown
    malaria_prophylaxis: bool = False
    tetanus_toxoid: bool = False
    iron_folic_acid: bool = False
    risk_factors: Optional[str] = None
    referred_from: Optional[str] = None
    notes: Optional[str] = None

    model_config = {"extra": "ignore"}


class ANCUpdate(BaseModel):
    gestational_age_weeks: Optional[int] = None
    edd: Optional[str] = None
    blood_group: Optional[str] = None
    rhesus: Optional[str] = None
    hiv_status: Optional[str] = None
    hbsag: Optional[str] = None
    syphilis: Optional[str] = None
    malaria_prophylaxis: Optional[bool] = None
    tetanus_toxoid: Optional[bool] = None
    iron_folic_acid: Optional[bool] = None
    risk_factors: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[str] = None           # active | delivered | miscarriage | referred

    model_config = {"extra": "ignore"}


class ANCVisitCreate(BaseModel):
    visit_date: Optional[str] = None       # ISO date
    gestational_age_weeks: Optional[int] = None
    weight_kg: Optional[float] = None
    bp_systolic: Optional[int] = None
    bp_diastolic: Optional[int] = None
    fundal_height_cm: Optional[float] = None
    fetal_heart_rate: Optional[int] = None
    presentation: Optional[str] = None    # cephalic | breech | transverse
    engagement: Optional[str] = None      # engaged | not engaged
    oedema: bool = False
    proteinuria: bool = False
    haemoglobin: Optional[float] = None
    malaria_rapid_test: Optional[str] = None   # negative | positive
    drugs_given: Optional[str] = None
    counselling_given: Optional[str] = None
    next_visit_date: Optional[str] = None
    clinician_id: Optional[str] = None
    notes: Optional[str] = None

    model_config = {"extra": "ignore"}


class PartographEntry(BaseModel):
    recorded_at: Optional[str] = None     # ISO datetime (defaults to now)
    cervical_dilation_cm: Optional[float] = Field(None, ge=0, le=10)
    fetal_heart_rate: Optional[int] = None
    contractions_per_10min: Optional[int] = Field(None, ge=0, le=5)
    contraction_duration_sec: Optional[int] = None
    liquor: Optional[str] = None          # C=clear | M=meconium | B=blood | A=absent
    moulding: Optional[str] = None        # 0 | + | ++ | +++
    bp_systolic: Optional[int] = None
    bp_diastolic: Optional[int] = None
    pulse: Optional[int] = None
    temperature: Optional[float] = None
    urine_output_ml: Optional[int] = None
    oxytocin_units: Optional[float] = None
    analgesics_given: Optional[str] = None
    notes: Optional[str] = None

    model_config = {"extra": "ignore"}


class DeliveryRecord(BaseModel):
    delivery_date: Optional[str] = None    # ISO date
    delivery_time: Optional[str] = None    # HH:MM
    mode_of_delivery: str = "svd"          # svd | assisted | cs | breech
    indication: Optional[str] = None       # reason for cs/assisted
    duration_of_labour_hours: Optional[float] = None
    blood_loss_ml: Optional[float] = None
    placenta_complete: bool = True
    perineal_tear: Optional[str] = None    # none | 1st | 2nd | 3rd | 4th
    episiotomy: bool = False
    maternal_complications: Optional[str] = None
    anaesthesia_type: Optional[str] = None
    attending_clinician: Optional[str] = None
    notes: Optional[str] = None

    model_config = {"extra": "ignore"}


class NewbornAssessment(BaseModel):
    sex: Optional[str] = None              # male | female | indeterminate
    birth_weight_kg: Optional[float] = None
    length_cm: Optional[float] = None
    head_circumference_cm: Optional[float] = None
    apgar_1min: Optional[int] = Field(None, ge=0, le=10)
    apgar_5min: Optional[int] = Field(None, ge=0, le=10)
    apgar_10min: Optional[int] = Field(None, ge=0, le=10)
    gestational_age_at_birth: Optional[int] = None
    cry_at_birth: bool = True
    resuscitation_needed: bool = False
    resuscitation_type: Optional[str] = None
    congenital_anomalies: Optional[str] = None
    eye_prophylaxis: bool = False
    vitamin_k_given: bool = False
    bcg_given: bool = False
    opv0_given: bool = False
    hbv_given: bool = False
    breast_feeding_initiated: bool = True
    notes: Optional[str] = None

    model_config = {"extra": "ignore"}


class ImmunisationRecord(BaseModel):
    vaccine_name: str = Field(..., min_length=1)
    dose_number: Optional[int] = None      # 1 | 2 | 3 | booster
    date_given: Optional[str] = None       # ISO date
    batch_number: Optional[str] = None
    site: Optional[str] = None             # LTA | RTA | LDL | oral etc.
    administered_by: Optional[str] = None
    next_due_date: Optional[str] = None
    reaction: Optional[str] = None
    notes: Optional[str] = None

    model_config = {"extra": "ignore"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_anc(anc_id: int) -> dict:
    r = db.table(TABLE_ANC_RECORDS).select("*").eq("id", anc_id).execute()
    if not r.data:
        raise HTTPException(status_code=404, detail=f"ANC record {anc_id} not found")
    return r.data[0]


def _get_delivery(delivery_id: int) -> dict:
    r = db.table(TABLE_DELIVERY_RECORDS).select("*").eq("id", delivery_id).execute()
    if not r.data:
        raise HTTPException(status_code=404, detail=f"Delivery record {delivery_id} not found")
    return r.data[0]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# ANC Registration
# ---------------------------------------------------------------------------

@router.post("/anc", status_code=201)
async def register_anc(payload: ANCCreate, user=Depends(verify_jwt)):
    """Register a patient for antenatal care."""
    data = payload.model_dump(exclude_none=True)
    data["registered_by"] = user.get("sub") or "system"
    data["status"] = "active"

    try:
        result = db.table(TABLE_ANC_RECORDS).insert(data).execute()
    except Exception as exc:
        logger.error("ANC registration failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to register ANC patient")

    record = result.data[0] if result.data else data
    audit_event(
        "anc_registered",
        {"patient_id": payload.patient_id, "gravida": payload.gravida, "edd": payload.edd},
        actor_id=user.get("sub"),
        subject_type="anc_record",
        subject_id=str(record.get("id") or ""),
    )
    return {"ok": True, "record": record}


@router.get("/anc")
async def list_anc(
    patient_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    user=Depends(verify_jwt),
):
    """List ANC registrations with optional filters."""
    query = db.table(TABLE_ANC_RECORDS).select("*").order("created_at", desc=True).limit(limit)
    if patient_id:
        query = query.eq("patient_id", patient_id)
    if status:
        query = query.eq("status", status)
    result = query.execute()
    return {"records": result.data or [], "count": len(result.data or [])}


@router.get("/anc/{anc_id}")
async def get_anc(anc_id: int, user=Depends(verify_jwt)):
    return {"record": _get_anc(anc_id)}


@router.patch("/anc/{anc_id}")
async def update_anc(anc_id: int, payload: ANCUpdate, user=Depends(verify_jwt)):
    """Update an ANC record (risk factors, test results, status)."""
    _get_anc(anc_id)
    updates = payload.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=422, detail="No fields to update")
    db.table(TABLE_ANC_RECORDS).update(updates).eq("id", anc_id).execute()
    audit_event("anc_updated", updates, actor_id=user.get("sub"), subject_type="anc_record", subject_id=str(anc_id))
    return {"ok": True, "anc_id": anc_id}


# ---------------------------------------------------------------------------
# ANC Visits
# ---------------------------------------------------------------------------

@router.post("/anc/{anc_id}/visits", status_code=201)
async def log_visit(anc_id: int, payload: ANCVisitCreate, user=Depends(verify_jwt)):
    """Log an antenatal visit."""
    anc = _get_anc(anc_id)
    data = payload.model_dump(exclude_none=True)
    data["anc_id"]    = anc_id
    data["patient_id"] = anc["patient_id"]
    data["recorded_by"] = user.get("sub") or "system"
    if "visit_date" not in data:
        data["visit_date"] = _now()[:10]

    try:
        result = db.table(TABLE_ANC_VISITS).insert(data).execute()
    except Exception as exc:
        logger.error("ANC visit log failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to log ANC visit")

    visit = result.data[0] if result.data else data
    audit_event("anc_visit_logged", {"anc_id": anc_id}, actor_id=user.get("sub"), subject_type="anc_visit", subject_id=str(visit.get("id") or ""))
    return {"ok": True, "visit": visit}


@router.get("/anc/{anc_id}/visits")
async def list_visits(anc_id: int, user=Depends(verify_jwt)):
    _get_anc(anc_id)
    result = db.table(TABLE_ANC_VISITS).select("*").eq("anc_id", anc_id).order("visit_date", desc=True).execute()
    return {"visits": result.data or [], "count": len(result.data or [])}


# ---------------------------------------------------------------------------
# Partograph
# ---------------------------------------------------------------------------

@router.post("/anc/{anc_id}/partograph", status_code=201)
async def add_partograph_entry(anc_id: int, payload: PartographEntry, user=Depends(verify_jwt)):
    """Add a partograph data point during active labour."""
    anc = _get_anc(anc_id)
    data = payload.model_dump(exclude_none=True)
    data["anc_id"]     = anc_id
    data["patient_id"] = anc["patient_id"]
    data["recorded_by"] = user.get("sub") or "system"
    if "recorded_at" not in data:
        data["recorded_at"] = _now()

    try:
        result = db.table(TABLE_PARTOGRAPH).insert(data).execute()
    except Exception as exc:
        logger.error("Partograph entry failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to record partograph entry")

    entry = result.data[0] if result.data else data
    audit_event("partograph_entry", {"anc_id": anc_id}, actor_id=user.get("sub"), subject_type="partograph", subject_id=str(entry.get("id") or ""))
    return {"ok": True, "entry": entry}


@router.get("/anc/{anc_id}/partograph")
async def get_partograph(anc_id: int, user=Depends(verify_jwt)):
    _get_anc(anc_id)
    result = db.table(TABLE_PARTOGRAPH).select("*").eq("anc_id", anc_id).order("recorded_at").execute()
    return {"entries": result.data or [], "count": len(result.data or [])}


# ---------------------------------------------------------------------------
# Delivery
# ---------------------------------------------------------------------------

@router.post("/anc/{anc_id}/delivery", status_code=201)
async def record_delivery(anc_id: int, payload: DeliveryRecord, user=Depends(verify_jwt)):
    """Record delivery outcome for an ANC case."""
    anc = _get_anc(anc_id)

    # Check no delivery record already exists
    existing = db.table(TABLE_DELIVERY_RECORDS).select("id").eq("anc_id", anc_id).execute()
    if existing.data:
        raise HTTPException(status_code=409, detail="Delivery record already exists for this ANC case")

    data = payload.model_dump(exclude_none=True)
    data["anc_id"]     = anc_id
    data["patient_id"] = anc["patient_id"]
    data["recorded_by"] = user.get("sub") or "system"
    if "delivery_date" not in data:
        data["delivery_date"] = _now()[:10]

    try:
        result = db.table(TABLE_DELIVERY_RECORDS).insert(data).execute()
    except Exception as exc:
        logger.error("Delivery record failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to record delivery")

    record = result.data[0] if result.data else data
    # Mark ANC as delivered
    db.table(TABLE_ANC_RECORDS).update({"status": "delivered"}).eq("id", anc_id).execute()
    audit_event(
        "delivery_recorded",
        {"mode": payload.mode_of_delivery, "anc_id": anc_id},
        actor_id=user.get("sub"),
        subject_type="delivery_record",
        subject_id=str(record.get("id") or ""),
    )
    return {"ok": True, "record": record}


@router.get("/anc/{anc_id}/delivery")
async def get_delivery(anc_id: int, user=Depends(verify_jwt)):
    _get_anc(anc_id)
    result = db.table(TABLE_DELIVERY_RECORDS).select("*").eq("anc_id", anc_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="No delivery record for this ANC case")
    return {"record": result.data[0]}


# ---------------------------------------------------------------------------
# Newborn Assessment
# ---------------------------------------------------------------------------

@router.post("/delivery/{delivery_id}/newborn", status_code=201)
async def add_newborn_assessment(delivery_id: int, payload: NewbornAssessment, user=Depends(verify_jwt)):
    """Record newborn assessment for a delivery."""
    delivery = _get_delivery(delivery_id)
    data = payload.model_dump(exclude_none=True)
    data["delivery_id"] = delivery_id
    data["patient_id"]  = delivery["patient_id"]
    data["assessed_by"] = user.get("sub") or "system"

    try:
        result = db.table(TABLE_NEWBORN_ASSESSMENT).insert(data).execute()
    except Exception as exc:
        logger.error("Newborn assessment failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to record newborn assessment")

    assessment = result.data[0] if result.data else data
    audit_event(
        "newborn_assessed",
        {"delivery_id": delivery_id, "apgar_1min": payload.apgar_1min},
        actor_id=user.get("sub"),
        subject_type="newborn_assessment",
        subject_id=str(assessment.get("id") or ""),
    )
    return {"ok": True, "assessment": assessment}


@router.get("/delivery/{delivery_id}/newborn")
async def get_newborn_assessments(delivery_id: int, user=Depends(verify_jwt)):
    _get_delivery(delivery_id)
    result = db.table(TABLE_NEWBORN_ASSESSMENT).select("*").eq("delivery_id", delivery_id).execute()
    return {"assessments": result.data or [], "count": len(result.data or [])}


# ---------------------------------------------------------------------------
# Immunisation
# ---------------------------------------------------------------------------

@router.post("/patients/{patient_id}/immunisation", status_code=201)
async def log_immunisation(patient_id: int, payload: ImmunisationRecord, user=Depends(verify_jwt)):
    """Record an immunisation dose for a patient (child or adult)."""
    data = payload.model_dump(exclude_none=True)
    data["patient_id"]      = patient_id
    data["administered_by"] = payload.administered_by or user.get("sub") or "system"
    if "date_given" not in data:
        data["date_given"] = _now()[:10]

    try:
        result = db.table(TABLE_IMMUNISATION).insert(data).execute()
    except Exception as exc:
        logger.error("Immunisation log failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to log immunisation")

    record = result.data[0] if result.data else data
    audit_event(
        "immunisation_logged",
        {"vaccine": payload.vaccine_name, "dose": payload.dose_number},
        actor_id=user.get("sub"),
        subject_type="immunisation",
        subject_id=str(record.get("id") or ""),
    )
    return {"ok": True, "record": record}


@router.get("/patients/{patient_id}/immunisation")
async def get_immunisation_history(
    patient_id: int,
    limit: int = Query(100, ge=1, le=500),
    user=Depends(verify_jwt),
):
    """Full immunisation history for a patient."""
    result = (
        db.table(TABLE_IMMUNISATION)
        .select("*")
        .eq("patient_id", patient_id)
        .order("date_given", desc=True)
        .limit(limit)
        .execute()
    )
    return {"immunisations": result.data or [], "count": len(result.data or [])}


# ---------------------------------------------------------------------------
# Summary endpoint — useful for dashboard
# ---------------------------------------------------------------------------

@router.get("/stats")
async def mch_stats(user=Depends(verify_jwt)):
    """Summary counts for MCH dashboard."""
    anc_result = db.table(TABLE_ANC_RECORDS).select("status").execute()
    rows = anc_result.data or []

    active     = sum(1 for r in rows if r.get("status") == "active")
    delivered  = sum(1 for r in rows if r.get("status") == "delivered")
    referred   = sum(1 for r in rows if r.get("status") == "referred")
    total_anc  = len(rows)

    delivery_result = db.table(TABLE_DELIVERY_RECORDS).select("mode_of_delivery").execute()
    deliveries = delivery_result.data or []
    mode_counts: dict = {}
    for d in deliveries:
        m = d.get("mode_of_delivery") or "other"
        mode_counts[m] = mode_counts.get(m, 0) + 1

    immunisation_result = db.table(TABLE_IMMUNISATION).select("vaccine_name").execute()
    imm_rows = immunisation_result.data or []
    vaccine_counts: dict = {}
    for i in imm_rows:
        v = i.get("vaccine_name") or "other"
        vaccine_counts[v] = vaccine_counts.get(v, 0) + 1

    # Encounter-based counts from historical Hope migration data
    enc_total = 0
    enc_today = 0
    try:
        today_iso = datetime.now(timezone.utc).date().isoformat()
        enc_resp = (
            db.table("royan_encounters")
            .select("id", count="exact")
            .or_("department.ilike.%obstet%,department.ilike.%gyn%,department.ilike.%mch%,department.ilike.%matern%,department.ilike.%antenat%")
            .execute()
        )
        enc_total = enc_resp.count or 0
        enc_today_resp = (
            db.table("royan_encounters")
            .select("id", count="exact")
            .or_("department.ilike.%obstet%,department.ilike.%gyn%,department.ilike.%mch%,department.ilike.%matern%,department.ilike.%antenat%")
            .gte("created_at", today_iso + "T00:00:00")
            .execute()
        )
        enc_today = enc_today_resp.count or 0
    except Exception:
        pass

    return {
        "anc": {"total": total_anc or enc_total, "active": active, "delivered": delivered, "referred": referred},
        "encounters": {"total": enc_total, "today": enc_today},
        "delivery_modes": mode_counts,
        "immunisation_counts": vaccine_counts,
    }
