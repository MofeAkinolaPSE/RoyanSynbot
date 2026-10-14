"""Small, dependency-light helpers shared across clinical routers.

Kept separate from clinical_service.py (which uses raw psycopg2 cursors for
encounter-level documentation) because this module deliberately uses the
db.table() query builder instead, matching how canonical.py, nursing.py, and
pharmacy_dispensing.py already query patient data.
"""
from __future__ import annotations

from typing import List, Dict, Any

from src.db import db
import re

from src.constants import TABLE_ALLERGIES, TABLE_STAFF

_UUID_RE = re.compile(r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$')


def get_patient_allergies(patient_id: int, active_only: bool = True) -> List[Dict[str, Any]]:
    """Return a patient's allergy rows.

    Previously duplicated ad hoc in canonical.py (no status filter, so
    resolved/inactive allergies leaked into the CPRS snapshot) and in
    pharmacy_dispensing.py (filtered on a nonexistent `active` column, so the
    dispense-time interaction check silently matched nothing). This is the
    one place that query should live.
    """
    query = db.table(TABLE_ALLERGIES).select("id,allergen,reaction,severity,status").eq("patient_id", patient_id)
    if active_only:
        query = query.eq("status", "active")
    result = query.execute()
    return result.data or []


def resolve_staff_names(subs: List[str]) -> Dict[str, str]:
    """Map JWT subjects / staff ids to display names, in one query.

    Results, reports and operative notes all store WHO signed them as the
    acting user's JWT sub -- a uuid. The panels then printed that uuid:

        Verified by 779b8e0d-9a8a-4bcb-a9f2-c05c0ed39235

    which does not answer "who authenticated this result", the question the
    column exists for. Names are resolved on read rather than denormalised on
    write so a corrected staff record propagates, and because 833k historical
    rows already carry ids that cannot be rewritten.

    Unresolvable subjects are simply absent from the map -- the caller keeps
    whatever it had rather than being handed a blank. 'hope_ingest' and similar
    system markers resolve to a readable label instead of being mistaken for a
    person.
    """
    wanted = {str(x).strip() for x in subs if x and str(x).strip()}
    if not wanted:
        return {}

    out: Dict[str, str] = {}

    # System actors, not people. Named here so a migrated row reads as migrated
    # rather than as an unknown clinician.
    SYSTEM = {
        "hope_ingest": "Migrated from Hope",
        "system": "System",
        "synbot_repair": "Data repair",
    }
    for marker, label in SYSTEM.items():
        if marker in wanted:
            out[marker] = label
    wanted -= set(SYSTEM)
    if not wanted:
        return out

    # royan_staff.user_id and .id are UUID columns, so a single malformed value
    # in the IN list makes Postgres fail the entire query -- and the caller then
    # gets NO names at all, not just the bad one. Legacy rows do carry non-uuid
    # markers, so this is a real case rather than a theoretical one: filter to
    # well-formed uuids first. Anything else could never match a uuid column
    # anyway, so nothing resolvable is lost.
    ids = [i for i in wanted if _UUID_RE.match(i)]
    if not ids:
        return out

    # Two different columns hold the same kind of value depending on which
    # router wrote the row: user_id for JWT subjects, id for staff-picker
    # selections. Both are looked up rather than guessing which applies.
    for column in ("user_id", "id"):
        remaining = [i for i in ids if i not in out]
        if not remaining:
            break
        try:
            rows = (
                db.table(TABLE_STAFF).select("id,user_id,full_name")
                .in_(column, remaining).execute().data or []
            )
        except Exception:
            continue
        for r in rows:
            name = (r.get("full_name") or "").strip()
            if not name:
                continue
            key = str(r.get(column) or "")
            if key:
                out[key] = name

    return out


def attach_staff_names(rows: List[Dict[str, Any]], fields: Dict[str, str]) -> None:
    """Add display names to rows in place.

    `fields` maps the id-bearing column to the name column to write, e.g.
    {"verified_by": "verified_by_name"}. One query covers every field and every
    row, rather than one lookup per row per field.
    """
    if not rows:
        return
    subs: List[str] = []
    for r in rows:
        for src in fields:
            if r.get(src):
                subs.append(str(r[src]))
    if not subs:
        return
    names = resolve_staff_names(subs)
    for r in rows:
        for src, dest in fields.items():
            val = r.get(src)
            if val and str(val) in names:
                r[dest] = names[str(val)]
