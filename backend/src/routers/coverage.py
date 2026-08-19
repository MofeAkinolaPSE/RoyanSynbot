"""HMO / insurance coverage router for RoyanHealth."""
from __future__ import annotations

import datetime as dt
import logging
from typing import Optional

import psycopg2.extras
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.constants import (
    COVERAGE_TYPES_ALLOWED,
    LIMIT_TYPES_ALLOWED,
    TABLE_COVERAGE_AUTHORIZATIONS,
    TABLE_COVERAGE_RULES,
    TABLE_HMO_PLANS,
    TABLE_HMOS,
    TABLE_INSURANCE_CLAIMS,
    TABLE_PATIENT_INSURANCE,
    TABLE_PATIENTS,
    TABLE_SERVICE_CATALOG,
)

CLAIM_STATUS_ALLOWED = {"submitted", "pre_authorised", "approved", "rejected", "paid", "disputed"}
from src.db import audit_event, db
from src.middleware import require_role, verify_jwt
from src.services.coverage import CoverageInput, calculate_coverage, estimate_bill_coverage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/coverage", tags=["Coverage"])


class HMOCreate(BaseModel):
    name: str = Field(..., min_length=1)
    code: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None
    notes: Optional[str] = None


class HMOUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1)
    code: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None


class HMOPlanCreate(BaseModel):
    name: str = Field(..., min_length=1)
    plan_code: Optional[str] = None
    notes: Optional[str] = None


class ServiceCreate(BaseModel):
    service_code: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    category: str = "misc"
    base_price: float = Field(0.0, ge=0)


class ServiceUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1)
    category: Optional[str] = None
    base_price: Optional[float] = Field(None, ge=0)
    is_active: Optional[bool] = None


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
    # Flexible bucket for per-HMO identity fields (employer, dependent
    # relationship, etc.) — exact fields vary by HMO and are still pending
    # from the client, so this ships now without forcing a schema change
    # once they arrive.
    identity_data: Optional[dict] = None


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


class CoverageRuleUpdate(BaseModel):
    coverage_type: Optional[str] = None
    coverage_value: Optional[float] = Field(None, ge=0)
    requires_approval: Optional[bool] = None
    limit_type: Optional[str] = None
    limit_value: Optional[float] = Field(None, ge=0)
    is_active: Optional[bool] = None
    notes: Optional[str] = None


class PatientInsuranceUpdate(BaseModel):
    hmo_id: Optional[int] = None
    plan_id: Optional[int] = None
    membership_id: Optional[str] = None
    status: Optional[str] = None
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None
    is_primary: Optional[bool] = None
    notes: Optional[str] = None
    identity_data: Optional[dict] = None


class ClaimUpdate(BaseModel):
    status: Optional[str] = None
    approved_amount: Optional[float] = Field(None, ge=0)
    authorisation_code: Optional[str] = None
    notes: Optional[str] = None


class BillCoverageEstimateRequest(BaseModel):
    patient_id: int
    consultation_fee: float = Field(0.0, ge=0)
    lab_charges: float = Field(0.0, ge=0)
    pharmacy_charges: float = Field(0.0, ge=0)
    ward_charges: float = Field(0.0, ge=0)
    procedure_charges: float = Field(0.0, ge=0)
    miscellaneous: float = Field(0.0, ge=0)


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


@router.patch("/hmos/{hmo_id}")
async def update_hmo(hmo_id: int, payload: HMOUpdate, user=Depends(require_role("admin"))):
    existing = db.table(TABLE_HMOS).select("id").eq("id", hmo_id).limit(1).execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail=f"HMO {hmo_id} not found")
    updates = payload.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=422, detail="No fields to update")
    try:
        result = db.table(TABLE_HMOS).update(updates).eq("id", hmo_id).execute()
    except Exception as exc:
        logger.error("HMO update failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to update HMO")
    hmo = (result.data or [{"id": hmo_id, **updates}])[0]
    audit_event("hmo_updated", {"hmo_id": hmo_id, "fields": list(updates.keys())}, actor_id=user.get("sub"), subject_type="hmo", subject_id=str(hmo_id))
    return {"ok": True, "hmo": hmo}


