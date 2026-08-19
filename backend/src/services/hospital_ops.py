"""
hospital_ops.py — Patient flow and clinical activity KPIs for the hospital dashboard.

All functions are safe: they query live royan_* tables and return zeros / empty
structures if the table is empty or a query fails — no 500 errors propagate upward.
"""
from __future__ import annotations

import logging
from datetime import datetime, date, timedelta
from typing import Any, Dict, List, Optional

from ..db import db
from ..cache import ttl_cache

logger = logging.getLogger("hospital_ops")

# Type alias kept simple for readability
DBClient = Any

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _today_iso() -> str:
    return date.today().isoformat()


def _parse_minutes(interval_str: Optional[str]) -> float:
    """
    Convert a Postgres INTERVAL string like '00:23:14' or '23 minutes 14 seconds'
    to total minutes (float). Returns 0.0 on parse failure.
    """
    if not interval_str:
        return 0.0
    try:
        # PostgreSQL returns interval as string e.g. '00:23:14'
        parts = str(interval_str).split(":")
        if len(parts) == 3:
            h, m, s = int(parts[0]), int(parts[1]), float(parts[2])
            return round(h * 60 + m + s / 60, 1)
    except Exception:
        pass
    return 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Patient Flow KPIs
# ─────────────────────────────────────────────────────────────────────────────

