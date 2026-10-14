"""
Wards & Beds Router — RoyanHealth / Royan Hospital
=====================================================
Manages ward configuration and real-time bed occupancy.

Endpoints:
  GET  /wards                           – List all wards with occupancy summary
  POST /wards                           – Create a new ward (admin)
  GET  /wards/{ward_id}/beds            – List beds in a ward
  POST /wards/{ward_id}/beds            – Add a bed to a ward (admin)
  POST /wards/{ward_id}/beds/{bed_id}/admit    – Admit patient to bed
  POST /wards/{ward_id}/beds/{bed_id}/discharge – Free a bed
  PATCH /wards/{ward_id}/beds/{bed_id}/status  – Set bed to available/reserved/maintenance
  GET  /wards/occupancy                 – Aggregated bed occupancy view
"""
from __future__ import annotations

import logging
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.db import db, audit_event
from src.middleware import verify_jwt, require_role
from src.services.event_service import emit_clinical_event
from src.constants import TABLE_WARDS, TABLE_BEDS, TABLE_ENCOUNTERS, TABLE_PATIENTS

logger = logging.getLogger(__name__)


def _natural_sort_key(bed_number: object):
    """Sort key that treats embedded digit runs as numbers, not characters —
    bed_number is a text column, so a plain ORDER BY sorts lexicographically
    ("1", "10", "2", "3", ...) instead of numerically. Splits "10" into
    [10] and "ICU-2" into ["icu-", 2] so mixed alphanumeric bed labels still
    compare consistently within a ward."""
    s = str(bed_number or "")
    return [int(chunk) if chunk.isdigit() else chunk.lower() for chunk in re.split(r"(\d+)", s)]


def _sort_beds_naturally(beds: list) -> list:
    """Room first, then bed number, both naturally.

    Sorting on bed_number alone put Room101 bed 1 next to Room108 bed 1 and
    scattered each room's beds through the list. Rooms are how staff navigate a
    ward, so they group first. Natural ordering on both keeps Room2 before
    Room10 and bed 2 before bed 10 — plain string sort gets each of those
    backwards.

    Run AFTER _enrich_bed_rooms, which is what puts room_name on the row.
    """
    try:
        return sorted(
            beds,
            key=lambda b: (
                _natural_sort_key(b.get("room_name") or "￿"),  # unroomed last
                _natural_sort_key(b.get("bed_number")),
            ),
        )
    except TypeError:
        # Mixed key shapes that don't compare (rare) — fall back to the
        # original (already lexicographically-ordered) sequence rather than
        # raising and breaking the endpoint.
        return beds

router = APIRouter(prefix="/wards", tags=["Wards & Beds"])

WARD_TYPES = {"general", "surgical", "icu", "maternity", "paediatric", "isolation", "emergency", "private"}
BED_TYPES  = {"standard", "icu", "isolation", "maternity", "recovery"}
BED_STATUSES = {"available", "occupied", "reserved", "maintenance"}


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class WardCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    ward_type: str
    floor: Optional[str] = None
    total_beds: int = Field(0, ge=0)
    description: Optional[str] = None
    notes: Optional[str] = None

    model_config = {"extra": "ignore"}


class BedCreate(BaseModel):
    bed_number: str = Field(..., min_length=1, max_length=20)
    bed_type: str = "standard"
    notes: Optional[str] = None


class AdmitRequest(BaseModel):
    patient_id: int
    encounter_id: Optional[int] = None
    notes: Optional[str] = None


class BedStatusUpdate(BaseModel):
    status: str
    notes: Optional[str] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/occupancy")
def bed_occupancy(user=Depends(verify_jwt)):
    """Return bed occupancy summary per ward from the royan_bed_occupancy view."""
    # Query the view directly; if unavailable, callers still get a clear 500.
    try:
        import psycopg2, psycopg2.extras, os
        conn = db.pool.getconn()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT * FROM public.royan_bed_occupancy ORDER BY ward_name")
        rows = [dict(r) for r in cur.fetchall()]
        cur.close()
        db.pool.putconn(conn)
        return {"wards": rows, "count": len(rows)}
    except Exception as exc:
        logger.error("Occupancy query failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to fetch occupancy data")


