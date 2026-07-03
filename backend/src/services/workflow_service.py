"""Workflow Engine Service — Chapter 8 of the Implementation Guide.

Implements the Enterprise Orchestration Engine (EOE) backed by the
workflow schema tables (migration 136) and workflow definitions stored
in configuration.workflow_definitions.

Functions:
  create_workflow_instance(conn, entity_type, entity_id, definition_id, started_by) → int
  transition(conn, instance_id, event_name, actor_id, actor_role, event_data, correlation_id) → dict
  get_current_state(conn, entity_type, entity_id) → str | None
  get_workflow_history(conn, instance_id) → list[dict]
  get_instance_for_entity(conn, entity_type, entity_id) → dict | None
  get_allowed_transitions(conn, instance_id, actor_role) → list[str]
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

import psycopg2.extras

from src.services.event_service import emit_clinical_event

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Definition cache (in-memory; reloaded if None)
# ─────────────────────────────────────────────────────────────────────────────

_definition_cache: Dict[str, Dict] = {}


def _load_definition(conn, definition_id: str) -> Optional[Dict]:
    """Load workflow definition from configuration schema. Caches in memory."""
    if definition_id in _definition_cache:
        return _definition_cache[definition_id]

    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT definition FROM configuration.workflow_definitions WHERE id = %s AND is_active = true",
                (definition_id,),
            )
            row = cur.fetchone()
    except Exception:
        # configuration schema may not yet exist in the environment
        return None

    if not row:
        return None

    defn = row["definition"]
    if isinstance(defn, str):
        defn = json.loads(defn)
    _definition_cache[definition_id] = defn
    return defn


def _infer_definition_id(entity_type: str, encounter_type: str = "outpatient") -> str:
    """Guess the workflow definition id from entity type."""
    mapping = {
        "encounter":    f"encounter.{encounter_type}.v1",
        "lab_order":    "lab_order.v1",
        "prescription": "prescription.v1",
        "invoice":      "invoice.v1",
    }
    return mapping.get(entity_type, f"{entity_type}.v1")


# ─────────────────────────────────────────────────────────────────────────────
# Instance management
# ─────────────────────────────────────────────────────────────────────────────

def create_workflow_instance(
    conn,
    entity_type: str,
    entity_id: int,
    definition_id: str,
    started_by: str = "system",
    context: Optional[Dict] = None,
) -> int:
    """Create a new workflow instance. Returns instance_id."""
    defn = _load_definition(conn, definition_id)
    initial_state = (defn or {}).get("initial_state", "created")

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO workflow.instances
                    (entity_type, entity_id, definition_id, current_state, started_by, context)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    entity_type, entity_id, definition_id, initial_state,
                    started_by, json.dumps(context or {}),
                ),
            )
            instance_id = cur.fetchone()[0]
        conn.commit()
    except Exception as exc:
        conn.rollback()
        raise RuntimeError(f"create_workflow_instance DB error: {exc}") from exc

    return instance_id


def get_instance_for_entity(
    conn,
    entity_type: str,
    entity_id: int,
) -> Optional[Dict[str, Any]]:
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT * FROM workflow.instances
                WHERE entity_type = %s AND entity_id = %s
                ORDER BY started_at DESC LIMIT 1
                """,
                (entity_type, entity_id),
            )
            row = cur.fetchone()
    except Exception:
        return None
    return dict(row) if row else None


def get_current_state(
    conn,
    entity_type: str,
    entity_id: int,
) -> Optional[str]:
    instance = get_instance_for_entity(conn, entity_type, entity_id)
    return instance["current_state"] if instance else None


def get_workflow_history(conn, instance_id: int) -> List[Dict[str, Any]]:
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM workflow.events WHERE instance_id = %s ORDER BY occurred_at ASC",
                (instance_id,),
            )
            return [dict(r) for r in cur.fetchall()]
    except Exception:
        return []


def get_allowed_transitions(
    conn,
    instance_id: int,
    actor_role: Optional[str] = None,
) -> List[str]:
    """Return event names the actor is permitted to fire from the current state."""
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT current_state, definition_id FROM workflow.instances WHERE id = %s",
                (instance_id,),
            )
            row = cur.fetchone()
    except Exception:
        return []

    if not row:
        return []

    current_state = row["current_state"]
    defn = _load_definition(conn, row["definition_id"])
    if not defn:
        return []

    allowed = []
    for t in defn.get("transitions", []):
        if t["from"] != current_state:
            continue
        if actor_role and t.get("roles") and actor_role not in t["roles"]:
            continue
        allowed.append(t["event"])
    return allowed


