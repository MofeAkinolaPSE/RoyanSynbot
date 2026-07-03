"""Enrichment loader — Blueprint Phase 7 (DrM FK backfill).

Populates the nullable FK columns added in migration 131 and creates
royan_discharge_records (migration 132) from already-imported encounter data.

All operations are:
  - Additive only: never overwrites existing FK values that are already set
  - Idempotent: safe to re-run multiple times
  - Batched: processes rows in configurable chunks (default 5,000) to cap
    transaction size and RAM usage

Passes available:
  enrich_encounter_depts   — royan_encounters.department_id via dept name/code
  enrich_encounter_doctors — royan_encounters.doctor_id via consulting_doctor text
  enrich_lab_catalog       — royan_lab_orders.catalog_id via test_code
  enrich_lab_ordered_by    — royan_lab_orders.ordered_by_id via ordered_by text
  enrich_rx_prescribed_by  — royan_prescriptions.prescribed_by_id via prescribed_by text
  enrich_billing_hmo       — royan_billing.hmo_id via patient's hmo_provider text
  enrich_discharge_records — INSERT royan_discharge_records from discharged encounters
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional, Tuple

import psycopg2
import psycopg2.extras

from transformers.enrichment import (
    build_dept_lookup,
    build_formulary_lookup,
    build_hmo_lookup,
    build_lab_catalog_lookup,
    build_staff_lookup,
    resolve_dept_id,
    resolve_hmo_id,
    resolve_staff_id,
)
from transformers._helpers import EXTERNAL_SOURCE, utcnow

logger = logging.getLogger(__name__)

_BATCH = 5_000


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _fetch(cur, sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
    cur.execute(sql, params)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def _load_master_table(conn, table: str, cols: str) -> List[Dict]:
    with conn.cursor() as cur:
        cur.execute(f"SELECT {cols} FROM public.{table}")
        col_names = [d[0] for d in cur.description]
        return [dict(zip(col_names, row)) for row in cur.fetchall()]


def _batch_update(
    conn,
    table: str,
    pk_col: str,
    set_col: str,
    ids_and_values: List[Tuple[int, int]],
    dry_run: bool = False,
    label: str = "",
) -> int:
    """Batch-update table.set_col = value WHERE pk_col = pk_id.
    Only writes if the column is currently NULL (additive-only).
    Returns number of rows updated.
    """
    if not ids_and_values:
        return 0

    if dry_run:
        logger.info("[DRY RUN] %s: would update %d rows in %s.%s", label, len(ids_and_values), table, set_col)
        return len(ids_and_values)

    updated = 0
    for i in range(0, len(ids_and_values), _BATCH):
        chunk = ids_and_values[i:i + _BATCH]
        with conn.cursor() as cur:
            # Build VALUES list for a single-statement batch update
            args = []
            value_rows = []
            for (pk_id, val) in chunk:
                value_rows.append("(%s, %s)")
                args.extend([pk_id, val])
            values_sql = ", ".join(value_rows)
            cur.execute(
                f"""
                UPDATE public.{table} t
                SET {set_col} = v.new_val::bigint
                FROM (VALUES {values_sql}) AS v(pk_id, new_val)
                WHERE t.{pk_col} = v.pk_id::bigint
                  AND t.{set_col} IS NULL
                """,
                args,
            )
            updated += cur.rowcount
        conn.commit()
        logger.debug("[%s] committed batch %d–%d (%d updated)", label, i, i + len(chunk), cur.rowcount)

    logger.info("[%s] %s.%s: %d rows updated.", label, table, set_col, updated)
    return updated


# ─────────────────────────────────────────────────────────────────────────────
# Pass 1 — encounter department_id
# ─────────────────────────────────────────────────────────────────────────────

def enrich_encounter_depts(conn, dry_run: bool = False) -> Dict[str, int]:
    """Set royan_encounters.department_id WHERE department_id IS NULL."""
    dept_rows = _load_master_table(conn, "royan_departments", "id, code, name")
    lookup = build_dept_lookup(dept_rows)

    matched: List[Tuple[int, int]] = []
    unmatched = 0

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, department
            FROM public.royan_encounters
            WHERE department IS NOT NULL
              AND department_id IS NULL
            """
        )
        for row in cur.fetchall():
            enc_id, dept_text = row
            dept_id = resolve_dept_id(dept_text, lookup)
            if dept_id:
                matched.append((enc_id, dept_id))
            else:
                unmatched += 1

    updated = _batch_update(conn, "royan_encounters", "id", "department_id", matched, dry_run, "enc:dept")

    result = {"matched": len(matched), "updated": updated, "unmatched": unmatched}
    logger.info("enrich_encounter_depts: %s", result)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Pass 2 — encounter doctor_id
