"""Production readiness gates — Chapter 5.15 of the blueprint.

Run after every full ETL load to assert the database meets minimum quality
thresholds before it is considered production-ready.

Gates that FAIL cause the script to exit with code 1 so CI/deployment
pipelines can block promotion.

Usage:
    python -m quality.readiness_gate --database-url postgresql://...
    python -m quality.readiness_gate   # uses DATABASE_URL env var

Exit codes:
    0 — all gates passed
    1 — one or more gates failed
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from dataclasses import dataclass
from typing import List

import psycopg2

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)


@dataclass
class Gate:
    name: str
    query: str
    threshold: float        # minimum acceptable value (0–100 for percentages, or count)
    operator: str           # "gte" | "lte" | "eq"
    description: str
    is_hard_fail: bool = True


# ─────────────────────────────────────────────────────────────────────────────
# Gate definitions
# ─────────────────────────────────────────────────────────────────────────────

GATES: List[Gate] = [
    Gate(
        name="patient_mrn_uniqueness",
        query="SELECT COUNT(*) FROM (SELECT mrn, COUNT(*) c FROM public.royan_patients GROUP BY mrn HAVING COUNT(*) > 1) dups",
        threshold=0,
        operator="lte",
        description="Zero duplicate MRNs in royan_patients",
    ),
    Gate(
        name="patient_required_fields_completeness",
        query="""
            SELECT ROUND(
                100.0 * COUNT(*) FILTER (
                    WHERE mrn IS NOT NULL AND mrn != ''
                      AND first_name IS NOT NULL AND first_name != ''
                      AND last_name IS NOT NULL AND last_name != ''
                ) / NULLIF(COUNT(*), 0), 1
            )
            FROM public.royan_patients
        """,
        threshold=98.0,
        operator="gte",
        description="Patient required fields (MRN, first_name, last_name) completeness ≥ 98%",
    ),
    Gate(
        name="orphaned_encounters",
        query="""
            SELECT COUNT(*)
            FROM public.royan_encounters e
            WHERE NOT EXISTS (SELECT 1 FROM public.royan_patients p WHERE p.id = e.patient_id)
        """,
        threshold=0,
        operator="lte",
        description="Zero orphaned encounters (missing patient_id FK)",
    ),
    Gate(
        name="orphaned_lab_orders",
        query="""
            SELECT COUNT(*)
            FROM public.royan_lab_orders lo
            WHERE NOT EXISTS (SELECT 1 FROM public.royan_patients p WHERE p.id = lo.patient_id)
        """,
        threshold=0,
        operator="lte",
        description="Zero orphaned lab orders (missing patient_id FK)",
    ),
    Gate(
        name="orphaned_prescriptions",
        query="""
            SELECT COUNT(*)
            FROM public.royan_prescriptions rx
            WHERE NOT EXISTS (SELECT 1 FROM public.royan_patients p WHERE p.id = rx.patient_id)
        """,
        threshold=0,
        operator="lte",
        description="Zero orphaned prescriptions (missing patient_id FK)",
    ),
    Gate(
        name="orphaned_billing",
        query="""
            SELECT COUNT(*)
            FROM public.royan_billing b
            WHERE NOT EXISTS (SELECT 1 FROM public.royan_patients p WHERE p.id = b.patient_id)
        """,
        threshold=0,
        operator="lte",
        description="Zero orphaned billing records (missing patient_id FK)",
    ),
    Gate(
        name="lab_test_name_resolution",
        query="""
            SELECT ROUND(
                100.0 * COUNT(*) FILTER (
                    WHERE lower(test_name) NOT IN (
                        'imported lab order', 'lab test', 'laboratory test', 'test', 'investigation', ''
                    )
                ) / NULLIF(COUNT(*), 0), 1
            )
            FROM public.royan_lab_orders
            WHERE external_source = 'hope'
        """,
        threshold=90.0,
        operator="gte",
        description="Lab orders with resolved test names ≥ 90% (run backfill_lab_test_names.py first)",
        is_hard_fail=False,      # warning only
    ),
    Gate(
        name="mdm_departments_seeded",
        query="SELECT COUNT(*) FROM public.royan_departments WHERE is_active = true",
        threshold=5,
        operator="gte",
        description="At least 5 active departments in master data",
    ),
    Gate(
        name="mdm_lab_catalog_seeded",
        query="SELECT COUNT(*) FROM public.royan_lab_catalog WHERE is_active = true",
        threshold=10,
        operator="gte",
        description="At least 10 active lab catalog entries",
    ),
    Gate(
        name="patient_count_sanity",
        query="SELECT COUNT(*) FROM public.royan_patients",
        threshold=1000,
        operator="gte",
        description="At least 1,000 patients present (confirms bulk import ran)",
    ),
    Gate(
        name="encounter_count_sanity",
        query="SELECT COUNT(*) FROM public.royan_encounters",
        threshold=1000,
        operator="gte",
        description="At least 1,000 encounters present",
    ),
    Gate(
        name="encounter_dept_enrichment",
        query="""
            SELECT ROUND(
                100.0 * COUNT(*) FILTER (WHERE department_id IS NOT NULL)
                / NULLIF(COUNT(*), 0), 1
            )
            FROM public.royan_encounters
            WHERE department IS NOT NULL AND department != ''
        """,
        threshold=80.0,
        operator="gte",
        description="Encounter department_id FK resolved ≥ 80% (run run_enrichment.py first)",
        is_hard_fail=False,
    ),
    Gate(
        name="encounter_doctor_enrichment",
        query="""
            SELECT ROUND(
                100.0 * COUNT(*) FILTER (WHERE doctor_id IS NOT NULL)
                / NULLIF(COUNT(*), 0), 1
            )
            FROM public.royan_encounters
            WHERE consulting_doctor IS NOT NULL AND consulting_doctor != ''
        """,
        threshold=30.0,
        operator="gte",
        description="Encounter doctor_id FK resolved ≥ 30% (lower threshold — Hope stores staff IDs not names)",
        is_hard_fail=False,
    ),
    Gate(
        name="discharge_records_created",
        query="""
            SELECT COUNT(*)
            FROM public.royan_discharge_records
        """,
        threshold=100,
        operator="gte",
        description="At least 100 discharge records created (run run_enrichment.py discharge:records)",
        is_hard_fail=False,
    ),
]


# ─────────────────────────────────────────────────────────────────────────────
# Runner
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class GateResult:
    gate: Gate
    actual_value: float
    passed: bool

    def __str__(self) -> str:
        status = "✓ PASS" if self.passed else ("⚠ WARN" if not self.gate.is_hard_fail else "✗ FAIL")
        return (
            f"{status}  {self.gate.name}\n"
            f"       {self.gate.description}\n"
            f"       Actual={self.actual_value}  Expected {self.gate.operator} {self.gate.threshold}"
        )


def _compare(actual: float, threshold: float, operator: str) -> bool:
    if operator == "gte":
        return actual >= threshold
    if operator == "lte":
        return actual <= threshold
    if operator == "eq":
        return actual == threshold
    return False


def run_gates(database_url: str) -> bool:
    """Run all gates. Returns True if all hard-fail gates pass."""
    conn = psycopg2.connect(database_url)
    results: List[GateResult] = []

    try:
        with conn.cursor() as cur:
            for gate in GATES:
                try:
                    cur.execute(gate.query)
                    row = cur.fetchone()
                    actual = float(row[0]) if row and row[0] is not None else 0.0
                    passed = _compare(actual, gate.threshold, gate.operator)
                    results.append(GateResult(gate=gate, actual_value=actual, passed=passed))
                except Exception as exc:
                    log.error("Gate '%s' error: %s", gate.name, exc)
                    results.append(GateResult(gate=gate, actual_value=-1, passed=False))
    finally:
        conn.close()

    print("\n" + "=" * 60)
    print("  SYNBOT HEALTH — PRODUCTION READINESS GATES")
    print("=" * 60)

    hard_failures = 0
    warnings = 0
    for r in results:
        print(f"\n{r}")
        if not r.passed:
            if r.gate.is_hard_fail:
                hard_failures += 1
            else:
                warnings += 1

    print("\n" + "=" * 60)
    print(f"  Gates: {len(results)}  |  Passed: {sum(r.passed for r in results)}"
          f"  |  Warnings: {warnings}  |  Hard Failures: {hard_failures}")

    if hard_failures == 0:
        print("\n  ✓ PLATFORM IS PRODUCTION READY")
    else:
        print(f"\n  ✗ PLATFORM NOT READY — {hard_failures} hard gate(s) failed")

    print("=" * 60 + "\n")
    return hard_failures == 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        default=os.getenv("DATABASE_URL", ""),
        help="PostgreSQL connection URL (default: $DATABASE_URL)",
    )
    args = parser.parse_args()

    if not args.database_url:
        log.error("DATABASE_URL not set. Pass --database-url or set env var.")
        sys.exit(1)

    ok = run_gates(args.database_url)
    sys.exit(0 if ok else 1)
