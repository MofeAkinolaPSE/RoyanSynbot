"""
Patient Flow Agent — RoyanHealth / Royan Hospital
====================================================
Monitors the real-time patient queue across the clinical workflow:
  patient_registered → triaged → consulting → lab_ordered → pharmacy_dispensing → billing_pending → discharged

Surfaces:
  - Bottleneck stages (encounters stalled > threshold minutes)
  - Triage delay alerts
  - Department queue depths
  - Average wait time by stage
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List

from src.agent_registry import register_agent
from src.agents.base_agent import BaseAgent, Insight
from src.constants import TABLE_ENCOUNTERS

logger = logging.getLogger(__name__)

# Minutes threshold before a stage is considered "stalled"
STAGE_STALL_THRESHOLDS: Dict[str, int] = {
    "patient_registered": 30,
    "triaged":            60,
    "consulting":         120,
    "lab_ordered":        180,
    "pharmacy_dispensing": 60,
    "billing_pending":    90,
}


@register_agent
class PatientFlowAgent(BaseAgent):
    name = "patient_flow_agent"
    required_role = "ops"

    # ------------------------------------------------------------------
    # collect_data: pull today's open encounters from DB
    # ------------------------------------------------------------------
    def collect_data(self) -> Dict[str, Any]:
        try:
            from src.db import db
            result = db.table(TABLE_ENCOUNTERS).select(
                "id", "patient_id", "status", "department",
                "encounter_type", "created_at", "triage_at", "consultation_at"
            ).neq("status", "discharged").order("created_at").execute()
            return {"encounters": result.data or []}
        except Exception as exc:
            logger.error("PatientFlowAgent.collect_data failed: %s", exc)
            return {"encounters": []}

    # ------------------------------------------------------------------
    # analyze: compute queue depths, stall counts, avg wait times
    # ------------------------------------------------------------------
    def analyze(self, data: Dict[str, Any]) -> Dict[str, Any]:
        encounters: List[Dict[str, Any]] = data.get("encounters") or []
        now = datetime.now(timezone.utc)

        stage_counts: Dict[str, int] = {}
        stalled: List[Dict[str, Any]] = []
        total_wait_mins: Dict[str, float] = {}
        wait_counts: Dict[str, int] = {}

        for enc in encounters:
            status = enc.get("status") or "unknown"
            stage_counts[status] = stage_counts.get(status, 0) + 1

            # Compute age in this stage (from created_at as proxy)
            created_raw = enc.get("created_at")
            if created_raw:
                try:
                    if isinstance(created_raw, str):
                        created_raw = created_raw.replace("Z", "+00:00")
                        created_dt = datetime.fromisoformat(created_raw)
                    else:
                        created_dt = created_raw
                    if created_dt.tzinfo is None:
                        created_dt = created_dt.replace(tzinfo=timezone.utc)
                    age_mins = (now - created_dt).total_seconds() / 60
                except Exception:
                    age_mins = 0.0
            else:
                age_mins = 0.0

            threshold = STAGE_STALL_THRESHOLDS.get(status, 120)
            if age_mins > threshold:
                stalled.append({
                    "encounter_id": enc.get("id"),
                    "patient_id": enc.get("patient_id"),
                    "status": status,
                    "department": enc.get("department"),
                    "age_mins": round(age_mins, 1),
                })

            total_wait_mins[status] = total_wait_mins.get(status, 0.0) + age_mins
            wait_counts[status] = wait_counts.get(status, 0) + 1

        avg_wait: Dict[str, float] = {
            s: round(total_wait_mins[s] / wait_counts[s], 1)
            for s in total_wait_mins
            if wait_counts.get(s)
        }

        # Identify worst bottleneck stage
        bottleneck = max(stage_counts, key=lambda s: stage_counts[s]) if stage_counts else None

        return {
            "total_active": len(encounters),
            "stage_counts": stage_counts,
            "stalled": stalled,
            "avg_wait_mins": avg_wait,
            "bottleneck_stage": bottleneck,
        }

    # ------------------------------------------------------------------
    # generate_insights
    # ------------------------------------------------------------------
    def generate_insights(self, analysis: Dict[str, Any]) -> Insight:
        insight = Insight()
        total = analysis.get("total_active", 0)
        stage_counts = analysis.get("stage_counts") or {}
        stalled = analysis.get("stalled") or []
        avg_wait = analysis.get("avg_wait_mins") or {}
        bottleneck = analysis.get("bottleneck_stage")

        insight.metrics = {
            "total_active_encounters": total,
            "stalled_count": len(stalled),
            "stage_counts": stage_counts,
            "avg_wait_mins": avg_wait,
            "bottleneck_stage": bottleneck,
        }

        if total == 0:
            insight.findings.append("No active patient encounters at this time.")
            insight.confidence_score = 0.95
            return insight

        insight.findings.append(f"{total} active encounter(s) in the clinical queue.")

        if bottleneck:
            depth = stage_counts.get(bottleneck, 0)
            insight.findings.append(
                f"Stage bottleneck: '{bottleneck}' has the most patients ({depth})."
            )

        if stalled:
            insight.risks.append(
                f"{len(stalled)} encounter(s) have exceeded stage wait-time thresholds "
                f"(e.g., {stalled[0]['department']} — {stalled[0]['age_mins']} min)."
            )
            insight.recommendations.append(
                "Review and escalate stalled encounters. Notify the relevant department head."
            )

        triage_wait = avg_wait.get("patient_registered", 0)
        if triage_wait > 45:
            insight.risks.append(
                f"Average pre-triage wait is {triage_wait} min — A&E triage protocol may need reinforcement."
            )

        if not stalled and total < 20:
            insight.findings.append("Patient flow is within normal operating parameters.")

        insight.recommendations.append(
            "Run /queue/encounters?status=billing_pending to clear patients waiting for billing."
        )
        insight.supporting_refs = stalled[:10]
        insight.confidence_score = 0.87

        return insight

    def write_cache(self, insight: Insight) -> None:
        cache = self.context.get("cache")
        if cache:
            cache.set(self.name, insight, ttl=int(self.context.get("cache_ttl_seconds", 120)))

    def get_output_schema(self) -> Dict[str, Any]:
        return {
            "total_active_encounters": "int",
            "stalled_count": "int",
            "stage_counts": "dict",
            "avg_wait_mins": "dict",
            "bottleneck_stage": "str",
            "findings": "list",
            "risks": "list",
            "recommendations": "list",
        }
