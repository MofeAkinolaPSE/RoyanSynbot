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
  GET  /wards/occupancy                 – Aggregated bed occupancy view
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.db import db, audit_event
from src.middleware import verify_jwt, require_role
from src.constants import TABLE_WARDS, TABLE_BEDS, TABLE_ENCOUNTERS, TABLE_PATIENTS

logger = logging.getLogger(__name__)

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


class BedStatusUpdate(BaseModel):
    status: str
    notes: Optional[str] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/occupancy")
async def bed_occupancy(user=Depends(verify_jwt)):
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
async def list_wards(user=Depends(verify_jwt)):
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
async def create_ward(payload: WardCreate, user=Depends(require_role("admin"))):
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
    audit_event("ward_created", {"name": payload.name}, actor_id=user.get("sub"), subject_type="ward", subject_id=str(ward.get("id") or ""))
    return {"ok": True, "ward": ward}


@router.get("/{ward_id}/beds")
async def list_beds(ward_id: int, user=Depends(verify_jwt)):
    result = db.table(TABLE_BEDS).select("*").eq("ward_id", ward_id).order("bed_number").execute()
    return {"beds": result.data, "count": len(result.data)}


@router.post("/{ward_id}/beds", status_code=201)
async def add_bed(ward_id: int, payload: BedCreate, user=Depends(require_role("admin"))):
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
async def admit_patient(ward_id: int, bed_id: int, payload: AdmitRequest, user=Depends(verify_jwt)):
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
    db.table(TABLE_BEDS).update(updates).eq("id", bed_id).execute()

    # Update encounter with bed/ward assignment
    if payload.encounter_id:
        db.table(TABLE_ENCOUNTERS).update({"bed_id": bed_id, "ward_id": ward_id}).eq("id", payload.encounter_id).execute()

    audit_event(
        "patient_admitted_to_bed",
        {"patient_id": payload.patient_id, "ward_id": ward_id},
        actor_id=user.get("sub"),
        subject_type="bed",
        subject_id=str(bed_id),
    )
    return {"ok": True, "bed_id": bed_id, "patient_id": payload.patient_id, "status": "occupied"}


@router.post("/{ward_id}/beds/{bed_id}/discharge")
async def free_bed(ward_id: int, bed_id: int, user=Depends(verify_jwt)):
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
