"""Pydantic contract for royan_lab_orders rows."""
from __future__ import annotations

from typing import Optional

from pydantic import field_validator

from contracts.base import BaseContract

_VALID_URGENCIES = {"routine", "urgent", "stat"}
_VALID_STATUSES = {"ordered", "sample_collected", "processing", "resulted", "cancelled"}


class LabContract(BaseContract):
    test_name: str
    test_code: Optional[str] = None
    urgency: str = "routine"
    status: str = "ordered"
    sample_type: Optional[str] = None
    ordered_at: Optional[str] = None
    notes: Optional[str] = None
    ordered_by: Optional[str] = None
    external_updated_at: Optional[str] = None

    @field_validator("urgency", mode="before")
    @classmethod
    def validate_urgency(cls, v: object) -> str:
        norm = str(v or "").strip().lower()
        return norm if norm in _VALID_URGENCIES else "routine"

    @field_validator("status", mode="before")
    @classmethod
    def validate_status(cls, v: object) -> str:
        norm = str(v or "").strip().lower()
        return norm if norm in _VALID_STATUSES else "ordered"

    @field_validator("test_name", mode="before")
    @classmethod
    def test_name_not_empty(cls, v: object) -> str:
        text = str(v or "").strip()
        if not text:
            raise ValueError("test_name is required")
        return text
