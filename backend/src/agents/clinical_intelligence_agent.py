"""Clinical Intelligence Agent — Chapter 12 / Phase 10 (Knowledge Layer).

Enterprise-grade situational awareness agent that consumes the canonical
aggregate endpoints (not raw DB tables) and synthesises multi-domain
clinical intelligence:

  Domain signals consumed:
    - Queue overview  → patient flow, wait-time pressure
    - Clinical KPIs   → lab TAT, bed occupancy, ward census
    - Data quality    → completeness live scores
    - Revenue snapshot → financial health

  Output Insight includes:
    - Operational risk score (0–1)
    - Cross-domain bottleneck detection
    - Capacity alert recommendations
    - 24-hour trend narrative

The agent is intentionally stateless: it calls existing `/api/v1/ops/*`
endpoints via the internal base URL rather than duplicating SQL, ensuring
a single source of truth for clinical metrics.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from src.agent_registry import register_agent
from src.agents.base_agent import BaseAgent, Insight

logger = logging.getLogger(__name__)

_INTELLIGENCE_INSTRUCTION = """You are ICOP (Intelligent Clinical Operations Platform) for a Nigerian tertiary hospital.
Analyse the following multi-domain clinical operations snapshot and provide:

1. EXECUTIVE SUMMARY: 2-sentence overall operational status.
2. KEY RISKS: Bullet list of the top 3 risks identified.
3. BOTTLENECKS: Which department/domain is the primary constraint right now?
4. RECOMMENDATIONS: 3 specific, actionable recommendations for the next 4 hours.

