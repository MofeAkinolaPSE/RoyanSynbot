"""Extract HMO/insurance claim records from Hope billing rows → royan_insurance_claims.

A claim row is only emitted when hmo_covered > 0.  The patient's hmo_provider
and hmo_id are carried through as private fields so the loader can enrich them
from royan_patients if they are missing from the billing row itself.

Payloads are keyed by `_hope_billing_ext_id` so the loader can look up
royan_billing.id.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from transformers._helpers import safe_date, safe_str, utcnow

_CLAIM_STATUS_MAP = {
    "paid":         "paid",
    "settled":      "paid",
    "part_paid":    "approved",
    "partial":      "approved",
    "waived":       "approved",
    "disputed":     "disputed",
    "rejected":     "rejected",      # keep if explicitly present
    "denied":       "rejected",
    "approved":     "approved",
    "pre_authorised": "pre_authorised",
    "pre_auth":     "pre_authorised",
}


def _to_float(value: Any) -> float:
    try:
        return max(0.0, float(str(value or 0).replace(",", "")))
    except (ValueError, TypeError):
        return 0.0


def transform(raw_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    seen_ext_ids: set = set()

    for row in raw_rows:
        raw = {k.lower(): v for k, v in row.items()}

        # Skip soft-deleted
        if str(raw.get("is_deleted", "0")).strip() not in ("0", "", "null", "None"):
            continue

        hmo_amount = _to_float(
            raw.get("hmo_claim") or raw.get("hmo_amount") or raw.get("covered_amount")
            or raw.get("insurance_amount") or raw.get("amount_net_covered")
        )
        if hmo_amount <= 0:
            continue

        ext_id = safe_str(
            raw.get("invoice_id") or raw.get("bill_id") or raw.get("id") or raw.get("transaction_id")
        )
        hope_pid = safe_str(raw.get("patient_id") or raw.get("patientid"))
        if not ext_id or not hope_pid:
            continue
        if ext_id in seen_ext_ids:
            continue
        seen_ext_ids.add(ext_id)

        bill_status = str(
            raw.get("payment_status") or raw.get("status") or ""
        ).strip().lower().replace("-", "_").replace(" ", "_")
        claim_status = _CLAIM_STATUS_MAP.get(bill_status, "submitted")

        approved_amount: Optional[float] = None
        settled_at: Optional[str] = None
        if claim_status in ("approved", "paid"):
            approved_amount = hmo_amount
        if claim_status == "paid":
            settled_at = (
                safe_date(raw.get("paid_at"))
                or safe_date(raw.get("updated_at"))
                or safe_date(raw.get("modify_time"))
            )

        submitted_at = (
            safe_date(raw.get("created_at"))
            or safe_date(raw.get("create_time"))
            or safe_date(raw.get("invoice_date"))
            or safe_date(raw.get("bill_date"))
        )

        out.append({
            "_hope_patient_id":      hope_pid,
            "_hope_billing_ext_id":  ext_id,
            # hmo_provider and hmo_id are enriched from royan_patients by the loader
            "_hmo_provider_hint":    safe_str(raw.get("hmo") or raw.get("hmo_name") or raw.get("insurance_name")),
            "_hmo_id_hint":          safe_str(raw.get("hmo_id") or raw.get("membership_no") or raw.get("member_no")),
            "claim_amount":          round(hmo_amount, 2),
            "status":                claim_status,
            "submitted_at":          submitted_at or utcnow(),
            "authorisation_code":    safe_str(
                raw.get("auth_code") or raw.get("authorization_code") or raw.get("hmo_auth") or raw.get("approval_code")
            ),
            "approved_amount":       approved_amount,
            "settled_at":            settled_at,
            "notes":                 None,
        })

    return out
