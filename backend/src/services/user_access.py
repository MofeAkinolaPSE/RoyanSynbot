"""User Access: logins, their roles, and the HR profile each login always has (reportGUide.md s4).

  catalog()      roles with what each opens, and the HR units, so HR and User Access agree
  users()        every login with the person's name, team, unit and job title from HR
  create()       login + HR profile in one step - the person appears in HR and on the Team tab at once
  set_roles()    reason required, cannot remove your own admin; the HR team follows the new roles

Routers stay thin (app.py /users*); the audit event is written by the caller with the reason.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from src import roles as role_catalog
from src.fin.db import ex, q, q1, tx
from src.services.staff_workspace import DEPARTMENTS, DEPT_ROLES, dept_for_roles, ensure_profile

log = logging.getLogger(__name__)


class AccessError(ValueError):
    pass


def catalog() -> Dict[str, Any]:
    with tx() as conn:
        units = [r["u"] for r in q(conn, """SELECT DISTINCT trim(department) AS u FROM royan_staff
                                           WHERE quarantined_at IS NULL AND COALESCE(trim(department),'') <> ''
                                           ORDER BY 1""")]
    return {"roles": role_catalog.ROLE_CATALOG, "units": units, "teams": DEPARTMENTS}


def users(limit: int = 500) -> List[Dict[str, Any]]:
    with tx() as conn:
        rows = q(conn, """SELECT u.id::text AS id, u.email, u.roles, u.is_active, u.created_at, u.updated_at,
                                 s.id::text AS staff_id, s.full_name, s.department AS unit, s.designation AS job_title,
                                 s.role AS staff_role
                          FROM royan_users u
                          LEFT JOIN royan_staff s ON s.user_id=u.id AND s.quarantined_at IS NULL
                          ORDER BY u.created_at DESC LIMIT %s""", (limit,))
    for r in rows:
        r["roles"] = list(r["roles"] or [])
        r["team"] = dept_for_roles([r["staff_role"]] if r["staff_role"] else r["roles"])
        r["has_profile"] = r["staff_id"] is not None
    return rows


def _role_for_team(roles: List[str]) -> Optional[str]:
    """The HR record's canonical role: the one that decides the person's team."""
    team = dept_for_roles(roles)
    hit = DEPT_ROLES.get(team, set()) & set(roles)
    return next(iter(hit), None)


def attach_profile(user_id: str, full_name: Optional[str] = None, unit: Optional[str] = None,
                   job_title: Optional[str] = None) -> str:
    """Create (or link) the HR profile for a new login and fill what User Access was told."""
    if full_name and full_name.strip():
        _link_by_name(user_id, full_name.strip())
    with tx() as conn:
        staff_id = ensure_profile(conn, user_id)
        sets, args = [], []
        for col, v in (("full_name", full_name), ("department", unit), ("designation", job_title)):
            if v and v.strip():
                sets.append(f"{col}=%s")
                args.append(v.strip())
        if sets:
            ex(conn, f"UPDATE royan_staff SET {', '.join(sets)}, updated_at=now() WHERE id=%s", (*args, staff_id))
    return staff_id


def _link_by_name(user_id: str, full_name: str) -> None:
    """HR may hold the person without an email. Link the login to their record when exactly one HR
    record has the same name (titles and order ignored) and no login yet - never a second record."""
    from src.services.staff_onboarding import hr_matches
    with tx() as conn:
        if q1(conn, "SELECT 1 FROM royan_staff WHERE user_id=%s AND quarantined_at IS NULL", (user_id,)):
            return
        email = q1(conn, "SELECT email FROM royan_users WHERE id=%s", (user_id,))["email"]
    exact = [m for m in hr_matches({"email": email, "full_name": full_name}) if m["score"] >= 0.95 and not m["has_login"]]
    if len(exact) == 1 and exact[0]["why"] != "same email":       # same email is already handled by ensure_profile
        with tx() as conn:
            ex(conn, """UPDATE royan_staff SET user_id=%s, email=COALESCE(NULLIF(email,''), %s), updated_at=now()
                        WHERE id::text=%s AND user_id IS NULL""", (user_id, email, exact[0]["id"]))


def set_roles(actor_id: str, user_id: str, new_roles: List[str], reason: str) -> Dict[str, Any]:
    if not (reason or "").strip():
        raise AccessError("Give a reason for the change - it is kept in the audit log")
    try:
        cleaned = role_catalog.normalize(new_roles)
    except ValueError as e:
        raise AccessError(str(e))
    with tx() as conn:
        u = q1(conn, "SELECT id::text AS id, email, roles FROM royan_users WHERE id=%s FOR UPDATE", (user_id,))
        if not u:
            raise LookupError("User not found")
        before = sorted(u["roles"] or [])
        if str(actor_id) == user_id and "admin" in before and "admin" not in cleaned:
            raise AccessError("You cannot remove your own admin role - ask another admin")
        ex(conn, "UPDATE royan_users SET roles=%s, updated_at=now() WHERE id=%s", (cleaned, user_id))
        # the HR team follows the roles, so routing ("For your role", team channels) stays right
        staff_role = _role_for_team(cleaned)
        if staff_role:
            ex(conn, """UPDATE royan_staff SET role=%s, updated_at=now()
                        WHERE user_id=%s AND quarantined_at IS NULL""", (staff_role, user_id))
    try:
        attach_profile(user_id)   # older logins created before profiles were automatic
    except Exception as exc:
        log.warning("user_access: could not attach HR profile for %s: %s", user_id, exc)
    return {"user_id": user_id, "email": u["email"], "roles": cleaned, "before": before}
