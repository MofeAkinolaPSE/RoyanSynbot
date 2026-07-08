from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Any, Dict, Optional
import logging

from src.db import db
from src.constants import TABLE_STAFF
from src.middleware import verify_jwt
from src.services.staff_ops import get_my_profile, update_my_profile, get_staff_by_email, resolve_department_id

router = APIRouter(prefix="/staff", tags=["staff-me"])
logger = logging.getLogger("staff_me")


class ProfilePatch(BaseModel):
    full_name: Optional[str] = None
    department: Optional[str] = None
    designation: Optional[str] = None
    phone: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


@router.get("/me")
def get_me(user: dict = Depends(verify_jwt)):
    email = (user or {}).get("email")
    if not email:
        raise HTTPException(status_code=400, detail="JWT has no email claim")
    profile = get_my_profile(email)
    if not profile:
        # Return a minimal shell so the frontend knows to trigger onboarding
        return {"data": None, "profile_complete": False}
    meta = profile.get("metadata") or {}
    return {"data": profile, "profile_complete": bool(meta.get("profile_complete"))}


@router.post("/me/ensure-profile")
def ensure_profile(body: ProfilePatch, user: dict = Depends(verify_jwt)):
    """Create the calling user's own royan_staff row if they don't have one yet.

    This is distinct from public self-registration (see public_registration.py) —
    it only ever runs for a caller who already holds a valid JWT, i.e. someone
    whose royan_users row was already created (either through the approval flow
    or directly by an admin/seed script). It never grants access; it just fills
    in the missing profile row for an account that already has it. `role` is
    taken from the trusted JWT claim, never from the request body, so it can't
    be spoofed to something the account wasn't actually granted.
    """
    email = (user or {}).get("email")
    user_id = user.get("sub") or user.get("id")
    if not email:
        raise HTTPException(status_code=400, detail="JWT has no email claim")
    existing = get_my_profile(email)
    if existing:
        meta = existing.get("metadata") or {}
        return {"data": existing, "profile_complete": bool(meta.get("profile_complete"))}
    if not body.department or not body.department.strip():
        raise HTTPException(status_code=400, detail="Department is required to complete your profile")

    roles = user.get("roles") or []
    role = roles[0] if roles else None
    department = body.department.strip()
    record = {
        "email": email,
        "full_name": body.full_name or email.split("@")[0],
        "department": department,
        "department_id": resolve_department_id(department),
        "designation": body.designation or "Staff",
        "role": role,
        "user_id": user_id,
        "staff_number": f"SELF-{email.split('@')[0].upper()}",
        "metadata": body.metadata or {},
    }
    try:
        resp = db.table(TABLE_STAFF).insert(record).execute()
        created = resp.data[0] if resp.data else None
    except Exception as exc:
        logger.error(f"ensure_profile insert failed: {exc}")
        raise HTTPException(status_code=500, detail="Could not create staff profile")
    if not created:
        raise HTTPException(status_code=500, detail="Could not create staff profile")
    meta = created.get("metadata") or {}
    return {"data": created, "profile_complete": bool(meta.get("profile_complete"))}


@router.patch("/me/profile")
def patch_me(body: ProfilePatch, user: dict = Depends(verify_jwt)):
    email = (user or {}).get("email")
    if not email:
        raise HTTPException(status_code=400, detail="JWT has no email claim")
    patch_data = body.model_dump(exclude_none=True)
    updated = update_my_profile(email, patch_data)
    if not updated:
        raise HTTPException(status_code=404, detail="Staff record not found — contact admin")
    meta = updated.get("metadata") or {}
    return {"data": updated, "profile_complete": bool(meta.get("profile_complete"))}


@router.patch("/me/tour")
def patch_tour_state(body: Dict[str, Any], user: dict = Depends(verify_jwt)):
    """Merge-update the calling staff member's tour progress (completed/skipped/current_step)."""
    email = (user or {}).get("email")
    if not email:
        raise HTTPException(status_code=400, detail="JWT has no email claim")
    profile = get_my_profile(email)
    if not profile:
        raise HTTPException(status_code=404, detail="Staff record not found")
    merged_tour_state = {**(profile.get("tour_state") or {}), **body}
    updated = update_my_profile(email, {"tour_state": merged_tour_state})
    return {"data": updated.get("tour_state") if updated else merged_tour_state}
