"""One-off repair for the shared encounter-key collision bug.

Root cause (fixed in transformers/lab.py, pharmacy.py, billing.py, and
backend/src/services/hope_sync.py): lab, pharmacy, and billing records were
each linked to a royan_encounters row keyed only by their OWN raw Hope ID
suffixed with ":encounter" — e.g. lab order #12345 and billing record #12345
both produced the key "12345:encounter". Since each entity has its own
independent ID sequence in Hope, this collided across entity types and
silently merged unrelated patients' records onto the same encounter row.

This script:
  1. Identifies every lab_order/prescription/billing row whose CURRENT
     encounter_id points to an encounter belonging to a DIFFERENT patient.
  2. Creates one "Ancillary Services" encounter per affected patient
     (idempotent — keyed on external_source='synbot_repair',
     external_id='ancillary:{patient_id}', ON CONFLICT DO NOTHING).
  3. Repoints encounter_id on those rows to the new, correct encounter.
  4. Deletes now-orphaned stub encounters — discovers EVERY table with an FK
     to royan_encounters via information_schema (not a hand-written list),
     so nothing with an ON DELETE SET NULL relationship (e.g. radiology
     orders) gets silently nulled out by being missed.

Every step is idempotent: rerunning after a successful (or partially
interrupted) run finds nothing left to do and is a no-op.

Usage:
    python scripts/repair_shared_encounter_keys.py --dry-run
    python scripts/repair_shared_encounter_keys.py --execute

Take a database backup before running with --execute. This is expected to
touch on the order of 450,000+ rows.
"""
from __future__ import annotations

import argparse
import logging
import sys

import psycopg2
import psycopg2.extras

sys.path.insert(0, ".")
from config import DATABASE_URL  # noqa: E402
from transformers._helpers import EXTERNAL_SOURCE  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("repair_shared_encounter_keys")

REPAIR_SOURCE = "synbot_repair"
BATCH_SIZE = 10_000

# The 3 tables the bug actually affects (see root cause above).
AFFECTED_TABLES = [
    ("royan_lab_orders", "lab orders"),
    ("royan_prescriptions", "prescriptions"),
    ("royan_billing", "billing records"),
]


def _connect() -> psycopg2.extensions.connection:
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False
    return conn


def _count_mismatched(cur, table: str) -> int:
    cur.execute(
        f"""
        SELECT count(*) FROM {table} t
        JOIN royan_encounters e ON e.id = t.encounter_id
        WHERE t.patient_id IS DISTINCT FROM e.patient_id
        """
    )
    return cur.fetchone()[0]


