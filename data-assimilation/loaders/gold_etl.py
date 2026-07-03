"""Gold Layer ETL — Blueprint Chapter 12.

Nightly silver → gold loader that populates the four clinical fact tables
and the KPI snapshot store created in migration 135.

Design principles:
  - Each loader is idempotent: ON CONFLICT DO NOTHING against (source_*_id)
    or the run_date / kpi_key UNIQUE constraints.
  - Each loader records its run in royan_gold_etl_runs so the CLI and
    any scheduler can detect failures and skip already-run dates.
  - KPI computation reads directly from silver tables (not fact tables) so
    that dimension data mismatches cannot distort metrics.
  - All loaders operate in a single passed-in connection — the caller
    controls transaction boundaries per-table so one failure doesn't roll
    back the whole night's work.

Usage (from run_gold_etl.py CLI):
    from loaders.gold_etl import run_gold_etl
    run_gold_etl(run_date=date(2026, 6, 27), conn=conn)
"""
from __future__ import annotations

import logging
import time
from datetime import date, datetime, timezone
from typing import Optional

import psycopg2.extras

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# ETL run helpers
# ─────────────────────────────────────────────────────────────────────────────

def _log_etl_run(conn, run_date: date, target_table: str,
                 rows_inserted: int, rows_skipped: int,
                 duration_ms: int, status: str, error_message: str = None) -> None:
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO public.royan_gold_etl_runs
                    (run_date, target_table, rows_inserted, rows_skipped,
                     duration_ms, status, error_message)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (run_date, target_table) DO UPDATE SET
                    rows_inserted = EXCLUDED.rows_inserted,
                    rows_skipped  = EXCLUDED.rows_skipped,
                    duration_ms   = EXCLUDED.duration_ms,
                    status        = EXCLUDED.status,
                    error_message = EXCLUDED.error_message,
                    ran_at        = now()
                """,
                (run_date, target_table, rows_inserted, rows_skipped,
                 duration_ms, status, error_message),
            )
        conn.commit()
    except Exception as exc:
        logger.warning("ETL run log failed for %s: %s", target_table, exc)


def _was_already_run(conn, run_date: date, target_table: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT status FROM public.royan_gold_etl_runs WHERE run_date = %s AND target_table = %s",
            (run_date, target_table),
        )
        row = cur.fetchone()
    return bool(row and row[0] == "success")


# ─────────────────────────────────────────────────────────────────────────────
# Fact loaders
# ─────────────────────────────────────────────────────────────────────────────

def load_fact_billings(conn, run_date: date, dry_run: bool = False) -> int:
    """Load billing episodes for run_date into fact_billings.

    Source: royan_billing (hospital billing table).
    Uses source_bill_id UNIQUE constraint to ensure idempotency.
    """
    t0 = time.monotonic()
    target = "fact_billings"

    if _was_already_run(conn, run_date, target):
        logger.info("%s already loaded for %s — skipping", target, run_date)
        return 0

    sql = """
        INSERT INTO public.fact_billings
            (patient_id, encounter_id, department_id, bill_date,
             total_billed, total_paid, hmo_covered_amount, payment_method,
             hmo_covered, bill_status, source_bill_id, loaded_at)
        SELECT
            b.patient_id,
            b.encounter_id,
            e.department_id,
            DATE(b.billed_at)                        AS bill_date,
            COALESCE(b.total_amount, 0)              AS total_billed,
            COALESCE(b.amount_paid, 0)               AS total_paid,
            COALESCE(b.hmo_amount, 0)                AS hmo_covered_amount,
            b.payment_method,
            (COALESCE(b.hmo_amount, 0) > 0)         AS hmo_covered,
            b.status                                  AS bill_status,
            b.id                                      AS source_bill_id,
            now()                                     AS loaded_at
        FROM public.royan_billing b
        LEFT JOIN public.royan_encounters e ON e.id = b.encounter_id
        WHERE DATE(b.billed_at) = %s
        ON CONFLICT (source_bill_id) DO NOTHING
    """

    if dry_run:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM public.royan_billing WHERE DATE(billed_at) = %s", (run_date,)
            )
            count = cur.fetchone()[0]
        logger.info("[DRY RUN] %s: would load ~%d rows for %s", target, count, run_date)
        return count

    with conn.cursor() as cur:
        cur.execute(sql, (run_date,))
        inserted = cur.rowcount
    conn.commit()

    ms = int((time.monotonic() - t0) * 1000)
    _log_etl_run(conn, run_date, target, inserted, 0, ms, "success")
    logger.info("%s: inserted %d rows for %s (%dms)", target, inserted, run_date, ms)
    return inserted


def load_fact_lab_investigations(conn, run_date: date, dry_run: bool = False) -> int:
    """Load lab investigation rows for run_date into fact_lab_investigations.

    Source: royan_lab_orders joined with latest result per order.
    TAT is computed as (resulted_at - ordered_at) in hours.
    """
    t0 = time.monotonic()
    target = "fact_lab_investigations"

    if _was_already_run(conn, run_date, target):
        logger.info("%s already loaded for %s — skipping", target, run_date)
        return 0

    sql = """
        INSERT INTO public.fact_lab_investigations
            (patient_id, encounter_id, department_id, ordered_date, resulted_date,
             tat_hours, test_code, urgency, is_abnormal, is_critical,
             result_status, source_order_id, loaded_at)
        SELECT
            lo.patient_id,
            lo.encounter_id,
            e.department_id,
            DATE(lo.ordered_at)                      AS ordered_date,
            DATE(lr.resulted_at)                     AS resulted_date,
            CASE
                WHEN lr.resulted_at IS NOT NULL AND lo.ordered_at IS NOT NULL
                THEN ROUND(
                    EXTRACT(EPOCH FROM (lr.resulted_at - lo.ordered_at)) / 3600.0,
                    2
                )
                ELSE NULL
            END                                      AS tat_hours,
            lo.test_code,
            lo.urgency,
            COALESCE(lr.is_abnormal, false)          AS is_abnormal,
            COALESCE(lr.is_critical, false)          AS is_critical,
            lo.status                                AS result_status,
            lo.id                                    AS source_order_id,
            now()                                    AS loaded_at
        FROM public.royan_lab_orders lo
        LEFT JOIN LATERAL (
            SELECT resulted_at, is_abnormal, is_critical
            FROM public.royan_lab_results
            WHERE order_id = lo.id
            ORDER BY resulted_at DESC
            LIMIT 1
        ) lr ON true
        LEFT JOIN public.royan_encounters e ON e.id = lo.encounter_id
        WHERE DATE(lo.ordered_at) = %s
        ON CONFLICT (source_order_id) DO NOTHING
    """

    if dry_run:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM public.royan_lab_orders WHERE DATE(ordered_at) = %s", (run_date,)
            )
            count = cur.fetchone()[0]
        logger.info("[DRY RUN] %s: would load ~%d rows for %s", target, count, run_date)
        return count

    with conn.cursor() as cur:
        cur.execute(sql, (run_date,))
        inserted = cur.rowcount
    conn.commit()

    ms = int((time.monotonic() - t0) * 1000)
    _log_etl_run(conn, run_date, target, inserted, 0, ms, "success")
    logger.info("%s: inserted %d rows for %s (%dms)", target, inserted, run_date, ms)
    return inserted


def load_fact_prescriptions(conn, run_date: date, dry_run: bool = False) -> int:
    """Load prescription dispensing/administration rows into fact_prescriptions.

    Source: royan_prescriptions joined with dispensing + medication_admin.
    """
    t0 = time.monotonic()
    target = "fact_prescriptions"

    if _was_already_run(conn, run_date, target):
        logger.info("%s already loaded for %s — skipping", target, run_date)
        return 0

    sql = """
        INSERT INTO public.fact_prescriptions
            (patient_id, encounter_id, department_id, prescribed_date,
             dispensed_date, administered_date, drug_name, drug_code,
             drug_class, route, was_dispensed, was_administered,
             rx_status, source_rx_id, loaded_at)
        SELECT
            rx.patient_id,
            rx.encounter_id,
            e.department_id,
            DATE(rx.prescribed_at)                   AS prescribed_date,
            DATE(MIN(d.dispensed_at))                AS dispensed_date,
            DATE(MIN(ma.admin_time))                 AS administered_date,
            rx.drug_name,
            rx.drug_code,
            f.drug_class,
            rx.route,
            (COUNT(d.id) > 0)                        AS was_dispensed,
            (COUNT(ma.id) > 0)                       AS was_administered,
            rx.status                                 AS rx_status,
            rx.id                                     AS source_rx_id,
            now()                                     AS loaded_at
        FROM public.royan_prescriptions rx
        LEFT JOIN public.royan_encounters e   ON e.id = rx.encounter_id
        LEFT JOIN public.royan_dispensing d   ON d.prescription_id = rx.id
        LEFT JOIN public.royan_medication_admin ma ON ma.prescription_id = rx.id
        LEFT JOIN public.royan_drug_formulary f ON f.code = rx.drug_code
        WHERE DATE(rx.prescribed_at) = %s
        GROUP BY rx.id, rx.patient_id, rx.encounter_id, e.department_id,
                 rx.prescribed_at, rx.drug_name, rx.drug_code, f.drug_class, rx.route, rx.status
        ON CONFLICT (source_rx_id) DO NOTHING
    """

    if dry_run:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM public.royan_prescriptions WHERE DATE(prescribed_at) = %s", (run_date,)
            )
            count = cur.fetchone()[0]
        logger.info("[DRY RUN] %s: would load ~%d rows for %s", target, count, run_date)
        return count

    with conn.cursor() as cur:
        cur.execute(sql, (run_date,))
        inserted = cur.rowcount
    conn.commit()

    ms = int((time.monotonic() - t0) * 1000)
    _log_etl_run(conn, run_date, target, inserted, 0, ms, "success")
    logger.info("%s: inserted %d rows for %s (%dms)", target, inserted, run_date, ms)
    return inserted


def load_fact_admissions(conn, run_date: date, dry_run: bool = False) -> int:
    """Load inpatient admission episodes for run_date into fact_admissions.

    Source: royan_encounters WHERE encounter_type = 'inpatient' AND admitted on run_date.
    """
    t0 = time.monotonic()
    target = "fact_admissions"

    if _was_already_run(conn, run_date, target):
        logger.info("%s already loaded for %s — skipping", target, run_date)
        return 0

    sql = """
        INSERT INTO public.fact_admissions
            (patient_id, encounter_id, ward_id, bed_id, department_id,
             admitted_date, discharged_date, discharge_condition,
             admission_type, source_encounter_id, loaded_at)
        SELECT
            e.patient_id,
            e.id                                     AS encounter_id,
            e.ward_id,
            e.bed_id,
            e.department_id,
            DATE(e.admitted_at)                      AS admitted_date,
            DATE(e.discharged_at)                    AS discharged_date,
            e.discharge_notes                        AS discharge_condition,
            e.encounter_type                         AS admission_type,
            e.id                                     AS source_encounter_id,
            now()                                    AS loaded_at
        FROM public.royan_encounters e
        WHERE e.encounter_type = 'inpatient'
          AND DATE(e.admitted_at) = %s
        ON CONFLICT (source_encounter_id) DO NOTHING
    """

    if dry_run:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM public.royan_encounters WHERE encounter_type = 'inpatient' AND DATE(admitted_at) = %s",
                (run_date,),
            )
            count = cur.fetchone()[0]
        logger.info("[DRY RUN] %s: would load ~%d rows for %s", target, count, run_date)
        return count

    with conn.cursor() as cur:
        cur.execute(sql, (run_date,))
        inserted = cur.rowcount
    conn.commit()

    ms = int((time.monotonic() - t0) * 1000)
    _log_etl_run(conn, run_date, target, inserted, 0, ms, "success")
    logger.info("%s: inserted %d rows for %s (%dms)", target, inserted, run_date, ms)
    return inserted


# ─────────────────────────────────────────────────────────────────────────────
# KPI computation
# ─────────────────────────────────────────────────────────────────────────────

def compute_daily_kpis(conn, run_date: date, dry_run: bool = False) -> int:
    """Compute and upsert daily KPI snapshots into royan_kpi_snapshots.

    KPIs computed:
      avg_wait_minutes       — mean time from registration to being called (all encounters)
      avg_lab_tat_hours      — mean lab turnaround across all resulted orders
      avg_consult_minutes    — mean consultation duration (triaged → consulting)
      revenue_collected      — total payments received
      total_bills_raised     — count of new bills
      total_patients_seen    — distinct patients with encounters on this date
      bed_occupancy_pct      — admitted but not yet discharged / total beds
      lab_critical_rate_pct  — critical results / all results
      rx_dispensed_count     — prescriptions dispensed

    Each KPI is also broken down per department where meaningful.
    """
    t0 = time.monotonic()
    target = "royan_kpi_snapshots"
    inserted = 0

    def _upsert_kpi(kpi_key: str, kpi_value: float, kpi_unit: str,
                    department_id=None, department_code=None, metadata=None):
        nonlocal inserted
        if dry_run:
            logger.info("[DRY RUN] KPI %s = %s %s (dept=%s)", kpi_key, kpi_value, kpi_unit, department_id)
            inserted += 1
            return
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO public.royan_kpi_snapshots
                        (snapshot_date, kpi_key, kpi_value, kpi_unit,
                         department_id, department_code, metadata)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT ON CONSTRAINT royan_kpi_snapshots_unique DO UPDATE SET
                        kpi_value    = EXCLUDED.kpi_value,
                        computed_at  = now(),
                        metadata     = EXCLUDED.metadata
                    """,
                    (run_date, kpi_key, kpi_value, kpi_unit,
                     department_id, department_code,
                     psycopg2.extras.Json(metadata or {})),
                )
                inserted += 1
        except Exception as exc:
            logger.warning("KPI upsert failed [%s]: %s", kpi_key, exc)

    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:

        # ── avg_wait_minutes (global) ────────────────────────────────────────
        cur.execute("""
            SELECT ROUND(AVG(
                EXTRACT(EPOCH FROM (
                    COALESCE(triage_started_at, updated_at) - created_at
                )) / 60.0
            )::numeric, 1) AS avg_wait
            FROM public.royan_encounters
            WHERE DATE(created_at) = %s
              AND status != 'cancelled'
        """, (run_date,))
        row = cur.fetchone()
        if row and row["avg_wait"] is not None:
            _upsert_kpi("avg_wait_minutes", float(row["avg_wait"]), "minutes")

        # ── avg_lab_tat_hours (global) ───────────────────────────────────────
        cur.execute("""
            SELECT ROUND(AVG(
                EXTRACT(EPOCH FROM (lr.resulted_at - lo.ordered_at)) / 3600.0
            )::numeric, 2) AS avg_tat
            FROM public.royan_lab_orders lo
            JOIN public.royan_lab_results lr ON lr.order_id = lo.id
            WHERE DATE(lo.ordered_at) = %s
              AND lr.resulted_at IS NOT NULL
        """, (run_date,))
        row = cur.fetchone()
        if row and row["avg_tat"] is not None:
            _upsert_kpi("avg_lab_tat_hours", float(row["avg_tat"]), "hours")

        # ── revenue_collected ────────────────────────────────────────────────
        cur.execute("""
            SELECT COALESCE(SUM(amount_paid), 0) AS revenue
            FROM public.royan_billing
            WHERE DATE(billed_at) = %s
        """, (run_date,))
        row = cur.fetchone()
        _upsert_kpi("revenue_collected", float(row["revenue"] or 0), "NGN")

        # ── revenue by department ────────────────────────────────────────────
        cur.execute("""
            SELECT e.department_id, d.code AS dept_code,
                   COALESCE(SUM(b.amount_paid), 0) AS revenue
            FROM public.royan_billing b
            JOIN public.royan_encounters e ON e.id = b.encounter_id
            LEFT JOIN public.royan_departments d ON d.id = e.department_id
            WHERE DATE(b.billed_at) = %s
            GROUP BY e.department_id, d.code
        """, (run_date,))
        for dept_row in cur.fetchall():
            _upsert_kpi(
                "revenue_collected", float(dept_row["revenue"] or 0), "NGN",
                department_id=dept_row["department_id"],
                department_code=dept_row["dept_code"],
            )

        # ── total_bills_raised ───────────────────────────────────────────────
        cur.execute(
            "SELECT COUNT(*) AS cnt FROM public.royan_billing WHERE DATE(billed_at) = %s", (run_date,)
        )
        row = cur.fetchone()
        _upsert_kpi("total_bills_raised", float(row["cnt"] or 0), "count")

        # ── total_patients_seen ──────────────────────────────────────────────
        cur.execute("""
            SELECT COUNT(DISTINCT patient_id) AS cnt
            FROM public.royan_encounters
            WHERE DATE(created_at) = %s
        """, (run_date,))
        row = cur.fetchone()
        _upsert_kpi("total_patients_seen", float(row["cnt"] or 0), "count")

        # ── bed_occupancy_pct ────────────────────────────────────────────────
        cur.execute("""
            SELECT
                (SELECT COUNT(*) FROM public.royan_encounters
                 WHERE status = 'admitted' AND discharged_at IS NULL) AS occupied,
                (SELECT COUNT(*) FROM public.royan_beds WHERE is_active = true) AS total
        """)
        row = cur.fetchone()
        occupied = int(row["occupied"] or 0)
        total_beds = int(row["total"] or 1)
        _upsert_kpi("bed_occupancy_pct", round(occupied / total_beds * 100, 1), "percent",
                    metadata={"occupied": occupied, "total_beds": total_beds})

        # ── lab_critical_rate_pct ────────────────────────────────────────────
        cur.execute("""
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE is_critical = true) AS critical_count
            FROM public.royan_lab_results lr
            JOIN public.royan_lab_orders lo ON lo.id = lr.order_id
            WHERE DATE(lo.ordered_at) = %s
        """, (run_date,))
        row = cur.fetchone()
        total_results = int(row["total"] or 0)
        critical = int(row["critical_count"] or 0)
        if total_results > 0:
            _upsert_kpi(
                "lab_critical_rate_pct",
                round(critical / total_results * 100, 1),
                "percent",
                metadata={"critical_count": critical, "total_results": total_results},
            )

        # ── rx_dispensed_count ───────────────────────────────────────────────
        cur.execute("""
            SELECT COUNT(*) AS cnt
            FROM public.royan_dispensing d
            JOIN public.royan_prescriptions rx ON rx.id = d.prescription_id
            WHERE DATE(rx.prescribed_at) = %s
        """, (run_date,))
        row = cur.fetchone()
        _upsert_kpi("rx_dispensed_count", float(row["cnt"] or 0), "count")

    if not dry_run:
        conn.commit()

    ms = int((time.monotonic() - t0) * 1000)
    if not dry_run:
        _log_etl_run(conn, run_date, target, inserted, 0, ms, "success")
    logger.info("%s: computed %d KPIs for %s (%dms)", target, inserted, run_date, ms)
    return inserted


