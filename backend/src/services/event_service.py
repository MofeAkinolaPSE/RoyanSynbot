"""Clinical Event Service — shared emit_clinical_event() for all domain routers.

Extracted from canonical.py so every router can emit to royan_clinical_event_log
without circular imports. Fire-and-forget: never raises, never blocks the caller.

Usage:
    from src.services.event_service import emit_clinical_event

    emit_clinical_event(
        event_type="LAB_RESULT_READY",
        encounter_id=order.get("encounter_id"),
        patient_id=order.get("patient_id"),
        entity_type="lab_order",
        entity_id=order_id,
        performed_by=user.get("sub"),
        event_data={"test_name": order.get("test_name"), "is_critical": True},
    )
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Exhaustive list of valid event types (mirrors migration 133 CHECK constraint)
_VALID_EVENT_TYPES = frozenset({
    # Encounter lifecycle
    "ENCOUNTER_CREATED", "ENCOUNTER_TRIAGED", "ENCOUNTER_CONSULTING",
    "ENCOUNTER_DISCHARGED", "ENCOUNTER_ADMITTED", "ENCOUNTER_TRANSFERRED",
    "ENCOUNTER_QUEUED", "ENCOUNTER_CLOSED", "CONSULTATION_COMPLETED",
    # Lab
    "LAB_ORDER_CREATED", "LAB_SAMPLE_COLLECTED", "LAB_RESULT_READY",
    "LAB_RESULT_CRITICAL", "LAB_RESULT_VERIFIED", "SPECIMEN_COLLECTED",
    # Medication
    "PRESCRIPTION_ISSUED", "MEDICATION_DISPENSED", "MEDICATION_ADMINISTERED",
    # Finance
    "BILL_GENERATED", "PAYMENT_RECEIVED", "INSURANCE_CLAIM_SUBMITTED",
    # Clinical
    "DIAGNOSIS_RECORDED", "REFERRAL_SENT", "VITALS_RECORDED",
    "TRIAGE_COMPLETED", "DISCHARGE_COMPLETED", "CONSENT_OBTAINED",
    "CLINICAL_NOTE_AUTHORED", "PATIENT_REGISTERED",
    # System
    "ALERT_TRIGGERED", "SYSTEM_EVENT",
})


def emit_clinical_event(
    event_type: str,
    encounter_id: Optional[int] = None,
    patient_id: Optional[int] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
    performed_by: Optional[str] = None,
    event_data: Optional[Dict[str, Any]] = None,
    outcome: str = "success",
) -> None:
    """Append one immutable event to royan_clinical_event_log.

    Safe to call from any FastAPI endpoint handler. Never raises — any
    database error is logged as a warning and swallowed so the clinical
    operation is never blocked by observability infrastructure.
    """
    if event_type not in _VALID_EVENT_TYPES:
        logger.warning(
            "emit_clinical_event: unknown event_type '%s' — using SYSTEM_EVENT", event_type
        )
        event_type = "SYSTEM_EVENT"

    try:
        from src.db import db
        conn = db.pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO public.royan_clinical_event_log
                        (event_type, encounter_id, patient_id, entity_type,
                         entity_id, performed_by, event_data, outcome, occurred_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, now())
                    """,
                    (
                        event_type,
                        encounter_id,
                        patient_id,
                        entity_type,
                        entity_id,
                        performed_by,
                        json.dumps(event_data or {}),
                        outcome,
                    ),
                )
                conn.commit()
        except Exception as exc:
            try:
                conn.rollback()
            except Exception:
                pass
            logger.warning("emit_clinical_event: DB write failed [%s]: %s", event_type, exc)
        finally:
            db.pool.putconn(conn)
    except Exception as exc:
        logger.warning("emit_clinical_event: pool error [%s]: %s", event_type, exc)
