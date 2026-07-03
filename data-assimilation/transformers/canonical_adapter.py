"""Canonical Adapter — Chapter 2 of the Implementation Guide.

Transforms raw DRM Hope source records into canonical enterprise business
objects. Every migrated record must pass through one of these adapters
before entering the Silver (operational) layer.

All canonical objects carry:
  source_system     = "hope"
  source_record_id  = the Hope primary key
  migration_batch   = batch reference string

Adapters are pure functions: they take dicts and return dicts.
No DB writes happen here — that responsibility belongs to the loaders.
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

SOURCE_SYSTEM = "hope"


# ─────────────────────────────────────────────────────────────────────────────
# Shared utilities
# ─────────────────────────────────────────────────────────────────────────────

def _str(val: Any) -> Optional[str]:
    """Coerce to string or None."""
    if val is None or val == "":
        return None
    return str(val).strip() or None


def _date(val: Any) -> Optional[str]:
    """Normalise various date formats to ISO-8601 date string (YYYY-MM-DD)."""
    if val is None:
        return None
    if isinstance(val, (date, datetime)):
        return val.isoformat()[:10]
    s = str(val).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y", "%Y/%m/%d", "%d-%b-%Y"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            pass
    logger.debug("Unrecognised date format: %s", val)
    return s or None


def _datetime(val: Any) -> Optional[str]:
    """Normalise to ISO-8601 datetime string."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.isoformat()
    if isinstance(val, date):
        return datetime(val.year, val.month, val.day).isoformat()
    s = str(val).strip()
    for fmt in (
        "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S",
        "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M",
        "%Y-%m-%d", "%d/%m/%Y",
    ):
        try:
            return datetime.strptime(s, fmt).isoformat()
        except ValueError:
            pass
    return s or None


def _float(val: Any) -> Optional[float]:
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _int(val: Any) -> Optional[int]:
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def _gender(val: Any) -> Optional[str]:
    v = str(val or "").strip().lower()[:1]
    return {"m": "male", "f": "female"}.get(v)


