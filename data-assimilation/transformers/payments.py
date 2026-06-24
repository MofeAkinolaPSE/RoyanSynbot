"""Extract individual payment records from Hope billing rows → royan_payments.

A payment row is only emitted when the bill status indicates money was actually
received (paid / partial / part_paid / settled).  The amount is derived from
the patient-owed portion (total minus HMO-covered), or the explicit patient_due
column when available.

Payloads are keyed by `_hope_billing_ext_id` so the loader can look up
royan_billing.id.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from transformers._helpers import safe_date, safe_str, utcnow

_PAID_STATUSES = {"paid", "part_paid", "partial", "settled", "paid_by_hmo"}

_PAYMENT_METHOD_MAP = {
    "cash":             "cash",
    "card":             "card",
    "pos":              "card",
    "debit_card":       "card",
    "credit_card":      "card",
    "transfer":         "transfer",
    "bank":             "transfer",
    "bank_transfer":    "transfer",
    "online":           "transfer",
    "hmo":              "hmo",
    "insurance":        "hmo",
    "nhis":             "hmo",
    "waiver":           "waiver",
    "waived":           "waiver",
    "free":             "waiver",
}


def _to_float(value: Any) -> float:
    try:
        return max(0.0, float(str(value or 0).replace(",", "")))
    except (ValueError, TypeError):
        return 0.0


def _normalise_method(value: Any) -> str:
    raw = str(value or "").strip().lower().replace(" ", "_").replace("-", "_")
    return _PAYMENT_METHOD_MAP.get(raw, "cash")


def transform(raw_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    seen_ext_ids: set = set()

    for row in raw_rows:
        raw = {k.lower(): v for k, v in row.items()}

        # Skip soft-deleted Hope records
        if str(raw.get("is_deleted", "0")).strip() not in ("0", "", "null", "None"):
            continue

        stat_raw = str(
            raw.get("payment_status") or raw.get("status") or ""
        ).strip().lower().replace("-", "_").replace(" ", "_")
        # Map aliases
        stat_norm = {"part_paid": "partial", "settled": "paid"}.get(stat_raw, stat_raw)
        if stat_norm not in _PAID_STATUSES:
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

        total = _to_float(
            raw.get("total_amount") or raw.get("amount") or raw.get("total") or raw.get("gross_amount")
        )
        hmo = _to_float(
            raw.get("hmo_claim") or raw.get("hmo_amount") or raw.get("covered_amount") or raw.get("insurance_amount")
        )
        discount = _to_float(raw.get("discount"))

        # Patient payment amount: prefer explicit patient_due column
        patient_paid = _to_float(
            raw.get("patient_due") or raw.get("patient_amount") or raw.get("copay")
        )
        if patient_paid <= 0 and total > 0:
            patient_paid = max(0.0, total - hmo - discount)

        if patient_paid <= 0:
            continue  # nothing to record

        payment_method = _normalise_method(
            raw.get("payment_method") or raw.get("pay_method")
            or raw.get("mode_of_payment") or raw.get("payment_mode")
        )

        received_at = (
            safe_date(raw.get("paid_at"))
            or safe_date(raw.get("updated_at"))
            or safe_date(raw.get("modify_time"))
            or safe_date(raw.get("created_at"))
        )

        out.append({
            "_hope_patient_id":      hope_pid,
            "_hope_billing_ext_id":  ext_id,
            "amount":                round(patient_paid, 2),
            "payment_method":        payment_method,
            "reference":             safe_str(
                raw.get("receipt_no") or raw.get("reference") or raw.get("transaction_ref")
            ),
            "received_by":           "hope_ingest",
            "received_at":           received_at or utcnow(),
            "notes":                 None,
        })

    return out
