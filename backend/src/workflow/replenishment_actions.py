"""
Replenishment actions stub — pharma procurement workflow removed.

Preserves the public interface so that registrations.py compiles without
the original Sage/pharma replenishment-tracking infrastructure.
All operations are no-ops that return safe default values.
"""
from __future__ import annotations
from typing import Any, Dict, Optional


def mark_replenishment_received(
    request_id: str,
    received_by: Optional[str] = None,
    notes: Optional[str] = None,
) -> Dict[str, Any]:
    """Mark a replenishment request as received. Stub: no-op, returns success."""
    return {
        "request_id": request_id,
        "status": "received",
        "received_by": received_by,
        "notes": notes,
        "_stub": True,
    }


def create_replenishment_request(
    sku: str,
    quantity: int,
    requested_by: Optional[str] = None,
    priority: str = "normal",
) -> Dict[str, Any]:
    """Create a replenishment request. Stub: no-op, returns empty record."""
    return {
        "sku": sku,
        "quantity": quantity,
        "requested_by": requested_by,
        "priority": priority,
        "status": "pending",
        "_stub": True,
    }
