from __future__ import annotations
import logging
from typing import Dict, Any, List, Optional
from typing import Any as DBClient
from datetime import date
from ..db import db
from ..constants import TABLE_STAFF, TABLE_TIMESHEETS
logger = logging.getLogger("ops")

# --- Staff Registry Logic ---

def resolve_department_id(department: str, client: DBClient = db) -> Optional[int]:
    """Look up the canonical royan_departments.id for a free-text department name.

    Matches case-insensitively against name, short_name, or code. Returns None
    if there's no match — callers should still store the free-text value and
    treat department_id as a best-effort enrichment, not a hard requirement.
    """
    if not department:
        return None
    try:
        resp = client.table("royan_departments").select("id,name,short_name,code").eq("is_active", True).execute()
        rows = resp.data or []
    except Exception as e:
        logger.warning(f"resolve_department_id: could not query royan_departments: {e}")
        return None
    needle = department.strip().lower()
    for row in rows:
        if needle in {
            (row.get("name") or "").strip().lower(),
            (row.get("short_name") or "").strip().lower(),
            (row.get("code") or "").strip().lower(),
        }:
            return row.get("id")
    return None


def create_staff_member(
    full_name: str,
    email: str,
    department: str,
    role: str,
    client: DBClient = db
) -> Dict[str, Any]:
    """Create a new staff record (Identity only, no authentication/user creation)."""
    payload = {
        "full_name": full_name,
        "email": email,
        "department": department,
        "role": role,
        "status": "active"
    }
    resp = client.table(TABLE_STAFF).insert(payload).execute()
    return resp.data[0] if resp.data else {}

def get_staff_by_department(department: Optional[str] = None, client: DBClient = db) -> List[Dict[str, Any]]:
    """List staff, optionally filtered by department. Excludes quarantined (non-staff) records."""
    query = client.table(TABLE_STAFF).select("*").is_("quarantined_at", "null")
    if department:
        query = query.eq("department", department)
    resp = query.execute()
    return resp.data or []

def get_staff_by_id(staff_id: str, client: DBClient = db) -> Optional[Dict[str, Any]]:
    resp = client.table(TABLE_STAFF).select("*").eq("id", staff_id).execute()
    return resp.data[0] if resp.data else None

def get_staff_by_user_id(user_id: str, client: DBClient = db) -> Optional[Dict[str, Any]]:
    """Resolve a royan_users.id (the JWT `sub`) to its linked staff identity.
    Filters quarantined_at IS NULL — the ~2,297-row Sage-customer-import
    contamination incident is exactly what that filter guards against, and
    unlike get_staff_by_id above this is used for identity display, not just
    lookup-by-known-staff-id, so it must not resurface a contaminated row."""
    resp = (
        client.table(TABLE_STAFF)
        .select("id,full_name,role,department,user_id")
        .eq("user_id", user_id)
        .is_("quarantined_at", "null")
        .limit(1)
        .execute()
    )
    return resp.data[0] if resp.data else None

def get_staff_by_email(email: str, client: DBClient = db) -> Optional[Dict[str, Any]]:
    resp = client.table(TABLE_STAFF).select("*").eq("email", email.lower().strip()).execute()
    return resp.data[0] if resp.data else None

def get_my_profile(email: str, client: DBClient = db) -> Optional[Dict[str, Any]]:
    return get_staff_by_email(email, client)

def update_my_profile(email: str, patch_data: Dict[str, Any], client: DBClient = db) -> Optional[Dict[str, Any]]:
    """Partial-update the calling user's own staff record. Only allows safe self-service fields."""
    allowed = {"full_name", "department", "designation", "phone", "metadata", "tour_state"}
    clean = {k: v for k, v in patch_data.items() if k in allowed}
    if not clean:
        return get_staff_by_email(email, client)
    if "department" in clean:
        clean["department_id"] = resolve_department_id(clean["department"], client)
    # Merge metadata rather than overwrite
    if "metadata" in clean:
        existing = get_staff_by_email(email, client)
        if existing:
            merged_meta = {**(existing.get("metadata") or {}), **clean["metadata"]}
            clean["metadata"] = merged_meta
        # specialty/license_number live inside this same metadata blob today
        # (populated by the KYC onboarding flow) — copy through to the
        # first-class columns whenever metadata changes, so they stay
        # queryable instead of only living inside the jsonb blob.
        if clean["metadata"].get("specialty"):
            clean["specialty"] = clean["metadata"]["specialty"]
        if clean["metadata"].get("medical_council_number"):
            clean["license_number"] = clean["metadata"]["medical_council_number"]
    resp = client.table(TABLE_STAFF).update(clean).eq("email", email.lower().strip()).execute()
    return resp.data[0] if resp.data else None