@router.get("")
def list_wards(user=Depends(verify_jwt)):
    result = db.table(TABLE_WARDS).select("*").order("name").execute()
    wards = result.data or []
    try:
        beds = db.table(TABLE_BEDS).select("ward_id,status").execute().data or []
        counts: dict = {}
        for bed in beds:
            ward_id = bed.get("ward_id")
            counts.setdefault(ward_id, {"total": 0, "occupied": 0, "available": 0})
            counts[ward_id]["total"] += 1
            if bed.get("status") == "occupied":
                counts[ward_id]["occupied"] += 1
            if bed.get("status") == "available":
                counts[ward_id]["available"] += 1
        for ward in wards:
            summary = counts.get(ward.get("id"), {})
            ward["total_beds"] = summary.get("total", ward.get("total_beds") or 0)
            ward["occupied_beds"] = summary.get("occupied", 0)
            ward["available_beds"] = summary.get("available", max((ward.get("total_beds") or 0) - summary.get("occupied", 0), 0))
            ward["description"] = ward.get("notes")
    except Exception:
        for ward in wards:
            ward["occupied_beds"] = 0
            ward["available_beds"] = ward.get("total_beds") or 0
            ward["description"] = ward.get("notes")
    return {"wards": wards, "count": len(wards)}


@router.post("", status_code=201)
def create_ward(payload: WardCreate, user=Depends(require_role("admin"))):
    ward_type = "paediatric" if payload.ward_type == "pediatrics" else payload.ward_type
    if ward_type not in WARD_TYPES:
        raise HTTPException(status_code=422, detail=f"ward_type must be one of {WARD_TYPES}")
    data = payload.model_dump(exclude_none=True)
    data["ward_type"] = ward_type
    if data.get("description") and not data.get("notes"):
        data["notes"] = data.pop("description")
    data.pop("description", None)
    try:
        result = db.table(TABLE_WARDS).insert(data).execute()
    except Exception as exc:
        logger.error("Ward create failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to create ward")
    ward = result.data[0] if result.data else data
    ward_id = ward.get("id")

    # Auto-provision `total_beds` real royan_beds rows. Previously only
    # add_bed() (POST /{ward_id}/beds) could create a real bed, and nothing
    # in the frontend ever called it — every new ward was permanently
    # admission-dead. bed_number is a simple zero-padded sequence; uniqueness
    # is guaranteed since this is a brand-new ward with no prior beds.
    beds_created: list = []
    total_beds = payload.total_beds or 0
    if ward_id and total_beds > 0:
        bed_rows = [
            {"ward_id": ward_id, "bed_number": f"{i:03d}", "bed_type": "standard", "status": "available"}
            for i in range(1, total_beds + 1)
        ]
        try:
            bed_result = db.table(TABLE_BEDS).insert(bed_rows).execute()
            beds_created = bed_result.data or []
        except Exception as exc:
            logger.error("Bed auto-provisioning failed for ward %s: %s", ward_id, exc)
            # db.table() has no cross-call transaction — compensate manually
            # rather than leaving a half-provisioned, admission-dead ward.
            try:
                db.table(TABLE_WARDS).delete().eq("id", ward_id).execute()
            except Exception:
                logger.error("Ward %s left behind after failed bed provisioning — needs manual cleanup", ward_id)
            raise HTTPException(status_code=500, detail="Ward created but bed provisioning failed; ward was rolled back")

    audit_event(
        "ward_created",
        {"name": payload.name, "beds_provisioned": len(beds_created)},
        actor_id=user.get("sub"), subject_type="ward", subject_id=str(ward_id or ""),
    )
    return {"ok": True, "ward": ward, "beds": beds_created}


def _enrich_bed_rooms(beds: list) -> None:
    """Attach room name and nightly rate to bed rows in place.

    Beds carried only a number, so the ward page could show "bed 3" but never
    "Room104" — the names Royan actually uses, and the ones their prices are
    keyed to. Batched: one query for every room on the page, not one per bed.
    """
    if not beds:
        return
    room_ids = list({b["room_id"] for b in beds if b.get("room_id") is not None})
    if not room_ids:
        return
    try:
        rows = db.table("royan_rooms").select("id,name,daily_rate,room_type").in_("id", room_ids).execute()
        rmap = {r["id"]: r for r in (rows.data or [])}
    except Exception as exc:
        logger.warning("Room enrichment failed: %s", exc)
        return
    for b in beds:
        r = rmap.get(b.get("room_id"))
        if r:
            b["room_name"] = r.get("name")
            b["room_daily_rate"] = r.get("daily_rate")
            b["room_type"] = r.get("room_type")


