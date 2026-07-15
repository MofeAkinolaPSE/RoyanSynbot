"""Clinical Reminders — patient-specific due/overdue care-gap alerts, the
CPRS "Clinical Reminders" cover-sheet card.

Deliberately NOT full USPSTF-style preventive-care/screening logic (age and
gender-based screening schedules) — that's a much bigger clinical rules
project. This starts small and real: two concrete rules derived directly
from data we actually have, architected so more rules can be added later
without touching the schema.

Reminders are persisted (not just computed-on-read) so a clinician can
dismiss one and have it stay dismissed — see `evaluate_reminders()`'s
dismissed-key handling below for why a naive upsert-every-time would be
wrong.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from ..constants import TABLE_CLINICAL_REMINDERS, TABLE_LAB_ORDERS
from ..db import db

logger = logging.getLogger("clinical_reminders")

# How many days an open lab order can sit in a pending state before it's
# flagged. Kept local to this module rather than the reliability stack's
# GUARDRAILS dataclass (backend/src/reliability/guardrails.py) — that config
# is explicitly scoped to ops/reliability agent safety limits (retry counts,
# escalation thresholds), not clinical business rules; conflating the two
# would be a category error, not genuine reuse.
STALE_LAB_ORDER_DAYS = 3

_STALE_LAB_STATUSES = ("ordered", "sample_collected", "processing")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ─────────────────────────────────────────────────────────────────────────────
# Rules — each returns a list of candidate reminder dicts (no patient_id key;
# the caller adds that before upserting)
# ─────────────────────────────────────────────────────────────────────────────

def _rule_overdue_followup(patient_id: int) -> List[Dict[str, Any]]:
    """Discharge follow-up date has passed with no newer encounter since.

    Scoped to native discharges (external_source IS NULL) — Hope-imported
    historical discharges are all, by definition, in the past, so every
    imported follow_up_date would look "overdue" and flood this rule with
    noise for any patient with Hope history.
    """
    today = _utcnow().date().isoformat()
    try:
        discharges = (
            db.table("royan_discharge_records")
            .select("id,follow_up_date,discharged_at,encounter_id")
            .eq("patient_id", patient_id)
            .lt("follow_up_date", today)
            .is_("external_source", None)
            .execute()
        ).data or []
    except Exception as exc:
        logger.warning("overdue_followup rule failed for patient %s: %s", patient_id, exc)
        return []

    candidates = []
    for d in discharges:
        follow_up_date = d.get("follow_up_date")
        discharged_at = d.get("discharged_at")
        if not follow_up_date or not discharged_at:
            continue
        try:
            newer = (
                db.table("royan_encounters")
                .select("id", count="exact")
                .eq("patient_id", patient_id)
                .gt("created_at", discharged_at)
                .execute()
            )
            if (newer.count or 0) > 0:
                continue  # patient already came back — this follow-up is moot
        except Exception:
            pass
        candidates.append({
            "rule_key": f"followup_overdue:{d['id']}",
            "message": f"Follow-up appointment overdue since {follow_up_date}",
            "due_since": follow_up_date,
            "severity": "warning",
        })
    return candidates


def _rule_stale_lab_order(patient_id: int) -> List[Dict[str, Any]]:
    """A native (live) lab order has been open (not yet resulted) too long.

    Excludes Hope-imported orders (external_source='hope') — those were
    bulk-loaded historical records the source migration never resulted, not
    live clinical work; without this filter almost every patient with Hope
    history would be flooded with reminders for years-old dead orders. Same
    external_source IS NULL convention used elsewhere in this codebase to
    separate "actually active" from "historical import."
    """
    cutoff = (_utcnow() - timedelta(days=STALE_LAB_ORDER_DAYS)).isoformat()
    try:
        rows = (
            db.table(TABLE_LAB_ORDERS)
            .select("id,test_name,status,ordered_at")
            .eq("patient_id", patient_id)
            .in_("status", list(_STALE_LAB_STATUSES))
            .lt("ordered_at", cutoff)
            .is_("external_source", None)
            .execute()
        ).data or []
    except Exception as exc:
        logger.warning("stale_lab_order rule failed for patient %s: %s", patient_id, exc)
        return []

    return [
        {
            "rule_key": f"stale_lab_order:{r['id']}",
            "message": f"Lab order '{r.get('test_name') or 'unnamed test'}' pending {STALE_LAB_ORDER_DAYS}+ days",
            "due_since": r.get("ordered_at"),
            "severity": "warning",
        }
        for r in rows
    ]


_RULES = (_rule_overdue_followup, _rule_stale_lab_order)


# ─────────────────────────────────────────────────────────────────────────────
# Evaluate + persist
# ─────────────────────────────────────────────────────────────────────────────

def evaluate_reminders(patient_id: int) -> List[Dict[str, Any]]:
    """Run every rule for this patient, upsert freshly-true conditions, and
    return the currently-active (non-dismissed) reminders.

    Rows already dismissed by a clinician are never re-upserted even if the
    underlying condition is still true — re-running the rules must not
    silently resurrect something someone already acknowledged. Rows whose
    condition is no longer true (e.g. the lab order finally resulted) are
    simply not upserted again; they stay in the table as history but the
    caller only reads back non-dismissed rows.
    """
    candidates: List[Dict[str, Any]] = []
    for rule in _RULES:
        candidates.extend(rule(patient_id))

    if candidates:
        try:
            existing = (
                db.table(TABLE_CLINICAL_REMINDERS)
                .select("rule_key,dismissed_at")
                .eq("patient_id", patient_id)
                .execute()
            ).data or []
            already_dismissed = {r["rule_key"] for r in existing if r.get("dismissed_at")}
            to_upsert = [c for c in candidates if c["rule_key"] not in already_dismissed]
            for c in to_upsert:
                db.table(TABLE_CLINICAL_REMINDERS).upsert(
                    {**c, "patient_id": patient_id},
                    on_conflict="patient_id,rule_key",
                ).execute()
        except Exception as exc:
            logger.warning("reminder upsert failed for patient %s: %s", patient_id, exc)

    try:
        active = (
            db.table(TABLE_CLINICAL_REMINDERS)
            .select("*")
            .eq("patient_id", patient_id)
            .is_("dismissed_at", None)
            .order("created_at", desc=True)
            .execute()
        ).data or []
    except Exception as exc:
        logger.warning("reminder read-back failed for patient %s: %s", patient_id, exc)
        active = []
    return active
