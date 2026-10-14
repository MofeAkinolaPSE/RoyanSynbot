"""Admin review queue for public staff self-registrations.

Approving a registration is the moment a royan_users row (login identity) and
a royan_staff row (clinical/HR identity) are both created and linked via
user_id — see public_registration.py for how a submission gets here.
"""
from __future__ import annotations

import datetime as dt
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.constants import TABLE_STAFF, TABLE_STAFF_REGISTRATIONS, TABLE_USERS
from src.db import db, audit_event
from src.middleware import require_role

router = APIRouter(prefix="/staff/registrations", tags=["staff-registrations-admin"])
logger = logging.getLogger("staff_registrations_admin")

_SAFE_COLUMNS = (
    "id,email,full_name,role,department,department_id,designation,phone,kyc_details,"
    "status,rejection_reason,reviewed_by,reviewed_at,created_staff_id,created_user_id,"
    "submitted_ip,created_at,updated_at"
)


class ApproveRequest(BaseModel):
    department_id_override: Optional[int] = None
    # the person's existing HR record to attach the login to (see GET /{id}/hr-matches), or create_new
    link_staff_id: Optional[str] = None
    create_new: bool = False
    approval_reason: str = Field(..., min_length=1, max_length=1000)
    attestation_text: str = Field(..., min_length=1, max_length=1000)


class RejectRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=1000)


@router.get("")
def list_registrations(status: str = "pending", limit: int = 50, user=Depends(require_role("admin"))):
    query = db.table(TABLE_STAFF_REGISTRATIONS).select(_SAFE_COLUMNS)
    if status != "all":
        query = query.eq("status", status)
    resp = query.order("created_at", desc=True).limit(limit).execute()
    return {"data": resp.data or []}


@router.get("/{registration_id}")
def get_registration(registration_id: str, user=Depends(require_role("admin"))):
    resp = (
        db.table(TABLE_STAFF_REGISTRATIONS)
        .select(_SAFE_COLUMNS)
        .eq("id", registration_id)
        .limit(1)
        .execute()
    )
    if not resp.data:
        raise HTTPException(status_code=404, detail="Registration not found")
    return {"data": resp.data[0]}


def _load_pending(registration_id: str) -> dict:
    resp = (
        db.table(TABLE_STAFF_REGISTRATIONS)
        .select("*")
        .eq("id", registration_id)
        .limit(1)
        .execute()
    )
    if not resp.data:
        raise HTTPException(status_code=404, detail="Registration not found")
    reg = resp.data[0]
    if reg.get("status") != "pending":
        raise HTTPException(status_code=409, detail=f"Registration is already {reg.get('status')}")
    return reg


@router.get("/{registration_id}/hr-matches")
def registration_hr_matches(registration_id: str, user=Depends(require_role("admin"))):
    """HR records this person may already have - same email (certain) or same name (likely)."""
    from src.services.staff_onboarding import hr_matches
    reg = _load_pending(registration_id)
    return {"data": hr_matches(reg)}


@router.post("/{registration_id}/approve")
def approve_registration(registration_id: str, body: ApproveRequest, user=Depends(require_role("admin"))):
    """Create the login and attach it to the person's HR record (or create one) - in one transaction,
    so HR never holds the same person twice (services/staff_onboarding.py)."""
    from src.services.staff_onboarding import OnboardingError, approve
    reg = _load_pending(registration_id)
    admin_id = user.get("sub") or user.get("user_id")
    try:
        out = approve(reg, str(admin_id), body.link_staff_id, body.create_new, body.department_id_override)
    except OnboardingError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as exc:
        logger.error(f"approve_registration failed for {registration_id}: {exc}")
        raise HTTPException(status_code=500, detail="Could not approve registration")
    audit_event(
        "staff_registration_approved",
        {"email": reg["email"], "role": reg["role"], "hr_record": out["mode"], "staff_id": out["staff_id"], "filled": out["filled"]},
        actor_id=admin_id,
        subject_type="staff_registration",
        subject_id=registration_id,
        approval_reason=body.approval_reason,
        attestation_text=body.attestation_text,
    )
    return out


@router.post("/{registration_id}/reject")
def reject_registration(registration_id: str, body: RejectRequest, user=Depends(require_role("admin"))):
    reg = _load_pending(registration_id)
    admin_id = user.get("sub") or user.get("user_id")
    now = dt.datetime.now(dt.timezone.utc).isoformat()

    db.table(TABLE_STAFF_REGISTRATIONS).update({
        "status": "rejected",
        "rejection_reason": body.reason,
        "reviewed_by": admin_id,
        "reviewed_at": now,
    }).eq("id", registration_id).execute()

    audit_event(
        "staff_registration_rejected",
        {"email": reg["email"], "role": reg["role"], "reason": body.reason},
        actor_id=admin_id,
        subject_type="staff_registration",
        subject_id=registration_id,
    )
    return {"status": "rejected"}