def _enrich_bed_patients(beds: list) -> None:
    """Batch-merge patient identity and the occupant's active encounter onto bed
    rows in place, keyed off current_patient_id — royan_beds has no patient
    identity columns of its own.

    current_encounter_id matters because nursing notes are written against an
    encounter, not a patient. Without it the ward view can show a patient's
    record but not add to it, which is a worse offer than not opening it at all.
    """
    if not beds:
        return
    try:
        pid_set = list({b["current_patient_id"] for b in beds if b.get("current_patient_id") is not None})
        if not pid_set:
            return
        pt_rows = db.table(TABLE_PATIENTS).select("id,mrn,first_name,last_name").in_("id", pid_set).execute()
        pt_map = {p["id"]: p for p in (pt_rows.data or [])}
        for b in beds:
            p = pt_map.get(b.get("current_patient_id"))
            if p:
                fn, ln = (p.get("first_name") or "").strip(), (p.get("last_name") or "").strip()
                b["patient_name"] = f"{fn} {ln}".strip() or None
                b["patient_mrn"] = p.get("mrn")

        # Newest non-discharged native encounter per occupant.
        try:
            enc_rows = (
                db.table(TABLE_ENCOUNTERS)
                .select("id,patient_id,status,created_at")
                .in_("patient_id", pid_set)
                .neq("status", "discharged")
                .is_("external_source", None)
                .order("created_at", desc=True)
                .execute()
                .data
                or []
            )
            enc_map: dict = {}
            for e in enc_rows:
                enc_map.setdefault(e["patient_id"], e["id"])
            for b in beds:
                b["current_encounter_id"] = enc_map.get(b.get("current_patient_id"))
        except Exception as exc:
            logger.warning("bed encounter enrichment failed: %s", exc)
    except Exception as exc:
        logger.warning("bed patient enrichment failed: %s", exc)


@router.get("/rooms")
def list_rooms(ward_id: Optional[int] = Query(None), user=Depends(verify_jwt)):
    """Rooms, with their nightly rate and how many beds each holds.

    Seeded in migration 209 from the real ward/room/bed structure in
    royan_ward_stay_history rather than invented, so the names match what staff
    actually say.
    """
    try:
        q = db.table("royan_rooms").select("id,ward_id,name,room_type,daily_rate,is_active").order("name")
        if ward_id:
            q = q.eq("ward_id", ward_id)
        rooms = q.execute().data or []
    except Exception as exc:
        logger.warning("Room listing failed: %s", exc)
        return {"rooms": [], "count": 0}

    try:
        beds = db.table(TABLE_BEDS).select("id,room_id,status,current_patient_id").execute().data or []
    except Exception:
        beds = []
    for r in rooms:
        mine = [b for b in beds if b.get("room_id") == r["id"]]
        r["bed_count"] = len(mine)
        r["occupied_count"] = sum(1 for b in mine if b.get("current_patient_id"))

    ward_ids = list({r["ward_id"] for r in rooms if r.get("ward_id")})
    if ward_ids:
        try:
            wards = db.table(TABLE_WARDS).select("id,name").in_("id", ward_ids).execute()
            wmap = {w["id"]: w.get("name") for w in wards.data or []}
            for r in rooms:
                r["ward_name"] = wmap.get(r.get("ward_id"))
        except Exception:
            pass

    return {"rooms": rooms, "count": len(rooms),
            "unpriced": sum(1 for r in rooms if not r.get("daily_rate"))}


class RoomRateUpdate(BaseModel):
    daily_rate: float = Field(..., ge=0)


