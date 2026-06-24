"""Pydantic contract for royan_appointments rows."""
from __future__ import annotations

from typing import Optional

from pydantic import field_validator

from contracts.base import BaseContract

_VALID_STATUSES = {
    "booked", "confirmed", "arrived", "completed",
    "no_show", "cancelled", "rescheduled",
}


class AppointmentContract(BaseContract):
    doctor_name: Optional[str] = None
    department: Optional[str] = None
    slot_date: Optional[str] = None
    slot_time: Optional[str] = None
    status: str = "booked"
    reason: Optional[str] = None
    external_updated_at: Optional[str] = None

    @field_validator("status", mode="before")
    @classmethod
    def validate_status(cls, v: object) -> str:
        norm = str(v or "").strip().lower()
        return norm if norm in _VALID_STATUSES else "booked"
