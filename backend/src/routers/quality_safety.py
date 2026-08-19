"""
Quality & Safety Router — RoyanHealth / Royan Hospital
=========================================================
Incident reporting, infection control surveillance, and HEFAMAA facility
inspection checklist management.

Endpoints:
  POST   /quality/incidents                      – Report incident
  GET    /quality/incidents                      – List incidents (filter: status, severity, category)
  GET    /quality/incidents/{id}                 – Incident detail
  PATCH  /quality/incidents/{id}/status          – Advance status
  PATCH  /quality/incidents/{id}/investigation   – Submit investigation findings

  POST   /quality/infection-control              – Log infection control event
  GET    /quality/infection-control              – List infection events
  GET    /quality/infection-control/stats        – Infection rates by type/ward

  POST   /quality/hefamaa                        – Submit HEFAMAA checklist
  GET    /quality/hefamaa                        – List HEFAMAA submissions
  GET    /quality/hefamaa/{id}                   – Checklist detail

  GET    /quality/stats                          – Dashboard KPIs
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.db import db, audit_event
from src.middleware import require_role
from src.constants import (
    TABLE_STAFF,
    TABLE_INCIDENT_REPORTS,
    TABLE_INFECTION_CONTROL,
    TABLE_HEFAMAA_CHECKLIST,
    INCIDENT_SEVERITY_ALLOWED,
    INCIDENT_STATUS_ALLOWED,
    INCIDENT_CATEGORY_ALLOWED,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/quality", tags=["Quality & Safety"])

SEVERITIES  = INCIDENT_SEVERITY_ALLOWED
STATUSES    = INCIDENT_STATUS_ALLOWED
CATEGORIES  = INCIDENT_CATEGORY_ALLOWED

# Nav gates the whole page to this role set (nav-items.ts) — all three
# sub-features here are uniformly clinical-safety-sensitive, unlike HR where
# only payroll needed a carve-out from the rest of the page.
QUALITY_ROLES = ("admin", "ops", "nurse", "doctor", "management", "quality_assurance")

STATUS_TRANSITIONS = {
    "reported":      {"under_review", "escalated", "closed"},
    "under_review":  {"investigated", "escalated", "closed"},
    "investigated":  {"closed", "escalated"},
    "escalated":     {"investigated", "closed"},
    "closed":        set(),
}

# The 19 HEFAMAA checklist booleans, grouped to match the 4 sections the
# frontend renders (HEFAMAA_SECTIONS in QualitySafety.tsx). Drives both the
# auto-score calculation and the nesting into the live `domain_scores` jsonb
# column — there are no individual boolean columns on the live table.
HEFAMAA_SECTION_FIELDS: dict[str, list[str]] = {
    "environment": [
        "clean_water_available", "waste_management_compliant", "fire_safety_equipment",
        "emergency_exits_clear", "adequate_lighting", "hand_hygiene_stations",
    ],
    "clinical": [
        "medication_storage_correct", "cold_chain_maintained", "sterilisation_process_compliant",
        "patient_records_secured", "informed_consent_documented", "infection_control_protocols_posted",
    ],
    "staffing": [
        "staff_registers_current", "cpd_records_maintained", "staff_uniforms_worn",
    ],
    "equipment": [
        "equipment_calibration_current", "biomedical_maintenance_records",
        "crash_cart_stocked", "oxygen_supply_available",
    ],
}


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class IncidentCreate(BaseModel):
    patient_id: Optional[int] = None
    encounter_id: Optional[int] = None
    ward: Optional[str] = None
    category: str = "other"
    severity: str = "minor"
    incident_date: Optional[str] = None        # ISO date
    incident_time: Optional[str] = None         # HH:MM
    description: str = Field(..., min_length=5)
    immediate_action_taken: Optional[str] = None
    reported_by: Optional[str] = None           # staff.id override; defaults to acting user's own
    witnesses: Optional[str] = None
    equipment_involved: Optional[str] = None
    contributing_factors: Optional[str] = None

    model_config = {"extra": "ignore"}


class IncidentStatusUpdate(BaseModel):
    status: str
    notes: Optional[str] = None

    model_config = {"extra": "ignore"}


class InvestigationUpdate(BaseModel):
    root_cause: Optional[str] = None
    contributing_factors: Optional[str] = None   # stored separately from the report-time field
    corrective_actions: Optional[str] = None
    preventive_actions: Optional[str] = None
    investigated_by: Optional[str] = None        # staff.id; defaults to acting user's own
    outcome: Optional[str] = None

    model_config = {"extra": "ignore"}


class InfectionEvent(BaseModel):
    patient_id: Optional[int] = None
    encounter_id: Optional[int] = None
    ward: Optional[str] = None
    event_type: str = Field(..., min_length=1)       # e.g. UTI, SSI, VAP, CLABSI
    pathogen: Optional[str] = None
    specimen_type: Optional[str] = None              # blood | urine | wound | sputum
    culture_result: Optional[str] = None
    onset_date: Optional[str] = None
    healthcare_associated: bool = True                # HAI vs community-acquired
    antibiotic_resistant: bool = False
    antibiotics_prescribed: Optional[str] = None
    isolation_precautions: Optional[str] = None        # contact | droplet | airborne
    outcome: Optional[str] = None                       # recovered | transferred | deceased
    notes: Optional[str] = None

    model_config = {"extra": "ignore"}


class HEFAMAAChecklist(BaseModel):
    assessment_date: Optional[str] = None
    assessor: Optional[str] = None               # staff.id; defaults to acting user's own
    department: Optional[str] = None

    # Section A — Environment & Infrastructure
    clean_water_available: bool = False
    waste_management_compliant: bool = False
    fire_safety_equipment: bool = False
    emergency_exits_clear: bool = False
    adequate_lighting: bool = False
    hand_hygiene_stations: bool = False

    # Section B — Clinical Standards
    medication_storage_correct: bool = False
    cold_chain_maintained: bool = False
    sterilisation_process_compliant: bool = False
    patient_records_secured: bool = False
    informed_consent_documented: bool = False
    infection_control_protocols_posted: bool = False

    # Section C — Staffing
    staff_registers_current: bool = False
    cpd_records_maintained: bool = False
    staff_uniforms_worn: bool = False

    # Section D — Equipment
    equipment_calibration_current: bool = False
    biomedical_maintenance_records: bool = False
    crash_cart_stocked: bool = False
    oxygen_supply_available: bool = False

    overall_score: Optional[int] = None   # computed if not manually entered (0-100)
    observations: Optional[str] = None
    recommendations: Optional[str] = None
    follow_up_date: Optional[str] = None

    model_config = {"extra": "ignore"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_incident(incident_id: str) -> dict:
    r = db.table(TABLE_INCIDENT_REPORTS).select("*").eq("id", incident_id).execute()
    if not r.data:
        raise HTTPException(status_code=404, detail=f"Incident {incident_id} not found")
    return r.data[0]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean(data: dict) -> dict:
    """Drop empty-string values alongside None — the frontend sends "" for
    untouched optional inputs (date/number fields especially), which
    `exclude_none=True` doesn't catch and Postgres rejects outright for
    typed columns like date/bigint."""
    return {k: v for k, v in data.items() if v != ""}


def _resolve_staff_id_for_user(user: dict) -> Optional[str]:
    """Map the acting JWT subject (an auth user id) to their own royan_staff.id,
    via royan_staff.user_id — the two are different uuid spaces, `sub` is never
    itself a valid royan_staff.id, so it can't be passed through directly."""
    sub = user.get("sub")
    if not sub:
        return None
    r = db.table(TABLE_STAFF).select("id").eq("user_id", sub).limit(1).execute()
    return r.data[0]["id"] if r.data else None


