"""
Credit risk stub — pharma billing workflow removed.

Preserves the public interface so that billing.py compiles without the
original Sage/pharma credit-risk assessment infrastructure.
All operations return safe default values (no customer is ever flagged).
"""
from __future__ import annotations
from typing import Any, Dict, Optional


def is_customer_flagged(customer_id: str) -> bool:
    """Check if a customer is on credit hold. Stub: always returns False."""
    return False


def apply_credit_action(
    customer_id: str,
    action: str,
    actor: Optional[str] = None,
    reason: Optional[str] = None,
) -> Dict[str, Any]:
    """Apply a credit action to a customer. Stub: no-op, returns success."""
    return {
        "customer_id": customer_id,
        "action": action,
        "applied": True,
        "actor": actor,
        "reason": reason,
    }
