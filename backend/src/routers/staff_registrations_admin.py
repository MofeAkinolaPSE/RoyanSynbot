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


@router.post("/{registration_id}/approve")
def approve_registration(registration_id: str, body: ApproveRequest, user=Depends(require_role("admin"))):
    reg = _load_pending(registration_id)
    admin_id = user.get("sub") or user.get("user_id")
    now = dt.datetime.now(dt.timezone.utc).isoformat()

    try:
        user_resp = db.table(TABLE_USERS).insert({
            "email": reg["email"],
            "hashed_password": reg["hashed_password"],
            "roles": [reg["role"]],
            "is_active": True,
        }).execute()
        new_user = user_resp.data[0] if user_resp.data else None
        if not new_user:
            raise RuntimeError("no row returned from royan_users insert")

        department_id = body.department_id_override if body.department_id_override is not None else reg.get("department_id")
        kyc = reg.get("kyc_details") or {}
        staff_resp = db.table(TABLE_STAFF).insert({
            "staff_number": f"REG-{reg['id'][:8].upper()}",
            "full_name": reg["full_name"],
            "department": reg.get("department") or "Unassigned",
            "department_id": department_id,
            "designation": reg.get("designation") or "Staff",
            "role": reg["role"],
            "email": reg["email"],
            "phone": reg.get("phone"),
            "metadata": kyc,
            "specialty": kyc.get("specialty"),
            "license_number": kyc.get("medical_council_number"),
            "user_id": new_user["id"],
        }).execute()
        new_staff = staff_resp.data[0] if staff_resp.data else None
        if not new_staff:
            raise RuntimeError("no row returned from royan_staff insert")

        db.table(TABLE_STAFF_REGISTRATIONS).update({
            "status": "approved",
            "reviewed_by": admin_id,
            "reviewed_at": now,
            "created_staff_id": new_staff["id"],
            "created_user_id": new_user["id"],
        }).eq("id", registration_id).execute()
    except Exception as exc:
        logger.error(f"approve_registration failed for {registration_id}: {exc}")
        raise HTTPException(status_code=500, detail="Could not approve registration")

    audit_event(
        "staff_registration_approved",
        {"email": reg["email"], "role": reg["role"]},
        actor_id=admin_id,
        subject_type="staff_registration",
        subject_id=registration_id,
        approval_reason=body.approval_reason,
        attestation_text=body.attestation_text,
    )
    return {"status": "approved", "staff_id": new_staff["id"], "user_id": new_user["id"]}


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
