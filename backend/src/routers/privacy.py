"""NDPA 2023 Privacy & Governance Router — Chapter 18 of the blueprint.

Implements the Data Subject Rights framework required by Nigeria's Data
Protection Act 2023 for SynbotHealth:
  - Patient consent management (per-purpose, withdrawable)
  - Data Subject Access Requests (DSAR)
  - Data erasure / anonymisation requests
  - PHI audit trail inspection (admin-only)
  - Breach notification log

Endpoints:
  POST /api/v1/privacy/consent/{patient_id}          Record patient consent
  GET  /api/v1/privacy/consent/{patient_id}          List active consents
  DELETE /api/v1/privacy/consent/{patient_id}/{type} Withdraw consent
  POST /api/v1/privacy/dsar                           Submit data access request
  GET  /api/v1/privacy/dsar/{request_id}             Check DSAR status
  POST /api/v1/privacy/erasure/{patient_id}          Request data anonymisation
  GET  /api/v1/privacy/phi-audit/{patient_id}        PHI access audit trail (admin)
  GET  /api/v1/privacy/compliance-summary            NDPA compliance dashboard
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone, date
from typing import Any, Dict, List, Optional

import psycopg2.extras
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.db import db, get_psycopg_dsn
from src.middleware import verify_jwt, require_role
from src.privacy import ALL_PHI, PHI_DIRECT, check_consent, log_phi_access
from src.services.consent_service import VALID_PURPOSES, _PURPOSE_MAP

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/privacy", tags=["Privacy & NDPA"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_conn():
    return db.pool.getconn()


def _put_conn(conn):
    db.pool.putconn(conn)


# ─────────────────────────────────────────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────────────────────────────────────────

VALID_CONSENT_TYPES = {
    "data_processing", "marketing", "research",
    "treatment", "surgical", "telemedicine",
    "third_party_sharing", "photography",
}


class ConsentGrantRequest(BaseModel):
    consent_type: str
    notes: Optional[str] = None
    expiry_date: Optional[str] = None   # ISO date YYYY-MM-DD


class DSARRequest(BaseModel):
    patient_id: int
    request_type: str = Field(..., description="access | rectification | erasure | portability | restriction")
    reason: Optional[str] = None
    contact_email: Optional[str] = None


class ErasureRequest(BaseModel):
    reason: str = Field(..., min_length=10, description="Clinical or legal reason for erasure")
    fields_to_anonymise: List[str] = Field(
        default_factory=lambda: ["phone", "email", "address", "next_of_kin_name", "next_of_kin_phone"]
    )


# ─────────────────────────────────────────────────────────────────────────────
# Consent — grant
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/consent/{patient_id}", status_code=201)
async def grant_consent(
    patient_id: int,
    payload: ConsentGrantRequest,
    request_obj=None,
    user=Depends(verify_jwt),
):
    """Record a patient's explicit consent for a specific processing purpose."""
    if payload.consent_type not in VALID_CONSENT_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid consent_type. Must be one of: {sorted(VALID_CONSENT_TYPES)}",
        )

    patient = db.table("royan_patients").select("id,mrn").eq("id", patient_id).execute()
    if not patient.data:
        raise HTTPException(status_code=404, detail=f"Patient {patient_id} not found")

    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO public.royan_patient_consent
                    (patient_id, consent_type, is_given, given_at, expiry_date, notes, recorded_by)
                VALUES (%s, %s, true, now(), %s, %s, %s)
                ON CONFLICT DO NOTHING
                RETURNING id
                """,
                (
                    patient_id,
                    payload.consent_type,
                    payload.expiry_date,
                    payload.notes,
                    user.get("name") or user.get("sub"),
                ),
            )
            row = cur.fetchone()
            consent_id = row[0] if row else None
        conn.commit()
    finally:
        _put_conn(conn)

    logger.info(
        "Consent granted: patient=%s type=%s by=%s",
        patient_id, payload.consent_type, user.get("sub"),
    )
    return {
        "success": True,
        "consent_id": consent_id,
        "patient_id": patient_id,
        "consent_type": payload.consent_type,
        "granted_at": _now(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Consent — list active
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/consent/{patient_id}")
async def list_consents(patient_id: int, user=Depends(verify_jwt)):
    """List all active (non-withdrawn) consents for a patient."""
    conn = _get_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, consent_type, is_given, given_at, withdrawn_at, expiry_date, notes, recorded_by
                FROM public.royan_patient_consent
                WHERE patient_id = %s
                ORDER BY given_at DESC
                """,
                (patient_id,),
            )
            rows = cur.fetchall()
    finally:
        _put_conn(conn)

    today = date.today().isoformat()
    consents = []
    for r in rows:
        active = (
            r["is_given"]
            and r["withdrawn_at"] is None
            and (r["expiry_date"] is None or str(r["expiry_date"]) >= today)
        )
        consents.append({
            "id": r["id"],
            "consent_type": r["consent_type"],
            "is_given": r["is_given"],
            "is_active": active,
            "given_at": str(r["given_at"]) if r["given_at"] else None,
            "withdrawn_at": str(r["withdrawn_at"]) if r["withdrawn_at"] else None,
            "expiry_date": str(r["expiry_date"]) if r["expiry_date"] else None,
            "notes": r["notes"],
        })

    return {
        "patient_id": patient_id,
        "total": len(consents),
        "active_count": sum(1 for c in consents if c["is_active"]),
        "consents": consents,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Consent — check (used by other services before serving PHI)
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/consent/check/{patient_id}/{purpose}")
async def check_consent_endpoint(
    patient_id: int,
    purpose: str,
    user=Depends(verify_jwt),
):
    """Check whether a patient has active consent for a given purpose.

    Returns {granted, consent_type, expires_at} — used by clinical UI before
    initiating research exports, telemedicine sessions, or marketing messages.

    Valid purposes: data_processing, research, third_party, marketing,
                    telemedicine, surgery, photography, treatment
    """
    if purpose not in VALID_PURPOSES:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown purpose '{purpose}'. Valid: {sorted(VALID_PURPOSES)}",
        )
    consent_type = _PURPOSE_MAP[purpose]

    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT is_given, withdrawn_at, expiry_date
                FROM public.royan_patient_consent
                WHERE patient_id = %s
                  AND consent_type = %s
                  AND is_given = true
                  AND withdrawn_at IS NULL
                  AND (expiry_date IS NULL OR expiry_date >= CURRENT_DATE)
                ORDER BY given_at DESC
                LIMIT 1
                """,
                (patient_id, consent_type),
            )
            row = cur.fetchone()
    finally:
        _put_conn(conn)

    granted = bool(row)
    expires_at = str(row[2]) if (row and row[2]) else None

    return {
        "patient_id": patient_id,
        "purpose": purpose,
        "consent_type": consent_type,
        "granted": granted,
        "expires_at": expires_at,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Consent — withdraw
# ─────────────────────────────────────────────────────────────────────────────

@router.delete("/consent/{patient_id}/{consent_type}", status_code=200)
async def withdraw_consent(
    patient_id: int,
    consent_type: str,
    user=Depends(verify_jwt),
):
    """Withdraw a previously granted consent. Sets withdrawn_at = now()."""
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE public.royan_patient_consent
                SET withdrawn_at = now()
                WHERE patient_id = %s
                  AND consent_type = %s
                  AND is_given = true
                  AND withdrawn_at IS NULL
                """,
                (patient_id, consent_type),
            )
            affected = cur.rowcount
        conn.commit()
    finally:
        _put_conn(conn)

    if affected == 0:
        raise HTTPException(
            status_code=404,
            detail=f"No active consent of type '{consent_type}' found for patient {patient_id}",
        )

    logger.info("Consent withdrawn: patient=%s type=%s by=%s", patient_id, consent_type, user.get("sub"))
    return {"success": True, "withdrawn_at": _now(), "affected_rows": affected}


