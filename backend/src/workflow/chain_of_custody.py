"""
Chain of custody stub — pharma cold-chain workflow removed.

Preserves the public interface so that custody.py compiles without the
original cold-chain custody tracking infrastructure.
All operations return safe empty/success values.
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional


def record_custody_event(
    batch_id: str,
    event_type: str,
    actor: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Record a custody transfer event. Stub: no-op, returns empty record."""
    return {
        "batch_id": batch_id,
        "event_type": event_type,
        "actor": actor,
        "details": details or {},
        "recorded": False,
        "_stub": True,
    }


def list_custody_events(batch_id: str) -> List[Dict[str, Any]]:
    """List custody events for a batch. Stub: returns empty list."""
    return []


def sign_delivery(
    batch_id: str,
    signature: str,
    actor: Optional[str] = None,
) -> Dict[str, Any]:
    """Sign off on a delivery. Stub: no-op, returns success."""
    return {
        "batch_id": batch_id,
        "signed": True,
        "actor": actor,
        "_stub": True,
    }
