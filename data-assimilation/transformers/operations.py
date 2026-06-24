"""Polymorphic transformer for operational events.

Merges fumigation_records, maintenance_records, deviations, audit_records,
and recall_events from DRM Hope into the unified royan_operations_events table.

Each source table is classified into an event_type using name heuristics.
The original source table name is preserved in source_table for data lineage.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from transformers._helpers import EXTERNAL_SOURCE, apply_map, safe_str, utcnow
from transformers.field_maps import OPERATIONS_MAP

# Maps source table name patterns to event_type values
_SOURCE_TABLE_EVENT_TYPES: List[Tuple[str, str]] = [
    ("fumigation",   "fumigation"),
    ("maintenance",  "maintenance"),
    ("deviation",    "deviation"),
    ("deviation_log","deviation"),
    ("audit",        "audit"),
    ("compliance",   "audit"),
    ("recall",       "recall"),
    ("product_recall","recall"),
]

_SEVERITY_ALIASES = {
    "low": "low", "minor": "low", "info": "low",
    "medium": "medium", "moderate": "medium", "warning": "medium",
    "high": "high", "major": "high",
    "critical": "critical", "severe": "critical", "urgent": "critical",
}

_VALID_STATUSES = {"open", "in_progress", "resolved", "closed", "cancelled"}


def classify_event_type(source_table: str) -> Optional[str]:
    """Derive event_type from source table name. Returns None if unrecognised."""
    lower = source_table.lower()
    for pattern, event_type in _SOURCE_TABLE_EVENT_TYPES:
        if pattern in lower:
            return event_type
    return None


def _normalise_severity(val: Any) -> Optional[str]:
    if val is None:
        return None
    return _SEVERITY_ALIASES.get(str(val).strip().lower())


def _normalise_status(val: Any) -> str:
    if val is None:
        return "open"
    norm = str(val).strip().lower()
    aliases = {
        "pending": "open", "new": "open", "active": "in_progress",
        "ongoing": "in_progress", "done": "resolved", "completed": "resolved",
        "closed": "closed", "cancelled": "cancelled", "canceled": "cancelled",
    }
    norm = aliases.get(norm, norm)
    return norm if norm in _VALID_STATUSES else "open"


def transform_table(
    source_table: str,
    raw_rows: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Transform rows from a single source table. Returns payloads for royan_operations_events."""
    event_type = classify_event_type(source_table)
    if not event_type:
        return []

    out = []
    seen_external_ids: set = set()

    for row in raw_rows:
        mapped = apply_map(row, OPERATIONS_MAP)

        external_id = safe_str(mapped.get("external_id"))
        if not external_id:
            external_id = safe_str(row.get("id") or row.get("record_id"))
        if not external_id:
            continue
        if external_id in seen_external_ids:
            continue
        seen_external_ids.add(external_id)

        title = safe_str(mapped.get("title")) or f"{event_type.title()} record {external_id}"
        event_date = safe_str(mapped.get("event_date")) or utcnow()[:10]

        # Collect unmapped fields into metadata for full fidelity
        mapped_keys = set(OPERATIONS_MAP.values()) | {"external_id", "_hope_patient_id"}
        extra: Dict[str, Any] = {
            k: v for k, v in row.items()
            if k.lower() not in mapped_keys and v is not None
        }
        notes = safe_str(mapped.get("notes"))
        if notes:
            extra["notes"] = notes

        out.append({
            "event_type":           event_type,
            "event_date":           event_date[:10],
            "title":                title,
            "status":               _normalise_status(mapped.get("status")),
            "severity":             _normalise_severity(mapped.get("severity")),
            "performed_by":         safe_str(mapped.get("performed_by")),
            "department":           safe_str(mapped.get("department")),
            "metadata":             json.dumps(extra, default=str) if extra else "{}",
            "source_table":         source_table,
            "external_source":      EXTERNAL_SOURCE,
            "external_id":          f"{source_table}:{external_id}",
            "external_updated_at":  safe_str(mapped.get("external_updated_at")) or utcnow(),
        })

    return out


def transform(raw_rows: List[Dict[str, Any]], source_table: str = "operations") -> List[Dict[str, Any]]:
    """Entry point called by ingest.py / pipeline.py for a single source table."""
    return transform_table(source_table, raw_rows)