# ─────────────────────────────────────────────────────────────────────────────

def enrich_encounter_doctors(conn, dry_run: bool = False) -> Dict[str, int]:
    """Set royan_encounters.doctor_id WHERE doctor_id IS NULL."""
    staff_rows = _load_master_table(conn, "royan_staff", "id, first_name, last_name, staff_code")
    lookup = build_staff_lookup(staff_rows)

    matched: List[Tuple[int, int]] = []
    unmatched = 0
    bare_ints = 0

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, consulting_doctor
            FROM public.royan_encounters
            WHERE consulting_doctor IS NOT NULL
              AND consulting_doctor != ''
              AND doctor_id IS NULL
            """
        )
        for row in cur.fetchall():
            enc_id, doc_text = row
            if str(doc_text).strip().isdigit():
                bare_ints += 1
                continue
            doc_id = resolve_staff_id(doc_text, lookup)
            if doc_id:
                matched.append((enc_id, doc_id))
            else:
                unmatched += 1

    updated = _batch_update(conn, "royan_encounters", "id", "doctor_id", matched, dry_run, "enc:doctor")

    result = {
        "matched": len(matched), "updated": updated,
        "unmatched": unmatched, "bare_integers_skipped": bare_ints,
    }
    logger.info("enrich_encounter_doctors: %s", result)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Pass 3 — lab order catalog_id
# ─────────────────────────────────────────────────────────────────────────────

def enrich_lab_catalog(conn, dry_run: bool = False) -> Dict[str, int]:
    """Set royan_lab_orders.catalog_id via test_code → royan_lab_catalog.code."""
    cat_rows = _load_master_table(conn, "royan_lab_catalog", "id, code")
    lookup = build_lab_catalog_lookup(cat_rows)

    matched: List[Tuple[int, int]] = []
    unmatched = 0

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, test_code
            FROM public.royan_lab_orders
            WHERE test_code IS NOT NULL
              AND test_code != ''
              AND catalog_id IS NULL
            """
        )
        for row in cur.fetchall():
            order_id, code = row
            cat_id = lookup.get(str(code).strip().lower())
            if cat_id:
                matched.append((order_id, cat_id))
            else:
                unmatched += 1

    updated = _batch_update(conn, "royan_lab_orders", "id", "catalog_id", matched, dry_run, "lab:catalog")

    result = {"matched": len(matched), "updated": updated, "unmatched": unmatched}
    logger.info("enrich_lab_catalog: %s", result)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Pass 4 — lab ordered_by_id
# ─────────────────────────────────────────────────────────────────────────────

