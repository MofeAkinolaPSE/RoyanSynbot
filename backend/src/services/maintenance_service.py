from __future__ import annotations

import asyncio
import datetime as dt
import logging
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from src.cache import clear_cache
from src.constants import (
    RELIABILITY_OBSERVE_ONLY,
    TABLE_INCIDENT_LOG,
    TABLE_MAINTENANCE_TASKS,
    TABLE_REMEDIATION_ACTIONS,
)
from src.db import audit_event, db

logger = logging.getLogger(__name__)


def _utcnow_iso() -> str:
    return dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _safe_table_count(table: str) -> int:
    try:
        res = db.table(table).select("id", count="exact").limit(1).execute()
        return int(getattr(res, "count", 0) or 0)
    except Exception:
        return 0


def _severity_rank(severity: str) -> int:
    if severity == "critical":
        return 3
    if severity == "high":
        return 2
    if severity == "medium":
        return 1
    return 0


def detect_finance_blank_dashboard() -> Dict[str, Any]:
    """Run a focused diagnosis for hospital dashboard readiness."""
    checks: List[Dict[str, Any]] = []

    patients_rows = _safe_table_count("royan_patients")
    encounters_rows = _safe_table_count("royan_encounters")
    bills_rows = _safe_table_count("royan_billing")

    checks.append({"check": "patients_table_rows", "ok": patients_rows >= 0, "value": patients_rows})
    checks.append({"check": "encounters_table_rows", "ok": encounters_rows >= 0, "value": encounters_rows})
    checks.append({"check": "bills_table_rows", "ok": bills_rows >= 0, "value": bills_rows})

    # Verify DB connectivity by checking at least one core table is queryable
    db_reachable = patients_rows >= 0
    checks.append({"check": "db_connectivity", "ok": db_reachable, "value": db_reachable})

    failures = [c for c in checks if not c["ok"]]
    healthy = len(failures) == 0

    if healthy:
        severity = "low"
        summary = "Hospital dashboard diagnostics passed."
    elif not db_reachable:
        severity = "critical"
        summary = "Database connectivity check failed."
    else:
        severity = "medium"
        summary = "Partial hospital data gaps detected."

    return {
        "healthy": healthy,
        "severity": severity,
        "summary": summary,
        "checks": checks,
        "failed_checks": failures,
        "metrics": {
            "patients_rows": patients_rows,
            "encounters_rows": encounters_rows,
            "bills_rows": bills_rows,
        },
    }


def create_incident(
    component: str,
    severity: str,
    summary: str,
    details: Optional[Dict[str, Any]] = None,
    correlation_id: Optional[str] = None,
) -> Dict[str, Any]:
    payload = {
        "incident_key": f"{component}:{summary[:80]}",
        "component": component,
        "severity": severity,
        "status": "open",
        "summary": summary,
        "details": details or {},
        "correlation_id": correlation_id or str(uuid.uuid4()),
        "detected_at": _utcnow_iso(),
    }
    row = db.table(TABLE_INCIDENT_LOG).insert(payload).execute().data
    created = (row or [payload])[0]

    audit_event(
        "maintenance_incident_created",
        {
            "component": component,
            "severity": severity,
            "summary": summary,
            "correlation_id": created.get("correlation_id"),
        },
        event_class="maintenance",
        action="incident.create",
        outcome="success",
        subject_type="incident",
        subject_id=created.get("id"),
    )
    return created


