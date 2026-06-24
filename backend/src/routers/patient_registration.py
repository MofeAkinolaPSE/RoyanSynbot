"""
Patient Registration Router — SynbotHealth / Royan Hospital
==============================================================
Endpoints:
  POST /patients/register          – Register a new patient (generates MRN)
  GET  /patients/{mrn}             – Fetch patient by MRN
  GET  /patients/search            – Search by name, phone, HMO ID
  PATCH /patients/{mrn}            – Update patient demographics
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from src.cache import invalidate_cache_tags
from src.db import db, audit_event
from src.middleware import verify_jwt, require_role
from src.constants import (
    TABLE_BILLING,
    TABLE_ENCOUNTERS,
    TABLE_LAB_ORDERS,
    TABLE_PATIENTS,
    TABLE_PRESCRIPTIONS,
)
from src.services.coverage import get_active_patient_insurance

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/patients", tags=["Patients"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class PatientCreate(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    date_of_birth: Optional[str] = None          # ISO date string: YYYY-MM-DD
    gender: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    next_of_kin_name: Optional[str] = None
    next_of_kin_phone: Optional[str] = None
    blood_group: Optional[str] = None
    blood_type: Optional[str] = None
    genotype: Optional[str] = None
    allergies: Optional[list[str]] = None
    hmo_provider: Optional[str] = None
    hmo_id: Optional[str] = None
    external_source: Optional[str] = None
    external_id: Optional[str] = None

    model_config = {"extra": "ignore"}

    @field_validator("gender")
    @classmethod
    def _valid_gender(cls, v):
        allowed = {"male", "female", "other", "prefer_not_to_say"}
        if v and v not in allowed:
            raise ValueError(f"gender must be one of {allowed}")
        return v

    @field_validator("blood_group")
    @classmethod
    def _valid_blood_group(cls, v):
        allowed = {"A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-", "unknown"}
        if v and v not in allowed:
            raise ValueError(f"blood_group must be one of {allowed}")
        return v


class PatientUpdate(BaseModel):
    phone: Optional[str] = Field(None, max_length=20)
    email: Optional[str] = Field(None, max_length=254)
    address: Optional[str] = Field(None, max_length=500)
    next_of_kin_name: Optional[str] = Field(None, max_length=200)
    next_of_kin_phone: Optional[str] = Field(None, max_length=20)
    hmo_provider: Optional[str] = Field(None, max_length=200)
    hmo_id: Optional[str] = Field(None, max_length=100)
    allergies: Optional[list[str]] = None
    blood_group: Optional[str] = Field(None, max_length=10)
    blood_type: Optional[str] = Field(None, max_length=10)
    genotype: Optional[str] = Field(None, max_length=10)
    is_active: Optional[bool] = None
    external_source: Optional[str] = Field(None, max_length=100)
    external_id: Optional[str] = Field(None, max_length=100)

    model_config = {"extra": "ignore"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fetch_patient_by_mrn(mrn: str) -> dict:
    result = db.table(TABLE_PATIENTS).select("*").eq("mrn", mrn.strip().upper()).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail=f"Patient with MRN '{mrn}' not found")
    return result.data[0]


def _generate_mrn() -> str:
    result = db.rpc("generate_mrn", {}).execute()
    if result.data:
        row = result.data[0]
        return row.get("generate_mrn") or row.get("mrn") or str(row)
    raise RuntimeError("MRN generation failed")


def _patient_card(patient: dict) -> dict:
    card = dict(patient)
    patient_id = patient.get("id")
    if patient_id is None:
        return card

    try:
        active = (
            db.table(TABLE_ENCOUNTERS)
            .select("id,status,department,encounter_type,created_at,triage_level")
            .eq("patient_id", patient_id)
            .neq("status", "discharged")
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        current = (active.data or [None])[0]
        card["current_encounter"] = current
        card["current_status"] = current.get("status") if current else None
    except Exception:
        card["current_encounter"] = None
        card["current_status"] = None

    try:
        insurance = get_active_patient_insurance(int(patient_id))
        if insurance:
            card["insurance"] = {
                "active": True,
                "hmo_name": insurance.get("hmo_name") or patient.get("hmo_provider"),
                "plan_name": insurance.get("plan_name"),
                "membership_id": insurance.get("membership_id") or patient.get("hmo_id"),
                "legacy_only": bool(insurance.get("legacy_only")),
            }
        else:
            card["insurance"] = {
                "active": bool(patient.get("hmo_provider") or patient.get("hmo_id")),
                "hmo_name": patient.get("hmo_provider"),
                "membership_id": patient.get("hmo_id"),
                "legacy_only": True,
            }
    except Exception:
        card["insurance"] = {
            "active": bool(patient.get("hmo_provider") or patient.get("hmo_id")),
            "hmo_name": patient.get("hmo_provider"),
            "membership_id": patient.get("hmo_id"),
            "legacy_only": True,
        }
    return card


def _search_patients_by_term(term: str, limit: int) -> list[dict]:
    safe = term.strip()
    if not safe:
        return []
    columns = "id,mrn,first_name,last_name,date_of_birth,gender,phone,email,address,next_of_kin_name,next_of_kin_phone,hmo_provider,hmo_id,is_active,blood_group,genotype,allergies,registered_at"
    parts = safe.split()

    # Base conditions — match the full term in any single field
    conditions = [
        f"mrn.ilike.%{safe}%",
        f"first_name.ilike.%{safe}%",
        f"last_name.ilike.%{safe}%",
        f"phone.ilike.%{safe}%",
        f"hmo_id.ilike.%{safe}%",
    ]

    # For multi-word input (e.g. "TOBILOBA OGUNTOSIN") also widen the OR so
    # that each individual word is matched against both name fields.  This
    # catches full-name queries that no single field can satisfy on its own.
    if len(parts) >= 2:
        for word in parts:
            conditions += [
                f"first_name.ilike.%{word}%",
                f"last_name.ilike.%{word}%",
            ]

    try:
        result = (
            db.table(TABLE_PATIENTS)
            .select(columns)
            .or_(",".join(conditions))
            .order("last_name")
            .limit(limit * 2)   # fetch extra so re-ranking has enough to pick from
            .execute()
        )
        rows = result.data or []
    except Exception:
        seen: set = set()
        rows = []
        for field in ("mrn", "first_name", "last_name", "phone", "hmo_id"):
            try:
                resp = db.table(TABLE_PATIENTS).select(columns).ilike(field, f"%{safe}%").limit(limit).execute()
                for row in resp.data or []:
                    key = row.get("id") or row.get("mrn")
                    if key not in seen:
                        seen.add(key)
                        rows.append(row)
            except Exception:
                continue

    # Re-rank multi-word results: patients matching ALL parts in their combined
    # name rank first, so "TOBILOBA OGUNTOSIN" surfaces before incidental hits.
    if len(parts) >= 2:
        words_lower = [w.lower() for w in parts]
        def _score(r: dict) -> int:
            combined = f"{r.get('first_name', '')} {r.get('last_name', '')}".lower()
            return 0 if all(w in combined for w in words_lower) else 1
        rows = sorted(rows, key=_score)

    # Deduplicate (widened OR can return duplicates) then trim to limit
    seen_ids: set = set()
    deduped: list[dict] = []
    for r in rows:
        key = r.get("id") or r.get("mrn")
        if key not in seen_ids:
            seen_ids.add(key)
            deduped.append(r)
    return deduped[:limit]


def _load_patient_profile(patient: dict) -> dict:
    patient_id = patient["id"]
    encounters = db.table(TABLE_ENCOUNTERS).select("*").eq("patient_id", patient_id).order("created_at", desc=True).limit(50).execute().data or []
    labs = db.table(TABLE_LAB_ORDERS).select("*").eq("patient_id", patient_id).order("ordered_at", desc=True).limit(50).execute().data or []
    prescriptions = db.table(TABLE_PRESCRIPTIONS).select("*").eq("patient_id", patient_id).order("prescribed_at", desc=True).limit(50).execute().data or []
    bills = db.table(TABLE_BILLING).select("*").eq("patient_id", patient_id).order("billed_at", desc=True).limit(50).execute().data or []

    timeline: list[dict] = []
    for enc in encounters:
        timeline.append({"type": "encounter", "timestamp": enc.get("created_at"), "record": enc})
    for order in labs:
        timeline.append({"type": "lab_order", "timestamp": order.get("ordered_at"), "record": order})
    for rx in prescriptions:
        timeline.append({"type": "prescription", "timestamp": rx.get("prescribed_at"), "record": rx})
    for bill in bills:
        timeline.append({"type": "bill", "timestamp": bill.get("billed_at"), "record": bill})
    timeline.sort(key=lambda item: item.get("timestamp") or "", reverse=True)

    card = _patient_card(patient)
    return {
        "patient": card,
        "insurance": card.get("insurance"),
        "active_encounter": card.get("current_encounter"),
        "encounters": encounters,
        "lab_orders": labs,
        "prescriptions": prescriptions,
        "bills": bills,
        "timeline": timeline,
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

def _check_duplicates(first_name: str, last_name: str, dob: Optional[str], phone: Optional[str]) -> list[dict]:
    """Return existing patients that match by name+DOB or phone."""
    matches: list[dict] = []
    cols = "id,mrn,first_name,last_name,date_of_birth,phone"
    try:
        if dob:
            r = (
                db.table(TABLE_PATIENTS)
                .select(cols)
                .ilike("first_name", first_name.strip())
                .ilike("last_name", last_name.strip())
                .eq("date_of_birth", dob)
                .execute()
            )
            matches.extend(r.data or [])
        if phone:
            r2 = db.table(TABLE_PATIENTS).select(cols).eq("phone", phone.strip()).execute()
            seen_ids = {m["id"] for m in matches}
            for row in r2.data or []:
                if row["id"] not in seen_ids:
                    matches.append(row)
    except Exception:
        pass
    return matches


@router.post("/register", status_code=201)
async def register_patient(
    payload: PatientCreate,
    force: bool = Query(False, description="Skip duplicate check and register anyway"),
    user=Depends(verify_jwt),
):
    """Register a new patient and return the generated MRN."""
    if not force:
        dupes = _check_duplicates(payload.first_name, payload.last_name, payload.date_of_birth, payload.phone)
        if dupes:
            return {
                "duplicate": True,
                "matches": [
                    {
                        "id": d["id"],
                        "mrn": d["mrn"],
                        "name": f"{d.get('first_name', '')} {d.get('last_name', '')}".strip(),
                        "date_of_birth": d.get("date_of_birth"),
                        "phone": d.get("phone"),
                    }
                    for d in dupes
                ],
            }
    mrn = _generate_mrn()
    data = payload.model_dump(exclude_none=True)
    if "blood_type" in data and "blood_group" not in data:
        data["blood_group"] = data.pop("blood_type")
    data.pop("blood_type", None)
    data["mrn"] = mrn
    data["registered_by"] = user.get("sub") or user.get("email") or "system"

    try:
        result = db.table(TABLE_PATIENTS).insert(data).execute()
    except Exception as exc:
        logger.error("Patient registration failed: %s", exc)
        raise HTTPException(status_code=500, detail="Registration failed")

    patient = result.data[0] if result.data else {"mrn": mrn}
    audit_event(
        "patient_registered",
        {"patient_id": patient.get("id"), "mrn": mrn},
        actor_id=user.get("sub"),
        subject_type="patient",
        subject_id=str(patient.get("id") or mrn),
    )
    logger.info("New patient registered: MRN=%s by %s", mrn, user.get("sub"))
    invalidate_cache_tags("hospital", "patient_flow", "encounters", "executive")
    return {"ok": True, "mrn": mrn, "patient": _patient_card(patient)}


@router.get("/search")
async def search_patients(
    q: Optional[str] = Query(None, description="Name, phone, or HMO ID fragment"),
    phone: Optional[str] = Query(None),
    hmo_id: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    user=Depends(verify_jwt),
):
    """Search patients by MRN, name fragment, phone, or HMO ID."""
    if phone:
        result = db.table(TABLE_PATIENTS).select("*").eq("phone", phone.strip()).limit(limit).execute()
        rows = result.data or []
    elif hmo_id:
        result = db.table(TABLE_PATIENTS).select("*").eq("hmo_id", hmo_id.strip()).limit(limit).execute()
        rows = result.data or []
    elif q:
        rows = _search_patients_by_term(q, limit)
    else:
        result = db.table(TABLE_PATIENTS).select("*").order("registered_at", desc=True).limit(limit).execute()
        rows = result.data or []

    patients = [_patient_card(row) for row in rows]
    return {"patients": patients, "count": len(patients)}


@router.get("/{mrn}/profile")
async def get_patient_profile(mrn: str, user=Depends(verify_jwt)):
    patient = _fetch_patient_by_mrn(mrn)
    audit_event(
        "patient_profile_viewed",
        {"mrn": mrn},
        actor_id=user.get("sub"),
        subject_type="patient",
        subject_id=str(patient.get("id") or mrn),
    )
    return _load_patient_profile(patient)


@router.get("/{mrn}")
async def get_patient(mrn: str, user=Depends(verify_jwt)):
    """Fetch a patient record by MRN."""
    patient = _fetch_patient_by_mrn(mrn)
    return _patient_card(patient)


@router.patch("/{mrn}")
async def update_patient(mrn: str, payload: PatientUpdate, user=Depends(verify_jwt)):
    """Update mutable patient demographics."""
    patient = _fetch_patient_by_mrn(mrn)
    updates = payload.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    if "blood_type" in updates and "blood_group" not in updates:
        updates["blood_group"] = updates.pop("blood_type")
    updates.pop("blood_type", None)

    try:
        db.table(TABLE_PATIENTS).update(updates).eq("id", patient["id"]).execute()
    except Exception as exc:
        logger.error("Patient update failed for MRN=%s: %s", mrn, exc)
        raise HTTPException(status_code=500, detail="Update failed")

    audit_event(
        "patient_updated",
        {"fields": list(updates.keys())},
        actor_id=user.get("sub"),
        subject_type="patient",
        subject_id=str(patient["id"]),
    )
    return {"ok": True, "mrn": mrn, "updated_fields": list(updates.keys())}