@router.get("/hmos/{hmo_id}/plans")
async def list_hmo_plans(hmo_id: int, active_only: bool = True, user=Depends(verify_jwt)):
    query = db.table(TABLE_HMO_PLANS).select("*").eq("hmo_id", hmo_id).order("name")
    if active_only:
        query = query.eq("is_active", True)
    result = query.execute()
    return {"plans": result.data or [], "count": len(result.data or [])}


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


@router.patch("/services/{service_id}")
async def update_service(service_id: int, payload: ServiceUpdate, user=Depends(require_role("admin"))):
    """Price/edit an existing catalog row — the seeded rows (CONSULT-GEN etc.)
    ship with base_price=0, and there was previously no way to fix that
    short of deleting and re-adding under a now-conflicting service_code."""
    existing = db.table(TABLE_SERVICE_CATALOG).select("id").eq("id", service_id).limit(1).execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail=f"Service {service_id} not found")

    updates = payload.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=422, detail="No fields to update")

    try:
        result = db.table(TABLE_SERVICE_CATALOG).update(updates).eq("id", service_id).execute()
    except Exception as exc:
        logger.error("Service update failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to update service")
    service = (result.data or [{"id": service_id, **updates}])[0]
    audit_event("service_catalog_updated", {"service_id": service_id, "fields": list(updates.keys())}, actor_id=user.get("sub"), subject_type="service", subject_id=str(service_id))
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


@router.get("/patient-insurance")
async def list_patient_insurance(patient_id: int = Query(...), user=Depends(verify_jwt)):
    """Full policy history for one patient (not just the active/primary one
    get_active_patient_insurance() uses internally) -- for the patient HMO
    workpanel, which needs to show and let staff change enrollment."""
    result = db.table(TABLE_PATIENT_INSURANCE).select("*").eq("patient_id", patient_id).order("created_at", desc=True).execute()
    rows = result.data or []
    hmo_ids = list({r["hmo_id"] for r in rows if r.get("hmo_id")})
    if hmo_ids:
        hmos = db.table(TABLE_HMOS).select("id,name").in_("id", hmo_ids).execute()
        hmos_by_id = {h["id"]: h["name"] for h in (hmos.data or [])}
        for r in rows:
            r["hmo_name"] = hmos_by_id.get(r.get("hmo_id"))
    return {"policies": rows, "count": len(rows)}


@router.patch("/patient-insurance/{policy_id}")
async def update_patient_insurance(policy_id: int, payload: PatientInsuranceUpdate, user=Depends(verify_jwt)):
    existing = db.table(TABLE_PATIENT_INSURANCE).select("id,patient_id").eq("id", policy_id).limit(1).execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail=f"Patient insurance record {policy_id} not found")
    updates = payload.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=422, detail="No fields to update")
    try:
        result = db.table(TABLE_PATIENT_INSURANCE).update(updates).eq("id", policy_id).execute()
    except Exception as exc:
        logger.error("Patient insurance update failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to update patient insurance (e.g. another active primary policy already exists for this patient)")
    policy = (result.data or [{"id": policy_id, **updates}])[0]
    audit_event("patient_insurance_updated", {"policy_id": policy_id, "fields": list(updates.keys())}, actor_id=user.get("sub"), subject_type="patient", subject_id=str(existing.data[0].get("patient_id")))
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


@router.patch("/rules/{rule_id}")
async def update_coverage_rule(rule_id: int, payload: CoverageRuleUpdate, user=Depends(require_role("admin"))):
    if payload.coverage_type and payload.coverage_type not in COVERAGE_TYPES_ALLOWED:
        raise HTTPException(status_code=422, detail=f"coverage_type must be one of {sorted(COVERAGE_TYPES_ALLOWED)}")
    if payload.limit_type and payload.limit_type not in LIMIT_TYPES_ALLOWED:
        raise HTTPException(status_code=422, detail=f"limit_type must be one of {sorted(LIMIT_TYPES_ALLOWED)}")
    existing = db.table(TABLE_COVERAGE_RULES).select("id").eq("id", rule_id).limit(1).execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail=f"Coverage rule {rule_id} not found")
    updates = payload.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=422, detail="No fields to update")
    try:
        result = db.table(TABLE_COVERAGE_RULES).update(updates).eq("id", rule_id).execute()
    except Exception as exc:
        logger.error("Coverage rule update failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to update coverage rule")
    rule = (result.data or [{"id": rule_id, **updates}])[0]
    audit_event("coverage_rule_updated", {"rule_id": rule_id, "fields": list(updates.keys())}, actor_id=user.get("sub"), subject_type="coverage_rule", subject_id=str(rule_id))
    return {"ok": True, "rule": rule}


