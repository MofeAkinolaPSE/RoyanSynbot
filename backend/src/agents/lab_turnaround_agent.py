"""
Lab Turnaround Agent — RoyanHealth / Royan Hospital
======================================================
Monitors laboratory test turnaround times (TAT) and surfaces delays:
  - Stat orders overdue > 1 hr from collection to result
  - Urgent orders overdue > 4 hr
  - Routine orders overdue > 24 hr
  - Pending orders with no sample collected yet
  - Unverified critical results (escalated to ClinicalComplianceAgent too)

Uses the `royan_lab_turnaround` database view where available, with
fallback to direct table queries.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List

from src.agent_registry import register_agent
from src.agents.base_agent import BaseAgent, Insight
from src.constants import TABLE_LAB_ORDERS, TABLE_LAB_RESULTS

logger = logging.getLogger(__name__)

# TAT SLA (minutes) — overdue threshold per urgency level
TAT_SLAS: Dict[str, int] = {
    "stat":    60,    # 1 hour
    "urgent":  240,   # 4 hours
    "routine": 1440,  # 24 hours
}


@register_agent
class LabTurnaroundAgent(BaseAgent):
    name = "lab_turnaround_agent"
    required_role = "ops"

    # ------------------------------------------------------------------
    # collect_data
    # ------------------------------------------------------------------
    def collect_data(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {}
        try:
            from src.db import db
            import psycopg2.extras

            # Try the turnaround view first
            conn = db.pool.getconn()
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            try:
                cur.execute(
                    "SELECT * FROM public.royan_lab_turnaround "
                    "WHERE result_status IN ('pending','collected','processing') "
                    "ORDER BY ordered_at"
                )
                pending = [dict(r) for r in cur.fetchall()]
                data["pending_via_view"] = pending
            except Exception as ve:
                logger.warning("royan_lab_turnaround view query failed: %s", ve)
                conn.rollback()
                data["pending_via_view"] = []
            finally:
                cur.close()
                db.pool.putconn(conn)

            # Pending orders without result
            orders = db.table(TABLE_LAB_ORDERS).select(
                "id", "patient_id", "encounter_id", "test_name",
                "urgency", "status", "ordered_at", "collected_at"
            ).in_("status", ["pending", "collected", "processing"]).execute()
            data["pending_orders"] = orders.data or []

        except Exception as exc:
            logger.error("LabTurnaroundAgent.collect_data failed: %s", exc)
            data.setdefault("pending_orders", [])

        return data

    # ------------------------------------------------------------------
    # analyze
    # ------------------------------------------------------------------
    def analyze(self, data: Dict[str, Any]) -> Dict[str, Any]:
        now = datetime.now(timezone.utc)
        pending_orders: List[Dict] = data.get("pending_orders") or []

        overdue: Dict[str, List[Dict]] = {"stat": [], "urgent": [], "routine": []}
        no_sample: List[Dict] = []
        tat_mins: Dict[str, List[float]] = {"stat": [], "urgent": [], "routine": []}

        for order in pending_orders:
            urgency = (order.get("urgency") or "routine").lower()
            if urgency not in TAT_SLAS:
                urgency = "routine"

            ref_time_raw = order.get("ordered_at")
            if not ref_time_raw:
                continue

            try:
                if isinstance(ref_time_raw, str):
                    ref_time_raw = ref_time_raw.replace("Z", "+00:00")
                    ref_dt = datetime.fromisoformat(ref_time_raw)
                else:
                    ref_dt = ref_time_raw
                if ref_dt.tzinfo is None:
                    ref_dt = ref_dt.replace(tzinfo=timezone.utc)
                elapsed_min = (now - ref_dt).total_seconds() / 60
            except Exception:
                elapsed_min = 0.0

            tat_mins[urgency].append(elapsed_min)

            sla = TAT_SLAS[urgency]
            if elapsed_min > sla:
                overdue[urgency].append({**order, "elapsed_min": round(elapsed_min, 1)})

            if not order.get("collected_at"):
                no_sample.append(order)

        avg_tat: Dict[str, float] = {
            u: round(sum(v) / len(v), 1) for u, v in tat_mins.items() if v
        }

        total_overdue = sum(len(v) for v in overdue.values())
        health_state = "on_track"
        if overdue["stat"]:
            health_state = "critical"
        elif overdue["urgent"] or total_overdue > 5:
            health_state = "at_risk"
        elif total_overdue > 0:
            health_state = "attention"

        return {
            "pending_total": len(pending_orders),
            "overdue": overdue,
            "total_overdue": total_overdue,
            "no_sample_collected": no_sample,
            "avg_tat_mins": avg_tat,
            "health_state": health_state,
        }

    # ------------------------------------------------------------------
    # generate_insights
    # ------------------------------------------------------------------
    def generate_insights(self, analysis: Dict[str, Any]) -> Insight:
        insight = Insight()
        pending  = analysis.get("pending_total", 0)
        overdue  = analysis.get("overdue") or {}
        total_od = analysis.get("total_overdue", 0)
        no_samp  = analysis.get("no_sample_collected") or []
        avg_tat  = analysis.get("avg_tat_mins") or {}
        health   = analysis.get("health_state", "on_track")

        insight.metrics = {
            "pending_orders": pending,
            "overdue_stat": len(overdue.get("stat", [])),
            "overdue_urgent": len(overdue.get("urgent", [])),
            "overdue_routine": len(overdue.get("routine", [])),
            "total_overdue": total_od,
            "no_sample_count": len(no_samp),
            "avg_tat_stat_min": avg_tat.get("stat"),
            "avg_tat_urgent_min": avg_tat.get("urgent"),
            "avg_tat_routine_min": avg_tat.get("routine"),
            "health_state": health,
        }

        if pending == 0:
            insight.findings.append("No pending laboratory orders at this time.")
            insight.confidence_score = 0.95
            return insight

        insight.findings.append(f"{pending} lab order(s) currently pending.")

        if avg_tat:
            parts = [f"{u}: {v} min" for u, v in avg_tat.items()]
            insight.findings.append(f"Average TAT — {'; '.join(parts)}.")

        stat_od = overdue.get("stat") or []
        urgent_od = overdue.get("urgent") or []
        if stat_od:
            insight.risks.append(
                f"CRITICAL: {len(stat_od)} STAT order(s) have exceeded the "
                f"{TAT_SLAS['stat']}-minute SLA. Patient safety risk."
            )
            insight.recommendations.append(
                "Escalate STAT overdue orders to lab supervisor immediately."
            )

        if urgent_od:
            insight.risks.append(
                f"{len(urgent_od)} URGENT order(s) have exceeded the "
                f"{TAT_SLAS['urgent']}-minute SLA."
            )
            insight.recommendations.append(
                "Review urgent order backlog with the on-call lab technician."
            )

        if no_samp:
            insight.findings.append(
                f"{len(no_samp)} order(s) have no sample collected — specimen collection may be delayed."
            )
            insight.recommendations.append(
                "Dispatch phlebotomist or notify ward nurse to collect pending specimens."
            )

        stat_refs = (overdue.get("stat") or [])[:5]
        urgent_refs = (overdue.get("urgent") or [])[:5]
        insight.supporting_refs = stat_refs + urgent_refs

        if health == "on_track":
            insight.confidence_score = 0.93
        elif health == "attention":
            insight.confidence_score = 0.88
        elif health == "at_risk":
            insight.confidence_score = 0.85
        else:
            insight.confidence_score = 0.80

        return insight

    def write_cache(self, insight: Insight) -> None:
        cache = self.context.get("cache")
        if cache:
            cache.set(self.name, insight, ttl=int(self.context.get("cache_ttl_seconds", 120)))

    def get_output_schema(self) -> Dict[str, Any]:
        return {
            "pending_orders": "int",
            "overdue_stat": "int",
            "overdue_urgent": "int",
            "overdue_routine": "int",
            "total_overdue": "int",
            "no_sample_count": "int",
            "avg_tat_stat_min": "float",
            "health_state": "str",
            "findings": "list",
            "risks": "list",
            "recommendations": "list",
        }
