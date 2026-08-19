"""
MCH / OB-GYN Router — RoyanHealth / Royan Hospital
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
from datetime import date, datetime, timedelta, timezone
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
    TABLE_VACCINE_SCHEDULE,
    TABLE_PATIENTS,
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
    # Patient-level bio fields (not columns on royan_newborn_assessment) —
    # split onto the baby's own royan_patients row in add_newborn_assessment.
    father_name: Optional[str] = None
    place_of_birth: Optional[str] = None

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


def _generate_mrn() -> str:
    """Same public.generate_mrn() RPC used by patient_registration.py and
    hope_sync.py — keeps MRN numbering consistent across every path that
    creates a royan_patients row, including a newborn's own record."""
    result = db.rpc("generate_mrn", {}).execute()
    if result.data:
        row = result.data[0]
        return row.get("generate_mrn") if isinstance(row, dict) else str(row)
    raise RuntimeError("generate_mrn() RPC returned no data")


_SEX_TO_GENDER = {"male": "male", "female": "female", "indeterminate": "other"}

_DUE_SOON_DAYS = 14  # upcoming (not yet overdue) doses due within this many days count as "due_soon"


def _as_date(v) -> Optional[date]:
    """Normalise a DB value that may come back as a date/datetime object or
    an ISO string (depends on driver/cursor path) into a plain date."""
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def _compute_immunisation_status(
    dob: Optional[date],
    given: list[dict],
    schedule_rows: list[dict],
) -> tuple[list[dict], dict]:
    """Annotate schedule rows with due_date/status/date_given for one patient,
    and return an aggregate summary.

    Matching is ordinal, not a strict dose-number join: for the k-th schedule
    row of a given vaccine name (ordered by age_days), we match it to the k-th
    administered dose of that same name (ordered by date_given) if one exists.
    Schedule rows don't consistently carry dose_number, and this mirrors how a
    real paper vaccination card gets filled in — in order, not by matching an
    explicit dose index.
    """
    today = date.today()
    _norm = lambda s: (s or "").strip().lower()
    schedule_rows = sorted(schedule_rows, key=lambda r: r.get("age_days") if r.get("age_days") is not None else 0)

    by_name_given: dict[str, list[dict]] = {}
    for g in sorted(given, key=lambda r: r.get("date_given") or ""):
        if g.get("vaccine_name"):
            by_name_given.setdefault(_norm(g["vaccine_name"]), []).append(g)

    given_cursor: dict[str, int] = {}
    annotated: list[dict] = []
    overdue_count = 0
    upcoming_count = 0
    next_due: Optional[dict] = None

    for row in schedule_rows:
        name = _norm(row["vaccine_name"])
        idx = given_cursor.get(name, 0)
        doses_given = by_name_given.get(name, [])
        out = dict(row)

        due_date = dob + timedelta(days=row.get("age_days") or 0) if dob else None
        out["due_date"] = due_date.isoformat() if due_date else None

        if idx < len(doses_given):
            dose = doses_given[idx]
            out["status"] = "given"
            out["date_given"] = dose.get("date_given")
            out["administered"] = True
            given_cursor[name] = idx + 1
        else:
            out["date_given"] = None
            out["administered"] = False
            if due_date is None:
                out["status"] = "upcoming"
            elif due_date < today:
                out["status"] = "overdue"
                overdue_count += 1
                if next_due is None or due_date < date.fromisoformat(next_due["due_date"]):
                    next_due = {"vaccine_name": row["vaccine_name"], "due_date": out["due_date"]}
            else:
                out["status"] = "upcoming"
                if due_date <= today + timedelta(days=_DUE_SOON_DAYS):
                    upcoming_count += 1
                    if next_due is None or due_date < date.fromisoformat(next_due["due_date"]):
                        next_due = {"vaccine_name": row["vaccine_name"], "due_date": out["due_date"]}

        annotated.append(out)

    if overdue_count:
        overall_status = "overdue"
    elif upcoming_count:
        overall_status = "due_soon"
    else:
        overall_status = "up_to_date"

    summary = {
        "overdue_count": overdue_count,
        "upcoming_count": upcoming_count,
        "next_due": next_due,
        "overall_status": overall_status,
    }
    return annotated, summary


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
    records = result.data or []

    patient_ids = list({r["patient_id"] for r in records if r.get("patient_id")})
    patients_by_id: dict[int, dict] = {}
    if patient_ids:
        patients = db.table(TABLE_PATIENTS).select("id,mrn,first_name,last_name").in_("id", patient_ids).execute()
        patients_by_id = {p["id"]: p for p in (patients.data or [])}

    for r in records:
        p = patients_by_id.get(r.get("patient_id"))
        r["patient_name"] = f"{p['first_name']} {p['last_name']}" if p else None
        r["mrn"] = p.get("mrn") if p else None

    return {"records": records, "count": len(records)}


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
    """Record newborn assessment for a delivery.

    Gives the baby their own royan_patients row (DOB = delivery date, gender
    from `sex`, mother_patient_id linking back) instead of filing the
    assessment under the mother's patient_id — the baby never had a distinct
    patient record before this, so there was nothing for a "Babies page" or
    immunisation history to attach to.
    """
    delivery = _get_delivery(delivery_id)
    mother = db.table(TABLE_PATIENTS).select("id,last_name,hmo_provider,hmo_id").eq("id", delivery["patient_id"]).execute()
    mother_row = mother.data[0] if mother.data else {}

    baby_patient = {
        "mrn": _generate_mrn(),
        "first_name": "Baby",
        "last_name": mother_row.get("last_name") or "Unknown",
        "date_of_birth": delivery.get("delivery_date"),
        "gender": _SEX_TO_GENDER.get((payload.sex or "").lower()),
        "hmo_provider": mother_row.get("hmo_provider"),
        "hmo_id": mother_row.get("hmo_id"),
        "mother_patient_id": delivery["patient_id"],
        "registered_by": user.get("sub") or "system",
    }
    if payload.father_name:
        baby_patient["father_name"] = payload.father_name
    if payload.place_of_birth:
        baby_patient["place_of_birth"] = payload.place_of_birth
    try:
        baby_result = db.table(TABLE_PATIENTS).insert(baby_patient).execute()
    except Exception as exc:
        logger.error("Baby patient record creation failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to create the newborn's patient record")
    baby = baby_result.data[0] if baby_result.data else baby_patient

    data = payload.model_dump(exclude_none=True, exclude={"father_name", "place_of_birth"})
    data["delivery_id"] = delivery_id
    data["patient_id"]  = baby["id"]
    data["assessed_by"] = user.get("sub") or "system"

    try:
        result = db.table(TABLE_NEWBORN_ASSESSMENT).insert(data).execute()
    except Exception as exc:
        logger.error("Newborn assessment failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to record newborn assessment")

    assessment = result.data[0] if result.data else data
    audit_event(
        "newborn_assessed",
        {"delivery_id": delivery_id, "apgar_1min": payload.apgar_1min, "baby_patient_id": baby["id"]},
        actor_id=user.get("sub"),
        subject_type="newborn_assessment",
        subject_id=str(assessment.get("id") or ""),
    )
    return {"ok": True, "assessment": assessment, "baby_patient": baby}


