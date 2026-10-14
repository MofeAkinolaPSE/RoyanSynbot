"""Clinical queue and encounter workflow router."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.constants import (
    ENCOUNTER_STATUS_ALLOWED,
    ENCOUNTER_STATUS_TRANSITIONS,
    ENCOUNTER_TYPES,
    HOSPITAL_DEPARTMENTS,
    TABLE_APPOINTMENTS,
    TABLE_BILLING,
    TABLE_DISPENSING,
    TABLE_ENCOUNTER_NOTES,
    TABLE_ENCOUNTERS,
    TABLE_HMOS,
    TABLE_LAB_ORDERS,
    TABLE_PATIENT_INSURANCE,
    TABLE_ADMISSION_REQUESTS,
    TABLE_INPATIENT_BILL_LINES,
    TABLE_WARDS,
    TABLE_BEDS,
    TABLE_ROOM_ASSIGNMENTS,
    TABLE_LAB_RESULTS,
    TABLE_NOTE_ADDENDA,
    TABLE_NOTE_TITLES,
    TABLE_PATIENTS,
    TABLE_PAYMENTS,
    TABLE_PRESCRIPTIONS,
    TABLE_RADIOLOGY_ORDERS,
    TABLE_STAFF,
    PRESENCE_STALE_SECONDS,
    TABLE_VITALS,
    TRIAGE_LEVELS,
)
from src.cache import invalidate_cache_tags
from src.db import audit_event, db
from src.middleware import verify_jwt
from src.services.patient_context import invalidate_patient_context
from src.services.realtime import realtime_hub

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/queue", tags=["Clinical Queue"])

# Department → short queue prefix mapping
_DEPT_PREFIX: dict[str, str] = {
    "OPD": "OPD",
    "A&E": "AE",
    "Maternity": "MAT",
    "Surgery": "SUR",
    "Inpatient Ward": "IPD",
    "Laboratory & Diagnostics": "LAB",
    "Pharmacy": "PHM",
    "Billing & Finance": "BIL",
    "Administration": "ADM",
    "Maintenance & Facilities": "MNT",
}


class EncounterCreate(BaseModel):
    patient_id: int | str
    encounter_type: str = "outpatient"
    department: Optional[str] = "OPD"
    chief_complaint: Optional[str] = None
    registered_by: Optional[str] = None
    # Chosen by front desk at registration. A patient WITH cover may still elect
    # to pay privately, so this is a decision, not something to re-derive from
    # the patient record on every read.
    payer_type: Optional[str] = None
    membership_id: Optional[str] = None
    # What the desk decided at check-in: how urgent the patient looked, and - when the patient is
    # going straight to a doctor - which doctor (royan_staff.id) and room. The doctor's dashboard
    # lists the patient from that moment.
    priority: Optional[str] = None
    doctor_id: Optional[str] = None
    consulting_room: Optional[str] = None
    # Stage billing: the front desk bills registration (new patients) and the consultation before the patient
    # sees the doctor. The specialty / first visit vs follow-up are pre-filled (front-desk-quote) and can be changed.
    consultation_specialty: Optional[str] = None
    visit_kind: Optional[str] = None            # initial | follow_up | review
    bill_now: bool = True


def _find_active_encounter(patient_id: int | str) -> Optional[dict]:
    """A patient's current non-discharged, native (not Hope-imported) encounter,
    if any — the single source of truth for "is this patient already on the
    queue," shared by both the open_encounter dedup check below and the
    active-encounter lookup endpoint so the two can never drift apart."""
    existing = (
        db.table(TABLE_ENCOUNTERS)
        .select("id,queue_number,status,department,encounter_type,created_at")
        .eq("patient_id", patient_id)
        .neq("status", "discharged")
        .is_("external_source", None)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    return existing.data[0] if existing.data else None


class TriageRequest(BaseModel):
    triage_level: Optional[str] = None
    triage_priority: Optional[str] = None
    triage_notes: Optional[str] = None
    chief_complaint: Optional[str] = None
    triage_by: Optional[str] = None

    model_config = {"extra": "ignore"}


class ConsultRequest(BaseModel):
    doctor_id: Optional[str] = None
    consulting_doctor: Optional[str] = None
    diagnosis_codes: Optional[list[str]] = None
    diagnosis_notes: Optional[str] = None


class AdvanceRequest(BaseModel):
    new_status: str
    notes: Optional[str] = None


class DischargeRequest(BaseModel):
    discharge_summary: str = Field(..., min_length=1)


class CallPatientRequest(BaseModel):
    room: Optional[str] = None
    discharge_by: Optional[str] = None


class AssignNurseRequest(BaseModel):
    nurse_id: Optional[str] = None  # royan_staff.id; None clears the assignment


class PauseConsultationRequest(BaseModel):
    reason: Optional[str] = None


class EndConsultationRequest(BaseModel):
    force_status: Optional[str] = None  # explicit override; still validated by _assert_transition
    disposition_notes: Optional[str] = None
    # True: "see the patient again when the results are back" (the visit returns for review when the last result
    # arrives). False: "end consultation" (results arriving move the visit on to pharmacy / payment).
    review_results: bool = False


class EncounterNoteCreate(BaseModel):
    note_type: str = "general"  # general | assessment | plan | soap | progress | discharge | nursing | handover | referral_letter | soap_summary
    note_title_id: Optional[int] = None  # resolves note_type from royan_note_titles.category when given
    note_title: Optional[str] = None     # denormalized title text; falls back to the looked-up title
    content: Optional[str] = None        # required unless SOAP fields are given (server composes a fallback)
    subjective: Optional[str] = None
    objective: Optional[str] = None
    assessment: Optional[str] = None
    plan: Optional[str] = None
    icd10_codes: Optional[list[str]] = None
    vitals_id: Optional[int] = None
    signed_by: Optional[str] = None      # staff.id override; auto-resolved from the acting user if omitted

    model_config = {"extra": "ignore"}


def _get_encounter(encounter_id: int) -> dict:
    result = db.table(TABLE_ENCOUNTERS).select("*").eq("id", encounter_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail=f"Encounter {encounter_id} not found")
    return result.data[0]


def _resolve_patient_id(value: int | str) -> int:
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if text.isdigit():
        return int(text)
    patient = db.table(TABLE_PATIENTS).select("id").eq("mrn", text.upper()).limit(1).execute()
    if not patient.data:
        raise HTTPException(status_code=404, detail=f"Patient '{value}' not found")
    return int(patient.data[0]["id"])


def _resolve_staff_id_for_user(user: dict) -> Optional[str]:
    """Map the acting JWT subject (an auth user id) to their own royan_staff.id,
    via royan_staff.user_id — the two are different uuid spaces, `sub` is never
    itself a valid royan_staff.id, so it can't be passed through directly."""
    sub = user.get("sub")
    if not sub:
        return None
    r = db.table(TABLE_STAFF).select("id").eq("user_id", sub).limit(1).execute()
    return r.data[0]["id"] if r.data else None


def _resolve_author_name(user: dict) -> str:
    """Display name for a clinical note author.

    Prefers the clinician's royan_staff.full_name over the JWT email. A note is
    a medico-legal document that may be read years later, quite possibly by
    someone outside the organisation — "Dr. Amaka Obi" is an attribution,
    "a.obi@royanhospital.com" is a login. Falls back to email, then to the raw
    subject, so a note is never left unattributed.
    """
    sub = user.get("sub")
    if sub:
        try:
            r = db.table(TABLE_STAFF).select("full_name").eq("user_id", sub).limit(1).execute()
            name = (r.data[0].get("full_name") if r.data else None) or ""
            if name.strip():
                return name.strip()
        except Exception:
            logger.debug("Staff name lookup failed for %s", sub, exc_info=True)
    return user.get("email") or str(sub or "unknown")


def _assert_transition(current: str, target: str) -> None:
    if target not in ENCOUNTER_STATUS_ALLOWED:
        raise HTTPException(status_code=422, detail=f"Unknown encounter status '{target}'")
    if target not in ENCOUNTER_STATUS_TRANSITIONS.get(current, set()):
        raise HTTPException(
            status_code=409,
            detail=f"Cannot transition from '{current}' to '{target}'. Allowed: {sorted(ENCOUNTER_STATUS_TRANSITIONS.get(current, set()))}",
        )


