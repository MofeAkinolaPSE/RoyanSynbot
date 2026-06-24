"""Base Pydantic v2 contract shared by all entity contracts."""
from __future__ import annotations

from pydantic import BaseModel, field_validator


class BaseContract(BaseModel):
    model_config = {"str_strip_whitespace": True, "extra": "ignore"}

    external_source: str
    external_id: str

    @field_validator("external_id", mode="before")
    @classmethod
    def external_id_not_empty(cls, v: object) -> str:
        text = str(v or "").strip()
        if not text:
            raise ValueError("external_id cannot be empty")
        return text
