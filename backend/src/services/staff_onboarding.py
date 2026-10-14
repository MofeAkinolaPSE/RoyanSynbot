"""Approving a staff self-registration without duplicating the person in HR.

Most people who register already have an HR record (HR loaded the staff list, or added them by
hand). Approval used to insert a second royan_staff row every time, so the person appeared twice
in HR and their hours, leave and payroll split across two records. Now:

  hr_matches(reg)   the HR records this registration could be: same email (certain), or the same
                    name once titles and order are ignored (likely - the admin confirms)
  approve(...)      in ONE transaction: create the login, then either LINK it to the chosen HR record
                    (filling only what HR has not recorded - HR stays the authority on its own data)
                    or create the HR record from the registration. Never both.

If an HR record already has the registration's email, approval links to it whatever the admin
picks, because creating a second record for the same email is never right.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from src.fin.db import Json, q, q1, tx
from src.services.staff_workspace import dept_for_roles

TITLES = {"dr", "doctor", "mr", "mrs", "miss", "ms", "prof", "professor", "nurse", "pharm", "sir", "chief", "engr", "barr"}


class OnboardingError(ValueError):
    pass


def _tokens(name: Optional[str]) -> List[str]:
    words = re.findall(r"[a-z]+", (name or "").lower())
    return [w for w in words if w not in TITLES and len(w) > 1]


def _name_score(a: Optional[str], b: Optional[str]) -> float:
    ta, tb = set(_tokens(a)), set(_tokens(b))
    if not ta or not tb:
        return 0.0
    common = ta & tb
    if len(common) >= 2 and (common == ta or common == tb):
        return 0.95 if ta == tb else 0.85          # same words in any order / one name inside the other
    if len(common) >= 2:
        return 0.7
    return 0.0


_STAFF_COLS = """id::text AS id, staff_number, full_name, email, phone, department, designation, role, specialty,
                 license_number, user_id::text AS user_id, external_source, is_active"""


def hr_matches(reg: Dict[str, Any]) -> List[Dict[str, Any]]:
    email = (reg.get("email") or "").strip().lower()
    with tx() as conn:
        rows = q(conn, f"SELECT {_STAFF_COLS} FROM royan_staff WHERE quarantined_at IS NULL")
    out = []
    for r in rows:
        if r["email"] and r["email"].strip().lower() == email:
            score, why = 1.0, "same email"
        else:
            score = _name_score(reg.get("full_name"), r["full_name"])
            why = "same name" if score >= 0.95 else "similar name" if score else ""
        if score >= 0.7:
            out.append({**r, "score": score, "why": why, "has_login": bool(r["user_id"])})
    return sorted(out, key=lambda m: -m["score"])


def approve(reg: Dict[str, Any], admin_id: str, link_staff_id: Optional[str], create_new: bool,
            department_id_override: Optional[int] = None) -> Dict[str, Any]:
    email = (reg.get("email") or "").strip().lower()
    kyc = reg.get("kyc_details") or {}
    matches = hr_matches(reg)
    by_email = next((m for m in matches if m["why"] == "same email"), None)
    if by_email:
        link_staff_id, create_new = by_email["id"], False        # never a second record for one email
    if not link_staff_id and not create_new:
        if matches:
            raise OnboardingError("This person may already be in HR - choose their record, or confirm they are new")
        create_new = True
    with tx() as conn:
        if q1(conn, "SELECT 1 FROM royan_users WHERE lower(email)=%s", (email,)):
            raise OnboardingError("A login with this email already exists - change its roles on User Access instead")
        user = q1(conn, """INSERT INTO royan_users (email, hashed_password, roles, is_active)
                           VALUES (%s, %s, %s, true) RETURNING id::text AS id""",
                  (email, reg["hashed_password"], [reg["role"]]))
        dept_id = department_id_override if department_id_override is not None else reg.get("department_id")
        if link_staff_id:
            s = q1(conn, f"SELECT {_STAFF_COLS} FROM royan_staff WHERE id::text=%s AND quarantined_at IS NULL FOR UPDATE", (link_staff_id,))
            if not s:
                raise OnboardingError("That HR record no longer exists")
            if s["user_id"]:
                raise OnboardingError(f"{s['full_name']}'s HR record already has a login")
            filled = []
            # HR's own entries stay; the registration fills what HR never recorded
            fill = {"email": email, "phone": reg.get("phone"), "designation": reg.get("designation"),
                    "department": reg.get("department"), "specialty": kyc.get("specialty"),
                    "license_number": kyc.get("medical_council_number"), "role": reg["role"]}
            sets, args = ["user_id=%s", "updated_at=now()"], [user["id"]]
            for col, val in fill.items():
                current = s.get(col)
                empty = current in (None, "", "Staff", "Unassigned") or (col == "email" and "placeholder" in (current or ""))
                if val and empty:
                    sets.append(f"{col}=%s")
                    args.append(val)
                    filled.append(col)
            if dept_id is not None:
                sets.append("department_id=COALESCE(department_id, %s)")
                args.append(dept_id)
            q1(conn, f"UPDATE royan_staff SET {', '.join(sets)} WHERE id::text=%s RETURNING id", (*args, link_staff_id))
            staff_id, mode = link_staff_id, "linked"
        else:
            filled = []
            row = q1(conn, """INSERT INTO royan_staff (staff_number, full_name, department, department_id, designation, role, email,
                                                      phone, metadata, specialty, license_number, user_id)
                              VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id::text AS id""",
                     (f"REG-{str(reg['id'])[:8].upper()}", reg["full_name"], reg.get("department") or dept_for_roles([reg["role"]]),
                      dept_id, reg.get("designation") or "Staff", reg["role"], email, reg.get("phone"), Json(kyc),
                      kyc.get("specialty"), kyc.get("medical_council_number"), user["id"]))
            staff_id, mode = row["id"], "created"
        q1(conn, """UPDATE royan_staff_registrations SET status='approved', reviewed_by=%s, reviewed_at=now(),
                    created_staff_id=%s, created_user_id=%s WHERE id::text=%s AND status='pending' RETURNING id""",
           (admin_id, staff_id, user["id"], str(reg["id"])))
    return {"status": "approved", "mode": mode, "staff_id": staff_id, "user_id": user["id"], "filled": filled}
