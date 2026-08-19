"""Enterprise Knowledge Engine (EKE) — Chapter 9 of the Implementation Guide.

Assembles longitudinal clinical knowledge objects by querying across all
Silver-layer domains. The EKE is the sole authority for producing
PatientClinicalContext, EncounterContext, and workspace view models.

Do not confuse with knowledge_service.py (RAG/vector search engine).
This module handles clinical data aggregation, not semantic search.

Functions:
  assemble_patient_context(conn, patient_id) → PatientClinicalContext | None
  assemble_encounter_context(conn, encounter_id) → dict
  get_patient_timeline(conn, patient_id, limit) → list[dict]
  get_medication_history(conn, patient_id) → list[dict]
  get_clinical_risk_profile(conn, patient_id) → dict
  invalidate_patient_context(conn, patient_id) → None
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import psycopg2.extras

from src.schemas.canonical import (
    DiagnosisRecord,
    EncounterBrief,
    LabOrderDetail,
    MedicationRecord,
    ObservationRecord,
    PatientClinicalContext,
    PatientDemographics,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Query helpers
# ─────────────────────────────────────────────────────────────────────────────

def _q(conn, sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            return [dict(r) for r in cur.fetchall()]
    except Exception as exc:
        logger.warning("EKE query failed: %s | %.80s", exc, sql)
        # A failed query aborts the current Postgres transaction — every
        # subsequent query on this same connection would fail too
        # ("current transaction is aborted...") until this rolls it back.
        # Without this, one bad query silently blanks every domain section
        # assembled after it, not just its own.
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


# ─────────────────────────────────────────────────────────────────────────────
# Domain loaders (private)
# ─────────────────────────────────────────────────────────────────────────────

def _patient(conn, pid: int) -> Optional[Dict]:
    return _q1(conn, "SELECT * FROM public.royan_patients WHERE id = %s", (pid,))


def _active_encounter(conn, pid: int) -> Optional[Dict]:
    return _q1(conn, """
        SELECT e.*, COALESCE(s.full_name, e.consulting_doctor) AS doctor_name
        FROM public.royan_encounters e
        LEFT JOIN public.royan_staff s ON s.id = e.doctor_id
        WHERE e.patient_id = %s AND e.status NOT IN ('discharged', 'closed')
        ORDER BY e.created_at DESC LIMIT 1
    """, (pid,))


def _latest_vitals(conn, pid: int) -> List[Dict]:
    return _q(conn, """
        SELECT * FROM public.royan_vitals WHERE patient_id = %s
        ORDER BY recorded_at DESC LIMIT 5
    """, (pid,))


def _active_diagnoses(conn, pid: int) -> List[Dict]:
    return _q(conn, """
        SELECT * FROM public.royan_clinical_diagnoses
        WHERE patient_id = %s
        ORDER BY diagnosed_at DESC LIMIT 20
    """, (pid,))


def _active_meds(conn, pid: int) -> List[Dict]:
    return _q(conn, """
        SELECT p.*, d.generic_name AS formulary_name
        FROM public.royan_prescriptions p
        LEFT JOIN public.royan_drug_formulary d ON d.id = p.formulary_id
        WHERE p.patient_id = %s AND p.status NOT IN ('cancelled', 'completed')
        ORDER BY p.prescribed_at DESC LIMIT 20
    """, (pid,))


def _pending_labs(conn, pid: int) -> List[Dict]:
    return _q(conn, """
        SELECT lo.*, lc.name AS catalog_name
        FROM public.royan_lab_orders lo
        LEFT JOIN public.royan_lab_catalog lc ON lc.id = lo.catalog_id
        WHERE lo.patient_id = %s AND lo.status NOT IN ('resulted', 'verified', 'cancelled')
        ORDER BY lo.ordered_at DESC LIMIT 10
    """, (pid,))


def _recent_results(conn, pid: int) -> List[Dict]:
    return _q(conn, """
        SELECT lo.*, lr.result_summary, lr.interpretation, lr.is_critical, lr.resulted_at,
               lc.name AS catalog_name
        FROM public.royan_lab_orders lo
        LEFT JOIN public.royan_lab_results lr ON lr.lab_order_id = lo.id
        LEFT JOIN public.royan_lab_catalog lc ON lc.id = lo.catalog_id
        WHERE lo.patient_id = %s AND lo.status IN ('resulted', 'verified')
        ORDER BY COALESCE(lr.resulted_at, lo.ordered_at) DESC LIMIT 10
    """, (pid,))


def _billing_summary(conn, pid: int) -> Dict:
    # royan_billing has no running paid-amount column — actual payment
    # records live in the separate royan_payments table.
    b = _q1(conn, """
        SELECT COUNT(*) AS cnt,
               COALESCE(SUM(subtotal), 0) AS total_billed,
               COALESCE(SUM(hmo_covered), 0) AS hmo_covered
        FROM public.royan_billing WHERE patient_id = %s
    """, (pid,)) or {}
    p = _q1(conn, """
        SELECT COALESCE(SUM(amount), 0) AS total_paid
        FROM public.royan_payments WHERE patient_id = %s
    """, (pid,)) or {}
    t = float(b.get("total_billed") or 0)
    paid = float(p.get("total_paid") or 0)
    h = float(b.get("hmo_covered") or 0)
    return {"total_billed": t, "total_paid": paid, "hmo_covered": h,
            "outstanding_balance": round(t - paid - h, 2), "bill_count": int(b.get("cnt") or 0)}


def _allergies(conn, pid: int) -> List[str]:
    rows = _q(conn, "SELECT allergen FROM public.royan_allergies WHERE patient_id = %s AND status = 'active'", (pid,))
    return [r["allergen"] for r in rows if r.get("allergen")]


def _hmo_name(conn, pid: int) -> Optional[str]:
    r = _q1(conn, """
        SELECT h.name FROM public.royan_patient_insurance pi
        JOIN public.royan_hmos h ON h.id = pi.hmo_id
        WHERE pi.patient_id = %s AND pi.status = 'active' LIMIT 1
    """, (pid,))
    return r["name"] if r else None


def _risk_flags(conn, pid: int, allergies: List[str], diagnoses: List[Dict]) -> List[str]:
    flags = []
    if allergies:
        flags.append(f"Allergies: {', '.join(allergies[:3])}")
    chronic_codes = {"E11", "E14", "I10", "I25", "I50", "N18", "J45"}
    for d in diagnoses:
        icd = (d.get("icd_code") or "").upper()
        if any(icd.startswith(c) for c in chronic_codes):
            flags.append(f"Chronic: {d.get('description', icd)}")
    critical = _q(conn, """
        SELECT lo.test_name FROM public.royan_lab_orders lo
        JOIN public.royan_lab_results lr ON lr.lab_order_id = lo.id
        WHERE lo.patient_id = %s AND lr.is_critical = true
        ORDER BY lr.resulted_at DESC LIMIT 3
    """, (pid,))
    for c in critical:
        flags.append(f"Critical lab: {c.get('test_name', '?')}")
    return flags[:10]


# ─────────────────────────────────────────────────────────────────────────────
# Public EKE functions
# ─────────────────────────────────────────────────────────────────────────────

def assemble_patient_context(conn, patient_id: int) -> Optional[PatientClinicalContext]:
    """Assemble complete 7-domain PatientClinicalContext. Returns None if not found."""
    pr = _patient(conn, patient_id)
    if not pr:
        return None

    patient = PatientDemographics(
        id=pr["id"], mrn=pr["mrn"],
        first_name=pr["first_name"], last_name=pr["last_name"],
        date_of_birth=_sd(pr.get("date_of_birth")), gender=pr.get("gender"),
        phone=pr.get("phone"), email=pr.get("email"), address=pr.get("address"),
        blood_group=pr.get("blood_group"), genotype=pr.get("genotype"),
        hmo_provider=pr.get("hmo_provider"), hmo_id=pr.get("hmo_id"),
        registered_at=_sd(pr.get("created_at")),
    )

    enc_row = _active_encounter(conn, patient_id)
    active_enc = EncounterBrief(
        id=enc_row["id"],
        encounter_type=enc_row.get("encounter_type"),
        status=enc_row.get("status"),
        department=enc_row.get("department"),
        consulting_doctor=enc_row.get("doctor_name"),
        chief_complaint=enc_row.get("chief_complaint"),
        diagnosis_notes=enc_row.get("diagnosis_notes"),
        triage_at=_sd(enc_row.get("triage_at")),
        discharge_at=_sd(enc_row.get("discharge_at")),
        created_at=_sd(enc_row.get("created_at")),
    ) if enc_row else None

    vitals_rows = _latest_vitals(conn, patient_id)
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
        ) for r in vitals_rows
    ]

    diag_rows = _active_diagnoses(conn, patient_id)
    diagnoses = [
        DiagnosisRecord(
            id=r.get("id"), icd_code=r.get("icd_code"),
            description=r.get("description") or "",
            diagnosis_type=r.get("diagnosis_type", "primary"),
            onset_date=_sd(r.get("onset_date")),
            resolution_date=_sd(r.get("resolution_date")),
            is_chronic=bool(r.get("is_chronic")),
            recorded_by=r.get("diagnosed_by"),
            recorded_at=_sd(r.get("diagnosed_at") or r.get("created_at")),
            encounter_id=r.get("encounter_id"),
        ) for r in diag_rows
    ]

    med_rows = _active_meds(conn, patient_id)
    medications = [
        MedicationRecord(
            id=r["id"], drug_name=r.get("drug_name") or r.get("formulary_name"),
            drug_code=r.get("drug_code"), dosage=r.get("dosage"),
            frequency=r.get("frequency"), route=r.get("route"),
            quantity=r.get("quantity"), duration_days=r.get("duration_days"),
            status=r.get("status"), prescribed_by=r.get("prescribed_by"),
            prescribed_at=_sd(r.get("prescribed_at") or r.get("created_at")),
            encounter_id=r.get("encounter_id"),
        ) for r in med_rows
    ]

    pending = [
        LabOrderDetail(
            id=r["id"], test_name=r.get("catalog_name") or r.get("test_name"),
            test_code=r.get("test_code"), urgency=r.get("urgency", "routine"),
            status=r.get("status"), sample_type=r.get("sample_type"),
            ordered_by=r.get("ordered_by"),
            ordered_at=_sd(r.get("ordered_at")),
            encounter_id=r.get("encounter_id"),
        ) for r in _pending_labs(conn, patient_id)
    ]

    results = [
        LabOrderDetail(
            id=r["id"], test_name=r.get("catalog_name") or r.get("test_name"),
            test_code=r.get("test_code"), status=r.get("status"),
            result_value=r.get("result_summary"), result_summary=r.get("result_summary"),
            interpretation=r.get("interpretation"),
            is_critical=bool(r.get("is_critical")),
            resulted_at=_sd(r.get("resulted_at")),
            encounter_id=r.get("encounter_id"),
        ) for r in _recent_results(conn, patient_id)
    ]

    billing = _billing_summary(conn, patient_id)
    allergy_list = _allergies(conn, patient_id)
    hmo = _hmo_name(conn, patient_id) or pr.get("hmo_provider")
    flags = _risk_flags(conn, patient_id, allergy_list, diag_rows)
    enc_count_row = _q1(conn, "SELECT COUNT(*) AS cnt FROM public.royan_encounters WHERE patient_id = %s", (patient_id,))
    enc_count = int((enc_count_row or {}).get("cnt") or 0)
    notes_count_row = _q1(conn, "SELECT COUNT(*) AS cnt FROM public.royan_encounter_notes WHERE patient_id = %s", (patient_id,))
    notes_count = int((notes_count_row or {}).get("cnt") or 0)

    return PatientClinicalContext(
        patient=patient,
        active_encounter=active_enc,
        encounter_count=enc_count,
        last_visit_date=_sd(enc_row.get("created_at")) if enc_row else None,
        latest_vitals=latest_vitals,
        active_diagnoses=diagnoses,
        chronic_conditions=[d for d in diagnoses if d.is_chronic],
        active_medications=medications,
        known_allergies=allergy_list,
        pending_lab_orders=pending,
        recent_lab_results=results,
        outstanding_balance=billing.get("outstanding_balance", 0.0),
        hmo_coverage=hmo,
        risk_flags=flags,
        clinical_notes_count=notes_count,
        context_assembled_at=datetime.now(timezone.utc).isoformat(),
        is_stale=False,
    )


def assemble_encounter_context(conn, encounter_id: int) -> Dict[str, Any]:
    """Full encounter context including all clinical sub-domains."""
    enc = _q1(conn, "SELECT * FROM public.royan_encounters WHERE id = %s", (encounter_id,))
    if not enc:
        return {}
    pid = enc.get("patient_id")
    return {
        "encounter": dict(enc),
        "patient": _patient(conn, pid) if pid else None,
        "vitals": _q(conn, "SELECT * FROM public.royan_vitals WHERE encounter_id = %s ORDER BY recorded_at", (encounter_id,)),
        "notes": _q(conn, "SELECT * FROM public.royan_encounter_notes WHERE encounter_id = %s ORDER BY created_at", (encounter_id,)),
        "lab_orders": _q(conn, """
            SELECT lo.*, lr.result_summary, lr.interpretation, lr.is_critical, lr.resulted_at,
                   lc.name AS catalog_name
            FROM public.royan_lab_orders lo
            LEFT JOIN public.royan_lab_results lr ON lr.lab_order_id = lo.id
            LEFT JOIN public.royan_lab_catalog lc ON lc.id = lo.catalog_id
            WHERE lo.encounter_id = %s ORDER BY lo.ordered_at
        """, (encounter_id,)),
        "prescriptions": _q(conn, """
            SELECT p.*, d.generic_name AS formulary_name
            FROM public.royan_prescriptions p
            LEFT JOIN public.royan_drug_formulary d ON d.id = p.formulary_id
            WHERE p.encounter_id = %s ORDER BY p.prescribed_at
        """, (encounter_id,)),
        "billing": _q1(conn, "SELECT * FROM public.royan_billing WHERE encounter_id = %s ORDER BY billed_at DESC LIMIT 1", (encounter_id,)),
        "workflow_state": _q1(conn, """
            SELECT current_state, is_terminal, last_transitioned_at
            FROM workflow.instances WHERE entity_type = 'encounter' AND entity_id = %s
        """, (encounter_id,)),
        "assembled_at": datetime.now(timezone.utc).isoformat(),
    }


def get_patient_timeline(conn, patient_id: int, limit: int = 50) -> List[Dict[str, Any]]:
    return _q(conn, """
        SELECT e.id, e.encounter_type, e.status, e.department, e.consulting_doctor,
               e.chief_complaint, e.diagnosis_notes, e.triage_at, e.discharge_at, e.created_at,
               (SELECT COUNT(*) FROM public.royan_lab_orders lo WHERE lo.encounter_id = e.id) AS lab_count,
               (SELECT COUNT(*) FROM public.royan_prescriptions rx WHERE rx.encounter_id = e.id) AS rx_count,
               (SELECT COALESCE(SUM(b.subtotal), 0) FROM public.royan_billing b WHERE b.encounter_id = e.id) AS total_billed
        FROM public.royan_encounters e
        WHERE e.patient_id = %s ORDER BY e.created_at DESC LIMIT %s
    """, (patient_id, limit))


def get_medication_history(conn, patient_id: int) -> List[Dict[str, Any]]:
    return _q(conn, """
        SELECT p.*, d.generic_name AS formulary_name, d.drug_class,
               disp.dispensed_at, disp.quantity_dispensed
        FROM public.royan_prescriptions p
        LEFT JOIN public.royan_drug_formulary d ON d.id = p.formulary_id
        LEFT JOIN public.royan_dispensing disp ON disp.prescription_id = p.id
        WHERE p.patient_id = %s ORDER BY p.prescribed_at DESC
    """, (patient_id,))


def get_clinical_risk_profile(conn, patient_id: int) -> Dict[str, Any]:
    allergy_list = _allergies(conn, patient_id)
    diag_rows = _active_diagnoses(conn, patient_id)
    flags = _risk_flags(conn, patient_id, allergy_list, diag_rows)
    critical = _q(conn, """
        SELECT lo.test_name, lr.result_summary, lr.resulted_at
        FROM public.royan_lab_orders lo
        JOIN public.royan_lab_results lr ON lr.lab_order_id = lo.id
        WHERE lo.patient_id = %s AND lr.is_critical = true
        ORDER BY lr.resulted_at DESC LIMIT 5
    """, (patient_id,))
    return {
        "patient_id": patient_id,
        "known_allergies": allergy_list,
        "active_diagnoses": [d.get("description") for d in diag_rows if d.get("description")],
        "chronic_conditions": [d.get("description") for d in diag_rows if d.get("is_chronic")],
        "critical_lab_results": critical,
        "risk_flags": flags,
        "risk_level": "high" if len(flags) >= 3 else ("medium" if flags else "low"),
    }


def invalidate_patient_context(conn, patient_id: int) -> None:
    """Mark cached knowledge object as stale after any domain event."""
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE knowledge.patient_context_cache SET is_stale = true, invalidated_at = now() WHERE patient_id = %s",
                (patient_id,),
            )
        conn.commit()
    except Exception as exc:
        logger.debug("invalidate_patient_context (non-fatal): %s", exc)