@router.patch("/rooms/{room_id}/rate")
def set_room_rate(room_id: int, payload: RoomRateUpdate, user=Depends(verify_jwt)):
    """Set a room's nightly rate."""
    try:
        db.table("royan_rooms").update({"daily_rate": payload.daily_rate}).eq("id", room_id).execute()
    except Exception as exc:
        logger.error("Room rate update failed: %s", exc)
        raise HTTPException(status_code=500, detail="Could not save the room rate")
    return {"ok": True, "room_id": room_id, "daily_rate": payload.daily_rate}


@router.get("/beds/available")
def list_available_beds(user=Depends(verify_jwt)):
    """Every free bed in the hospital, with its ward name.

    Beds were only listable one ward at a time. Admitting a patient means
    picking from whatever is free ANYWHERE, so the client would otherwise fetch
    the ward list and then one request per ward just to populate a dropdown.

    "Free" excludes maintenance beds: a bed out of service is not a placement
    option, and offering it invites a nurse to admit someone into a bed that is
    broken.
    """
    try:
        beds = (
            db.table(TABLE_BEDS)
            .select("id,ward_id,bed_number,bed_type,status,current_patient_id,notes")
            .is_("current_patient_id", None)
            .order("bed_number")
            .limit(500)
            .execute().data or []
        )
    except Exception as exc:
        logger.warning("Available-bed lookup failed: %s", exc)
        return {"beds": [], "count": 0}

    beds = [b for b in beds if (b.get("status") or "available") not in ("maintenance", "reserved")]

    ward_ids = list({b["ward_id"] for b in beds if b.get("ward_id")})
    ward_names = {}
    if ward_ids:
        try:
            wards = db.table(TABLE_WARDS).select("id,name").in_("id", ward_ids).execute()
            ward_names = {w["id"]: w.get("name") for w in wards.data or []}
        except Exception:
            ward_names = {}
    for b in beds:
        b["ward_name"] = ward_names.get(b.get("ward_id"))

    _enrich_bed_rooms(beds)
    beds = _sort_beds_naturally(beds)
    return {"beds": beds, "count": len(beds)}


@router.get("/{ward_id}/beds")
def list_beds(ward_id: int, user=Depends(verify_jwt)):
    result = db.table(TABLE_BEDS).select("*").eq("ward_id", ward_id).execute()
    beds = result.data or []
    _enrich_bed_patients(beds)
    _enrich_bed_rooms(beds)
    # After enrichment: the sort keys on room_name, which _enrich_bed_rooms adds.
    beds = _sort_beds_naturally(beds)
    return {"beds": beds, "count": len(beds)}


@router.post("/{ward_id}/beds", status_code=201)
def add_bed(ward_id: int, payload: BedCreate, user=Depends(require_role("admin"))):
    if payload.bed_type not in BED_TYPES:
        raise HTTPException(status_code=422, detail=f"bed_type must be one of {BED_TYPES}")
    # Verify ward exists
    ward = db.table(TABLE_WARDS).select("id").eq("id", ward_id).execute()
    if not ward.data:
        raise HTTPException(status_code=404, detail=f"Ward {ward_id} not found")
    data = {**payload.model_dump(exclude_none=True), "ward_id": ward_id, "status": "available"}
    try:
        result = db.table(TABLE_BEDS).insert(data).execute()
    except Exception as exc:
        logger.error("Bed create failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to add bed (bed number may already exist in this ward)")
    bed = result.data[0] if result.data else data
    return {"ok": True, "bed": bed}


