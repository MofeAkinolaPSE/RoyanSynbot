"""
Clinical Compliance Agent — SynbotHealth / Royan Hospital
===========================================================
Monitors clinical documentation and regulatory compliance signals:
  - NDPA 2023 (Nigeria Data Protection Act) — patient data handling
  - Unverified critical lab results (must be communicated within 1 hr)
  - Encounters missing triage documentation
  - Prescriptions without counselling sign-off
  - Discharge summaries not completed within 24 hrs

The agent surfaces gaps as ordered risks with remediation guidance.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List

from src.agent_registry import register_agent
from src.agents.base_agent import BaseAgent, Insight
from src.constants import (
    TABLE_ENCOUNTERS,
    TABLE_LAB_RESULTS,
    TABLE_PRESCRIPTIONS,
)

logger = logging.getLogger(__name__)

# SLA thresholds
CRITICAL_RESULT_NOTIFY_MINUTES = 60    # Unverified critical result SLA
DISCHARGE_SUMMARY_HOURS         = 24   # Discharge summary completion SLA


@register_agent
class ClinicalComplianceAgent(BaseAgent):
    name = "clinical_compliance_agent"
    required_role = "ops"

    # ------------------------------------------------------------------
    # collect_data
    # ------------------------------------------------------------------
    def collect_data(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {}
        try:
            from src.db import db

            # 1. Unverified critical lab results
            critical_unverified = db.table(TABLE_LAB_RESULTS).select(
                "id", "order_id", "result_status", "is_critical", "resulted_at"
            ).eq("is_critical", True).eq("result_status", "resulted").execute()
            data["critical_unverified"] = critical_unverified.data or []

            # 2. Discharged encounters missing discharge_summary
            discharged_no_summary = db.table(TABLE_ENCOUNTERS).select(
                "id", "patient_id", "discharged_at", "department"
            ).eq("status", "discharged").is_("discharge_summary", "null").execute()
            data["discharged_no_summary"] = discharged_no_summary.data or []

            # 3. Encounters with no triage_at that are beyond triage stage
            missing_triage = db.table(TABLE_ENCOUNTERS).select(
                "id", "patient_id", "status", "department", "created_at"
            ).neq("status", "patient_registered").neq("status", "discharged").is_("triage_at", "null").execute()
            data["missing_triage"] = missing_triage.data or []

            # 4. Prescriptions without counselling flag
            uncounselled = db.table(TABLE_PRESCRIPTIONS).select(
                "id", "patient_id", "encounter_id", "prescribed_at", "counselled"
            ).eq("counselled", False).neq("status", "cancelled").execute()
            data["uncounselled_rx"] = uncounselled.data or []

        except Exception as exc:
            logger.error("ClinicalComplianceAgent.collect_data failed: %s", exc)

        return data

    # ------------------------------------------------------------------
    # analyze
    # ------------------------------------------------------------------
    def analyze(self, data: Dict[str, Any]) -> Dict[str, Any]:
        now = datetime.now(timezone.utc)

        critical_unverified: List[Dict] = data.get("critical_unverified") or []
        discharged_no_summary: List[Dict] = data.get("discharged_no_summary") or []
        missing_triage: List[Dict] = data.get("missing_triage") or []
        uncounselled_rx: List[Dict] = data.get("uncounselled_rx") or []

        # Critical results breaching 1-hr SLA
        critical_breaching: List[Dict] = []
        for r in critical_unverified:
            raw = r.get("resulted_at")
            if raw:
                try:
                    if isinstance(raw, str):
                        raw = raw.replace("Z", "+00:00")
                        dt = datetime.fromisoformat(raw)
                    else:
                        dt = raw
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    elapsed_min = (now - dt).total_seconds() / 60
                    if elapsed_min > CRITICAL_RESULT_NOTIFY_MINUTES:
                        critical_breaching.append({**r, "elapsed_min": round(elapsed_min, 1)})
                except Exception:
                    pass

        # Discharge summaries overdue (> 24 hrs post discharge)
        overdue_summaries: List[Dict] = []
        for enc in discharged_no_summary:
            raw = enc.get("discharged_at")
            if raw:
                try:
                    if isinstance(raw, str):
                        raw = raw.replace("Z", "+00:00")
                        dt = datetime.fromisoformat(raw)
                    else:
                        dt = raw
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    elapsed_hr = (now - dt).total_seconds() / 3600
                    if elapsed_hr > DISCHARGE_SUMMARY_HOURS:
                        overdue_summaries.append({**enc, "elapsed_hr": round(elapsed_hr, 1)})
                except Exception:
                    pass

        gap_count = (
            len(critical_breaching)
            + len(overdue_summaries)
            + len(missing_triage)
            + len(uncounselled_rx)
        )

        health_state = "compliant"
        if gap_count > 0:
            health_state = "gaps_detected"
        if len(critical_breaching) > 0:
            health_state = "critical_breach"

        return {
            "critical_breaching": critical_breaching,
            "overdue_summaries": overdue_summaries,
            "missing_triage": missing_triage,
            "uncounselled_rx": uncounselled_rx,
            "gap_count": gap_count,
            "health_state": health_state,
        }

    # ------------------------------------------------------------------
    # generate_insights
    # ------------------------------------------------------------------
    def generate_insights(self, analysis: Dict[str, Any]) -> Insight:
        insight = Insight()
        critical_b = analysis.get("critical_breaching") or []
        overdue_s  = analysis.get("overdue_summaries") or []
        miss_t     = analysis.get("missing_triage") or []
        uncounselled = analysis.get("uncounselled_rx") or []
        gap_count  = analysis.get("gap_count", 0)
        health_state = analysis.get("health_state", "compliant")

        insight.metrics = {
            "critical_result_breaches": len(critical_b),
            "overdue_discharge_summaries": len(overdue_s),
            "missing_triage_records": len(miss_t),
            "uncounselled_prescriptions": len(uncounselled),
            "total_compliance_gaps": gap_count,
            "health_state": health_state,
        }

        if health_state == "compliant":
            insight.findings.append(
                "All clinical compliance checks passed. No documentation gaps detected."
            )
            insight.confidence_score = 0.93
            return insight

        insight.findings.append(f"{gap_count} clinical compliance gap(s) detected.")

        if critical_b:
            insight.risks.append(
                f"CRITICAL: {len(critical_b)} unverified critical lab result(s) have exceeded the "
                f"{CRITICAL_RESULT_NOTIFY_MINUTES}-minute notification SLA. "
                "This is a patient safety risk and may breach NDPA 2023 § 25."
            )
            insight.recommendations.append(
                "Immediately notify the ordering clinician and verify/sign-off the critical result(s) via /lab/results."
            )

        if overdue_s:
            insight.risks.append(
                f"{len(overdue_s)} discharged patient(s) have no discharge summary after "
                f"{DISCHARGE_SUMMARY_HOURS} hours — clinical record gap and medico-legal risk."
            )
            insight.recommendations.append(
                "Assign responsible clinician to complete outstanding discharge summaries urgently."
            )

        if miss_t:
            insight.findings.append(
                f"{len(miss_t)} encounter(s) progressed past registration with no triage record — "
                "audit documentation gap."
            )

        if uncounselled:
            insight.findings.append(
                f"{len(uncounselled)} prescription(s) have no counselling sign-off recorded."
            )
            insight.recommendations.append(
                "Pharmacist should complete counselling documentation for outstanding prescriptions."
            )

        insight.supporting_refs = (critical_b + overdue_s)[:10]
        insight.confidence_score = 0.88 if health_state == "gaps_detected" else 0.82
        return insight

    def write_cache(self, insight: Insight) -> None:
        cache = self.context.get("cache")
        if cache:
            cache.set(self.name, insight, ttl=int(self.context.get("cache_ttl_seconds", 180)))

    def get_output_schema(self) -> Dict[str, Any]:
        return {
            "critical_result_breaches": "int",
            "overdue_discharge_summaries": "int",
            "missing_triage_records": "int",
            "uncounselled_prescriptions": "int",
            "total_compliance_gaps": "int",
            "health_state": "str",
            "findings": "list",
            "risks": "list",
            "recommendations": "list",
        }