@router.get("/delivery/{delivery_id}/newborn")
async def get_newborn_assessments(delivery_id: int, user=Depends(verify_jwt)):
    _get_delivery(delivery_id)
    result = db.table(TABLE_NEWBORN_ASSESSMENT).select("*").eq("delivery_id", delivery_id).execute()
    return {"assessments": result.data or [], "count": len(result.data or [])}


# ---------------------------------------------------------------------------
# Immunisation
# ---------------------------------------------------------------------------

@router.post("/patients/{patient_id}/immunisation", status_code=201)
async def log_immunisation(
    patient_id: int,
    payload: ImmunisationRecord | list[ImmunisationRecord],
    user=Depends(verify_jwt),
):
    """Record one or more immunisation doses for a patient in a single call
    (client ask: "can take multiple immunisation at once")."""
    records = payload if isinstance(payload, list) else [payload]
    if not records:
        raise HTTPException(status_code=422, detail="At least one immunisation record is required")

    rows = []
    for rec in records:
        row = rec.model_dump(exclude_none=True)
        row["patient_id"]      = patient_id
        row["administered_by"] = rec.administered_by or user.get("sub") or "system"
        if "date_given" not in row:
            row["date_given"] = _now()[:10]
        rows.append(row)

    try:
        result = db.table(TABLE_IMMUNISATION).insert(rows).execute()
    except Exception as exc:
        logger.error("Immunisation log failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to log immunisation")

    saved = result.data or rows
    for rec, row in zip(records, saved):
        audit_event(
            "immunisation_logged",
            {"vaccine": rec.vaccine_name, "dose": rec.dose_number},
            actor_id=user.get("sub"),
            subject_type="immunisation",
            subject_id=str(row.get("id") or ""),
        )
    return {"ok": True, "records": saved, "count": len(saved)}


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
# Babies (mother-baby linkage) + vaccine schedule reference data
# ---------------------------------------------------------------------------

