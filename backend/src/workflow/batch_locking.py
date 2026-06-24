"""
Batch locking stub — pharma cold-chain workflow removed.

Preserves the public interface so that workflow.py and billing.py compile
without the original Sage/pharma batch management infrastructure.
All operations are no-ops that return safe default values.
"""
from __future__ import annotations
from typing import Any, Optional


def lock_batch(batch_id: str, reason: str = "locked_by_system", actor: Optional[str] = None) -> dict:
    """Lock a batch. Stub: no-op, returns success."""
    return {"locked": True, "batch_id": batch_id, "reason": reason, "actor": actor}


def unlock_batch(batch_id: str, actor: Optional[str] = None) -> dict:
    """Unlock a batch. Stub: no-op, returns success."""
    return {"locked": False, "batch_id": batch_id, "actor": actor}


def is_batch_locked(batch_id: str) -> bool:
    """Check if a batch is locked. Stub: always returns False."""
    return False


def auto_release_batch(batch_id: str) -> bool:
    """Auto-release a locked batch. Stub: always returns True."""
    return True


def enforce_no_locked_batches(batch_ids: Any) -> None:
    """Raise if any batch is locked. Stub: no-op (no batches are ever locked)."""
    return None
