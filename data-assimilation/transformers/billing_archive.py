"""Extract Hope's real billing/payment transaction history from `billings`
+ `final_billings` (staged as hope_billings/hope_final_billings) ->
royan_billing_transactions + royan_billing_summaries. A supplement to the
existing royan_billing (sourced from service_bills/consultant_billings),
not a replacement -- per explicit user decision.

transformers/payments.py's own header comment claims `billings` is
"confirmed EMPTY" -- wrong, based on the known-unreliable keyword-search
candidates cache. Direct content sampling confirmed real transactions
spanning 2016-2025 (real bill numbers like "BL24-E31/108", real patient
names in remarks).
"""
from __future__ import annotations

from typing import Any, Dict, List

from transformers._helpers import EXTERNAL_SOURCE, safe_date, safe_str


def _to_number(value: Any):
    try:
        s = str(value).strip().replace(",", "")
        return round(float(s), 2) if s and s.lower() not in ("none", "") else None
    except (ValueError, TypeError):
        return None


def transform_transactions(raw_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for row in raw_rows:
        raw = {k.lower(): v for k, v in row.items()}
        if safe_str(raw.get("is_deleted")) == "1":
            continue

        ext_id = safe_str(raw.get("id"))
        hope_pid = safe_str(raw.get("patient_id"))
        if not ext_id or not hope_pid:
            continue

        out.append({
            "_hope_patient_id":  hope_pid,
            "bill_number":       safe_str(raw.get("bill_number")),
            "transaction_date":  safe_date(raw.get("date")),
            "payment_category":  safe_str(raw.get("payment_category")),
            "mode_of_payment":   safe_str(raw.get("mode_of_payment")),
            "amount":            _to_number(raw.get("amount")),
            "total_amount":      _to_number(raw.get("total_amount")),
            "amount_paid":       _to_number(raw.get("amount_paid")),
            "amount_pending":    _to_number(raw.get("amount_pending")),
            "discount_amount":   _to_number(raw.get("discount_amount")),
            "remark":            safe_str(raw.get("remark")),
            "external_source":   EXTERNAL_SOURCE,
            "external_id":       ext_id,
        })
    return out


def transform_summaries(raw_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for row in raw_rows:
        raw = {k.lower(): v for k, v in row.items()}

        ext_id = safe_str(raw.get("id"))
        hope_pid = safe_str(raw.get("patient_id"))
        if not ext_id or not hope_pid:
            continue

        out.append({
            "_hope_patient_id":  hope_pid,
            "bill_number":       safe_str(raw.get("bill_number")),
            "bill_date":         safe_date(raw.get("date")),
            "total_amount":      _to_number(raw.get("total_amount")),
            "amount_paid":       _to_number(raw.get("amount_paid")),
            "amount_pending":    _to_number(raw.get("amount_pending")),
            "discount":          _to_number(raw.get("discount")),
            "claim_status":      safe_str(raw.get("claim_status")),
            "discharge_date":    safe_date(raw.get("discharge_date")),
            "external_source":   EXTERNAL_SOURCE,
            "external_id":       ext_id,
        })
    return out