# --- Timesheet Logic ---

def record_timesheet_entry(
    staff_id: str,
    work_date: date,
    hours: float,
    department: str,
    note: Optional[str],
    recorded_by: str,
    client: DBClient = db
) -> Dict[str, Any]:
    """Record a single timesheet entry (submitted for HR review, like a clock-out).

    royan_timesheets keeps the note in `notes` - there is no activity_note column,
    so this insert used to fail for every call.
    """
    payload = {
        "staff_id": staff_id,
        "date": work_date.isoformat(),
        "hours_worked": hours,
        "department": department,
        "notes": note,
        "recorded_by": recorded_by,
        "source": "manual",
        "status": "submitted",
    }
    resp = client.table(TABLE_TIMESHEETS).insert(payload).execute()
    return resp.data[0] if resp.data else {}

def get_timesheets(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    department: Optional[str] = None,
    staff_id: Optional[str] = None,
    limit: int = 100,
    client: DBClient = db
) -> List[Dict[str, Any]]:
    """Query timesheets with flexible filters."""
    query = client.table(TABLE_TIMESHEETS).select("*")
    
    if start_date:
        query = query.gte("date", start_date.isoformat())
    if end_date:
        query = query.lte("date", end_date.isoformat())
    if department:
        query = query.eq("department", department)
    if staff_id:
        query = query.eq("staff_id", staff_id)
        
    resp = query.order("date", desc=True).limit(limit).execute()
    return resp.data or []


def sync_staff_batch(staff_rows: List[Dict[str, Any]], client: DBClient = db) -> int:
    """
    Syncs a batch of staff rows from Sage import to the live royan_staff table.
    Matches strictly on 'email' to avoid duplicates.
    Updates full_name, department, role if found.
    Inserts if new (and has email).
    Returns count of processed records.
    """
    to_upsert = []
    for row in staff_rows:
        email = (row.get("email") or "").strip()
        # Synthesize a stable placeholder email if missing to satisfy NOT NULL/UNIQUE
        # Uses staff_id if available, else a slug from full_name.
        if not email or "@" not in email:
            sid = (row.get("staff_id") or "").strip()
            if sid:
                email = f"staff-{sid.lower()}@placeholder.local"
            else:
                name = (row.get("full_name") or "unknown").strip().lower().replace(" ", "-")
                email = f"staff-{name}@placeholder.local"

        # Map Sage fields to royan_staff fields
        # Note: 'staff_id' from Sage is ignored in favor of UUID, 
        # unless we add an external_id column later.
        record = {
            "email": email.lower().strip(),
            "full_name": row.get("full_name"),
            "department": row.get("department") or "Operations", # Default if missing
            "role": row.get("role"),
            "status": "active" # Reactivate if previously inactive? Or trust source?
        }
        
        # simple validation for department as per constraint
        if record["department"] not in ('Finance', 'Sales', 'Operations', 'HR', 'Management'):
            record["department"] = "Operations" # Fallback
            
        to_upsert.append(record)
        
    if not to_upsert:
        return 0
        
    # Batch upsert
    # on_conflict="email" handles the update vs insert
    try:
        resp = client.table(TABLE_STAFF).upsert(to_upsert, on_conflict="email").execute()
        return len(resp.data) if resp.data else 0
    except Exception as e:
        logger.error(f"Failed to sync staff batch: {e}")
        return 0


def get_latest_staff_snapshot(limit: int = 1000, client: DBClient = db) -> List[Dict[str, Any]]:
    """Return latest staff snapshot rows (append-only) for visibility/fallback.

    Orders by imported_at desc then id desc; limits results. Deduplicates by email if present.
    No batch_id filter — the KPI batch_id belongs to finance/GL and has no rows here.
    Returns an empty list when the sage_staff_snapshot table is absent (hospital deployment).
    """
    try:
        q = client.table("sage_staff_snapshot").select(
            "staff_id,full_name,email,department,role,status,imported_at"
        )
        resp = q.order("imported_at", desc=True).order("id", desc=True).limit(limit).execute()
        rows = resp.data or []
    except Exception as e:
        logger.debug(f"get_latest_staff_snapshot: sage_staff_snapshot unavailable ({e})")
        return []
    latest_by_email: Dict[str, Dict[str, Any]] = {}
    result: List[Dict[str, Any]] = []
    for r in rows:
        email = (r.get("email") or "").strip().lower()
        if email:
            if email in latest_by_email:
                continue
            latest_by_email[email] = r
            result.append(r)
        else:
            result.append(r)
    return result
