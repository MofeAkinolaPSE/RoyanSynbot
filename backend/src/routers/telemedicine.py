"""
Telemedicine Router — RoyanHealth / Royan Hospital
====================================================
Virtual consultation session management with Jitsi Meet integration stub.
In production, replace _generate_meeting_link() with your video provider SDK.

Endpoints:
  POST   /telemedicine/sessions              – Create session
  GET    /telemedicine/sessions              – List sessions (filter: status, doctor, date)
  GET    /telemedicine/sessions/{id}         – Session detail
  PATCH  /telemedicine/sessions/{id}/status  – Advance status
  GET    /telemedicine/sessions/{id}/join    – Get join links (patient + doctor)
"""
from __future__ import annotations

import logging
import os
import hashlib
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.db import db, audit_event
from src.middleware import verify_jwt
from src.constants import (
    TABLE_TELEMEDICINE_SESSIONS,
    TELEMEDICINE_STATUS_ALLOWED,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/telemedicine", tags=["Telemedicine"])

JITSI_BASE_URL = os.getenv("JITSI_BASE_URL", "https://meet.jit.si")

STATUSES = TELEMEDICINE_STATUS_ALLOWED
TRANSITIONS = {
    "scheduled":  {"active", "cancelled", "no_show"},
    "active":     {"completed", "cancelled"},
    "completed":  set(),
    "cancelled":  set(),
    "no_show":    set(),
}


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class SessionCreate(BaseModel):
    patient_id: int
    encounter_id: Optional[int] = None
    doctor_id: str = Field(..., min_length=1)
    scheduled_date: str                         # ISO date
    scheduled_time: str                         # HH:MM
    duration_minutes: int = Field(30, ge=5, le=120)
    visit_type: str = "consultation"            # consultation | follow_up | review | urgent
    chief_complaint: Optional[str] = None
    notes: Optional[str] = None

    model_config = {"extra": "ignore"}


class StatusAdvance(BaseModel):
    status: str
    notes: Optional[str] = None
    doctor_notes: Optional[str] = None          # clinical notes captured post-session
    prescriptions_issued: bool = False

    model_config = {"extra": "ignore"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_session(session_id: int) -> dict:
    r = db.table(TABLE_TELEMEDICINE_SESSIONS).select("*").eq("id", session_id).execute()
    if not r.data:
        raise HTTPException(status_code=404, detail=f"Telemedicine session {session_id} not found")
    return r.data[0]


def _generate_meeting_link(session_id: int, patient_id: int, doctor_id: str, date: str) -> str:
    """
    Generate a deterministic Jitsi room name for the session.
    In production: replace with Zoom/Whereby/Daily.co API call to create a real room.
    """
    room_token = hashlib.sha256(
        f"royan-{session_id}-{patient_id}-{doctor_id}-{date}".encode()
    ).hexdigest()[:16]
    return f"{JITSI_BASE_URL}/royan-{room_token}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/sessions", status_code=201)
def create_session(payload: SessionCreate, user=Depends(verify_jwt)):
    """Schedule a new telemedicine session."""
    meeting_link = _generate_meeting_link(0, payload.patient_id, payload.doctor_id, payload.scheduled_date)

    data = payload.model_dump(exclude_none=True)
    data["status"]       = "scheduled"
    data["meeting_link"] = meeting_link
    data["created_by"]   = user.get("sub") or "system"

    try:
        result = db.table(TABLE_TELEMEDICINE_SESSIONS).insert(data).execute()
    except Exception as exc:
        logger.error("Telemedicine session creation failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to create telemedicine session")

    session = result.data[0] if result.data else data
    # Regenerate link with real id if available
    if session.get("id"):
        link = _generate_meeting_link(session["id"], payload.patient_id, payload.doctor_id, payload.scheduled_date)
        db.table(TABLE_TELEMEDICINE_SESSIONS).update({"meeting_link": link}).eq("id", session["id"]).execute()
        session["meeting_link"] = link

    audit_event(
        "telemedicine_session_created",
        {"patient_id": payload.patient_id, "doctor_id": payload.doctor_id, "date": payload.scheduled_date},
        actor_id=user.get("sub"),
        subject_type="telemedicine_session",
        subject_id=str(session.get("id") or ""),
    )
    return {"ok": True, "session": session}


@router.get("/sessions")
def list_sessions(
    status: Optional[str] = Query(None),
    doctor_id: Optional[str] = Query(None),
    patient_id: Optional[int] = Query(None),
    date: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    user=Depends(verify_jwt),
):
    query = db.table(TABLE_TELEMEDICINE_SESSIONS).select("*").order("scheduled_date", desc=True).limit(limit)
    if status:     query = query.eq("status", status)
    if doctor_id:  query = query.eq("doctor_id", doctor_id)
    if patient_id: query = query.eq("patient_id", patient_id)
    if date:       query = query.eq("scheduled_date", date)
    result = query.execute()
    return {"sessions": result.data or [], "count": len(result.data or [])}


@router.get("/sessions/{session_id}")
def get_session(session_id: int, user=Depends(verify_jwt)):
    return {"session": _get_session(session_id)}


@router.patch("/sessions/{session_id}/status")
def advance_status(session_id: int, payload: StatusAdvance, user=Depends(verify_jwt)):
    """Advance session through the status state machine."""
    session = _get_session(session_id)
    current = session["status"]

    if payload.status not in STATUSES:
        raise HTTPException(status_code=422, detail=f"status must be one of {STATUSES}")
    if payload.status not in TRANSITIONS.get(current, set()):
        raise HTTPException(
            status_code=409,
            detail=f"Cannot transition '{current}' → '{payload.status}'. Allowed: {TRANSITIONS.get(current)}",
        )

    updates: dict = {"status": payload.status}
    if payload.notes:               updates["notes"]               = payload.notes
    if payload.doctor_notes:        updates["doctor_notes"]        = payload.doctor_notes
    if payload.prescriptions_issued: updates["prescriptions_issued"] = True
    if payload.status == "active":
        updates["started_at"] = _now()
    if payload.status == "completed":
        updates["ended_at"] = _now()

    db.table(TABLE_TELEMEDICINE_SESSIONS).update(updates).eq("id", session_id).execute()
    audit_event(
        "telemedicine_status_advanced",
        {"from": current, "to": payload.status},
        actor_id=user.get("sub"),
        subject_type="telemedicine_session",
        subject_id=str(session_id),
    )
    return {"ok": True, "session_id": session_id, "status": payload.status}


@router.get("/sessions/{session_id}/join")
def get_join_links(session_id: int, user=Depends(verify_jwt)):
    """Return the meeting join link for doctor and patient."""
    session = _get_session(session_id)
    link = session.get("meeting_link") or _generate_meeting_link(
        session_id, session["patient_id"], session["doctor_id"], session["scheduled_date"]
    )
    return {
        "session_id": session_id,
        "meeting_link": link,
        "doctor_link":  link + "?role=host",
        "patient_link": link + "?role=guest",
        "scheduled_date": session.get("scheduled_date"),
        "scheduled_time": session.get("scheduled_time"),
    }


@router.get("/stats")
def telemedicine_stats(user=Depends(verify_jwt)):
    result = db.table(TABLE_TELEMEDICINE_SESSIONS).select("status,visit_type,duration_minutes").execute()
    rows = result.data or []

    by_status: dict = {}
    by_type: dict = {}
    total_duration = 0
    completed_count = 0

    for r in rows:
        s = r.get("status") or "scheduled"
        t = r.get("visit_type") or "consultation"
        by_status[s] = by_status.get(s, 0) + 1
        by_type[t]   = by_type.get(t, 0) + 1
        if s == "completed" and r.get("duration_minutes"):
            total_duration  += r["duration_minutes"]
            completed_count += 1

    avg_duration = round(total_duration / completed_count, 1) if completed_count else 0

    return {
        "total": len(rows),
        "by_status": by_status,
        "by_visit_type": by_type,
        "avg_duration_minutes": avg_duration,
        "completed": by_status.get("completed", 0),
        "scheduled": by_status.get("scheduled", 0),
    }
