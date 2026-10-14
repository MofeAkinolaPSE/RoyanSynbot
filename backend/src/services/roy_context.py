"""Dynamic per-user activity context for Roy — bounded, role-gated snapshots of
a staff member's own upcoming appointments, recently attended patients, and
open tasks, assembled at chat time so Roy can speak naturally about a user's
own work instead of only their static profile fields.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any, Dict, List

from ..db import db
from ..cache import ttl_cache

logger = logging.getLogger("roy_context")

MAX_ITEMS = 5


def _upcoming_appointments(staff_id: str) -> List[Dict[str, Any]]:
    try:
        resp = (
            db.table("royan_appointment_slots")
            .select("id,slot_date,slot_time,patient_name,department,status")
            .eq("doctor_id", staff_id)
            .gte("slot_date", date.today().isoformat())
            .order("slot_date")
            .order("slot_time")
            .limit(MAX_ITEMS)
            .execute()
        )
        return resp.data or []
    except Exception as e:
        logger.debug(f"upcoming_appointments lookup failed: {e}")
        return []


def _recent_patients(staff_id: str) -> List[Dict[str, Any]]:
    try:
        resp = (
            db.table("royan_encounters")
            .select("id,patient_id,status,updated_at,consulting_doctor_id,doctor_id")
            .or_(f"consulting_doctor_id.eq.{staff_id},doctor_id.eq.{staff_id}")
            .order("updated_at", desc=True)
            .limit(MAX_ITEMS * 2)
            .execute()
        )
        rows = resp.data or []
    except Exception as e:
        logger.debug(f"recent_patients lookup failed: {e}")
        return []

    seen_patients: set = set()
    deduped: List[Dict[str, Any]] = []
    for row in rows:
        pid = row.get("patient_id")
        if not pid or pid in seen_patients:
            continue
        seen_patients.add(pid)
        deduped.append(row)
        if len(deduped) >= MAX_ITEMS:
            break
    return deduped


def _open_tasks(actor_user_id: str) -> List[Dict[str, Any]]:
    try:
        resp = (
            db.table("royan_tasks")
            .select("id,title,status,priority,due_date")
            .eq("assigned_to", actor_user_id)
            # open work only: 'completed'/'cancelled' (Staff Workspace) were slipping through a != 'done' filter
            .in_("status", ["pending", "in_progress", "waiting", "blocked"])
            .neq("kind", "note")
            .order("due_date")
            .limit(MAX_ITEMS)
            .execute()
        )
        return resp.data or []
    except Exception as e:
        logger.debug(f"open_tasks lookup failed: {e}")
        return []


@ttl_cache(ttl_seconds=60, tags=["roy_context"])
def build_roy_activity_snapshot(staff_id: str, actor_user_id: str) -> Dict[str, Any]:
    """Bounded, best-effort snapshot of a staff member's own current work.

    Any individual sub-query failing (e.g. missing FK data from a sparse ETL
    backfill) degrades gracefully to an empty list rather than failing the
    whole chat request.
    """
    return {
        "upcoming_appointments": _upcoming_appointments(staff_id) if staff_id else [],
        "recent_patients": _recent_patients(staff_id) if staff_id else [],
        "open_tasks": _open_tasks(actor_user_id) if actor_user_id else [],
    }


def render_activity_snapshot(snapshot: Dict[str, Any], roles: set) -> str:
    """Render the snapshot as short role-gated bullet lines for the Roy system prompt."""
    lines: List[str] = []
    is_doctor = "doctor" in roles

    if is_doctor and snapshot.get("upcoming_appointments"):
        lines.append("Your upcoming appointments:")
        for appt in snapshot["upcoming_appointments"]:
            lines.append(
                f"  - {appt.get('slot_date')} {appt.get('slot_time') or ''} — "
                f"{appt.get('patient_name') or 'patient'} ({appt.get('status') or 'scheduled'})"
            )

    if is_doctor and snapshot.get("recent_patients"):
        lines.append("Patients you've recently attended to:")
        for enc in snapshot["recent_patients"]:
            lines.append(f"  - Encounter {enc.get('id')} — status: {enc.get('status')}")

    if snapshot.get("open_tasks"):
        lines.append("Your open tasks:")
        for task in snapshot["open_tasks"]:
            due = f" (due {task.get('due_date')})" if task.get("due_date") else ""
            lines.append(f"  - {task.get('title')}{due}")

    return "\n".join(lines)