@router.get("/patients")
async def list_covered_patients(
    hmo_id: Optional[int] = Query(None),
    search: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    user=Depends(verify_jwt),
):
    """Patient roster under HMO cover — matches Hope's HMO Dashboard patient
    list (registration date, name, insurance no., age/gender, HMO, status).
    Joins the modern royan_patient_insurance table, falling back to the
    legacy royan_patients.hmo_provider field for patients registered before
    that table existed (same fallback used elsewhere in this app)."""
    conn = db.pool.getconn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            sql = """
                SELECT p.id AS patient_id, p.mrn, p.first_name, p.last_name,
                       p.date_of_birth, p.gender, p.registered_at, p.patient_type,
                       COALESCE(h.name, p.hmo_provider) AS hmo_name,
                       pi.hmo_id AS hmo_id,
                       COALESCE(pi.membership_id, p.hmo_id::text) AS membership_id,
                       COALESCE(pi.status, 'active') AS status
                FROM public.royan_patients p
                LEFT JOIN LATERAL (
                    SELECT * FROM public.royan_patient_insurance ins
                    WHERE ins.patient_id = p.id AND ins.is_primary = true AND ins.status = 'active'
                    ORDER BY ins.created_at DESC LIMIT 1
                ) pi ON true
                LEFT JOIN public.royan_hmos h ON h.id = pi.hmo_id
                WHERE (pi.id IS NOT NULL OR NULLIF(trim(p.hmo_provider), '') IS NOT NULL)
            """
            params: list = []
            if hmo_id:
                sql += " AND pi.hmo_id = %s"
                params.append(hmo_id)
            if search:
                sql += " AND (p.first_name ILIKE %s OR p.last_name ILIKE %s OR p.mrn ILIKE %s)"
                like = f"%{search.strip()}%"
                params.extend([like, like, like])
            sql += " ORDER BY p.registered_at DESC NULLS LAST LIMIT %s"
            params.append(limit)
            cur.execute(sql, tuple(params))
            rows = [dict(r) for r in cur.fetchall()]
        conn.commit()
    except Exception as exc:
        try:
            conn.rollback()
        except Exception:
            pass
        logger.error("Covered-patients roster query failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to load HMO patient roster")
    finally:
        db.pool.putconn(conn)

    for r in rows:
        r["patient_name"] = f"{r.pop('first_name', '') or ''} {r.pop('last_name', '') or ''}".strip() or None

    return {"patients": rows, "count": len(rows)}


@router.post("/quote")
async def quote_coverage(payload: CoverageQuoteRequest, user=Depends(verify_jwt)):
    quote = calculate_coverage(CoverageInput(**payload.model_dump()))
    return {"ok": True, "quote": quote}


@router.post("/estimate-bill")
async def estimate_bill(payload: BillCoverageEstimateRequest, user=Depends(verify_jwt)):
    """Auto-suggest the HMO-covered portion of a flat-category bill (the
    GenerateBillPanel form) so staff see the discount already applied
    instead of typing it in by hand — matches Hope's behavior where an
    HMO-attached patient's bill template already reflects their coverage."""
    result = estimate_bill_coverage(payload.patient_id, {
        "consultation_fee": payload.consultation_fee,
        "lab_charges": payload.lab_charges,
        "pharmacy_charges": payload.pharmacy_charges,
        "ward_charges": payload.ward_charges,
        "procedure_charges": payload.procedure_charges,
        "miscellaneous": payload.miscellaneous,
    })
    return result


# ─── Claims ───────────────────────────────────────────────────────────────────

