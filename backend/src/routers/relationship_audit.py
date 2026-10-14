"""Relationship Audit HTTP Router — SDIL database-integrity endpoints.

Exposes the Relationship Auditor's cached insight plus an on-demand run, and
the per-patient relationship tree consumed by the Clinical Data Explorer.
Modeled on routers/capability_discovery.py.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request

from src.middleware import verify_jwt

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/audit", tags=["relationship_audit"])

_ALLOWED_ROLES = {"admin", "management", "ops"}


def _require_audit_access(request: Request, user=Depends(verify_jwt)):
    user_ctx = getattr(request.state, "user", {}) or {}
    roles = set(user_ctx.get("roles") or [])
    if not roles.intersection(_ALLOWED_ROLES):
        raise HTTPException(status_code=403, detail="Insufficient role for integrity audit access.")
    return user_ctx


@router.get("/integrity")
def api_get_integrity(user_ctx=Depends(_require_audit_access)):
    """Latest cached integrity insight; runs the audit fresh if nothing is cached."""
    from src.routers.cache_ui import get_shared_cache
    cache = get_shared_cache()
    cached = cache.get("relationship_auditor")
    if cached is not None:
        insight = cached
    else:
        from src.agents.relationship_auditor_agent import RelationshipAuditorAgent
        insight = RelationshipAuditorAgent({"actor_id": user_ctx.get("sub")}).run()
    return {
        "metrics": insight.metrics,
        "findings": insight.findings,
        "risks": insight.risks,
        "recommendations": insight.recommendations,
        "confidence_score": insight.confidence_score,
        "supporting_refs": insight.supporting_refs,
        "execution_metadata": insight.execution_metadata,
    }


@router.post("/run")
def api_run_audit(user_ctx=Depends(_require_audit_access)):
    """Force a fresh integrity audit run (bypasses the cached insight)."""
    from src.agents.relationship_auditor_agent import RelationshipAuditorAgent
    insight = RelationshipAuditorAgent({"actor_id": user_ctx.get("sub")}).run()
    return {
        "metrics": insight.metrics,
        "findings": insight.findings,
        "risks": insight.risks,
        "recommendations": insight.recommendations,
        "confidence_score": insight.confidence_score,
        "execution_metadata": insight.execution_metadata,
    }
