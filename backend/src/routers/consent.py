"""Consent Records Router — capture and retrieve patient consent forms."""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.constants import TABLE_CONSENT_RECORDS, TABLE_PATIENTS
from src.db import audit_event, db
from src.middleware import verify_jwt

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/patients", tags=["Consent"])

CONSENT_TYPES = {
    "general_treatment",
    "surgery",
    "anaesthesia",
    "blood_transfusion",
    "hiv_testing",
    "data_processing",
    "photography",
    "research",
    "other",
}


class ConsentCreate(BaseModel):
    consent_type: str = "general_treatment"
    consented: bool = True
    encounter_id: Optional[int] = None
    notes: Optional[str] = None
    witness_name: Optional[str] = None

    model_config = {"extra": "ignore"}


@router.post("/{patient_id}/consent", status_code=201)
async def add_consent(patient_id: int, payload: ConsentCreate, user=Depends(verify_jwt)):
    """Record a patient consent event."""
    r = db.table(TABLE_PATIENTS).select("id").eq("id", patient_id).execute()
    if not r.data:
        raise HTTPException(status_code=404, detail=f"Patient {patient_id} not found")

    if payload.consent_type not in CONSENT_TYPES:
        raise HTTPException(status_code=422, detail=f"consent_type must be one of {sorted(CONSENT_TYPES)}")

    from datetime import datetime, timezone
    data = {
        "patient_id": patient_id,
        "encounter_id": payload.encounter_id,
        "consent_type": payload.consent_type,
        "consented": payload.consented,
        "signed_at": datetime.now(timezone.utc).isoformat(),
        "captured_by": user.get("sub") or user.get("email"),
        "notes": payload.notes,
        "witness_name": payload.witness_name,
    }
    try:
        result = db.table(TABLE_CONSENT_RECORDS).insert(data).execute()
    except Exception as exc:
        logger.error("Consent insert failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to record consent")

    consent = (result.data or [data])[0]
    audit_event(
        "consent_recorded",
        {"consent_type": payload.consent_type, "consented": payload.consented},
        actor_id=user.get("sub"),
        subject_type="patient",
        subject_id=str(patient_id),
    )
    return {"ok": True, "consent": consent}


@router.get("/{patient_id}/consent")
async def list_consent(
    patient_id: int,
    user=Depends(verify_jwt),
):
    """List all consent records for a patient."""
    r = db.table(TABLE_PATIENTS).select("id").eq("id", patient_id).execute()
    if not r.data:
        raise HTTPException(status_code=404, detail=f"Patient {patient_id} not found")

    result = (
        db.table(TABLE_CONSENT_RECORDS)
        .select("*")
        .eq("patient_id", patient_id)
        .order("signed_at", desc=True)
        .execute()
    )
    return {"consents": result.data or [], "count": len(result.data or [])}
