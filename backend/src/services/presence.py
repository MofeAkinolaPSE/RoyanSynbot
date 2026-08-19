"""Live 'who's online' presence tracking.

One row per open WebSocket connection (not per user) in royan_presence_sessions
— a staff member with multiple tabs/devices doesn't drop offline just because
one closes. "Online" is always computed at READ time from last_seen_at
freshness, never from the disconnect event alone: an unclean disconnect
(laptop sleep, dropped network) may never fire server-side, so correctness
can't depend on it. Cleanup of stale rows happens opportunistically inside
online_summary() rather than via a scheduled job, to avoid adding a
background task to an already single-event-loop-constrained backend.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from src.constants import PRESENCE_STALE_SECONDS, TABLE_PRESENCE_SESSIONS, TABLE_STAFF
from src.db import db

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def record_connect(user_id: str, user_agent: Optional[str], ip_address: Optional[str]) -> Optional[str]:
    try:
        result = db.table(TABLE_PRESENCE_SESSIONS).insert({
            "user_id": user_id,
            "user_agent": user_agent,
            "ip_address": ip_address,
        }).execute()
        rows = result.data or []
        return rows[0]["id"] if rows else None
    except Exception as exc:
        logger.warning("presence record_connect failed: %s", exc)
        return None


def touch(session_id: Optional[str]) -> None:
    if not session_id:
        return
    try:
        db.table(TABLE_PRESENCE_SESSIONS).update({"last_seen_at": _now_iso()}).eq("id", session_id).execute()
    except Exception as exc:
        logger.warning("presence touch failed: %s", exc)


def record_disconnect(session_id: Optional[str]) -> None:
    """Courtesy cleanup on a clean disconnect — not relied on for the online
    count's correctness, which is staleness-based (see online_summary)."""
    if not session_id:
        return
    try:
        db.table(TABLE_PRESENCE_SESSIONS).delete().eq("id", session_id).execute()
    except Exception as exc:
        logger.warning("presence record_disconnect failed: %s", exc)


def online_summary() -> dict[str, Any]:
    """Live count + roster of who's currently online, plus an opportunistic
    sweep of long-stale rows so the table doesn't grow unbounded without a
    scheduled job."""
    try:
        db.table(TABLE_PRESENCE_SESSIONS).delete().lt(
            "last_seen_at",
            (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
        ).execute()
    except Exception as exc:
        logger.warning("presence stale-session cleanup failed: %s", exc)

    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=PRESENCE_STALE_SECONDS)).isoformat()
        sessions = (
            db.table(TABLE_PRESENCE_SESSIONS)
            .select("id,user_id,connected_at,last_seen_at")
            .gte("last_seen_at", cutoff)
            .execute()
        )
        rows = sessions.data or []
    except Exception as exc:
        logger.warning("presence online_summary query failed: %s", exc)
        return {"count": 0, "staff": []}

    # Earliest connected_at per user across all their open sessions/tabs.
    by_user: dict[str, dict[str, Any]] = {}
    for row in rows:
        uid = row["user_id"]
        existing = by_user.get(uid)
        if not existing or row["connected_at"] < existing["connected_at"]:
            by_user[uid] = row

    user_ids = list(by_user.keys())
    staff_by_user: dict[str, dict[str, Any]] = {}
    if user_ids:
        try:
            staff_rows = (
                db.table(TABLE_STAFF)
                .select("user_id,full_name,role,department")
                .in_("user_id", user_ids)
                .is_("quarantined_at", "null")
                .execute()
            )
            staff_by_user = {s["user_id"]: s for s in (staff_rows.data or [])}
        except Exception as exc:
            logger.warning("presence staff lookup failed: %s", exc)

    staff_list = []
    for uid, session in by_user.items():
        staff = staff_by_user.get(uid)
        staff_list.append({
            "user_id": uid,
            "full_name": (staff or {}).get("full_name") or "Unknown user",
            "role": (staff or {}).get("role"),
            "department": (staff or {}).get("department"),
            "connected_since": session["connected_at"],
        })
    staff_list.sort(key=lambda s: s["full_name"])

    return {"count": len(by_user), "staff": staff_list}
