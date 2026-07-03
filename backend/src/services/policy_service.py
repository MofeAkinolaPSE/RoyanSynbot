"""Policy Engine Service — Chapter 11 of the Implementation Guide.

Provides RBAC + consent-aware access control, NDPA data retention
enforcement, and AI recommendation auditing.

Functions:
    can_access_record(conn, user_id, record_type, record_id, user_roles) → bool
    enforce_data_retention(conn, table, cutoff_date, dry_run) → int
    audit_ai_recommendation(conn, recommendation, evidence, actor_id, correlation_id) → int
    get_retention_policy(record_type) → dict
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import psycopg2.extras

logger = logging.getLogger(__name__)


# ── NDPA Retention policies ───────────────────────────────────────────────────
# Nigeria Data Protection Act (NDPA) 2023 — health records retention schedule

_RETENTION_POLICIES: Dict[str, Dict[str, Any]] = {
    "royan_clinical_event_log":   {"years": 10, "description": "Clinical event audit trail"},
    "royan_encounter_notes":      {"years": 10, "description": "Clinical documentation"},
    "royan_vitals":               {"years": 7,  "description": "Vital signs observations"},
    "royan_lab_orders":           {"years": 7,  "description": "Laboratory orders"},
    "royan_lab_results":          {"years": 7,  "description": "Laboratory results"},
    "royan_prescriptions":        {"years": 7,  "description": "Prescriptions"},
    "royan_billing":              {"years": 7,  "description": "Billing records"},
    "royan_payments":             {"years": 7,  "description": "Payment records"},
    "royan_import_rejections":    {"years": 2,  "description": "ETL rejection log"},
    "royan_audit_logs":           {"years": 5,  "description": "System audit log"},
}

# Role → permitted record types
_ROLE_PERMISSIONS: Dict[str, set] = {
    "admin":   {"*"},
    "doctor":  {"encounter", "patient", "lab_order", "prescription", "vitals", "clinical_note"},
    "nurse":   {"encounter", "patient", "vitals", "prescription", "clinical_note"},
    "lab":     {"lab_order", "lab_result", "patient"},
    "pharmacy":{"prescription", "patient"},
    "billing": {"billing", "payment", "patient", "encounter"},
    "patient": {"own_records"},
}


# ── RBAC + consent access control ────────────────────────────────────────────

def can_access_record(
    conn,
    user_id: str,
    record_type: str,
    record_id: Optional[int],
    user_roles: Optional[List[str]] = None,
) -> bool:
    """Return True if the authenticated user may access this record.

    Checks:
    1. Role-based permission (RBAC).
    2. Patient consent override — if the patient has withdrawn consent for
       data sharing, non-treating clinicians are blocked.

    Args:
        conn:        psycopg2 connection.
        user_id:     Authenticated user sub/ID.
        record_type: e.g. "patient", "encounter", "lab_order".
        record_id:   Specific record ID (None = any record of type).
        user_roles:  JWT-derived roles list.
    """
    roles = set(user_roles or [])

    # Admin always has access
    if "admin" in roles:
        return True

    # Check RBAC
    allowed = False
    for role in roles:
        permitted = _ROLE_PERMISSIONS.get(role, set())
        if "*" in permitted or record_type in permitted:
            allowed = True
            break

    if not allowed:
        logger.info(
            "PolicyService: access DENIED user=%s record_type=%s record_id=%s roles=%s",
            user_id, record_type, record_id, roles,
        )
        return False

    # Consent check for patient records (non-treating access)
    if record_type == "patient" and record_id and "patient_portal" not in roles:
        consent_blocked = _check_consent_block(conn, record_id, user_id)
        if consent_blocked:
            logger.info(
                "PolicyService: consent BLOCKED user=%s patient_id=%s",
                user_id, record_id,
            )
            return False

    return True


def _check_consent_block(conn, patient_id: int, user_id: str) -> bool:
    """Return True if this patient has blocked data sharing for this accessor."""
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT EXISTS(
                    SELECT 1 FROM public.royan_patient_consent
                    WHERE patient_id = %s
                      AND consent_type = 'data_sharing'
                      AND status = 'withdrawn'
                      AND (expires_at IS NULL OR expires_at > now())
                )
                """,
                (patient_id,),
            )
            return bool(cur.fetchone()[0])
    except Exception as exc:
        logger.debug("Consent check error (table may not exist): %s", exc)
        return False


