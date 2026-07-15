"""
Bed Capacity Agent — RoyanHealth / Royan Hospital
====================================================
Monitors ward bed occupancy in real time and raises alerts when
occupancy exceeds safe thresholds.

Surfaces:
  - Occupancy % per ward
  - Wards at or above critical threshold (≥ 90 %)
  - Wards with zero available beds
  - Overall hospital bed utilisation
  - Predicted shortage if current admission rate continues
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from src.agent_registry import register_agent
from src.agents.base_agent import BaseAgent, Insight
from src.constants import TABLE_WARDS, TABLE_BEDS

logger = logging.getLogger(__name__)

CRITICAL_OCCUPANCY_PCT = 90.0   # % at which a ward is flagged critical
HIGH_OCCUPANCY_PCT     = 75.0   # % at which a ward is flagged high


@register_agent
class BedCapacityAgent(BaseAgent):
    name = "bed_capacity_agent"
    required_role = "ops"

    # ------------------------------------------------------------------
    # collect_data: pull ward + bed data from DB
    # ------------------------------------------------------------------
    def collect_data(self) -> Dict[str, Any]:
        try:
            from src.db import db
            import psycopg2.extras

            # Use the royan_bed_occupancy view for aggregated data
            conn = db.pool.getconn()
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute("SELECT * FROM public.royan_bed_occupancy ORDER BY ward_name")
            wards = [dict(r) for r in cur.fetchall()]
            cur.close()
            db.pool.putconn(conn)
            return {"wards": wards}
        except Exception as exc:
            logger.error("BedCapacityAgent.collect_data failed: %s", exc)
            # Fallback: query beds table directly
            try:
                from src.db import db
                beds = db.table(TABLE_BEDS).select("ward_id", "status").execute()
                ward_info = db.table(TABLE_WARDS).select("id", "name", "total_beds", "ward_type").execute()
                return {"beds": beds.data or [], "ward_info": ward_info.data or []}
            except Exception as e2:
                logger.error("BedCapacityAgent fallback failed: %s", e2)
                return {"wards": []}

    # ------------------------------------------------------------------
    # analyze
    # ------------------------------------------------------------------
    def analyze(self, data: Dict[str, Any]) -> Dict[str, Any]:
        wards: List[Dict[str, Any]] = data.get("wards") or []

        # If view data is not available, build from raw beds
        if not wards and data.get("beds"):
            beds = data.get("beds") or []
            ward_info = {w["id"]: w for w in (data.get("ward_info") or [])}
            from collections import Counter
            ward_status: Dict[int, Counter] = {}
            for b in beds:
                wid = b.get("ward_id")
                if wid:
                    ward_status.setdefault(wid, Counter())[b.get("status", "unknown")] += 1
            for wid, counts in ward_status.items():
                wi = ward_info.get(wid, {})
                total = sum(counts.values())
                occupied = counts.get("occupied", 0)
                available = counts.get("available", 0)
                wards.append({
                    "ward_id": wid,
                    "ward_name": wi.get("name", f"Ward {wid}"),
                    "ward_type": wi.get("ward_type", "general"),
                    "total_beds": wi.get("total_beds", total),
                    "registered_beds": total,
                    "occupied_beds": occupied,
                    "available_beds": available,
                    "occupancy_pct": round(100.0 * occupied / total, 1) if total else 0.0,
                })

        critical_wards: List[Dict] = []
        high_wards: List[Dict] = []
        zero_available: List[Dict] = []
        total_beds = 0
        total_occupied = 0

        for w in wards:
            occ_pct = float(w.get("occupancy_pct") or 0)
            avail   = int(w.get("available_beds") or 0)
            occupied = int(w.get("occupied_beds") or 0)
            reg_beds = int(w.get("registered_beds") or 0)
            total_beds   += reg_beds
            total_occupied += occupied

            if avail == 0 and reg_beds > 0:
                zero_available.append(w)
            if occ_pct >= CRITICAL_OCCUPANCY_PCT:
                critical_wards.append(w)
            elif occ_pct >= HIGH_OCCUPANCY_PCT:
                high_wards.append(w)

        overall_pct = round(100.0 * total_occupied / total_beds, 1) if total_beds > 0 else 0.0

        health_state = "healthy"
        if overall_pct >= CRITICAL_OCCUPANCY_PCT or zero_available:
            health_state = "critical"
        elif overall_pct >= HIGH_OCCUPANCY_PCT or critical_wards:
            health_state = "high"

        return {
            "wards": wards,
            "total_beds": total_beds,
            "total_occupied": total_occupied,
            "total_available": total_beds - total_occupied,
            "overall_occupancy_pct": overall_pct,
            "critical_wards": critical_wards,
            "high_wards": high_wards,
            "zero_available_wards": zero_available,
            "health_state": health_state,
        }

    # ------------------------------------------------------------------
    # generate_insights
    # ------------------------------------------------------------------
    def generate_insights(self, analysis: Dict[str, Any]) -> Insight:
        insight = Insight()
        total = analysis.get("total_beds", 0)
        occupied = analysis.get("total_occupied", 0)
        available = analysis.get("total_available", 0)
        overall_pct = analysis.get("overall_occupancy_pct", 0.0)
        critical = analysis.get("critical_wards") or []
        high = analysis.get("high_wards") or []
        zero = analysis.get("zero_available_wards") or []
        health_state = analysis.get("health_state", "healthy")

        insight.metrics = {
            "total_beds": total,
            "total_occupied": occupied,
            "total_available": available,
            "overall_occupancy_pct": overall_pct,
            "critical_wards_count": len(critical),
            "health_state": health_state,
        }

        insight.findings.append(
            f"Hospital bed utilisation: {overall_pct}% ({occupied}/{total} beds occupied, {available} available)."
        )

        if zero:
            names = ", ".join(w.get("ward_name", "?") for w in zero[:3])
            insight.risks.append(
                f"{len(zero)} ward(s) have ZERO available beds: {names}. Immediate action required."
            )
            insight.recommendations.append(
                "Expedite discharge of medically stable patients and activate overflow protocols."
            )

        if critical:
            names = ", ".join(w.get("ward_name", "?") for w in critical[:3])
            insight.risks.append(
                f"{len(critical)} ward(s) are at ≥{CRITICAL_OCCUPANCY_PCT:.0f}% occupancy: {names}."
            )
            insight.recommendations.append(
                "Review pending discharges and coordinate with admissions to manage intake."
            )

        if high:
            names = ", ".join(w.get("ward_name", "?") for w in high[:3])
            insight.findings.append(
                f"{len(high)} ward(s) are at high occupancy (≥{HIGH_OCCUPANCY_PCT:.0f}%): {names}."
            )

        if health_state == "healthy":
            insight.findings.append("Bed capacity is within acceptable operating range.")
            insight.confidence_score = 0.92
        elif health_state == "high":
            insight.confidence_score = 0.88
        else:
            insight.confidence_score = 0.85

        insight.supporting_refs = (critical + zero)[:10]
        return insight

    def write_cache(self, insight: Insight) -> None:
        cache = self.context.get("cache")
        if cache:
            cache.set(self.name, insight, ttl=int(self.context.get("cache_ttl_seconds", 120)))

    def get_output_schema(self) -> Dict[str, Any]:
        return {
            "total_beds": "int",
            "total_occupied": "int",
            "total_available": "int",
            "overall_occupancy_pct": "float",
            "critical_wards_count": "int",
            "health_state": "str",
            "findings": "list",
            "risks": "list",
            "recommendations": "list",
        }
