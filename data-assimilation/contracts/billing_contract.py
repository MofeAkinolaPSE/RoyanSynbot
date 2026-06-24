"""Pydantic contract for royan_billing rows with proper fee-column routing."""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, Optional

from pydantic import field_validator, model_validator

from contracts.base import BaseContract

_VALID_STATUSES = {"pending", "partial", "paid", "waived", "disputed", "written_off"}
_VALID_PAYMENT_METHODS = {"cash", "card", "transfer", "hmo", "waiver", "mixed"}

# Maps category hints (from Hope source) to the correct royan_billing column
_CATEGORY_ROUTING: Dict[str, str] = {
    "consultation":     "consultation_fee",
    "consult":          "consultation_fee",
    "doctor":           "consultation_fee",
    "opd":              "consultation_fee",
    "lab":              "lab_charges",
    "laboratory":       "lab_charges",
    "diagnostics":      "lab_charges",
    "test":             "lab_charges",
    "pharmacy":         "pharmacy_charges",
    "drug":             "pharmacy_charges",
    "medication":       "pharmacy_charges",
    "dispensing":       "pharmacy_charges",
    "ward":             "ward_charges",
    "bed":              "ward_charges",
    "admission":        "ward_charges",
    "inpatient":        "ward_charges",
    "procedure":        "procedure_charges",
    "surgery":          "procedure_charges",
    "theatre":          "procedure_charges",
    "operation":        "procedure_charges",
    "imaging":          "procedure_charges",
    "radiology":        "procedure_charges",
}


def route_amount(amount: Any, category_hint: Optional[str]) -> Dict[str, Decimal]:
    """Return a dict with the correct fee column set to *amount*, rest zero."""
    zero = Decimal("0")
    cols = {
        "consultation_fee":  zero,
        "lab_charges":       zero,
        "pharmacy_charges":  zero,
        "ward_charges":      zero,
        "procedure_charges": zero,
        "miscellaneous":     zero,
    }
    try:
        val = Decimal(str(amount or 0))
    except Exception:
        val = zero

    if val == zero:
        return cols

    key = None
    if category_hint:
        norm = str(category_hint).strip().lower()
        key = _CATEGORY_ROUTING.get(norm)

    col = key or "miscellaneous"
    cols[col] = val
    return cols


class BillingContract(BaseContract):
    consultation_fee:   Decimal = Decimal("0")
    lab_charges:        Decimal = Decimal("0")
    pharmacy_charges:   Decimal = Decimal("0")
    ward_charges:       Decimal = Decimal("0")
    procedure_charges:  Decimal = Decimal("0")
    miscellaneous:      Decimal = Decimal("0")
    hmo_covered:        Optional[Decimal] = None
    patient_balance:    Optional[Decimal] = None
    discount:           Optional[Decimal] = None
    status:             str = "pending"
    payment_method:     Optional[str] = None
    billed_at:          Optional[str] = None
    notes:              Optional[str] = None
    external_updated_at: Optional[str] = None

    @field_validator("status", mode="before")
    @classmethod
    def validate_status(cls, v: object) -> str:
        norm = str(v or "").strip().lower()
        return norm if norm in _VALID_STATUSES else "pending"

    @field_validator("payment_method", mode="before")
    @classmethod
    def validate_payment_method(cls, v: object) -> Optional[str]:
        if v is None:
            return None
        norm = str(v).strip().lower()
        return norm if norm in _VALID_PAYMENT_METHODS else None