Be direct and clinical. Use numbers from the data. Do not exceed 300 words."""


@register_agent
class ClinicalIntelligenceAgent(BaseAgent):
    """Synthesises real-time multi-domain clinical intelligence from canonical APIs."""

    name = "clinical_intelligence_agent"
    required_role = "ops"

    # ------------------------------------------------------------------
    # collect_data — call canonical obs endpoints (internal HTTP)
    # ------------------------------------------------------------------
    def collect_data(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {}
        try:
            import os, requests
            base = os.getenv("APP_BASE_URL", "http://localhost:8000").rstrip("/")
            headers = self._internal_auth_header()

            endpoints = {
                "clinical_kpis":      f"{base}/api/v1/ops/clinical-kpis",
                "workflow":           f"{base}/api/v1/ops/workflow-performance",
                "data_quality":       f"{base}/api/v1/ops/data-quality-live",
                "bed_census":         f"{base}/api/v1/ops/bed-census",
                "lab_performance":    f"{base}/api/v1/ops/lab-performance",
                "revenue":            f"{base}/api/v1/ops/revenue-snapshot",
                "queue_overview":     f"{base}/api/v1/queue/overview",
            }

            for key, url in endpoints.items():
                try:
                    r = requests.get(url, headers=headers, timeout=10)
                    if r.status_code == 200:
                        data[key] = r.json()
                    else:
                        logger.warning("ClinicalIntelligence: %s returned %s", key, r.status_code)
                        data[key] = {}
                except Exception as req_exc:
                    logger.warning("ClinicalIntelligence: %s unreachable: %s", key, req_exc)
                    data[key] = {}

        except Exception as exc:
            logger.error("ClinicalIntelligenceAgent.collect_data failed: %s", exc)

        return data

    # ------------------------------------------------------------------
    # analyze — derive operational risk score + bottleneck identification
    # ------------------------------------------------------------------
    def analyze(self, data: Dict[str, Any]) -> Dict[str, Any]:
        kpis         = data.get("clinical_kpis") or {}
        workflow     = data.get("workflow") or {}
        quality      = data.get("data_quality") or {}
        bed_census   = data.get("bed_census") or {}
        lab_perf     = data.get("lab_performance") or {}
        revenue      = data.get("revenue") or {}
        queue        = data.get("queue_overview") or {}

        risk_signals: List[str] = []
        risk_score = 0.0
        risk_weight = 0.0

        # ── Queue pressure ────────────────────────────────────────────
        queue_depts = queue.get("departments") or []
        max_wait = 0
        congested_depts: List[str] = []
        for dept in queue_depts:
            w = dept.get("avg_wait_minutes") or 0
            if w > max_wait:
                max_wait = w
            if w > 60:
                congested_depts.append(dept.get("department", "Unknown"))
        if max_wait > 120:
            risk_score += 0.25; risk_weight += 0.25
            risk_signals.append(f"Critical queue wait: {max_wait} min in {', '.join(congested_depts)}")
        elif max_wait > 60:
            risk_score += 0.12; risk_weight += 0.25
            risk_signals.append(f"Elevated queue wait: {max_wait} min")

        # ── Bed occupancy ─────────────────────────────────────────────
        beds = bed_census.get("wards") or []
        total_beds = sum(w.get("total", 0) for w in beds)
        occupied   = sum(w.get("occupied", 0) for w in beds)
        occupancy_pct = (occupied / total_beds * 100) if total_beds > 0 else 0
        if occupancy_pct >= 95:
            risk_score += 0.25; risk_weight += 0.25
            risk_signals.append(f"Bed occupancy critical: {occupancy_pct:.1f}%")
        elif occupancy_pct >= 85:
            risk_score += 0.10; risk_weight += 0.25
            risk_signals.append(f"Bed occupancy high: {occupancy_pct:.1f}%")

        # ── Lab TAT pressure ──────────────────────────────────────────
        overdue_stat  = kpis.get("stat_lab_overdue", 0)
        overdue_urgent = kpis.get("urgent_lab_overdue", 0)
        if overdue_stat:
            risk_score += 0.20; risk_weight += 0.20
            risk_signals.append(f"{overdue_stat} STAT lab orders overdue — patient safety risk")
        elif overdue_urgent:
            risk_score += 0.08; risk_weight += 0.20
            risk_signals.append(f"{overdue_urgent} URGENT lab orders overdue")

        # ── Data quality ──────────────────────────────────────────────
        q_scores = quality.get("domain_scores") or {}
        low_quality_domains = [d for d, s in q_scores.items() if isinstance(s, (int, float)) and s < 0.7]
        if low_quality_domains:
            risk_signals.append(f"Data quality below 70%: {', '.join(low_quality_domains)}")

        # ── Revenue health ────────────────────────────────────────────
        rev = revenue.get("summary") or {}
        collection_rate = rev.get("collection_rate_pct", 100)
        if collection_rate < 60:
            risk_signals.append(f"Revenue collection rate low: {collection_rate:.1f}%")

        # Normalise risk score to 0-1
        normalized_risk = min(risk_score, 1.0)

        # Bottleneck detection — which domain is worst
        bottleneck = "None identified"
        if overdue_stat:
            bottleneck = "Laboratory (STAT overdue)"
        elif occupancy_pct >= 95:
            bottleneck = "Ward capacity"
        elif max_wait > 120:
            bottleneck = f"OPD queue ({', '.join(congested_depts)})"
        elif collection_rate < 60:
            bottleneck = "Revenue / billing"

        return {
            "risk_score": round(normalized_risk, 3),
            "risk_signals": risk_signals,
            "bottleneck": bottleneck,
            "max_queue_wait_min": max_wait,
            "bed_occupancy_pct": round(occupancy_pct, 1),
            "overdue_stat_labs": overdue_stat,
            "overdue_urgent_labs": overdue_urgent,
            "low_quality_domains": low_quality_domains,
            "collection_rate_pct": collection_rate,
            "context_text": self._build_context_text(data, {
                "risk_score": round(normalized_risk, 3),
                "bottleneck": bottleneck,
                "max_queue_wait_min": max_wait,
                "bed_occupancy_pct": round(occupancy_pct, 1),
                "overdue_stat_labs": overdue_stat,
                "collection_rate_pct": collection_rate,
            }),
        }

    # ------------------------------------------------------------------
    # generate_insights — LLM narrative + structured Insight
    # ------------------------------------------------------------------
    def generate_insights(self, analysis: Dict[str, Any]) -> Insight:
        insight = Insight()
        risk     = analysis.get("risk_score", 0.0)
        signals  = analysis.get("risk_signals") or []
        bottleneck = analysis.get("bottleneck", "None")

        # Metrics
        insight.metrics = {
            "operational_risk_score":   risk,
            "bottleneck":               bottleneck,
            "max_queue_wait_min":       analysis.get("max_queue_wait_min"),
            "bed_occupancy_pct":        analysis.get("bed_occupancy_pct"),
            "overdue_stat_labs":        analysis.get("overdue_stat_labs"),
            "overdue_urgent_labs":      analysis.get("overdue_urgent_labs"),
            "collection_rate_pct":      analysis.get("collection_rate_pct"),
            "low_quality_domains":      analysis.get("low_quality_domains"),
            "assessed_at":              datetime.utcnow().isoformat(),
        }

        # Findings from risk signals
        insight.findings = signals or ["All operational domains within normal parameters."]

        # Risk → narrative
        if risk >= 0.5:
            insight.risks.append(f"High operational risk ({risk:.0%}). Immediate management attention required.")
        elif risk >= 0.25:
            insight.risks.append(f"Moderate operational risk ({risk:.0%}). Monitor closely.")
        else:
            insight.risks.append(f"Low operational risk ({risk:.0%}). Operations proceeding normally.")

        # Recommendations from analysis
        if analysis.get("overdue_stat_labs"):
            insight.recommendations.append(
                "Escalate overdue STAT lab orders to lab supervisor immediately.")
        if analysis.get("bed_occupancy_pct", 0) >= 90:
            insight.recommendations.append(
                "Activate bed management protocol — consider expediting discharge reviews.")
        if analysis.get("max_queue_wait_min", 0) > 60:
            insight.recommendations.append(
                "Deploy additional triage staff or open overflow clinic to reduce wait times.")
        if analysis.get("low_quality_domains"):
            insight.recommendations.append(
                "Run enrichment pipeline to improve data completeness in flagged domains.")
        if not insight.recommendations:
            insight.recommendations.append("Maintain current operational tempo; review again in 2 hours.")

        # LLM narrative
        ctx = analysis.get("context_text", "")
        if ctx:
            try:
                from src.llm_client import LLMClient
                llm = LLMClient()
                narrative = llm.generate_response(
                    context=ctx,
                    question="Provide a clinical intelligence brief for hospital management.",
                    instruction=_INTELLIGENCE_INSTRUCTION,
                )
                if narrative:
                    insight.supporting_refs = [{"intelligence_brief": narrative}]
            except Exception as exc:
                logger.warning("ClinicalIntelligenceAgent LLM call failed: %s", exc)

        # Confidence: higher when we have actual data
        insight.confidence_score = 0.92 if ctx else 0.55
        return insight

    # ------------------------------------------------------------------
    # write_cache
    # ------------------------------------------------------------------
    def write_cache(self, insight: Insight) -> None:
        cache = self.context.get("cache")
        if cache:
            cache.set(self.name, insight, ttl=int(self.context.get("cache_ttl_seconds", 180)))

    def get_output_schema(self) -> Dict[str, Any]:
        return {
            "operational_risk_score":   "float (0–1)",
            "bottleneck":               "str",
            "max_queue_wait_min":       "int",
            "bed_occupancy_pct":        "float",
            "overdue_stat_labs":        "int",
            "collection_rate_pct":      "float",
            "low_quality_domains":      "list[str]",
            "findings":                 "list[str]",
            "risks":                    "list[str]",
            "recommendations":          "list[str]",
            "intelligence_brief":       "str (in supporting_refs[0])",
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------
    def _internal_auth_header(self) -> Dict[str, str]:
        """Forge a short-lived system token for internal API calls."""
        try:
            import time, jwt
            from src.constants import JWT_SECRET
            token = jwt.encode(
                {
                    "sub": "clinical_intelligence_agent",
                    "roles": ["ops", "admin"],
                    "iat": int(time.time()),
                    "exp": int(time.time()) + 60,
                },
                JWT_SECRET,
                algorithm="HS256",
            )
            return {"Authorization": f"Bearer {token}"}
        except Exception:
            return {}

    def _build_context_text(self, data: Dict, summary: Dict) -> str:
        lines: List[str] = [
            f"OPERATIONAL SNAPSHOT — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
            f"Risk Score: {summary.get('risk_score', 0):.0%}  |  "
            f"Bottleneck: {summary.get('bottleneck', 'None')}",
            "",
        ]

        kpis = data.get("clinical_kpis") or {}
        if kpis:
            lines.append("CLINICAL KPIs:")
            for k, v in kpis.items():
                lines.append(f"  {k}: {v}")
            lines.append("")

        queue = data.get("queue_overview") or {}
        depts = queue.get("departments") or []
        if depts:
            lines.append("QUEUE BY DEPARTMENT:")
            for d in depts:
                lines.append(f"  {d.get('department','?')}: {d.get('active_encounters',0)} patients, "
                             f"avg wait {d.get('avg_wait_minutes',0):.0f} min")
            lines.append("")

        census = data.get("bed_census") or {}
        wards = census.get("wards") or []
        if wards:
            lines.append("BED CENSUS:")
            for w in wards:
                lines.append(f"  {w.get('ward','?')}: {w.get('occupied',0)}/{w.get('total',0)} occupied")
            lines.append("")

        rev = data.get("revenue") or {}
        if rev:
            lines.append(f"REVENUE: {rev}")
            lines.append("")

        return "\n".join(lines)