@router.post("/{ward_id}/beds/{bed_id}/admit")
def admit_patient(ward_id: int, bed_id: int, payload: AdmitRequest, user=Depends(verify_jwt)):
    """Assign a patient to a bed (marks bed as occupied)."""
    bed = db.table(TABLE_BEDS).select("*").eq("id", bed_id).eq("ward_id", ward_id).execute()
    if not bed.data:
        raise HTTPException(status_code=404, detail="Bed not found in this ward")
    b = bed.data[0]
    if b["status"] != "available":
        raise HTTPException(status_code=409, detail=f"Bed is currently '{b['status']}', cannot admit")

    from datetime import datetime, timezone
    updates = {
        "status": "occupied",
        "current_patient_id": payload.patient_id,
        "current_encounter_id": payload.encounter_id,
        "admitted_at": datetime.now(timezone.utc).isoformat(),
    }
    if payload.notes is not None:
        updates["notes"] = payload.notes
    db.table(TABLE_BEDS).update(updates).eq("id", bed_id).execute()

    # Update encounter with bed/ward assignment — validated so a stale or
    # mismatched encounter_id doesn't silently attach itself to this patient.
    if payload.encounter_id:
        enc = db.table(TABLE_ENCOUNTERS).select("id,patient_id").eq("id", payload.encounter_id).execute()
        if not enc.data:
            raise HTTPException(status_code=404, detail=f"Encounter {payload.encounter_id} not found")
        if enc.data[0].get("patient_id") != payload.patient_id:
            raise HTTPException(status_code=409, detail="encounter_id does not belong to this patient")
        db.table(TABLE_ENCOUNTERS).update({"bed_id": bed_id, "ward_id": ward_id}).eq("id", payload.encounter_id).execute()

    audit_event(
        "patient_admitted_to_bed",
        {"patient_id": payload.patient_id, "ward_id": ward_id},
        actor_id=user.get("sub"),
        subject_type="bed",
        subject_id=str(bed_id),
    )
    emit_clinical_event(
        event_type="ENCOUNTER_ADMITTED",
        encounter_id=payload.encounter_id,
        patient_id=payload.patient_id,
        entity_type="bed", entity_id=bed_id,
        performed_by=user.get("sub"),
        event_data={"ward_id": ward_id, "bed_id": bed_id},
    )
    return {"ok": True, "bed_id": bed_id, "patient_id": payload.patient_id, "status": "occupied"}


@router.post("/{ward_id}/beds/{bed_id}/discharge")
def free_bed(ward_id: int, bed_id: int, user=Depends(verify_jwt)):
    """Free a bed after patient discharge (marks bed as available)."""
    bed = db.table(TABLE_BEDS).select("*").eq("id", bed_id).eq("ward_id", ward_id).execute()
    if not bed.data:
        raise HTTPException(status_code=404, detail="Bed not found in this ward")

    db.table(TABLE_BEDS).update({
        "status": "available",
        "current_patient_id": None,
        "current_encounter_id": None,
        "admitted_at": None,
    }).eq("id", bed_id).execute()

    audit_event("bed_freed", {"ward_id": ward_id}, actor_id=user.get("sub"), subject_type="bed", subject_id=str(bed_id))
    return {"ok": True, "bed_id": bed_id, "status": "available"}


BED_STATUS_TRANSITIONS = {
    "available":   {"reserved", "maintenance"},
    "reserved":    {"available", "maintenance"},
    "maintenance": {"available", "reserved"},
    "occupied":    set(),
}


@router.patch("/{ward_id}/beds/{bed_id}/status")
def update_bed_status(ward_id: int, bed_id: int, payload: BedStatusUpdate, user=Depends(verify_jwt)):
    """Set a bed to available/reserved/maintenance. Occupying is admit's job;
    freeing an occupied bed is discharge's job — both already own clearing
    current_patient_id/admitted_at correctly."""
    if payload.status not in {"available", "reserved", "maintenance"}:
        raise HTTPException(status_code=422, detail="status must be one of {'available','reserved','maintenance'} — use /admit to occupy a bed")

    bed = db.table(TABLE_BEDS).select("*").eq("id", bed_id).eq("ward_id", ward_id).execute()
    if not bed.data:
        raise HTTPException(status_code=404, detail="Bed not found in this ward")
    current = bed.data[0]["status"]

    if payload.status not in BED_STATUS_TRANSITIONS.get(current, set()):
        if current == "occupied":
            raise HTTPException(status_code=409, detail="Bed is occupied — discharge the patient first")
        raise HTTPException(status_code=409, detail=f"Cannot change bed status from '{current}' to '{payload.status}'")

    updates: dict = {"status": payload.status}
    if payload.notes is not None:
        updates["notes"] = payload.notes
    db.table(TABLE_BEDS).update(updates).eq("id", bed_id).execute()

    audit_event("bed_status_updated", {"from": current, "to": payload.status},
                actor_id=user.get("sub"), subject_type="bed", subject_id=str(bed_id))
    return {"ok": True, "bed_id": bed_id, "status": payload.status}
