"""
Billing Reconciliation Agent — RoyanHealth / Royan Hospital
=============================================================
Monitors hospital revenue collection and billing integrity:
  - Unpaid / partially paid bills and outstanding balances
  - HMO / insurance claim aging (submitted, pending, disputed)
  - Revenue leakage from waived amounts
  - Claims not submitted within 48 hrs of discharge
  - Dispute escalation triggers

Required role: `finance` — only accessible to finance staff.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List

from src.agent_registry import register_agent
from src.agents.base_agent import BaseAgent, Insight
from src.constants import TABLE_BILLING, TABLE_PAYMENTS, TABLE_INSURANCE_CLAIMS

logger = logging.getLogger(__name__)

CLAIM_SUBMISSION_SLA_HOURS = 48    # Submit HMO claim within 48 hrs of discharge
DISPUTE_AGING_DAYS         = 30    # Flag disputed claims older than 30 days


@register_agent
class BillingReconciliationAgent(BaseAgent):
    name = "billing_reconciliation_agent"
    required_role = "finance"

    # ------------------------------------------------------------------
    # collect_data
    # ------------------------------------------------------------------
    def collect_data(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {}
        try:
            from src.db import db

            # Unpaid and partially paid bills
            unpaid_bills = db.table(TABLE_BILLING).select(
                "id", "bill_number", "patient_id", "encounter_id",
                "subtotal", "paid_amount", "waived_amount",
                "billing_status", "billed_at"
            ).in_("billing_status", ["pending", "partial"]).execute()
            data["unpaid_bills"] = unpaid_bills.data or []

            # Insurance claims by status
            claims = db.table(TABLE_INSURANCE_CLAIMS).select(
                "id", "bill_id", "insurer_name", "claim_amount",
                "claim_status", "submitted_at", "approved_amount", "dispute_reason"
            ).execute()
            data["claims"] = claims.data or []

            # Recent waived amounts (last 30 days)
            waived = db.table(TABLE_BILLING).select(
                "id", "bill_number", "patient_id", "waived_amount", "waived_by", "billed_at"
            ).gt("waived_amount", 0).execute()
            data["waived_bills"] = waived.data or []

        except Exception as exc:
            logger.error("BillingReconciliationAgent.collect_data failed: %s", exc)

        return data

    # ------------------------------------------------------------------
    # analyze
    # ------------------------------------------------------------------
    def analyze(self, data: Dict[str, Any]) -> Dict[str, Any]:
        now = datetime.now(timezone.utc)
        unpaid_bills: List[Dict] = data.get("unpaid_bills") or []
        claims: List[Dict] = data.get("claims") or []
        waived_bills: List[Dict] = data.get("waived_bills") or []

        # Outstanding balance from unpaid bills
        total_outstanding = 0.0
        for bill in unpaid_bills:
            try:
                total_amt  = float(bill.get("subtotal") or 0)
                paid_amt   = float(bill.get("paid_amount") or 0)
                waived_amt = float(bill.get("waived_amount") or 0)
                total_outstanding += max(0.0, total_amt - paid_amt - waived_amt)
            except Exception:
                pass

        # Claim aging analysis
        pending_claims: List[Dict] = []
        disputed_claims: List[Dict] = []
        long_disputed: List[Dict] = []

        for c in claims:
            status = (c.get("claim_status") or "").lower()
            if status in ("submitted", "pending", "under_review"):
                pending_claims.append(c)
            elif status == "disputed":
                disputed_claims.append(c)
                raw = c.get("submitted_at")
                if raw:
                    try:
                        if isinstance(raw, str):
                            raw = raw.replace("Z", "+00:00")
                            dt = datetime.fromisoformat(raw)
                        else:
                            dt = raw
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=timezone.utc)
                        age_days = (now - dt).days
                        if age_days > DISPUTE_AGING_DAYS:
                            long_disputed.append({**c, "age_days": age_days})
                    except Exception:
                        pass

        total_claim_value = sum(float(c.get("claim_amount") or 0) for c in claims)
        pending_claim_value = sum(float(c.get("claim_amount") or 0) for c in pending_claims)
        disputed_claim_value = sum(float(c.get("claim_amount") or 0) for c in disputed_claims)

        total_waived = sum(float(b.get("waived_amount") or 0) for b in waived_bills)

        health_state = "healthy"
        if long_disputed or total_outstanding > 1_000_000:
            health_state = "at_risk"
        elif disputed_claims or total_outstanding > 500_000:
            health_state = "attention"

        return {
            "total_unpaid_bills": len(unpaid_bills),
            "total_outstanding": round(total_outstanding, 2),
            "pending_claims_count": len(pending_claims),
            "pending_claims_value": round(pending_claim_value, 2),
            "disputed_claims_count": len(disputed_claims),
            "disputed_claims_value": round(disputed_claim_value, 2),
            "long_disputed_claims": long_disputed,
            "total_waived": round(total_waived, 2),
            "total_claim_value": round(total_claim_value, 2),
            "unpaid_bills": unpaid_bills[:20],
            "health_state": health_state,
        }

    # ------------------------------------------------------------------
    # generate_insights
    # ------------------------------------------------------------------
    def generate_insights(self, analysis: Dict[str, Any]) -> Insight:
        insight = Insight()

        unpaid_count    = analysis.get("total_unpaid_bills", 0)
        outstanding     = analysis.get("total_outstanding", 0.0)
        pend_claims     = analysis.get("pending_claims_count", 0)
        pend_val        = analysis.get("pending_claims_value", 0.0)
        disp_count      = analysis.get("disputed_claims_count", 0)
        disp_val        = analysis.get("disputed_claims_value", 0.0)
        long_disp       = analysis.get("long_disputed_claims") or []
        total_waived    = analysis.get("total_waived", 0.0)
        health          = analysis.get("health_state", "healthy")

        insight.metrics = {
            "total_unpaid_bills": unpaid_count,
            "total_outstanding_ngn": outstanding,
            "pending_claims_count": pend_claims,
            "pending_claims_value_ngn": pend_val,
            "disputed_claims_count": disp_count,
            "disputed_claims_value_ngn": disp_val,
            "long_disputed_count": len(long_disp),
            "total_waived_ngn": total_waived,
            "health_state": health,
        }

        insight.findings.append(
            f"{unpaid_count} bill(s) with a combined outstanding balance of ₦{outstanding:,.2f}."
        )

        if pend_claims > 0:
            insight.findings.append(
                f"{pend_claims} HMO/insurance claim(s) pending adjudication — "
                f"total value ₦{pend_val:,.2f}."
            )

        if disp_count > 0:
            insight.risks.append(
                f"{disp_count} disputed HMO claim(s) worth ₦{disp_val:,.2f} require resolution."
            )
            insight.recommendations.append(
                "Assign billing team to review disputed claims and prepare supporting documentation."
            )

        if long_disp:
            insight.risks.append(
                f"{len(long_disp)} disputed claim(s) are older than {DISPUTE_AGING_DAYS} days "
                f"— escalate to HMO relationship manager immediately."
            )

        if total_waived > 100_000:
            insight.risks.append(
                f"Total waived amounts this period: ₦{total_waived:,.2f}. "
                "Validate all waivers comply with the hospital's discount approval policy."
            )

        if health == "healthy" and unpaid_count == 0:
            insight.findings.append("All bills settled and no claims in dispute — billing is fully reconciled.")

        insight.recommendations.append(
            "Run /billing_hospital/bills?status=pending to view and process outstanding bills."
        )

        insight.supporting_refs = (analysis.get("unpaid_bills") or [])[:10]

        if health == "healthy":
            insight.confidence_score = 0.92
        elif health == "attention":
            insight.confidence_score = 0.87
        else:
            insight.confidence_score = 0.83

        return insight

    def write_cache(self, insight: Insight) -> None:
        cache = self.context.get("cache")
        if cache:
            cache.set(self.name, insight, ttl=int(self.context.get("cache_ttl_seconds", 300)))

    def get_output_schema(self) -> Dict[str, Any]:
        return {
            "total_unpaid_bills": "int",
            "total_outstanding_ngn": "float",
            "pending_claims_count": "int",
            "pending_claims_value_ngn": "float",
            "disputed_claims_count": "int",
            "disputed_claims_value_ngn": "float",
            "long_disputed_count": "int",
            "total_waived_ngn": "float",
            "health_state": "str",
            "findings": "list",
            "risks": "list",
            "recommendations": "list",
        }
