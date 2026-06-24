"""Pydantic contract for radiology imaging orders."""
from __future__ import annotations

from typing import Optional

from pydantic import field_validator

from contracts.base import BaseContract

_VALID_STUDY_TYPES = {"xray", "ultrasound", "ct", "mri", "fluoroscopy", "mammography", "other"}
_VALID_STATUSES = {"ordered", "in_progress", "reported", "verified", "cancelled"}


class RadiologyContract(BaseContract):
    study_type: str = "other"
    body_region: Optional[str] = None
    ordering_doctor: str
    radiographer: Optional[str] = None
    status: str = "ordered"
    report_text: Optional[str] = None
    performed_at: Optional[str] = None
    reported_at: Optional[str] = None
    external_updated_at: Optional[str] = None

    @field_validator("study_type", mode="before")
    @classmethod
    def validate_study_type(cls, v: object) -> str:
        norm = str(v or "").strip().lower().replace("-", "_").replace(" ", "_")
        aliases = {
            "x_ray": "xray", "x-ray": "xray",
            "computed_tomography": "ct", "mri_scan": "mri",
            "scan": "ct", "echo": "ultrasound",
        }
        norm = aliases.get(norm, norm)
        return norm if norm in _VALID_STUDY_TYPES else "other"

    @field_validator("status", mode="before")
    @classmethod
    def validate_status(cls, v: object) -> str:
        norm = str(v or "").strip().lower()
        return norm if norm in _VALID_STATUSES else "ordered"

    @field_validator("ordering_doctor", mode="before")
    @classmethod
    def doctor_not_empty(cls, v: object) -> str:
        text = str(v or "").strip()
        if not text:
            raise ValueError("ordering_doctor is required")
        return text