@ttl_cache(ttl_seconds=30, ignore_kwargs=("client",), tags=("hospital", "patient_flow", "executive"))
def get_patient_flow_kpis(client: DBClient = db) -> Dict[str, Any]:
    """
    Real-time patient flow metrics derived from royan_encounters.
    Only counts native system encounters (external_source IS NULL) — excludes Hope imports.

    Returns:
        patients_waiting        — active encounters in patient_registered / triaged
        active_consultations    — encounters currently in 'consulting' state
        patients_seen_today     — encounters discharged today
        avg_wait_minutes        — mean minutes from triage_at delta (today)
        total_encounters_today  — all native encounters opened today
    """
    today = _today_iso()
    result = {
        "patients_waiting":       0,
        "active_consultations":   0,
        "patients_seen_today":    0,
        "avg_wait_minutes":       0.0,
        "total_encounters_today": 0,
    }
    conn = db.pool.getconn()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT
                COUNT(*) FILTER (WHERE status NOT IN ('discharged', 'billing_pending')
                                       AND external_source IS NULL),
                COUNT(*) FILTER (WHERE status = 'consulting'
                                       AND external_source IS NULL),
                COUNT(*) FILTER (WHERE status = 'discharged'
                                       AND external_source IS NULL
                                       AND updated_at::date = %s::date),
                COUNT(*) FILTER (WHERE external_source IS NULL
                                       AND created_at::date = %s::date)
            FROM public.royan_encounters
        """, (today, today))
        cur2 = conn.cursor()
        cur2.execute("""
            SELECT ROUND(
                EXTRACT(EPOCH FROM AVG(
                    CASE WHEN triage_at IS NOT NULL AND created_at IS NOT NULL
                         THEN triage_at - created_at END
                )) / 60.0, 1
            )
            FROM public.royan_encounters
            WHERE external_source IS NULL
              AND created_at::date = %s::date
        """, (today,))
        row = cur.fetchone()
        row2 = cur2.fetchone()
        if row:
            result["patients_waiting"]       = int(row[0] or 0)
            result["active_consultations"]   = int(row[1] or 0)
            result["patients_seen_today"]    = int(row[2] or 0)
            result["total_encounters_today"] = int(row[3] or 0)
        if row2:
            result["avg_wait_minutes"]       = float(row2[0] or 0.0)
    except Exception as exc:
        logger.debug(f"get_patient_flow_kpis: SQL query failed ({exc})")
    finally:
        db.pool.putconn(conn)

    return result


# ─────────────────────────────────────────────────────────────────────────────
# Queue by Department
# ─────────────────────────────────────────────────────────────────────────────

@ttl_cache(ttl_seconds=30, ignore_kwargs=("client",), tags=("hospital", "queue", "executive"))
def get_queue_by_department(client: DBClient = db) -> List[Dict[str, Any]]:
    """
    Count active (non-discharged) native encounters grouped by department.
    Excludes Hope-imported historical data (external_source IS NULL only).

    Returns a list sorted by waiting count descending:
        [{"department": "OPD", "waiting": 4, "consulting": 2}, ...]
    """
    conn = db.pool.getconn()
    rows = []
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT
                department,
                COUNT(*) FILTER (WHERE status IN ('patient_registered', 'triaged')) AS waiting,
                COUNT(*) FILTER (WHERE status = 'consulting')                        AS consulting
            FROM public.royan_encounters
            WHERE status != 'discharged'
              AND department IS NOT NULL
              AND external_source IS NULL
            GROUP BY department
            ORDER BY waiting DESC
            LIMIT 100
        """)
        rows = cur.fetchall()
    except Exception as exc:
        logger.debug(f"get_queue_by_department: SQL query failed ({exc})")
    finally:
        db.pool.putconn(conn)

    return [
        {"department": row[0], "waiting": int(row[1] or 0), "consulting": int(row[2] or 0)}
        for row in rows
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Daily Clinical Stats
# ─────────────────────────────────────────────────────────────────────────────

@ttl_cache(ttl_seconds=60, ignore_kwargs=("client",), tags=("hospital", "clinical_stats"))
def get_daily_clinical_stats(client: DBClient = db) -> Dict[str, Any]:
    """
    Appointments, lab orders, and prescriptions for today.

    Only counts native system records (external_source IS NULL) for the pending
    counters — Hope-imported historical lab orders/prescriptions were bulk
    loaded still sitting in 'ordered'/'pending' status (their real historical
    outcome was never migrated), so without this filter these counters showed
    six-figure all-time totals instead of the live operational backlog.

    Returns:
        appointments_today  — confirmed or arrived appointments
        lab_orders_pending  — native lab orders in 'ordered' or 'sample_collected' state
        prescriptions_pending — native prescriptions awaiting dispensing
    """
    today = _today_iso()
    result = {
        "appointments_today":    0,
        "lab_orders_pending":    0,
        "prescriptions_pending": 0,
    }

    try:
        appt_resp = (
            client.table("royan_appointments")
            .select("id", count="exact")
            .in_("status", ["confirmed", "arrived"])
            .gte("booked_at", today + "T00:00:00")
            .lt("booked_at",  today + "T23:59:59")
            .execute()
        )
        result["appointments_today"] = appt_resp.count or 0
    except Exception as exc:
        logger.debug(f"get_daily_clinical_stats: appointments query failed ({exc})")

    try:
        lab_resp = (
            client.table("royan_lab_orders")
            .select("id", count="exact")
            .in_("status", ["ordered", "sample_collected", "processing"])
            .is_("external_source", None)
            .execute()
        )
        result["lab_orders_pending"] = lab_resp.count or 0
    except Exception as exc:
        logger.debug(f"get_daily_clinical_stats: lab_orders query failed ({exc})")

    try:
        rx_resp = (
            client.table("royan_prescriptions")
            .select("id", count="exact")
            .eq("status", "pending")
            .is_("external_source", None)
            .execute()
        )
        result["prescriptions_pending"] = rx_resp.count or 0
    except Exception as exc:
        logger.debug(f"get_daily_clinical_stats: prescriptions query failed ({exc})")

    return result


# ─────────────────────────────────────────────────────────────────────────────
# Patient Flow by Hour (for chart)
# ─────────────────────────────────────────────────────────────────────────────

@ttl_cache(ttl_seconds=60, ignore_kwargs=("client",), tags=("hospital", "patient_flow_chart"))
def get_patient_flow_by_hour(client: DBClient = db) -> List[Dict[str, Any]]:
    """
    Encounters created per hour today (for the Patient Flow chart).

    Returns 24 slots from 00 → 23:
        [{"hour": "08:00", "patients": 3}, ...]
    """
    today = _today_iso()
    buckets: Dict[int, int] = {h: 0 for h in range(24)}

    try:
        resp = (
            client.table("royan_encounters")
            .select("created_at")
            .gte("created_at", today + "T00:00:00")
            .lt("created_at",  today + "T23:59:59")
            .limit(2000)
            .execute()
        )
        for r in (resp.data or []):
            try:
                dt = datetime.fromisoformat(str(r["created_at"]).replace("Z", "+00:00"))
                buckets[dt.hour] += 1
            except Exception:
                pass
    except Exception as exc:
        logger.debug(f"get_patient_flow_by_hour: query failed ({exc})")

    return [{"hour": f"{h:02d}:00", "patients": buckets[h]} for h in range(24)]


# ─────────────────────────────────────────────────────────────────────────────
# Clinical Tool Handlers (used by tool_registry for Roy context)
# ─────────────────────────────────────────────────────────────────────────────

@ttl_cache(ttl_seconds=20, ignore_kwargs=("client",), tags=("hospital", "encounters"))
def get_active_encounters(limit: int = 20, client: DBClient = db) -> List[Dict[str, Any]]:
    """Return open encounter rows for Roy to surface to doctors/nurses."""
    try:
        resp = (
            client.table("royan_encounters")
            .select("id,patient_id,status,department,chief_complaint,consulting_doctor,created_at,triage_at,queue_number,nurse_done_at")
            .neq("status", "discharged")
            .is_("external_source", None)
            .order("created_at", desc=False)
            .limit(limit)
            .execute()
        )
        return resp.data or []
    except Exception as exc:
        logger.debug(f"get_active_encounters: query failed ({exc})")
        return []


@ttl_cache(ttl_seconds=20, ignore_kwargs=("client",), tags=("hospital", "lab_orders"))
def get_pending_lab_orders(limit: int = 20, client: DBClient = db) -> List[Dict[str, Any]]:
    """Return lab orders pending processing — for DocRoy and LabRoy."""
    try:
        resp = (
            client.table("royan_lab_orders")
            .select("id,patient_id,encounter_id,test_name,status,ordered_at,ordered_by")
            .in_("status", ["ordered", "sample_collected", "processing"])
            .order("ordered_at", desc=False)
            .limit(limit)
            .execute()
        )
        return resp.data or []
    except Exception as exc:
        logger.debug(f"get_pending_lab_orders: query failed ({exc})")
        return []


@ttl_cache(ttl_seconds=20, ignore_kwargs=("client",), tags=("hospital", "prescriptions"))
def get_pending_prescriptions(limit: int = 20, client: DBClient = db) -> List[Dict[str, Any]]:
    """Return prescriptions awaiting dispensing — for PharmRoy."""
    try:
        resp = (
            client.table("royan_prescriptions")
            .select("id,patient_id,encounter_id,drug_name,dosage,quantity,status,prescribed_at,prescribed_by")
            .eq("status", "pending")
            .order("prescribed_at", desc=False)
            .limit(limit)
            .execute()
        )
        return resp.data or []
    except Exception as exc:
        logger.debug(f"get_pending_prescriptions: query failed ({exc})")
        return []


@ttl_cache(ttl_seconds=30, ignore_kwargs=("client",), tags=("hospital", "beds"))
def get_bed_status(client: DBClient = db) -> List[Dict[str, Any]]:
    """Return ward bed occupancy summary — for NurseRoy and admin."""
    try:
        resp = (
            client.table("royan_beds")
            .select("id,ward_id,bed_number,status,current_patient_id")
            .order("ward_id")
            .limit(200)
            .execute()
        )
        rows = resp.data or []
    except Exception as exc:
        logger.debug(f"get_bed_status: query failed ({exc})")
        return []

    ward_map: Dict[str, Dict[str, int]] = {}
    for r in rows:
        wid = str(r.get("ward_id") or "unknown")
        if wid not in ward_map:
            ward_map[wid] = {"total": 0, "occupied": 0, "available": 0}
        ward_map[wid]["total"] += 1
        if r.get("status") == "occupied":
            ward_map[wid]["occupied"] += 1
        else:
            ward_map[wid]["available"] += 1

    return [{"ward_id": wid, **counts} for wid, counts in ward_map.items()]


def get_patient_record(identifier: str, client: DBClient = db) -> Dict[str, Any]:
    """Resolve a patient by MRN or name fragment and return a Roy-facing
    summary — demographics, active encounter, and open clinical items.

    This is the tool `getActiveEncounters` (list of currently-open encounters)
    could never answer: "pull up patient X" needs to search the FULL patient
    roster, not just who happens to be mid-visit right now. Not cached —
    a stale "patient not found" would be worse than an extra query.
    """
    term = (identifier or "").strip()
    if not term:
        return {"found": False, "query": identifier, "message": "No patient name or MRN was given."}

    try:
        # MRN is the unambiguous fast path — exact match, case-insensitive.
        exact = (
            client.table("royan_patients")
            .select("id,mrn,first_name,last_name,date_of_birth,gender,phone,hmo_provider,hmo_id")
            .ilike("mrn", term)
            .limit(1)
            .execute()
        )
        matches = exact.data or []
        if not matches:
            # Name search — every word must appear somewhere in first/last name,
            # matching the same "AND-across-words" approach proven in the
            # Front Desk / patient registration search (a naive single ILIKE
            # on a full "First Last" string misses reordered or partial names).
            words = [w for w in term.split() if w]
            query = (
                client.table("royan_patients")
                .select("id,mrn,first_name,last_name,date_of_birth,gender,phone,hmo_provider,hmo_id")
            )
            for w in words[:4]:
                query = query.or_(f"first_name.ilike.%{w}%,last_name.ilike.%{w}%")
            resp = query.order("registered_at", desc=True).limit(5).execute()
            matches = resp.data or []
    except Exception as exc:
        logger.warning(f"get_patient_record({identifier!r}): search failed ({exc})")
        return {"found": False, "query": identifier, "message": "Patient search failed due to a system error."}

    if not matches:
        return {"found": False, "query": identifier, "message": f"No patient matching '{identifier}' was found in the system."}

    if len(matches) > 1:
        return {
            "found": False,
            "query": identifier,
            "message": f"Multiple patients match '{identifier}' — ask the user to confirm which one by MRN.",
            "candidates": [
                {"mrn": m.get("mrn"), "name": f"{m.get('first_name', '')} {m.get('last_name', '')}".strip()}
                for m in matches
            ],
        }

    patient = matches[0]
    patient_id = patient.get("id")
    mrn = patient.get("mrn")
    name = f"{patient.get('first_name', '')} {patient.get('last_name', '')}".strip()

    active_encounter = None
    notes_count = 0
    active_prescriptions: List[str] = []
    pending_labs: List[str] = []
    try:
        enc = (
            client.table("royan_encounters")
            .select("id,status,department,encounter_type,chief_complaint,created_at")
            .eq("patient_id", patient_id)
            .neq("status", "discharged")
            .is_("external_source", None)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if enc.data:
            active_encounter = enc.data[0]
    except Exception as exc:
        logger.debug(f"get_patient_record: active encounter lookup failed ({exc})")

    try:
        notes = client.table("royan_encounter_notes").select("id", count="exact").eq("patient_id", patient_id).execute()
        notes_count = notes.count or 0
    except Exception as exc:
        logger.debug(f"get_patient_record: notes count failed ({exc})")

    try:
        rx = (
            client.table("royan_prescriptions")
            .select("drug_name")
            .eq("patient_id", patient_id)
            .in_("status", ["pending", "partially_dispensed"])
            .limit(10)
            .execute()
        )
        active_prescriptions = [r.get("drug_name") for r in (rx.data or []) if r.get("drug_name")]
    except Exception as exc:
        logger.debug(f"get_patient_record: prescriptions lookup failed ({exc})")

    try:
        labs = (
            client.table("royan_lab_orders")
            .select("test_name")
            .eq("patient_id", patient_id)
            .in_("status", ["ordered", "sample_collected", "processing"])
            .limit(10)
            .execute()
        )
        pending_labs = [r.get("test_name") for r in (labs.data or []) if r.get("test_name")]
    except Exception as exc:
        logger.debug(f"get_patient_record: lab orders lookup failed ({exc})")

    return {
        "found": True,
        "patient_id": patient_id,
        "mrn": mrn,
        "name": name,
        "date_of_birth": patient.get("date_of_birth"),
        "gender": patient.get("gender"),
        "phone": patient.get("phone"),
        "hmo_provider": patient.get("hmo_provider"),
        "active_encounter": active_encounter,
        "clinical_notes_count": notes_count,
        "active_prescriptions": active_prescriptions,
        "pending_lab_orders": pending_labs,
        "profile_url": f"/hospital/patients/{mrn}" if mrn else None,
    }


@ttl_cache(ttl_seconds=60, ignore_kwargs=("client",), tags=("hospital", "encounters"))
def get_patient_by_id(patient_id: int, client: DBClient = db) -> Optional[Dict[str, Any]]:
    """Cached patient lookup by ID — prevents N×1 DB calls in notification/encounter enrichment."""
    try:
        resp = (
            client.table("royan_patients")
            .select("id,first_name,last_name,phone,mrn")
            .eq("id", patient_id)
            .limit(1)
            .execute()
        )
        rows = resp.data or []
        return rows[0] if rows else None
    except Exception as exc:
        logger.debug(f"get_patient_by_id({patient_id}): query failed ({exc})")
        return None
