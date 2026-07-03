"""MDM Governance Router — Blueprint Chapter 4.3–4.11.

Implements the Master Data Management lifecycle approval workflow over
all reference/catalogue entities: departments, staff, lab tests, drugs,
diagnoses, procedures.

Every change to MDM entities (create / update / deprecate / reactivate)
MUST flow through this router so that:
  - A change request is logged in royan_mdm_change_requests
  - An admin/data_steward reviews and approves/rejects before any live
    data changes occur
  - Every publish action is recorded in royan_mdm_audit with before/after

Endpoints:
  POST /api/v1/mdm/{entity_type}/request      — submit draft change request
  GET  /api/v1/mdm/requests                   — list pending (admin/data_steward)
  GET  /api/v1/mdm/requests/{id}              — get single request
  POST /api/v1/mdm/requests/{id}/submit       — move draft → pending_review
  POST /api/v1/mdm/requests/{id}/approve      — approve + publish (admin only)
  POST /api/v1/mdm/requests/{id}/reject       — reject with notes (admin only)
  POST /api/v1/mdm/requests/{id}/withdraw     — withdraw own draft request
  POST /api/v1/mdm/{entity_type}/{id}/deprecate — soft-delete (admin only)
  GET  /api/v1/mdm/{entity_type}              — list records (active; or all)
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

import psycopg2.extras
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.db import db, audit_event
from src.middleware import verify_jwt, require_role
from src.services.event_service import emit_clinical_event

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/mdm", tags=["MDM Governance"])

# ─────────────────────────────────────────────────────────────────────────────
# Entity type → actual table name mapping
# ─────────────────────────────────────────────────────────────────────────────

_ENTITY_TABLES: Dict[str, str] = {
    "department":          "royan_departments",
    "staff":               "royan_staff",
    "lab_catalog":         "royan_lab_catalog",
    "drug_formulary":      "royan_drug_formulary",
    "diagnosis_catalog":   "royan_diagnosis_catalog",
    "procedure_catalog":   "royan_procedure_catalog",
}

VALID_ENTITY_TYPES = set(_ENTITY_TABLES.keys())

# Which columns to update per entity type when publishing a change request
# (columns that actually exist in those tables — subset of proposed_data keys)
_ENTITY_WRITABLE_FIELDS: Dict[str, set] = {
    "department":          {"name", "short_name", "dept_type", "parent_id", "is_active", "code"},
    "staff":               {"title", "first_name", "last_name", "role", "specialty", "department_id", "license_number", "is_active"},
    "lab_catalog":         {"name", "loinc_code", "category", "specimen_type", "unit", "reference_range", "turnaround_hours", "base_price", "is_active"},
    "drug_formulary":      {"generic_name", "brand_name", "drug_class", "form", "strength", "route", "requires_prescription", "is_controlled", "unit_cost", "is_active"},
    "diagnosis_catalog":   {"icd_code", "description", "category", "subcategory", "is_clinical_default", "is_active"},
    "procedure_catalog":   {"code", "name", "category", "department_id", "duration_minutes", "requires_anaesthesia", "requires_consent", "base_price", "is_active"},
}


# ─────────────────────────────────────────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────────────────────────────────────────

class ChangeRequestCreate(BaseModel):
    entity_id: Optional[int] = None     # None for 'create' action
    action: str = Field(..., description="create|update|deprecate|reactivate")
    proposed_data: Dict[str, Any] = Field(..., min_length=1)
    notes: Optional[str] = None

    model_config = {"extra": "ignore"}


class ReviewDecision(BaseModel):
    notes: Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _get_conn():
    return db.pool.getconn()


def _put_conn(conn):
    db.pool.putconn(conn)


def _get_request(request_id: int, conn) -> Dict:
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            "SELECT * FROM public.royan_mdm_change_requests WHERE id = %s",
            (request_id,),
        )
        row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"MDM change request {request_id} not found")
    return dict(row)


def _get_entity_current(entity_type: str, entity_id: int, conn) -> Optional[Dict]:
    table = _ENTITY_TABLES[entity_type]
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(f"SELECT * FROM public.{table} WHERE id = %s", (entity_id,))
        row = cur.fetchone()
    return dict(row) if row else None


def _write_mdm_audit(request_id, entity_type, entity_id, action,
                     before_data, after_data, performed_by, conn) -> None:
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO public.royan_mdm_audit
                    (change_request_id, entity_type, entity_id, action,
                     before_data, after_data, performed_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    request_id, entity_type, entity_id, action,
                    json.dumps(before_data or {}), json.dumps(after_data or {}), performed_by,
                ),
            )
    except Exception as exc:
        logger.warning("MDM audit write failed: %s", exc)


def _publish_change(entity_type: str, entity_id: Optional[int],
                    action: str, proposed_data: Dict, conn) -> Optional[int]:
    """Apply the approved change to the live MDM table. Returns new/updated entity id."""
    table = _ENTITY_TABLES[entity_type]
    writable = _ENTITY_WRITABLE_FIELDS.get(entity_type, set())
    clean = {k: v for k, v in proposed_data.items() if k in writable}

    with conn.cursor() as cur:
        if action == "create":
            if not clean:
                raise HTTPException(status_code=422, detail="proposed_data contains no writable fields")
            cols = ", ".join(clean.keys())
            placeholders = ", ".join(["%s"] * len(clean))
            cur.execute(
                f"INSERT INTO public.{table} ({cols}) VALUES ({placeholders}) RETURNING id",
                list(clean.values()),
            )
            row = cur.fetchone()
            return row[0] if row else None

        elif action in ("update", "reactivate"):
            if not entity_id:
                raise HTTPException(status_code=422, detail="entity_id required for update/reactivate")
            if not clean:
                raise HTTPException(status_code=422, detail="proposed_data contains no writable fields")
            set_clause = ", ".join(f"{k} = %s" for k in clean)
            cur.execute(
                f"UPDATE public.{table} SET {set_clause} WHERE id = %s",
                list(clean.values()) + [entity_id],
            )
            return entity_id

        elif action == "deprecate":
            if not entity_id:
                raise HTTPException(status_code=422, detail="entity_id required for deprecate")
            cur.execute(
                f"UPDATE public.{table} SET is_active = false, deprecated_at = now() WHERE id = %s",
                (entity_id,),
            )
            return entity_id

    return entity_id


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/{entity_type}/request", status_code=201)
async def submit_change_request(
    entity_type: str,
    payload: ChangeRequestCreate,
    user=Depends(verify_jwt),
):
    """Submit a draft MDM change request. Starts in 'draft' status."""
    if entity_type not in VALID_ENTITY_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown entity_type '{entity_type}'. Valid: {sorted(VALID_ENTITY_TYPES)}",
        )
    valid_actions = {"create", "update", "deprecate", "reactivate"}
    if payload.action not in valid_actions:
        raise HTTPException(status_code=422, detail=f"action must be one of {valid_actions}")

    requester = user.get("sub") or user.get("name") or "system"

    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO public.royan_mdm_change_requests
                    (entity_type, entity_id, action, proposed_data, status, requested_by)
                VALUES (%s, %s, %s, %s, 'draft', %s)
                RETURNING id, status, submitted_at
                """,
                (entity_type, payload.entity_id, payload.action,
                 json.dumps(payload.proposed_data), requester),
            )
            row = cur.fetchone()
        conn.commit()
    finally:
        _put_conn(conn)

    audit_event(
        "mdm_change_request_created",
        {"entity_type": entity_type, "action": payload.action, "entity_id": payload.entity_id},
        actor_id=requester, subject_type="mdm", subject_id=str(row[0]),
    )
    return {
        "ok": True,
        "request_id": row[0],
        "status": row[1],
        "entity_type": entity_type,
        "action": payload.action,
    }


