"""Public, unauthenticated staff self-registration.

Distinct from staff_me.py (which assumes an already-authenticated caller):
these endpoints are reachable by anyone, before any royan_users row exists.
Submissions land in royan_staff_registrations as 'pending' — no login is
possible until an admin approves via staff_registrations_admin.py.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field, field_validator

from src.auth_utils import hash_password, normalize_email, validate_password_strength
from src.constants import STAFF_ROLES, TABLE_STAFF_REGISTRATIONS, TABLE_USERS
from src.db import db, audit_event
from src.middleware import rate_limit
from src.services.staff_ops import resolve_department_id

router = APIRouter(tags=["public-registration"])
logger = logging.getLogger("public_registration")


class RegistrationRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1, max_length=200)
    full_name: str = Field(..., min_length=1, max_length=200)
    role: str
    department: str = Field(..., min_length=1, max_length=100)
    designation: Optional[str] = Field(None, max_length=100)
    phone: Optional[str] = Field(None, max_length=30)
    kyc_details: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        if v not in STAFF_ROLES:
            raise ValueError(f"role must be one of {STAFF_ROLES}")
        return v


@router.get("/roles")
def list_roles():
    """Public role vocabulary — the single source of truth other than STAFF_ROLES itself."""
    return {"roles": STAFF_ROLES}


@router.get("/departments")
def list_departments_public():
    """Public department list for the registration form (names only, no auth required)."""
    resp = (
        db.table("royan_departments")
        .select("id,code,name,short_name")
        .eq("is_active", True)
        .order("name")
        .execute()
    )
    return {"records": resp.data or []}


@router.post("/register", status_code=201)
def register(request: Request, body: RegistrationRequest):
    email = normalize_email(body.email)
    rate_limit(request, key=f"register:{email}")
    validate_password_strength(body.password)

    existing_user = db.table(TABLE_USERS).select("id").eq("email", email).limit(1).execute()
    if existing_user.data:
        raise HTTPException(status_code=409, detail="An account with this email already exists")

    existing_pending = (
        db.table(TABLE_STAFF_REGISTRATIONS)
        .select("id")
        .eq("email", email)
        .eq("status", "pending")
        .limit(1)
        .execute()
    )
    if existing_pending.data:
        raise HTTPException(status_code=409, detail="A registration for this email is already pending review")

    department_id = resolve_department_id(body.department)
    record = {
        "email": email,
        "hashed_password": hash_password(body.password),
        "full_name": body.full_name.strip(),
        "role": body.role,
        "department": body.department.strip(),
        "department_id": department_id,
        "designation": (body.designation or "").strip() or None,
        "phone": (body.phone or "").strip() or None,
        "kyc_details": body.kyc_details or {},
        "submitted_ip": request.client.host if request.client else None,
    }
    try:
        resp = db.table(TABLE_STAFF_REGISTRATIONS).insert(record).execute()
        created = resp.data[0] if resp.data else None
    except Exception as exc:
        logger.error(f"registration insert failed: {exc}")
        raise HTTPException(status_code=500, detail="Could not submit registration")

    audit_event(
        "staff_registration_submitted",
        {"email": email, "role": body.role, "department": body.department},
        subject_type="staff_registration",
        subject_id=created.get("id") if created else None,
    )
    return {"status": "pending_review", "registration_id": created.get("id") if created else None}
