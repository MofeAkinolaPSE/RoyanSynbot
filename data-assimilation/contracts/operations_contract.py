"""Pydantic contract for royan_operations_events (polymorphic operational events)."""
from __future__ import annotations

import json
from datetime import date
from typing import Any, Dict, Optional

from pydantic import BaseModel, field_validator

_VALID_TYPES = {"audit", "deviation", "maintenance", "fumigation", "recall"}
_VALID_STATUSES = {"open", "in_progress", "resolved", "closed", "cancelled"}
_VALID_SEVERITIES = {"low", "medium", "high", "critical"}


class OperationsEventContract(BaseModel):
    model_config = {"str_strip_whitespace": True, "extra": "ignore"}

    event_type:     str
    event_date:     str
    title:          str
    status:         str = "open"
    severity:       Optional[str] = None
    performed_by:   Optional[str] = None
    department:     Optional[str] = None
    metadata:       Dict[str, Any] = {}
    source_table:   str
    external_source: Optional[str] = None
    external_id:    Optional[str] = None

    @field_validator("event_type", mode="before")
    @classmethod
    def validate_event_type(cls, v: object) -> str:
        norm = str(v or "").strip().lower()
        if norm not in _VALID_TYPES:
            raise ValueError(f"Unknown event_type '{norm}'. Must be one of {_VALID_TYPES}")
        return norm

    @field_validator("title", mode="before")
    @classmethod
    def title_not_empty(cls, v: object) -> str:
        text = str(v or "").strip()
        if not text:
            raise ValueError("title is required")
        return text

    @field_validator("status", mode="before")
    @classmethod
    def validate_status(cls, v: object) -> str:
        norm = str(v or "").strip().lower()
        return norm if norm in _VALID_STATUSES else "open"

    @field_validator("severity", mode="before")
    @classmethod
    def validate_severity(cls, v: object) -> Optional[str]:
        if v is None:
            return None
        norm = str(v).strip().lower()
        return norm if norm in _VALID_SEVERITIES else None

    @field_validator("metadata", mode="before")
    @classmethod
    def coerce_metadata(cls, v: object) -> Dict[str, Any]:
        if v is None:
            return {}
        if isinstance(v, dict):
            return v
        try:
            return json.loads(str(v))
        except Exception:
            return {"raw": str(v)}