@router.post("/requests/{request_id}/submit")
async def submit_for_review(request_id: int, user=Depends(verify_jwt)):
    """Move a draft request to pending_review so reviewers can see it."""
    conn = _get_conn()
    try:
        req = _get_request(request_id, conn)
        requester = user.get("sub") or "system"

        if req["status"] != "draft":
            raise HTTPException(status_code=409, detail=f"Request is '{req['status']}'; only drafts can be submitted")
        if req["requested_by"] != requester:
            roles = set(user.get("roles") or user.get("permissions") or [])
            if "admin" not in roles:
                raise HTTPException(status_code=403, detail="You can only submit your own draft requests")

        with conn.cursor() as cur:
            cur.execute(
                "UPDATE public.royan_mdm_change_requests SET status = 'pending_review', submitted_at = now() WHERE id = %s",
                (request_id,),
            )
        conn.commit()
    finally:
        _put_conn(conn)

    return {"ok": True, "request_id": request_id, "status": "pending_review"}


@router.get("/requests")
async def list_change_requests(
    entity_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None, description="draft|pending_review|approved|rejected|published|withdrawn"),
    limit: int = Query(50, ge=1, le=200),
    user=Depends(require_role("admin", "data_steward", "dpo")),
):
    """List MDM change requests (admin/data_steward only)."""
    conn = _get_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            conditions = []
            params = []
            if entity_type:
                conditions.append("entity_type = %s")
                params.append(entity_type)
            if status:
                conditions.append("status = %s")
                params.append(status)
            where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
            cur.execute(
                f"SELECT * FROM public.royan_mdm_change_requests {where} ORDER BY submitted_at DESC LIMIT %s",
                params + [limit],
            )
            rows = [dict(r) for r in cur.fetchall()]
    finally:
        _put_conn(conn)
    return {"requests": rows, "count": len(rows)}