# ─────────────────────────────────────────────────────────────────────────────
# Transition
# ─────────────────────────────────────────────────────────────────────────────

def transition(
    conn,
    instance_id: int,
    event_name: str,
    actor_id: str = "system",
    actor_role: Optional[str] = None,
    event_data: Optional[Dict] = None,
    correlation_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Execute a state transition on a workflow instance.

    Validates the event is legal from the current state (and optionally
    that the actor role is permitted). Writes an immutable workflow.events
    row and updates workflow.instances.current_state.

    Returns the updated instance dict.
    Raises ValueError for invalid transitions.
    Raises RuntimeError on DB failure.
    """
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM workflow.instances WHERE id = %s FOR UPDATE",
                (instance_id,),
            )
            instance = cur.fetchone()
    except Exception as exc:
        raise RuntimeError(f"transition: cannot load instance {instance_id}: {exc}") from exc

    if not instance:
        raise ValueError(f"Workflow instance {instance_id} not found")
    if instance["is_terminal"]:
        raise ValueError(f"Workflow instance {instance_id} is in a terminal state '{instance['current_state']}'")

    current_state = instance["current_state"]
    definition_id = instance["definition_id"]
    defn = _load_definition(conn, definition_id)

    # Validate transition
    target_state = None
    if defn:
        for t in defn.get("transitions", []):
            if t["from"] == current_state and t["event"] == event_name:
                if actor_role and t.get("roles") and actor_role not in t["roles"]:
                    raise ValueError(
                        f"Role '{actor_role}' is not permitted to fire '{event_name}' "
                        f"from state '{current_state}'"
                    )
                target_state = t["to"]
                break

        if target_state is None:
            raise ValueError(
                f"Event '{event_name}' is not a valid transition from state '{current_state}' "
                f"in workflow '{definition_id}'"
            )
    else:
        # No definition found — allow free transition (migration not yet applied)
        target_state = event_data.get("to_state", "unknown") if event_data else "unknown"
        logger.warning("transition: definition '%s' not found — free transition allowed", definition_id)

    is_terminal = target_state in (defn or {}).get("terminal_states", [])

    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Write immutable event
            cur.execute(
                """
                INSERT INTO workflow.events
                    (instance_id, from_state, to_state, event_name,
                     actor_id, actor_role, correlation_id, event_data)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    instance_id, current_state, target_state, event_name,
                    actor_id, actor_role, correlation_id,
                    json.dumps(event_data or {}),
                ),
            )

            # Update instance
            cur.execute(
                """
                UPDATE workflow.instances
                SET current_state = %s,
                    previous_state = %s,
                    is_terminal = %s,
                    last_transitioned_at = now(),
                    completed_at = CASE WHEN %s THEN now() ELSE completed_at END
                WHERE id = %s
                RETURNING *
                """,
                (target_state, current_state, is_terminal, is_terminal, instance_id),
            )
            updated = dict(cur.fetchone())
        conn.commit()
    except (ValueError, RuntimeError):
        raise
    except Exception as exc:
        conn.rollback()
        raise RuntimeError(f"transition DB write error: {exc}") from exc

    # Emit clinical event for encounter transitions
    if instance["entity_type"] == "encounter":
        _emit_encounter_event(event_name, instance["entity_id"], actor_id, correlation_id)

    logger.info(
        "WorkflowTransition instance=%d %s --[%s]--> %s actor=%s",
        instance_id, current_state, event_name, target_state, actor_id,
    )
    return updated


def _emit_encounter_event(event_name: str, entity_id: int, actor_id: str, correlation_id: Optional[str]) -> None:
    """Map workflow event names to clinical event types."""
    mapping = {
        "QUEUE_PATIENT":         "ENCOUNTER_QUEUED",
        "START_TRIAGE":          "ENCOUNTER_TRIAGED",
        "COMPLETE_TRIAGE":       "TRIAGE_COMPLETED",
        "CALL_PATIENT":          "ENCOUNTER_CONSULTING",
        "ORDER_LAB":             "LAB_ORDER_CREATED",
        "RESULTS_READY":         "LAB_RESULT_READY",
        "COMPLETE_CONSULTATION": "CONSULTATION_COMPLETED",
        "PAYMENT_RECEIVED":      "PAYMENT_RECEIVED",
        "CLOSE_ENCOUNTER":       "ENCOUNTER_CLOSED",
    }
    clinical_type = mapping.get(event_name, "SYSTEM_EVENT")
    emit_clinical_event(
        event_type=clinical_type,
        encounter_id=entity_id,
        entity_type="encounter",
        entity_id=entity_id,
        performed_by=actor_id,
        event_data={"workflow_event": event_name, "correlation_id": correlation_id},
    )
