"""Pydantic contract for surgical theatre cases."""
from __future__ import annotations

from typing import Optional

from pydantic import field_validator

from contracts.base import BaseContract

_VALID_STATUSES = {"scheduled", "in_progress", "completed", "cancelled", "abandoned"}
_VALID_ANAESTHESIA = {"general", "spinal", "epidural", "local", "sedation", "none", "other"}


class TheatreContract(BaseContract):
    procedure_name: str
    surgeon: str
    anaesthetist: Optional[str] = None
    scrub_nurse: Optional[str] = None
    status: str = "scheduled"
    theatre_room: Optional[str] = None
    scheduled_at: Optional[str] = None
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    duration_mins: Optional[int] = None
    anaesthesia_type: Optional[str] = None
    notes: Optional[str] = None
    external_updated_at: Optional[str] = None

    @field_validator("procedure_name", "surgeon", mode="before")
    @classmethod
    def required_not_empty(cls, v: object) -> str:
        text = str(v or "").strip()
        if not text:
            raise ValueError("field is required")
        return text

    @field_validator("status", mode="before")
    @classmethod
    def validate_status(cls, v: object) -> str:
        norm = str(v or "").strip().lower()
        return norm if norm in _VALID_STATUSES else "scheduled"

    @field_validator("anaesthesia_type", mode="before")
    @classmethod
    def validate_anaesthesia(cls, v: object) -> Optional[str]:
        if v is None:
            return None
        norm = str(v).strip().lower()
        return norm if norm in _VALID_ANAESTHESIA else "other"
