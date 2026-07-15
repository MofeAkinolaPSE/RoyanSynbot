"""HMO / insurance coverage router for RoyanHealth."""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.constants import (
    COVERAGE_TYPES_ALLOWED,
    LIMIT_TYPES_ALLOWED,
    TABLE_COVERAGE_AUTHORIZATIONS,
    TABLE_COVERAGE_RULES,
    TABLE_HMO_PLANS,
    TABLE_HMOS,
    TABLE_PATIENT_INSURANCE,
    TABLE_SERVICE_CATALOG,
)
from src.db import audit_event, db
from src.middleware import require_role, verify_jwt
from src.services.coverage import CoverageInput, calculate_coverage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/coverage", tags=["Coverage"])


class HMOCreate(BaseModel):
    name: str = Field(..., min_length=1)
    code: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None
    notes: Optional[str] = None


class HMOPlanCreate(BaseModel):
    name: str = Field(..., min_length=1)
    plan_code: Optional[str] = None
    notes: Optional[str] = None


class ServiceCreate(BaseModel):
    service_code: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    category: str = "misc"
    base_price: float = Field(0.0, ge=0)


class PatientInsuranceCreate(BaseModel):
    patient_id: int
    hmo_id: int
    plan_id: Optional[int] = None
    membership_id: str = Field(..., min_length=1)
    status: str = "active"
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None
    is_primary: bool = True
    source: str = "synbot"
    notes: Optional[str] = None


class CoverageRuleCreate(BaseModel):
    hmo_id: int
    service_id: int
    plan_id: Optional[int] = None
    coverage_type: str = "none"
    coverage_value: float = Field(0.0, ge=0)
    requires_approval: bool = False
    limit_type: str = "none"
    limit_value: Optional[float] = Field(None, ge=0)
    notes: Optional[str] = None


class CoverageQuoteRequest(BaseModel):
    patient_id: int
    service_id: Optional[int] = None
    service_code: Optional[str] = None
    service_name: Optional[str] = None
    category: str = "misc"
    quantity: float = Field(1.0, gt=0)
    unit_price: Optional[float] = Field(None, ge=0)
    amount: Optional[float] = Field(None, ge=0)
    encounter_id: Optional[int] = None


@router.get("/hmos")
async def list_hmos(active_only: bool = True, user=Depends(verify_jwt)):
    query = db.table(TABLE_HMOS).select("*").order("name")
    if active_only:
        query = query.eq("is_active", True)
    result = query.execute()
    return {"hmos": result.data or [], "count": len(result.data or [])}


@router.post("/hmos", status_code=201)
async def create_hmo(payload: HMOCreate, user=Depends(require_role("admin"))):
    data = payload.model_dump(exclude_none=True)
    try:
        result = db.table(TABLE_HMOS).insert(data).execute()
    except Exception as exc:
        logger.error("HMO create failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to create HMO")
    hmo = (result.data or [data])[0]
    audit_event("hmo_created", {"hmo_id": hmo.get("id"), "name": payload.name}, actor_id=user.get("sub"), subject_type="hmo", subject_id=str(hmo.get("id") or ""))
    return {"ok": True, "hmo": hmo}


@router.post("/hmos/{hmo_id}/plans", status_code=201)
async def create_hmo_plan(hmo_id: int, payload: HMOPlanCreate, user=Depends(require_role("admin"))):
    hmo = db.table(TABLE_HMOS).select("id").eq("id", hmo_id).limit(1).execute()
    if not hmo.data:
        raise HTTPException(status_code=404, detail=f"HMO {hmo_id} not found")
    data = {**payload.model_dump(exclude_none=True), "hmo_id": hmo_id}
    try:
        result = db.table(TABLE_HMO_PLANS).insert(data).execute()
    except Exception as exc:
        logger.error("HMO plan create failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to create HMO plan")
    plan = (result.data or [data])[0]
    audit_event("hmo_plan_created", {"hmo_id": hmo_id, "plan_id": plan.get("id")}, actor_id=user.get("sub"), subject_type="hmo_plan", subject_id=str(plan.get("id") or ""))
    return {"ok": True, "plan": plan}


@router.get("/services")
async def list_services(category: Optional[str] = Query(None), user=Depends(verify_jwt)):
    query = db.table(TABLE_SERVICE_CATALOG).select("*").eq("is_active", True).order("name")
    if category:
        query = query.eq("category", category)
    result = query.execute()
    return {"services": result.data or [], "count": len(result.data or [])}


@router.post("/services", status_code=201)
async def create_service(payload: ServiceCreate, user=Depends(require_role("admin"))):
    data = payload.model_dump()
    try:
        result = db.table(TABLE_SERVICE_CATALOG).insert(data).execute()
    except Exception as exc:
        logger.error("Service create failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to create service")
    service = (result.data or [data])[0]
    audit_event("service_catalog_created", {"service_id": service.get("id"), "code": payload.service_code}, actor_id=user.get("sub"), subject_type="service", subject_id=str(service.get("id") or ""))
    return {"ok": True, "service": service}


