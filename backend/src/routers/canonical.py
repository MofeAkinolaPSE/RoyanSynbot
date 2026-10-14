"""Canonical Aggregate API — Chapter 3.13, 8.7, 10 & 15 of the blueprint.

Read-only aggregate endpoints that return a fully composed view across all
clinical domains for a given patient or encounter. These exist alongside the
domain-specific routers (lab, pharmacy, billing) — they do not replace them.

Aggregate endpoints (Chapter 3.13):
  GET  /api/v1/patients/{mrn}/summary       PatientSummary
  GET  /api/v1/patients/{mrn}/timeline      EncounterTimeline
  GET  /api/v1/patients/{mrn}/medications   MedicationHistory
  GET  /api/v1/patients/{mrn}/labs          LaboratoryHistory
  GET  /api/v1/patients/{mrn}/billing       BillingSummary
  GET  /api/v1/encounters/{id}/complete     EncounterComplete
  GET  /api/v1/queue/overview               QueueOverview

Business-capability endpoints — encounter-scoped (Chapter 15):
  POST /api/v1/encounters/{id}/start-consultation
  POST /api/v1/encounters/{id}/order-lab
  POST /api/v1/encounters/{id}/prescribe
  POST /api/v1/encounters/{id}/discharge

Business-capability endpoints — canonical (Chapter 10):
  POST /api/v1/capabilities/register-patient
  POST /api/v1/capabilities/start-encounter
  POST /api/v1/capabilities/complete-consultation/{encounter_id}
  POST /api/v1/capabilities/discharge/{encounter_id}
  POST /api/v1/capabilities/record-vitals/{encounter_id}

Workspace endpoints (Chapter 10):
  GET  /api/v1/workspaces/doctor/{encounter_id}   DoctorWorkspace
  GET  /api/v1/workspaces/nurse/{encounter_id}    NurseWorkspace
  GET  /api/v1/workspaces/billing/{encounter_id}  BillingWorkspace
  GET  /api/v1/workspaces/patient/{patient_id}    PatientPortalView
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import psycopg2.extras
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from src.db import db, audit_event, get_psycopg_dsn
from src.middleware import verify_jwt, require_role
from src.schemas.canonical import (
    BillingSummary,
    BillingWorkspace,
    CompleteConsultationRequest,
    DepartmentQueue,
    DischargeRequest,
    DoctorWorkspace,
    EncounterBrief,
    EncounterComplete,
    EncounterTimeline,
    EncounterTimelineItem,
    LabOrderDetail,
    LaboratoryHistory,
    MedicationHistory,
    MedicationRecord,
    NurseWorkspace,
    OrderLabRequest,
    PatientClinicalContext,
    PatientDemographics,
    PatientPortalView,
    PatientSummary,
    PrescribeRequest,
    QueueEntry,
    QueueOverview,
    RecordVitalsRequest,
    RegisterPatientRequest,
    StartConsultationRequest,
    StartEncounterRequest,
    StaffRef,
)
from src.services import patient_service, encounter_service, clinical_service
from src.services import view_model_factory
from src.services.clinical_shared import get_patient_allergies
from src.constants import (
    TABLE_ENCOUNTERS,
    TABLE_LAB_ORDERS,
    TABLE_LAB_RESULTS,
    TABLE_PATIENTS,
    TABLE_PAYMENTS,
    TABLE_PRESCRIPTIONS,
    TABLE_BILLING,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["Canonical Aggregates"])


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_conn():
    """Borrow a psycopg2 connection from the shared pool (returns RealDictCursor rows)."""
    return db.pool.getconn()


def _put_conn(conn):
    db.pool.putconn(conn)


def _fetch_patient(mrn: str) -> Dict[str, Any]:
    result = db.table(TABLE_PATIENTS).select("*").eq("mrn", mrn).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail=f"Patient '{mrn}' not found")
    return result.data[0]


def _fetch_encounter(encounter_id: int) -> Dict[str, Any]:
    result = db.table(TABLE_ENCOUNTERS).select("*").eq("id", encounter_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail=f"Encounter {encounter_id} not found")
    return result.data[0]


def _str(v: Any) -> Optional[str]:
    return str(v) if v is not None else None


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/v1/patients/{mrn}/summary
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/patients/{mrn}/summary", response_model=PatientSummary)
def get_patient_summary(mrn: str, user=Depends(verify_jwt)):
    """Full patient summary: demographics + clinical snapshot across all domains."""
    pat = _fetch_patient(mrn)
    patient_id = pat["id"]

    # Encounter stats
    enc_rows = db.table(TABLE_ENCOUNTERS).select(
        "id,encounter_type,status,department,consulting_doctor,diagnosis_notes,triage_at,discharge_at,created_at"
    ).eq("patient_id", patient_id).order("created_at", desc=True).execute().data or []

    last_enc = enc_rows[0] if enc_rows else None

    # Last diagnosis (non-empty)
    last_dx = None
    for e in enc_rows:
        if e.get("diagnosis_notes"):
            last_dx = e["diagnosis_notes"][:200]
            break

    # Active medications
    active_rx = db.table(TABLE_PRESCRIPTIONS).select("id").eq(
        "patient_id", patient_id
    ).in_("status", ["pending", "partially_dispensed"]).execute()
    active_count = len(active_rx.data or [])

    # Pending lab orders
    pending_labs = db.table(TABLE_LAB_ORDERS).select("id").eq(
        "patient_id", patient_id
    ).in_("status", ["ordered", "sample_collected", "processing"]).execute()
    pending_count = len(pending_labs.data or [])

    # Outstanding balance (sum of unpaid bills, minus payments recorded
    # against each — royan_billing has no running paid-amount column;
    # actual payments live in the separate royan_payments table).
    conn = _get_conn()
    outstanding = 0.0
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COALESCE(SUM(
                    b.subtotal - b.discount - b.hmo_covered - COALESCE((
                        SELECT SUM(p.amount) FROM public.royan_payments p WHERE p.billing_id = b.id
                    ), 0)
                ), 0.0)
                FROM public.royan_billing b
                WHERE b.patient_id = %s
                  AND b.status NOT IN ('paid', 'waived', 'written_off')
                """,
                (patient_id,),
            )
            row = cur.fetchone()
            if row and row[0] is not None:
                outstanding = float(row[0])
    finally:
        _put_conn(conn)

    # Allergies — active only (previously had no status filter, so
    # resolved/inactive allergies leaked into the CPRS snapshot)
    allergies: List[str] = []
    try:
        allergies = [r["allergen"] for r in get_patient_allergies(patient_id) if r.get("allergen")]
    except Exception:
        allergies = pat.get("allergies") or []

    # Primary doctor
    primary_doc = None
    if pat.get("primary_doctor_id"):
        doc_row = db.table("royan_staff").select(
            "id,full_name,role,specialty"
        ).eq("id", pat["primary_doctor_id"]).execute().data
        if doc_row:
            d = doc_row[0]
            primary_doc = StaffRef(
                id=d["id"],
                name=d.get("full_name") or "",
                role=d.get("role"),
                specialty=d.get("specialty"),
            )

    return PatientSummary(
        patient=PatientDemographics(**{
            k: (_str(pat.get(k)) if k in ("date_of_birth", "registered_at") else pat.get(k))
            for k in PatientDemographics.model_fields
        }),
        total_encounters=len(enc_rows),
        last_encounter_date=_str(last_enc.get("created_at")) if last_enc else None,
        last_encounter_type=last_enc.get("encounter_type") if last_enc else None,
        last_diagnosis=last_dx,
        active_medications=active_count,
        pending_lab_orders=pending_count,
        outstanding_balance=outstanding,
        hmo_coverage=pat.get("hmo_provider"),
        known_allergies=allergies[:20],
        primary_doctor=primary_doc,
    )


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/v1/patients/{mrn}/timeline
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/patients/{mrn}/timeline", response_model=EncounterTimeline)
def get_patient_timeline(
    mrn: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user=Depends(verify_jwt),
):
    """Chronological list of all encounters with per-encounter aggregates."""
    pat = _fetch_patient(mrn)
    patient_id = pat["id"]

    conn = _get_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT
                    e.id            AS encounter_id,
                    e.encounter_type,
                    e.status,
                    e.department,
                    e.consulting_doctor,
                    e.chief_complaint,
                    e.diagnosis_notes,
                    e.triage_at,
                    e.discharge_at,
                    e.created_at,
                    COUNT(DISTINCT lo.id)  AS lab_count,
                    COUNT(DISTINCT rx.id)  AS prescription_count,
                    COALESCE(SUM(b.subtotal - b.discount), 0.0) AS total_billed
                FROM public.royan_encounters e
                LEFT JOIN public.royan_lab_orders lo ON lo.encounter_id = e.id
                LEFT JOIN public.royan_prescriptions rx ON rx.encounter_id = e.id
                LEFT JOIN public.royan_billing b ON b.encounter_id = e.id
                WHERE e.patient_id = %s
                GROUP BY e.id
                ORDER BY e.created_at DESC
                LIMIT %s OFFSET %s
                """,
                (patient_id, limit, offset),
            )
            rows = cur.fetchall()

            cur.execute(
                "SELECT COUNT(*) FROM public.royan_encounters WHERE patient_id = %s",
                (patient_id,),
            )
            total = cur.fetchone()["count"]
    finally:
        _put_conn(conn)

    items = [
        EncounterTimelineItem(
            encounter_id=r["encounter_id"],
            encounter_type=r.get("encounter_type"),
            status=r.get("status"),
            department=r.get("department"),
            consulting_doctor=r.get("consulting_doctor"),
            chief_complaint=r.get("chief_complaint"),
            diagnosis_notes=r.get("diagnosis_notes"),
            triage_at=_str(r.get("triage_at")),
            discharge_at=_str(r.get("discharge_at")),
            created_at=_str(r.get("created_at")),
            lab_count=int(r.get("lab_count") or 0),
            prescription_count=int(r.get("prescription_count") or 0),
            total_billed=float(r.get("total_billed") or 0.0),
        )
        for r in rows
    ]

    return EncounterTimeline(
        patient_mrn=mrn,
        total_encounters=int(total),
        encounters=items,
    )


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/v1/patients/{mrn}/medications
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/patients/{mrn}/medications", response_model=MedicationHistory)
def get_medication_history(
    mrn: str,
    status: Optional[str] = Query(None, description="Filter by status: active, completed, cancelled"),
    limit: int = Query(100, ge=1, le=500),
    user=Depends(verify_jwt),
):
    """Full medication history for a patient, optionally filtered by status."""
    pat = _fetch_patient(mrn)
    patient_id = pat["id"]

    q = db.table(TABLE_PRESCRIPTIONS).select("*").eq("patient_id", patient_id)
    if status:
        q = q.eq("status", status)
    rows = q.order("prescribed_at", desc=True).limit(limit).execute().data or []

    active = sum(1 for r in rows if r.get("status") == "active")

    records = [
        MedicationRecord(
            id=r["id"],
            drug_name=r.get("drug_name"),
            drug_code=r.get("drug_code"),
            dosage=r.get("dosage"),
            frequency=r.get("frequency"),
            route=r.get("route"),
            quantity=r.get("quantity"),
            duration_days=r.get("duration_days"),
            status=r.get("status"),
            prescribed_by=r.get("prescribed_by"),
            prescribed_at=_str(r.get("prescribed_at")),
            encounter_id=r.get("encounter_id"),
        )
        for r in rows
    ]

    return MedicationHistory(
        patient_mrn=mrn,
        total_prescriptions=len(records),
        active_count=active,
        prescriptions=records,
    )


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/v1/patients/{mrn}/labs
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/patients/{mrn}/labs", response_model=LaboratoryHistory)
def get_lab_history(
    mrn: str,
    status: Optional[str] = Query(None, description="pending|collected|resulted|verified"),
    limit: int = Query(100, ge=1, le=500),
    user=Depends(verify_jwt),
):
    """Complete laboratory history for a patient, joined with results."""
    pat = _fetch_patient(mrn)
    patient_id = pat["id"]

    conn = _get_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            status_filter = "AND lo.status = %s" if status else ""
            params = [patient_id] + ([status] if status else []) + [limit]
            cur.execute(
                f"""
                SELECT
                    lo.id,
                    lo.test_name,
                    lo.test_code,
                    lo.urgency,
                    lo.status,
                    lo.sample_type,
                    lo.ordered_by,
                    lo.ordered_at,
                    lo.encounter_id,
                    lr.result_data ->> 'value' AS result_value,
                    lr.result_summary,
                    lr.interpretation,
                    lr.is_critical,
                    lr.resulted_at
                FROM public.royan_lab_orders lo
                LEFT JOIN public.royan_lab_results lr ON lr.lab_order_id = lo.id
                WHERE lo.patient_id = %s
                {status_filter}
                ORDER BY lo.ordered_at DESC
                LIMIT %s
                """,
                params,
            )
            rows = cur.fetchall()
    finally:
        _put_conn(conn)

    critical = sum(1 for r in rows if r.get("is_critical"))
    pending = sum(1 for r in rows if r.get("status") == "pending")

    orders = [
        LabOrderDetail(
            id=r["id"],
            test_name=r.get("test_name"),
            test_code=r.get("test_code"),
            urgency=r.get("urgency"),
            status=r.get("status"),
            sample_type=r.get("sample_type"),
            ordered_by=r.get("ordered_by"),
            ordered_at=_str(r.get("ordered_at")),
            result_value=r.get("result_value"),
            result_summary=r.get("result_summary"),
            interpretation=r.get("interpretation"),
            is_critical=r.get("is_critical"),
            resulted_at=_str(r.get("resulted_at")),
            encounter_id=r.get("encounter_id"),
        )
        for r in rows
    ]

    return LaboratoryHistory(
        patient_mrn=mrn,
        total_orders=len(orders),
        critical_count=critical,
        pending_count=pending,
        orders=orders,
    )


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/v1/patients/{mrn}/billing
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/patients/{mrn}/billing", response_model=BillingSummary)
def get_billing_summary(mrn: str, user=Depends(verify_jwt)):
    """Billing summary: total billed, paid, outstanding, and HMO coverage."""
    pat = _fetch_patient(mrn)
    patient_id = pat["id"]

    conn = _get_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # royan_billing tracks charges (subtotal/discount/hmo_covered), not
            # payments received — those live in royan_payments, keyed by
            # patient_id directly (billing_id is nullable there, e.g. Hope's
            # voucher_payments have no bill concept, so joining through
            # royan_billing would silently drop those rows).
            cur.execute(
                """
                SELECT
                    COUNT(*)                                    AS bill_count,
                    COALESCE(SUM(subtotal - discount), 0.0)     AS total_billed,
                    COALESCE(SUM(hmo_covered), 0.0)              AS hmo_covered
                FROM public.royan_billing
                WHERE patient_id = %s
                """,
                (patient_id,),
            )
            agg = cur.fetchone() or {}

            cur.execute(
                "SELECT COALESCE(SUM(amount), 0.0) AS total_paid FROM public.royan_payments WHERE patient_id = %s",
                (patient_id,),
            )
            total_paid = float((cur.fetchone() or {}).get("total_paid") or 0)

            # Last payment
            cur.execute(
                """
                SELECT received_at, payment_method
                FROM public.royan_payments
                WHERE patient_id = %s
                ORDER BY received_at DESC
                LIMIT 1
                """,
                (patient_id,),
            )
            last_pmt = cur.fetchone()

            # Pending insurance claims — real status values are
            # submitted/pre_authorised/approved/rejected/paid/disputed
            # (royan_insurance_claims_status_check); "pending"/"under_review"
            # were never valid values, so this always matched zero rows.
            cur.execute(
                """
                SELECT COUNT(*)
                FROM public.royan_insurance_claims
                WHERE patient_id = %s
                  AND status IN ('submitted', 'pre_authorised')
                """,
                (patient_id,),
            )
            pending_claims = cur.fetchone()["count"]
    finally:
        _put_conn(conn)

    total_billed = float(agg.get("total_billed") or 0)
    hmo_covered = float(agg.get("hmo_covered") or 0)

    return BillingSummary(
        patient_mrn=mrn,
        total_billed=total_billed,
        total_paid=total_paid,
        outstanding_balance=total_billed - hmo_covered - total_paid,
        hmo_covered=hmo_covered,
        last_payment_date=_str(last_pmt.get("received_at")) if last_pmt else None,
        payment_method=last_pmt.get("payment_method") if last_pmt else None,
        bill_count=int(agg.get("bill_count") or 0),
        pending_claims=int(pending_claims),
    )


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/v1/encounters/{id}/complete
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/encounters/{encounter_id}/complete", response_model=EncounterComplete)
def get_encounter_complete(encounter_id: int, user=Depends(verify_jwt)):
    """Full encounter record: encounter + patient + labs + prescriptions + vitals + notes + billing."""
    enc = _fetch_encounter(encounter_id)
    pat = _fetch_patient_by_id(enc["patient_id"])

    labs = db.table(TABLE_LAB_ORDERS).select("*").eq("encounter_id", encounter_id).execute().data or []
    rx   = db.table(TABLE_PRESCRIPTIONS).select("*").eq("encounter_id", encounter_id).execute().data or []

    vitals: List[Dict] = []
    try:
        vitals = db.table("royan_vitals").select("*").eq("encounter_id", encounter_id).execute().data or []
    except Exception:
        pass

    notes: List[Dict] = []
    try:
        notes = db.table("royan_encounter_notes").select("*").eq("encounter_id", encounter_id).execute().data or []
    except Exception:
        pass

    billing = None
    bill_rows = db.table(TABLE_BILLING).select("*").eq("encounter_id", encounter_id).execute().data
    if bill_rows:
        billing = bill_rows[0]

    return EncounterComplete(
        encounter=EncounterBrief(
            id=enc["id"],
            encounter_type=enc.get("encounter_type"),
            status=enc.get("status"),
            department=enc.get("department"),
            consulting_doctor=enc.get("consulting_doctor"),
            chief_complaint=enc.get("chief_complaint"),
            diagnosis_notes=enc.get("diagnosis_notes"),
            triage_at=_str(enc.get("triage_at")),
            discharge_at=_str(enc.get("discharge_at")),
            created_at=_str(enc.get("created_at")),
        ),
        patient=PatientDemographics(**{k: pat.get(k) for k in PatientDemographics.model_fields}),
        lab_orders=labs,
        prescriptions=rx,
        vitals=vitals,
        notes=notes,
        billing=billing,
    )


def _fetch_patient_by_id(patient_id: int) -> Dict[str, Any]:
    result = db.table(TABLE_PATIENTS).select("*").eq("id", patient_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail=f"Patient {patient_id} not found")
    return result.data[0]


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/v1/queue/overview
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/queue/overview", response_model=QueueOverview)
def get_queue_overview(
    department: Optional[str] = Query(None, description="Filter to a specific department"),
    user=Depends(verify_jwt),
):
    """Live operational queue: active encounters grouped by department with wait times."""
    conn = _get_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            dept_filter = "AND e.department = %s" if department else ""
            params = ([department] if department else [])
            cur.execute(
                f"""
                SELECT
                    e.id            AS encounter_id,
                    e.status,
                    e.department,
                    e.triage_at,
                    e.triage_level,
                    p.mrn           AS patient_mrn,
                    p.first_name || ' ' || p.last_name AS patient_name,
                    EXTRACT(EPOCH FROM (now() - e.triage_at)) / 60 AS wait_minutes
                FROM public.royan_encounters e
                JOIN public.royan_patients p ON p.id = e.patient_id
                WHERE e.status IN ('waiting', 'triaged', 'in_consultation')
                  AND e.discharge_at IS NULL
                  {dept_filter}
                ORDER BY e.triage_at ASC NULLS LAST
                """,
                params,
            )
            rows = cur.fetchall()
    finally:
        _put_conn(conn)

    dept_map: Dict[str, DepartmentQueue] = {}
    for r in rows:
        dept = r.get("department") or "General"
        if dept not in dept_map:
            dept_map[dept] = DepartmentQueue(department=dept)
        dq = dept_map[dept]
        wait = float(r["wait_minutes"]) if r.get("wait_minutes") else None
        status = r.get("status", "")

        if status == "in_consultation":
            dq.in_consultation += 1
        else:
            dq.waiting += 1

        dq.entries.append(QueueEntry(
            encounter_id=r["encounter_id"],
            patient_mrn=r["patient_mrn"],
            patient_name=r["patient_name"],
            triage_level=r.get("triage_level"),
            department=dept,
            status=status,
            wait_minutes=int(wait) if wait is not None else None,
            triage_at=_str(r.get("triage_at")),
        ))

        # Rolling average wait (waiting patients only)
        if status != "in_consultation" and wait is not None:
            if dq.avg_wait_minutes is None:
                dq.avg_wait_minutes = wait
            else:
                dq.avg_wait_minutes = round((dq.avg_wait_minutes + wait) / 2, 1)

    return QueueOverview(
        total_active=len(rows),
        departments=list(dept_map.values()),
        generated_at=_now(),
    )


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/v1/encounters/{id}/start-consultation
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/encounters/{encounter_id}/start-consultation")
def start_consultation(
    encounter_id: int,
    payload: StartConsultationRequest,
    user=Depends(verify_jwt),
):
    """Transition encounter to 'in_consultation'; assign consulting doctor."""
    enc = _fetch_encounter(encounter_id)
    if enc.get("status") not in {"waiting", "triaged", "registered"}:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot start consultation from status '{enc.get('status')}'"
        )

    update: Dict[str, Any] = {"status": "in_consultation"}
    if payload.doctor_name:
        update["consulting_doctor"] = payload.doctor_name
    if payload.department:
        update["department"] = payload.department

    db.table(TABLE_ENCOUNTERS).update(update).eq("id", encounter_id).execute()

    _emit_event(
        event_type="ENCOUNTER_CONSULTING",
        encounter_id=encounter_id,
        patient_id=enc["patient_id"],
        entity_type="encounter",
        entity_id=encounter_id,
        performed_by=user.get("name") or user.get("sub"),
        event_data={"doctor": payload.doctor_name, "department": payload.department},
    )

    audit_event("encounter_consultation_started", {
        "encounter_id": encounter_id, "doctor": payload.doctor_name
    }, actor_id=_actor(user))
    return {"success": True, "encounter_id": encounter_id, "status": "in_consultation"}


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/v1/encounters/{id}/order-lab
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/encounters/{encounter_id}/order-lab", status_code=201)
def order_lab(
    encounter_id: int,
    payload: OrderLabRequest,
    user=Depends(verify_jwt),
):
    """Place a lab order within the context of an encounter."""
    enc = _fetch_encounter(encounter_id)

    row = db.table(TABLE_LAB_ORDERS).insert({
        "encounter_id":  encounter_id,
        "patient_id":    enc["patient_id"],
        "test_name":     payload.test_name,
        "test_code":     payload.test_code,
        "urgency":       payload.urgency,
        "sample_type":   payload.sample_type,
        "ordered_by":    user.get("name") or user.get("sub"),
        "status":        "ordered",
        "notes":         payload.notes,
        "ordered_at":    _now(),
    }).execute()

    order_id = row.data[0]["id"] if row.data else None

    _emit_event(
        event_type="LAB_ORDER_CREATED",
        encounter_id=encounter_id,
        patient_id=enc["patient_id"],
        entity_type="lab_order",
        entity_id=order_id,
        performed_by=user.get("name") or user.get("sub"),
        event_data={"test_name": payload.test_name, "test_code": payload.test_code},
    )

    audit_event("lab_order_created", {
        "encounter_id": encounter_id, "test_name": payload.test_name
    }, actor_id=_actor(user))
    return {"success": True, "order_id": order_id}


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/v1/encounters/{id}/prescribe
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/encounters/{encounter_id}/prescribe", status_code=201)
def prescribe(
    encounter_id: int,
    payload: PrescribeRequest,
    user=Depends(verify_jwt),
):
    """Issue a prescription within an encounter context."""
    enc = _fetch_encounter(encounter_id)

    row = db.table(TABLE_PRESCRIPTIONS).insert({
        "encounter_id":  encounter_id,
        "patient_id":    enc["patient_id"],
        "drug_name":     payload.drug_name,
        "drug_code":     payload.drug_code,
        "dosage":        payload.dosage,
        "frequency":     payload.frequency,
        "route":         payload.route,
        "quantity":      payload.quantity,
        "duration_days": payload.duration_days,
        "status":        "active",
        "prescribed_by": user.get("name") or user.get("sub"),
        "prescribed_at": _now(),
        "notes":         payload.notes,
    }).execute()

    rx_id = row.data[0]["id"] if row.data else None

    _emit_event(
        event_type="PRESCRIPTION_ISSUED",
        encounter_id=encounter_id,
        patient_id=enc["patient_id"],
        entity_type="prescription",
        entity_id=rx_id,
        performed_by=user.get("name") or user.get("sub"),
        event_data={"drug_name": payload.drug_name, "dosage": payload.dosage},
    )

    audit_event("prescription_issued", {
        "encounter_id": encounter_id, "drug_name": payload.drug_name
    }, actor_id=_actor(user))
    return {"success": True, "prescription_id": rx_id}


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/v1/encounters/{id}/discharge
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/encounters/{encounter_id}/discharge")
def discharge_patient(
    encounter_id: int,
    payload: DischargeRequest,
    user=Depends(verify_jwt),
):
    """Formally discharge a patient: updates encounter status and creates a discharge record."""
    enc = _fetch_encounter(encounter_id)
    if enc.get("status") == "discharged":
        raise HTTPException(
            status_code=409,
            detail="Encounter is already discharged"
        )

    discharged_at = _now()

    # Update encounter
    db.table(TABLE_ENCOUNTERS).update({
        "status":       "discharged",
        "discharge_at": discharged_at,
    }).eq("id", encounter_id).execute()

    # Create discharge record
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO public.royan_discharge_records (
                    encounter_id, patient_id, discharge_condition, discharge_diagnosis,
                    discharge_summary, follow_up_instructions, follow_up_date,
                    discharged_by, discharged_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (encounter_id) DO UPDATE SET
                    discharge_condition    = EXCLUDED.discharge_condition,
                    discharge_summary      = EXCLUDED.discharge_summary,
                    discharged_by          = EXCLUDED.discharged_by,
                    discharged_at          = EXCLUDED.discharged_at
                """,
                (
                    encounter_id,
                    enc["patient_id"],
                    payload.discharge_condition,
                    payload.discharge_diagnosis,
                    payload.discharge_summary,
                    payload.follow_up_instructions,
                    payload.follow_up_date,
                    user.get("name") or user.get("sub"),
                    discharged_at,
                ),
            )
            conn.commit()
    finally:
        _put_conn(conn)

    _emit_event(
        event_type="DISCHARGE_COMPLETED",
        encounter_id=encounter_id,
        patient_id=enc["patient_id"],
        entity_type="encounter",
        entity_id=encounter_id,
        performed_by=user.get("name") or user.get("sub"),
        event_data={"condition": payload.discharge_condition},
    )

    audit_event("patient_discharged", {
        "encounter_id": encounter_id,
        "condition": payload.discharge_condition,
    }, actor_id=_actor(user))
    return {
        "success": True,
        "encounter_id": encounter_id,
        "status": "discharged",
        "discharged_at": discharged_at,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Internal: emit to clinical event log
# ─────────────────────────────────────────────────────────────────────────────

def _emit_event(
    event_type: str,
    performed_by: Optional[str] = None,
    encounter_id: Optional[int] = None,
    patient_id: Optional[int] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
    event_data: Optional[Dict] = None,
) -> None:
    """Append an immutable event to royan_clinical_event_log. Fire-and-forget."""
    import json
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO public.royan_clinical_event_log
                    (event_type, encounter_id, patient_id, entity_type, entity_id,
                     performed_by, event_data, occurred_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, now())
                """,
                (
                    event_type,
                    encounter_id,
                    patient_id,
                    entity_type,
                    entity_id,
                    performed_by,
                    json.dumps(event_data or {}),
                ),
            )
            conn.commit()
    except Exception as exc:
        logger.warning("Clinical event log write failed: %s", exc)
    finally:
        _put_conn(conn)


def _correlation_id(request: Request) -> str:
    try:
        return request.state.correlation_id
    except AttributeError:
        return str(uuid.uuid4())


def _actor(user: Dict) -> str:
    return user.get("name") or user.get("sub") or "unknown"


# ─────────────────────────────────────────────────────────────────────────────
# Chapter 10 — Canonical Business-Capability Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/capabilities/register-patient", status_code=201)
def capability_register_patient(
    request: Request,
    payload: RegisterPatientRequest,
    user=Depends(verify_jwt),
):
    """Register a new patient through the canonical patient service.

    Returns MRN, patient_id, and a PATIENT_REGISTERED event is emitted.
    """
    cid = _correlation_id(request)
    actor = _actor(user)

    conn = _get_conn()
    try:
        result = patient_service.register_patient(
            conn=conn,
            data=payload.model_dump(exclude_none=True),
            actor_id=actor,
            correlation_id=cid,
        )
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    finally:
        _put_conn(conn)

    audit_event("patient_registered_canonical", {
        "patient_id": result.get("id"), "mrn": result.get("mrn"),
        "correlation_id": cid,
    }, actor_id=_actor(user))
    return {"success": True, "patient_id": result["id"], "mrn": result["mrn"], "correlation_id": cid}


@router.post("/capabilities/start-encounter", status_code=201)
def capability_start_encounter(
    request: Request,
    payload: StartEncounterRequest,
    user=Depends(verify_jwt),
):
    """Start a new encounter via the canonical encounter service.

    Looks up the patient by MRN, creates the encounter, seeds the workflow
    instance, and emits ENCOUNTER_CREATED.
    """
    cid = _correlation_id(request)
    actor = _actor(user)

    pat = _fetch_patient(payload.patient_mrn)

    conn = _get_conn()
    try:
        encounter_id = encounter_service.start_encounter(
            conn=conn,
            patient_id=pat["id"],
            encounter_type=payload.encounter_type,
            department=payload.department,
            department_id=payload.department_id,
            chief_complaint=payload.chief_complaint,
            actor_id=actor,
            correlation_id=cid,
        )
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    finally:
        _put_conn(conn)

    audit_event("encounter_started_canonical", {
        "encounter_id": encounter_id, "patient_mrn": payload.patient_mrn,
        "encounter_type": payload.encounter_type, "correlation_id": cid,
    }, actor_id=_actor(user))
    return {
        "success": True,
        "encounter_id": encounter_id,
        "patient_mrn": payload.patient_mrn,
        "encounter_type": payload.encounter_type,
        "correlation_id": cid,
    }


@router.post("/capabilities/complete-consultation/{encounter_id}")
def capability_complete_consultation(
    request: Request,
    encounter_id: int,
    payload: CompleteConsultationRequest,
    user=Depends(verify_jwt),
):
    """Mark a consultation complete: records diagnoses, transitions workflow,
    emits CONSULTATION_COMPLETED.
    """
    cid = _correlation_id(request)
    actor = _actor(user)

    conn = _get_conn()
    try:
        result = encounter_service.complete_consultation(
            conn=conn,
            encounter_id=encounter_id,
            diagnosis_notes=payload.diagnosis_notes,
            diagnoses=payload.diagnoses,
            follow_up_required=payload.follow_up_required,
            follow_up_date=payload.follow_up_date,
            actor_id=actor,
            correlation_id=cid,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    finally:
        _put_conn(conn)

    audit_event("consultation_completed_canonical", {
        "encounter_id": encounter_id, "correlation_id": cid,
    }, actor_id=_actor(user))
    return {"success": True, "encounter_id": encounter_id, "status": result.get("status"), "correlation_id": cid}


@router.post("/capabilities/discharge/{encounter_id}")
def capability_discharge(
    request: Request,
    encounter_id: int,
    payload: DischargeRequest,
    user=Depends(verify_jwt),
):
    """Discharge a patient through the canonical encounter service.

    Transitions encounter to 'discharged', creates discharge record,
    emits DISCHARGE_COMPLETED.
    """
    cid = _correlation_id(request)
    actor = _actor(user)

    conn = _get_conn()
    try:
        result = encounter_service.discharge_patient(
            conn=conn,
            encounter_id=encounter_id,
            discharge_data=payload.model_dump(exclude_none=True),
            actor_id=actor,
            correlation_id=cid,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    finally:
        _put_conn(conn)

    audit_event("patient_discharged_canonical", {
        "encounter_id": encounter_id, "correlation_id": cid,
    }, actor_id=_actor(user))
    return {
        "success": True, "encounter_id": encounter_id,
        "status": "discharged", "discharged_at": result.get("discharge_at"),
        "correlation_id": cid,
    }


@router.post("/capabilities/record-vitals/{encounter_id}", status_code=201)
def capability_record_vitals(
    request: Request,
    encounter_id: int,
    payload: RecordVitalsRequest,
    user=Depends(verify_jwt),
):
    """Record a vitals observation for an active encounter."""
    cid = _correlation_id(request)
    actor = _actor(user)

    enc = _fetch_encounter(encounter_id)
    conn = _get_conn()
    try:
        vitals_id = clinical_service.record_vitals(
            conn=conn,
            encounter_id=encounter_id,
            patient_id=enc["patient_id"],
            vitals=payload.model_dump(exclude_none=True),
            actor_id=actor,
            correlation_id=cid,
        )
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    finally:
        _put_conn(conn)

    audit_event("vitals_recorded_canonical", {
        "encounter_id": encounter_id, "vitals_id": vitals_id, "correlation_id": cid,
    }, actor_id=actor)
    return {"success": True, "vitals_id": vitals_id, "encounter_id": encounter_id, "correlation_id": cid}


# ─────────────────────────────────────────────────────────────────────────────
# Chapter 10 — Workspace View Endpoints (one-call role-specific composites)
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/workspaces/doctor/{encounter_id}", response_model=DoctorWorkspace)
def workspace_doctor(
    request: Request,
    encounter_id: int,
    user=Depends(verify_jwt),
):
    """Doctor consultation workspace: patient + encounter + diagnoses + vitals
    + medications + allergies + pending labs + risk flags in a single call.
    """
    conn = _get_conn()
    try:
        ws = view_model_factory.doctor_workspace(conn, encounter_id)
    finally:
        _put_conn(conn)

    if not ws:
        raise HTTPException(status_code=404, detail=f"Encounter {encounter_id} not found")
    return ws


@router.get("/workspaces/nurse/{encounter_id}", response_model=NurseWorkspace)
def workspace_nurse(
    request: Request,
    encounter_id: int,
    user=Depends(verify_jwt),
):
    """Nurse workspace: patient + encounter + latest vitals + medications
    + allergies + nursing tasks in a single call.
    """
    conn = _get_conn()
    try:
        ws = view_model_factory.nurse_workspace(conn, encounter_id)
    finally:
        _put_conn(conn)

    if not ws:
        raise HTTPException(status_code=404, detail=f"Encounter {encounter_id} not found")
    return ws


@router.get("/workspaces/billing/{encounter_id}", response_model=BillingWorkspace)
def workspace_billing(
    request: Request,
    encounter_id: int,
    user=Depends(verify_jwt),
):
    """Billing workspace: patient + encounter + billing summary + bill items
    + payments + insurance claim status in a single call.
    """
    conn = _get_conn()
    try:
        ws = view_model_factory.billing_workspace(conn, encounter_id)
    finally:
        _put_conn(conn)

    if not ws:
        raise HTTPException(status_code=404, detail=f"Encounter {encounter_id} not found")
    return ws


@router.get("/workspaces/patient/{patient_id}", response_model=PatientPortalView)
def workspace_patient_portal(
    request: Request,
    patient_id: int,
    user=Depends(verify_jwt),
):
    """Patient portal view: demographics + upcoming appointments + recent
    encounters + active medications + outstanding balance in a single call.
    """
    conn = _get_conn()
    try:
        ws = view_model_factory.patient_portal(conn, patient_id)
    finally:
        _put_conn(conn)

    if not ws:
        raise HTTPException(status_code=404, detail=f"Patient {patient_id} not found")
    return ws
