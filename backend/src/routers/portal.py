"""
Patient Portal Router — RoyanHealth / Royan Hospital
======================================================
Lightweight public-facing endpoints for the patient-portal PWA.

Endpoints:
  POST /portal/auth                  — login with MRN + phone, return short-lived JWT
  GET  /portal/me                    — patient profile (portal JWT required)
  GET  /portal/appointments          — patient's own appointments
  GET  /portal/lab-results           — patient's own resulted lab orders
  GET  /portal/bills                 — patient's own bills
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from jose import jwt as jose_jwt
from pydantic import BaseModel

from src.db import db
from src.constants import (
    TABLE_PATIENTS, TABLE_APPOINTMENTS, TABLE_LAB_ORDERS, TABLE_LAB_RESULTS,
    TABLE_BILLING, TABLE_BILL_ITEMS, TABLE_PRESCRIPTIONS, TABLE_VITALS,
    TABLE_NOTIFICATION_LOGS, TABLE_TELEMEDICINE_SESSIONS, TABLE_ENCOUNTERS,
    JWT_SECRET, JWT_ALGORITHM,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/portal", tags=["Patient Portal"])

PORTAL_TOKEN_EXPIRE_HOURS = int(os.getenv("PORTAL_TOKEN_EXPIRE_HOURS", "24"))
PORTAL_AUDIENCE = "patient_portal"


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def _create_portal_token(patient_id: int | str, mrn: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=PORTAL_TOKEN_EXPIRE_HOURS)
    return jose_jwt.encode(
        {"sub": str(patient_id), "mrn": mrn, "aud": PORTAL_AUDIENCE, "exp": expire},
        JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )


def _verify_portal_token(token: str) -> dict:
    try:
        return jose_jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM], audience=PORTAL_AUDIENCE)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired portal session")


def _portal_auth(authorization: str = "") -> dict:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Portal auth required")
    return _verify_portal_token(authorization[7:])


from fastapi import Header


async def portal_jwt(authorization: str = Header(default="")) -> dict:
    return _portal_auth(authorization)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class PortalLoginRequest(BaseModel):
    mrn: str
    phone: str

    model_config = {"extra": "ignore"}


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/auth")
def portal_login(payload: PortalLoginRequest):
    """Authenticate a patient using their MRN and registered phone number."""
    mrn = payload.mrn.strip().upper()
    phone = payload.phone.strip().replace(" ", "").replace("-", "")

    result = db.table(TABLE_PATIENTS).select("*").eq("mrn", mrn).limit(1).execute()
    if not result.data:
        raise HTTPException(status_code=401, detail="Patient not found")

    patient = result.data[0]

    # Normalise stored phone for comparison
    stored_phone = (patient.get("phone") or "").replace(" ", "").replace("-", "")
    if not stored_phone or stored_phone != phone:
        raise HTTPException(status_code=401, detail="Phone number does not match our records")

    token = _create_portal_token(patient["id"], mrn)
    return {
        "token": token,
        "patient": {
            "id": patient["id"],
            "mrn": patient["mrn"],
            "first_name": patient.get("first_name"),
            "last_name": patient.get("last_name"),
        },
    }


@router.get("/me")
def portal_me(claims: dict = Depends(portal_jwt)):
    """Return the authenticated patient's profile."""
    patient_id = claims["sub"]
    result = db.table(TABLE_PATIENTS).select(
        "id,mrn,first_name,last_name,date_of_birth,gender,phone,email,address,"
        "next_of_kin_name,next_of_kin_phone,blood_group,genotype,allergies,hmo_provider,hmo_id"
    ).eq("id", patient_id).limit(1).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Patient not found")
    return {"patient": result.data[0]}


@router.get("/appointments")
def portal_appointments(claims: dict = Depends(portal_jwt)):
    """Return the patient's appointments (upcoming first)."""
    patient_id = claims["sub"]
    result = (
        db.table(TABLE_APPOINTMENTS)
        .select("id,appointment_date,appointment_type,department,doctor_name,status,notes")
        .eq("patient_id", patient_id)
        .order("appointment_date", desc=False)
        .limit(50)
        .execute()
    )
    return {"appointments": result.data or []}


@router.get("/lab-results")
def portal_lab_results(claims: dict = Depends(portal_jwt)):
    """Return the patient's resulted lab orders with result values."""
    patient_id = claims["sub"]
    orders = (
        db.table(TABLE_LAB_ORDERS)
        .select("id,test_name,test_code,urgency,status,ordered_at")
        .eq("patient_id", patient_id)
        .eq("status", "resulted")
        .order("ordered_at", desc=True)
        .limit(100)
        .execute()
        .data or []
    )
    if not orders:
        return {"results": []}
    order_ids = [o["id"] for o in orders]
    lab_results = (
        db.table(TABLE_LAB_RESULTS)
        .select("lab_order_id,result_data,result_summary,interpretation,reference_range,resulted_at,is_critical")
        .in_("lab_order_id", order_ids)
        .execute()
        .data or []
    )
    result_map = {r["lab_order_id"]: r for r in lab_results}
    return {"results": [{**o, **result_map.get(o["id"], {})} for o in orders]}


