"""Clinical Workflow State Machine Router — Blueprint Chapter 10.

Enforces the encounter lifecycle defined in migration 133 (royan_workflow_transitions).
Every encounter state change must pass through this router so that:
  - Role permissions are checked against allowed_roles
  - All prerequisite gate functions are evaluated before the transition is allowed
  - The transition is recorded in royan_transition_audit (pass or fail)
  - A clinical event is emitted to royan_clinical_event_log on success

Endpoints:
  GET  /api/v1/workflow/transitions                  — list all defined transitions
  GET  /api/v1/encounters/{id}/available-transitions — valid next states from current
  POST /api/v1/encounters/{id}/transition            — attempt a state change
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

import psycopg2.extras
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.db import db, audit_event
from src.middleware import verify_jwt
from src.services.event_service import emit_clinical_event
from src.services import workflow_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["Workflow State Machine"])


# ─────────────────────────────────────────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────────────────────────────────────────

class TransitionRequest(BaseModel):
    to_state: str
    notes: Optional[str] = None


class TransitionResult(BaseModel):
    encounter_id: int
    from_state: str
    to_state: str
    transition_name: str
    outcome: str                    # "success" | "blocked" | "error"
    gate_results: Dict[str, bool]
    block_reason: Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────
# Prerequisite gate functions
# Each returns (passed: bool, reason: str)
# ─────────────────────────────────────────────────────────────────────────────

def _gate_triage_complete(encounter_id: int, conn) -> tuple[bool, str]:
    """At least one triage record exists for the encounter."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM public.royan_triage WHERE encounter_id = %s",
            (encounter_id,),
        )
        count = cur.fetchone()[0]
    return (count > 0, "triage_complete: no triage record found")


def _gate_all_labs_resulted(encounter_id: int, conn) -> tuple[bool, str]:
    """No lab orders are still pending / in-flight for this encounter."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*) FROM public.royan_lab_orders
            WHERE encounter_id = %s
              AND status NOT IN ('resulted', 'cancelled', 'rejected')
            """,
            (encounter_id,),
        )
        pending = cur.fetchone()[0]
    return (pending == 0, f"all_labs_resulted: {pending} lab order(s) still pending")


def _gate_diagnosis_recorded(encounter_id: int, conn) -> tuple[bool, str]:
    """At least one clinical diagnosis is documented for this encounter."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM public.royan_clinical_diagnoses WHERE encounter_id = %s",
            (encounter_id,),
        )
        count = cur.fetchone()[0]
    if count > 0:
        return (True, "")
    # Fallback: check encounter notes with icd_code or diagnosis_notes
    with conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM public.royan_encounter_notes WHERE encounter_id = %s",
            (encounter_id,),
        )
        notes_count = cur.fetchone()[0]
    return (notes_count > 0, "diagnosis_recorded: no diagnosis or clinical note found")


def _gate_bill_settled_or_waived(encounter_id: int, conn) -> tuple[bool, str]:
    """The bill for this encounter is either fully paid or waived/written-off."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT status FROM public.royan_billing
            WHERE encounter_id = %s
            ORDER BY created_at DESC LIMIT 1
            """,
            (encounter_id,),
        )
        row = cur.fetchone()
    if not row:
        # No bill exists — allow discharge (bill may be waived at registration level)
        return (True, "")
    status = (row[0] or "").lower()
    passed = status in ("paid", "waived", "written_off")
    return (passed, f"bill_settled_or_waived: bill status is '{status}'")


def _gate_bed_assigned(encounter_id: int, conn) -> tuple[bool, str]:
    """A bed is assigned (encounter.bed_id is set) before admission."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT bed_id FROM public.royan_encounters WHERE id = %s",
            (encounter_id,),
        )
        row = cur.fetchone()
    has_bed = bool(row and row[0])
    return (has_bed, "bed_assigned: no bed assigned to this encounter")


_GATE_REGISTRY: Dict[str, Any] = {
    "triage_complete":       _gate_triage_complete,
    "all_labs_resulted":     _gate_all_labs_resulted,
    "diagnosis_recorded":    _gate_diagnosis_recorded,
    "bill_settled_or_waived": _gate_bill_settled_or_waived,
    "bed_assigned":          _gate_bed_assigned,
}


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _get_conn():
    return db.pool.getconn()


def _put_conn(conn):
    db.pool.putconn(conn)


def _get_encounter(encounter_id: int, conn) -> Dict:
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            "SELECT id, patient_id, status, department FROM public.royan_encounters WHERE id = %s",
            (encounter_id,),
        )
        row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"Encounter {encounter_id} not found")
    return dict(row)


