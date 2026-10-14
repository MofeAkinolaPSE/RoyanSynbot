"""Clinical Observability & KPI Router — Chapter 17 of the blueprint.

Provides real-time operational intelligence for clinical administrators
and department heads. All endpoints require authenticated access; some
require the 'admin' or 'manager' role.

Endpoints:
  GET /api/v1/ops/health               Platform + DB health check
  GET /api/v1/ops/clinical-kpis        Real-time clinical performance KPIs
  GET /api/v1/ops/workflow-performance  Encounter lifecycle and throughput
  GET /api/v1/ops/data-quality-live    Current data quality scores per domain
  GET /api/v1/ops/bed-census           Ward bed occupancy and turnover
  GET /api/v1/ops/lab-performance      Lab turnaround time analysis
  GET /api/v1/ops/revenue-snapshot     Revenue by payer and service period
"""
from __future__ import annotations

import logging
import os
import time
from datetime import date, datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

import psycopg2.extras
from fastapi import APIRouter, Depends, Query

from src.db import db, get_psycopg_dsn
from src.middleware import verify_jwt

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/ops", tags=["Observability"])


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_conn():
    return db.pool.getconn()


def _put_conn(conn):
    db.pool.putconn(conn)


def _today() -> str:
    return date.today().isoformat()