def format_patient_age(dob: Optional[str]) -> Optional[str]:
    """Age in the units a clinician actually uses at that age.

    Asked for explicitly: "for the age, we need to start from hours. If the baby
    is 24 hours old, it needs to write 24 hours... if it's one month old, it
    needs to write one month... After that, we just start counting years."

    A neonate's age in years is 0, which tells a paediatrician nothing. Hours
    matter in the first day, days in the first month, months in the first year.
    """
    if not dob:
        return None
    try:
        born = datetime.fromisoformat(str(dob).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    if born.tzinfo is not None:
        born = born.replace(tzinfo=None)

    delta = datetime.now() - born
    if delta.total_seconds() < 0:
        return None

    hours = int(delta.total_seconds() // 3600)
    if hours < 24:
        return "%d hour%s" % (hours, "" if hours == 1 else "s")

    days = delta.days
    if days < 31:
        return "%d day%s" % (days, "" if days == 1 else "s")

    months = days // 30
    if months < 12:
        return "%d month%s" % (months, "" if months == 1 else "s")

    return "%dy" % (days // 365)


def _enrich_encounters(rows: list[dict]) -> list[dict]:
    patient_ids = list({row.get("patient_id") for row in rows if row.get("patient_id") is not None})
    encounter_ids = list({row.get("id") for row in rows if row.get("id") is not None})
    nurse_ids = list({row.get("assigned_nurse_id") for row in rows if row.get("assigned_nurse_id")})

    patient_map: dict = {}
    if patient_ids:
        try:
            patients = (
                db.table(TABLE_PATIENTS)
                .select("id,mrn,first_name,last_name,phone,hmo_provider,hmo_id,patient_type,date_of_birth,gender")
                .in_("id", patient_ids)
                .execute()
            )
            patient_map = {row["id"]: row for row in patients.data or []}
        except Exception:
            patient_map = {}

    # Primary insurance, one query for the whole queue. Asked for in both
    # meetings: "if the patient is HMO, that insurance ID number should always
    # appear on the list". royan_patient_insurance was empty until the Phase D
    # load; it now covers 18,124 patients.
    insurance_map: dict = {}
    if patient_ids:
        try:
            pol = (
                db.table(TABLE_PATIENT_INSURANCE)
                .select("patient_id,hmo_id,plan_id,membership_id,status,is_primary")
                .in_("patient_id", patient_ids)
                .eq("is_primary", True)
                .eq("status", "active")
                .execute()
            )
            hmo_ids = list({r["hmo_id"] for r in pol.data or [] if r.get("hmo_id")})
            hmo_names: dict = {}
            if hmo_ids:
                hm = db.table(TABLE_HMOS).select("id,name").in_("id", hmo_ids).execute()
                hmo_names = {r["id"]: r.get("name") for r in hm.data or []}
            # the plan's name lives on the plan (royan_hmo_plans), not the policy row - selecting a
            # plan_name column that does not exist made this whole lookup fail on every queue load
            plan_ids = list({r["plan_id"] for r in pol.data or [] if r.get("plan_id")})
            plan_names: dict = {}
            if plan_ids:
                pl = db.table("royan_hmo_plans").select("id,name").in_("id", plan_ids).execute()
                plan_names = {r["id"]: r.get("name") for r in pl.data or []}
            for r in pol.data or []:
                insurance_map[r["patient_id"]] = {
                    "membership_id": r.get("membership_id"),
                    "plan_name": plan_names.get(r.get("plan_id")),
                    "hmo_name": hmo_names.get(r.get("hmo_id")),
                }
        except Exception as exc:
            logger.warning("queue insurance lookup failed: %s", exc)
            insurance_map = {}

    nurse_map: dict = {}
    if nurse_ids:
        try:
            nurses = db.table(TABLE_STAFF).select("id,full_name").in_("id", nurse_ids).execute()
            nurse_map = {row["id"]: row.get("full_name") for row in nurses.data or []}
        except Exception:
            nurse_map = {}

    # Lab/Radiology order counts + a "has assessment note" flag per encounter —
    # matches Hope's "LAB 0/0, RAD 0/0" + Initial Assmt/SOAP indicators on the
    # Outpatient Dashboard row. Batched (one query per domain, not per row).
    lab_counts: dict = {}
    rad_counts: dict = {}
    rx_counts: dict = {}
    note_flags: dict = {}
    if encounter_ids:
        try:
            lab_rows = db.table(TABLE_LAB_ORDERS).select("encounter_id,status").in_("encounter_id", encounter_ids).execute().data or []
            for r in lab_rows:
                eid = r.get("encounter_id")
                bucket = lab_counts.setdefault(eid, {"total": 0, "done": 0})
                bucket["total"] += 1
                if r.get("status") in ("resulted", "sent_out"):
                    bucket["done"] += 1
        except Exception:
            pass
        try:
            rad_rows = db.table(TABLE_RADIOLOGY_ORDERS).select("encounter_id,status").in_("encounter_id", encounter_ids).execute().data or []
            for r in rad_rows:
                eid = r.get("encounter_id")
                bucket = rad_counts.setdefault(eid, {"total": 0, "done": 0})
                bucket["total"] += 1
                if r.get("status") == "reported":
                    bucket["done"] += 1
        except Exception:
            pass
        try:
            rx_rows = db.table(TABLE_PRESCRIPTIONS).select("encounter_id,status").in_("encounter_id", encounter_ids).execute().data or []
            for r in rx_rows:
                eid = r.get("encounter_id")
                bucket = rx_counts.setdefault(eid, {"total": 0, "done": 0})
                bucket["total"] += 1
                if r.get("status") in ("dispensed", "partially_dispensed"):
                    bucket["done"] += 1
        except Exception:
            pass
        try:
            note_rows = (
                db.table(TABLE_ENCOUNTER_NOTES).select("encounter_id,note_type")
                .in_("encounter_id", encounter_ids)
                .in_("note_type", ["assessment", "soap", "soap_summary", "progress"])
                .execute().data or []
            )
            for r in note_rows:
                note_flags[r.get("encounter_id")] = True
        except Exception:
            pass

    enriched: list[dict] = []
    for row in rows:
        patient = patient_map.get(row.get("patient_id")) or {}
        name = f"{patient.get('first_name', '')} {patient.get('last_name', '')}".strip()
        eid = row.get("id")
        lab = lab_counts.get(eid, {"total": 0, "done": 0})
        rad = rad_counts.get(eid, {"total": 0, "done": 0})
        rx = rx_counts.get(eid, {"total": 0, "done": 0})
        enriched.append({
            **row,
            "patient": patient or None,
            "patient_name": name or None,
            "mrn": patient.get("mrn"),
            "hmo_provider": patient.get("hmo_provider"),
            "hmo_id": patient.get("hmo_id"),
            "patient_type": patient.get("patient_type"),
            "gender": patient.get("gender"),
            "age_display": format_patient_age(patient.get("date_of_birth")),
            # "private" vs "hmo" decided by whether a policy actually exists,
            # not by a flag someone remembered to set.
            # The choice made at registration wins. Only fall back to "does this
            # patient hold a policy" for historical rows, where nobody was asked.
            "payer_type": row.get("payer_type") or ("hmo" if insurance_map.get(row.get("patient_id")) else "private"),
            "insurance": (
                {**(insurance_map.get(row.get("patient_id")) or {}), "membership_id": row["membership_id"]}
                if row.get("membership_id")
                else insurance_map.get(row.get("patient_id"))
            ),
            "assigned_nurse_name": nurse_map.get(row.get("assigned_nurse_id")),
            "lab_order_count": lab["total"],
            "lab_resulted_count": lab["done"],
            "radiology_order_count": rad["total"],
            "radiology_resulted_count": rad["done"],
            "prescription_count": rx["total"],
            "prescription_dispensed_count": rx["done"],
            "has_assessment_note": bool(note_flags.get(eid)),
        })
    return enriched


def _outstanding_by_encounter(encounter_ids: list) -> dict:
    """What the patient still owes on each visit: bills (not void) less receipts (not void). The HMO's share is not
    the patient's to pay at the till."""
    if not encounter_ids:
        return {}
    from src.fin.db import q as _q, tx as _tx
    with _tx() as conn:
        rows = _q(conn, """SELECT b.encounter_id, SUM(GREATEST(b.patient_balance - COALESCE(p.paid, 0), 0)) AS owed
                           FROM royan_billing b
                           LEFT JOIN LATERAL (SELECT SUM(amount) AS paid FROM royan_payments
                                              WHERE billing_id=b.id AND COALESCE(status,'posted') <> 'void') p ON true
                           WHERE b.encounter_id = ANY(%s) AND b.status NOT IN ('void','waived','written_off')
                           GROUP BY 1""", (list(encounter_ids),))
    return {int(r["encounter_id"]): float(r["owed"] or 0) for r in rows}


def open_encounter_for_patient(
    patient_id: int,
    *,
    encounter_type: str = "outpatient",
    department: Optional[str] = None,
    chief_complaint: Optional[str] = None,
    registered_by: Optional[str] = None,
    payer_type: Optional[str] = None,
    membership_id: Optional[str] = None,
    actor_sub: Optional[str] = None,
    priority: Optional[str] = None,
    doctor_id: Optional[str] = None,
    consulting_room: Optional[str] = None,
) -> tuple[dict, bool]:
    """Core "open an encounter" logic, shared by POST /encounters and any other
    flow that should land a patient on the live clinical queue (e.g. marking an
    appointment as arrived). Returns (encounter, already_active) — already_active
    is True when the patient already had a non-discharged encounter and this
    call reused it instead of creating a duplicate."""
    patient = db.table(TABLE_PATIENTS).select("id,mrn,first_name,last_name").eq("id", patient_id).limit(1).execute()
    if not patient.data:
        raise HTTPException(status_code=404, detail=f"Patient {patient_id} not found")

    # Don't silently create a second open encounter for a patient who already has one —
    # this is what produced duplicate queue numbers when the CPRS page suggested
    # "New Encounter" for a patient whose Front-Desk encounter just hadn't refreshed yet.
    existing = _find_active_encounter(patient_id)
    if existing:
        return existing, True

    dept = department or "OPD"
    data = {
        "patient_id": patient_id,
        "encounter_type": encounter_type,
        "department": dept,
        "chief_complaint": chief_complaint,
        "status": "patient_registered",
        "registered_by": registered_by or actor_sub or "system",
    }
    # Only written when front desk actually chose. Omitted rather than defaulted
    # to "private", so a NULL keeps meaning "nobody said" and the queue can fall
    # back to the policy on file.
    if payer_type in ("private", "hmo"):
        data["payer_type"] = payer_type
        if payer_type == "hmo" and membership_id:
            data["membership_id"] = membership_id.strip()
    if priority:
        if priority not in ("normal", "urgent", "emergency"):
            raise HTTPException(status_code=422, detail="priority must be normal, urgent or emergency")
        data["arrival_priority"] = priority
        # The front desk has already sorted the patient (priority, doctor, room): that is the triage, so the patient
        # arrives on the queue ready for vitals and nobody is asked to triage them again.
        data["status"] = "triaged"
        data["triage_level"] = {"emergency": "immediate", "urgent": "urgent"}.get(priority, "non_urgent")
        data["triage_at"] = datetime.now(timezone.utc).isoformat()
        data["triage_by"] = actor_sub or registered_by or "front desk"
    if doctor_id:
        doc = db.table(TABLE_STAFF).select("id,full_name,role").eq("id", doctor_id).limit(1).execute().data
        if not doc or doc[0].get("role") != "doctor":
            raise HTTPException(status_code=422, detail="Choose a doctor from the list")
        data["doctor_id"] = doctor_id
        data["consulting_doctor"] = doc[0].get("full_name")
        if not consulting_room:
            # the doctor's consulting room for today (front desk: Consulting rooms today) goes with the patient
            try:
                ra = (db.table(TABLE_ROOM_ASSIGNMENTS).select("room").eq("doctor_id", doctor_id)
                      .eq("assigned_on", datetime.now().date().isoformat()).limit(1).execute().data)
                consulting_room = ra[0]["room"] if ra else None
            except Exception:
                consulting_room = None
    if consulting_room:
        data["consulting_room"] = consulting_room.strip()
    try:
        result = db.table(TABLE_ENCOUNTERS).insert(data).execute()
    except Exception as exc:
        logger.error("Encounter creation failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to open encounter")

    encounter = (result.data or [data])[0]

    # Generate queue number (e.g. OPD-001) and write back to DB
    queue_number: Optional[str] = None
    enc_id = encounter.get("id")
    if enc_id is not None:
        try:
            prefix = _DEPT_PREFIX.get(dept, dept[:3].upper().replace("/", "").replace(" ", ""))
            today = datetime.now(timezone.utc).date().isoformat()
            conn = db.pool.getconn()
            try:
                cur = conn.cursor()
                # Serialize the count-then-write below across concurrent requests for the
                # same department+day so two near-simultaneous encounters can never be
                # handed the same queue number. Postgres releases this lock automatically
                # at the end of the transaction (conn.commit() below).
                cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (f"queue:{dept}:{today}",))
                cur.execute(
                    "SELECT COUNT(*) FROM public.royan_encounters WHERE department = %s AND created_at::date = %s AND external_source IS NULL",
                    (dept, today),
                )
                seq = int(cur.fetchone()[0] or 0)
                queue_number = f"{prefix}-{seq:03d}"
                cur.execute("UPDATE public.royan_encounters SET queue_number = %s WHERE id = %s", (queue_number, enc_id))
                conn.commit()
                encounter["queue_number"] = queue_number
            finally:
                db.pool.putconn(conn)
        except Exception as exc:
            logger.warning("Queue number generation failed: %s", exc)

    audit_event(
        "encounter_opened",
        {"patient_id": patient_id, "queue_number": queue_number},
        actor_id=actor_sub,
        subject_type="encounter",
        subject_id=str(enc_id or ""),
    )
    invalidate_cache_tags("hospital", "patient_flow", "queue", "encounters", "executive")

    pt = patient.data[0]
    realtime_hub.publish("encounter_updates", {
        "event": "encounter_opened",
        "encounter_id": enc_id,
        "queue_number": queue_number,
        "department": dept,
        "patient_name": f"{pt.get('first_name', '')} {pt.get('last_name', '')}".strip(),
    })

    return encounter, False


@router.post("/encounters", status_code=201)
def open_encounter(payload: EncounterCreate, user=Depends(verify_jwt)):
    if payload.encounter_type not in ENCOUNTER_TYPES:
        raise HTTPException(status_code=422, detail=f"encounter_type must be one of {sorted(ENCOUNTER_TYPES)}")
    if payload.department and payload.department not in HOSPITAL_DEPARTMENTS:
        raise HTTPException(status_code=422, detail=f"Unknown department '{payload.department}'")

    patient_id = _resolve_patient_id(payload.patient_id)
    encounter, already_active = open_encounter_for_patient(
        patient_id,
        encounter_type=payload.encounter_type,
        department=payload.department,
        chief_complaint=payload.chief_complaint,
        registered_by=payload.registered_by,
        payer_type=payload.payer_type,
        membership_id=payload.membership_id,
        actor_sub=user.get("sub"),
        priority=payload.priority,
        doctor_id=payload.doctor_id,
        consulting_room=payload.consulting_room,
    )
    bill = None
    if payload.bill_now and not already_active and encounter.get("id"):
        try:
            from src.services import stage_billing
            bill = stage_billing.bill_front_desk(int(encounter["id"]), user, specialty=payload.consultation_specialty,
                                                 kind=payload.visit_kind)
        except Exception as exc:   # the patient is still on the queue; the cashier can bill from the encounter
            logger.exception("Front-desk bill failed for encounter %s: %s", encounter.get("id"), exc)
            bill = {"error": "The bill could not be created - the cashier can raise it from the encounter."}
    return {"ok": True, "encounter": encounter, **({"already_active": True} if already_active else {}),
            **({"bill": bill} if bill else {})}


@router.get("/doctors-today")
async def doctors_today(user=Depends(verify_jwt)):
    """Doctors on seat today for the check-in picker: in a consulting room, on the work clock, or on
    today's roster - and not on leave. Each with their room and how many patients are waiting for them."""
    from src.fin.db import q, tx
    from fastapi.concurrency import run_in_threadpool

    def build():
        with tx() as conn:
            return q(conn, """
                WITH d AS (
                  SELECT s.id::text AS id, s.full_name, s.department, s.specialty, s.user_id
                  FROM royan_staff s
                  WHERE s.role='doctor' AND s.quarantined_at IS NULL AND COALESCE(s.is_active, true)),
                room AS (SELECT doctor_id::text AS id, room FROM royan_room_assignments WHERE assigned_on=CURRENT_DATE),
                clock AS (SELECT DISTINCT user_id FROM staff_time_sessions WHERE ended_at IS NULL),
                -- signed in to Roy and active in the last few minutes counts as in today
                online AS (SELECT DISTINCT user_id::text AS uid FROM royan_presence_sessions
                           WHERE last_seen_at > now() - make_interval(secs => %s)),
                roster AS (SELECT DISTINCT staff_id::text AS id, MIN(start_time::text) AS starts, MAX(end_time::text) AS ends
                           FROM royan_staff_shifts WHERE shift_date=CURRENT_DATE AND COALESCE(status,'scheduled') <> 'cancelled'
                           GROUP BY 1),
                leave AS (SELECT DISTINCT staff_id::text AS id FROM royan_leave_requests
                          WHERE status='approved' AND CURRENT_DATE BETWEEN start_date AND end_date),
                load AS (SELECT doctor_id::text AS id, COUNT(*) AS waiting FROM royan_encounters
                         WHERE external_source IS NULL AND created_at::date=CURRENT_DATE
                           AND status NOT IN ('discharged','closed','consulting','in_consultation') GROUP BY 1)
                SELECT d.id, d.full_name, d.department, d.specialty, room.room, (c.user_id IS NOT NULL) AS on_clock,
                       (o.uid IS NOT NULL) AS online,
                       (r.id IS NOT NULL) AS rostered, r.starts, r.ends, (l.id IS NOT NULL) AS on_leave,
                       COALESCE(load.waiting, 0) AS waiting
                FROM d LEFT JOIN room ON room.id=d.id LEFT JOIN clock c ON c.user_id=d.user_id
                LEFT JOIN online o ON o.uid=d.user_id::text
                LEFT JOIN roster r ON r.id=d.id LEFT JOIN leave l ON l.id=d.id LEFT JOIN load ON load.id=d.id
                ORDER BY (room.room IS NULL), (c.user_id IS NULL AND o.uid IS NULL), (r.id IS NULL), d.full_name""",
                     (PRESENCE_STALE_SECONDS,))

    rows = await run_in_threadpool(build)
    for r in rows:
        r["on_seat"] = bool((r["room"] or r["on_clock"] or r["online"] or r["rostered"]) and not r["on_leave"])
    return {"doctors": rows, "on_seat": sum(1 for r in rows if r["on_seat"]), "total": len(rows)}


@router.get("/patients/{patient_id}/active-encounter")
def get_active_encounter(patient_id: str, user=Depends(verify_jwt)):
    """Lets front-desk/queue UIs check *before* submitting whether a patient
    already has an active encounter, so the 'can't double-book' rule can be
    surfaced as a clear, proactive lock rather than a silent no-op discovered
    only after the fact. Accepts either a numeric patient id or an MRN, same
    as open_encounter above, since the Queue page's dialog collects a raw MRN."""
    resolved_id = _resolve_patient_id(patient_id)
    return {"active_encounter": _find_active_encounter(resolved_id)}


@router.get("/encounters")
def list_encounters(
    status: Optional[str] = Query(None),
    department: Optional[str] = Query(None),
    doctor: Optional[str] = Query(None),
    patient_id: Optional[int] = Query(None),
    active_only: bool = Query(
        False,
        description="If true and no status filter is given, return all non-discharged encounters",
    ),
    limit: int = Query(50, ge=1, le=200),
    user=Depends(verify_jwt),
):
    # Live queue = native encounters only (external_source IS NULL). Any
    # imported/synthetic row — Hope historical data or a synbot_repair
    # ancillary bucket (see repair_shared_encounter_keys.py) — must never
    # count as an active queue entry. This filter has to run in SQL BEFORE
    # the limit: filtering client-side after LIMIT (the previous approach,
    # and it only excluded 'hope') let a batch of same-timestamp synthetic
    # rows silently crowd out real entries whenever they sorted first.
    query = (
        db.table(TABLE_ENCOUNTERS)
        .select("*")
        .is_("external_source", None)
        .order("created_at", desc=True)
        .limit(limit)
    )
    if status:
        if status not in ENCOUNTER_STATUS_ALLOWED:
            raise HTTPException(status_code=422, detail=f"Unknown status '{status}'")
        query = query.eq("status", status)
    elif active_only:
        # "discharged" is the only terminal status (ENCOUNTER_STATUS_ALLOWED,
        # constants.py) — every other status is a patient still under active
        # care. Computed here so every consumer (Nursing Station's worklist,
        # NurseDashboard's Active Inpatients card) shares one definition of
        # "active" instead of re-deriving it client-side.
        query = query.neq("status", "discharged")
    if department:
        query = query.eq("department", department)
    if doctor:
        # `doctor` is the assigned doctor's royan_staff.id (uuid FK) — the
        # legacy free-text `consulting_doctor` column is display-only and
        # never a reliable match target (nurses type arbitrary names into it).
        query = query.eq("doctor_id", doctor)
    if patient_id:
        query = query.eq("patient_id", patient_id)
    result = query.execute()
    encounters = _enrich_encounters(result.data or [])
    owed = _outstanding_by_encounter([e["id"] for e in encounters if e.get("id")])
    for e in encounters:
        e["amount_owed"] = round(owed.get(int(e["id"]), 0.0), 2) if e.get("id") else 0.0
        # Royan's flow (confirmed 14 Oct 2026): vitals -> doctor -> cashier -> services. A patient is not held for
        # payment before vitals or the consultation; they pay at the cashier after seeing the doctor, and lab / scan /
        # pharmacy wait for that payment (stage_billing.require_clearance on each order).
        e["pay_first"] = None
    return {"encounters": encounters, "count": len(encounters)}


@router.get("/encounters/{encounter_id}")
def get_encounter(encounter_id: int, user=Depends(verify_jwt)):
    """Full encounter detail — everything that happened during this visit, in
    one round trip, so the frontend can render it as a single chronological
    story instead of a flat status/date summary. Each clinical domain
    (labs, radiology, prescriptions, billing) is returned as orders/records
    plus their outcomes (results, dispensing, payments) so the timeline can
    show both "ordered" and "resulted" as distinct moments."""
    encounter = _get_encounter(encounter_id)

    vitals = db.table(TABLE_VITALS).select("*").eq("encounter_id", encounter_id).order("recorded_at", desc=True).execute().data or []
    notes = db.table(TABLE_ENCOUNTER_NOTES).select("*").eq("encounter_id", encounter_id).order("created_at", desc=True).execute().data or []

    labs = db.table(TABLE_LAB_ORDERS).select("*").eq("encounter_id", encounter_id).order("ordered_at", desc=True).execute().data or []
    lab_order_ids = [row["id"] for row in labs if row.get("id") is not None]
    lab_results = (
        db.table(TABLE_LAB_RESULTS).select("*").in_("lab_order_id", lab_order_ids).execute().data or []
        if lab_order_ids else []
    )

    radiology_orders = db.table(TABLE_RADIOLOGY_ORDERS).select("*").eq("encounter_id", encounter_id).order("ordered_at", desc=True).execute().data or []

    prescriptions = db.table(TABLE_PRESCRIPTIONS).select("*").eq("encounter_id", encounter_id).order("prescribed_at", desc=True).execute().data or []
    rx_ids = [row["id"] for row in prescriptions if row.get("id") is not None]
    dispensing = (
        db.table(TABLE_DISPENSING).select("*").in_("prescription_id", rx_ids).execute().data or []
        if rx_ids else []
    )

    bills = db.table(TABLE_BILLING).select("*").eq("encounter_id", encounter_id).order("billed_at", desc=True).execute().data or []
    bill_ids = [row["id"] for row in bills if row.get("id") is not None]
    payments = (
        db.table(TABLE_PAYMENTS).select("*").in_("billing_id", bill_ids).order("received_at", desc=True).execute().data or []
        if bill_ids else []
    )

    return {
        "encounter": _enrich_encounters([encounter])[0],
        "vitals": vitals,
        "notes": notes,
        "lab_orders": labs,
        "lab_results": lab_results,
        "radiology_orders": radiology_orders,
        "prescriptions": prescriptions,
        "dispensing": dispensing,
        "bills": bills,
        "payments": payments,
    }


@router.post("/encounters/{encounter_id}/triage")
def triage_encounter(encounter_id: int, payload: TriageRequest, user=Depends(verify_jwt)):
    encounter = _get_encounter(encounter_id)
    _assert_transition(encounter["status"], "triaged")

    triage_level = payload.triage_level or payload.triage_priority
    if triage_level == "standard":
        triage_level = "non_urgent"
    if triage_level not in TRIAGE_LEVELS:
        raise HTTPException(status_code=422, detail=f"triage_level must be one of {sorted(TRIAGE_LEVELS)}")

    updates = {
        "status": "triaged",
        "triage_level": triage_level,
        "triage_notes": payload.triage_notes,
        "chief_complaint": payload.chief_complaint or encounter.get("chief_complaint"),
        "triage_by": payload.triage_by or user.get("sub"),
        "triage_at": datetime.now(timezone.utc).isoformat(),
    }
    db.table(TABLE_ENCOUNTERS).update(updates).eq("id", encounter_id).execute()
    audit_event("encounter_triaged", {"level": triage_level}, actor_id=user.get("sub"), subject_type="encounter", subject_id=str(encounter_id))
    return {"ok": True, "encounter_id": encounter_id, "status": "triaged"}


@router.post("/encounters/{encounter_id}/nurse-done")
async def nurse_assessment_done(encounter_id: int, user=Depends(verify_jwt)):
    """Nurse marks vitals recorded — patient ready for doctor."""
    encounter = _get_encounter(encounter_id)
    _assert_transition(encounter["status"], "nurse_assessment")
    # no payment hold before the doctor: the patient pays at the cashier after the consultation (14 Oct 2026)
    now = datetime.now(timezone.utc).isoformat()
    db.table(TABLE_ENCOUNTERS).update({"status": "nurse_assessment", "nurse_done_at": now}).eq("id", encounter_id).execute()
    invalidate_cache_tags("hospital", "queue", "patient_flow", "encounters")
    audit_event("nurse_assessment_done", {}, actor_id=user.get("sub"), subject_type="encounter", subject_id=str(encounter_id))
    realtime_hub.publish("encounter_updates", {
        "event": "nurse_done",
        "encounter_id": encounter_id,
        "queue_number": encounter.get("queue_number"),
        "department": encounter.get("department"),
    })
    return {"ok": True, "encounter_id": encounter_id, "status": "nurse_assessment"}


@router.patch("/encounters/{encounter_id}/assign-nurse")
async def assign_nurse(encounter_id: int, payload: AssignNurseRequest, user=Depends(verify_jwt)):
    """Assign (or clear) the nurse responsible for this patient's care —
    Hope's Outpatient Dashboard has this as a per-row dropdown; this app had
    no such concept at all until now."""
    _get_encounter(encounter_id)
    nurse_name = None
    if payload.nurse_id:
        nurse = db.table(TABLE_STAFF).select("id,full_name").eq("id", payload.nurse_id).limit(1).execute()
        if not nurse.data:
            raise HTTPException(status_code=404, detail=f"Staff {payload.nurse_id} not found")
        nurse_name = nurse.data[0].get("full_name")

    db.table(TABLE_ENCOUNTERS).update({"assigned_nurse_id": payload.nurse_id}).eq("id", encounter_id).execute()
    invalidate_cache_tags("hospital", "queue", "patient_flow", "encounters")
    audit_event(
        "nurse_assigned" if payload.nurse_id else "nurse_unassigned",
        {"nurse_id": payload.nurse_id},
        actor_id=user.get("sub"),
        subject_type="encounter",
        subject_id=str(encounter_id),
    )
    realtime_hub.publish("encounter_updates", {
        "event": "nurse_assigned", "encounter_id": encounter_id, "nurse_id": payload.nurse_id,
    })
    return {"ok": True, "encounter_id": encounter_id, "assigned_nurse_id": payload.nurse_id, "assigned_nurse_name": nurse_name}


@router.post("/encounters/{encounter_id}/call")
async def call_patient(encounter_id: int, payload: CallPatientRequest, user=Depends(verify_jwt)):
    """Doctor calls patient into the consulting room — appears on display board."""
    encounter = _get_encounter(encounter_id)
    _assert_transition(encounter["status"], "called")
    now = datetime.now(timezone.utc).isoformat()
    updates = {"status": "called", "called_at": now}
    if payload.room:
        updates["consulting_room"] = payload.room
    db.table(TABLE_ENCOUNTERS).update(updates).eq("id", encounter_id).execute()
    invalidate_cache_tags("hospital", "queue", "patient_flow", "encounters")
    audit_event("patient_called", {"room": payload.room}, actor_id=user.get("sub"), subject_type="encounter", subject_id=str(encounter_id))
    realtime_hub.publish("encounter_updates", {
        "event": "patient_called",
        "encounter_id": encounter_id,
        "queue_number": encounter.get("queue_number"),
        "department": encounter.get("department"),
        "room": payload.room,
    })
    return {"ok": True, "encounter_id": encounter_id, "status": "called", "room": payload.room}


@router.post("/encounters/{encounter_id}/consult")
async def record_consultation(encounter_id: int, payload: ConsultRequest, user=Depends(verify_jwt)):
    encounter = _get_encounter(encounter_id)
    # ENCOUNTER_STATUS_TRANSITIONS allows a "consulting" self-loop specifically so
    # this can be re-called on an already-consulting encounter to (re)assign the
    # doctor without requiring a status change.
    _assert_transition(encounter["status"], "consulting")
    # No payment hold before the consultation (14 Oct 2026): vitals -> doctor -> cashier -> services.

    # Resolve the doctor as a stable royan_staff.id FK, not a free-text name:
    # a hand-typed name (or the submitting nurse/receptionist's own JWT sub)
    # can never match the doctor_id filter the Doctor Dashboard queries by.
    # Explicit doctor_id from the request (doctor picker) wins; otherwise, if
    # the caller is themselves a doctor self-assigning from their own
    # dashboard, fall back to their own staff record.
    doctor_id = payload.doctor_id
    if not doctor_id and "doctor" in (user.get("roles") or []):
        caller_staff = (
            db.table(TABLE_STAFF).select("id").eq("user_id", user.get("sub")).limit(1).execute()
        )
        if caller_staff.data:
            doctor_id = caller_staff.data[0]["id"]

    doctor_name = payload.consulting_doctor
    if doctor_id and not doctor_name:
        staff = db.table(TABLE_STAFF).select("full_name,email").eq("id", doctor_id).limit(1).execute()
        if staff.data:
            doctor_name = staff.data[0].get("full_name") or staff.data[0].get("email")
    doctor_name = doctor_name or "doctor"

    updates = {
        "status": "consulting",
        "doctor_id": doctor_id,
        "consulting_doctor": doctor_name,
        "diagnosis_codes": payload.diagnosis_codes or [],
        "diagnosis_notes": payload.diagnosis_notes,
        "consultation_at": datetime.now(timezone.utc).isoformat(),
    }
    db.table(TABLE_ENCOUNTERS).update(updates).eq("id", encounter_id).execute()
    invalidate_cache_tags("hospital", "queue", "patient_flow", "encounters")
    audit_event("encounter_consulting", {"doctor": doctor_name, "doctor_id": doctor_id}, actor_id=user.get("sub"), subject_type="encounter", subject_id=str(encounter_id))
    realtime_hub.publish("encounter_updates", {
        "event": "consultation_started",
        "encounter_id": encounter_id,
        "queue_number": encounter.get("queue_number"),
        "department": encounter.get("department"),
        "doctor": doctor_name,
        "doctor_id": doctor_id,
    })
    return {"ok": True, "encounter_id": encounter_id, "status": "consulting", "doctor_id": doctor_id}


@router.post("/encounters/{encounter_id}/pause")
async def pause_consultation(encounter_id: int, payload: PauseConsultationRequest, user=Depends(verify_jwt)):
    """Mark a consultation paused without changing its queue status — a
    display/ops-awareness flag, not a workflow state (the department blueprint
    names Pause/Resume as a quick action with no backing status of its own)."""
    encounter = _get_encounter(encounter_id)
    if encounter["status"] != "consulting":
        raise HTTPException(status_code=409, detail="Can only pause an encounter that is currently consulting")
    db.table(TABLE_ENCOUNTERS).update({
        "paused_at": datetime.now(timezone.utc).isoformat(),
        "paused_reason": payload.reason,
    }).eq("id", encounter_id).execute()
    invalidate_cache_tags("hospital", "queue", "patient_flow", "encounters")
    audit_event("consultation_paused", {"reason": payload.reason}, actor_id=user.get("sub"), subject_type="encounter", subject_id=str(encounter_id))
    realtime_hub.publish("encounter_updates", {
        "event": "consultation_paused", "encounter_id": encounter_id, "queue_number": encounter.get("queue_number"),
    })
    return {"ok": True, "encounter_id": encounter_id, "paused": True}


@router.post("/encounters/{encounter_id}/resume")
async def resume_consultation(encounter_id: int, user=Depends(verify_jwt)):
    encounter = _get_encounter(encounter_id)
    db.table(TABLE_ENCOUNTERS).update({"paused_at": None, "paused_reason": None}).eq("id", encounter_id).execute()
    invalidate_cache_tags("hospital", "queue", "patient_flow", "encounters")
    audit_event("consultation_resumed", {}, actor_id=user.get("sub"), subject_type="encounter", subject_id=str(encounter_id))
    realtime_hub.publish("encounter_updates", {
        "event": "consultation_resumed", "encounter_id": encounter_id, "queue_number": encounter.get("queue_number"),
    })
    return {"ok": True, "encounter_id": encounter_id, "paused": False}


@router.post("/encounters/{encounter_id}/end-consultation")
async def end_consultation(encounter_id: int, payload: EndConsultationRequest, user=Depends(verify_jwt)):
    """One-click 'End Consultation': evaluates what was ordered during the
    visit and auto-routes the encounter to the correct next queue, matching
    the department standard's requirement that ending a consultation triggers
    workflow evaluation rather than requiring the clinician to pick a status."""
    encounter = _get_encounter(encounter_id)
    if encounter["status"] not in ("consulting", "lab_ordered", "pharmacy_dispensing", "awaiting_results"):
        raise HTTPException(status_code=409, detail=f"Cannot end consultation from status '{encounter['status']}'")

    has_note = db.table(TABLE_ENCOUNTER_NOTES).select("id").eq("encounter_id", encounter_id).limit(1).execute().data
    if not has_note:
        raise HTTPException(status_code=422, detail="At least one clinical note is required before ending the consultation.")

    pending_labs = (
        db.table(TABLE_LAB_ORDERS).select("id").eq("encounter_id", encounter_id)
        .not_in("status", ["resulted", "cancelled"]).execute().data or []
    )
    pending_rx = (
        db.table(TABLE_PRESCRIPTIONS).select("id").eq("encounter_id", encounter_id)
        .in_("status", ["pending", "partially_dispensed"]).execute().data or []
    )

    if payload.force_status:
        target, reason = payload.force_status, "clinician override"
    elif pending_labs:
        target, reason = "lab_ordered", (f"{len(pending_labs)} lab order(s) awaiting result - "
                                         + ("the doctor sees the patient again when they are back" if payload.review_results
                                            else "the visit moves on when they are back"))
    elif pending_rx:
        target, reason = "pharmacy_dispensing", f"{len(pending_rx)} prescription(s) pending dispensing"
    else:
        target, reason = "billing_pending", "no pending labs or prescriptions"

    if target == encounter["status"]:
        # Already exactly where the evidence says it should be (e.g. doctor
        # re-clicks End Consultation on an encounter still awaiting a lab
        # result) — no transition needed; most statuses have no self-loop in
        # ENCOUNTER_STATUS_TRANSITIONS so _assert_transition would otherwise
        # reject this as an illegal no-op transition.
        return {
            "ok": True, "encounter_id": encounter_id, "status": target, "routed_to": target,
            "routing_reason": f"already {target.replace('_', ' ')} — {reason}",
            "evidence": {"pending_labs": len(pending_labs), "pending_prescriptions": len(pending_rx)},
        }

    _assert_transition(encounter["status"], target)
    db.table(TABLE_ENCOUNTERS).update({
        "status": target,
        "paused_at": None,
        "paused_reason": None,
        "review_after_results": bool(payload.review_results),
    }).eq("id", encounter_id).execute()
    invalidate_cache_tags("hospital", "queue", "patient_flow", "encounters")
    invalidate_patient_context(encounter["patient_id"])
    audit_event("consultation_ended", {"routed_to": target, "reason": reason}, actor_id=user.get("sub"), subject_type="encounter", subject_id=str(encounter_id))
    realtime_hub.publish("encounter_updates", {
        "event": "consultation_ended", "encounter_id": encounter_id,
        "queue_number": encounter.get("queue_number"), "status": target,
    })
    return {
        "ok": True, "encounter_id": encounter_id, "status": target, "routed_to": target,
        "routing_reason": reason,
        "evidence": {"pending_labs": len(pending_labs), "pending_prescriptions": len(pending_rx)},
        "billing": await _send_to_cashier(encounter_id, user),
    }


async def _send_to_cashier(encounter_id: int, user: dict) -> dict:
    """Bill what the doctor ordered (lab, drugs; scans on a Scancare bill) so the patient pays before the services."""
    from fastapi.concurrency import run_in_threadpool
    from src.services import stage_billing
    try:
        return await run_in_threadpool(stage_billing.bill_orders, encounter_id, user)
    except Exception as exc:
        logger.exception("Send-to-cashier billing failed for encounter %s: %s", encounter_id, exc)
        return {"bills": [], "error": "The orders could not be billed - the cashier can bill them from the encounter."}


@router.post("/encounters/{encounter_id}/send-to-cashier")
async def send_to_cashier(encounter_id: int, user=Depends(verify_jwt)):
    """Doctor (or cashier): bill everything ordered so far that is not on a bill yet."""
    _get_encounter(encounter_id)
    return {"ok": True, **(await _send_to_cashier(encounter_id, user))}


@router.post("/encounters/{encounter_id}/advance")
async def advance_encounter(encounter_id: int, payload: AdvanceRequest, user=Depends(verify_jwt)):
    encounter = _get_encounter(encounter_id)
    _assert_transition(encounter["status"], payload.new_status)
    if payload.new_status == "discharged":
        raise HTTPException(status_code=400, detail="Use POST /encounters/{id}/discharge to discharge a patient")
    db.table(TABLE_ENCOUNTERS).update({"status": payload.new_status}).eq("id", encounter_id).execute()
    invalidate_cache_tags("hospital", "queue", "patient_flow", "encounters")
    audit_event("encounter_advanced", {"to": payload.new_status, "notes": payload.notes}, actor_id=user.get("sub"), subject_type="encounter", subject_id=str(encounter_id))
    realtime_hub.publish("encounter_updates", {
        "event": "encounter_advanced",
        "encounter_id": encounter_id,
        "queue_number": encounter.get("queue_number"),
        "department": encounter.get("department"),
        "status": payload.new_status,
    })
    return {"ok": True, "encounter_id": encounter_id, "status": payload.new_status}


@router.post("/encounters/{encounter_id}/discharge")
async def discharge_encounter(encounter_id: int, payload: DischargeRequest, user=Depends(verify_jwt)):
    encounter = _get_encounter(encounter_id)
    _assert_transition(encounter["status"], "discharged")

    has_note = db.table(TABLE_ENCOUNTER_NOTES).select("id").eq("encounter_id", encounter_id).limit(1).execute().data
    if not has_note:
        raise HTTPException(status_code=422, detail="At least one clinical note is required before discharge.")
    owed = _outstanding_by_encounter([encounter_id]).get(encounter_id, 0.0)
    if owed > 0.009:
        raise HTTPException(status_code=409, detail=f"₦{owed:,.2f} is still unpaid on this visit - the patient pays at the cashier before discharge.")

    now = datetime.now(timezone.utc).isoformat()
    updates = {
        "status": "discharged",
        "discharge_summary": payload.discharge_summary,
        "discharge_by": user.get("sub") or "system",
        "discharge_at": now,
    }
    db.table(TABLE_ENCOUNTERS).update(updates).eq("id", encounter_id).execute()
    audit_event("encounter_discharged", {"summary_len": len(payload.discharge_summary)}, actor_id=user.get("sub"), subject_type="encounter", subject_id=str(encounter_id))
    realtime_hub.publish("encounter_updates", {
        "event": "encounter_discharged",
        "encounter_id": encounter_id,
        "queue_number": encounter.get("queue_number"),
        "department": encounter.get("department"),
    })

    # If this encounter was opened from an appointment arrival (see
    # appointments.py's mark_arrived), that appointment is still sitting in
    # "arrived" — nothing ever moved it forward, so it lingered on the
    # calendar/appointments list indefinitely even after the visit was
    # actually done. Close the loop: a completed visit completes the booking
    # that brought the patient in.
    try:
        linked = (
            db.table(TABLE_APPOINTMENTS)
            .select("id,status")
            .eq("encounter_id", encounter_id)
            .in_("status", ["arrived", "booked", "confirmed"])
            .execute()
        ).data or []
        for appt in linked:
            db.table(TABLE_APPOINTMENTS).update({"status": "completed"}).eq("id", appt["id"]).execute()
            audit_event("appointment_completed", {"reason": "encounter_discharged"}, actor_id=user.get("sub"), subject_type="appointment", subject_id=str(appt["id"]))
            realtime_hub.publish("appointment_updates", {
                "event": "appointment_completed",
                "appointment_id": appt["id"],
            })
    except Exception as exc:
        logger.warning("Auto-completing linked appointment failed for encounter %s: %s", encounter_id, exc)

    return {"ok": True, "encounter_id": encounter_id, "status": "discharged", "discharged_at": now}


# ─── Encounter Notes ──────────────────────────────────────────────────────────

@router.post("/encounters/{encounter_id}/notes", status_code=201)
def add_encounter_note(encounter_id: int, payload: EncounterNoteCreate, user=Depends(verify_jwt)):
    """Add a clinical note to an encounter, either free-text (note_type) or
    picked from the Notes Master catalog (note_title_id — resolves note_type
    from the title's category and denormalizes the title text onto the row)."""
    encounter = _get_encounter(encounter_id)

    note_type = payload.note_type
    note_title = payload.note_title
    if payload.note_title_id is not None:
        title_row = db.table(TABLE_NOTE_TITLES).select("title,category").eq("id", payload.note_title_id).execute()
        if title_row.data:
            note_type = title_row.data[0]["category"]
            note_title = note_title or title_row.data[0]["title"]

    content = payload.content
    if not content:
        content = " | ".join(filter(None, [
            f"S: {payload.subjective}" if payload.subjective else "",
            f"O: {payload.objective}" if payload.objective else "",
            f"A: {payload.assessment}" if payload.assessment else "",
            f"P: {payload.plan}" if payload.plan else "",
        ]))
    if not content:
        raise HTTPException(status_code=422, detail="Note must have content or at least one SOAP field")

    signed_by = payload.signed_by or _resolve_staff_id_for_user(user)

    data = {
        "encounter_id": encounter_id,
        "patient_id": encounter["patient_id"],
        "note_type": note_type,
        "note_title_id": payload.note_title_id,
        "note_title": note_title,
        "content": content,
        "subjective": payload.subjective,
        "objective": payload.objective,
        "assessment": payload.assessment,
        "plan": payload.plan,
        "icd10_codes": payload.icd10_codes,
        "vitals_id": payload.vitals_id,
        "author_id": user.get("sub"),
        "author_name": _resolve_author_name(user),
    }
    if signed_by:
        data["signed_by"] = signed_by
        data["signed_at"] = datetime.now(timezone.utc).isoformat()
    try:
        result = db.table(TABLE_ENCOUNTER_NOTES).insert(data).execute()
    except Exception as exc:
        logger.error("Encounter note insert failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to save encounter note")
    note = (result.data or [data])[0]
    invalidate_patient_context(encounter["patient_id"])
    audit_event(
        "encounter_note_added",
        {"note_type": note_type, "note_title": note_title},
        actor_id=user.get("sub"),
        subject_type="encounter",
        subject_id=str(encounter_id),
    )
    return {"ok": True, "note": note}


@router.get("/encounters/{encounter_id}/notes")
def list_encounter_notes(encounter_id: int, user=Depends(verify_jwt)):
    """List all clinical notes for an encounter, ordered chronologically.

    Each note carries its addenda inline so the reader always sees a
    correction alongside the text it corrects — never the original alone.
    """
    _get_encounter(encounter_id)
    result = (
        db.table(TABLE_ENCOUNTER_NOTES)
        .select("*")
        .eq("encounter_id", encounter_id)
        .order("created_at", desc=False)
        .execute()
    )
    notes = result.data or []

    if notes:
        try:
            addenda = (
                db.table(TABLE_NOTE_ADDENDA)
                .select("id,note_id,content,reason,author_name,created_at")
                .in_("note_id", [n["id"] for n in notes])
                .order("created_at")
                .execute()
                .data
                or []
            )
            by_note: dict[int, list] = {}
            for a in addenda:
                by_note.setdefault(a["note_id"], []).append(a)
            for n in notes:
                n["addenda"] = by_note.get(n["id"], [])
        except Exception as exc:
            # An addendum-table failure must never hide the notes themselves.
            logger.error("Addendum fetch failed for encounter %s: %s", encounter_id, exc)
            for n in notes:
                n.setdefault("addenda", [])

    return {"notes": notes, "count": len(notes)}


class NoteAddendumCreate(BaseModel):
    content: str = Field(..., min_length=1)
    reason: Optional[str] = None

    model_config = {"extra": "ignore"}


@router.post("/encounters/{encounter_id}/notes/{note_id}/addendum", status_code=201)
def add_note_addendum(
    encounter_id: int,
    note_id: int,
    payload: NoteAddendumCreate,
    user=Depends(verify_jwt),
):
    """Append a correction to an existing clinical note.

    This is the ONLY sanctioned way to change what a note says. The original
    row is never rewritten — there is deliberately no PATCH/PUT/DELETE for
    royan_encounter_notes anywhere in this codebase, because a signed clinical
    note is a medico-legal document that may be produced in court years later.
    A correction is therefore additive, separately timestamped, and attributed
    to whoever made it (often not the original author).
    """
    _get_encounter(encounter_id)

    note = (
        db.table(TABLE_ENCOUNTER_NOTES)
        .select("id,encounter_id")
        .eq("id", note_id)
        .execute()
        .data
    )
    if not note:
        raise HTTPException(status_code=404, detail=f"Note {note_id} not found")
    if note[0]["encounter_id"] != encounter_id:
        raise HTTPException(status_code=400, detail="Note does not belong to this encounter")

    row = {
        "note_id": note_id,
        "content": payload.content,
        "reason": payload.reason,
        "author_id": user.get("sub"),
        "author_name": _resolve_author_name(user),
    }
    signed_by = _resolve_staff_id_for_user(user)
    if signed_by:
        row["signed_by"] = signed_by

    try:
        created = db.table(TABLE_NOTE_ADDENDA).insert(row).execute()
    except Exception as exc:
        logger.error("Addendum insert failed for note %s: %s", note_id, exc)
        raise HTTPException(status_code=500, detail="Failed to record addendum")

    audit_event(
        "clinical_note_amended",
        {"note_id": note_id, "encounter_id": encounter_id, "reason": payload.reason},
        actor_id=user.get("sub"),
        subject_type="encounter",
        subject_id=str(encounter_id),
    )
    return {"ok": True, "addendum": (created.data or [row])[0]}


# ── Consulting-room assignment ───────────────────────────────────────────────
#
# "once the doctor registers and signs up, they are assigned a room by the front
# desk... the front desk wants that ability to designate what consulting rooms
# belong to a particular doctor on the ground."
#
# Per day, not per doctor: room allocation follows the shift rota, and
# yesterday's allocation should not silently apply this morning.

class RoomAssignmentCreate(BaseModel):
    doctor_id: str
    room: str = Field(..., min_length=1, max_length=100)
    assigned_on: Optional[str] = None
    notes: Optional[str] = None


@router.get("/room-assignments")
def list_room_assignments(
    assigned_on: Optional[str] = Query(None, description="ISO date; defaults to today"),
    user=Depends(verify_jwt),
):
    """Who is in which consulting room, for a given day."""
    day = assigned_on or datetime.now().date().isoformat()
    try:
        rows = (
            db.table(TABLE_ROOM_ASSIGNMENTS)
            .select("id,doctor_id,room,assigned_on,notes,created_at")
            .eq("assigned_on", day)
            .order("room")
            .execute().data or []
        )
    except Exception:
        return {"assignments": [], "count": 0, "assigned_on": day}

    doctor_ids = [r["doctor_id"] for r in rows if r.get("doctor_id")]
    names: dict = {}
    if doctor_ids:
        try:
            staff = db.table(TABLE_STAFF).select("id,full_name,department").in_("id", doctor_ids).execute()
            names = {x["id"]: x for x in staff.data or []}
        except Exception:
            names = {}
    for r in rows:
        info = names.get(r.get("doctor_id")) or {}
        r["doctor_name"] = info.get("full_name")
        r["department"] = info.get("department")
    return {"assignments": rows, "count": len(rows), "assigned_on": day}


@router.post("/room-assignments", status_code=201)
def assign_room(payload: RoomAssignmentCreate, user=Depends(verify_jwt)):
    """Assign a doctor to a consulting room for a day.

    Re-assigning the same doctor replaces their room rather than adding a
    second one, so a correction is one action instead of delete-then-create.
    A room already taken by someone else that day is rejected outright: two
    doctors in one room sends two patients to the same door.
    """
    day = payload.assigned_on or datetime.now().date().isoformat()
    room = payload.room.strip()

    try:
        clash = (
            db.table(TABLE_ROOM_ASSIGNMENTS)
            .select("id,doctor_id")
            .eq("assigned_on", day)
            .eq("room", room)
            .execute().data or []
        )
    except Exception:
        clash = []
    for c in clash:
        if str(c.get("doctor_id")) != str(payload.doctor_id):
            raise HTTPException(
                status_code=409,
                detail=f"{room} is already assigned to another doctor on {day}.",
            )

    # assigned_by references royan_staff: the assigner's staff record, or none (an admin login without one -
    # passing the login id here broke every assignment made from such an account)
    assigner = None
    try:
        me = db.table(TABLE_STAFF).select("id").eq("user_id", user.get("sub")).limit(1).execute().data
        assigner = me[0]["id"] if me else None
    except Exception:
        assigner = None
    row = {
        "doctor_id": payload.doctor_id,
        "room": room,
        "assigned_on": day,
        "notes": payload.notes or (None if assigner else f"assigned by {user.get('email') or user.get('sub')}"),
        "assigned_by": assigner,
    }
    try:
        existing = (
            db.table(TABLE_ROOM_ASSIGNMENTS)
            .select("id").eq("assigned_on", day).eq("doctor_id", payload.doctor_id)
            .limit(1).execute().data
        )
        if existing:
            db.table(TABLE_ROOM_ASSIGNMENTS).update(
                {"room": room, "notes": payload.notes, "updated_at": datetime.now(timezone.utc).isoformat()}
            ).eq("id", existing[0]["id"]).execute()
            result = {**row, "id": existing[0]["id"]}
        else:
            created = db.table(TABLE_ROOM_ASSIGNMENTS).insert(row).execute()
            result = (created.data or [row])[0]
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Room assignment failed: %s", exc)
        raise HTTPException(status_code=500, detail="Could not save the room assignment")

    invalidate_cache_tags("queue", "encounters")
    return {"ok": True, "assignment": result}


@router.delete("/room-assignments/{assignment_id}")
def clear_room_assignment(assignment_id: int, user=Depends(verify_jwt)):
    """Free a room — the doctor has gone off shift or moved."""
    try:
        db.table(TABLE_ROOM_ASSIGNMENTS).delete().eq("id", assignment_id).execute()
    except Exception as exc:
        logger.error("Clearing room assignment failed: %s", exc)
        raise HTTPException(status_code=500, detail="Could not clear the assignment")
    invalidate_cache_tags("queue", "encounters")
    return {"ok": True}


# -- Admission requests -------------------------------------------------------
#
# "when a doctor requests admission for a particular patient, the nurse
# dashboard needs to have a card that pops up that says one patient waiting
# admission."
#
# Kept OFF the encounter status deliberately (see migration 206). The patient
# stays on the clinical queue while the request is open, and a decline has to
# leave them exactly where they were.

class AdmissionRequestCreate(BaseModel):
    ward_preference: Optional[str] = None
    reason: Optional[str] = None
    urgency: str = "routine"


class AdmissionDecision(BaseModel):
    accept: bool
    bed_id: Optional[int] = None
    note: Optional[str] = None


@router.post("/encounters/{encounter_id}/request-admission", status_code=201)
async def request_admission(
    encounter_id: int, payload: AdmissionRequestCreate, user=Depends(verify_jwt)
):
    """Doctor asks for a bed. Raises the ticket the nursing board reads."""
    encounter = _get_encounter(encounter_id)
    if encounter["status"] == "discharged":
        raise HTTPException(status_code=409, detail="This patient has already been discharged.")
    if payload.urgency not in ("routine", "urgent", "immediate"):
        raise HTTPException(status_code=422, detail="urgency must be routine, urgent or immediate")

    existing = (
        db.table(TABLE_ADMISSION_REQUESTS).select("id")
        .eq("encounter_id", encounter_id).eq("status", "pending").limit(1).execute().data
    )
    if existing:
        # Not an error: the doctor pressed it twice, or a colleague already
        # asked. Returning the open ticket beats a 409 nobody can act on.
        return {"ok": True, "already_requested": True, "request_id": existing[0]["id"]}

    row = {
        "encounter_id": encounter_id,
        "patient_id": encounter["patient_id"],
        "requested_by": user.get("sub"),
        "ward_preference": payload.ward_preference,
        "reason": payload.reason,
        "urgency": payload.urgency,
    }
    try:
        created = db.table(TABLE_ADMISSION_REQUESTS).insert(row).execute()
    except Exception as exc:
        logger.error("Admission request failed: %s", exc)
        raise HTTPException(status_code=500, detail="Could not raise the admission request")

    audit_event(
        "admission_requested",
        {"encounter_id": encounter_id, "urgency": payload.urgency},
        actor_id=user.get("sub"), subject_type="encounter", subject_id=str(encounter_id),
    )
    invalidate_cache_tags("queue", "encounters", "hospital")
    realtime_hub.publish("encounter_updates", {
        "event": "admission_requested",
        "encounter_id": encounter_id,
        "urgency": payload.urgency,
    })
    return {"ok": True, "request": (created.data or [row])[0]}


@router.get("/admission-requests")
def list_admission_requests(status: str = Query("pending"), user=Depends(verify_jwt)):
    """The nursing admission board."""
    try:
        rows = (
            db.table(TABLE_ADMISSION_REQUESTS)
            .select("id,encounter_id,patient_id,requested_by,requested_at,ward_preference,"
                    "reason,urgency,status,decided_at,decision_note,bed_id")
            .eq("status", status)
            .order("requested_at")
            .limit(100).execute().data or []
        )
    except Exception:
        return {"requests": [], "count": 0}

    pids = list({r["patient_id"] for r in rows if r.get("patient_id")})
    pmap = {}
    if pids:
        try:
            pts = (
                db.table(TABLE_PATIENTS)
                .select("id,mrn,first_name,last_name,date_of_birth,gender")
                .in_("id", pids).execute()
            )
            pmap = {x["id"]: x for x in pts.data or []}
        except Exception:
            pmap = {}

    eids = list({r["encounter_id"] for r in rows if r.get("encounter_id")})
    emap = {}
    if eids:
        try:
            encs = (
                db.table(TABLE_ENCOUNTERS)
                .select("id,queue_number,department,chief_complaint,status")
                .in_("id", eids).execute()
            )
            emap = {x["id"]: x for x in encs.data or []}
        except Exception:
            emap = {}

    for r in rows:
        pt = pmap.get(r.get("patient_id")) or {}
        enc = emap.get(r.get("encounter_id")) or {}
        r["patient_name"] = ("%s %s" % (pt.get("first_name", ""), pt.get("last_name", ""))).strip() or None
        r["patient_mrn"] = pt.get("mrn")
        r["age_display"] = format_patient_age(pt.get("date_of_birth"))
        r["gender"] = pt.get("gender")
        r["queue_number"] = enc.get("queue_number")
        r["department"] = enc.get("department")
        r["chief_complaint"] = enc.get("chief_complaint")
        r["encounter_status"] = enc.get("status")

    return {"requests": rows, "count": len(rows)}


@router.post("/admission-requests/{request_id}/decision")
def decide_admission_request(
    request_id: int, payload: AdmissionDecision, user=Depends(verify_jwt)
):
    """Nurse admits the patient to a bed, or declines with a reason.

    Accepting also occupies the bed in the same call, so the ward board and the
    admission board cannot disagree about where the patient is.
    """
    found = db.table(TABLE_ADMISSION_REQUESTS).select("*").eq("id", request_id).limit(1).execute().data
    if not found:
        raise HTTPException(status_code=404, detail="Admission request not found")
    req = found[0]
    if req["status"] != "pending":
        raise HTTPException(status_code=409, detail="This request was already %s." % req["status"])

    decision = "admitted" if payload.accept else "declined"
    now = datetime.now(timezone.utc).isoformat()
    update = {
        "status": decision,
        "decided_by": user.get("sub"),
        "decided_at": now,
        "decision_note": payload.note,
        "updated_at": now,
    }

    if payload.accept and payload.bed_id:
        bed = db.table("royan_beds").select("id,status,current_patient_id").eq("id", payload.bed_id).limit(1).execute().data
        if not bed:
            raise HTTPException(status_code=404, detail="That bed does not exist")
        occupant = bed[0].get("current_patient_id")
        if occupant and str(occupant) != str(req["patient_id"]):
            raise HTTPException(status_code=409, detail="That bed is already occupied.")
        db.table("royan_beds").update({
            "status": "occupied",
            "current_patient_id": req["patient_id"],
            "admitted_at": now,
        }).eq("id", payload.bed_id).execute()
        update["bed_id"] = payload.bed_id

    db.table(TABLE_ADMISSION_REQUESTS).update(update).eq("id", request_id).execute()

    audit_event(
        "admission_%s" % decision,
        {"request_id": request_id, "bed_id": payload.bed_id, "note": payload.note},
        actor_id=user.get("sub"), subject_type="encounter", subject_id=str(req["encounter_id"]),
    )
    invalidate_cache_tags("queue", "encounters", "hospital", "wards")
    return {"ok": True, "status": decision}


# -- The inpatient queue ------------------------------------------------------
#
# "let's add it to the queue and flow so staff can alternate between both
# queues... OPD and IPD... and the IPD would be designed just like the OPD queue
# with all the information about the patient easily accessible through the work
# panel."
#
# AN INPATIENT IS SOMEONE IN A BED
# --------------------------------
# Not "encounter_type = inpatient". That field is set at registration and never
# corrected, so it says what someone INTENDED, not where the patient is: an
# outpatient admitted after a bad result keeps encounter_type 'outpatient', and
# an inpatient encounter that was never given a bed would appear on a ward round
# for a patient who went home. Occupancy of royan_beds is the fact on the
# ground, and it is also what drives the room charge, so the queue and the bill
# cannot disagree about who is admitted.

@router.get("/inpatients")
def list_inpatients(user=Depends(verify_jwt)):
    """Everyone currently in a bed, with where they are and what they have run up."""
    try:
        beds = (
            db.table(TABLE_BEDS)
            .select("id,ward_id,room_id,bed_number,admitted_at,current_patient_id,current_encounter_id,notes")
            # This wrapper spells IS NOT NULL as is_(col, <anything non-null>);
            # .not_.is_() is not supported and fails at runtime.
            .is_("current_patient_id", "not.null")
            .execute().data or []
        )
    except Exception as exc:
        logger.warning("Inpatient queue lookup failed: %s", exc)
        return {"inpatients": [], "count": 0}

    if not beds:
        return {"inpatients": [], "count": 0}

    ward_map, room_map, patient_map, enc_map = {}, {}, {}, {}

    ward_ids = list({b["ward_id"] for b in beds if b.get("ward_id")})
    if ward_ids:
        try:
            rows = db.table(TABLE_WARDS).select("id,name,daily_rate").in_("id", ward_ids).execute()
            ward_map = {r["id"]: r for r in rows.data or []}
        except Exception:
            pass

    room_ids = list({b["room_id"] for b in beds if b.get("room_id")})
    if room_ids:
        try:
            rows = db.table("royan_rooms").select("id,name,daily_rate").in_("id", room_ids).execute()
            room_map = {r["id"]: r for r in rows.data or []}
        except Exception:
            pass

    pids = list({b["current_patient_id"] for b in beds if b.get("current_patient_id")})
    if pids:
        try:
            rows = (
                db.table(TABLE_PATIENTS)
                .select("id,mrn,first_name,last_name,date_of_birth,gender,phone")
                .in_("id", pids).execute()
            )
            patient_map = {r["id"]: r for r in rows.data or []}
        except Exception:
            pass

    eids = list({b["current_encounter_id"] for b in beds if b.get("current_encounter_id")})
    if eids:
        try:
            rows = (
                db.table(TABLE_ENCOUNTERS)
                .select("id,status,department,chief_complaint,queue_number,created_at,"
                        "payer_type,membership_id,doctor_id,consulting_doctor")
                .in_("id", eids).execute()
            )
            enc_map = {r["id"]: r for r in rows.data or []}
        except Exception:
            pass

    # Ad-hoc charges, one query for the whole ward rather than per patient.
    charge_totals = {}
    if eids:
        try:
            rows = (
                db.table(TABLE_INPATIENT_BILL_LINES)
                .select("encounter_id,total").in_("encounter_id", eids).execute().data or []
            )
            for r in rows:
                eid = r.get("encounter_id")
                charge_totals[eid] = charge_totals.get(eid, 0.0) + float(r.get("total") or 0)
        except Exception:
            charge_totals = {}

    now = datetime.now(timezone.utc)
    out = []
    for b in beds:
        pt = patient_map.get(b.get("current_patient_id")) or {}
        enc = enc_map.get(b.get("current_encounter_id")) or {}
        ward = ward_map.get(b.get("ward_id")) or {}
        room = room_map.get(b.get("room_id")) or {}

        nights, room_total = 0, 0.0
        rate = float(room.get("daily_rate") or ward.get("daily_rate") or 0)
        if b.get("admitted_at"):
            try:
                adm = datetime.fromisoformat(str(b["admitted_at"]).replace("Z", "+00:00"))
                if adm.tzinfo is None:
                    adm = adm.replace(tzinfo=timezone.utc)
                elapsed = now - adm
                # Admission on any given day occupies that night, so night one
                # counts immediately rather than after 24 hours.
                nights = max(1, int(elapsed.total_seconds() // 86400)
                             + (1 if elapsed.total_seconds() % 86400 else 0))
                room_total = round(rate * nights, 2)
            except (ValueError, TypeError):
                pass

        adhoc = round(charge_totals.get(b.get("current_encounter_id"), 0.0), 2)

        out.append({
            "bed_id": b["id"],
            "encounter_id": b.get("current_encounter_id"),
            "patient_id": b.get("current_patient_id"),
            "patient_name": ("%s %s" % (pt.get("first_name", ""), pt.get("last_name", ""))).strip() or None,
            "mrn": pt.get("mrn"),
            "age_display": format_patient_age(pt.get("date_of_birth")),
            "gender": pt.get("gender"),
            "ward_name": ward.get("name"),
            "room_name": room.get("name"),
            "bed_number": b.get("bed_number"),
            "admitted_at": b.get("admitted_at"),
            "nights": nights,
            "daily_rate": rate,
            "room_charges": room_total,
            "other_charges": adhoc,
            "running_total": round(room_total + adhoc, 2),
            # Flagged rather than hidden: an unpriced ward bills nothing for the
            # bed, and the ward round is where somebody would notice.
            "needs_rate": rate <= 0,
            "status": enc.get("status"),
            "department": enc.get("department"),
            "chief_complaint": enc.get("chief_complaint"),
            "queue_number": enc.get("queue_number"),
            "payer_type": enc.get("payer_type"),
            "membership_id": enc.get("membership_id"),
            "consulting_doctor": enc.get("consulting_doctor"),
            # A bed still held by a discharged encounter is a real problem: the
            # bed shows unavailable and the charge keeps running.
            "encounter_closed": enc.get("status") == "discharged",
        })

    out.sort(key=lambda r: (r.get("ward_name") or "", r.get("room_name") or "", r.get("bed_number") or ""))
    return {
        "inpatients": out,
        "count": len(out),
        "running_total": round(sum(r["running_total"] for r in out), 2),
        "unpriced": sum(1 for r in out if r["needs_rate"]),
        "stale_beds": sum(1 for r in out if r["encounter_closed"]),
    }