@router.post("/patient-insurance", status_code=201)
async def create_patient_insurance(payload: PatientInsuranceCreate, user=Depends(verify_jwt)):
    data = payload.model_dump(exclude_none=True)
    try:
        result = db.table(TABLE_PATIENT_INSURANCE).insert(data).execute()
    except Exception as exc:
        logger.error("Patient insurance create failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to create patient insurance")
    policy = (result.data or [data])[0]
    audit_event("patient_insurance_created", {"patient_id": payload.patient_id, "hmo_id": payload.hmo_id}, actor_id=user.get("sub"), subject_type="patient", subject_id=str(payload.patient_id))
    return {"ok": True, "insurance": policy}


@router.post("/rules", status_code=201)
async def create_coverage_rule(payload: CoverageRuleCreate, user=Depends(require_role("admin"))):
    if payload.coverage_type not in COVERAGE_TYPES_ALLOWED:
        raise HTTPException(status_code=422, detail=f"coverage_type must be one of {sorted(COVERAGE_TYPES_ALLOWED)}")
    if payload.limit_type not in LIMIT_TYPES_ALLOWED:
        raise HTTPException(status_code=422, detail=f"limit_type must be one of {sorted(LIMIT_TYPES_ALLOWED)}")
    data = payload.model_dump(exclude_none=True)
    try:
        result = db.table(TABLE_COVERAGE_RULES).insert(data).execute()
    except Exception as exc:
        logger.error("Coverage rule create failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to create coverage rule")
    rule = (result.data or [data])[0]
    audit_event("coverage_rule_created", {"rule_id": rule.get("id"), "hmo_id": payload.hmo_id, "service_id": payload.service_id}, actor_id=user.get("sub"), subject_type="coverage_rule", subject_id=str(rule.get("id") or ""))
    return {"ok": True, "rule": rule}


@router.get("/rules")
async def list_coverage_rules(hmo_id: Optional[int] = None, service_id: Optional[int] = None, user=Depends(verify_jwt)):
    query = db.table(TABLE_COVERAGE_RULES).select("*").order("created_at", desc=True).limit(500)
    if hmo_id:
        query = query.eq("hmo_id", hmo_id)
    if service_id:
        query = query.eq("service_id", service_id)
    result = query.execute()
    return {"rules": result.data or [], "count": len(result.data or [])}


@router.post("/quote")
async def quote_coverage(payload: CoverageQuoteRequest, user=Depends(verify_jwt)):
    quote = calculate_coverage(CoverageInput(**payload.model_dump()))
    return {"ok": True, "quote": quote}


# ─── HMO Authorization Workflow ──────────────────────────────────────────────

class AuthorizationCreate(BaseModel):
    patient_id: int
    service_id: Optional[int] = None
    service_name: Optional[str] = None
    hmo_id: Optional[int] = None
    hmo_name: Optional[str] = None
    requested_by: Optional[str] = None
    notes: Optional[str] = None


class AuthorizationResolve(BaseModel):
    status: str  # "approved" | "rejected"
    approval_code: Optional[str] = None
    notes: Optional[str] = None


@router.post("/authorizations", status_code=201)
async def request_authorization(payload: AuthorizationCreate, user=Depends(verify_jwt)):
    """Create a pre-authorization request for a service that requires HMO approval."""
    data = {
        **payload.model_dump(exclude_none=True),
        "status": "pending",
        "requested_by": payload.requested_by or user.get("email") or user.get("sub"),
    }
    result = db.table(TABLE_COVERAGE_AUTHORIZATIONS).insert(data).execute()
    auth = (result.data or [data])[0]
    audit_event("authorization_requested", {"patient_id": payload.patient_id, "service_name": payload.service_name}, actor_id=user.get("sub"), subject_type="authorization", subject_id=str(auth.get("id") or ""))
    return {"ok": True, "authorization": auth}


@router.get("/authorizations")
async def list_authorizations(
    status: Optional[str] = None,
    hmo_id: Optional[int] = None,
    limit: int = 100,
    user=Depends(verify_jwt),
):
    query = db.table(TABLE_COVERAGE_AUTHORIZATIONS).select("*").order("created_at", desc=True).limit(limit)
    if status:
        query = query.eq("status", status)
    if hmo_id:
        query = query.eq("hmo_id", hmo_id)
    result = query.execute()
    return {"authorizations": result.data or [], "count": len(result.data or [])}


@router.patch("/authorizations/{auth_id}")
async def resolve_authorization(auth_id: int, payload: AuthorizationResolve, user=Depends(require_role("admin", "finance"))):
    if payload.status not in ("approved", "rejected"):
        raise HTTPException(status_code=422, detail="status must be 'approved' or 'rejected'")
    update = {
        "status": payload.status,
        "resolved_by": user.get("email") or user.get("sub"),
    }
    if payload.approval_code:
        update["approval_code"] = payload.approval_code
    if payload.notes:
        update["notes"] = payload.notes
    result = db.table(TABLE_COVERAGE_AUTHORIZATIONS).update(update).eq("id", auth_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail=f"Authorization {auth_id} not found")
    audit_event(f"authorization_{payload.status}", {"approval_code": payload.approval_code}, actor_id=user.get("sub"), subject_type="authorization", subject_id=str(auth_id))
    return {"ok": True, "authorization": result.data[0]}
