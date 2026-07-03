"""Encounter Business Service — Chapter 7 of the Implementation Guide.

Capability-oriented service for clinical encounter lifecycle management.
All encounter state changes flow through here so workflow events, audit
events, and knowledge invalidation happen consistently.

Functions:
  start_encounter(conn, patient_id, encounter_type, ...) → int
  assign_clinician(conn, encounter_id, staff_id, actor_id) → dict
  complete_consultation(conn, encounter_id, data, actor_id) → dict
  discharge_patient(conn, encounter_id, data, actor_id) → dict
  get_encounter(conn, encounter_id) → dict | None
  get_active_encounter(conn, patient_id) → dict | None
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import psycopg2.extras

from src.services.event_service import emit_clinical_event

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Capabilities
# ─────────────────────────────────────────────────────────────────────────────

def start_encounter(
    conn,
    patient_id: int,
    encounter_type: str = "outpatient",
    department: Optional[str] = None,
    department_id: Optional[int] = None,
    chief_complaint: Optional[str] = None,
    actor_id: str = "system",
    correlation_id: Optional[str] = None,
) -> int:
    """Open a new encounter for a patient and emit EncounterStarted event.

    Also creates a workflow.instances row for the encounter lifecycle.
    Returns new encounter_id.
    """
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO public.royan_encounters
                    (patient_id, encounter_type, status, department,
                     department_id, chief_complaint, source_system)
                VALUES (%s, %s, 'patient_registered', %s, %s, %s, 'synbot')
                RETURNING id
                """,
                (patient_id, encounter_type, department, department_id, chief_complaint),
            )
            encounter_id = cur.fetchone()[0]

            # Create workflow instance
            cur.execute(
                """
                INSERT INTO workflow.instances
                    (entity_type, entity_id, definition_id, current_state, started_by)
                VALUES ('encounter', %s, %s, 'registered', %s)
                """,
                (
                    encounter_id,
                    f"encounter.{encounter_type}.v1",
                    actor_id,
                ),
            )
        conn.commit()
    except Exception as exc:
        conn.rollback()
        raise RuntimeError(f"start_encounter DB error: {exc}") from exc

    emit_clinical_event(
        event_type="ENCOUNTER_CREATED",
        encounter_id=encounter_id,
        patient_id=patient_id,
        entity_type="encounter",
        entity_id=encounter_id,
        performed_by=actor_id,
        event_data={
            "encounter_type": encounter_type,
            "department": department,
            "chief_complaint": chief_complaint,
            "correlation_id": correlation_id,
        },
    )
    logger.info("EncounterStarted encounter_id=%d patient_id=%d actor=%s", encounter_id, patient_id, actor_id)
    return encounter_id


def assign_clinician(
    conn,
    encounter_id: int,
    staff_id: Optional[int] = None,
    staff_name: Optional[str] = None,
    actor_id: str = "system",
    correlation_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Assign a consulting doctor to an encounter."""
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                UPDATE public.royan_encounters
                SET consulting_doctor_id = %s,
                    consulting_doctor = COALESCE(%s, consulting_doctor),
                    status = 'consulting',
                    updated_at = now()
                WHERE id = %s
                RETURNING *
                """,
                (staff_id, staff_name, encounter_id),
            )
            row = cur.fetchone()
        conn.commit()
    except Exception as exc:
        conn.rollback()
        raise RuntimeError(f"assign_clinician DB error: {exc}") from exc

    if not row:
        raise ValueError(f"Encounter {encounter_id} not found")

    emit_clinical_event(
        event_type="ENCOUNTER_CONSULTING",
        encounter_id=encounter_id,
        patient_id=row.get("patient_id"),
        entity_type="encounter",
        entity_id=encounter_id,
        performed_by=actor_id,
        event_data={"staff_id": staff_id, "staff_name": staff_name, "correlation_id": correlation_id},
    )
    return dict(row)