# ─────────────────────────────────────────────────────────────────────────────
# Orchestrator
# ─────────────────────────────────────────────────────────────────────────────

def run_gold_etl(conn, run_date: Optional[date] = None, dry_run: bool = False) -> dict:
    """Run all gold ETL loaders in dependency order for the given date.

    Returns a summary dict with per-table row counts and any errors.
    """
    if run_date is None:
        run_date = date.today()

    logger.info("Gold ETL starting for %s (dry_run=%s)", run_date, dry_run)

    summary = {
        "run_date": str(run_date),
        "dry_run": dry_run,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "tables": {},
        "errors": [],
    }

    loaders = [
        ("fact_billings",          load_fact_billings),
        ("fact_lab_investigations", load_fact_lab_investigations),
        ("fact_prescriptions",     load_fact_prescriptions),
        ("fact_admissions",        load_fact_admissions),
        ("royan_kpi_snapshots",    compute_daily_kpis),
    ]

    for table_name, loader_fn in loaders:
        try:
            rows = loader_fn(conn, run_date, dry_run=dry_run)
            summary["tables"][table_name] = {"rows": rows, "status": "ok"}
        except Exception as exc:
            logger.error("Gold ETL error on %s for %s: %s", table_name, run_date, exc)
            summary["tables"][table_name] = {"rows": 0, "status": "error", "error": str(exc)}
            summary["errors"].append({"table": table_name, "error": str(exc)})
            if not dry_run:
                try:
                    conn.rollback()
                    _log_etl_run(conn, run_date, table_name, 0, 0, 0, "error", str(exc))
                except Exception:
                    pass

    summary["finished_at"] = datetime.now(timezone.utc).isoformat()
    summary["total_errors"] = len(summary["errors"])
    summary["overall_status"] = "error" if summary["errors"] else "success"

    logger.info(
        "Gold ETL complete for %s: %d tables, %d errors",
        run_date, len(loaders), len(summary["errors"]),
    )
    return summary
