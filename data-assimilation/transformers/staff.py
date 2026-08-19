"""Extract real Royan doctors from Hope's `doctors` table (staged as
`hope_doctors`) -> royan_staff.

Hope's `consultants` table was deliberately NOT used here -- inspection
showed it's a referring-facility/external-referrer directory
(refferer_doctor_id, hospital_name, referal_spot_amount, doctor_commision),
not Royan's own staff.

`doctors` itself is a mix: rows 1-11 (plus 13, 33) are English-template /
literal-"Hope"/"Test" placeholder rows created in a tight 2015-06 to
2016-06 setup window ("Physician Coon", "Joe Doe", "Hope Doctor",
"NewHope TEstDoctor") -- confirmed seed data, not real staff. Everything
else is genuine Nigerian physician data, with the same "multiple rows per
real person across re-registration events" pattern seen in patients --
deduped here by normalized name, keeping the latest by create_time.

is_deleted on the LATEST row per person is treated as the real
active/inactive signal (older superseded rows' is_deleted values are
noise from the multi-registration pattern, not a real employment signal).
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from transformers._helpers import EXTERNAL_SOURCE, safe_date, safe_str, utcnow

_ZERO_DATE = "0000-00-00 00:00:00"

# Explicit demo/setup cluster confirmed by manual inspection (see module
# docstring) -- English-template names and literal Hope/Test markers,
# clustered in the initial 2015-2016 setup window.
_DEMO_IDS = {"1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "13", "33"}


def _norm_name(name: str) -> str:
    return re.sub(r"\s+", " ", (name or "").strip().lower())


def filter_and_dedupe(raw_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Apply the demo-exclusion + name-dedup rules and return the clean
    per-person list (exposed separately from transform() so a dry-run
    preview can show exactly who will be loaded before committing)."""
    kept = []
    for row in raw_rows:
        if str(row.get("id")) in _DEMO_IDS:
            continue
        name = (row.get("doctor_name") or "").strip()
        if not name:
            continue
        ct = row.get("create_time")
        if not ct or ct == _ZERO_DATE:
            continue
        kept.append(row)

    by_name: Dict[str, Dict[str, Any]] = {}
    for row in kept:
        key = _norm_name(row.get("doctor_name"))
        existing = by_name.get(key)
        if not existing or (row.get("create_time") or "") > (existing.get("create_time") or ""):
            by_name[key] = row
    return list(by_name.values())


def transform(
    raw_rows: List[Dict[str, Any]],
    department_names: Optional[Dict[str, str]] = None,
) -> List[Dict[str, Any]]:
    department_names = department_names or {}
    people = filter_and_dedupe(raw_rows)
    out = []

    for row in people:
        ext_id = safe_str(row.get("id"))
        name = " ".join(
            p for p in [
                safe_str(row.get("first_name")),
                safe_str(row.get("middle_name")),
                safe_str(row.get("last_name")),
            ] if p
        ) or safe_str(row.get("doctor_name"))
        if not ext_id or not name:
            continue

        dept_id = safe_str(row.get("department_id"))
        department = department_names.get(dept_id) if dept_id else None
        department = (department or "").strip().rstrip(".") or "General"

        is_deleted = str(row.get("is_deleted") or "0").strip()

        out.append({
            "staff_number":      f"HOPE-DOC-{ext_id}",
            "full_name":         name,
            "department":        department,
            "designation":       "Consultant",
            "employment_type":   "full_time",
            "role":              "doctor",
            "is_active":         is_deleted != "1",
            "joined_at":         (safe_date(row.get("create_time")) or utcnow())[:10],
            "specialty":         safe_str(row.get("specility_keyword")),
            "license_number":    safe_str(row.get("licensure_no")),
            "external_source":   EXTERNAL_SOURCE,
            "external_id":       ext_id,
        })

    return out
