"""Pydantic contract for royan_encounters (admission) rows."""
from __future__ import annotations

from typing import Optional

from pydantic import field_validator

from contracts.base import BaseContract

_VALID_STATUSES = {
    "patient_registered", "triaged", "consulting",
    "lab_ordered", "pharmacy_dispensing", "billing_pending", "discharged",
}
_VALID_TYPES = {"outpatient", "inpatient", "emergency", "maternity", "surgical"}


class AdmissionContract(BaseContract):
    encounter_type: str = "inpatient"
    status: str = "patient_registered"
    department: Optional[str] = None
    ward_name: Optional[str] = None
    bed_label: Optional[str] = None
    admitted_at: Optional[str] = None
    discharged_at: Optional[str] = None
    diagnosis_notes: Optional[str] = None
    consulting_doctor: Optional[str] = None
    registered_by: str = "hope_ingest"
    external_updated_at: Optional[str] = None

    @field_validator("encounter_type", mode="before")
    @classmethod
    def validate_type(cls, v: object) -> str:
        norm = str(v or "").strip().lower()
        return norm if norm in _VALID_TYPES else "inpatient"

    @field_validator("status", mode="before")
    @classmethod
    def validate_status(cls, v: object) -> str:
        norm = str(v or "").strip().lower()
        return norm if norm in _VALID_STATUSES else "patient_registered"