# ─────────────────────────────────────────────────────────────────────────────
# Data Subject Access Request (DSAR)
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/dsar", status_code=201)
async def submit_dsar(payload: DSARRequest, user=Depends(verify_jwt)):
    """Submit a Data Subject Access Request. Logged for 30-day processing SLA."""
    valid_types = {"access", "rectification", "erasure", "portability", "restriction"}
    if payload.request_type not in valid_types:
        raise HTTPException(
            status_code=422,
            detail=f"request_type must be one of: {sorted(valid_types)}",
        )

    patient = db.table("royan_patients").select("id,mrn,first_name,last_name").eq(
        "id", payload.patient_id
    ).execute()
    if not patient.data:
        raise HTTPException(status_code=404, detail=f"Patient {payload.patient_id} not found")

    request_id = str(uuid.uuid4())
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO public.royan_audit_logs
                    (entity_type, entity_id, action, actor, details, created_at)
                VALUES ('patient', %s, 'dsar_submitted', %s, %s, now())
                """,
                (
                    payload.patient_id,
                    user.get("sub", "patient"),
                    json.dumps({
                        "request_id": request_id,
                        "request_type": payload.request_type,
                        "reason": payload.reason,
                        "contact_email": payload.contact_email,
                        "sla_deadline": _sla_deadline(),
                    }),
                ),
            )
        conn.commit()
    finally:
        _put_conn(conn)

    return {
        "success": True,
        "request_id": request_id,
        "request_type": payload.request_type,
        "patient_id": payload.patient_id,
        "submitted_at": _now(),
        "sla_deadline": _sla_deadline(),
        "status": "pending",
        "message": "Your DSAR has been logged and will be processed within 30 days per NDPA 2023.",
    }


def _sla_deadline() -> str:
    from datetime import timedelta
    return (datetime.now(timezone.utc) + timedelta(days=30)).date().isoformat()


# ─────────────────────────────────────────────────────────────────────────────
# Data Anonymisation (soft erasure — preserves clinical record, masks PHI)
# ─────────────────────────────────────────────────────────────────────────────

ANONYMISABLE_FIELDS = {"phone", "email", "address", "next_of_kin_name", "next_of_kin_phone"}


@router.post("/erasure/{patient_id}")
async def request_erasure(
    patient_id: int,
    payload: ErasureRequest,
    user=Depends(require_role("admin", "dpo")),
):
    """Anonymise direct identifiers on a patient record (NDPA right to erasure).

    Medical/clinical records are NEVER deleted — only contact identifiers are
    replaced with anonymised values as required by NDPA 2023 §42 (which permits
    retention of records required by medical law).
    """
    patient = db.table("royan_patients").select("id,mrn").eq("id", patient_id).execute()
    if not patient.data:
        raise HTTPException(status_code=404, detail=f"Patient {patient_id} not found")

    invalid = set(payload.fields_to_anonymise) - ANONYMISABLE_FIELDS
    if invalid:
        raise HTTPException(
            status_code=422,
            detail=f"Cannot anonymise clinical fields: {invalid}. Allowed: {ANONYMISABLE_FIELDS}",
        )

    anonymised_vals: Dict[str, str] = {
        "phone":              f"ANON-{patient_id}",
        "email":              f"anon-{patient_id}@deleted.invalid",
        "address":            "[ANONYMISED]",
        "next_of_kin_name":   "[ANONYMISED]",
        "next_of_kin_phone":  "[ANONYMISED]",
    }

    updates = {f: anonymised_vals[f] for f in payload.fields_to_anonymise if f in anonymised_vals}

    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            set_clause = ", ".join(f"{col} = %s" for col in updates)
            vals = list(updates.values()) + [patient_id]
            cur.execute(
                f"UPDATE public.royan_patients SET {set_clause} WHERE id = %s",
                vals,
            )
            # Log the erasure action
            cur.execute(
                """
                INSERT INTO public.royan_audit_logs
                    (entity_type, entity_id, action, actor, details, created_at)
                VALUES ('patient', %s, 'phi_erasure', %s, %s, now())
                """,
                (
                    patient_id,
                    user.get("sub"),
                    json.dumps({"fields_anonymised": list(updates.keys()), "reason": payload.reason}),
                ),
            )
        conn.commit()
    finally:
        _put_conn(conn)

    logger.warning(
        "PHI erasure: patient=%s fields=%s by=%s reason=%s",
        patient_id, list(updates.keys()), user.get("sub"), payload.reason,
    )
    return {
        "success": True,
        "patient_id": patient_id,
        "fields_anonymised": list(updates.keys()),
        "anonymised_at": _now(),
        "note": "Clinical records retained per NDPA 2023 §42 (medical records exemption).",
    }


# ─────────────────────────────────────────────────────────────────────────────
# PHI Audit Trail (admin only)
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/phi-audit/{patient_id}")
async def phi_audit_trail(
    patient_id: int,
    limit: int = Query(50, ge=1, le=200),
    user=Depends(require_role("admin", "dpo", "audit")),
):
    """Return PHI access audit trail for a patient (admin/DPO only)."""
    conn = _get_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT action, actor, details, created_at
                FROM public.royan_audit_logs
                WHERE entity_type = 'patient'
                  AND entity_id = %s
                  AND action IN ('phi_read', 'phi_erasure', 'dsar_submitted')
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (patient_id, limit),
            )
            rows = cur.fetchall()
    finally:
        _put_conn(conn)

    events = []
    for r in rows:
        details = r.get("details") or {}
        if isinstance(details, str):
            try:
                details = json.loads(details)
            except Exception:
                details = {"raw": details}
        events.append({
            "action": r["action"],
            "actor": r["actor"],
            "details": details,
            "occurred_at": str(r["created_at"]),
        })

    return {
        "patient_id": patient_id,
        "total_events": len(events),
        "events": events,
    }


# ─────────────────────────────────────────────────────────────────────────────
# NDPA Compliance Dashboard
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/compliance-summary")
async def compliance_summary(user=Depends(require_role("admin", "dpo"))):
    """High-level NDPA compliance metrics for the DPO dashboard."""
    conn = _get_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Total patients vs those with data_processing consent
            cur.execute("""
                SELECT
                    (SELECT COUNT(*) FROM public.royan_patients) AS total_patients,
                    COUNT(DISTINCT patient_id) AS patients_with_consent
                FROM public.royan_patient_consent
                WHERE consent_type = 'data_processing'
                  AND is_given = true
                  AND withdrawn_at IS NULL
            """)
            consent_stats = cur.fetchone() or {}

            # PHI access events in last 30 days
            cur.execute("""
                SELECT COUNT(*) AS phi_reads_30d
                FROM public.royan_audit_logs
                WHERE action = 'phi_read'
                  AND created_at >= now() - interval '30 days'
            """)
            phi_stats = cur.fetchone() or {}

            # DSAR requests in last 90 days
            cur.execute("""
                SELECT COUNT(*) AS dsar_90d
                FROM public.royan_audit_logs
                WHERE action = 'dsar_submitted'
                  AND created_at >= now() - interval '90 days'
            """)
            dsar_stats = cur.fetchone() or {}

            # Erasure actions
            cur.execute("""
                SELECT COUNT(*) AS erasures_total
                FROM public.royan_audit_logs
                WHERE action = 'phi_erasure'
            """)
            erasure_stats = cur.fetchone() or {}

    finally:
        _put_conn(conn)

    total = int(consent_stats.get("total_patients") or 0)
    consented = int(consent_stats.get("patients_with_consent") or 0)

    return {
        "generated_at": _now(),
        "framework": "NDPA 2023 (Nigeria Data Protection Act)",
        "consent": {
            "total_patients": total,
            "patients_with_data_processing_consent": consented,
            "consent_coverage_pct": round(consented / max(total, 1) * 100, 1),
        },
        "phi_access": {
            "phi_reads_last_30_days": int(phi_stats.get("phi_reads_30d") or 0),
        },
        "data_subject_requests": {
            "dsar_last_90_days": int(dsar_stats.get("dsar_90d") or 0),
        },
        "erasures": {
            "total_anonymisations": int(erasure_stats.get("erasures_total") or 0),
        },
        "compliance_notes": [
            "Medical records are retained per NDPA 2023 §42 (healthcare exemption).",
            "PHI access is logged for all patient data reads.",
            "DSARs are processed within 30 days per NDPA 2023 §34.",
        ],
    }
