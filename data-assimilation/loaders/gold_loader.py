"""Gold layer loader: populates dim/fact tables and refreshes materialized views.

Called by pipeline.py after all Silver entity loads complete.
Functions are idempotent — safe to call on every run.
"""
from __future__ import annotations

import logging
from datetime import datetime, date
from typing import Optional

import psycopg2
import psycopg2.extras

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Dimension refreshes (upsert from Silver tables)
# ---------------------------------------------------------------------------

def refresh_dim_patient(conn) -> int:
    """Upsert dim_patient from royan_patients. Returns rows upserted."""
    upserted = 0
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO public.dim_patient (
                patient_id, mrn, full_name, gender, age_band, hmo_provider, is_active, valid_from
            )
            SELECT
                p.id,
                p.mrn,
                TRIM(COALESCE(p.first_name, '') || ' ' || COALESCE(p.last_name, '')) AS full_name,
                p.gender,
                CASE
                    WHEN p.date_of_birth IS NULL THEN NULL
                    WHEN DATE_PART('year', AGE(p.date_of_birth::date)) <= 5   THEN '0-5'
                    WHEN DATE_PART('year', AGE(p.date_of_birth::date)) <= 17  THEN '6-17'
                    WHEN DATE_PART('year', AGE(p.date_of_birth::date)) <= 40  THEN '18-40'
                    WHEN DATE_PART('year', AGE(p.date_of_birth::date)) <= 60  THEN '41-60'
                    ELSE '60+'
                END AS age_band,
                p.hmo_provider,
                p.is_active,
                now()
            FROM public.royan_patients p
            ON CONFLICT (patient_id) DO UPDATE SET
                mrn          = EXCLUDED.mrn,
                full_name    = EXCLUDED.full_name,
                gender       = EXCLUDED.gender,
                age_band     = EXCLUDED.age_band,
                hmo_provider = EXCLUDED.hmo_provider,
                is_active    = EXCLUDED.is_active
        """)
        upserted = cur.rowcount
    conn.commit()
    logger.info("dim_patient refreshed: %d rows", upserted)
    return upserted


def refresh_dim_service(conn) -> int:
    """Upsert dim_service from royan_service_catalog."""
    upserted = 0
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO public.dim_service (
                service_id, service_code, service_name, category, base_price
            )
            SELECT id, service_code, name, category, base_price
            FROM public.royan_service_catalog
            ON CONFLICT (service_code) DO UPDATE SET
                service_name = EXCLUDED.service_name,
                category     = EXCLUDED.category,
                base_price   = EXCLUDED.base_price
        """)
        upserted = cur.rowcount
    conn.commit()
    logger.info("dim_service refreshed: %d rows", upserted)
    return upserted