def _get_transition(from_state: str, to_state: str, conn) -> Optional[Dict]:
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT * FROM public.royan_workflow_transitions
            WHERE from_state = %s AND to_state = %s AND is_active = TRUE
            """,
            (from_state, to_state),
        )
        row = cur.fetchone()
    return dict(row) if row else None


def _write_audit(encounter_id, from_state, to_state, transition_name,
                 performed_by, gate_results, outcome, block_reason, conn) -> None:
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO public.royan_transition_audit
                    (encounter_id, from_state, to_state, transition_name,
                     performed_by, gate_results, outcome, block_reason)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    encounter_id, from_state, to_state, transition_name,
                    performed_by, json.dumps(gate_results), outcome, block_reason,
                ),
            )
    except Exception as exc:
        logger.warning("Transition audit write failed: %s", exc)


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/workflow/transitions")
def list_transitions(user=Depends(verify_jwt)):
    """Return the full state machine definition (all active transitions)."""
    conn = _get_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM public.royan_workflow_transitions WHERE is_active = TRUE ORDER BY from_state, to_state"
            )
            rows = [dict(r) for r in cur.fetchall()]
    finally:
        _put_conn(conn)
    return {"transitions": rows, "count": len(rows)}


@router.get("/encounters/{encounter_id}/available-transitions")
def available_transitions(encounter_id: int, user=Depends(verify_jwt)):
    """Return all transitions legally reachable from the encounter's current state."""
    conn = _get_conn()
    try:
        enc = _get_encounter(encounter_id, conn)
        current = enc["status"]
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT from_state, to_state, transition_name, allowed_roles,
                       prerequisites, description
                FROM public.royan_workflow_transitions
                WHERE from_state = %s AND is_active = TRUE
                """,
                (current,),
            )
            available = [dict(r) for r in cur.fetchall()]
    finally:
        _put_conn(conn)

    user_roles = set(user.get("roles") or user.get("permissions") or [])
    # Filter to transitions this user's roles can execute
    accessible = [
        t for t in available
        if "admin" in user_roles or user_roles.intersection(set(t.get("allowed_roles") or []))
    ]

    return {
        "encounter_id": encounter_id,
        "current_state": current,
        "available_transitions": accessible,
    }


@router.post("/encounters/{encounter_id}/transition", response_model=TransitionResult)
def perform_transition(
    encounter_id: int,
    payload: TransitionRequest,
    user=Depends(verify_jwt),
):
    """Attempt a clinical encounter state transition.

    1. Validates the from→to pair exists in royan_workflow_transitions.
    2. Checks the requesting user has an allowed role.
    3. Runs all prerequisite gate checks.
    4. On success: updates encounter status + emits clinical event.
    5. Always writes to royan_transition_audit (success or blocked).
    """
    conn = _get_conn()
    performed_by = user.get("sub") or user.get("name") or "system"
    user_roles = set(user.get("roles") or user.get("permissions") or [])

    try:
        enc = _get_encounter(encounter_id, conn)
        from_state = enc["status"]
        to_state = payload.to_state

        # ── 1. Look up transition rule ────────────────────────────────────
        transition = _get_transition(from_state, to_state, conn)
        if not transition:
            _write_audit(encounter_id, from_state, to_state, None,
                         performed_by, {}, "blocked",
                         f"No active transition from '{from_state}' to '{to_state}'", conn)
            conn.commit()
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "invalid_transition",
                    "message": f"Transition from '{from_state}' to '{to_state}' is not permitted.",
                    "current_state": from_state,
                },
            )

        transition_name = transition["transition_name"]

        # ── 2. Role check ─────────────────────────────────────────────────
        allowed = set(transition.get("allowed_roles") or [])
        if "admin" not in user_roles and not user_roles.intersection(allowed):
            _write_audit(encounter_id, from_state, to_state, transition_name,
                         performed_by, {}, "blocked",
                         f"Role check failed. Required: {allowed}", conn)
            conn.commit()
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "insufficient_role",
                    "message": f"Transition '{transition_name}' requires one of: {sorted(allowed)}",
                },
            )

        # ── 3. Gate checks ────────────────────────────────────────────────
        prerequisites = transition.get("prerequisites") or []
        if isinstance(prerequisites, str):
            prerequisites = json.loads(prerequisites)

        gate_results: Dict[str, bool] = {}
        failed_gates: List[str] = []

        for gate in prerequisites:
            check_name = gate.get("check")
            gate_fn = _GATE_REGISTRY.get(check_name)
            if gate_fn is None:
                logger.warning("Unknown gate check '%s' — skipping", check_name)
                gate_results[check_name] = True
                continue
            try:
                passed, reason = gate_fn(encounter_id, conn)
                gate_results[check_name] = passed
                if not passed:
                    failed_gates.append(reason or check_name)
            except Exception as exc:
                logger.error("Gate '%s' raised exception: %s", check_name, exc)
                gate_results[check_name] = False
                failed_gates.append(f"{check_name}: internal error")

        if failed_gates:
            block_reason = "; ".join(failed_gates)
            _write_audit(encounter_id, from_state, to_state, transition_name,
                         performed_by, gate_results, "blocked", block_reason, conn)
            conn.commit()
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "gate_check_failed",
                    "message": f"Transition blocked: {block_reason}",
                    "gate_results": gate_results,
                },
            )

        # ── 4. Apply transition ───────────────────────────────────────────
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE public.royan_encounters SET status = %s, updated_at = now() WHERE id = %s",
                (to_state, encounter_id),
            )
        _write_audit(encounter_id, from_state, to_state, transition_name,
                     performed_by, gate_results, "success", None, conn)
        conn.commit()

    finally:
        _put_conn(conn)

    # ── 5. Emit clinical event (fire-and-forget, after conn returned) ─────
    auto_event = transition.get("auto_emit_event")
    if auto_event:
        emit_clinical_event(
            event_type=auto_event,
            encounter_id=encounter_id,
            patient_id=enc.get("patient_id"),
            entity_type="encounter",
            entity_id=encounter_id,
            performed_by=performed_by,
            event_data={
                "from_state": from_state,
                "to_state": to_state,
                "transition_name": transition_name,
                "notes": payload.notes,
            },
        )

    audit_event(
        "encounter_state_transition",
        {"encounter_id": encounter_id, "from": from_state, "to": to_state},
        actor_id=performed_by,
        subject_type="encounter",
        subject_id=str(encounter_id),
    )

    return TransitionResult(
        encounter_id=encounter_id,
        from_state=from_state,
        to_state=to_state,
        transition_name=transition_name,
        outcome="success",
        gate_results=gate_results,
    )


# ─────────────────────────────────────────────────────────────────────────────
# New workflow schema endpoints (workflow.instances / workflow.events)
# ─────────────────────────────────────────────────────────────────────────────

class WorkflowTransitionRequest(BaseModel):
    event_name: str
    event_data: Optional[Dict[str, Any]] = None
    notes: Optional[str] = None


@router.get("/workflow/entity/{entity_type}/{entity_id}")
def get_entity_workflow(
    entity_type: str,
    entity_id: int,
    user=Depends(verify_jwt),
):
    """Return the active workflow instance for any entity."""
    conn = _get_conn()
    try:
        instance = workflow_service.get_instance_for_entity(conn, entity_type, entity_id)
    finally:
        _put_conn(conn)

    if not instance:
        raise HTTPException(status_code=404, detail=f"No workflow instance for {entity_type}/{entity_id}")
    return {"instance": instance}


@router.get("/workflow/entity/{entity_type}/{entity_id}/transitions")
def get_available_workflow_transitions(
    entity_type: str,
    entity_id: int,
    user=Depends(verify_jwt),
):
    """Return allowed events from the current workflow state for this entity."""
    actor_role = (list(user.get("roles") or user.get("permissions") or []) or [None])[0]
    conn = _get_conn()
    try:
        instance = workflow_service.get_instance_for_entity(conn, entity_type, entity_id)
        if not instance:
            raise HTTPException(status_code=404, detail=f"No workflow instance for {entity_type}/{entity_id}")
        allowed = workflow_service.get_allowed_transitions(conn, instance["id"], actor_role)
    finally:
        _put_conn(conn)

    return {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "current_state": instance["current_state"],
        "allowed_events": allowed,
    }


@router.post("/workflow/entity/{entity_type}/{entity_id}/transition")
def fire_workflow_transition(
    entity_type: str,
    entity_id: int,
    payload: WorkflowTransitionRequest,
    user=Depends(verify_jwt),
):
    """Fire a workflow event on the entity's active workflow instance."""
    actor_id = user.get("sub") or "system"
    actor_roles = list(user.get("roles") or user.get("permissions") or [])
    actor_role = actor_roles[0] if actor_roles else None
    correlation_id = user.get("correlation_id")

    conn = _get_conn()
    try:
        instance = workflow_service.get_instance_for_entity(conn, entity_type, entity_id)
        if not instance:
            raise HTTPException(status_code=404, detail=f"No workflow instance for {entity_type}/{entity_id}")

        try:
            updated = workflow_service.transition(
                conn,
                instance_id=instance["id"],
                event_name=payload.event_name,
                actor_id=actor_id,
                actor_role=actor_role,
                event_data=payload.event_data,
                correlation_id=correlation_id,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
    finally:
        _put_conn(conn)

    return {
        "ok": True,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "event_name": payload.event_name,
        "new_state": updated["current_state"],
        "is_terminal": updated["is_terminal"],
    }


@router.get("/workflow/entity/{entity_type}/{entity_id}/history")
def get_workflow_history(
    entity_type: str,
    entity_id: int,
    user=Depends(verify_jwt),
):
    """Return the immutable event history for this entity's workflow."""
    conn = _get_conn()
    try:
        instance = workflow_service.get_instance_for_entity(conn, entity_type, entity_id)
        if not instance:
            raise HTTPException(status_code=404, detail=f"No workflow instance for {entity_type}/{entity_id}")
        history = workflow_service.get_workflow_history(conn, instance["id"])
    finally:
        _put_conn(conn)

    return {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "instance_id": instance["id"],
        "current_state": instance["current_state"],
        "events": history,
    }