_BILL_COMPONENT_FEES = (
    "consultation_fee", "lab_charges", "pharmacy_charges",
    "ward_charges", "procedure_charges", "miscellaneous",
)


@router.get("/bills")
def portal_bills(claims: dict = Depends(portal_jwt)):
    """Return the patient's bills with itemised line items where available."""
    patient_id = claims["sub"]
    result = (
        db.table(TABLE_BILLING)
        .select(
            "id,bill_number,subtotal,discount,hmo_covered,patient_balance,status,billed_at,paid_at,encounter_id,"
            "consultation_fee,lab_charges,pharmacy_charges,ward_charges,procedure_charges,miscellaneous"
        )
        .eq("patient_id", patient_id)
        .order("billed_at", desc=True)
        .limit(50)
        .execute()
    )
    bills = result.data or []
    if bills:
        bill_ids = [b["id"] for b in bills]
        items_res = (
            db.table(TABLE_BILL_ITEMS)
            .select("billing_id,description,category,quantity,unit_price,patient_amount,covered_amount")
            .in_("billing_id", bill_ids)
            .execute()
        )
        items_by_bill: dict = {}
        for item in (items_res.data or []):
            items_by_bill.setdefault(item["billing_id"], []).append(item)
        for bill in bills:
            # total_amount is computed (mirrors _total_from_bill in billing_hospital.py)
            if bill.get("subtotal") is not None:
                bill["total_amount"] = float(bill["subtotal"] or 0)
            else:
                bill["total_amount"] = sum(float(bill.get(f) or 0) for f in _BILL_COMPONENT_FEES)
            bill["items"] = items_by_bill.get(bill["id"], [])
    return {"bills": bills}


@router.get("/prescriptions")
def portal_prescriptions(claims: dict = Depends(portal_jwt)):
    """Return the patient's prescriptions (active and past)."""
    patient_id = claims["sub"]
    result = (
        db.table(TABLE_PRESCRIPTIONS)
        .select("id,drug_name,dosage,frequency,duration,route,status,prescribed_at")
        .eq("patient_id", patient_id)
        .order("prescribed_at", desc=True)
        .limit(50)
        .execute()
    )
    return {"prescriptions": result.data or []}


@router.get("/vitals")
def portal_vitals(claims: dict = Depends(portal_jwt)):
    """Return the patient's vitals from the last 30 days."""
    from datetime import timedelta
    patient_id = claims["sub"]
    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    result = (
        db.table(TABLE_VITALS)
        .select("id,temperature,pulse,bp_systolic,bp_diastolic,spo2,weight,pain_score,recorded_at")
        .eq("patient_id", patient_id)
        .gte("recorded_at", cutoff)
        .order("recorded_at", desc=True)
        .limit(60)
        .execute()
    )
    return {"vitals": result.data or []}


@router.get("/notifications")
def portal_notifications(claims: dict = Depends(portal_jwt)):
    """Return SMS/WhatsApp messages sent to this patient."""
    patient_id = claims["sub"]
    try:
        result = (
            db.table(TABLE_NOTIFICATION_LOGS)
            .select("id,channel,message,status,sent_at,created_at")
            .eq("patient_id", patient_id)
            .order("created_at", desc=True)
            .limit(30)
            .execute()
        )
        return {"notifications": result.data or []}
    except Exception:
        return {"notifications": []}


@router.get("/telemedicine")
def portal_telemedicine(claims: dict = Depends(portal_jwt)):
    """Return upcoming or active telemedicine sessions for this patient."""
    patient_id = claims["sub"]
    result = (
        db.table(TABLE_TELEMEDICINE_SESSIONS)
        .select("id,doctor_id,scheduled_date,scheduled_time,duration_minutes,visit_type,status,meeting_link,chief_complaint")
        .eq("patient_id", patient_id)
        .in_("status", ["scheduled", "active"])
        .order("scheduled_date", desc=False)
        .limit(10)
        .execute()
    )
    return {"sessions": result.data or []}


@router.get("/encounters")
def portal_encounters(claims: dict = Depends(portal_jwt)):
    """Return the patient's clinical encounter history (outpatient & inpatient)."""
    patient_id = claims["sub"]
    result = (
        db.table(TABLE_ENCOUNTERS)
        .select("id,encounter_type,status,chief_complaint,diagnosis_notes,consulting_doctor,department,triage_level,created_at,discharge_at,discharge_summary")
        .eq("patient_id", patient_id)
        .order("created_at", desc=True)
        .limit(50)
        .execute()
    )
    return {"encounters": result.data or []}