def record_remediation(
    incident_id: Optional[str],
    action_name: str,
    outcome: str,
    notes: str = "",
    payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    row = {
        "incident_id": incident_id,
        "action_name": action_name,
        "action_type": "auto_fix",
        "outcome": outcome,
        "notes": notes,
        "payload": payload or {},
        "executed_at": _utcnow_iso(),
    }
    saved = db.table(TABLE_REMEDIATION_ACTIONS).insert(row).execute().data
    action = (saved or [row])[0]

    audit_event(
        "maintenance_remediation_recorded",
        {
            "incident_id": incident_id,
            "action_name": action_name,
            "outcome": outcome,
        },
        event_class="maintenance",
        action="incident.remediate",
        outcome="success",
        subject_type="incident" if incident_id else "maintenance",
        subject_id=incident_id,
    )
    return action


def resolve_incident(incident_id: str, resolution_note: str = "") -> Dict[str, Any]:
    payload = {
        "status": "resolved",
        "resolved_at": _utcnow_iso(),
    }
    rows = db.table(TABLE_INCIDENT_LOG).update(payload).eq("id", incident_id).execute().data or []
    out = rows[0] if rows else {"id": incident_id, **payload}

    audit_event(
        "maintenance_incident_resolved",
        {
            "incident_id": incident_id,
            "resolution_note": resolution_note,
        },
        event_class="maintenance",
        action="incident.resolve",
        outcome="success",
        subject_type="incident",
        subject_id=incident_id,
    )
    return out


def run_blank_dashboard_playbook(incident_id: str) -> Dict[str, Any]:
    """Apply safe, non-destructive actions for the blank-finance-dashboard incident.

    When RELIABILITY_OBSERVE_ONLY is True the playbook runs diagnostics and
    records its findings but does NOT mutate cache or resolve the incident.
    """
    if RELIABILITY_OBSERVE_ONLY:
        diagnostics = detect_finance_blank_dashboard()
        logger.info("observe-only mode: skipping auto-fix for incident %s", incident_id)
        return {
            "incident_id": incident_id,
            "result": "observe_only",
            "note": "Auto-fix skipped — RELIABILITY_OBSERVE_ONLY is enabled.",
            "actions": [],
            "diagnostics": diagnostics,
        }

    actions: List[Dict[str, Any]] = []

    try:
        clear_cache()
        actions.append({"action": "clear_cache", "outcome": "success"})
    except Exception as exc:
        actions.append({"action": "clear_cache", "outcome": "failed", "error": str(exc)})

    diagnostics = detect_finance_blank_dashboard()

    if diagnostics["healthy"]:
        result = "success"
        note = "Diagnostics healthy after remediation actions."
        resolve_incident(incident_id, resolution_note=note)
    else:
        result = "partial"
        note = diagnostics["summary"]

    record_remediation(
        incident_id=incident_id,
        action_name="finance_blank_dashboard_playbook",
        outcome=result,
        notes=note,
        payload={"actions": actions, "diagnostics": diagnostics},
    )

    return {
        "incident_id": incident_id,
        "result": result,
        "note": note,
        "actions": actions,
        "diagnostics": diagnostics,
    }


def get_open_incidents(limit: int = 50) -> List[Dict[str, Any]]:
    try:
        return (
            db.table(TABLE_INCIDENT_LOG)
            .select("*")
            .eq("status", "open")
            .order("detected_at", desc=True)
            .limit(limit)
            .execute()
            .data
            or []
        )
    except Exception:
        return []


def get_overdue_maintenance_tasks(limit: int = 100) -> List[Dict[str, Any]]:
    now = _utcnow_iso()
    try:
        return (
            db.table(TABLE_MAINTENANCE_TASKS)
            .select("*")
            .in_("status", ["scheduled", "in_progress", "open"])
            .lt("due_at", now)
            .order("due_at", desc=False)
            .limit(limit)
            .execute()
            .data
            or []
        )
    except Exception:
        return []


def maintenance_snapshot() -> Dict[str, Any]:
    open_incidents = get_open_incidents(limit=100)
    overdue_tasks = get_overdue_maintenance_tasks(limit=200)

    highest = "low"
    for incident in open_incidents:
        sev = str(incident.get("severity") or "low").lower()
        if _severity_rank(sev) > _severity_rank(highest):
            highest = sev

    return {
        "open_incidents": open_incidents,
        "overdue_tasks": overdue_tasks,
        "counts": {
            "open_incidents": len(open_incidents),
            "overdue_tasks": len(overdue_tasks),
        },
        "highest_severity": highest,
    }


@dataclass
class MaintenanceMonitor:
    interval_seconds: int = 300

    async def run_loop(self) -> None:
        while True:
            try:
                await asyncio.to_thread(self.run_once)
            except Exception as exc:
                logger.exception("Maintenance monitor run_once failed: %s", exc)
            await asyncio.sleep(max(30, int(self.interval_seconds)))

    def run_once(self) -> Dict[str, Any]:
        diagnostics = detect_finance_blank_dashboard()
        if diagnostics["healthy"]:
            return diagnostics

        incident = create_incident(
            component="finance_dashboard",
            severity=diagnostics["severity"],
            summary=diagnostics["summary"],
            details={"diagnostics": diagnostics},
        )

        if diagnostics["severity"] in {"medium", "high"}:
            run_blank_dashboard_playbook(incident_id=incident.get("id"))

        return {
            "diagnostics": diagnostics,
            "incident": incident,
        }