def complete_consultation(
    conn,
    encounter_id: int,
    diagnosis_notes: Optional[str] = None,
    diagnoses: Optional[list] = None,
    follow_up_required: bool = False,
    follow_up_date: Optional[str] = None,
    actor_id: str = "system",
    correlation_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Mark consultation as complete, record diagnoses, move encounter to billing_pending."""
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                UPDATE public.royan_encounters
                SET status = 'billing_pending',
                    diagnosis_notes = COALESCE(%s, diagnosis_notes),
                    updated_at = now()
                WHERE id = %s
                RETURNING *
                """,
                (diagnosis_notes, encounter_id),
            )
            row = cur.fetchone()
            if not row:
                raise ValueError(f"Encounter {encounter_id} not found")

            # Record ICD-10 diagnoses if provided
            if diagnoses:
                for diag in diagnoses:
                    icd = diag.get("icd_code") or diag.get("code")
                    desc = diag.get("description") or diag.get("name") or ""
                    if desc:
                        try:
                            cur.execute(
                                """
                                INSERT INTO public.royan_encounter_diagnoses
                                    (encounter_id, patient_id, icd_code, description,
                                     diagnosis_type, recorded_by)
                                VALUES (%s, %s, %s, %s, %s, %s)
                                ON CONFLICT DO NOTHING
                                """,
                                (
                                    encounter_id, row["patient_id"],
                                    icd, desc,
                                    diag.get("type", "primary"),
                                    actor_id,
                                ),
                            )
                        except Exception:
                            pass  # Non-fatal: diagnosis table may not have all columns yet

            # Update workflow instance
            try:
                cur.execute(
                    """
                    UPDATE workflow.instances
                    SET current_state = 'billing_pending',
                        previous_state = current_state,
                        last_transitioned_at = now()
                    WHERE entity_type = 'encounter' AND entity_id = %s
                    """,
                    (encounter_id,),
                )
            except Exception:
                pass  # Non-fatal if workflow schema not yet applied

        conn.commit()
    except (ValueError, RuntimeError):
        raise
    except Exception as exc:
        conn.rollback()
        raise RuntimeError(f"complete_consultation DB error: {exc}") from exc

    emit_clinical_event(
        event_type="CONSULTATION_COMPLETED",
        encounter_id=encounter_id,
        patient_id=row.get("patient_id"),
        entity_type="encounter",
        entity_id=encounter_id,
        performed_by=actor_id,
        event_data={
            "diagnosis_notes": diagnosis_notes,
            "follow_up_required": follow_up_required,
            "follow_up_date": follow_up_date,
            "correlation_id": correlation_id,
        },
    )
    logger.info("ConsultationCompleted encounter_id=%d actor=%s", encounter_id, actor_id)
    return dict(row)


def discharge_patient(
    conn,
    encounter_id: int,
    discharge_data: Optional[Dict[str, Any]] = None,
    actor_id: str = "system",
    correlation_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Discharge a patient — moves encounter to 'discharged' state."""
    data = discharge_data or {}
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                UPDATE public.royan_encounters
                SET status = 'discharged',
                    discharge_at = now(),
                    discharge_condition = %s,
                    discharge_summary = %s,
                    follow_up_instructions = %s,
                    updated_at = now()
                WHERE id = %s AND status NOT IN ('discharged', 'closed')
                RETURNING *
                """,
                (
                    data.get("discharge_condition", "stable"),
                    data.get("discharge_summary"),
                    data.get("follow_up_instructions"),
                    encounter_id,
                ),
            )
            row = cur.fetchone()
            if not row:
                raise ValueError(f"Encounter {encounter_id} not found or already discharged")

            try:
                cur.execute(
                    """
                    UPDATE workflow.instances
                    SET current_state = 'discharged',
                        previous_state = current_state,
                        last_transitioned_at = now()
                    WHERE entity_type = 'encounter' AND entity_id = %s
                    """,
                    (encounter_id,),
                )
            except Exception:
                pass

        conn.commit()
    except (ValueError, RuntimeError):
        raise
    except Exception as exc:
        conn.rollback()
        raise RuntimeError(f"discharge_patient DB error: {exc}") from exc

    emit_clinical_event(
        event_type="DISCHARGE_COMPLETED",
        encounter_id=encounter_id,
        patient_id=row.get("patient_id"),
        entity_type="encounter",
        entity_id=encounter_id,
        performed_by=actor_id,
        event_data={
            "discharge_condition": data.get("discharge_condition"),
            "follow_up_date": data.get("follow_up_date"),
            "correlation_id": correlation_id,
        },
    )
    logger.info("PatientDischarged encounter_id=%d actor=%s", encounter_id, actor_id)
    return dict(row)


def get_encounter(conn, encounter_id: int) -> Optional[Dict[str, Any]]:
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM public.royan_encounters WHERE id = %s", (encounter_id,))
        row = cur.fetchone()
    return dict(row) if row else None


def get_active_encounter(conn, patient_id: int) -> Optional[Dict[str, Any]]:
    """Return the most recent non-discharged encounter for a patient."""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT * FROM public.royan_encounters
            WHERE patient_id = %s AND status NOT IN ('discharged', 'closed')
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (patient_id,),
        )
        row = cur.fetchone()
    return dict(row) if row else None
