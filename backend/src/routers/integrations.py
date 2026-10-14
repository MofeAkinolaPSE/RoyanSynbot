"""
Integrations Router — RoyanHealth / Royan Hospital
=====================================================
PACS radiology image archive integration (stub) and QR kiosk patient check-in.

Endpoints:
  POST  /integrations/pacs/study               – Push imaging study to PACS
  GET   /integrations/pacs/study/{accession}   – Retrieve PACS study metadata
  GET   /integrations/pacs/studies             – List PACS study records
  POST  /integrations/kiosk/checkin            – QR kiosk patient check-in
  GET   /integrations/kiosk/queue-status       – Live queue for kiosk display
  GET   /integrations/kiosk/checkins           – List today's kiosk check-ins
"""
from __future__ import annotations

import hashlib
import logging
import os
import uuid
from datetime import date, datetime, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.db import db, audit_event
from src.middleware import verify_jwt
from src.constants import (
    TABLE_PACS_STUDIES,
    TABLE_KIOSK_CHECKINS,
    TABLE_PATIENTS,
    TABLE_ENCOUNTERS,
    PACS_STATUS_ALLOWED,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/integrations", tags=["Integrations"])

# ── Env config ──────────────────────────────────────────────────────────────
PACS_BASE_URL  = os.getenv("PACS_BASE_URL", "")
PACS_API_KEY   = os.getenv("PACS_API_KEY",  "")
_PACS_STUB     = not (PACS_BASE_URL and PACS_API_KEY)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today() -> str:
    return date.today().isoformat()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class PACSStudyPush(BaseModel):
    radiology_order_id: Optional[int]  = None
    encounter_id:       Optional[int]  = None
    patient_id:         Optional[int]  = None
    modality:           str            = "xray"
    study_date:         Optional[str]  = None
    body_part:          Optional[str]  = None
    dicom_series_uid:   Optional[str]  = None
    file_url:           Optional[str]  = None
    notes:              Optional[str]  = None

    model_config = {"extra": "ignore"}


class KioskCheckin(BaseModel):
    qr_code:      Optional[str] = None
    mrn:          Optional[str] = None
    phone:        Optional[str] = None
    appointment_id: Optional[int] = None
    checkin_type: str = "walk_in"

    model_config = {"extra": "ignore"}


# ---------------------------------------------------------------------------
# PACS helpers
# ---------------------------------------------------------------------------

def _generate_accession(study_id: int | str) -> str:
    token = hashlib.sha256(f"royan-pacs-{study_id}".encode()).hexdigest()[:12].upper()
    return f"ACC-{token}"


async def _pacs_push(study: dict) -> dict:
    """Send study metadata to PACS. Returns stub response when PACS_BASE_URL absent."""
    if _PACS_STUB:
        return {
            "pacs_study_id":    f"STUB-{uuid.uuid4().hex[:8].upper()}",
            "status":           "available",
            "stub":             True,
            "viewer_url":       None,
        }
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(
            f"{PACS_BASE_URL}/studies",
            headers={"X-Api-Key": PACS_API_KEY},
            json=study,
        )
    if resp.status_code not in (200, 201):
        raise HTTPException(status_code=502, detail=f"PACS error: {resp.text}")
    return resp.json()


async def _pacs_fetch(accession: str) -> dict:
    if _PACS_STUB:
        return {"accession_number": accession, "status": "available", "stub": True}
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"{PACS_BASE_URL}/studies/{accession}",
            headers={"X-Api-Key": PACS_API_KEY},
        )
    if resp.status_code == 404:
        raise HTTPException(status_code=404, detail="Study not found in PACS")
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"PACS fetch error: {resp.text}")
    return resp.json()


# ---------------------------------------------------------------------------
# PACS Endpoints
# ---------------------------------------------------------------------------

