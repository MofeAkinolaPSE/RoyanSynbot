"""Pydantic contract for royan_patients rows."""
from __future__ import annotations

from typing import Optional

from pydantic import field_validator

from contracts.base import BaseContract

_VALID_GENDERS = {"male", "female", "other", "prefer_not_to_say"}
_VALID_BLOOD_GROUPS = {"A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-", "unknown"}
_VALID_GENOTYPES = {"AA", "AS", "SS", "AC", "SC", "unknown"}


class PatientContract(BaseContract):
    mrn: str
    first_name: str = "Unknown"
    last_name: str = "Patient"
    date_of_birth: Optional[str] = None
    gender: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    blood_group: Optional[str] = None
    genotype: Optional[str] = None
    hmo_provider: Optional[str] = None
    hmo_id: Optional[str] = None
    registered_by: str = "hope_ingest"
    registered_at: Optional[str] = None
    external_updated_at: Optional[str] = None

    @field_validator("gender", mode="before")
    @classmethod
    def validate_gender(cls, v: object) -> Optional[str]:
        if v is None:
            return None
        norm = str(v).strip().lower()
        return norm if norm in _VALID_GENDERS else None

    @field_validator("blood_group", mode="before")
    @classmethod
    def validate_blood_group(cls, v: object) -> Optional[str]:
        if v is None:
            return None
        norm = str(v).strip().upper().replace(" ", "")
        return norm if norm in _VALID_BLOOD_GROUPS else "unknown"

    @field_validator("genotype", mode="before")
    @classmethod
    def validate_genotype(cls, v: object) -> Optional[str]:
        if v is None:
            return None
        norm = str(v).strip().upper()
        return norm if norm in _VALID_GENOTYPES else "unknown"