# ── Data retention ────────────────────────────────────────────────────────────

def get_retention_policy(record_type: str) -> Optional[Dict[str, Any]]:
    """Return the NDPA retention policy for *record_type*."""
    return _RETENTION_POLICIES.get(record_type)


def enforce_data_retention(
    conn,
    table: str,
    cutoff_date: Optional[date] = None,
    dry_run: bool = True,
) -> int:
    """Mark or delete records older than the retention cutoff.

    Soft-deletes by setting `is_archived = true` where supported;
    falls back to hard delete only when explicitly requested (dry_run=False).

    Args:
        conn:        psycopg2 connection.
        table:       Table name (must be in _RETENTION_POLICIES).
        cutoff_date: Override the computed cutoff. None = use policy years.
        dry_run:     If True, only counts — no mutations.

    Returns:
        Number of records that would be / were affected.
    """
    policy = _RETENTION_POLICIES.get(table)
    if not policy:
        raise ValueError(f"No retention policy defined for table '{table}'")

    if cutoff_date is None:
        cutoff_date = date.today() - timedelta(days=policy["years"] * 365)

    # Pick the most likely timestamp column
    ts_columns = ["occurred_at", "created_at", "billed_at", "prescribed_at", "ordered_at"]

    count = 0
    try:
        with conn.cursor() as cur:
            for ts_col in ts_columns:
                try:
                    if dry_run:
                        cur.execute(
                            f"SELECT COUNT(*) FROM public.{table} WHERE {ts_col} < %s",
                            (cutoff_date,),
                        )
                        count = cur.fetchone()[0]
                    else:
                        cur.execute(
                            f"""
                            UPDATE public.{table}
                            SET is_archived = true
                            WHERE {ts_col} < %s
                              AND (is_archived IS NULL OR is_archived = false)
                            """,
                            (cutoff_date,),
                        )
                        count = cur.rowcount
                        conn.commit()
                    break
                except psycopg2.errors.UndefinedColumn:
                    conn.rollback()
                    continue
                except Exception:
                    conn.rollback()
                    raise
    except Exception as exc:
        logger.warning("enforce_data_retention error for '%s': %s", table, exc)
        return 0

    logger.info(
        "DataRetention table=%s cutoff=%s dry_run=%s affected=%d",
        table, cutoff_date, dry_run, count,
    )
    return count


# ── AI recommendation audit ───────────────────────────────────────────────────

def audit_ai_recommendation(
    conn,
    recommendation: str,
    evidence: Dict[str, Any],
    actor_id: str = "system",
    patient_id: Optional[int] = None,
    encounter_id: Optional[int] = None,
    model_id: Optional[str] = None,
    confidence: Optional[float] = None,
    correlation_id: Optional[str] = None,
) -> Optional[int]:
    """Persist an AI recommendation to the clinical AI audit trail.

    Required by NDPA and good clinical governance — every AI output that
    influences clinical decisions must be traceable with its evidence.

    Returns the audit record id, or None on failure.
    """
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO public.royan_ai_audit
                    (recommendation, evidence, actor_id, patient_id, encounter_id,
                     model_id, confidence_score, correlation_id, occurred_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, now())
                RETURNING id
                """,
                (
                    recommendation[:2000],
                    json.dumps(evidence or {}),
                    actor_id,
                    patient_id,
                    encounter_id,
                    model_id,
                    confidence,
                    correlation_id,
                ),
            )
            audit_id = cur.fetchone()
            if audit_id:
                audit_id = audit_id[0]
        conn.commit()
        return audit_id
    except Exception as exc:
        conn.rollback()
        logger.warning("audit_ai_recommendation failed: %s", exc)
        return None