@router.get("/requests/{request_id}")
async def get_change_request(request_id: int, user=Depends(verify_jwt)):
    """Get a single MDM change request."""
    conn = _get_conn()
    try:
        req = _get_request(request_id, conn)
    finally:
        _put_conn(conn)
    return {"request": req}


@router.post("/requests/{request_id}/approve",
             dependencies=[Depends(require_role("admin"))])
async def approve_change_request(
    request_id: int,
    payload: ReviewDecision = ReviewDecision(),
    user=Depends(verify_jwt),
):
    """Approve a pending MDM request and immediately publish the change to the live table."""
    conn = _get_conn()
    reviewer = user.get("sub") or "system"
    try:
        req = _get_request(request_id, conn)
        if req["status"] != "pending_review":
            raise HTTPException(
                status_code=409,
                detail=f"Request is '{req['status']}'; only pending_review requests can be approved",
            )

        entity_type = req["entity_type"]
        entity_id = req.get("entity_id")
        action = req["action"]
        proposed = req.get("proposed_data") or {}
        if isinstance(proposed, str):
            proposed = json.loads(proposed)

        # Capture before-state for audit
        before_data = _get_entity_current(entity_type, entity_id, conn) if entity_id else None

        # Publish the change
        new_entity_id = _publish_change(entity_type, entity_id, action, proposed, conn)

        # Capture after-state
        after_data = _get_entity_current(entity_type, new_entity_id or entity_id, conn)

        # Mark request as published
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE public.royan_mdm_change_requests
                SET status = 'published', reviewed_by = %s,
                    review_notes = %s, reviewed_at = now(), published_at = now()
                WHERE id = %s
                """,
                (reviewer, payload.notes, request_id),
            )

        _write_mdm_audit(request_id, entity_type, new_entity_id or entity_id,
                         action, before_data, after_data, reviewer, conn)
        conn.commit()
    finally:
        _put_conn(conn)

    audit_event(
        "mdm_change_approved",
        {"entity_type": req["entity_type"], "action": req["action"]},
        actor_id=reviewer, subject_type="mdm", subject_id=str(request_id),
    )
    emit_clinical_event(
        event_type="SYSTEM_EVENT",
        entity_type=req["entity_type"],
        entity_id=new_entity_id or entity_id,
        performed_by=reviewer,
        event_data={"action": "mdm_published", "change_request_id": request_id},
    )

    return {
        "ok": True,
        "request_id": request_id,
        "status": "published",
        "entity_type": req["entity_type"],
        "entity_id": new_entity_id or entity_id,
    }


@router.post("/requests/{request_id}/reject",
             dependencies=[Depends(require_role("admin", "data_steward"))])
async def reject_change_request(
    request_id: int,
    payload: ReviewDecision,
    user=Depends(verify_jwt),
):
    """Reject a pending MDM change request with review notes."""
    conn = _get_conn()
    reviewer = user.get("sub") or "system"
    try:
        req = _get_request(request_id, conn)
        if req["status"] != "pending_review":
            raise HTTPException(
                status_code=409,
                detail=f"Request is '{req['status']}'; only pending_review requests can be rejected",
            )
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE public.royan_mdm_change_requests
                SET status = 'rejected', reviewed_by = %s,
                    review_notes = %s, reviewed_at = now()
                WHERE id = %s
                """,
                (reviewer, payload.notes, request_id),
            )
        conn.commit()
    finally:
        _put_conn(conn)

    audit_event("mdm_change_rejected", {"notes": payload.notes},
                actor_id=reviewer, subject_type="mdm", subject_id=str(request_id))
    return {"ok": True, "request_id": request_id, "status": "rejected"}