def enrich_lab_ordered_by(conn, dry_run: bool = False) -> Dict[str, int]:
    """Set royan_lab_orders.ordered_by_id via ordered_by text → royan_staff."""
    staff_rows = _load_master_table(conn, "royan_staff", "id, first_name, last_name, staff_code")
    lookup = build_staff_lookup(staff_rows)

    matched: List[Tuple[int, int]] = []
    unmatched = 0

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, ordered_by
            FROM public.royan_lab_orders
            WHERE ordered_by IS NOT NULL
              AND ordered_by != ''
              AND ordered_by_id IS NULL
            """
        )
        for row in cur.fetchall():
            order_id, name = row
            sid = resolve_staff_id(name, lookup)
            if sid:
                matched.append((order_id, sid))
            else:
                unmatched += 1

    updated = _batch_update(conn, "royan_lab_orders", "id", "ordered_by_id", matched, dry_run, "lab:ordered_by")

    result = {"matched": len(matched), "updated": updated, "unmatched": unmatched}
    logger.info("enrich_lab_ordered_by: %s", result)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Pass 5 — prescription prescribed_by_id
# ─────────────────────────────────────────────────────────────────────────────

def enrich_rx_prescribed_by(conn, dry_run: bool = False) -> Dict[str, int]:
    """Set royan_prescriptions.prescribed_by_id via prescribed_by text → royan_staff."""
    staff_rows = _load_master_table(conn, "royan_staff", "id, first_name, last_name, staff_code")
    lookup = build_staff_lookup(staff_rows)

    matched: List[Tuple[int, int]] = []
    unmatched = 0

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, prescribed_by
            FROM public.royan_prescriptions
            WHERE prescribed_by IS NOT NULL
              AND prescribed_by != ''
              AND prescribed_by_id IS NULL
            """
        )
        for row in cur.fetchall():
            rx_id, name = row
            sid = resolve_staff_id(name, lookup)
            if sid:
                matched.append((rx_id, sid))
            else:
                unmatched += 1

    updated = _batch_update(conn, "royan_prescriptions", "id", "prescribed_by_id", matched, dry_run, "rx:prescribed_by")

    result = {"matched": len(matched), "updated": updated, "unmatched": unmatched}
    logger.info("enrich_rx_prescribed_by: %s", result)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Pass 6 — billing hmo_id
# ─────────────────────────────────────────────────────────────────────────────

def enrich_billing_hmo(conn, dry_run: bool = False) -> Dict[str, int]:
    """Set royan_billing.hmo_id via patient's hmo_provider text → royan_hmos."""
    hmo_rows = _load_master_table(conn, "royan_hmos", "id, name")
    lookup = build_hmo_lookup(hmo_rows)

    matched_billing: List[Tuple[int, int]] = []
    matched_claims: List[Tuple[int, int]] = []
    unmatched = 0

    with conn.cursor() as cur:
        # Billing: join via patient to get hmo_provider
        cur.execute(
            """
            SELECT b.id, p.hmo_provider
            FROM public.royan_billing b
            JOIN public.royan_patients p ON p.id = b.patient_id
            WHERE p.hmo_provider IS NOT NULL
              AND p.hmo_provider != ''
              AND b.hmo_id IS NULL
            """
        )
        for row in cur.fetchall():
            bill_id, hmo_name = row
            hmo_id = resolve_hmo_id(hmo_name, lookup)
            if hmo_id:
                matched_billing.append((bill_id, hmo_id))
            else:
                unmatched += 1

        # Insurance claims (royan_insurance_claims uses billing_id, not bill_id)
        cur.execute(
            """
            SELECT ic.id, p.hmo_provider
            FROM public.royan_insurance_claims ic
            JOIN public.royan_billing b ON b.id = ic.billing_id
            JOIN public.royan_patients p ON p.id = b.patient_id
            WHERE p.hmo_provider IS NOT NULL
              AND p.hmo_provider != ''
              AND ic.hmo_id IS NULL
            """
        )
        for row in cur.fetchall():
            claim_id, hmo_name = row
            hmo_id = resolve_hmo_id(hmo_name, lookup)
            if hmo_id:
                matched_claims.append((claim_id, hmo_id))

    updated_billing = _batch_update(
        conn, "royan_billing", "id", "hmo_id", matched_billing, dry_run, "billing:hmo"
    )
    updated_claims = _batch_update(
        conn, "royan_insurance_claims", "id", "hmo_id", matched_claims, dry_run, "claims:hmo"
    )

    result = {
        "billing_matched": len(matched_billing), "billing_updated": updated_billing,
        "claims_matched": len(matched_claims), "claims_updated": updated_claims,
        "unmatched_patients": unmatched,
    }
    logger.info("enrich_billing_hmo: %s", result)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Pass 7 — discharge records
# ─────────────────────────────────────────────────────────────────────────────