def _attach_assessor_name(rows: list[dict]) -> list[dict]:
    ids = list({r["assessor"] for r in rows if r.get("assessor")})
    if not ids:
        return rows
    staff = db.table(TABLE_STAFF).select("id,full_name").in_("id", ids).execute()
    by_id = {s["id"]: s.get("full_name") for s in (staff.data or [])}
    for r in rows:
        r["assessor_name"] = by_id.get(r.get("assessor"))
    return rows


def _auto_score(checklist: HEFAMAAChecklist) -> int:
    """Calculate HEFAMAA compliance score as percentage of True items."""
    all_fields = [f for fields in HEFAMAA_SECTION_FIELDS.values() for f in fields]
    passed = sum(1 for f in all_fields if getattr(checklist, f, False))
    return round(passed / len(all_fields) * 100)


def _nest_domain_scores(checklist: HEFAMAAChecklist) -> dict:
    return {
        section: {f: getattr(checklist, f) for f in fields}
        for section, fields in HEFAMAA_SECTION_FIELDS.items()
    }


# ---------------------------------------------------------------------------
# Incident Endpoints
# ---------------------------------------------------------------------------

@router.post("/incidents", status_code=201)
async def report_incident(payload: IncidentCreate, user=Depends(require_role(*QUALITY_ROLES))):
    """Report a new clinical incident or near-miss."""
    if payload.severity not in SEVERITIES:
        raise HTTPException(status_code=422, detail=f"severity must be one of {sorted(SEVERITIES)}")
    if payload.category not in CATEGORIES:
        raise HTTPException(status_code=422, detail=f"category must be one of {sorted(CATEGORIES)}")

    data = _clean(payload.model_dump(exclude_none=True))
    data.pop("reported_by", None)
    data["status"] = "reported"
    resolved = payload.reported_by or _resolve_staff_id_for_user(user)
    if resolved:
        data["reported_by"] = resolved
    if "incident_date" not in data:
        data["incident_date"] = _now()[:10]

    try:
        result = db.table(TABLE_INCIDENT_REPORTS).insert(data).execute()
    except Exception as exc:
        logger.error("Incident report failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to report incident")

    incident = result.data[0] if result.data else data
    audit_event(
        "incident_reported",
        {"category": payload.category, "severity": payload.severity},
        actor_id=user.get("sub"),
        subject_type="incident",
        subject_id=str(incident.get("id") or ""),
    )
    return {"ok": True, "incident": incident}


