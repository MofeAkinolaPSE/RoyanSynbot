"""Relationship Auditor — the database-integrity engine of the Synbot Data
Intelligence Layer (SDIL).

Instead of validating tables by row count, this validates *relationships*:
  - discovers the live FK graph rooted at royan_patients / royan_encounters
    from pg_catalog (never a hand-maintained table list),
  - counts orphaned rows per relationship,
  - computes relationship coverage % per hop (patient→encounter→lab→billing),
  - flags cardinality violations — the generalized form of the encounter-key
    collision bug found in the 2026-07 audit, where a row's own patient_id
    disagreed with its linked encounter's patient_id,
  - rolls everything up into a single integrity score.

Raw SQL against pg_catalog/information_schema via the shared connection pool
(same pattern as routers/mdm_governance.py) — the db.table() builder can't
express catalog introspection.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from ..db import db

logger = logging.getLogger("relationship_auditor")

ROOT_TABLES = ("royan_patients", "royan_encounters")


def _get_conn():
    return db.pool.getconn()


def _put_conn(conn):
    db.pool.putconn(conn)


# ─────────────────────────────────────────────────────────────────────────────
# FK graph discovery
# ─────────────────────────────────────────────────────────────────────────────

def get_fk_graph() -> List[Dict[str, Any]]:
    """Every FK edge pointing at royan_patients or royan_encounters,
    discovered live from pg_catalog. Partition children are excluded — the
    parent partitioned table covers them."""
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT
                    cl.relname AS referencing_table,
                    a.attname AS referencing_column,
                    ref.relname AS referenced_table,
                    CASE con.confdeltype
                        WHEN 'a' THEN 'NO ACTION'
                        WHEN 'r' THEN 'RESTRICT'
                        WHEN 'c' THEN 'CASCADE'
                        WHEN 'n' THEN 'SET NULL'
                        WHEN 'd' THEN 'SET DEFAULT'
                    END AS delete_rule
                FROM pg_constraint con
                JOIN pg_class cl ON cl.oid = con.conrelid
                JOIN pg_class ref ON ref.oid = con.confrelid
                JOIN pg_attribute a ON a.attrelid = con.conrelid AND a.attnum = ANY(con.conkey)
                WHERE con.contype = 'f'
                  AND ref.relname IN %s
                  AND cl.relispartition = false
                ORDER BY 3, 1
                """,
                (ROOT_TABLES,),
            )
            cols = [d.name for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
    finally:
        _put_conn(conn)


# ─────────────────────────────────────────────────────────────────────────────
# Orphans & coverage
# ─────────────────────────────────────────────────────────────────────────────

def compute_orphan_counts(fk_graph: List[Dict[str, Any]] | None = None) -> List[Dict[str, Any]]:
    """Per FK edge: how many rows have a non-NULL FK value that resolves to
    no row in the referenced table. With real FK constraints enforced this
    should always be 0 — a non-zero count means a constraint is NOT VALID
    (unvalidated legacy data) or was dropped."""
    edges = fk_graph if fk_graph is not None else get_fk_graph()
    results: List[Dict[str, Any]] = []
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            for edge in edges:
                t, c, ref = edge["referencing_table"], edge["referencing_column"], edge["referenced_table"]
                try:
                    cur.execute(
                        f"""
                        SELECT count(*) FROM {t} child
                        WHERE child.{c} IS NOT NULL
                          AND NOT EXISTS (SELECT 1 FROM {ref} p WHERE p.id = child.{c})
                        """
                    )
                    orphans = cur.fetchone()[0]
                except Exception as exc:
                    conn.rollback()
                    logger.warning("orphan check failed for %s.%s: %s", t, c, exc)
                    orphans = None
                results.append({**edge, "orphan_count": orphans})
    finally:
        _put_conn(conn)
    return results


def compute_relationship_coverage(fk_graph: List[Dict[str, Any]] | None = None) -> List[Dict[str, Any]]:
    """Per FK edge: total rows, rows with the FK populated, and the coverage
    percentage — 'X% of lab orders are linked to an encounter' rather than a
    bare row count."""
    edges = fk_graph if fk_graph is not None else get_fk_graph()
    results: List[Dict[str, Any]] = []
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            for edge in edges:
                t, c = edge["referencing_table"], edge["referencing_column"]
                try:
                    cur.execute(f"SELECT count(*), count({c}) FROM {t}")
                    total, linked = cur.fetchone()
                    pct = round(linked / total * 100, 1) if total else None
                except Exception as exc:
                    conn.rollback()
                    logger.warning("coverage check failed for %s.%s: %s", t, c, exc)
                    total, linked, pct = None, None, None
                results.append({
                    "referencing_table": t,
                    "referencing_column": c,
                    "referenced_table": edge["referenced_table"],
                    "total_rows": total,
                    "linked_rows": linked,
                    "coverage_pct": pct,
                })
    finally:
        _put_conn(conn)
    return results


# ─────────────────────────────────────────────────────────────────────────────
# Cardinality / cross-reference consistency
# ─────────────────────────────────────────────────────────────────────────────

def compute_cardinality_violations() -> List[Dict[str, Any]]:
    """For every table that carries BOTH a patient_id and an encounter_id,
    count rows where the row's own patient_id disagrees with its linked
    encounter's patient_id — the generalized form of the encounter-key
    collision bug. Should be 0 everywhere after the 2026-07 repair."""
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            # Find candidate tables: non-partition public tables having both columns
            cur.execute(
                """
                SELECT c.relname
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'public'
                  AND c.relkind IN ('r', 'p')
                  AND c.relispartition = false
                  AND c.relname != 'royan_encounters'
                  AND EXISTS (SELECT 1 FROM pg_attribute a WHERE a.attrelid = c.oid AND a.attname = 'patient_id' AND NOT a.attisdropped)
                  AND EXISTS (SELECT 1 FROM pg_attribute a WHERE a.attrelid = c.oid AND a.attname = 'encounter_id' AND NOT a.attisdropped)
                ORDER BY 1
                """
            )
            tables = [row[0] for row in cur.fetchall()]

            results: List[Dict[str, Any]] = []
            for t in tables:
                try:
                    cur.execute(
                        f"""
                        SELECT count(*) FROM {t} t
                        JOIN royan_encounters e ON e.id = t.encounter_id
                        WHERE t.patient_id IS DISTINCT FROM e.patient_id
                        """
                    )
                    violations = cur.fetchone()[0]
                except Exception as exc:
                    conn.rollback()
                    logger.warning("cardinality check failed for %s: %s", t, exc)
                    violations = None
                results.append({"table": t, "patient_encounter_mismatches": violations})
            return results
    finally:
        _put_conn(conn)


# ─────────────────────────────────────────────────────────────────────────────
# Integrity score
# ─────────────────────────────────────────────────────────────────────────────

def compute_integrity_score() -> Dict[str, Any]:
    """Assemble the full audit and roll it into one score.

    Score = average of:
      - orphan health: 100 if zero orphans anywhere, scaled down otherwise
      - cardinality health: 100 if zero patient/encounter mismatches
      - coverage: mean coverage_pct across NOT NULL-intended clinical edges
    """
    fk_graph = get_fk_graph()
    orphans = compute_orphan_counts(fk_graph)
    coverage = compute_relationship_coverage(fk_graph)
    cardinality = compute_cardinality_violations()

    total_orphans = sum(o["orphan_count"] or 0 for o in orphans)
    total_mismatches = sum(c["patient_encounter_mismatches"] or 0 for c in cardinality)
    coverage_values = [c["coverage_pct"] for c in coverage if c["coverage_pct"] is not None]
    mean_coverage = round(sum(coverage_values) / len(coverage_values), 1) if coverage_values else 0.0

    orphan_health = 100.0 if total_orphans == 0 else max(0.0, 100.0 - total_orphans / 100)
    cardinality_health = 100.0 if total_mismatches == 0 else max(0.0, 100.0 - total_mismatches / 1000)
    overall = round((orphan_health + cardinality_health + mean_coverage) / 3, 1)

    return {
        "overall_score": overall,
        "orphan_health": round(orphan_health, 1),
        "cardinality_health": round(cardinality_health, 1),
        "mean_relationship_coverage_pct": mean_coverage,
        "total_orphans": total_orphans,
        "total_patient_encounter_mismatches": total_mismatches,
        "fk_edge_count": len(fk_graph),
        "fk_graph": fk_graph,
        "orphan_counts": orphans,
        "relationship_coverage": coverage,
        "cardinality_violations": cardinality,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Per-patient relationship tree (consumed by the Clinical Data Explorer)
# ─────────────────────────────────────────────────────────────────────────────

def get_patient_relationship_tree(patient_id: int) -> Dict[str, Any]:
    """Counts of every FK-linked record type for one patient — the 'click a
    patient, see everything' graph view, discovered from the same live FK
    graph rather than a hardcoded table list."""
    fk_graph = get_fk_graph()
    patient_edges = [e for e in fk_graph if e["referenced_table"] == "royan_patients"]

    tree: Dict[str, Any] = {"patient_id": patient_id, "relations": []}
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            for edge in patient_edges:
                t, c = edge["referencing_table"], edge["referencing_column"]
                try:
                    cur.execute(f"SELECT count(*) FROM {t} WHERE {c} = %s", (patient_id,))
                    count = cur.fetchone()[0]
                except Exception as exc:
                    conn.rollback()
                    logger.warning("tree count failed for %s.%s: %s", t, c, exc)
                    count = None
                if count:
                    tree["relations"].append({
                        "table": t,
                        "column": c,
                        "count": count,
                    })
    finally:
        _put_conn(conn)
    tree["relations"].sort(key=lambda r: -(r["count"] or 0))
    return tree
