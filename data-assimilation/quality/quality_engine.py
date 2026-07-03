"""Data Quality Engine — Chapter 4 of the Implementation Guide.

Central validation runner that sits between Bronze extraction and Silver
upsert. Wraps the existing scorer + dimensions with domain-specific rule
overrides and writes rejected records to royan_import_rejections.

Pipeline position:
    Bronze → Transform → **QualityEngine.run()** → Silver upsert

Usage:
    engine = QualityEngine(conn, batch_id="20260628_0900")
    good, report = engine.run("patients", canonical_records)
    # `good` → pass to Silver upsert
    # report.hard_fails → already written to royan_import_rejections
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict
from typing import Any, Dict, List, Optional, Tuple

from quality.scorer import BatchQualityReport, score_batch
from quality.dimensions import DOMAIN_CONFIGS

logger = logging.getLogger(__name__)

# ── Domain config + extra-rule registry ──────────────────────────────────────

def _load_domain_config(domain: str) -> Dict[str, Any]:
    """Merge the base DOMAIN_CONFIGS entry with domain-specific overrides."""
    base = dict(DOMAIN_CONFIGS.get(domain, {}))

    try:
        if domain == "patients":
            from quality.rules.patient_rules import PATIENT_CONFIG
            base.update(PATIENT_CONFIG)
        elif domain in ("encounters", "encounter"):
            from quality.rules.encounter_rules import ENCOUNTER_CONFIG
            base.update(ENCOUNTER_CONFIG)
        elif domain in ("lab_orders", "lab"):
            from quality.rules.lab_rules import LAB_CONFIG
            base.update(LAB_CONFIG)
        elif domain in ("prescriptions", "pharmacy"):
            from quality.rules.pharmacy_rules import PHARMACY_CONFIG
            base.update(PHARMACY_CONFIG)
        elif domain == "billing":
            from quality.rules.billing_rules import BILLING_CONFIG
            base.update(BILLING_CONFIG)
    except ImportError:
        pass

    return base


def _run_extra_checks(domain: str, record: Dict[str, Any]) -> List[str]:
    """Call domain-specific extra_checks() if available."""
    try:
        if domain == "patients":
            from quality.rules.patient_rules import extra_checks
        elif domain in ("encounters", "encounter"):
            from quality.rules.encounter_rules import extra_checks
        elif domain in ("lab_orders", "lab"):
            from quality.rules.lab_rules import extra_checks
        elif domain in ("prescriptions", "pharmacy"):
            from quality.rules.pharmacy_rules import extra_checks
        elif domain == "billing":
            from quality.rules.billing_rules import extra_checks
        else:
            return []
        return extra_checks(record)
    except ImportError:
        return []


# ── Quality Engine ────────────────────────────────────────────────────────────

class QualityEngine:
    """Run quality scoring on a canonical record batch.

    Args:
        conn:     psycopg2 connection to the Synbot PostgreSQL database.
                  Required for writing rejections to royan_import_rejections.
                  May be None for dry-run / test scenarios.
        batch_id: Migration batch identifier — stored in rejection records.
    """

    def __init__(self, conn=None, batch_id: str = "manual") -> None:
        self._conn = conn
        self._batch_id = batch_id

    def run(
        self,
        domain: str,
        records: List[Dict[str, Any]],
        run_id: Optional[str] = None,
    ) -> Tuple[List[Dict[str, Any]], BatchQualityReport]:
        """Score *records* and return (passing_records, BatchQualityReport).

        Hard-fail records are written to royan_import_rejections and excluded
        from the returned passing_records list.

        Args:
            domain:  e.g. "patients", "encounters", "lab_orders"
            records: Canonical transformed records ready for Silver upsert.
            run_id:  Orchestrator run UUID for lineage.

        Returns:
            passing_records: Records that cleared quality gates.
            report:          Full BatchQualityReport for observability.
        """
        if not records:
            return [], BatchQualityReport(entity=domain)

        config = _load_domain_config(domain)

        # Augment records with extra-check violations stored as _quality_warnings
        augmented: List[Dict[str, Any]] = []
        for r in records:
            extra = _run_extra_checks(domain, r)
            if extra:
                r = {**r, "_extra_violations": extra}
            augmented.append(r)

        report, dlq_items = score_batch(domain, augmented, config)

        # Build set of DLQ keys for fast lookup
        dlq_keys = {
            str(item.get("record_key") or item.get("raw_record", {}).get("source_record_id") or "")
            for item in dlq_items
        }

        # Separate passing from rejected
        passing: List[Dict[str, Any]] = []
        for r in records:
            key = str(
                r.get("source_record_id")
                or r.get("mrn")
                or r.get("external_id")
                or r.get("id")
                or ""
            )
            if key not in dlq_keys:
                passing.append(r)

        # Persist hard failures to DLQ table
        if dlq_items and self._conn:
            self._write_rejections(domain, dlq_items, run_id)

        logger.info(
            "QualityEngine domain=%s total=%d passed=%d rejected=%d score=%.1f%%",
            domain, len(records), len(passing), len(dlq_items),
            report.overall_score * 100,
        )

        return passing, report

    def _write_rejections(
        self,
        domain: str,
        dlq_items: List[Dict[str, Any]],
        run_id: Optional[str],
    ) -> None:
        """Persist hard-fail records to royan_import_rejections."""
        try:
            with self._conn.cursor() as cur:
                for item in dlq_items:
                    raw = item.get("raw_record", {})
                    violations_json = json.dumps(item.get("violations", {}))
                    cur.execute(
                        """
                        INSERT INTO public.royan_import_rejections
                            (run_id, domain, source_system, source_record_id,
                             raw_record, error_message, rejected_at)
                        VALUES (%s, %s, %s, %s, %s, %s, now())
                        ON CONFLICT DO NOTHING
                        """,
                        (
                            run_id or self._batch_id,
                            domain,
                            raw.get("source_system", "hope"),
                            str(raw.get("source_record_id") or item.get("record_key") or ""),
                            json.dumps(raw),
                            violations_json[:2000],
                        ),
                    )
            self._conn.commit()
        except Exception as exc:
            self._conn.rollback()
            logger.warning("QualityEngine: DLQ write failed: %s", exc)

    def latest_report_summary(self, domain: str) -> Optional[Dict[str, Any]]:
        """Query royan_import_rejections for the most recent batch stats for *domain*."""
        if not self._conn:
            return None
        try:
            with self._conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        run_id,
                        COUNT(*)                 AS rejected_count,
                        MAX(rejected_at)         AS last_rejected_at
                    FROM public.royan_import_rejections
                    WHERE domain = %s
                    GROUP BY run_id
                    ORDER BY MAX(rejected_at) DESC
                    LIMIT 1
                    """,
                    (domain,),
                )
                row = cur.fetchone()
        except Exception:
            return None
        if not row:
            return None
        return {
            "domain": domain,
            "run_id": row[0],
            "rejected_count": row[1],
            "last_rejected_at": str(row[2]) if row[2] else None,
        }
