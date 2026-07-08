"""Internal, machine-to-machine reliability endpoints.

Not part of the public/user-facing API surface — no nginx location block
ever proxies `/internal/...` (see deploy/nginx/nginx.conf), so this is
unreachable from outside the Docker network by construction. The shared-secret
header check below is defense-in-depth against *other* containers on the same
compose network (frontend, patient_portal, db all share royan_net with the
backend), not the only control.

This is the ingestion point for the log-tail watcher sidecar: it POSTs a
normalized, PHI-scrubbed error signature here, which is recorded via the same
capability_engine.record_signal() path used by every other signal source, so
recurring log errors flow into the existing human-reviewable proposal queue
instead of a separate, parallel system.
"""
from __future__ import annotations

import asyncio
import hmac
import logging
import os
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from src.cache import get_redis_client
from src.reliability.guardrails import GUARDRAILS
from src.services.capability_engine import record_signal, run_discovery_cycle

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/internal/reliability", tags=["internal"])

_DISCOVERY_COOLDOWN_KEY = "reliability:discovery_cycle:cooldown"
_DISCOVERY_COOLDOWN_SECONDS = 300


def _require_internal_key(request: Request) -> None:
    expected = os.environ.get("INTERNAL_SIGNAL_KEY", "")
    got = request.headers.get("X-Internal-Key", "")
    # Fail closed: an unset secret must never be treated as "no auth required".
    if not expected or not hmac.compare_digest(got, expected):
        raise HTTPException(status_code=403, detail="forbidden")


class LogSignalRequest(BaseModel):
    component: str
    description: str = Field(..., description="Already normalized/fingerprinted by the watcher — PHI-scrubbed.")
    source_container: str
    raw_excerpt: Optional[str] = None
    severity: Optional[str] = "medium"


async def _trigger_discovery_cycle() -> None:
    """Run a discovery cycle inline on the main event loop (not via
    asyncio.to_thread) so create_alert()'s realtime push — which depends on
    asyncio.get_running_loop() succeeding — actually fires. to_thread runs in
    a separate OS thread with no event loop of its own, which would silently
    drop the WebSocket notification (the DB row would still be written)."""
    try:
        run_discovery_cycle()
    except Exception as exc:
        logger.error("internal_reliability: triggered discovery cycle failed: %s", exc)


@router.post("/log-signal")
async def log_signal(payload: LogSignalRequest, _=Depends(_require_internal_key)):
    """Record a log-derived capability signal and, if it just crossed the
    proposal threshold, trigger an immediate discovery cycle rather than
    waiting for CapabilityDiscoveryEngine's daily loop (light_interval_seconds
    = 86400 — far too slow for this)."""
    result = record_signal(
        signal_type="log_error",
        description=payload.description,
        component=payload.component,
        metadata={
            "source_container": payload.source_container,
            "raw_excerpt": (payload.raw_excerpt or "")[:2000],
            "severity": payload.severity,
        },
    )

    if result.get("created"):
        r = get_redis_client()
        if r is not None:
            hour_key = f"reliability:log_signal_new_count:{time.strftime('%Y%m%d%H')}"
            new_count = r.incr(hour_key)
            r.expire(hour_key, 3600)
            if new_count > GUARDRAILS.max_new_log_signals_per_hour:
                logger.warning(
                    "internal_reliability: %d new log_error signals this hour (limit %d) — "
                    "watcher normalization may need tightening (too many distinct fingerprints "
                    "for what's likely the same underlying error)",
                    new_count, GUARDRAILS.max_new_log_signals_per_hour,
                )

    # >= (not ==) because record_signal's read-then-write frequency update
    # isn't atomic under concurrent calls — a race could skip the exact
    # threshold value. The Redis cooldown lock (not the >= check alone) is
    # what actually prevents the discovery cycle from firing repeatedly
    # during a burst of the same error.
    if result.get("frequency", 0) >= GUARDRAILS.min_signal_frequency_for_proposal:
        r = get_redis_client()
        should_trigger = True
        if r is not None:
            should_trigger = bool(r.set(_DISCOVERY_COOLDOWN_KEY, "1", nx=True, ex=_DISCOVERY_COOLDOWN_SECONDS))
        if should_trigger:
            asyncio.create_task(_trigger_discovery_cycle())

    return result