@router.post("/pacs/study", status_code=201)
async def push_pacs_study(payload: PACSStudyPush, user=Depends(verify_jwt)):
    """Push an imaging study to the PACS archive (stub when PACS_BASE_URL not configured)."""
    data = payload.model_dump(exclude_none=True)
    if "study_date" not in data:
        data["study_date"] = _today()
    data["status"]       = "pending"
    data["submitted_by"] = user.get("sub") or "system"
    data["submitted_at"] = _now()

    try:
        result = db.table(TABLE_PACS_STUDIES).insert(data).execute()
    except Exception as exc:
        logger.error("PACS record insert failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to save PACS study record")

    record   = result.data[0] if result.data else data
    study_id = record.get("id", uuid.uuid4().hex[:8])

    accession    = data.get("dicom_series_uid") or _generate_accession(study_id)
    pacs_result  = await _pacs_push({**data, "accession_number": accession, "local_id": study_id})

    db.table(TABLE_PACS_STUDIES).update({
        "accession_number": accession,
        "pacs_study_id":    pacs_result.get("pacs_study_id"),
        "viewer_url":       pacs_result.get("viewer_url"),
        "status":           pacs_result.get("status", "sent"),
    }).eq("id", study_id).execute()

    audit_event("pacs_study_pushed", {"modality": payload.modality, "accession": accession},
                actor_id=user.get("sub"), subject_type="pacs_study", subject_id=str(study_id))

    return {
        "ok":               True,
        "study_id":         study_id,
        "accession_number": accession,
        "pacs_result":      pacs_result,
        "stub":             _PACS_STUB,
    }


@router.get("/pacs/study/{accession}")
async def get_pacs_study(accession: str, user=Depends(verify_jwt)):
    """Retrieve PACS study metadata by accession number."""
    r = db.table(TABLE_PACS_STUDIES).select("*").eq("accession_number", accession).execute()
    if not r.data:
        raise HTTPException(status_code=404, detail="Study not found locally")

    pacs_data = await _pacs_fetch(accession)
    return {"local_record": r.data[0], "pacs_data": pacs_data}


@router.get("/pacs/studies")
def list_pacs_studies(
    patient_id:         Optional[int] = Query(None),
    radiology_order_id: Optional[int] = Query(None),
    status:             Optional[str] = Query(None),
    limit:              int           = Query(50, ge=1, le=200),
    user=Depends(verify_jwt),
):
    q = db.table(TABLE_PACS_STUDIES).select(
        "id,accession_number,modality,body_part,study_date,status,viewer_url,patient_id,encounter_id,radiology_order_id"
    ).order("study_date", desc=True).limit(limit)
    if patient_id:          q = q.eq("patient_id",          patient_id)
    if radiology_order_id:  q = q.eq("radiology_order_id",  radiology_order_id)
    if status:              q = q.eq("status",               status)
    result = q.execute()
    return {"studies": result.data or [], "count": len(result.data or [])}


# ---------------------------------------------------------------------------
# Kiosk Check-in Endpoints
# ---------------------------------------------------------------------------

@router.post("/kiosk/checkin", status_code=201)
def kiosk_checkin(payload: KioskCheckin):
    """
    QR kiosk self-service patient check-in.
    Accepts QR code, MRN, or phone number to identify the patient.
    No JWT required — this endpoint is publicly accessible from kiosk terminals.
    """
    patient = None

    if payload.mrn:
        r = db.table(TABLE_PATIENTS).select("id,first_name,last_name,mrn").eq("mrn", payload.mrn).execute()
        patient = r.data[0] if r.data else None

    if not patient and payload.phone:
        r = db.table(TABLE_PATIENTS).select("id,first_name,last_name,mrn").eq("phone", payload.phone).execute()
        patient = r.data[0] if r.data else None

    if not patient and payload.qr_code:
        # QR code format: "ROYAN-MRN-<mrn>" or raw MRN
        mrn_from_qr = payload.qr_code.replace("ROYAN-MRN-", "").strip()
        r = db.table(TABLE_PATIENTS).select("id,first_name,last_name,mrn").eq("mrn", mrn_from_qr).execute()
        patient = r.data[0] if r.data else None

    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found. Please register at the front desk.")

    checkin_record = {
        "patient_id":     patient["id"],
        "mrn":            patient.get("mrn"),
        "appointment_id": payload.appointment_id,
        "checkin_type":   payload.checkin_type,
        "checkin_time":   _now(),
        "checkin_date":   _today(),
        "status":         "checked_in",
    }
    try:
        result = db.table(TABLE_KIOSK_CHECKINS).insert(checkin_record).execute()
    except Exception as exc:
        logger.error("Kiosk check-in failed: %s", exc)
        raise HTTPException(status_code=500, detail="Check-in failed. Please see front desk.")

    record = result.data[0] if result.data else checkin_record

    # Find active encounters to get queue position. Live queue = native
    # encounters only (external_source IS NULL) — Hope historical data must
    # never surface as an active encounter (see queue_clinical.py's
    # list_encounters for the same invariant).
    try:
        enc = db.table(TABLE_ENCOUNTERS).select("id,status").eq("patient_id", patient["id"]) \
                .not_.eq("status", "discharged").is_("external_source", None) \
                .order("created_at", desc=True).limit(1).execute()
        encounter = enc.data[0] if enc.data else None
    except Exception as exc:
        logger.error("Kiosk check-in: active-encounter lookup failed: %s", exc)
        encounter = None

    return {
        "ok":          True,
        "checkin_id":  record.get("id"),
        "patient": {
            "id":   patient["id"],
            "name": f"{patient.get('first_name', '')} {patient.get('last_name', '')}".strip(),
            "mrn":  patient.get("mrn"),
        },
        "message": f"Welcome {patient.get('first_name', '')}! You have been checked in. Please take a seat.",
        "encounter": encounter,
    }


