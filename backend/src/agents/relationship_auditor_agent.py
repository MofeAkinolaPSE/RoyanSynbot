"""Relationship Auditor Agent.

Registered under the name ``relationship_auditor``. Runs the SDIL database
integrity audit (FK graph, orphans, relationship coverage, cardinality
violations) and emits an Insight summarizing the health of the clinical
data graph.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from src.agent_registry import register_agent
from src.agents.base_agent import BaseAgent, Insight
from src.services.relationship_auditor import compute_integrity_score

logger = logging.getLogger(__name__)


@register_agent
class RelationshipAuditorAgent(BaseAgent):
    """Database integrity — validates the FK graph rooted at patients/encounters."""

    name = "relationship_auditor"
    required_role = "ops"

    # ── Lifecycle ────────────────────────────────────────────────────────────

    def collect_data(self) -> Dict[str, Any]:
        return compute_integrity_score()

    def analyze(self, data: Dict[str, Any]) -> Dict[str, Any]:
        # compute_integrity_score already returns the fully-shaped audit
        return data

    def generate_insights(self, analysis: Dict[str, Any]) -> Insight:
        findings: list[str] = []
        risks: list[str] = []
        recommendations: list[str] = []

        findings.append(
            f"Overall integrity score: {analysis['overall_score']} "
            f"({analysis['fk_edge_count']} FK relationships audited)."
        )
        findings.append(
            f"Mean relationship coverage: {analysis['mean_relationship_coverage_pct']}% "
            f"across the patient/encounter graph."
        )

        if analysis["total_patient_encounter_mismatches"] == 0:
            findings.append("Zero patient/encounter cross-reference mismatches — the encounter-key collision class of bug is clear.")
        else:
            risks.append(
                f"{analysis['total_patient_encounter_mismatches']} rows point to an encounter "
                "belonging to a different patient — the encounter-key collision bug may have "
                "recurred. Re-run data-assimilation/scripts/repair_shared_encounter_keys.py."
            )
            recommendations.append("Re-run the encounter repair script and check for un-prefixed encounter keys in recent syncs.")

        if analysis["total_orphans"] == 0:
            findings.append("Zero orphaned FK references detected.")
        else:
            for o in analysis["orphan_counts"]:
                if o.get("orphan_count"):
                    risks.append(
                        f"{o['orphan_count']} orphaned rows in {o['referencing_table']}.{o['referencing_column']} "
                        f"(→ {o['referenced_table']})."
                    )
            recommendations.append("Investigate orphaned rows — likely a NOT VALID constraint hiding unvalidated legacy data.")

        low_coverage = [
            c for c in analysis["relationship_coverage"]
            if c["coverage_pct"] is not None and c["coverage_pct"] < 50 and (c["total_rows"] or 0) > 0
        ]
        for c in low_coverage[:5]:
            findings.append(
                f"Low linkage: only {c['coverage_pct']}% of {c['referencing_table']} rows have "
                f"{c['referencing_column']} populated ({c['linked_rows']}/{c['total_rows']})."
            )

        if not risks:
            risks.append("No integrity risks detected in the clinical data graph.")
        if not recommendations:
            recommendations.append("Schedule this audit to run after every Hope sync or bulk import.")

        return Insight(
            metrics={
                "overall_score": analysis["overall_score"],
                "orphan_health": analysis["orphan_health"],
                "cardinality_health": analysis["cardinality_health"],
                "mean_relationship_coverage_pct": analysis["mean_relationship_coverage_pct"],
                "total_orphans": analysis["total_orphans"],
                "total_patient_encounter_mismatches": analysis["total_patient_encounter_mismatches"],
                "fk_edge_count": analysis["fk_edge_count"],
            },
            findings=findings,
            risks=risks,
            recommendations=recommendations,
            confidence_score=0.9,
            supporting_refs=[
                {"type": "relationship_coverage", "data": analysis["relationship_coverage"]},
                {"type": "cardinality_violations", "data": analysis["cardinality_violations"]},
            ],
        )

    def write_cache(self, insight: Insight) -> None:
        try:
            from src.routers.cache_ui import get_shared_cache
            cache = get_shared_cache()
            cache.set(self.name, insight, ttl=3600)
        except Exception as exc:
            logger.warning("relationship_auditor: cache write failed: %s", exc)

    def get_output_schema(self) -> Dict[str, Any]:
        return {
            "overall_score": "float",
            "orphan_health": "float",
            "cardinality_health": "float",
            "mean_relationship_coverage_pct": "float",
            "total_orphans": "int",
            "total_patient_encounter_mismatches": "int",
            "fk_edge_count": "int",
        }