def refresh_dim_staff(conn) -> int:
    """Upsert dim_staff from royan_staff."""
    upserted = 0
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO public.dim_staff (
                staff_id, staff_number, full_name, department, designation, employment_type
            )
            SELECT id, staff_number, full_name, department, designation, employment_type
            FROM public.royan_staff
            ON CONFLICT (staff_number) DO UPDATE SET
                full_name       = EXCLUDED.full_name,
                department      = EXCLUDED.department,
                designation     = EXCLUDED.designation,
                employment_type = EXCLUDED.employment_type
        """)
        upserted = cur.rowcount
    conn.commit()
    logger.info("dim_staff refreshed: %d rows", upserted)
    return upserted


# ---------------------------------------------------------------------------
# Fact table population
# ---------------------------------------------------------------------------

def populate_fact_queue_visits(
    conn,
    run_id: str,
    since: Optional[str] = None,
) -> int:
    """Insert new encounter rows into fact_queue_visits.

    In incremental mode, *since* is the ISO timestamp of the last watermark —
    only encounters created after that point are processed.
    """
    since_filter = "AND e.created_at > %s::timestamptz" if since else ""
    params = (run_id, run_id)
    if since:
        params = (since, run_id, run_id)

    inserted = 0
    with conn.cursor() as cur:
        sql = f"""
            INSERT INTO public.fact_queue_visits (
                visit_date, patient_sk, encounter_id, encounter_type,
                department, status, triage_level,
                wait_minutes, consult_minutes, total_visit_minutes,
                consulting_doctor, run_id
            )
            SELECT
                e.created_at::date,
                dp.patient_sk,
                e.id,
                e.encounter_type,
                e.department,
                e.status,
                e.triage_level,
                ROUND(EXTRACT(EPOCH FROM (e.triage_at - e.created_at)) / 60.0, 2),
                ROUND(EXTRACT(EPOCH FROM (e.consultation_at - e.triage_at)) / 60.0, 2),
                ROUND(EXTRACT(EPOCH FROM (e.discharge_at - e.created_at)) / 60.0, 2),
                e.consulting_doctor,
                %s
            FROM public.royan_encounters e
            LEFT JOIN public.dim_patient dp ON dp.patient_id = e.patient_id
            WHERE e.created_at IS NOT NULL
              {since_filter}
            ON CONFLICT DO NOTHING
        """
        cur.execute(sql, params if since else (run_id,))
        inserted = cur.rowcount
    conn.commit()
    logger.info("fact_queue_visits populated: %d rows (since=%s)", inserted, since)
    return inserted


def populate_fact_billing_summary(
    conn,
    run_id: str,
    since: Optional[str] = None,
) -> int:
    """Insert new billing rows into fact_billing_summary."""
    since_filter = "AND b.billed_at > %s::timestamptz" if since else ""

    inserted = 0
    with conn.cursor() as cur:
        sql = f"""
            INSERT INTO public.fact_billing_summary (
                billing_date, patient_sk, billing_id, encounter_id,
                consultation_fee, lab_charges, pharmacy_charges,
                ward_charges, procedure_charges, miscellaneous,
                total_charged, hmo_covered, patient_balance,
                payment_method, status, run_id
            )
            SELECT
                COALESCE(b.billed_at::date, now()::date),
                dp.patient_sk,
                b.id,
                b.encounter_id,
                COALESCE(b.consultation_fee, 0),
                COALESCE(b.lab_charges, 0),
                COALESCE(b.pharmacy_charges, 0),
                COALESCE(b.ward_charges, 0),
                COALESCE(b.procedure_charges, 0),
                COALESCE(b.miscellaneous, 0),
                COALESCE(b.subtotal, 0),
                COALESCE(b.hmo_covered, 0),
                COALESCE(b.patient_balance, 0),
                b.payment_method,
                b.status,
                %s
            FROM public.royan_billing b
            LEFT JOIN public.dim_patient dp ON dp.patient_id = b.patient_id
            WHERE b.patient_id IS NOT NULL
              {since_filter}
            ON CONFLICT DO NOTHING
        """
        params = (run_id,) if not since else (since, run_id)
        # since_filter places %s before run_id in the WHERE, but run_id is in SELECT
        # so correct param order depends on position
        if since:
            cur.execute(sql, (run_id, since))
        else:
            cur.execute(sql, (run_id,))
        inserted = cur.rowcount
    conn.commit()
    logger.info("fact_billing_summary populated: %d rows (since=%s)", inserted, since)
    return inserted


# ---------------------------------------------------------------------------
# Materialized view refresh
# ---------------------------------------------------------------------------

def refresh_materialized_views(conn) -> None:
    """Refresh all Gold materialized views concurrently."""
    views = [
        "public.mv_daily_queue_stats",
        "public.mv_service_utilization",
    ]
    with conn.cursor() as cur:
        for view in views:
            try:
                cur.execute(f"REFRESH MATERIALIZED VIEW CONCURRENTLY {view}")
                logger.info("Refreshed materialized view: %s", view)
            except Exception as exc:
                logger.warning("Could not refresh %s: %s", view, exc)
                conn.rollback()
                continue
    conn.commit()


# ---------------------------------------------------------------------------
# Full Gold refresh (called by pipeline.py after all Silver loads)
# ---------------------------------------------------------------------------

def run_gold_refresh(conn, run_id: str, since: Optional[str] = None) -> dict:
    """Run the full Gold layer refresh pipeline. Returns a summary dict."""
    summary = {}
    try:
        summary["dim_patient"] = refresh_dim_patient(conn)
        summary["dim_service"] = refresh_dim_service(conn)
        summary["dim_staff"] = refresh_dim_staff(conn)
        summary["fact_queue_visits"] = populate_fact_queue_visits(conn, run_id, since)
        summary["fact_billing_summary"] = populate_fact_billing_summary(conn, run_id, since)
        refresh_materialized_views(conn)
        summary["materialized_views"] = "refreshed"
    except Exception as exc:
        logger.error("Gold refresh failed: %s", exc, exc_info=True)
        summary["error"] = str(exc)
    return summary