def _days_ago(n: int) -> str:
    return (date.today() - timedelta(days=n)).isoformat()


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/v1/ops/health
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/health")
def platform_health():
    """Infrastructure health: API alive, DB reachable, table row counts."""
    t0 = time.perf_counter()
    db_ok = False
    patient_count = 0
    encounter_count = 0

    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM public.royan_patients")
            patient_count = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM public.royan_encounters")
            encounter_count = cur.fetchone()[0]
        db_ok = True
    except Exception as exc:
        logger.error("Health check DB error: %s", exc)
    finally:
        _put_conn(conn)

    latency_ms = round((time.perf_counter() - t0) * 1000, 1)

    return {
        "status": "ok" if db_ok else "degraded",
        "api": "ok",
        "database": "ok" if db_ok else "error",
        "db_latency_ms": latency_ms,
        "patient_count": patient_count,
        "encounter_count": encounter_count,
        "checked_at": _now_utc(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/v1/ops/clinical-kpis
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/clinical-kpis")
def clinical_kpis(
    since: Optional[str] = Query(None, description="ISO date YYYY-MM-DD (default: today)"),
    user=Depends(verify_jwt),
):
    """Real-time clinical KPIs: queue wait, lab TAT, bed occupancy, discharge rate."""
    since_date = since or _today()

    conn = _get_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:

            # Active queue size & avg wait. Real status enum (see
            # ENCOUNTER_STATUS_ALLOWED in constants.py) has no 'waiting' or
            # 'in_consultation' value — "active" here means anything short
            # of discharged, which also covers the intent more robustly than
            # naming specific mid-flow statuses that could change.
            cur.execute("""
                SELECT
                    COUNT(*) AS active_encounters,
                    ROUND(AVG(EXTRACT(EPOCH FROM (now() - triage_at)) / 60)::numeric, 1)
                        AS avg_wait_minutes
                FROM public.royan_encounters
                WHERE status != 'discharged'
                  AND discharge_at IS NULL
            """)
            queue = cur.fetchone() or {}

            # Today's arrivals and discharges
            cur.execute("""
                SELECT
                    COUNT(*) FILTER (WHERE DATE(created_at) = CURRENT_DATE) AS arrived_today,
                    COUNT(*) FILTER (WHERE DATE(discharge_at) = CURRENT_DATE) AS discharged_today
                FROM public.royan_encounters
                WHERE created_at >= %s::date
            """, (since_date,))
            throughput = cur.fetchone() or {}

            # Lab TAT (hours from ordered_at to result)
            cur.execute("""
                SELECT
                    ROUND(AVG(
                        EXTRACT(EPOCH FROM (lr.resulted_at - lo.ordered_at)) / 3600
                    )::numeric, 2) AS avg_lab_tat_hours,
                    COUNT(lr.id) AS results_today
                FROM public.royan_lab_orders lo
                JOIN public.royan_lab_results lr ON lr.lab_order_id = lo.id
                WHERE DATE(lo.ordered_at) >= %s::date
            """, (since_date,))
            lab = cur.fetchone() or {}

            # Bed occupancy
            cur.execute("""
                SELECT
                    COUNT(*) FILTER (WHERE status = 'occupied') AS occupied_beds,
                    COUNT(*) AS total_beds
                FROM public.royan_beds
            """)
            beds = cur.fetchone() or {}

            # Pending critical lab results — royan_lab_results has no
            # acknowledged_at column; verified_at is the real analog
            # (a clinician hasn't reviewed/signed off on the result yet).
            cur.execute("""
                SELECT COUNT(*) AS critical_unacked
                FROM public.royan_lab_results
                WHERE is_critical = true
                  AND verified_at IS NULL
            """)
            critical = cur.fetchone() or {}

            # Pending prescriptions (issued but not dispensed)
            cur.execute("""
                SELECT COUNT(*) AS pending_rx
                FROM public.royan_prescriptions
                WHERE status = 'active'
                  AND DATE(prescribed_at) >= %s::date
            """, (since_date,))
            rx = cur.fetchone() or {}

    finally:
        _put_conn(conn)

    occupied = int(beds.get("occupied_beds") or 0)
    total_beds = int(beds.get("total_beds") or 1)

    return {
        "as_of": _now_utc(),
        "since": since_date,
        "queue": {
            "active_encounters": int(queue.get("active_encounters") or 0),
            "avg_wait_minutes": float(queue.get("avg_wait_minutes") or 0),
        },
        "throughput": {
            "arrived_today": int(throughput.get("arrived_today") or 0),
            "discharged_today": int(throughput.get("discharged_today") or 0),
        },
        "laboratory": {
            "avg_tat_hours": float(lab.get("avg_lab_tat_hours") or 0),
            "results_today": int(lab.get("results_today") or 0),
            "critical_unacknowledged": int(critical.get("critical_unacked") or 0),
        },
        "beds": {
            "occupied": occupied,
            "total": total_beds,
            "occupancy_pct": round(occupied / total_beds * 100, 1) if total_beds else 0,
        },
        "pharmacy": {
            "pending_prescriptions": int(rx.get("pending_rx") or 0),
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/v1/ops/workflow-performance
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/workflow-performance")
def workflow_performance(
    days: int = Query(7, ge=1, le=90, description="Look-back window in days"),
    user=Depends(verify_jwt),
):
    """Encounter lifecycle analysis: completion rates and bottleneck detection."""
    since = _days_ago(days)

    conn = _get_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:

            # Status distribution
            cur.execute("""
                SELECT status, COUNT(*) AS cnt
                FROM public.royan_encounters
                WHERE created_at >= %s::date
                GROUP BY status
                ORDER BY cnt DESC
            """, (since,))
            status_dist = {r["status"]: int(r["cnt"]) for r in cur.fetchall()}

            # Department throughput
            cur.execute("""
                SELECT
                    COALESCE(department, 'Unassigned') AS department,
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE status = 'discharged') AS discharged,
                    ROUND(AVG(
                        EXTRACT(EPOCH FROM (discharge_at - triage_at)) / 3600
                    ) FILTER (WHERE discharge_at IS NOT NULL)::numeric, 2)
                        AS avg_los_hours
                FROM public.royan_encounters
                WHERE created_at >= %s::date
                GROUP BY department
                ORDER BY total DESC
                LIMIT 15
            """, (since,))
            dept_rows = cur.fetchall()

            # Average Length of Stay overall
            cur.execute("""
                SELECT
                    ROUND(AVG(
                        EXTRACT(EPOCH FROM (discharge_at - triage_at)) / 3600
                    )::numeric, 2) AS avg_los_hours,
                    ROUND(AVG(
                        EXTRACT(EPOCH FROM (triage_at - created_at)) / 60
                    )::numeric, 1) AS avg_reg_to_triage_minutes
                FROM public.royan_encounters
                WHERE created_at >= %s::date
                  AND discharge_at IS NOT NULL
            """, (since,))
            overall = cur.fetchone() or {}

    finally:
        _put_conn(conn)

    total = sum(status_dist.values())
    discharged = status_dist.get("discharged", 0)

    return {
        "period_days": days,
        "since": since,
        "total_encounters": total,
        "completion_rate_pct": round(discharged / total * 100, 1) if total else 0,
        "status_distribution": status_dist,
        "avg_length_of_stay_hours": float(overall.get("avg_los_hours") or 0),
        "avg_registration_to_triage_minutes": float(
            overall.get("avg_reg_to_triage_minutes") or 0
        ),
        "by_department": [
            {
                "department": r["department"],
                "total": int(r["total"]),
                "discharged": int(r["discharged"]),
                "completion_rate_pct": round(
                    int(r["discharged"]) / max(int(r["total"]), 1) * 100, 1
                ),
                "avg_los_hours": float(r["avg_los_hours"] or 0),
            }
            for r in dept_rows
        ],
    }


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/v1/ops/data-quality-live
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/data-quality-live")
def data_quality_live(user=Depends(verify_jwt)):
    """Current data quality scores per clinical domain (completeness + integrity)."""
    conn = _get_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:

            # Patient completeness
            cur.execute("""
                SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE mrn IS NOT NULL AND mrn != '') AS has_mrn,
                    COUNT(*) FILTER (WHERE first_name IS NOT NULL AND first_name != '') AS has_first,
                    COUNT(*) FILTER (WHERE last_name IS NOT NULL AND last_name != '') AS has_last,
                    COUNT(*) FILTER (WHERE date_of_birth IS NOT NULL) AS has_dob,
                    COUNT(*) FILTER (WHERE phone IS NOT NULL AND phone != '') AS has_phone
                FROM public.royan_patients
            """)
            pat = cur.fetchone() or {}

            # Encounter integrity (no orphaned records)
            cur.execute("""
                SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE patient_id IS NOT NULL) AS has_patient,
                    COUNT(*) FILTER (WHERE department IS NOT NULL AND department != '') AS has_dept,
                    COUNT(*) FILTER (WHERE consulting_doctor IS NOT NULL AND consulting_doctor != '')
                        AS has_doctor
                FROM public.royan_encounters
            """)
            enc = cur.fetchone() or {}

            # Lab orders: test name resolution
            cur.execute("""
                SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER (
                        WHERE lower(test_name) NOT IN (
                            'imported lab order', 'lab test', 'laboratory test',
                            'test', 'investigation', ''
                        ) AND test_name IS NOT NULL
                    ) AS has_real_name,
                    COUNT(*) FILTER (WHERE test_code IS NOT NULL AND test_code != '')
                        AS has_code,
                    COUNT(*) FILTER (WHERE status = 'resulted') AS resulted
                FROM public.royan_lab_orders
            """)
            lab = cur.fetchone() or {}

            # Prescriptions
            cur.execute("""
                SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE drug_name IS NOT NULL AND drug_name != '') AS has_drug,
                    COUNT(*) FILTER (WHERE dosage IS NOT NULL AND dosage != '') AS has_dosage
                FROM public.royan_prescriptions
            """)
            rx = cur.fetchone() or {}

            # Billing
            cur.execute("""
                SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE patient_id IS NOT NULL) AS has_patient,
                    COUNT(*) FILTER (WHERE subtotal > 0) AS has_amount
                FROM public.royan_billing
            """)
            bill = cur.fetchone() or {}

    finally:
        _put_conn(conn)

    def _pct(num, denom):
        return round(int(num or 0) / max(int(denom or 1), 1) * 100, 1)

    return {
        "generated_at": _now_utc(),
        "domains": {
            "patients": {
                "total": int(pat.get("total") or 0),
                "mrn_completeness_pct": _pct(pat.get("has_mrn"), pat.get("total")),
                "name_completeness_pct": _pct(pat.get("has_first"), pat.get("total")),
                "dob_completeness_pct": _pct(pat.get("has_dob"), pat.get("total")),
                "phone_completeness_pct": _pct(pat.get("has_phone"), pat.get("total")),
            },
            "encounters": {
                "total": int(enc.get("total") or 0),
                "patient_fk_pct": _pct(enc.get("has_patient"), enc.get("total")),
                "department_pct": _pct(enc.get("has_dept"), enc.get("total")),
                "doctor_assignment_pct": _pct(enc.get("has_doctor"), enc.get("total")),
            },
            "lab_orders": {
                "total": int(lab.get("total") or 0),
                "name_resolution_pct": _pct(lab.get("has_real_name"), lab.get("total")),
                "test_code_pct": _pct(lab.get("has_code"), lab.get("total")),
                "resulted_pct": _pct(lab.get("resulted"), lab.get("total")),
            },
            "prescriptions": {
                "total": int(rx.get("total") or 0),
                "drug_name_pct": _pct(rx.get("has_drug"), rx.get("total")),
                "dosage_pct": _pct(rx.get("has_dosage"), rx.get("total")),
            },
            "billing": {
                "total": int(bill.get("total") or 0),
                "patient_linked_pct": _pct(bill.get("has_patient"), bill.get("total")),
                "has_amount_pct": _pct(bill.get("has_amount"), bill.get("total")),
            },
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/v1/ops/bed-census
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/bed-census")
def bed_census(user=Depends(verify_jwt)):
    """Ward-level bed census: occupied, available, and maintenance counts."""
    conn = _get_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT
                    w.name AS ward_name,
                    w.ward_type,
                    COUNT(b.id) AS total_beds,
                    COUNT(b.id) FILTER (WHERE b.status = 'occupied') AS occupied,
                    COUNT(b.id) FILTER (WHERE b.status = 'available') AS available,
                    COUNT(b.id) FILTER (WHERE b.status = 'maintenance') AS maintenance
                FROM public.royan_wards w
                LEFT JOIN public.royan_beds b ON b.ward_id = w.id
                GROUP BY w.id, w.name, w.ward_type
                ORDER BY w.name
            """)
            rows = cur.fetchall()
    finally:
        _put_conn(conn)

    total_occupied = sum(int(r.get("occupied") or 0) for r in rows)
    total_beds = sum(int(r.get("total_beds") or 0) for r in rows)

    return {
        "generated_at": _now_utc(),
        "summary": {
            "total_beds": total_beds,
            "occupied": total_occupied,
            "available": total_beds - total_occupied,
            "occupancy_pct": round(total_occupied / max(total_beds, 1) * 100, 1),
        },
        "wards": [
            {
                "ward_name": r["ward_name"],
                "ward_type": r.get("ward_type"),
                "total_beds": int(r.get("total_beds") or 0),
                "occupied": int(r.get("occupied") or 0),
                "available": int(r.get("available") or 0),
                "maintenance": int(r.get("maintenance") or 0),
                "occupancy_pct": round(
                    int(r.get("occupied") or 0) / max(int(r.get("total_beds") or 1), 1) * 100, 1
                ),
            }
            for r in rows
        ],
    }


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/v1/ops/lab-performance
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/lab-performance")
def lab_performance(
    days: int = Query(7, ge=1, le=90),
    user=Depends(verify_jwt),
):
    """Lab turnaround time by test category and urgency level."""
    since = _days_ago(days)

    conn = _get_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT
                    COALESCE(lc.category, 'Uncategorised') AS category,
                    lo.urgency,
                    COUNT(lo.id) AS orders,
                    COUNT(lr.id) AS resulted,
                    ROUND(AVG(
                        EXTRACT(EPOCH FROM (lr.resulted_at - lo.ordered_at)) / 3600
                    )::numeric, 2) AS avg_tat_hours,
                    ROUND(PERCENTILE_CONT(0.9) WITHIN GROUP (
                        ORDER BY EXTRACT(EPOCH FROM (lr.resulted_at - lo.ordered_at)) / 3600
                    )::numeric, 2) AS p90_tat_hours,
                    COUNT(lr.id) FILTER (WHERE lr.is_critical = true) AS critical_count
                FROM public.royan_lab_orders lo
                LEFT JOIN public.royan_lab_catalog lc ON lc.code = lo.test_code
                LEFT JOIN public.royan_lab_results lr ON lr.lab_order_id = lo.id
                WHERE lo.ordered_at >= %s::date
                GROUP BY COALESCE(lc.category, 'Uncategorised'), lo.urgency
                ORDER BY orders DESC
                LIMIT 30
            """, (since,))
            rows = cur.fetchall()
    finally:
        _put_conn(conn)

    return {
        "period_days": days,
        "since": since,
        "generated_at": _now_utc(),
        "by_category_and_urgency": [
            {
                "category": r["category"],
                "urgency": r.get("urgency", "routine"),
                "orders": int(r["orders"]),
                "resulted": int(r.get("resulted") or 0),
                "result_rate_pct": round(
                    int(r.get("resulted") or 0) / max(int(r["orders"]), 1) * 100, 1
                ),
                "avg_tat_hours": float(r.get("avg_tat_hours") or 0),
                "p90_tat_hours": float(r.get("p90_tat_hours") or 0),
                "critical_count": int(r.get("critical_count") or 0),
            }
            for r in rows
        ],
    }


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/v1/ops/revenue-snapshot
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/revenue-snapshot")
def revenue_snapshot(
    days: int = Query(30, ge=1, le=365),
    user=Depends(verify_jwt),
):
    """Revenue breakdown by payer type for the specified period."""
    since = _days_ago(days)

    conn = _get_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:

            # Revenue by payment method. royan_billing tracks charges only
            # (subtotal/discount/hmo_covered) — actual money collected lives
            # in royan_payments, joined via billing_id, so "billed" and
            # "collected" are aggregated at separate grains (per-bill,
            # per-payment) via CTEs rather than a naive single-query JOIN,
            # which would double-count billed amounts for bills with more
            # than one payment.
            cur.execute("""
                WITH billed AS (
                    SELECT COALESCE(payment_method, 'Unknown') AS payer,
                           COUNT(*) AS bill_count,
                           SUM(subtotal - discount) AS billed,
                           SUM(hmo_covered) AS hmo_covered
                    FROM public.royan_billing
                    WHERE billed_at >= %s::date
                    GROUP BY payment_method
                ),
                collected AS (
                    SELECT COALESCE(b.payment_method, 'Unknown') AS payer,
                           SUM(p.amount) AS collected
                    FROM public.royan_payments p
                    JOIN public.royan_billing b ON b.id = p.billing_id
                    WHERE b.billed_at >= %s::date
                    GROUP BY b.payment_method
                )
                SELECT billed.payer, billed.bill_count, billed.billed, billed.hmo_covered,
                       COALESCE(collected.collected, 0) AS collected
                FROM billed
                LEFT JOIN collected ON collected.payer = billed.payer
                ORDER BY billed.billed DESC
            """, (since, since))
            payer_rows = cur.fetchall()

            # Daily revenue trend (last N days)
            cur.execute("""
                WITH billed AS (
                    SELECT DATE(billed_at) AS bill_date,
                           SUM(subtotal - discount) AS daily_billed
                    FROM public.royan_billing
                    WHERE billed_at >= %s::date
                    GROUP BY DATE(billed_at)
                ),
                collected AS (
                    SELECT DATE(b.billed_at) AS bill_date,
                           SUM(p.amount) AS daily_collected
                    FROM public.royan_payments p
                    JOIN public.royan_billing b ON b.id = p.billing_id
                    WHERE b.billed_at >= %s::date
                    GROUP BY DATE(b.billed_at)
                )
                SELECT billed.bill_date, billed.daily_billed,
                       COALESCE(collected.daily_collected, 0) AS daily_collected
                FROM billed
                LEFT JOIN collected ON collected.bill_date = billed.bill_date
                ORDER BY billed.bill_date
            """, (since, since))
            trend_rows = cur.fetchall()

    finally:
        _put_conn(conn)

    total_billed = sum(float(r.get("billed") or 0) for r in payer_rows)
    total_collected = sum(float(r.get("collected") or 0) for r in payer_rows)

    return {
        "period_days": days,
        "since": since,
        "generated_at": _now_utc(),
        "summary": {
            "total_billed": round(total_billed, 2),
            "total_collected": round(total_collected, 2),
            "collection_rate_pct": round(
                total_collected / max(total_billed, 1) * 100, 1
            ),
        },
        "by_payer": [
            {
                "payer": r["payer"],
                "bill_count": int(r["bill_count"]),
                "billed": float(r.get("billed") or 0),
                "collected": float(r.get("collected") or 0),
                "hmo_covered": float(r.get("hmo_covered") or 0),
            }
            for r in payer_rows
        ],
        "daily_trend": [
            {
                "date": str(r["bill_date"]),
                "billed": float(r.get("daily_billed") or 0),
                "collected": float(r.get("daily_collected") or 0),
            }
            for r in trend_rows
        ],
    }


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/v1/ops/workflow-health
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/workflow-health")
def workflow_health(
    stuck_threshold_hours: int = Query(4, ge=1, le=72,
        description="Hours with no transition before an encounter is considered stuck"),
    user=Depends(verify_jwt),
):
    """Workflow state machine health: stuck encounters and failed transitions."""
    conn = _get_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:

            # Stuck workflow instances (no transition for > threshold)
            try:
                cur.execute("""
                    SELECT
                        wi.id AS instance_id,
                        wi.entity_type,
                        wi.entity_id,
                        wi.current_state,
                        wi.definition_id,
                        wi.last_transitioned_at,
                        EXTRACT(EPOCH FROM (now() - wi.last_transitioned_at)) / 3600
                            AS hours_in_state
                    FROM workflow.instances wi
                    WHERE wi.is_terminal = false
                      AND (
                          wi.last_transitioned_at IS NULL OR
                          wi.last_transitioned_at < now() - (%s * INTERVAL '1 hour')
                      )
                    ORDER BY wi.last_transitioned_at ASC NULLS FIRST
                    LIMIT 50
                """, (stuck_threshold_hours,))
                stuck = [dict(r) for r in cur.fetchall()]
            except Exception:
                stuck = []

            # Recent failed transitions (workflow events that resulted in errors)
            # We surface encounters stuck in billing_pending > 24h as billing failures
            cur.execute("""
                SELECT
                    id AS encounter_id,
                    status,
                    department,
                    EXTRACT(EPOCH FROM (now() - created_at)) / 3600 AS age_hours
                FROM public.royan_encounters
                WHERE status = 'billing_pending'
                  AND created_at < now() - INTERVAL '24 hours'
                  AND discharge_at IS NULL
                ORDER BY created_at ASC
                LIMIT 20
            """)
            billing_stuck = [dict(r) for r in cur.fetchall()]

            # Count by state
            try:
                cur.execute("""
                    SELECT current_state, COUNT(*) AS cnt
                    FROM workflow.instances
                    WHERE is_terminal = false
                    GROUP BY current_state
                    ORDER BY cnt DESC
                """)
                state_dist = {r["current_state"]: int(r["cnt"]) for r in cur.fetchall()}
            except Exception:
                state_dist = {}

    finally:
        _put_conn(conn)

    for r in stuck:
        if r.get("last_transitioned_at"):
            r["last_transitioned_at"] = str(r["last_transitioned_at"])
        r["hours_in_state"] = round(float(r.get("hours_in_state") or 0), 1)

    return {
        "generated_at": _now_utc(),
        "stuck_threshold_hours": stuck_threshold_hours,
        "stuck_instances": stuck,
        "stuck_count": len(stuck),
        "billing_stuck_count": len(billing_stuck),
        "billing_pending_over_24h": billing_stuck,
        "active_state_distribution": state_dist,
    }


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/v1/ops/data-quality/latest
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/data-quality/latest")
def data_quality_latest(user=Depends(verify_jwt)):
    """Quality scores from the latest completed pipeline run.

    Reads from royan_import_rejections to surface rejection counts per
    domain and per run, grouped by the most recent batch.
    """
    conn = _get_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:

            # Most recent run_id per domain
            cur.execute("""
                SELECT
                    domain,
                    run_id,
                    COUNT(*) AS rejected_count,
                    MAX(rejected_at) AS last_rejection_at
                FROM public.royan_import_rejections
                GROUP BY domain, run_id
                ORDER BY MAX(rejected_at) DESC
                LIMIT 20
            """)
            rows = cur.fetchall()

            # Total patients / encounters / labs as denominator proxy
            cur.execute("""
                SELECT
                    (SELECT COUNT(*) FROM public.royan_patients)   AS patient_total,
                    (SELECT COUNT(*) FROM public.royan_encounters)  AS encounter_total,
                    (SELECT COUNT(*) FROM public.royan_lab_orders)  AS lab_total,
                    (SELECT COUNT(*) FROM public.royan_prescriptions) AS rx_total,
                    (SELECT COUNT(*) FROM public.royan_billing)    AS billing_total
            """)
            totals = cur.fetchone() or {}

    finally:
        _put_conn(conn)

    # Group by domain, take latest run
    by_domain: Dict[str, Any] = {}
    for r in rows:
        d = r["domain"]
        if d not in by_domain:
            by_domain[d] = {
                "domain": d,
                "run_id": r["run_id"],
                "rejected_count": int(r["rejected_count"]),
                "last_rejection_at": str(r["last_rejection_at"]) if r.get("last_rejection_at") else None,
            }

    return {
        "generated_at": _now_utc(),
        "silver_layer_totals": {
            "patients": int(totals.get("patient_total") or 0),
            "encounters": int(totals.get("encounter_total") or 0),
            "lab_orders": int(totals.get("lab_total") or 0),
            "prescriptions": int(totals.get("rx_total") or 0),
            "billing": int(totals.get("billing_total") or 0),
        },
        "latest_rejections_by_domain": list(by_domain.values()),
    }


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/v1/ops/knowledge-freshness
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/knowledge-freshness")
def knowledge_freshness(user=Depends(verify_jwt)):
    """Knowledge cache freshness: age of assembled PatientClinicalContext objects."""
    conn = _get_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            try:
                cur.execute("""
                    SELECT
                        COUNT(*) AS cached_patients,
                        COUNT(*) FILTER (WHERE is_stale = true) AS stale_count,
                        AVG(EXTRACT(EPOCH FROM (now() - assembled_at)) / 60)
                            AS avg_age_minutes,
                        MAX(assembled_at) AS most_recent,
                        MIN(assembled_at) AS oldest
                    FROM knowledge.patient_context_cache
                """)
                ctx = dict(cur.fetchone() or {})
            except Exception:
                ctx = {}

            try:
                cur.execute("""
                    SELECT
                        COUNT(*) AS cached_encounters,
                        AVG(EXTRACT(EPOCH FROM (now() - assembled_at)) / 60)
                            AS avg_age_minutes,
                        MAX(assembled_at) AS most_recent
                    FROM knowledge.encounter_context_cache
                """)
                enc_ctx = dict(cur.fetchone() or {})
            except Exception:
                enc_ctx = {}

    finally:
        _put_conn(conn)

    return {
        "generated_at": _now_utc(),
        "patient_context_cache": {
            "cached_count": int(ctx.get("cached_patients") or 0),
            "stale_count": int(ctx.get("stale_count") or 0),
            "avg_age_minutes": round(float(ctx.get("avg_age_minutes") or 0), 1),
            "most_recent_assembled": str(ctx.get("most_recent")) if ctx.get("most_recent") else None,
            "oldest_assembled": str(ctx.get("oldest")) if ctx.get("oldest") else None,
        },
        "encounter_context_cache": {
            "cached_count": int(enc_ctx.get("cached_encounters") or 0),
            "avg_age_minutes": round(float(enc_ctx.get("avg_age_minutes") or 0), 1),
            "most_recent_assembled": str(enc_ctx.get("most_recent")) if enc_ctx.get("most_recent") else None,
        },
    }