@router.get("/claims")
async def list_claims(
    patient_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    hmo_provider_id: Optional[int] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    user=Depends(verify_jwt),
):
    query = db.table(TABLE_INSURANCE_CLAIMS).select("*").order("submitted_at", desc=True).limit(limit)
    if patient_id:
        query = query.eq("patient_id", patient_id)
    if status:
        query = query.eq("status", status)
    if hmo_provider_id:
        query = query.eq("hmo_provider_id", hmo_provider_id)
    result = query.execute()
    claims = result.data or []

    patient_ids = list({c["patient_id"] for c in claims if c.get("patient_id")})
    patients_by_id: dict[int, dict] = {}
    if patient_ids:
        patients = db.table(TABLE_PATIENTS).select("id,mrn,first_name,last_name").in_("id", patient_ids).execute()
        patients_by_id = {p["id"]: p for p in (patients.data or [])}
    for c in claims:
        p = patients_by_id.get(c.get("patient_id"))
        c["patient_name"] = f"{p['first_name']} {p['last_name']}" if p else None
        c["mrn"] = p.get("mrn") if p else None

    return {"claims": claims, "count": len(claims)}


@router.patch("/claims/{claim_id}")
async def update_claim(claim_id: int, payload: ClaimUpdate, user=Depends(require_role("admin", "finance"))):
    """Confirm/progress a claim (submitted -> pre_authorised/approved/rejected
    -> paid/disputed). Moving to 'paid' auto-stamps settled_at unless the
    caller already knows a specific settlement date -- that's not exposed
    here since staff confirming a claim are marking "this happened now",
    not backdating one."""
    if payload.status and payload.status not in CLAIM_STATUS_ALLOWED:
        raise HTTPException(status_code=422, detail=f"status must be one of {sorted(CLAIM_STATUS_ALLOWED)}")
    existing = db.table(TABLE_INSURANCE_CLAIMS).select("id").eq("id", claim_id).limit(1).execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail=f"Claim {claim_id} not found")
    updates = payload.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=422, detail="No fields to update")
    if updates.get("status") == "paid":
        updates["settled_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    try:
        result = db.table(TABLE_INSURANCE_CLAIMS).update(updates).eq("id", claim_id).execute()
    except Exception as exc:
        logger.error("Claim update failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to update claim")
    claim = (result.data or [{"id": claim_id, **updates}])[0]
    audit_event(f"claim_{payload.status or 'updated'}", {"claim_id": claim_id, "fields": list(updates.keys())}, actor_id=user.get("sub"), subject_type="claim", subject_id=str(claim_id))
    return {"ok": True, "claim": claim}


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
        "status": "requested",
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
    query = db.table(TABLE_COVERAGE_AUTHORIZATIONS).select("*").order("requested_at", desc=True).limit(limit)
    if status:
        query = query.eq("status", status)
    if hmo_id:
        query = query.eq("hmo_id", hmo_id)
    result = query.execute()
    authorizations = result.data or []

    patient_ids = list({a["patient_id"] for a in authorizations if a.get("patient_id")})
    patients_by_id: dict[int, dict] = {}
    if patient_ids:
        patients = db.table(TABLE_PATIENTS).select("id,mrn,first_name,last_name").in_("id", patient_ids).execute()
        patients_by_id = {p["id"]: p for p in (patients.data or [])}

    for a in authorizations:
        p = patients_by_id.get(a.get("patient_id"))
        a["patient_name"] = f"{p['first_name']} {p['last_name']}" if p else None
        a["mrn"] = p.get("mrn") if p else None

    return {"authorizations": authorizations, "count": len(authorizations)}


@router.patch("/authorizations/{auth_id}")
async def resolve_authorization(auth_id: int, payload: AuthorizationResolve, user=Depends(require_role("admin", "finance"))):
    if payload.status not in ("approved", "rejected"):
        raise HTTPException(status_code=422, detail="status must be 'approved' or 'rejected'")
    update = {
        "status": payload.status,
        "decided_by": user.get("email") or user.get("sub"),
    }
    if payload.approval_code:
        update["authorization_code"] = payload.approval_code
    if payload.notes:
        update["notes"] = payload.notes
    result = db.table(TABLE_COVERAGE_AUTHORIZATIONS).update(update).eq("id", auth_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail=f"Authorization {auth_id} not found")
    audit_event(f"authorization_{payload.status}", {"approval_code": payload.approval_code}, actor_id=user.get("sub"), subject_type="authorization", subject_id=str(auth_id))
    return {"ok": True, "authorization": result.data[0]}
