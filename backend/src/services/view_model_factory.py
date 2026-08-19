"""View Model Factory — Chapter 9 of the Implementation Guide.

Produces role-specific workspace view models by composing EKE knowledge
objects. The frontend receives one complete business context per screen
rather than orchestrating multiple API calls.

Workspaces:
  doctor_workspace(conn, encounter_id)   → DoctorWorkspace
  nurse_workspace(conn, encounter_id)    → NurseWorkspace
  billing_workspace(conn, encounter_id)  → BillingWorkspace
  patient_portal(conn, patient_id)       → PatientPortalView
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import psycopg2.extras

from src.services import eke_service
from src.schemas.canonical import (
    BillingSummary,
    BillingWorkspace,
    DoctorWorkspace,
    EncounterBrief,
    EncounterTimelineItem,
    MedicationRecord,
    NurseWorkspace,
    PatientDemographics,
    PatientPortalView,
)

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _q(conn, sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            return [dict(r) for r in cur.fetchall()]
    except Exception as exc:
        logger.warning("ViewModelFactory query failed: %s | %.80s", exc, sql)
        # A failed query aborts the current Postgres transaction — every
        # subsequent query on this same connection would fail too until
        # this rolls it back (see eke_service._q for the same fix).
        try:
            conn.rollback()
        except Exception:
            pass
        return []


def _q1(conn, sql: str, params: tuple = ()) -> Optional[Dict[str, Any]]:
    rows = _q(conn, sql, params)
    return rows[0] if rows else None


def _sd(val: Any) -> Optional[str]:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.isoformat()
    return str(val)


def _load_encounter_and_patient(conn, encounter_id: int):
    enc = _q1(conn, """
        SELECT e.*, COALESCE(s.full_name, e.consulting_doctor) AS doctor_name
        FROM public.royan_encounters e
        LEFT JOIN public.royan_staff s ON s.id = e.doctor_id
        WHERE e.id = %s
    """, (encounter_id,))
    if not enc:
        return None, None
    patient = _q1(conn, "SELECT * FROM public.royan_patients WHERE id = %s", (enc["patient_id"],))
    return enc, patient


def _enc_brief(enc: Dict) -> EncounterBrief:
    return EncounterBrief(
        id=enc["id"],
        encounter_type=enc.get("encounter_type"),
        status=enc.get("status"),
        department=enc.get("department"),
        consulting_doctor=enc.get("doctor_name") or enc.get("consulting_doctor"),
        chief_complaint=enc.get("chief_complaint"),
        diagnosis_notes=enc.get("diagnosis_notes"),
        triage_at=_sd(enc.get("triage_at")),
        discharge_at=_sd(enc.get("discharge_at")),
        created_at=_sd(enc.get("created_at")),
    )


def _patient_demo(p: Dict) -> PatientDemographics:
    return PatientDemographics(
        id=p["id"], mrn=p["mrn"],
        first_name=p["first_name"], last_name=p["last_name"],
        date_of_birth=_sd(p.get("date_of_birth")), gender=p.get("gender"),
        phone=p.get("phone"), email=p.get("email"), address=p.get("address"),
        blood_group=p.get("blood_group"), genotype=p.get("genotype"),
        hmo_provider=p.get("hmo_provider"), hmo_id=p.get("hmo_id"),
        registered_at=_sd(p.get("created_at")),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Doctor Workspace
# ─────────────────────────────────────────────────────────────────────────────

def doctor_workspace(conn, encounter_id: int) -> Optional[DoctorWorkspace]:
    """Assemble the full clinical view for the doctor consultation screen."""
    enc, patient = _load_encounter_and_patient(conn, encounter_id)
    if not enc or not patient:
        return None

    pid = patient["id"]
    ctx = eke_service.assemble_patient_context(conn, pid)
    if not ctx:
        return None

    workflow = _q1(conn, """
        SELECT current_state FROM workflow.instances
        WHERE entity_type = 'encounter' AND entity_id = %s
    """, (encounter_id,))

    return DoctorWorkspace(
        patient=ctx.patient,
        encounter=_enc_brief(enc),
        active_diagnoses=ctx.active_diagnoses,
        latest_vitals=ctx.latest_vitals,
        active_medications=ctx.active_medications,
        known_allergies=ctx.known_allergies,
        pending_lab_orders=ctx.pending_lab_orders,
        recent_lab_results=ctx.recent_lab_results,
        chronic_conditions=ctx.chronic_conditions,
        risk_flags=ctx.risk_flags,
        workflow_state=workflow["current_state"] if workflow else enc.get("status"),
        assembled_at=_now(),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Nurse Workspace
# ─────────────────────────────────────────────────────────────────────────────

def nurse_workspace(conn, encounter_id: int) -> Optional[NurseWorkspace]:
    """Assemble the nursing assessment and care delivery view."""
    enc, patient = _load_encounter_and_patient(conn, encounter_id)
    if not enc or not patient:
        return None

    pid = patient["id"]
    vitals = eke_service._latest_vitals(conn, pid)
    allergies = eke_service._allergies(conn, pid)
    meds = eke_service._active_meds(conn, pid)

    # Nursing tasks from nursing_care_plans
    nursing_tasks = _q(conn, """
        SELECT * FROM public.royan_nursing_care_plans
        WHERE encounter_id = %s AND status != 'completed'
        ORDER BY priority DESC, created_at
        LIMIT 20
    """, (encounter_id,))

    triage_notes = None
    triage_row = _q1(conn, """
        SELECT triage_notes, triage_level FROM public.royan_triage
        WHERE encounter_id = %s ORDER BY created_at DESC LIMIT 1
    """, (encounter_id,))
    if triage_row:
        triage_notes = triage_row.get("triage_notes")

    workflow = _q1(conn, """
        SELECT current_state FROM workflow.instances
        WHERE entity_type = 'encounter' AND entity_id = %s
    """, (encounter_id,))

    medications = [
        MedicationRecord(
            id=r["id"], drug_name=r.get("drug_name") or r.get("formulary_name"),
            drug_code=r.get("drug_code"), dosage=r.get("dosage"),
            frequency=r.get("frequency"), route=r.get("route"),
            quantity=r.get("quantity"), duration_days=r.get("duration_days"),
            status=r.get("status"), prescribed_by=r.get("prescribed_by"),
            prescribed_at=_sd(r.get("prescribed_at") or r.get("created_at")),
            encounter_id=r.get("encounter_id"),
        ) for r in meds
    ]

    from src.schemas.canonical import ObservationRecord
    latest_vitals = [
        ObservationRecord(
            observation_type="vital",
            name=f"Vitals ({_sd(r.get('recorded_at'))})",
            value=(
                f"BP {r.get('bp_systolic')}/{r.get('bp_diastolic')}, "
                f"PR {r.get('pulse')}, Temp {r.get('temperature')}°C, "
                f"SpO2 {r.get('spo2')}%"
            ),
            recorded_by=r.get("recorded_by"),
            recorded_at=_sd(r.get("recorded_at")),
            encounter_id=r.get("encounter_id"),
        ) for r in vitals
    ]

    return NurseWorkspace(
        patient=_patient_demo(patient),
        encounter=_enc_brief(enc),
        latest_vitals=latest_vitals,
        active_medications=medications,
        known_allergies=allergies,
        nursing_tasks=nursing_tasks,
        workflow_state=workflow["current_state"] if workflow else enc.get("status"),
        triage_notes=triage_notes,
        assembled_at=_now(),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Billing Workspace
# ─────────────────────────────────────────────────────────────────────────────

def billing_workspace(conn, encounter_id: int) -> Optional[BillingWorkspace]:
    """Assemble the billing and cashiering view."""
    enc, patient = _load_encounter_and_patient(conn, encounter_id)
    if not enc or not patient:
        return None

    pid = patient["id"]
    billing_row = _q1(conn, """
        SELECT * FROM public.royan_billing
        WHERE encounter_id = %s ORDER BY billed_at DESC LIMIT 1
    """, (encounter_id,))

    bill_items = _q(conn, """
        SELECT * FROM public.royan_bill_items
        WHERE billing_id = %s ORDER BY created_at
    """, (billing_row["id"],) if billing_row else (0,))

    payments = _q(conn, """
        SELECT * FROM public.royan_payments
        WHERE billing_id = %s ORDER BY received_at DESC
    """, (billing_row["id"],) if billing_row else (0,))

    hmo_row = _q1(conn, """
        SELECT h.name FROM public.royan_patient_insurance pi
        JOIN public.royan_hmos h ON h.id = pi.hmo_id
        WHERE pi.patient_id = %s AND pi.status = 'active' LIMIT 1
    """, (pid,))
    hmo_name = hmo_row["name"] if hmo_row else None

    claim_row = _q1(conn, """
        SELECT status FROM public.royan_insurance_claims
        WHERE billing_id = %s ORDER BY submitted_at DESC LIMIT 1
    """, (billing_row["id"],) if billing_row else (0,))

    workflow = _q1(conn, """
        SELECT current_state FROM workflow.instances
        WHERE entity_type = 'encounter' AND entity_id = %s
    """, (encounter_id,))

    # royan_billing has no running paid-amount column — payments are summed
    # from the separate royan_payments table (already fetched above).
    b = billing_row or {}
    total = float(b.get("subtotal") or 0)
    hmo_cov = float(b.get("hmo_covered") or 0)
    paid = sum(float(p.get("amount") or 0) for p in payments)
    last_payment = max((p.get("received_at") for p in payments if p.get("received_at")), default=None)
    billing_summary = BillingSummary(
        patient_mrn=patient["mrn"],
        total_billed=total, total_paid=paid, outstanding_balance=round(total - paid - hmo_cov, 2),
        hmo_covered=hmo_cov,
        last_payment_date=_sd(last_payment),
        payment_method=b.get("payment_method"),
        bill_count=1 if billing_row else 0,
    )

    return BillingWorkspace(
        patient=_patient_demo(patient),
        encounter=_enc_brief(enc),
        billing_summary=billing_summary,
        bill_items=bill_items,
        payments=payments,
        hmo_coverage=hmo_name,
        insurance_claim_status=claim_row["status"] if claim_row else None,
        workflow_state=workflow["current_state"] if workflow else enc.get("status"),
        assembled_at=_now(),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Patient Portal View
# ─────────────────────────────────────────────────────────────────────────────

def patient_portal(conn, patient_id: int) -> Optional[PatientPortalView]:
    """Assemble the patient-facing portal view."""
    patient = _q1(conn, "SELECT * FROM public.royan_patients WHERE id = %s", (patient_id,))
    if not patient:
        return None

    upcoming_appts = _q(conn, """
        SELECT a.*, sl.doctor_name, sl.slot_date, sl.slot_time, sl.department
        FROM public.royan_appointments a
        JOIN public.royan_appointment_slots sl ON sl.id = a.slot_id
        WHERE a.patient_id = %s AND sl.slot_date >= CURRENT_DATE
          AND a.status NOT IN ('cancelled', 'no_show')
        ORDER BY sl.slot_date ASC, sl.slot_time ASC LIMIT 5
    """, (patient_id,))

    timeline_rows = eke_service.get_patient_timeline(conn, patient_id, limit=10)
    recent_encounters = [
        EncounterTimelineItem(
            encounter_id=r["id"],
            encounter_type=r.get("encounter_type"),
            status=r.get("status"),
            department=r.get("department"),
            consulting_doctor=r.get("consulting_doctor"),
            chief_complaint=r.get("chief_complaint"),
            diagnosis_notes=r.get("diagnosis_notes"),
            triage_at=_sd(r.get("triage_at")),
            discharge_at=_sd(r.get("discharge_at")),
            created_at=_sd(r.get("created_at")),
            lab_count=int(r.get("lab_count") or 0),
            prescription_count=int(r.get("rx_count") or 0),
            total_billed=float(r.get("total_billed") or 0),
        ) for r in timeline_rows
    ]

    med_rows = eke_service._active_meds(conn, patient_id)
    medications = [
        MedicationRecord(
            id=r["id"], drug_name=r.get("drug_name") or r.get("formulary_name"),
            drug_code=r.get("drug_code"), dosage=r.get("dosage"),
            frequency=r.get("frequency"), route=r.get("route"),
            status=r.get("status"),
            prescribed_at=_sd(r.get("prescribed_at") or r.get("created_at")),
            encounter_id=r.get("encounter_id"),
        ) for r in med_rows
    ]

    billing = eke_service._billing_summary(conn, patient_id)

    return PatientPortalView(
        patient=_patient_demo(patient),
        upcoming_appointments=upcoming_appts,
        recent_encounters=recent_encounters,
        active_medications=medications,
        outstanding_balance=billing.get("outstanding_balance", 0.0),
        assembled_at=_now(),
    )