@router.get("/incidents")
async def list_incidents(
    status: Optional[str]   = Query(None),
    severity: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    ward: Optional[str]     = Query(None),
    patient_id: Optional[int] = Query(None),
    limit: int              = Query(50, ge=1, le=200),
    user=Depends(require_role(*QUALITY_ROLES)),
):
    query = db.table(TABLE_INCIDENT_REPORTS).select("*").order("incident_date", desc=True).limit(limit)
    if status:     query = query.eq("status", status)
    if severity:   query = query.eq("severity", severity)
    if category:   query = query.eq("category", category)
    if ward:       query = query.eq("ward", ward)
    if patient_id: query = query.eq("patient_id", patient_id)
    result = query.execute()
    return {"incidents": result.data or [], "count": len(result.data or [])}


@router.get("/incidents/{incident_id}")
async def get_incident(incident_id: str, user=Depends(require_role(*QUALITY_ROLES))):
    return {"incident": _get_incident(incident_id)}


@router.patch("/incidents/{incident_id}/status")
async def update_incident_status(incident_id: str, payload: IncidentStatusUpdate, user=Depends(require_role(*QUALITY_ROLES))):
    incident = _get_incident(incident_id)
    current = incident["status"]
    if payload.status not in STATUSES:
        raise HTTPException(status_code=422, detail=f"status must be one of {sorted(STATUSES)}")
    if payload.status not in STATUS_TRANSITIONS.get(current, set()):
        raise HTTPException(
            status_code=409,
            detail=f"Cannot transition '{current}' → '{payload.status}'. Allowed: {STATUS_TRANSITIONS.get(current)}",
        )
    updates: dict = {"status": payload.status}
    if payload.notes:
        updates["status_notes"] = payload.notes
    if payload.status == "closed":
        updates["closed_at"] = _now()
    db.table(TABLE_INCIDENT_REPORTS).update(updates).eq("id", incident_id).execute()
    audit_event("incident_status_updated", {"from": current, "to": payload.status},
                actor_id=user.get("sub"), subject_type="incident", subject_id=str(incident_id))
    return {"ok": True, "incident_id": incident_id, "status": payload.status}


