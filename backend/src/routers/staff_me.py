from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Any, Dict, Optional
import logging

from src.middleware import verify_jwt
from src.services.staff_ops import get_my_profile, update_my_profile, get_staff_by_email
from src.db import db
from src.constants import TABLE_STAFF

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


@router.post("/me/register")
def register_me(body: ProfilePatch, user: dict = Depends(verify_jwt)):
    """Self-registration: creates a staff record for a user who authenticated but has no staff row yet."""
    email = (user or {}).get("email")
    if not email:
        raise HTTPException(status_code=400, detail="JWT has no email claim")
    existing = get_my_profile(email)
    if existing:
        return {"data": existing, "profile_complete": bool((existing.get("metadata") or {}).get("profile_complete"))}
    record = {
        "email": email.lower().strip(),
        "full_name": body.full_name or email.split("@")[0],
        "department": body.department or "General",
        "designation": body.designation or "Staff",
        "staff_number": f"AUTO-{email.split('@')[0].upper()}",
        "metadata": body.metadata or {},
    }
    try:
        resp = db.table(TABLE_STAFF).insert(record).execute()
        created = resp.data[0] if resp.data else None
    except Exception as exc:
        logger.error(f"register_me insert failed: {exc}")
        raise HTTPException(status_code=500, detail="Could not create staff record")
    return {"data": created, "profile_complete": False}
