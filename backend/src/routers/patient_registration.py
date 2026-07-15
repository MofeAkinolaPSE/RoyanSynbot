"""
Patient Registration Router — RoyanHealth / Royan Hospital
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
    """Build a single patient card with encounter + insurance detail (2 queries).
    Use _batch_patient_cards() when building cards for a list of patients.
    """
    card = dict(patient)
    patient_id = patient.get("id")
    if patient_id is None:
        return card

    try:
        # Only a native encounter (external_source IS NULL) counts as "active" —
        # a Hope historical import or a synbot_repair ancillary bucket (see
        # repair_shared_encounter_keys.py) can sit in a non-discharged status
        # forever without the patient actually being in the building, and must
        # never be reported as their current encounter.
        active = (
            db.table(TABLE_ENCOUNTERS)
            .select("id,status,department,encounter_type,created_at,triage_level")
            .eq("patient_id", patient_id)
            .neq("status", "discharged")
            .is_("external_source", None)
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

    if not card.get("current_encounter"):
        # No active native encounter — surface the most recent real visit
        # instead (any status, including discharged/Hope-imported) so the
        # profile shows honest "last seen" context rather than nothing. The
        # synbot_repair ancillary bucket is excluded here too — it's a data
        # bucket for orphaned lab/pharmacy/billing links, not a real visit.
        try:
            last = (
                db.table(TABLE_ENCOUNTERS)
                .select("id,status,department,encounter_type,created_at,discharge_at,triage_level,external_source")
                .eq("patient_id", patient_id)
                .or_("external_source.is.null,external_source.neq.synbot_repair")
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )
            card["last_encounter"] = (last.data or [None])[0]
        except Exception:
            card["last_encounter"] = None
    else:
        card["last_encounter"] = None

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


def _batch_patient_cards(patients: list[dict]) -> list[dict]:
    """Build patient cards for a list of patients using 1 batched encounter query
    instead of N individual queries. Insurance uses legacy hmo_provider/hmo_id
    fields already present on the patient row — no extra queries needed.
    """
    if not patients:
        return []

    patient_ids = [p["id"] for p in patients if p.get("id") is not None]
    enc_map: dict = {}

    if patient_ids:
        try:
            # Native encounters only — see _patient_card()'s docstring note on
            # why Hope/synbot_repair rows must never count as "active".
            enc_result = (
                db.table(TABLE_ENCOUNTERS)
                .select("id,patient_id,status,department,encounter_type,created_at,triage_level")
                .in_("patient_id", patient_ids)
                .neq("status", "discharged")
                .is_("external_source", None)
                .order("created_at", desc=True)
                .execute()
            )
            for enc in (enc_result.data or []):
                pid = enc.get("patient_id")
                if pid is not None and pid not in enc_map:
                    enc_map[pid] = enc
        except Exception:
            pass

    cards = []
    for patient in patients:
        card = dict(patient)
        patient_id = patient.get("id")
        current = enc_map.get(patient_id)
        card["current_encounter"] = current
        card["current_status"] = current.get("status") if current else None
        card["insurance"] = {
            "active": bool(patient.get("hmo_provider") or patient.get("hmo_id")),
            "hmo_name": patient.get("hmo_provider"),
            "membership_id": patient.get("hmo_id"),
            "legacy_only": True,
        }
        cards.append(card)

    return cards


def _search_patients_by_term(term: str, limit: int) -> list[dict]:
    """Search patients by name/MRN/phone/HMO ID.

    NOTE on ordering: every query below appends "id" as a secondary sort key
    after the natural sort column. Postgres gives no ordering guarantee among
    rows tied on the primary sort column (e.g. dozens of patients sharing the
    exact last_name "AKINOLA") — without a tiebreaker, which rows survive a
    LIMIT cutoff is arbitrary and can change between queries as autovacuum/
    ANALYZE alter the scan plan, silently dropping a real match from results
    that previously included it. This was caught in production (2026-07): a
    patient who appeared in search one day was gone from it the next, despite
    the row being fully intact — a pagination bug, not data loss.
    """
    safe = term.strip()
    if not safe:
        return []
    columns = "id,mrn,first_name,last_name,date_of_birth,gender,phone,email,address,next_of_kin_name,next_of_kin_phone,hmo_provider,hmo_id,is_active,blood_group,genotype,allergies,registered_at"
    parts = safe.split()

    seen_ids: set = set()
    deduped: list[dict] = []

    def _add_rows(rows: list[dict]) -> None:
        for r in rows:
            key = r.get("id") or r.get("mrn")
            if key not in seen_ids:
                seen_ids.add(key)
                deduped.append(r)

    # For multi-word input (e.g. "MOFE AKINOLA"), run a precise AND-across-words
    # match FIRST and give it its own limit — every word must appear somewhere
    # in first_name/last_name. True full-name matches are rare, so this query
    # is never at risk of being truncated out by ties on a much more common
    # single field (e.g. a shared surname) the way the broader OR query below
    # can be.
    if len(parts) >= 2:
        try:
            q = db.table(TABLE_PATIENTS).select(columns)
            for word in parts:
                q = q.or_(f"first_name.ilike.%{word}%,last_name.ilike.%{word}%")
            exact = q.order("last_name").order("id").limit(limit * 2).execute()
            _add_rows(exact.data or [])
        except Exception:
            pass

    # Broader single-field OR match — catches MRN/phone/HMO ID hits and
    # partial/fuzzy name matches the precise query above wouldn't.
    if len(deduped) < limit:
        conditions = [
            f"mrn.ilike.%{safe}%",
            f"first_name.ilike.%{safe}%",
            f"last_name.ilike.%{safe}%",
            f"phone.ilike.%{safe}%",
            f"hmo_id.ilike.%{safe}%",
        ]
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
                .order("id")   # deterministic tiebreak — see docstring
                .limit(limit * 2)   # fetch extra so re-ranking has enough to pick from
                .execute()
            )
            _add_rows(result.data or [])
        except Exception:
            # Fallback: single OR query across all fields (1 query, not 5)
            try:
                fallback_or = f"mrn.ilike.%{safe}%,first_name.ilike.%{safe}%,last_name.ilike.%{safe}%,phone.ilike.%{safe}%,hmo_id.ilike.%{safe}%"
                resp = db.table(TABLE_PATIENTS).select(columns).or_(fallback_or).order("id").limit(limit * 2).execute()
                _add_rows(resp.data or [])
            except Exception:
                pass

    rows = deduped

    # Re-rank multi-word results: patients matching ALL parts in their combined
    # name rank first, so "TOBILOBA OGUNTOSIN" surfaces before incidental hits.
    if len(parts) >= 2:
        words_lower = [w.lower() for w in parts]
        def _score(r: dict) -> int:
            combined = f"{r.get('first_name', '')} {r.get('last_name', '')}".lower()
            return 0 if all(w in combined for w in words_lower) else 1
        rows = sorted(rows, key=_score)

    return rows[:limit]


# Per-patient aggregation now lives in services/patient_context.py (the SDIL
# Patient Context Engine) — see GET /{mrn}/profile below.


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
    from src.services.event_service import emit_clinical_event
    emit_clinical_event(
        event_type="PATIENT_REGISTERED",
        patient_id=patient.get("id"),
        performed_by=user.get("sub"),
        event_data={"mrn": mrn},
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

    patients = _batch_patient_cards(rows)
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
    # Full longitudinal record via the Patient Context Engine (SDIL) — cached
    # per patient, invalidated by invalidate_patient_context() on writes.
    from src.services.patient_context import build_patient_context
    card = _patient_card(patient)
    context = build_patient_context(patient["id"])
    return {
        "patient": card,
        "insurance_summary": card.get("insurance"),
        "active_encounter": card.get("current_encounter"),
        "last_encounter": card.get("last_encounter"),
        **context,
    }


@router.get("/{mrn}/relationship-tree")
async def get_patient_relationship_tree_endpoint(mrn: str, user=Depends(verify_jwt)):
    """Counts of every FK-linked record type for one patient — powers the
    Clinical Data Explorer's graph view. Discovered from the live FK graph."""
    patient = _fetch_patient_by_mrn(mrn)
    from src.services.relationship_auditor import get_patient_relationship_tree
    tree = get_patient_relationship_tree(patient["id"])
    tree["mrn"] = mrn
    tree["patient_name"] = f"{patient.get('first_name', '')} {patient.get('last_name', '')}".strip()
    return tree


@router.get("/{mrn}")
async def get_patient(mrn: str, user=Depends(verify_jwt)):
    """Fetch a patient record by MRN."""
    patient = _fetch_patient_by_mrn(mrn)
    return _patient_card(patient)


@router.patch("/{mrn}")
async def update_patient(mrn: str, payload: PatientUpdate, user=Depends(verify_jwt)):
    """Update mutable patient demographics.

    Uses exclude_unset (not exclude_none) so a field can be explicitly
    cleared: a client that sends {"blood_group": null} gets that column set
    to NULL, while a field simply omitted from the request body is left
    untouched. blood_group/genotype both have a DB CHECK restricting them to
    a fixed enum — NULL satisfies a CHECK (Postgres treats it as "unknown",
    not a violation), but an empty string does not, so this is the only way
    to clear those two fields short of an invalid write.
    """
    patient = _fetch_patient_by_mrn(mrn)
    updates = payload.model_dump(exclude_unset=True)
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