def _canonical_meta(source_record_id: Any, migration_batch: str) -> Dict[str, str]:
    return {
        "source_system": SOURCE_SYSTEM,
        "source_record_id": str(source_record_id),
        "migration_batch": migration_batch,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Patient adapter
# ─────────────────────────────────────────────────────────────────────────────

def adapt_patient(hope_row: Dict[str, Any], migration_batch: str) -> Dict[str, Any]:
    """Hope patient record → CanonicalPatient dict (maps to royan_patients columns).

    Hope fields observed: pat_id, file_no (MRN), fname, lname, dob, sex,
    phone, address, blood_group, genotype, email, created_date.
    """
    pid = hope_row.get("pat_id") or hope_row.get("id")
    mrn = _str(hope_row.get("file_no") or hope_row.get("mrn") or hope_row.get("patient_id"))

    record = {
        "mrn": mrn,
        "first_name": _str(hope_row.get("fname") or hope_row.get("first_name")) or "Unknown",
        "last_name":  _str(hope_row.get("lname") or hope_row.get("last_name")) or "Unknown",
        "date_of_birth": _date(hope_row.get("dob") or hope_row.get("date_of_birth")),
        "gender": _gender(hope_row.get("sex") or hope_row.get("gender")),
        "phone":   _str(hope_row.get("phone") or hope_row.get("mobile")),
        "email":   _str(hope_row.get("email")),
        "address": _str(hope_row.get("address") or hope_row.get("home_address")),
        "blood_group": _str(hope_row.get("blood_group") or hope_row.get("blood_grp")),
        "genotype":    _str(hope_row.get("genotype")),
        "created_at":  _datetime(hope_row.get("created_date") or hope_row.get("reg_date")),
        # Source lineage
        **_canonical_meta(pid, migration_batch),
    }

    if not record["mrn"]:
        logger.warning("Patient record without MRN — source_id=%s", pid)

    return record


# ─────────────────────────────────────────────────────────────────────────────
# Encounter adapter
# ─────────────────────────────────────────────────────────────────────────────

_ENCOUNTER_STATUS_MAP = {
    # Hope status codes → Synbot canonical statuses
    "OPD": "consulting",
    "IPD": "admitted",
    "AE":  "consulting",
    "DISCHARGE": "discharged",
    "CLOSED": "discharged",
    "": "patient_registered",
}


def adapt_encounter(
    hope_row: Dict[str, Any],
    migration_batch: str,
    patient_id: Optional[int] = None,
    dept_by_name: Optional[Dict[str, int]] = None,
    staff_by_name: Optional[Dict[str, int]] = None,
) -> Dict[str, Any]:
    """Hope admission/OPD record → CanonicalEncounter dict.

    Hope fields observed: adm_id / visit_id, pat_id, visit_date, doc_name,
    dept_name, diagnosis, discharge_date, type (OPD/IPD/AE).
    """
    eid = hope_row.get("adm_id") or hope_row.get("visit_id") or hope_row.get("id")
    raw_status = _str(hope_row.get("type") or hope_row.get("status") or "")
    canonical_status = _ENCOUNTER_STATUS_MAP.get(
        (raw_status or "").upper(), "patient_registered"
    )

    # Resolve department FK
    raw_dept = _str(hope_row.get("dept_name") or hope_row.get("department"))
    dept_id = None
    if dept_by_name and raw_dept:
        dept_id = dept_by_name.get(raw_dept.lower())

    # Resolve consulting doctor FK
    raw_doctor = _str(hope_row.get("doc_name") or hope_row.get("doctor_name") or hope_row.get("physician"))
    staff_id = None
    if staff_by_name and raw_doctor:
        staff_id = staff_by_name.get(raw_doctor.lower())

    record = {
        "patient_id": patient_id,
        "encounter_type": (raw_status or "outpatient").lower(),
        "status": canonical_status,
        "department": raw_dept,
        "department_id": dept_id,
        "consulting_doctor": raw_doctor,
        "consulting_doctor_id": staff_id,
        "chief_complaint": _str(hope_row.get("complaint") or hope_row.get("presenting_complaint")),
        "diagnosis_notes": _str(hope_row.get("diagnosis") or hope_row.get("working_diagnosis")),
        "triage_at": _datetime(hope_row.get("visit_date") or hope_row.get("adm_date")),
        "discharge_at": _datetime(hope_row.get("discharge_date") or hope_row.get("disc_date")),
        "created_at": _datetime(hope_row.get("visit_date") or hope_row.get("adm_date") or hope_row.get("created_date")),
        **_canonical_meta(eid, migration_batch),
    }

    return record


# ─────────────────────────────────────────────────────────────────────────────
# Laboratory order adapter
# ─────────────────────────────────────────────────────────────────────────────

_LAB_STATUS_MAP = {
    "PENDING":   "pending",
    "COLLECTED": "specimen_collected",
    "PROCESS":   "processing",
    "RESULTED":  "resulted",
    "VERIFIED":  "verified",
    "CANCELLED": "cancelled",
}


def adapt_lab_order(
    hope_row: Dict[str, Any],
    migration_batch: str,
    patient_id: Optional[int] = None,
    encounter_id: Optional[int] = None,
    lab_by_code: Optional[Dict[str, int]] = None,
    staff_by_name: Optional[Dict[str, int]] = None,
) -> Dict[str, Any]:
    """Hope lab order → CanonicalLabOrder dict (maps to royan_lab_orders)."""
    lid = hope_row.get("lab_id") or hope_row.get("order_id") or hope_row.get("id")
    raw_status = (_str(hope_row.get("status") or "") or "PENDING").upper()
    canonical_status = _LAB_STATUS_MAP.get(raw_status, "pending")

    raw_code = _str(hope_row.get("test_code") or hope_row.get("investigation_code") or hope_row.get("code"))
    catalog_id = lab_by_code.get(raw_code) if (lab_by_code and raw_code) else None

    raw_doctor = _str(hope_row.get("doc_name") or hope_row.get("ordered_by") or hope_row.get("physician"))
    requested_by_id = None
    if staff_by_name and raw_doctor:
        requested_by_id = staff_by_name.get(raw_doctor.lower())

    record = {
        "patient_id": patient_id,
        "encounter_id": encounter_id,
        "catalog_id": catalog_id,
        "test_name": _str(
            hope_row.get("investigation") or hope_row.get("test_name") or
            hope_row.get("lab_test") or (raw_code or "Unknown Test")
        ),
        "test_code": raw_code,
        "urgency": "routine",
        "status": canonical_status,
        "sample_type": _str(hope_row.get("sample_type") or hope_row.get("specimen")),
        "requested_by": raw_doctor,
        "requested_by_id": requested_by_id,
        "result_value": _str(hope_row.get("result") or hope_row.get("result_value")),
        "result_summary": _str(hope_row.get("interpretation") or hope_row.get("result_remarks")),
        "is_critical": bool(hope_row.get("is_critical") or hope_row.get("critical_flag")),
        "resulted_at": _datetime(hope_row.get("result_date") or hope_row.get("report_date")),
        "ordered_at": _datetime(
            hope_row.get("order_date") or hope_row.get("request_date") or hope_row.get("created_date")
        ),
        **_canonical_meta(lid, migration_batch),
    }

    return record


# ─────────────────────────────────────────────────────────────────────────────
# Prescription adapter
# ─────────────────────────────────────────────────────────────────────────────

def adapt_prescription(
    hope_row: Dict[str, Any],
    migration_batch: str,
    patient_id: Optional[int] = None,
    encounter_id: Optional[int] = None,
    drug_by_code: Optional[Dict[str, int]] = None,
    drug_by_name: Optional[Dict[str, int]] = None,
    staff_by_name: Optional[Dict[str, int]] = None,
) -> Dict[str, Any]:
    """Hope prescription → CanonicalPrescription dict (maps to royan_prescriptions)."""
    rxid = hope_row.get("rx_id") or hope_row.get("prescription_id") or hope_row.get("id")

    raw_code = _str(hope_row.get("drug_code") or hope_row.get("drug_id"))
    raw_name = _str(hope_row.get("drug_name") or hope_row.get("drug") or hope_row.get("item_name"))
    drug_id = None
    if drug_by_code and raw_code:
        drug_id = drug_by_code.get(raw_code)
    if drug_id is None and drug_by_name and raw_name:
        drug_id = drug_by_name.get(raw_name.lower())

    raw_doctor = _str(hope_row.get("doc_name") or hope_row.get("prescribed_by") or hope_row.get("physician"))
    prescriber_id = None
    if staff_by_name and raw_doctor:
        prescriber_id = staff_by_name.get(raw_doctor.lower())

    record = {
        "patient_id": patient_id,
        "encounter_id": encounter_id,
        "drug_id": drug_id,
        "drug_name": raw_name or "Unknown Drug",
        "drug_code": raw_code,
        "dosage": _str(hope_row.get("dosage") or hope_row.get("dose")),
        "frequency": _str(hope_row.get("frequency") or hope_row.get("freq")),
        "route": _str(hope_row.get("route") or "oral"),
        "quantity": _float(hope_row.get("quantity") or hope_row.get("qty")),
        "duration_days": _int(hope_row.get("duration") or hope_row.get("duration_days")),
        "prescribed_by": raw_doctor,
        "prescribed_by_id": prescriber_id,
        "status": "prescribed",
        "prescribed_at": _datetime(
            hope_row.get("rx_date") or hope_row.get("prescription_date") or hope_row.get("created_date")
        ),
        **_canonical_meta(rxid, migration_batch),
    }

    return record


# ─────────────────────────────────────────────────────────────────────────────
# Billing adapter
# ─────────────────────────────────────────────────────────────────────────────

def adapt_billing(
    hope_row: Dict[str, Any],
    migration_batch: str,
    patient_id: Optional[int] = None,
    encounter_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Hope billing record → CanonicalBillingItem dict (maps to royan_billing)."""
    bid = hope_row.get("bill_id") or hope_row.get("invoice_id") or hope_row.get("id")

    total = _float(hope_row.get("amount") or hope_row.get("total_amount") or hope_row.get("bill_amount")) or 0.0
    paid = _float(hope_row.get("amount_paid") or hope_row.get("paid_amount")) or 0.0
    discount = _float(hope_row.get("discount") or hope_row.get("discount_amount")) or 0.0
    hmo_covered = _float(hope_row.get("hmo_amount") or hope_row.get("insurance_amount")) or 0.0

    record = {
        "patient_id": patient_id,
        "encounter_id": encounter_id,
        "total_amount": total,
        "amount_paid": paid,
        "discount": discount,
        "hmo_covered": hmo_covered,
        "balance_due": round(total - paid - hmo_covered - discount, 2),
        "payment_method": _str(hope_row.get("payment_method") or hope_row.get("pay_method")),
        "payment_status": "paid" if paid >= (total - discount - hmo_covered) and total > 0 else (
            "partial" if paid > 0 else "pending"
        ),
        "invoice_date": _date(hope_row.get("bill_date") or hope_row.get("invoice_date") or hope_row.get("created_date")),
        **_canonical_meta(bid, migration_batch),
    }

    return record


# ─────────────────────────────────────────────────────────────────────────────
# Batch adapters — apply adapters to lists with error isolation
# ─────────────────────────────────────────────────────────────────────────────

def adapt_patients_batch(
    rows: List[Dict[str, Any]],
    migration_batch: str,
) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    for row in rows:
        try:
            results.append(adapt_patient(row, migration_batch))
        except Exception as exc:
            logger.error("Patient adapt failed for row %s: %s", row.get("pat_id"), exc)
    return results


def adapt_encounters_batch(
    rows: List[Dict[str, Any]],
    migration_batch: str,
    patient_id_map: Dict[str, int],
    dept_by_name: Dict[str, int],
    staff_by_name: Dict[str, int],
) -> List[Dict[str, Any]]:
    """patient_id_map: {source_record_id: royan_patients.id}"""
    results: List[Dict[str, Any]] = []
    for row in rows:
        try:
            src_pat_id = str(row.get("pat_id") or row.get("patient_id") or "")
            patient_id = patient_id_map.get(src_pat_id)
            results.append(adapt_encounter(
                row, migration_batch,
                patient_id=patient_id,
                dept_by_name=dept_by_name,
                staff_by_name=staff_by_name,
            ))
        except Exception as exc:
            logger.error("Encounter adapt failed for row %s: %s", row.get("adm_id"), exc)
    return results


def adapt_lab_orders_batch(
    rows: List[Dict[str, Any]],
    migration_batch: str,
    patient_id_map: Dict[str, int],
    encounter_id_map: Dict[str, int],
    lab_by_code: Dict[str, int],
    staff_by_name: Dict[str, int],
) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    for row in rows:
        try:
            src_pid = str(row.get("pat_id") or row.get("patient_id") or "")
            src_eid = str(row.get("adm_id") or row.get("visit_id") or row.get("encounter_id") or "")
            results.append(adapt_lab_order(
                row, migration_batch,
                patient_id=patient_id_map.get(src_pid),
                encounter_id=encounter_id_map.get(src_eid),
                lab_by_code=lab_by_code,
                staff_by_name=staff_by_name,
            ))
        except Exception as exc:
            logger.error("Lab order adapt failed for row %s: %s", row.get("lab_id"), exc)
    return results


def adapt_prescriptions_batch(
    rows: List[Dict[str, Any]],
    migration_batch: str,
    patient_id_map: Dict[str, int],
    encounter_id_map: Dict[str, int],
    drug_by_code: Dict[str, int],
    drug_by_name: Dict[str, int],
    staff_by_name: Dict[str, int],
) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    for row in rows:
        try:
            src_pid = str(row.get("pat_id") or row.get("patient_id") or "")
            src_eid = str(row.get("adm_id") or row.get("visit_id") or row.get("encounter_id") or "")
            results.append(adapt_prescription(
                row, migration_batch,
                patient_id=patient_id_map.get(src_pid),
                encounter_id=encounter_id_map.get(src_eid),
                drug_by_code=drug_by_code,
                drug_by_name=drug_by_name,
                staff_by_name=staff_by_name,
            ))
        except Exception as exc:
            logger.error("Prescription adapt failed for row %s: %s", row.get("rx_id"), exc)
    return results


def adapt_billings_batch(
    rows: List[Dict[str, Any]],
    migration_batch: str,
    patient_id_map: Dict[str, int],
    encounter_id_map: Dict[str, int],
) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    for row in rows:
        try:
            src_pid = str(row.get("pat_id") or row.get("patient_id") or "")
            src_eid = str(row.get("adm_id") or row.get("visit_id") or row.get("encounter_id") or "")
            results.append(adapt_billing(
                row, migration_batch,
                patient_id=patient_id_map.get(src_pid),
                encounter_id=encounter_id_map.get(src_eid),
            ))
        except Exception as exc:
            logger.error("Billing adapt failed for row %s: %s", row.get("bill_id"), exc)
    return results