def enrich_discharge_records(conn, dry_run: bool = False) -> Dict[str, int]:
    """INSERT royan_discharge_records for all encounters where discharge_at IS NOT NULL.

    ON CONFLICT (encounter_id) DO NOTHING so re-runs are safe.
    Only creates a record if discharge_summary or discharge_by exists in the encounter,
    OR if the encounter has status = 'discharged'.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                e.id AS encounter_id,
                e.patient_id,
                e.discharge_at,
                e.discharge_summary,
                e.discharge_by,
                e.consulting_doctor
            FROM public.royan_encounters e
            WHERE e.status = 'discharged'
              OR e.discharge_at IS NOT NULL
            """
        )
        enc_rows = cur.fetchall()

    if dry_run:
        logger.info("[DRY RUN] enrich_discharge_records: would create %d records", len(enc_rows))
        return {"candidates": len(enc_rows), "inserted": 0}

    inserted = 0
    skipped = 0

    for i in range(0, len(enc_rows), _BATCH):
        chunk = enc_rows[i:i + _BATCH]
        with conn.cursor() as cur:
            for row in chunk:
                enc_id, pat_id, discharge_at, summary, discharged_by, doctor = row

                # Skip if discharge_at is null and no useful discharge info
                if not discharge_at and not summary and not discharged_by:
                    skipped += 1
                    continue

                cur.execute("SAVEPOINT _dr_sp")
                try:
                    cur.execute(
                        """
                        INSERT INTO public.royan_discharge_records (
                            encounter_id, patient_id, discharge_condition,
                            discharge_summary, discharged_by, discharged_at,
                            external_source, external_id
                        )
                        VALUES (%s, %s, 'stable', %s, %s, %s, %s, %s)
                        ON CONFLICT (encounter_id) DO NOTHING
                        """,
                        (
                            enc_id, pat_id, summary,
                            discharged_by or doctor,
                            discharge_at or utcnow(),
                            EXTERNAL_SOURCE,
                            str(enc_id),
                        ),
                    )
                    cur.execute("RELEASE SAVEPOINT _dr_sp")
                    if cur.rowcount > 0:
                        inserted += 1
                except Exception as exc:
                    cur.execute("ROLLBACK TO SAVEPOINT _dr_sp")
                    cur.execute("RELEASE SAVEPOINT _dr_sp")
                    logger.warning("discharge_records skip enc %s: %s", enc_id, exc)

        conn.commit()
        logger.debug("discharge_records batch %d–%d, %d inserted so far", i, i + len(chunk), inserted)

    result = {"candidates": len(enc_rows), "inserted": inserted, "skipped": skipped}
    logger.info("enrich_discharge_records: %s", result)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Master orchestrator
# ─────────────────────────────────────────────────────────────────────────────

ALL_PASSES = [
    "enc:dept",
    "enc:doctor",
    "lab:catalog",
    "lab:ordered-by",
    "rx:prescribed-by",
    "billing:hmo",
    "discharge:records",
]

_PASS_FN: Dict[str, Callable] = {
    "enc:dept":         enrich_encounter_depts,
    "enc:doctor":       enrich_encounter_doctors,
    "lab:catalog":      enrich_lab_catalog,
    "lab:ordered-by":   enrich_lab_ordered_by,
    "rx:prescribed-by": enrich_rx_prescribed_by,
    "billing:hmo":      enrich_billing_hmo,
    "discharge:records": enrich_discharge_records,
}


def run_all_passes(conn, passes: List[str], dry_run: bool = False) -> Dict[str, Any]:
    """Run a list of named enrichment passes. Returns a summary dict."""
    results: Dict[str, Any] = {}
    for name in passes:
        fn = _PASS_FN.get(name)
        if fn is None:
            logger.warning("Unknown pass: %s — skipping", name)
            results[name] = "SKIPPED (unknown)"
            continue
        logger.info("=== Running pass: %s ===", name)
        try:
            results[name] = fn(conn, dry_run=dry_run)
        except Exception as exc:
            logger.error("Pass %s FAILED: %s", name, exc, exc_info=True)
            try:
                conn.rollback()
            except Exception:
                pass
            results[name] = f"FAILED: {exc}"
    return results
