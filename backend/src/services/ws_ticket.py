"""Short-lived, single-use tickets for WebSocket auth handshakes.

Browsers cannot attach an Authorization header to a WebSocket upgrade
request, so the JWT would otherwise have to travel in the URL query string —
which means it lands in plaintext in every proxy/access log it passes
through. Instead, the client exchanges its real JWT (sent properly, in a
header) for a one-time ticket via POST /realtime/ws-ticket, then opens the
socket with that ticket in the URL. The ticket carries no identity a reader
could reuse: it is meaningless after TICKET_TTL_SECONDS or after first use.
"""
from __future__ import annotations

import json
import secrets
import threading
import time
from typing import Any, Optional

from src.cache import get_redis_client

TICKET_TTL_SECONDS = 30
_KEY_PREFIX = "ws_ticket:"

# In-process fallback store, used only if Redis is unavailable. Fine for a
# single backend replica; a shared store (Redis) is required once the
# backend runs with more than one replica.
_local_store: dict[str, tuple[float, dict]] = {}
_local_lock = threading.Lock()


def issue_ticket(payload: dict[str, Any]) -> str:
    ticket = secrets.token_urlsafe(32)
    r = get_redis_client()
    if r is not None:
        r.setex(_KEY_PREFIX + ticket, TICKET_TTL_SECONDS, json.dumps(payload))
        return ticket
    with _local_lock:
        _local_store[ticket] = (time.time() + TICKET_TTL_SECONDS, payload)
    return ticket


def redeem_ticket(ticket: str) -> Optional[dict[str, Any]]:
    """Return and invalidate the payload for a ticket. None if unknown/expired."""
    if not ticket:
        return None
    r = get_redis_client()
    if r is not None:
        key = _KEY_PREFIX + ticket
        pipe = r.pipeline()
        pipe.get(key)
        pipe.delete(key)
        raw, _ = pipe.execute()
        return json.loads(raw) if raw else None
    with _local_lock:
        entry = _local_store.pop(ticket, None)
    if not entry:
        return None
    expires_at, payload = entry
    return payload if expires_at >= time.time() else None
