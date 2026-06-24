"""Pydantic contract for royan_prescriptions rows."""
from __future__ import annotations

from typing import Optional

from pydantic import field_validator

from contracts.base import BaseContract

_VALID_STATUSES = {"pending", "dispensed", "partially_dispensed", "cancelled", "returned"}
_VALID_ROUTES = {"oral", "iv", "im", "topical", "inhaled", "sublingual", "rectal", "other"}


class PharmacyContract(BaseContract):
    drug_name: str
    drug_code: Optional[str] = None
    dosage: Optional[str] = None
    frequency: Optional[str] = None
    duration: Optional[str] = None
    route: Optional[str] = None
    quantity: Optional[str] = None
    unit: Optional[str] = None
    status: str = "pending"
    special_instructions: Optional[str] = None
    prescribed_by: Optional[str] = None
    prescribed_at: Optional[str] = None
    external_updated_at: Optional[str] = None

    @field_validator("drug_name", mode="before")
    @classmethod
    def drug_name_not_empty(cls, v: object) -> str:
        text = str(v or "").strip()
        if not text:
            raise ValueError("drug_name is required")
        return text

    @field_validator("status", mode="before")
    @classmethod
    def validate_status(cls, v: object) -> str:
        norm = str(v or "").strip().lower()
        return norm if norm in _VALID_STATUSES else "pending"

    @field_validator("route", mode="before")
    @classmethod
    def validate_route(cls, v: object) -> Optional[str]:
        if v is None:
            return None
        norm = str(v).strip().lower()
        return norm if norm in _VALID_ROUTES else "other"