@router.get("/patients/{patient_id}/babies")
async def list_babies(patient_id: int, user=Depends(verify_jwt)):
    """List a mother's babies — royan_patients rows linked via mother_patient_id
    (set by add_newborn_assessment above). Powers the frontend's "Babies" card
    on a mother's patient profile."""
    result = (
        db.table(TABLE_PATIENTS)
        .select("id,mrn,first_name,last_name,date_of_birth,gender,mother_patient_id")
        .eq("mother_patient_id", patient_id)
        .order("date_of_birth", desc=True)
        .execute()
    )
    return {"babies": result.data or [], "count": len(result.data or [])}


@router.get("/vaccine-schedule")
async def get_vaccine_schedule(
    patient_id: Optional[int] = Query(None, description="Compute due/overdue status against this patient's DOB and history"),
    user=Depends(verify_jwt),
):
    """Reference vaccination schedule (seeded from the client's vaccination
    booklet). When patient_id is passed, each row is annotated with a real
    due_date (patient's date_of_birth + age_days) and a status of
    given/overdue/upcoming — not just a boolean "ever given" — via
    _compute_immunisation_status."""
    result = db.table(TABLE_VACCINE_SCHEDULE).select("*").order("age_days").execute()
    rows = result.data or []

    if patient_id is not None:
        patient = db.table(TABLE_PATIENTS).select("id,date_of_birth").eq("id", patient_id).execute()
        dob = _as_date(patient.data[0]["date_of_birth"]) if patient.data else None

        given = (
            db.table(TABLE_IMMUNISATION)
            .select("vaccine_name,date_given")
            .eq("patient_id", patient_id)
            .execute()
        )
        rows, summary = _compute_immunisation_status(dob, given.data or [], rows)
        return {"schedule": rows, "count": len(rows), "summary": summary}

    return {"schedule": rows, "count": len(rows)}


# ---------------------------------------------------------------------------
# Babies roster — hospital-wide, not scoped to a single mother
# ---------------------------------------------------------------------------

class BabyRegister(BaseModel):
    mother_patient_id: int
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: Optional[str] = Field(None, max_length=100)   # defaults to mother's last name
    date_of_birth: str = Field(..., description="ISO date")
    gender: Optional[str] = None
    place_of_birth: Optional[str] = None
    father_name: Optional[str] = None


@router.post("/babies/register", status_code=201)
async def register_baby(payload: BabyRegister, user=Depends(verify_jwt)):
    """Start a new baby directly onto the immunisation program — the
    Immunisation page's "New Baby" entry point. Unlike add_newborn_assessment
    (gated behind a delivery record in this system), this covers any baby
    brought in for vaccination, including ones born elsewhere. The mother
    link is mandatory, not optional — a baby record can never be created
    without a resolved, real mother patient behind it."""
    mother = db.table(TABLE_PATIENTS).select("id,last_name,hmo_provider,hmo_id,mrn").eq("id", payload.mother_patient_id).execute()
    if not mother.data:
        raise HTTPException(status_code=404, detail=f"Mother patient {payload.mother_patient_id} not found")
    mother_row = mother.data[0]

    if payload.gender and payload.gender not in {"male", "female", "other", "prefer_not_to_say"}:
        raise HTTPException(status_code=422, detail="gender must be one of male/female/other/prefer_not_to_say")

    baby_patient = {
        "mrn": _generate_mrn(),
        "first_name": payload.first_name.strip(),
        "last_name": (payload.last_name or mother_row.get("last_name") or "Unknown").strip(),
        "date_of_birth": payload.date_of_birth,
        "gender": payload.gender,
        "hmo_provider": mother_row.get("hmo_provider"),
        "hmo_id": mother_row.get("hmo_id"),
        "mother_patient_id": payload.mother_patient_id,
        "registered_by": user.get("sub") or "system",
    }
    if payload.father_name:
        baby_patient["father_name"] = payload.father_name
    if payload.place_of_birth:
        baby_patient["place_of_birth"] = payload.place_of_birth

    try:
        result = db.table(TABLE_PATIENTS).insert(baby_patient).execute()
    except Exception as exc:
        logger.error("Baby registration failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to register baby")
    baby = result.data[0] if result.data else baby_patient

    audit_event(
        "baby_registered",
        {"mother_patient_id": payload.mother_patient_id, "mrn": baby.get("mrn")},
        actor_id=user.get("sub"),
        subject_type="patient",
        subject_id=str(baby.get("id") or ""),
    )
    return {"ok": True, "baby": baby}


