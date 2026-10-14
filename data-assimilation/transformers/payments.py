"""Extract real payment records from Hope's `service_cash_payments` table
(staged as `hope_payments`) -> royan_payments.

This REPLACES the earlier design that tried to derive payments from
`raw_billing` (service_bills) rows -- service_bills has no payment-status
field at all, so that path always emitted zero rows. `service_cash_payments`
is a genuine, dedicated per-payment table with its own row per cash/card
receipt against a bill.

Each row gets its own external_id (the Hope service_cash_payments.id), so
the loader can do a normal ON CONFLICT upsert instead of the old
one-payment-per-bill restriction -- a bill legitimately has 0..N payments.

billing_id is deliberately NOT resolved: `service_cash_payments.billing_id`
references Hope's `billings` table. Passing that raw value through to the
loader's royan_billing.external_id lookup produced spurious matches
against `service_bills` rows (a coincidentally-overlapping but unrelated
auto-increment id sequence) -- confirmed by finding "linked" payments
whose patient didn't match the bill's own patient. patient_id is the only
reliable link here.

CORRECTION (2026-08-22): this docstring previously asserted Hope's
`billings` table was "confirmed EMPTY in this dump export". That was
WRONG -- it came from the keyword-search candidates cache
(scan_reports/db_drmnigeria_candidates.json), which reports row_count 0
as a placeholder for any table its earlier keyword scan didn't match, and
must never be used as evidence of emptiness. `billings` actually holds
419,135 real rows spanning 2016-2025 and is now loaded into
royan_billing_transactions (migration 190, transformers/billing_archive.py).
The billing_id non-resolution above still stands on its own merits.
"""
from __future__ import annotations

from typing import Any, Dict, List

from transformers._helpers import EXTERNAL_SOURCE, safe_date, safe_str, utcnow


def _to_float(value: Any) -> float:
    try:
        return float(str(value or 0).replace(",", ""))
    except (ValueError, TypeError):
        return 0.0


def transform(raw_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for row in raw_rows:
        raw = {k.lower(): v for k, v in row.items()}

        if str(raw.get("is_deleted", "0")).strip() not in ("0", "", "null", "None"):
            continue

        ext_id = safe_str(raw.get("id"))
        hope_pid = safe_str(raw.get("patient_id"))
        if not ext_id or not hope_pid:
            continue

        paid_amount = _to_float(raw.get("paid_amount"))
        if paid_amount <= 0:
            continue  # nothing was actually collected on this row

        by_card = _to_float(raw.get("paid_by_card"))
        by_cash = _to_float(raw.get("paid_by_cash"))
        if by_card > 0 and by_card >= by_cash:
            payment_method = "card"
        elif by_cash > 0:
            payment_method = "cash"
        else:
            payment_method = "other"

        received_at = safe_date(raw.get("created_time")) or safe_date(raw.get("create_time")) or utcnow()

        out.append({
            "_hope_patient_id":     hope_pid,
            "amount":               round(paid_amount, 2),
            "payment_method":       payment_method,
            "reference":            None,
            "received_by":          safe_str(raw.get("created_by")) or "hope_ingest",
            "received_at":          received_at,
            "notes":                None,
            "external_source":      EXTERNAL_SOURCE,
            "external_id":          ext_id,
            "external_updated_at":  received_at,
        })

    return out
