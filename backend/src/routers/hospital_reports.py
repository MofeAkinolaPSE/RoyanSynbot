"""
Hospital Reports Router — SynbotHealth / Royan Hospital
=========================================================
Aggregate clinical and financial reporting for NHIA/HMIS submission,
disease burden analysis, financial summaries, and patient demographics.

Endpoints:
  GET  /hospital-reports/disease-burden       – Top diagnoses by ICD-10 code
  GET  /hospital-reports/hmis                 – HMIS aggregate statistics
  GET  /hospital-reports/nhia-export          – NHIA-formatted encounter + billing data
  GET  /hospital-reports/financial-summary    – Revenue by payer type and service category
  GET  /hospital-reports/patient-demographics – Age group + gender distribution
  GET  /hospital-reports/bed-occupancy        – Ward bed utilisation
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query

from src.db import db
from src.middleware import verify_jwt
from src.constants import (
    TABLE_ENCOUNTERS,
    TABLE_PATIENTS,
    TABLE_BILLING,
    TABLE_PAYMENTS,
    TABLE_WARDS,
    TABLE_BEDS,
    TABLE_APPOINTMENTS,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/hospital-reports", tags=["Hospital Reports"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _age_band(dob: Optional[str]) -> str:
    if not dob:
        return "unknown"
    try:
        birth = date.fromisoformat(str(dob)[:10])
        years = (date.today() - birth).days // 365
        if years < 1:  return "0-1"
        if years < 5:  return "1-4"
        if years < 15: return "5-14"
        if years < 25: return "15-24"
        if years < 45: return "25-44"
        if years < 65: return "45-64"
        return "65+"
    except Exception:
        return "unknown"


# ---------------------------------------------------------------------------
# Disease Burden
# ---------------------------------------------------------------------------

@router.get("/disease-burden")
async def disease_burden(
    start_date: Optional[str] = Query(None, description="ISO date YYYY-MM-DD"),
    end_date:   Optional[str] = Query(None),
    limit:      int           = Query(20, ge=1, le=100),
    user=Depends(verify_jwt),
):
    """Aggregate encounter diagnoses by ICD-10 code, returning the top N."""
    q = db.table(TABLE_ENCOUNTERS).select(
        "icd10_codes,encounter_date,encounter_type"
    ).order("encounter_date", desc=True)
    if start_date: q = q.gte("encounter_date", start_date)
    if end_date:   q = q.lte("encounter_date", end_date)
    rows = q.execute().data or []

    code_counts: dict = defaultdict(int)
    total = len(rows)

    for r in rows:
        codes = r.get("icd10_codes") or []
        if isinstance(codes, str):
            codes = [c.strip() for c in codes.split(",") if c.strip()]
        for code in codes:
            code_counts[code] += 1

    ranked = sorted(code_counts.items(), key=lambda x: x[1], reverse=True)[:limit]
    return {
        "total_encounters_sampled": total,
        "top_diagnoses": [
            {
                "icd10_code": code,
                "count": cnt,
                "pct": round(cnt / total * 100, 1) if total else 0,
            }
            for code, cnt in ranked
        ],
    }


# ---------------------------------------------------------------------------
# HMIS Summary
# ---------------------------------------------------------------------------

@router.get("/hmis")
async def hmis_summary(
    month: Optional[str] = Query(None, description="YYYY-MM"),
    user=Depends(verify_jwt),
):
    """Health Management Information System aggregate statistics."""
    enc_q  = db.table(TABLE_ENCOUNTERS).select("encounter_type,status,encounter_date")
    appt_q = db.table(TABLE_APPOINTMENTS).select("status,appointment_date")
    bed_q  = db.table(TABLE_BEDS).select("status")

    if month:
        yr, mo = int(month[:4]), int(month[5:7])
        start  = f"{month}-01"
        nxt    = f"{yr}-{mo+1:02d}-01" if mo < 12 else f"{yr+1}-01-01"
        enc_q  = enc_q.gte("encounter_date", start).lt("encounter_date", nxt)
        appt_q = appt_q.gte("appointment_date", start).lt("appointment_date", nxt)

    encounters   = enc_q.execute().data  or []
    appointments = appt_q.execute().data or []
    beds         = bed_q.execute().data  or []

    by_type: dict   = defaultdict(int)
    by_status: dict = defaultdict(int)
    for e in encounters:
        by_type[e.get("encounter_type") or "other"]  += 1
        by_status[e.get("status") or "unknown"]      += 1

    appt_by_status: dict = defaultdict(int)
    for a in appointments:
        appt_by_status[a.get("status") or "unknown"] += 1

    occupied   = sum(1 for b in beds if b.get("status") == "occupied")
    total_beds = len(beds)

    return {
        "period": month or "all_time",
        "encounters": {
            "total":     len(encounters),
            "by_type":   dict(by_type),
            "by_status": dict(by_status),
            "opd":       by_type.get("outpatient", 0),
            "ipd":       by_type.get("inpatient", 0),
            "emergency": by_type.get("emergency", 0),
        },
        "appointments": {
            "total":       len(appointments),
            "by_status":   dict(appt_by_status),
            "no_show_rate": round(
                appt_by_status.get("no_show", 0) / len(appointments) * 100, 1
            ) if appointments else 0,
        },
        "beds": {
            "total":          total_beds,
            "occupied":       occupied,
            "available":      total_beds - occupied,
            "occupancy_rate": round(occupied / total_beds * 100, 1) if total_beds else 0,
        },
    }


# ---------------------------------------------------------------------------
# NHIA Export
# ---------------------------------------------------------------------------

@router.get("/nhia-export")
async def nhia_export(
    start_date: Optional[str] = Query(None),
    end_date:   Optional[str] = Query(None),
    hmo_id:     Optional[int] = Query(None),
    limit:      int           = Query(200, ge=1, le=1000),
    user=Depends(verify_jwt),
):
    """Return encounter + billing data in NHIA-compatible format for submission."""
    enc_q = db.table(TABLE_ENCOUNTERS).select(
        "id,patient_id,encounter_date,encounter_type,icd10_codes,status,hmo_plan_id"
    ).order("encounter_date", desc=True).limit(limit)
    if start_date: enc_q = enc_q.gte("encounter_date", start_date)
    if end_date:   enc_q = enc_q.lte("encounter_date", end_date)
    if hmo_id:     enc_q = enc_q.eq("hmo_id", hmo_id)

    encounters = enc_q.execute().data or []
    enc_ids    = [e["id"] for e in encounters]

    billing_map: dict = {}
    if enc_ids:
        bills = db.table(TABLE_BILLING).select(
            "encounter_id,total_amount,hmo_amount,patient_amount,status"
        ).in_("encounter_id", enc_ids).execute().data or []
        for b in bills:
            billing_map[b["encounter_id"]] = b

    records = []
    for e in encounters:
        b = billing_map.get(e["id"], {})
        records.append({
            "encounter_id":   e["id"],
            "patient_id":     e.get("patient_id"),
            "encounter_date": e.get("encounter_date"),
            "encounter_type": e.get("encounter_type"),
            "diagnoses":      e.get("icd10_codes") or [],
            "total_amount":   b.get("total_amount", 0),
            "hmo_amount":     b.get("hmo_amount", 0),
            "patient_copay":  b.get("patient_amount", 0),
            "billing_status": b.get("status", "pending"),
        })

    return {
        "export_generated_at": _now(),
        "period_start":  start_date,
        "period_end":    end_date,
        "record_count":  len(records),
        "records":       records,
    }


# ---------------------------------------------------------------------------
# Financial Summary
# ---------------------------------------------------------------------------

@router.get("/financial-summary")
async def financial_summary(
    start_date: Optional[str] = Query(None),
    end_date:   Optional[str] = Query(None),
    user=Depends(verify_jwt),
):
    """Revenue breakdown by payer type and billing status."""
    bill_q = db.table(TABLE_BILLING).select(
        "total_amount,hmo_amount,patient_amount,status,created_at"
    )
    if start_date: bill_q = bill_q.gte("created_at", start_date)
    if end_date:   bill_q = bill_q.lte("created_at", end_date)
    bills = bill_q.execute().data or []

    total_rev   = 0.0
    hmo_rev     = 0.0
    patient_rev = 0.0
    by_status: dict = defaultdict(float)
    pending_count   = 0

    for b in bills:
        amt = float(b.get("total_amount") or 0)
        total_rev   += amt
        hmo_rev     += float(b.get("hmo_amount")     or 0)
        patient_rev += float(b.get("patient_amount") or 0)
        st = b.get("status") or "pending"
        by_status[st] += amt
        if st not in ("paid", "waived"):
            pending_count += 1

    pay_q = db.table(TABLE_PAYMENTS).select("amount,payment_method,paid_at")
    if start_date: pay_q = pay_q.gte("paid_at", start_date)
    if end_date:   pay_q = pay_q.lte("paid_at", end_date)
    payments = pay_q.execute().data or []

    by_method: dict  = defaultdict(float)
    total_collected  = 0.0
    for p in payments:
        amt = float(p.get("amount") or 0)
        total_collected += amt
        by_method[p.get("payment_method") or "other"] += amt

    return {
        "period_start": start_date,
        "period_end":   end_date,
        "invoiced": {
            "total":           round(total_rev, 2),
            "hmo_portion":     round(hmo_rev, 2),
            "patient_portion": round(patient_rev, 2),
            "by_status":       {k: round(v, 2) for k, v in by_status.items()},
            "pending_invoices": pending_count,
        },
        "collected": {
            "total":           round(total_collected, 2),
            "by_method":       {k: round(v, 2) for k, v in by_method.items()},
            "collection_rate": round(
                total_collected / total_rev * 100, 1
            ) if total_rev else 0,
        },
    }


# ---------------------------------------------------------------------------
# Patient Demographics
# ---------------------------------------------------------------------------

@router.get("/patient-demographics")
async def patient_demographics(user=Depends(verify_jwt)):
    """Age band + gender distribution of registered patients."""
    patients = db.table(TABLE_PATIENTS).select(
        "date_of_birth,gender"
    ).execute().data or []

    age_bands: dict = defaultdict(int)
    genders: dict   = defaultdict(int)

    for p in patients:
        age_bands[_age_band(p.get("date_of_birth"))] += 1
        genders[str(p.get("gender") or "unknown").lower()] += 1

    return {
        "total_patients": len(patients),
        "by_age_band":    dict(age_bands),
        "by_gender":      dict(genders),
    }


# ---------------------------------------------------------------------------
# Bed Occupancy
# ---------------------------------------------------------------------------

@router.get("/bed-occupancy")
async def bed_occupancy(user=Depends(verify_jwt)):
    """Per-ward bed utilisation snapshot."""
    wards = db.table(TABLE_WARDS).select("id,name,ward_type").execute().data or []
    beds  = db.table(TABLE_BEDS).select("ward_id,status").execute().data  or []

    ward_map = {w["id"]: w for w in wards}
    summary: dict = {}

    for b in beds:
        wid = b.get("ward_id")
        if wid not in summary:
            w = ward_map.get(wid, {})
            summary[wid] = {
                "ward_name": w.get("name", str(wid)),
                "ward_type": w.get("ward_type", "general"),
                "total": 0, "occupied": 0,
            }
        summary[wid]["total"] += 1
        if b.get("status") == "occupied":
            summary[wid]["occupied"] += 1

    result = []
    for entry in summary.values():
        t, o = entry["total"], entry["occupied"]
        result.append({
            **entry,
            "available":      t - o,
            "occupancy_pct":  round(o / t * 100, 1) if t else 0,
        })
    result.sort(key=lambda x: x["occupancy_pct"], reverse=True)

    total_beds     = sum(e["total"] for e in result)
    total_occupied = sum(e["occupied"] for e in result)

    return {
        "overall_occupancy_pct": round(total_occupied / total_beds * 100, 1) if total_beds else 0,
        "total_beds":     total_beds,
        "total_occupied": total_occupied,
        "wards":          result,
    }