@router.get("/babies")
async def list_all_babies(
    search: Optional[str] = Query(None, description="Match against first/last name or MRN"),
    status: Optional[str] = Query(None, description="Filter: overdue | due_soon | up_to_date"),
    limit: int = Query(100, ge=1, le=500),
    user=Depends(verify_jwt),
):
    """Hospital-wide roster of babies in the immunisation program — powers the
    dedicated Immunisation page (there was previously no way to browse babies
    without already knowing a specific patient ID). A "baby" is any patient
    linked to a mother via mother_patient_id (created through the Newborn
    Assessment flow) OR any patient with at least one immunisation record on
    file (covers a pediatric patient registered directly, without an ANC/
    delivery record in this system)."""
    linked = db.table(TABLE_PATIENTS).select("id").is_("mother_patient_id", "not_null").execute()
    dosed = db.table(TABLE_IMMUNISATION).select("patient_id").execute()
    candidate_ids = {r["id"] for r in (linked.data or [])} | {r["patient_id"] for r in (dosed.data or []) if r.get("patient_id")}

    if not candidate_ids:
        return {"babies": [], "count": 0}

    query = (
        db.table(TABLE_PATIENTS)
        .select("id,mrn,first_name,last_name,date_of_birth,gender,mother_patient_id")
        .in_("id", list(candidate_ids))
    )
    if search:
        like = f"%{search}%"
        query = query.or_(f"first_name.ilike.{like},last_name.ilike.{like},mrn.ilike.{like}")
    babies = query.order("date_of_birth", desc=True).limit(limit).execute().data or []

    if not babies:
        return {"babies": [], "count": 0}

    baby_ids = [b["id"] for b in babies]
    mother_ids = [b["mother_patient_id"] for b in babies if b.get("mother_patient_id")]

    imm_rows = (
        db.table(TABLE_IMMUNISATION).select("patient_id,vaccine_name,date_given").in_("patient_id", baby_ids).execute()
    ).data or []
    imm_by_patient: dict[int, list[dict]] = {}
    for r in imm_rows:
        imm_by_patient.setdefault(r["patient_id"], []).append(r)

    mothers_by_id: dict[int, dict] = {}
    if mother_ids:
        mothers = db.table(TABLE_PATIENTS).select("id,first_name,last_name,mrn").in_("id", mother_ids).execute()
        mothers_by_id = {m["id"]: m for m in (mothers.data or [])}

    schedule = db.table(TABLE_VACCINE_SCHEDULE).select("*").order("age_days").execute().data or []

    roster = []
    for baby in babies:
        dob = _as_date(baby.get("date_of_birth"))
        _rows, summary = _compute_immunisation_status(dob, imm_by_patient.get(baby["id"], []), schedule)
        mother = mothers_by_id.get(baby.get("mother_patient_id"))
        roster.append({
            **baby,
            "mother_name": f"{mother['first_name']} {mother['last_name']}" if mother else None,
            "mother_mrn": mother.get("mrn") if mother else None,
            "overall_status": summary["overall_status"],
            "overdue_count": summary["overdue_count"],
            "upcoming_count": summary["upcoming_count"],
            "next_due": summary["next_due"],
        })

    if status:
        roster = [b for b in roster if b["overall_status"] == status]

    return {"babies": roster, "count": len(roster)}


@router.get("/babies/{patient_id}")
async def get_baby_detail(patient_id: int, user=Depends(verify_jwt)):
    """Combined bio header for a baby's Vaccination Record page: the patient
    row (incl. father_name/place_of_birth), their birth stats from the
    newborn assessment, and their mother's identity."""
    patient = db.table(TABLE_PATIENTS).select(
        "id,mrn,first_name,last_name,date_of_birth,gender,father_name,place_of_birth,"
        "address,phone,allergies,mother_patient_id"
    ).eq("id", patient_id).execute()
    if not patient.data:
        raise HTTPException(status_code=404, detail=f"Patient {patient_id} not found")
    baby = patient.data[0]

    assessment = (
        db.table(TABLE_NEWBORN_ASSESSMENT)
        .select("birth_weight_kg,length_cm,head_circumference_cm,apgar_1min,apgar_5min,apgar_10min")
        .eq("patient_id", patient_id)
        .execute()
    )
    baby["newborn_assessment"] = assessment.data[0] if assessment.data else None

    mother = None
    if baby.get("mother_patient_id"):
        m = db.table(TABLE_PATIENTS).select("id,mrn,first_name,last_name,phone").eq("id", baby["mother_patient_id"]).execute()
        mother = m.data[0] if m.data else None
    baby["mother"] = mother

    return {"baby": baby}


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
