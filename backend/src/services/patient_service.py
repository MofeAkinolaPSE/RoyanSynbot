"""Patient Business Service — Chapter 7 of the Implementation Guide.

Capability-oriented service layer for patient identity management.
All patient mutations flow through here so that domain events are
emitted consistently and canonical data quality is enforced.

Functions:
  register_patient(conn, data, actor_id) → int  (patient_id)
  update_patient_demographics(conn, patient_id, data, actor_id) → dict
  get_patient_by_mrn(conn, mrn) → dict | None
  get_patient_by_id(conn, patient_id) → dict | None
  list_patients(conn, search, limit, offset) → list[dict]
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional

import psycopg2.extras

from src.services.event_service import emit_clinical_event

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _generate_mrn(conn) -> str:
    """Generate next MRN in the sequence RH-YYYYNNNNNN."""
    from datetime import datetime
    year = datetime.now().year
    with conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM public.royan_patients WHERE mrn LIKE %s",
            (f"RH-{year}%",),
        )
        count = cur.fetchone()[0]
    return f"RH-{year}{str(count + 1).zfill(6)}"


def _row_to_dict(row, cur) -> Dict[str, Any]:
    cols = [d[0] for d in cur.description]
    return dict(zip(cols, row))


# ─────────────────────────────────────────────────────────────────────────────
# Capabilities
# ─────────────────────────────────────────────────────────────────────────────

def register_patient(
    conn,
    data: Dict[str, Any],
    actor_id: str = "system",
    correlation_id: Optional[str] = None,
) -> int:
    """Create a new patient record and emit PatientRegistered event.

    Returns the new patient_id.
    Raises ValueError if required fields are missing.
    Raises RuntimeError on DB failure.
    """
    first_name = (data.get("first_name") or "").strip()
    last_name = (data.get("last_name") or "").strip()
    if not first_name or not last_name:
        raise ValueError("first_name and last_name are required to register a patient")

    mrn = (data.get("mrn") or "").strip() or _generate_mrn(conn)

    # Check for MRN conflict
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM public.royan_patients WHERE mrn = %s", (mrn,))
        if cur.fetchone():
            raise ValueError(f"MRN '{mrn}' already exists")

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO public.royan_patients
                    (mrn, first_name, last_name, date_of_birth, gender,
                     phone, email, address, blood_group, genotype,
                     source_system, source_record_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    mrn, first_name, last_name,
                    data.get("date_of_birth"),
                    data.get("gender"),
                    data.get("phone"),
                    data.get("email"),
                    data.get("address"),
                    data.get("blood_group"),
                    data.get("genotype"),
                    data.get("source_system", "synbot"),
                    data.get("source_record_id"),
                ),
            )
            patient_id = cur.fetchone()[0]
        conn.commit()
    except Exception as exc:
        conn.rollback()
        raise RuntimeError(f"register_patient DB error: {exc}") from exc

    emit_clinical_event(
        event_type="PATIENT_REGISTERED",
        patient_id=patient_id,
        entity_type="patient",
        entity_id=patient_id,
        performed_by=actor_id,
        event_data={"mrn": mrn, "name": f"{first_name} {last_name}", "correlation_id": correlation_id},
    )
    logger.info("PatientRegistered mrn=%s id=%d actor=%s", mrn, patient_id, actor_id)
    return patient_id


def update_patient_demographics(
    conn,
    patient_id: int,
    data: Dict[str, Any],
    actor_id: str = "system",
    correlation_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Update mutable demographic fields and emit PatientUpdated event."""
    allowed = {
        "first_name", "last_name", "date_of_birth", "gender",
        "phone", "email", "address", "blood_group", "genotype",
    }
    updates = {k: v for k, v in data.items() if k in allowed and v is not None}
    if not updates:
        raise ValueError("No valid fields provided for patient update")

    set_clause = ", ".join(f"{k} = %s" for k in updates)
    values = list(updates.values()) + [patient_id]

    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                f"UPDATE public.royan_patients SET {set_clause}, updated_at = now() WHERE id = %s RETURNING *",
                values,
            )
            row = cur.fetchone()
        conn.commit()
    except Exception as exc:
        conn.rollback()
        raise RuntimeError(f"update_patient_demographics DB error: {exc}") from exc

    if not row:
        raise ValueError(f"Patient {patient_id} not found")

    emit_clinical_event(
        event_type="SYSTEM_EVENT",
        patient_id=patient_id,
        entity_type="patient",
        entity_id=patient_id,
        performed_by=actor_id,
        event_data={"action": "patient_updated", "fields": list(updates.keys()), "correlation_id": correlation_id},
    )
    return dict(row)


def get_patient_by_mrn(conn, mrn: str) -> Optional[Dict[str, Any]]:
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM public.royan_patients WHERE mrn = %s", (mrn,))
        row = cur.fetchone()
    return dict(row) if row else None


def get_patient_by_id(conn, patient_id: int) -> Optional[Dict[str, Any]]:
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM public.royan_patients WHERE id = %s", (patient_id,))
        row = cur.fetchone()
    return dict(row) if row else None


def list_patients(
    conn,
    search: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    """Return patients ordered by registration date. Optional name/MRN search."""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        if search:
            term = f"%{search}%"
            cur.execute(
                """
                SELECT * FROM public.royan_patients
                WHERE mrn ILIKE %s
                   OR first_name ILIKE %s
                   OR last_name ILIKE %s
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
                """,
                (term, term, term, limit, offset),
            )
        else:
            cur.execute(
                "SELECT * FROM public.royan_patients ORDER BY created_at DESC LIMIT %s OFFSET %s",
                (limit, offset),
            )
        return [dict(r) for r in cur.fetchall()]
