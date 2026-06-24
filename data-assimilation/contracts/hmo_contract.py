"""Pydantic contracts for HMO providers and patient insurance enrollments."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, field_validator

from contracts.base import BaseContract

_VALID_INSURANCE_STATUSES = {"active", "expired", "suspended", "inactive"}


class HmoContract(BaseContract):
    name: str
    code: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None
    is_active: bool = True

    @field_validator("name", mode="before")
    @classmethod
    def name_not_empty(cls, v: object) -> str:
        text = str(v or "").strip()
        if not text:
            raise ValueError("HMO name is required")
        return text


class PatientInsuranceContract(BaseModel):
    model_config = {"str_strip_whitespace": True, "extra": "ignore"}

    _hope_patient_id: Optional[str] = None   # resolved to patient_id by loader
    _hope_hmo_id: Optional[str] = None       # resolved to hmo_id by loader
    membership_id: Optional[str] = None
    status: str = "active"
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None
    is_primary: bool = True
    source: str = "hope_ingest"

    @field_validator("status", mode="before")
    @classmethod
    def validate_status(cls, v: object) -> str:
        norm = str(v or "").strip().lower()
        return norm if norm in _VALID_INSURANCE_STATUSES else "active"