@router.get("/kiosk/queue-status")
def kiosk_queue_status():
    """
    Live queue status for kiosk display board.
    No JWT required — public display endpoint.
    """
    try:
        # Live queue = native encounters only (external_source IS NULL) — see
        # queue_clinical.py's list_encounters for the same invariant.
        enc = db.table(TABLE_ENCOUNTERS).select(
            "id,status,triage_level,created_at"
        ).not_.eq("status", "discharged").is_("external_source", None) \
         .order("created_at").execute()
        active = enc.data or []
    except Exception as exc:
        logger.error("Kiosk queue-status: active-encounter lookup failed: %s", exc)
        active = []

    waiting  = [e for e in active if e.get("status") in ("patient_registered", "triaged")]
    in_consult = [e for e in active if e.get("status") == "consulting"]

    try:
        checkins_today = db.table(TABLE_KIOSK_CHECKINS).select(
            "id,checkin_time"
        ).eq("checkin_date", _today()).execute()
        today_count = len(checkins_today.data or [])
    except Exception as exc:
        logger.error("Kiosk queue-status: today's checkin count failed: %s", exc)
        today_count = 0

    return {
        "queue": {
            "total_active":     len(active),
            "waiting":          len(waiting),
            "in_consult":       len(in_consult),
            "checkins_today":   today_count,
        },
        "as_of": _now(),
    }


@router.get("/kiosk/checkins")
def list_kiosk_checkins(
    checkin_date: Optional[str] = Query(None, description="ISO date, defaults to today"),
    limit:        int           = Query(100, ge=1, le=500),
    user=Depends(verify_jwt),
):
    q = db.table(TABLE_KIOSK_CHECKINS).select(
        "id,patient_id,mrn,checkin_type,checkin_time,status,appointment_id"
    ).order("checkin_time", desc=True).limit(limit)
    q = q.eq("checkin_date", checkin_date or _today())
    result = q.execute()
    return {"checkins": result.data or [], "count": len(result.data or [])}


@router.get("/queue/display")
def queue_display(department: Optional[str] = Query(None)):
    """
    Public display board data — no JWT required.
    Returns called, now-serving, and next-up waiting encounters with queue numbers.
    Patient names are omitted for privacy — queue numbers only.
    """
    today = _today()
    try:
        conn = db.pool.getconn()
        try:
            cur = conn.cursor()
            # department is bound as a parameter: this endpoint is public (the waiting-room screen), and the
            # value used to be pasted into the SQL, which let anyone run their own query.
            cur.execute("""
                SELECT status, queue_number, consulting_room, called_at, consultation_at
                FROM public.royan_encounters
                WHERE external_source IS NULL
                  AND created_at::date = %s
                  AND status IN ('called', 'consulting', 'patient_registered', 'triaged', 'nurse_assessment')
                  AND (%s::text IS NULL OR department = %s)
                ORDER BY COALESCE(called_at, consultation_at, created_at) ASC
                LIMIT 60
            """, (today, department, department))
            rows = cur.fetchall()
        finally:
            db.pool.putconn(conn)
    except Exception as exc:
        logger.warning("queue_display raw SQL failed: %s", exc)
        rows = []

    called, now_serving, waiting_next = [], [], []
    for status, queue_number, room, called_at, consult_at in rows:
        entry = {"queue_number": queue_number or "—", "room": room}
        if status == "called":
            called.append(entry)
        elif status == "consulting":
            now_serving.append(entry)
        else:
            waiting_next.append({"queue_number": queue_number or "—"})

    return {
        "called":       called[:6],
        "now_serving":  now_serving[:6],
        "waiting_next": waiting_next[:10],
        "as_of":        _now(),
    }
