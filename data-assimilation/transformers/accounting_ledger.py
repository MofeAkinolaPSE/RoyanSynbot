"""Phase A3 ("finish the job") transformers for Hope's finance-side ledger:

  account_receipts    -> royan_account_receipts            (50,294)
  voucher_entries     -> royan_voucher_entries             (78,685)
  voucher_payments    -> royan_account_receipts            (526, same shape)
  patient_cards       -> royan_patient_card_transactions   (29,358)
  discount_requests   -> royan_discount_requests           (2,082)
  settlement_billings -> royan_settlement_billings         (302)

Archive/reference only -- these supplement, never replace, royan_billing
and royan_payments (per the same decision that governed migration 190).

patient_cards keys on `person_id`, NOT patient_id. Hope's `persons` table
bridges it: persons.id -> persons.patient_uid (the MRN, e.g. "RH16-2879")
-> royan_patients.mrn. Verified: 29,358/29,358 (100%) of patient_cards
person_ids resolve through this bridge, and sampled MRNs all exist in the
staged patient set.

settlement_billings.name is an encrypted blob ("$E$lTQk31oYpy...") with no
key anywhere in the dump -- dropped rather than loaded as garbage; the
numeric columns on those rows are still real and kept.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from transformers._helpers import EXTERNAL_SOURCE, normalize_text, safe_date, safe_str

_ENCRYPTED_PREFIX = "$E$"


def _num(value: Any) -> Optional[float]:
    try:
        s = str(value).strip().replace(",", "")
        return round(float(s), 2) if s and s.lower() != "none" else None
    except (ValueError, TypeError):
        return None


def build_person_to_mrn(persons_raw: List[Dict[str, Any]]) -> Dict[str, str]:
    """persons.id -> patient_uid (MRN). See module docstring."""
    out: Dict[str, str] = {}
    for p in persons_raw:
        pid = safe_str(p.get("id"))
        uid = safe_str(p.get("patient_uid"))
        if pid and uid:
            out[pid] = uid
    return out


def transform_account_receipts(
    receipts_raw: List[Dict[str, Any]],
    voucher_payments_raw: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """account_receipts and voucher_payments share the same real shape
    (paid_amount / narration / date / type / patient_id), so both land in
    royan_account_receipts. external_ids are prefixed per source to keep
    them from colliding in the shared key space.
    """
    out = []
    for row, prefix in [(r, "receipt") for r in receipts_raw] + \
                       [(r, "voucher_payment") for r in voucher_payments_raw]:
        if safe_str(row.get("is_deleted")) == "1":
            continue
        ext_id = safe_str(row.get("id"))
        if not ext_id:
            continue
        amount = _num(row.get("paid_amount"))
        if amount is None:
            continue

        out.append({
            "_hope_patient_id": safe_str(row.get("patient_id")) or None,
            "receipt_number":   safe_str(row.get("account_receipt_no")),
            "receipt_date":     safe_date(row.get("date")) or safe_date(row.get("create_time")),
            "amount":           amount,
            "payment_mode":     safe_str(row.get("type")),
            "narration":        normalize_text(safe_str(row.get("narration"))),
            "external_source":  EXTERNAL_SOURCE,
            "external_id":      f"{prefix}:{ext_id}",
        })
    return out


def transform_voucher_entries(raw_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for row in raw_rows:
        if safe_str(row.get("is_deleted")) == "1":
            continue
        ext_id = safe_str(row.get("id"))
        if not ext_id:
            continue
        debit = _num(row.get("debit_amount"))
        credit = _num(row.get("credit_amount"))
        if debit is None and credit is None:
            continue

        out.append({
            "_hope_patient_id": safe_str(row.get("patient_id")) or None,
            "account_ref":      safe_str(row.get("account_id")),
            "entry_date":       safe_date(row.get("date")) or safe_date(row.get("create_time")),
            "debit_amount":     debit,
            "credit_amount":    credit,
            "narration":        normalize_text(safe_str(row.get("narration"))),
            "entry_type":       safe_str(row.get("type")),
            "batch_identifier": safe_str(row.get("batch_identifier")),
            "external_source":  EXTERNAL_SOURCE,
            "external_id":      ext_id,
        })
    return out


def transform_patient_card_transactions(
    raw_rows: List[Dict[str, Any]], person_to_mrn: Dict[str, str],
) -> List[Dict[str, Any]]:
    out = []
    for row in raw_rows:
        if safe_str(row.get("is_deleted")) == "1":
            continue
        ext_id = safe_str(row.get("id"))
        if not ext_id:
            continue

        mrn = person_to_mrn.get(safe_str(row.get("person_id")) or "")

        out.append({
            "_hope_patient_mrn": mrn,
            "instrument_type":   safe_str(row.get("type")),
            "amount":            _num(row.get("amount")),
            "bank_account_no":   safe_str(row.get("bank_account_no")),
            "credit_card_no":    safe_str(row.get("credit_card_no")),
            "cheque_no":         safe_str(row.get("cheque_no")),
            "mode_type":         safe_str(row.get("mode_type")),
            "transacted_at":     safe_date(row.get("create_time")),
            "external_source":   EXTERNAL_SOURCE,
            "external_id":       ext_id,
        })
    return out


def transform_discount_requests(raw_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for row in raw_rows:
        ext_id = safe_str(row.get("id"))
        if not ext_id:
            continue
        # is_deleted is NOT used as a real-vs-test signal here -- these are
        # approval-workflow records where a rejected/withdrawn request is
        # still real history worth keeping.
        approved_raw = safe_str(row.get("is_approved"))

        out.append({
            "_hope_patient_id":    safe_str(row.get("patient_id")) or None,
            "patient_name":        safe_str(row.get("patient_name")),
            "request_type":        safe_str(row.get("type")),
            "discount_amount":     _num(row.get("discount_amount")),
            "discount_percentage": _num(row.get("discount_percentage")),
            "total_amount":        _num(row.get("total_amount")),
            "payment_category":    safe_str(row.get("payment_category")),
            "requested_by":        safe_str(row.get("request_by")),
            "requested_to":        safe_str(row.get("request_to")),
            "is_approved":         (approved_raw == "1") if approved_raw else None,
            "is_closed":           safe_str(row.get("closed")) == "1",
            "requested_at":        safe_date(row.get("create_time")),
            "external_source":     EXTERNAL_SOURCE,
            "external_id":         ext_id,
        })
    return out


def transform_settlement_billings(raw_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for row in raw_rows:
        ext_id = safe_str(row.get("id"))
        if not ext_id:
            continue

        name = safe_str(row.get("name"))
        if name and name.startswith(_ENCRYPTED_PREFIX):
            name = None  # encrypted blob, no key in the dump

        out.append({
            "_hope_patient_id": safe_str(row.get("patient_id")) or None,
            "item_name":        name,
            "units":            _num(row.get("unit")),
            "rate":             _num(row.get("rate")),
            "amount":           _num(row.get("amount")),
            "settled_at":       safe_date(row.get("create_time")),
            "external_source":  EXTERNAL_SOURCE,
            "external_id":      ext_id,
        })
    return out
