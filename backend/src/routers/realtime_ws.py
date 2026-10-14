from __future__ import annotations

import datetime as dt
import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from src.constants import WEBSOCKET_ENABLED
from src.middleware import require_role, verify_jwt
from src.services import presence
from src.services.realtime import realtime_hub
from src.services.ws_ticket import TICKET_TTL_SECONDS, issue_ticket, redeem_ticket

logger = logging.getLogger("realtime_ws")
router = APIRouter(prefix="/realtime", tags=["realtime"])

_ALLOWED_CHANNELS: dict[str, set[str]] = {
    "workflow_updates":  {"admin", "management", "compliance", "finance", "ops", "procurement"},
    "calendar_tasks":    {"admin", "management", "hr", "ops", "finance", "sales", "crm"},
    "alerts_updates":    {"admin", "management", "ops", "finance", "hr", "compliance", "procurement", "sales", "doctor", "nurse", "clinical", "clinical_staff"},
    "inventory_updates": {"admin", "management", "ops", "inventory", "procurement", "finance"},
    "finance_updates":   {"admin", "management", "finance", "ops"},
    "logistics_updates": {"admin", "management", "ops", "procurement", "inventory"},
    "staff_updates":     {"admin", "management", "hr", "ops"},
    "crm_updates":       {"admin", "management", "crm", "sales"},
    "chat_updates":      {"admin", "management", "hr", "ops", "crm", "sales", "staff"},
    "encounter_updates": {"admin", "management", "doctor", "nurse", "clinical", "clinical_staff", "ops", "hr"},
    "appointment_updates": {"admin", "management", "receptionist", "doctor", "nurse", "ops", "hr"},
}

# Channels open to any authenticated ticket holder, regardless of role — no
# role list to keep in sync as roles evolve. "presence" needs every staff
# role to connect (a doctor/nurse/pharmacist is exactly who should show up
# as "online"), unlike the admin/hr/ops-only channels above.
# "workspace_updates" (Staff Workspace) is the same: every member of staff has a
# workspace, and its messages only say "refresh" plus the user ids concerned,
# never task, request or message content.
_OPEN_CHANNELS: set[str] = {"presence", "workspace_updates"}


async def _authorize_channel(websocket: WebSocket, channel: str) -> dict[str, Any]:
    if channel not in _ALLOWED_CHANNELS and channel not in _OPEN_CHANNELS:
        await websocket.close(code=4404)
        raise RuntimeError("Unknown channel")

    # Tickets only — no raw-JWT-in-URL fallback. A raw access token in the
    # query string would land in proxy/access logs for the token's full
    # 45-minute lifetime; the short-lived, single-use ticket (issued via
    # POST /realtime/ws-ticket) avoids that.
    ticket = websocket.query_params.get("ticket")
    if not ticket:
        await websocket.close(code=4401)
        raise RuntimeError("Missing ticket")
    payload = redeem_ticket(ticket.strip())
    if not payload:
        await websocket.close(code=4401)
        raise RuntimeError("Invalid or expired ticket")

    if channel not in _OPEN_CHANNELS:
        roles = set(payload.get("roles") or [])
        allowed = _ALLOWED_CHANNELS[channel]
        if not roles.intersection(allowed):
            await websocket.close(code=4403)
            raise RuntimeError("Insufficient role")

    return payload


@router.post("/ws-ticket")
def get_ws_ticket(user: dict = Depends(verify_jwt)):
    """Exchange the caller's JWT (sent properly, in a header) for a
    short-lived, single-use ticket to open a WebSocket with — keeps the raw
    access token out of proxy/access logs."""
    ticket = issue_ticket({
        "sub": user.get("sub"),
        "roles": user.get("roles", []),
        "email": user.get("email"),
    })
    return {"ticket": ticket, "expires_in": TICKET_TTL_SECONDS}


@router.get("/presence/summary")
def presence_summary(user: dict = Depends(require_role("admin", "management", "hr", "ops"))):
    """Live count + roster of who's currently online — same audience as
    staff_updates, since that's who should see a headcount card."""
    return presence.online_summary()


@router.websocket("/ws/{channel}")
async def realtime_channel_ws(websocket: WebSocket, channel: str):
    if not WEBSOCKET_ENABLED:
        await websocket.close(code=4403)
        return

    try:
        payload = await _authorize_channel(websocket, channel)
    except RuntimeError:
        return

    await realtime_hub.connect(channel, websocket)
    await realtime_hub.broadcast(
        channel,
        {
            "event": "subscriber_joined",
            "channel": channel,
            "user": payload.get("sub"),
            "at": dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        },
    )

    presence_session_id: str | None = None
    if channel == "presence" and payload.get("sub"):
        presence_session_id = presence.record_connect(
            payload["sub"],
            websocket.headers.get("user-agent"),
            websocket.client.host if websocket.client else None,
        )
        await realtime_hub.broadcast(
            "staff_updates",
            {"event": "staff_presence_joined", "user": payload.get("sub")},
        )

    try:
        while True:
            raw = await websocket.receive_text()
            if not raw:
                continue
            try:
                message = json.loads(raw)
            except Exception:
                message = {"type": "ping"}
            if message.get("type") == "ping":
                if presence_session_id:
                    presence.touch(presence_session_id)
                await websocket.send_text(json.dumps({"event": "pong", "channel": channel}))
    except WebSocketDisconnect:
        await realtime_hub.disconnect(channel, websocket)
        if presence_session_id:
            presence.record_disconnect(presence_session_id)
            await realtime_hub.broadcast(
                "staff_updates",
                {"event": "staff_presence_left", "user": payload.get("sub")},
            )
    except Exception as exc:
        logger.warning(f"realtime websocket error channel={channel}: {exc}")
        await realtime_hub.disconnect(channel, websocket)
        if presence_session_id:
            presence.record_disconnect(presence_session_id)
            await realtime_hub.broadcast(
                "staff_updates",
                {"event": "staff_presence_left", "user": payload.get("sub")},
            )