@router.patch("/incidents/{incident_id}/investigation")
async def submit_investigation(incident_id: str, payload: InvestigationUpdate, user=Depends(require_role(*QUALITY_ROLES))):
    _get_incident(incident_id)
    updates = _clean(payload.model_dump(exclude_none=True))
    if not updates:
        raise HTTPException(status_code=422, detail="No fields to update")
    if "contributing_factors" in updates:
        updates["investigation_contributing_factors"] = updates.pop("contributing_factors")
    if not updates.get("investigated_by"):
        resolved = _resolve_staff_id_for_user(user)
        if resolved:
            updates["investigated_by"] = resolved
        else:
            updates.pop("investigated_by", None)
    updates["status"] = "investigated"
    updates["investigation_completed_at"] = _now()
    db.table(TABLE_INCIDENT_REPORTS).update(updates).eq("id", incident_id).execute()
    audit_event("incident_investigated", {}, actor_id=user.get("sub"),
                subject_type="incident", subject_id=str(incident_id))
    return {"ok": True, "incident_id": incident_id}


# ---------------------------------------------------------------------------
# Infection Control
# ---------------------------------------------------------------------------

@router.post("/infection-control", status_code=201)
async def log_infection_event(payload: InfectionEvent, user=Depends(require_role(*QUALITY_ROLES))):
    data = _clean(payload.model_dump(exclude_none=True))
    resolved = _resolve_staff_id_for_user(user)
    if resolved:
        data["reported_by"] = resolved
    if "onset_date" not in data:
        data["onset_date"] = _now()[:10]
    try:
        result = db.table(TABLE_INFECTION_CONTROL).insert(data).execute()
    except Exception as exc:
        logger.error("Infection control log failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to log infection event")
    record = result.data[0] if result.data else data
    audit_event("infection_event_logged", {"type": payload.event_type, "hai": payload.healthcare_associated},
                actor_id=user.get("sub"), subject_type="infection_event", subject_id=str(record.get("id") or ""))
    return {"ok": True, "record": record}


@router.get("/infection-control")
async def list_infection_events(
    ward: Optional[str] = Query(None),
    event_type: Optional[str] = Query(None),
    healthcare_associated: Optional[bool] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    user=Depends(require_role(*QUALITY_ROLES)),
):
    query = db.table(TABLE_INFECTION_CONTROL).select("*").order("onset_date", desc=True).limit(limit)
    if ward:               query = query.eq("ward", ward)
    if event_type:         query = query.eq("event_type", event_type)
    if healthcare_associated is not None:
        query = query.eq("healthcare_associated", healthcare_associated)
    result = query.execute()
    return {"events": result.data or [], "count": len(result.data or [])}


@router.get("/infection-control/stats")
async def infection_stats(user=Depends(require_role(*QUALITY_ROLES))):
    result = db.table(TABLE_INFECTION_CONTROL).select(
        "event_type,ward,healthcare_associated,antibiotic_resistant,outcome"
    ).execute()
    rows = result.data or []
    by_type: dict = {}
    by_ward: dict = {}
    by_outcome: dict = {}
    hai_count = 0
    amr_count = 0
    for r in rows:
        t = r.get("event_type") or "other"
        w = r.get("ward") or "unknown"
        o = r.get("outcome") or "unknown"
        by_type[t]    = by_type.get(t, 0) + 1
        by_ward[w]    = by_ward.get(w, 0) + 1
        by_outcome[o] = by_outcome.get(o, 0) + 1
        if r.get("healthcare_associated"): hai_count += 1
        if r.get("antibiotic_resistant"):  amr_count += 1
    return {
        "total": len(rows),
        "hai_count": hai_count,
        "amr_count": amr_count,
        "by_infection_type": by_type,
        "by_ward": by_ward,
        "by_outcome": by_outcome,
    }


