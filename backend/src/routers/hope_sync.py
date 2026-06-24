"""Read-only Hope Software sync endpoints."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from src.db import audit_event
from src.middleware import require_role
from src.services.hope_sync import SUPPORTED_ENTITIES, sync_entity

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/hope", tags=["Hope Sync"])


@router.post("/sync/{entity}")
async def sync_hope_entity(
    entity: str,
    limit: int = Query(200, ge=1, le=1000),
    user=Depends(require_role("admin")),
):
    """Pull rows from the local Hope bridge and normalize into Synbot tables.

    This is intentionally read-only with respect to Hope Software.
    """
    if entity not in SUPPORTED_ENTITIES:
        raise HTTPException(status_code=404, detail=f"Unsupported Hope sync entity '{entity}'")
    try:
        result = sync_entity(entity, limit=limit)
    except Exception as exc:
        logger.error("Hope sync failed for %s: %s", entity, exc)
        audit_event(
            "hope_sync_failed",
            {"entity": entity, "error": str(exc)},
            actor_id=user.get("sub"),
            event_class="integration",
            action="hope_sync",
            outcome="failure",
            subject_type="hope_sync",
            subject_id=entity,
        )
        raise HTTPException(status_code=502, detail=f"Hope sync failed: {exc}")

    audit_event(
        "hope_sync_completed",
        result,
        actor_id=user.get("sub"),
        event_class="integration",
        action="hope_sync",
        outcome="success",
        subject_type="hope_sync",
        subject_id=entity,
    )
    return {"ok": True, **result}
