"""Clinical Business Service — Chapter 7 of the Implementation Guide.

Handles encounter-level clinical documentation:
  record_vitals       — observation capture (vitals)
  record_diagnosis    — ICD-10 diagnosis against an encounter
  create_soap_note    — clinical note authoring
  get_encounter_notes — retrieve clinical notes for an encounter
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

import psycopg2.extras

from src.services.event_service import emit_clinical_event

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Vitals / Observations
# ─────────────────────────────────────────────────────────────────────────────

def record_vitals(
    conn,
    encounter_id: int,
    patient_id: int,
    vitals: Dict[str, Any],
    actor_id: str = "system",
    correlation_id: Optional[str] = None,
) -> int:
    """Insert a vitals record and emit VITALS_RECORDED event. Returns new record id."""
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO public.royan_vitals
                    (encounter_id, patient_id,
                     temperature, bp_systolic, bp_diastolic, pulse,
                     respiratory_rate, spo2, weight, height,
                     notes, recorded_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    encounter_id, patient_id,
                    vitals.get("temperature"),
                    vitals.get("systolic_bp"),
                    vitals.get("diastolic_bp"),
                    vitals.get("pulse_rate"),
                    vitals.get("respiratory_rate"),
                    vitals.get("oxygen_saturation"),
                    vitals.get("weight_kg"),
                    vitals.get("height_cm"),
                    vitals.get("notes"),
                    actor_id,
                ),
            )
            record_id = cur.fetchone()[0]
        conn.commit()
    except Exception as exc:
        conn.rollback()
        raise RuntimeError(f"record_vitals DB error: {exc}") from exc

    emit_clinical_event(
        event_type="VITALS_RECORDED",
        encounter_id=encounter_id,
        patient_id=patient_id,
        entity_type="vitals",
        entity_id=record_id,
        performed_by=actor_id,
        event_data={"correlation_id": correlation_id},
    )
    return record_id


# ─────────────────────────────────────────────────────────────────────────────
# Diagnoses
# ─────────────────────────────────────────────────────────────────────────────

def record_diagnosis(
    conn,
    encounter_id: int,
    patient_id: int,
    description: str,
    icd_code: Optional[str] = None,
    diagnosis_type: str = "primary",
    is_chronic: bool = False,
    actor_id: str = "system",
    correlation_id: Optional[str] = None,
) -> Optional[int]:
    """Record a diagnosis against an encounter. Returns new record id or None."""
    if not description:
        raise ValueError("Diagnosis description is required")

    # Also update the encounter's diagnosis_notes field with the primary diagnosis
    try:
        with conn.cursor() as cur:
            if diagnosis_type == "primary":
                cur.execute(
                    "UPDATE public.royan_encounters SET diagnosis_notes = %s WHERE id = %s",
                    (description, encounter_id),
                )

            # Try to insert into dedicated diagnoses table if it exists
            try:
                cur.execute(
                    """
                    INSERT INTO public.royan_encounter_diagnoses
                        (encounter_id, patient_id, icd_code, description,
                         diagnosis_type, is_chronic, recorded_by)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (encounter_id, patient_id, icd_code, description,
                     diagnosis_type, is_chronic, actor_id),
                )
                record_id = cur.fetchone()[0]
            except Exception:
                # Table may not exist yet — gracefully fall back to encounter update only
                record_id = None

        conn.commit()
    except (ValueError, RuntimeError):
        raise
    except Exception as exc:
        conn.rollback()
        raise RuntimeError(f"record_diagnosis DB error: {exc}") from exc

    emit_clinical_event(
        event_type="DIAGNOSIS_RECORDED",
        encounter_id=encounter_id,
        patient_id=patient_id,
        entity_type="diagnosis",
        entity_id=record_id,
        performed_by=actor_id,
        event_data={
            "icd_code": icd_code,
            "description": description,
            "diagnosis_type": diagnosis_type,
            "correlation_id": correlation_id,
        },
    )
    return record_id


# ─────────────────────────────────────────────────────────────────────────────
# Clinical notes (SOAP / Progress notes)
# ─────────────────────────────────────────────────────────────────────────────

def create_soap_note(
    conn,
    encounter_id: int,
    patient_id: int,
    note_type: str = "soap",
    subjective: Optional[str] = None,
    objective: Optional[str] = None,
    assessment: Optional[str] = None,
    plan: Optional[str] = None,
    free_text: Optional[str] = None,
    actor_id: str = "system",
    correlation_id: Optional[str] = None,
) -> int:
    """Create a SOAP note or free-text clinical note. Returns new note_id."""
    content = free_text or " | ".join(filter(None, [
        f"S: {subjective}" if subjective else "",
        f"O: {objective}" if objective else "",
        f"A: {assessment}" if assessment else "",
        f"P: {plan}" if plan else "",
    ]))
    if not content.strip():
        raise ValueError("Clinical note must have content")

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO public.royan_encounter_notes
                    (encounter_id, patient_id, note_type, content,
                     subjective, objective, assessment, plan, author_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (encounter_id, patient_id, note_type, content,
                 subjective, objective, assessment, plan, actor_id),
            )
            note_id = cur.fetchone()[0]
        conn.commit()
    except Exception as exc:
        conn.rollback()
        raise RuntimeError(f"create_soap_note DB error: {exc}") from exc

    emit_clinical_event(
        event_type="CLINICAL_NOTE_AUTHORED",
        encounter_id=encounter_id,
        patient_id=patient_id,
        entity_type="clinical_note",
        entity_id=note_id,
        performed_by=actor_id,
        event_data={"note_type": note_type, "correlation_id": correlation_id},
    )
    return note_id


def get_encounter_notes(
    conn,
    encounter_id: int,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT * FROM public.royan_encounter_notes
            WHERE encounter_id = %s
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (encounter_id, limit),
        )
        return [dict(r) for r in cur.fetchall()]


def get_encounter_vitals(
    conn,
    encounter_id: int,
) -> List[Dict[str, Any]]:
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT * FROM public.royan_vitals
            WHERE encounter_id = %s
            ORDER BY recorded_at DESC
            """,
            (encounter_id,),
        )
        return [dict(r) for r in cur.fetchall()]