@router.post("/requests/{request_id}/withdraw")
async def withdraw_change_request(request_id: int, user=Depends(verify_jwt)):
    """Withdraw your own draft/pending request."""
    conn = _get_conn()
    requester = user.get("sub") or "system"
    try:
        req = _get_request(request_id, conn)
        if req["status"] not in ("draft", "pending_review"):
            raise HTTPException(
                status_code=409,
                detail=f"Request is '{req['status']}'; only draft/pending requests can be withdrawn",
            )
        roles = set(user.get("roles") or user.get("permissions") or [])
        if req["requested_by"] != requester and "admin" not in roles:
            raise HTTPException(status_code=403, detail="You can only withdraw your own requests")

        with conn.cursor() as cur:
            cur.execute(
                "UPDATE public.royan_mdm_change_requests SET status = 'withdrawn' WHERE id = %s",
                (request_id,),
            )
        conn.commit()
    finally:
        _put_conn(conn)
    return {"ok": True, "request_id": request_id, "status": "withdrawn"}


@router.post("/{entity_type}/{entity_id}/deprecate",
             dependencies=[Depends(require_role("admin"))])
async def deprecate_entity(
    entity_type: str,
    entity_id: int,
    notes: Optional[str] = Query(None),
    user=Depends(verify_jwt),
):
    """Immediately deprecate (soft-delete) an MDM entity.

    Creates and auto-approves a deprecate change request so the audit trail
    is always complete even for emergency deprecations.
    """
    if entity_type not in VALID_ENTITY_TYPES:
        raise HTTPException(status_code=422, detail=f"Unknown entity_type '{entity_type}'")

    actor = user.get("sub") or "system"
    conn = _get_conn()
    try:
        before_data = _get_entity_current(entity_type, entity_id, conn)
        if not before_data:
            raise HTTPException(status_code=404, detail=f"{entity_type} {entity_id} not found")

        # Write change request (auto-approved)
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO public.royan_mdm_change_requests
                    (entity_type, entity_id, action, proposed_data, status,
                     requested_by, reviewed_by, review_notes, submitted_at, reviewed_at, published_at)
                VALUES (%s, %s, 'deprecate', %s, 'published', %s, %s, %s, now(), now(), now())
                RETURNING id
                """,
                (entity_type, entity_id, json.dumps({}), actor, actor, notes or "Direct deprecation by admin"),
            )
            req_id = cur.fetchone()[0]

        # Apply the deprecation
        table = _ENTITY_TABLES[entity_type]
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE public.{table} SET is_active = false, deprecated_at = now(), deprecated_by = %s WHERE id = %s",
                (actor, entity_id),
            )

        after_data = _get_entity_current(entity_type, entity_id, conn)
        _write_mdm_audit(req_id, entity_type, entity_id, "deprecate", before_data, after_data, actor, conn)
        conn.commit()
    finally:
        _put_conn(conn)

    audit_event("mdm_entity_deprecated", {"entity_type": entity_type, "entity_id": entity_id},
                actor_id=actor, subject_type="mdm", subject_id=str(entity_id))
    return {"ok": True, "entity_type": entity_type, "entity_id": entity_id, "status": "deprecated"}


@router.get("/{entity_type}")
async def list_mdm_entities(
    entity_type: str,
    include_deprecated: bool = Query(False, description="Include deprecated/inactive records"),
    limit: int = Query(200, ge=1, le=1000),
    user=Depends(verify_jwt),
):
    """List active MDM records for an entity type."""
    if entity_type not in VALID_ENTITY_TYPES:
        raise HTTPException(status_code=422, detail=f"Unknown entity_type '{entity_type}'")

    table = _ENTITY_TABLES[entity_type]
    conn = _get_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            if include_deprecated:
                cur.execute(f"SELECT * FROM public.{table} ORDER BY id LIMIT %s", (limit,))
            else:
                cur.execute(
                    f"SELECT * FROM public.{table} WHERE is_active = true ORDER BY id LIMIT %s",
                    (limit,),
                )
            rows = [dict(r) for r in cur.fetchall()]
    finally:
        _put_conn(conn)

    return {"entity_type": entity_type, "records": rows, "count": len(rows)}
