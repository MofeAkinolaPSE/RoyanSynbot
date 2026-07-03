from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Any, Dict, Optional
import logging

from src.middleware import verify_jwt
from src.services.staff_ops import get_my_profile, update_my_profile, get_staff_by_email

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
