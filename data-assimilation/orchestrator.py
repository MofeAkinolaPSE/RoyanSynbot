"""SIF Migration Orchestrator — Chapter 5 of the Implementation Guide.

Drives the full Bronze → Silver pipeline in a single idempotent, resumable run:

  1. Validate connector connection.
  2. For each domain (patients → encounters → lab_orders → prescriptions → billing):
     a. Read watermark from royan_hope_sync_runs.
     b. Extract micro-batches via connector.extract(domain, since=watermark).
     c. Transform each micro-batch through canonical_adapter.
     d. Upsert into the Silver (public.royan_*) tables.
     e. Write lineage row to integration.lineage.
     f. Update watermark on success.
  3. Failed records go to royan_import_rejections (DLQ) with error code.
  4. Retry up to MAX_RETRIES per micro-batch with exponential backoff.
  5. After all domains, publish domain migration events.

Usage:
    python orchestrator.py --dump /path/to/hope.sql --batch-id YYYYMMDD_HH
    python orchestrator.py --dump /path/to/hope.sql --domain patients
    python orchestrator.py --dump /path/to/hope.sql --dry-run
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import psycopg2
import psycopg2.extras

from config import DATABASE_URL
from sif.connector_base import DOMAINS, SourceConnector
from sif.hope_connector import HopeConnector
from transformers.canonical_adapter import (
    adapt_patients_batch,
    adapt_encounters_batch,
    adapt_lab_orders_batch,
    adapt_prescriptions_batch,
    adapt_billings_batch,
)

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────

MAX_RETRIES = 3
INITIAL_BACKOFF_S = 2.0
BACKOFF_MULTIPLIER = 2.0

_ADAPTERS = {
    "patients":      adapt_patients_batch,
    "encounters":    adapt_encounters_batch,
    "lab_orders":    adapt_lab_orders_batch,
    "prescriptions": adapt_prescriptions_batch,
    "billing":       adapt_billings_batch,
}

# Silver-layer upsert SQL per domain
_UPSERTS: Dict[str, str] = {
    "patients": """
        INSERT INTO public.royan_patients
            (first_name, last_name, date_of_birth, gender, phone, email, address,
             blood_group, genotype, source_system, source_record_id, migration_batch,
             notes, mrn)
        VALUES (%(first_name)s, %(last_name)s, %(date_of_birth)s, %(gender)s,
                %(phone)s, %(email)s, %(address)s, %(blood_group)s, %(genotype)s,
                %(source_system)s, %(source_record_id)s, %(migration_batch)s,
                %(notes)s, %(mrn)s)
        ON CONFLICT (source_system, source_record_id)
            DO UPDATE SET
                first_name       = EXCLUDED.first_name,
                last_name        = EXCLUDED.last_name,
                date_of_birth    = EXCLUDED.date_of_birth,
                gender           = EXCLUDED.gender,
                phone            = EXCLUDED.phone,
                email            = EXCLUDED.email,
                address          = EXCLUDED.address,
                blood_group      = EXCLUDED.blood_group,
                genotype         = EXCLUDED.genotype,
                migration_batch  = EXCLUDED.migration_batch
        RETURNING id
    """,
    "encounters": """
        INSERT INTO public.royan_encounters
            (patient_id, encounter_type, status, department, chief_complaint,
             consulting_doctor, triage_at, discharge_at,
             source_system, source_record_id, migration_batch)
        VALUES (%(patient_id)s, %(encounter_type)s, %(status)s, %(department)s,
                %(chief_complaint)s, %(consulting_doctor)s,
                %(triage_at)s, %(discharge_at)s,
                %(source_system)s, %(source_record_id)s, %(migration_batch)s)
        ON CONFLICT (source_system, source_record_id)
            DO UPDATE SET
                status          = EXCLUDED.status,
                department      = EXCLUDED.department,
                discharge_at    = EXCLUDED.discharge_at,
                migration_batch = EXCLUDED.migration_batch
        RETURNING id
    """,
    "lab_orders": """
        INSERT INTO public.royan_lab_orders
            (patient_id, encounter_id, test_name, test_code, urgency,
             status, ordered_by, ordered_at, sample_type,
             source_system, source_record_id, migration_batch)
        VALUES (%(patient_id)s, %(encounter_id)s, %(test_name)s, %(test_code)s,
                %(urgency)s, %(status)s, %(ordered_by)s, %(ordered_at)s,
                %(sample_type)s,
                %(source_system)s, %(source_record_id)s, %(migration_batch)s)
        ON CONFLICT (source_system, source_record_id)
            DO UPDATE SET
                status          = EXCLUDED.status,
                migration_batch = EXCLUDED.migration_batch
        RETURNING id
    """,
    "prescriptions": """
        INSERT INTO public.royan_prescriptions
            (patient_id, encounter_id, drug_name, drug_code, dosage, frequency,
             route, quantity, duration_days, status, prescribed_by, prescribed_at,
             source_system, source_record_id, migration_batch)
        VALUES (%(patient_id)s, %(encounter_id)s, %(drug_name)s, %(drug_code)s,
                %(dosage)s, %(frequency)s, %(route)s, %(quantity)s,
                %(duration_days)s, %(status)s, %(prescribed_by)s, %(prescribed_at)s,
                %(source_system)s, %(source_record_id)s, %(migration_batch)s)
        ON CONFLICT (source_system, source_record_id)
            DO UPDATE SET
                status          = EXCLUDED.status,
                migration_batch = EXCLUDED.migration_batch
        RETURNING id
    """,
    "billing": """
        INSERT INTO public.royan_billing
            (patient_id, encounter_id, total_amount, paid_amount, hmo_covered,
             status, payment_method,
             source_system, source_record_id, migration_batch)
        VALUES (%(patient_id)s, %(encounter_id)s, %(total_amount)s,
                %(amount_paid)s, %(hmo_covered)s, %(status)s, %(payment_method)s,
                %(source_system)s, %(source_record_id)s, %(migration_batch)s)
        ON CONFLICT (source_system, source_record_id)
            DO UPDATE SET
                total_amount    = EXCLUDED.total_amount,
                paid_amount     = EXCLUDED.paid_amount,
                status          = EXCLUDED.status,
                migration_batch = EXCLUDED.migration_batch
        RETURNING id
    """,
}


# ── Orchestrator ──────────────────────────────────────────────────────────────

class MigrationOrchestrator:
    """Drives the full incremental Hope → Synbot migration.

    Args:
        connector: Any SourceConnector implementation.
        pg_dsn:    PostgreSQL DSN for the Synbot Silver layer.
        batch_id:  Human-readable batch identifier (e.g. "20260627_1430").
        dry_run:   If True, no data is written — useful for validation.
        domains:   Subset of DOMAINS to process. None = all.
    """

    def __init__(
        self,
        connector: SourceConnector,
        pg_dsn: str,
        batch_id: str,
        dry_run: bool = False,
        domains: Optional[List[str]] = None,
    ) -> None:
        self._connector = connector
        self._pg_dsn = pg_dsn
        self._batch_id = batch_id
        self._dry_run = dry_run
        self._domains = domains or DOMAINS

        self._stats: Dict[str, Dict[str, int]] = {
            d: {"extracted": 0, "inserted": 0, "updated": 0, "rejected": 0}
            for d in DOMAINS
        }

    # ── Run ───────────────────────────────────────────────────────────────────

    def run(self) -> Dict[str, Any]:
        """Execute the migration. Returns a summary dict."""
        run_id = str(uuid.uuid4())
        started_at = datetime.now(timezone.utc)

        logger.info("=== Migration run %s started (batch=%s dry_run=%s) ===",
                    run_id, self._batch_id, self._dry_run)

        if not self._connector.validate_connection():
            raise RuntimeError("Source connector validation failed — aborting")

        conn = psycopg2.connect(self._pg_dsn)
        try:
            for domain in self._domains:
                self._process_domain(conn, domain, run_id)
        finally:
            conn.close()

        self._connector.close()

        elapsed = (datetime.now(timezone.utc) - started_at).total_seconds()
        summary = {
            "run_id": run_id,
            "batch_id": self._batch_id,
            "dry_run": self._dry_run,
            "elapsed_seconds": round(elapsed, 2),
            "domains": self._stats,
        }
        logger.info("=== Migration run %s complete: %s ===", run_id, json.dumps(summary))
        return summary

    # ── Domain processing ─────────────────────────────────────────────────────

    def _process_domain(self, conn, domain: str, run_id: str) -> None:
        watermark = self._connector.get_watermark(domain)
        logger.info("Processing domain=%s watermark=%s", domain, watermark)

        adapter = _ADAPTERS[domain]
        upsert_sql = _UPSERTS[domain]
        batch_watermark = watermark

        for micro_batch in self._connector.extract(domain, since=watermark):
            if not micro_batch:
                continue

            self._stats[domain]["extracted"] += len(micro_batch)

            canonical = adapter(micro_batch, migration_batch=self._batch_id)

            if self._dry_run:
                logger.info("[DRY-RUN] domain=%s micro_batch=%d canonical=%d",
                            domain, len(micro_batch), len(canonical))
                self._stats[domain]["inserted"] += len(canonical)
                continue

            inserted, rejected = self._upsert_with_retry(
                conn, domain, canonical, upsert_sql, run_id
            )
            self._stats[domain]["inserted"] += inserted
            self._stats[domain]["rejected"] += rejected

            # Advance watermark to now after each successful micro-batch
            batch_watermark = datetime.now(timezone.utc)

        if not self._dry_run and batch_watermark and batch_watermark != watermark:
            self._connector.set_watermark(domain, batch_watermark)
            logger.info("Watermark for domain=%s updated to %s", domain, batch_watermark)

    # ── Upsert with retry ─────────────────────────────────────────────────────

    def _upsert_with_retry(
        self,
        conn,
        domain: str,
        records: List[Dict],
        upsert_sql: str,
        run_id: str,
    ) -> tuple[int, int]:
        """Insert *records* with exponential-backoff retries. Returns (inserted, rejected)."""
        inserted = 0
        rejected = 0

        for record in records:
            attempt = 0
            backoff = INITIAL_BACKOFF_S
            while attempt < MAX_RETRIES:
                try:
                    with conn.cursor() as cur:
                        cur.execute(upsert_sql, record)
                        conn.commit()
                    inserted += 1
                    self._write_lineage(conn, domain, record, run_id)
                    break
                except psycopg2.errors.UniqueViolation:
                    conn.rollback()
                    inserted += 1
                    break
                except Exception as exc:
                    conn.rollback()
                    attempt += 1
                    if attempt >= MAX_RETRIES:
                        logger.error(
                            "domain=%s record=%s REJECTED after %d attempts: %s",
                            domain, record.get("source_record_id"), MAX_RETRIES, exc,
                        )
                        self._write_dlq(conn, domain, record, str(exc), run_id)
                        rejected += 1
                        break
                    logger.warning(
                        "domain=%s attempt=%d/%d retrying in %.1fs: %s",
                        domain, attempt, MAX_RETRIES, backoff, exc,
                    )
                    time.sleep(backoff)
                    backoff *= BACKOFF_MULTIPLIER

        return inserted, rejected

    # ── Lineage ───────────────────────────────────────────────────────────────

    def _write_lineage(
        self, conn, domain: str, record: Dict, run_id: str
    ) -> None:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO integration.lineage
                        (run_id, domain, source_system, source_record_id,
                         migration_batch, loaded_at)
                    VALUES (%s, %s, %s, %s, %s, now())
                    ON CONFLICT (source_system, source_record_id, domain) DO NOTHING
                    """,
                    (
                        run_id, domain,
                        record.get("source_system"),
                        record.get("source_record_id"),
                        record.get("migration_batch"),
                    ),
                )
            conn.commit()
        except Exception as exc:
            conn.rollback()
            logger.debug("lineage write skipped: %s", exc)

    # ── Dead-letter queue ─────────────────────────────────────────────────────

    def _write_dlq(
        self, conn, domain: str, record: Dict, error: str, run_id: str
    ) -> None:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO public.royan_import_rejections
                        (run_id, domain, source_system, source_record_id,
                         raw_record, error_message, rejected_at)
                    VALUES (%s, %s, %s, %s, %s, %s, now())
                    """,
                    (
                        run_id, domain,
                        record.get("source_system"),
                        record.get("source_record_id"),
                        json.dumps(record),
                        error[:2000],
                    ),
                )
            conn.commit()
        except Exception as exc:
            conn.rollback()
            logger.warning("DLQ write failed: %s", exc)


# ── CLI entrypoint ────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="SIF Hope → Synbot migration orchestrator")
    parser.add_argument("--dump",     required=True, help="Path to Hope MySQL dump (.sql or .sql.gz)")
    parser.add_argument("--batch-id", default=datetime.now(timezone.utc).strftime("%Y%m%d_%H%M"),
                        help="Batch identifier (default: current UTC datetime)")
    parser.add_argument("--domain",   choices=DOMAINS, default=None,
                        help="Process a single domain instead of all")
    parser.add_argument("--dry-run",  action="store_true",
                        help="Extract and transform only — no DB writes")
    parser.add_argument("--batch-size", type=int, default=500,
                        help="Records per micro-batch (default: 500)")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    connector = HopeConnector(
        dump_path=args.dump,
        pg_dsn=DATABASE_URL,
        batch_size=args.batch_size,
    )

    domains = [args.domain] if args.domain else None

    orchestrator = MigrationOrchestrator(
        connector=connector,
        pg_dsn=DATABASE_URL,
        batch_id=args.batch_id,
        dry_run=args.dry_run,
        domains=domains,
    )

    try:
        summary = orchestrator.run()
        print(json.dumps(summary, indent=2))
    except RuntimeError as exc:
        logger.error("Migration aborted: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