def _get_encounter_referencing_tables(cur) -> list[dict]:
    """Discover every table with an FK to royan_encounters, via pg_catalog
    introspection rather than a hand-maintained list — this is exactly the
    kind of check the Relationship Auditor (Part B.1) formalizes, done here
    inline since this script must be safe standalone.

    Uses pg_constraint/pg_class/pg_attribute directly rather than
    information_schema, which fans out one row per matched join path and
    produces duplicate (table, column) pairs. `relispartition = false`
    excludes partition child tables (e.g. fact_billing_summary_2024) since
    querying the parent partitioned table already covers all its partitions.
    """
    cur.execute(
        """
        SELECT DISTINCT
            cl.relname AS referencing_table,
            a.attname AS referencing_column,
            CASE con.confdeltype
                WHEN 'a' THEN 'NO ACTION'
                WHEN 'r' THEN 'RESTRICT'
                WHEN 'c' THEN 'CASCADE'
                WHEN 'n' THEN 'SET NULL'
                WHEN 'd' THEN 'SET DEFAULT'
            END AS delete_rule
        FROM pg_constraint con
        JOIN pg_class cl ON cl.oid = con.conrelid
        JOIN pg_attribute a ON a.attrelid = con.conrelid AND a.attnum = ANY(con.conkey)
        WHERE con.contype = 'f'
          AND con.confrelid = 'royan_encounters'::regclass
          AND cl.relispartition = false
        ORDER BY 1
        """
    )
    cols = [d.name for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def step1_identify(cur) -> dict[str, int]:
    counts = {}
    for table, label in AFFECTED_TABLES:
        n = _count_mismatched(cur, table)
        still_split = _count_needing_repoint(cur, table) - n
        counts[table] = n
        logger.info(
            "Step 1: %s mismatched (wrong-patient) rows in %s (%s); %s more still on an old single-record stub awaiting consolidation",
            n, table, label, still_split,
        )
    return counts


def step2_create_ancillary_encounters(cur, dry_run: bool) -> int:
    # A patient needs an ancillary encounter if either (a) they currently have
    # a mismatched-patient link (the correctness bug), or (b) they own an old
    # single-record stub encounter (external_id LIKE '%:encounter' — the
    # pre-fix key format) that should be folded into one consolidated
    # encounter rather than left as a one-record-per-stub leftover. Without
    # (b), only the mismatched records get consolidated and the patient whose
    # record legitimately created the stub first is left split across two
    # encounters instead of one.
    select_affected_patients = """
        SELECT DISTINCT t.patient_id FROM (
            SELECT patient_id, encounter_id FROM royan_lab_orders
            UNION ALL
            SELECT patient_id, encounter_id FROM royan_prescriptions
            UNION ALL
            SELECT patient_id, encounter_id FROM royan_billing
        ) t
        JOIN royan_encounters e ON e.id = t.encounter_id
        WHERE t.patient_id IS DISTINCT FROM e.patient_id
           OR e.external_id LIKE '%:encounter'
    """
    if dry_run:
        cur.execute(select_affected_patients)
        n = len(cur.fetchall())
        logger.info("Step 2 [dry-run]: would create up to %s ancillary encounters", n)
        return n

    # REPAIR_SOURCE is a fixed internal constant, not external input — inlined
    # directly (rather than via a %s placeholder) so this call passes no
    # params at all, since the LIKE '%...' pattern above would otherwise
    # collide with psycopg2's %-style parameter substitution.
    cur.execute(
        f"""
        INSERT INTO royan_encounters
            (patient_id, encounter_type, status, registered_by,
             external_source, external_id, external_updated_at, diagnosis_notes)
        SELECT DISTINCT patient_id, 'outpatient', 'consulting', 'synbot_repair_2026_07',
               '{REPAIR_SOURCE}', 'ancillary:' || patient_id, now(),
               'Consolidated ancillary (lab/pharmacy/billing) encounter created during the 2026-07 encounter-integrity repair'
        FROM ({select_affected_patients}) affected_patients
        ON CONFLICT (external_source, external_id) WHERE external_source IS NOT NULL AND external_id IS NOT NULL
        DO NOTHING
        """
    )
    n = cur.rowcount
    logger.info("Step 2: created %s new ancillary encounters", n)
    return n


def _count_needing_repoint(cur, table: str) -> int:
    """Rows that either mismatch their encounter's patient (the correctness
    bug) OR still point at an old single-record stub (external_id LIKE
    '%:encounter') that should be folded into the patient's consolidated
    ancillary encounter."""
    cur.execute(
        f"""
        SELECT count(*) FROM {table} t
        JOIN royan_encounters e ON e.id = t.encounter_id
        WHERE t.patient_id IS DISTINCT FROM e.patient_id
           OR e.external_id LIKE '%:encounter'
        """
    )
    return cur.fetchone()[0]


def step3_repoint(cur, table: str, label: str, dry_run: bool) -> int:
    if dry_run:
        n = _count_needing_repoint(cur, table)
        logger.info("Step 3 [dry-run]: would repoint %s rows in %s", n, table)
        return n

    total = 0
    while True:
        # BATCH_SIZE and REPAIR_SOURCE are fixed internal constants, inlined
        # directly rather than via %s placeholders — this call passes no
        # params, avoiding a collision between psycopg2's %-style parameter
        # substitution and the literal % in the LIKE pattern below.
        cur.execute(
            f"""
            WITH batch AS (
                SELECT t.id
                FROM {table} t
                JOIN royan_encounters e ON e.id = t.encounter_id
                WHERE t.patient_id IS DISTINCT FROM e.patient_id
                   OR e.external_id LIKE '%:encounter'
                LIMIT {BATCH_SIZE}
            )
            UPDATE {table} t
            SET encounter_id = anc.id
            FROM royan_encounters anc
            WHERE t.id IN (SELECT id FROM batch)
              AND anc.external_source = '{REPAIR_SOURCE}'
              AND anc.external_id = 'ancillary:' || t.patient_id
            """
        )
        n = cur.rowcount
        total += n
        logger.info("Step 3: repointed %s rows in %s (running total %s)", n, table, total)
        if n == 0:
            break
    return total


def step4_cleanup_orphans(cur, dry_run: bool) -> int:
    referencing = _get_encounter_referencing_tables(cur)
    logger.info("Step 4: discovered %s tables referencing royan_encounters", len(referencing))
    for ref in referencing:
        if ref["delete_rule"] == "SET NULL":
            marker = " (SET NULL - would silently null a real FK if missed)"
        elif ref["delete_rule"] == "CASCADE":
            marker = " (CASCADE - would silently delete real clinical rows if missed)"
        else:
            marker = ""
        logger.info("  - %s.%s [%s]%s", ref["referencing_table"], ref["referencing_column"], ref["delete_rule"], marker)

    if not referencing:
        raise RuntimeError(
            "FK introspection returned zero referencing tables — refusing to run the "
            "orphan cleanup with no exclusion list. This should never happen; investigate "
            "before proceeding."
        )

    not_exists_clauses = "\n      AND ".join(
        f'NOT EXISTS (SELECT 1 FROM {ref["referencing_table"]} WHERE {ref["referencing_column"]} = e.id)'
        for ref in referencing
    )

    select_orphans = f"""
        SELECT e.id FROM royan_encounters e
        WHERE e.department IN ('Laboratory & Diagnostics', 'Pharmacy', 'Billing & Finance')
          AND {not_exists_clauses}
    """

    if dry_run:
        cur.execute(select_orphans)
        n = len(cur.fetchall())
        logger.info("Step 4 [dry-run]: would delete %s now-orphaned stub encounters", n)
        return n

    deleted = 0
    while True:
        cur.execute(f"{select_orphans} LIMIT {BATCH_SIZE}")
        ids = [row[0] for row in cur.fetchall()]
        if not ids:
            break
        for eid in ids:
            try:
                cur.execute("SAVEPOINT _del_sp")
                cur.execute("DELETE FROM royan_encounters WHERE id = %s", (eid,))
                cur.execute("RELEASE SAVEPOINT _del_sp")
                deleted += 1
            except Exception as exc:
                cur.execute("ROLLBACK TO SAVEPOINT _del_sp")
                cur.execute("RELEASE SAVEPOINT _del_sp")
                logger.warning("Could not delete encounter %s: %s", eid, exc)
        logger.info("Step 4: deleted %s stub encounters so far", deleted)
    return deleted


def main():
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    dry_run = args.dry_run

    conn = _connect()
    try:
        with conn.cursor() as cur:
            logger.info("=== Step 1: identify ===")
            before_counts = step1_identify(cur)

            logger.info("=== Step 2: create ancillary encounters ===")
            step2_create_ancillary_encounters(cur, dry_run)

            logger.info("=== Step 3: repoint encounter_id ===")
            for table, label in AFFECTED_TABLES:
                step3_repoint(cur, table, label, dry_run)

            logger.info("=== Step 4: clean up orphaned stub encounters ===")
            step4_cleanup_orphans(cur, dry_run)

            logger.info("=== Verification: re-count mismatches ===")
            after_counts = step1_identify(cur)
            for table, _ in AFFECTED_TABLES:
                logger.info(
                    "%s: %s -> %s mismatched rows",
                    table, before_counts[table], after_counts[table] if not dry_run else "(unchanged, dry-run)",
                )

        if dry_run:
            conn.rollback()
            logger.info("Dry-run complete - no changes committed.")
        else:
            conn.commit()
            logger.info("Repair complete - changes committed.")
    except Exception:
        conn.rollback()
        logger.exception("Repair failed - rolled back.")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