# ---------------------------------------------------------------------------
# HEFAMAA Checklist
# ---------------------------------------------------------------------------

@router.post("/hefamaa", status_code=201)
async def submit_hefamaa(payload: HEFAMAAChecklist, user=Depends(require_role(*QUALITY_ROLES))):
    score = payload.overall_score if payload.overall_score is not None else _auto_score(payload)
    data = _clean({
        "overall_score": score,
        "domain_scores": _nest_domain_scores(payload),
        "assessor": payload.assessor or _resolve_staff_id_for_user(user),
        "assessment_date": payload.assessment_date or _now()[:10],
        "department": payload.department,
        "observations": payload.observations,
        "recommendations": payload.recommendations,
        "follow_up_date": payload.follow_up_date,
    })
    try:
        result = db.table(TABLE_HEFAMAA_CHECKLIST).insert(data).execute()
    except Exception as exc:
        logger.error("HEFAMAA submission failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to submit HEFAMAA checklist")
    record = result.data[0] if result.data else data
    audit_event("hefamaa_submitted", {"score": score, "department": payload.department},
                actor_id=user.get("sub"), subject_type="hefamaa", subject_id=str(record.get("id") or ""))
    return {"ok": True, "record": record, "score": score}


@router.get("/hefamaa")
async def list_hefamaa(
    department: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    user=Depends(require_role(*QUALITY_ROLES)),
):
    query = db.table(TABLE_HEFAMAA_CHECKLIST).select(
        "id,assessment_date,assessor,department,overall_score,follow_up_date"
    ).order("assessment_date", desc=True).limit(limit)
    if department:
        query = query.eq("department", department)
    result = query.execute()
    checklists = _attach_assessor_name(result.data or [])
    return {"checklists": checklists, "count": len(checklists)}


@router.get("/hefamaa/{checklist_id}")
async def get_hefamaa(checklist_id: str, user=Depends(require_role(*QUALITY_ROLES))):
    r = db.table(TABLE_HEFAMAA_CHECKLIST).select("*").eq("id", checklist_id).execute()
    if not r.data:
        raise HTTPException(status_code=404, detail="HEFAMAA checklist not found")
    return {"checklist": r.data[0]}


# ---------------------------------------------------------------------------
# Quality Dashboard Stats
# ---------------------------------------------------------------------------

@router.get("/stats")
async def quality_stats(user=Depends(require_role(*QUALITY_ROLES))):
    inc_result = db.table(TABLE_INCIDENT_REPORTS).select("severity,status,category").execute()
    incidents = inc_result.data or []

    by_severity: dict = {}
    by_status: dict = {}
    by_category: dict = {}
    open_count = 0

    for i in incidents:
        s  = i.get("severity") or "minor"
        st = i.get("status")   or "reported"
        c  = i.get("category") or "other"
        by_severity[s]  = by_severity.get(s, 0)  + 1
        by_status[st]   = by_status.get(st, 0)   + 1
        by_category[c]  = by_category.get(c, 0)  + 1
        if st not in ("closed",):
            open_count += 1

    inf_result = db.table(TABLE_INFECTION_CONTROL).select("healthcare_associated").execute()
    hai_total  = sum(1 for r in (inf_result.data or []) if r.get("healthcare_associated"))

    hef_result = db.table(TABLE_HEFAMAA_CHECKLIST).select("overall_score").execute()
    hef_rows   = hef_result.data or []
    avg_score  = round(sum(r["overall_score"] for r in hef_rows if r.get("overall_score")) / len(hef_rows), 1) if hef_rows else 0

    return {
        "incidents": {
            "total": len(incidents),
            "open": open_count,
            "by_severity": by_severity,
            "by_status": by_status,
            "by_category": by_category,
        },
        "infection": {"hai_total": hai_total},
        "hefamaa": {"submissions": len(hef_rows), "avg_score": avg_score},
    }
