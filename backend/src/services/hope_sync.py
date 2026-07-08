"""Read-only Hope bridge synchronization for Synbot Health.

The bridge is treated as an external data source. This module never writes back
to Hope; it only pulls rows, normalizes them, and upserts Synbot-owned records
with external identifiers for idempotency.
"""
from __future__ import annotations

import datetime as dt
import logging
from typing import Any, Callable

import requests

from src.constants import (
    HOPE_BRIDGE_KEY,
    HOPE_BRIDGE_TIMEOUT_SECONDS,
    HOPE_BRIDGE_URL,
    HOSPITAL_DEPARTMENTS,
    TABLE_APPOINTMENT_SLOTS,
    TABLE_APPOINTMENTS,
    TABLE_BILLING,
    TABLE_ENCOUNTERS,
    TABLE_HMOS,
    TABLE_HOPE_SYNC_RUNS,
    TABLE_LAB_ORDERS,
    TABLE_PATIENTS,
    TABLE_PRESCRIPTIONS,
)
from src.db import db

logger = logging.getLogger(__name__)

EXTERNAL_SOURCE = "hope"
SUPPORTED_ENTITIES = {"patients", "appointments", "admissions", "lab", "pharmacy", "billing"}


def _utcnow() -> str:
    return dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _rows(result: Any) -> list[dict[str, Any]]:
    return list(getattr(result, "data", None) or [])


def _first(result: Any) -> dict[str, Any] | None:
    rows = _rows(result)
    return rows[0] if rows else None


def _safe_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _gender(value: Any) -> str | None:
    text = str(value or "").strip().lower()
    if text in {"m", "male"}:
        return "male"
    if text in {"f", "female"}:
        return "female"
    if text in {"other", "prefer_not_to_say"}:
        return text
    return None


def _department(value: Any, fallback: str = "OPD") -> str:
    text = _safe_str(value) or fallback
    return text if text in HOSPITAL_DEPARTMENTS else fallback


def _status(value: Any, allowed: set[str], fallback: str) -> str:
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "pending": "booked",
        "scheduled": "booked",
        "part_paid": "partial",
        "collected": "sample_collected",
        # "active" omitted: falls through to fallback so each entity gets its
        # own correct default (lab→"ordered", billing→"pending", etc.)
    }
    text = aliases.get(text, text)
    return text if text in allowed else fallback


def _upsert(table: str, rows: list[dict[str, Any]], on_conflict: str = "external_source,external_id") -> int:
    if not rows:
        return 0
    try:
        db.table(table).upsert(rows, on_conflict=on_conflict).execute()
    except TypeError:
        db.table(table).upsert(rows).execute()
    return len(rows)


def _fetch_bridge(entity: str, limit: int) -> list[dict[str, Any]]:
    endpoint_map = {
        "patients": "/patients",
        "appointments": "/appointments",
        "admissions": "/admissions",
        "lab": "/lab/orders",
        "pharmacy": "/pharmacy/orders",
        "billing": "/billing",
    }
    endpoint = endpoint_map[entity]
    headers = {"X-Bridge-Key": HOPE_BRIDGE_KEY} if HOPE_BRIDGE_KEY else {}
    response = requests.get(
        f"{HOPE_BRIDGE_URL.rstrip('/')}{endpoint}",
        params={"limit": limit},
        headers=headers,
        timeout=HOPE_BRIDGE_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    payload = response.json()
    return payload if isinstance(payload, list) else list(payload.get("data") or [])


def _generate_mrn() -> str:
    result = db.rpc("generate_mrn", {}).execute()
    if result.data:
        row = result.data[0]
        if isinstance(row, dict):
            return row.get("generate_mrn") or row.get("mrn") or str(row)
        return str(row)
    return f"RH{dt.datetime.utcnow():%Y%m%d%H%M%S}"


def _ensure_hmo(name: str | None) -> None:
    if not name:
        return
    existing = _first(db.table(TABLE_HMOS).select("id").ilike("name", name).limit(1).execute())
    if existing:
        return
    try:
        db.table(TABLE_HMOS).insert({"name": name, "notes": "Created from Hope read-only sync"}).execute()
    except Exception:
        logger.debug("HMO shell already exists or could not be created: %s", name)


def _patient_id_by_external(external_id: str | None) -> int | None:
    if not external_id:
        return None
    row = _first(
        db.table(TABLE_PATIENTS)
        .select("id")
        .eq("external_source", EXTERNAL_SOURCE)
        .eq("external_id", external_id)
        .limit(1)
        .execute()
    )
    return int(row["id"]) if row and row.get("id") is not None else None


def _ensure_external_encounter(patient_id: int, external_id: str, *, encounter_type: str = "outpatient", department: str = "OPD") -> int | None:
    row = _first(
        db.table(TABLE_ENCOUNTERS)
        .select("id")
        .eq("external_source", EXTERNAL_SOURCE)
        .eq("external_id", external_id)
        .limit(1)
        .execute()
    )
    if row:
        return int(row["id"])
    data = {
        "patient_id": patient_id,
        "encounter_type": encounter_type,
        "status": "consulting",
        "department": department,
        "registered_by": "hope_sync",
        "external_source": EXTERNAL_SOURCE,
        "external_id": external_id,
        "external_updated_at": _utcnow(),
    }
    result = db.table(TABLE_ENCOUNTERS).insert(data).execute()
    inserted = _first(result)
    return int(inserted["id"]) if inserted and inserted.get("id") is not None else None


def _sync_patients(rows: list[dict[str, Any]]) -> int:
    normalized: list[dict[str, Any]] = []
    for row in rows:
        external_id = _safe_str(row.get("patient_id") or row.get("id") or row.get("mrn"))
        if not external_id:
            continue
        hmo = _safe_str(row.get("hmo") or row.get("hmo_provider"))
        _ensure_hmo(hmo)
        normalized.append({
            "mrn": _safe_str(row.get("mrn")) or _generate_mrn(),
            "first_name": _safe_str(row.get("first_name")) or "Unknown",
            "last_name": _safe_str(row.get("last_name")) or "Patient",
            "date_of_birth": _safe_str(row.get("dob") or row.get("date_of_birth")),
            "gender": _gender(row.get("gender")),
            "phone": _safe_str(row.get("phone")),
            "blood_group": _safe_str(row.get("blood_group")),
            "hmo_provider": hmo,
            "hmo_id": _safe_str(row.get("hmo_id") or row.get("membership_id")),
            "registered_by": "hope_sync",
            "external_source": EXTERNAL_SOURCE,
            "external_id": external_id,
            "external_updated_at": _safe_str(row.get("updated_at")) or _utcnow(),
        })
    return _upsert(TABLE_PATIENTS, normalized)


def _sync_appointments(rows: list[dict[str, Any]]) -> int:
    upserted = 0
    for row in rows:
        external_id = _safe_str(row.get("appointment_id") or row.get("id"))
        patient_id = _patient_id_by_external(_safe_str(row.get("patient_id")))
        if not external_id or not patient_id:
            continue
        department = _department(row.get("department"))
        slot_data = {
            "doctor_name": _safe_str(row.get("doctor")) or "Unassigned",
            "department": department,
            "slot_date": _safe_str(row.get("slot_date")) or dt.date.today().isoformat(),
            "slot_time": (_safe_str(row.get("slot_time")) or "08:00")[:5],
            "duration_mins": 15,
            "max_patients": 1,
            "is_available": False,
            "external_source": EXTERNAL_SOURCE,
            "external_id": f"{external_id}:slot",
            "external_updated_at": _utcnow(),
        }
        _upsert(TABLE_APPOINTMENT_SLOTS, [slot_data])
        slot = _first(
            db.table(TABLE_APPOINTMENT_SLOTS)
            .select("id")
            .eq("external_source", EXTERNAL_SOURCE)
            .eq("external_id", f"{external_id}:slot")
            .limit(1)
            .execute()
        )
        if not slot:
            continue
        appt = {
            "patient_id": patient_id,
            "slot_id": slot["id"],
            "status": _status(row.get("status"), {"booked", "confirmed", "arrived", "completed", "no_show", "cancelled", "rescheduled"}, "booked"),
            "booked_by": "hope_sync",
            "external_source": EXTERNAL_SOURCE,
            "external_id": external_id,
            "external_updated_at": _utcnow(),
        }
        upserted += _upsert(TABLE_APPOINTMENTS, [appt])
    return upserted


def _sync_admissions(rows: list[dict[str, Any]]) -> int:
    normalized: list[dict[str, Any]] = []
    for row in rows:
        external_id = _safe_str(row.get("admission_id") or row.get("id"))
        patient_id = _patient_id_by_external(_safe_str(row.get("patient_id")))
        if not external_id or not patient_id:
            continue
        normalized.append({
            "patient_id": patient_id,
            "encounter_type": "inpatient",
            "status": "consulting" if not row.get("discharged_at") else "discharged",
            "department": "Inpatient Ward",
            "consulting_doctor": _safe_str(row.get("consultant")),
            "diagnosis_notes": _safe_str(row.get("diagnosis")),
            "registered_by": "hope_sync",
            "external_source": EXTERNAL_SOURCE,
            "external_id": external_id,
            "external_updated_at": _utcnow(),
        })
    return _upsert(TABLE_ENCOUNTERS, normalized)


def _sync_lab(rows: list[dict[str, Any]]) -> int:
    normalized: list[dict[str, Any]] = []
    for row in rows:
        external_id = _safe_str(row.get("order_id") or row.get("id"))
        patient_id = _patient_id_by_external(_safe_str(row.get("patient_id")))
        if not external_id or not patient_id:
            continue
        encounter_id = _ensure_external_encounter(patient_id, f"lab:{external_id}", department="Laboratory & Diagnostics")
        if not encounter_id:
            continue
        test_name = _safe_str(
            row.get("test_name")
            or row.get("test")
            or row.get("investigation")
            or row.get("lab_test")
            or row.get("test_type")
            or row.get("description")
            or row.get("service_name")
            or row.get("item_name")
        )
        normalized.append({
            "encounter_id": encounter_id,
            "patient_id": patient_id,
            "test_name": test_name or "Imported lab order",
            "status": _status(row.get("status") or row.get("labdash_status"), {"ordered", "sample_collected", "processing", "resulted", "cancelled"}, "ordered"),
            "ordered_by": "hope_sync",
            "notes": _safe_str(row.get("result_summary")),
            "external_source": EXTERNAL_SOURCE,
            "external_id": external_id,
            "external_updated_at": _safe_str(row.get("updated_at") or row.get("resulted_at") or row.get("ordered_at")) or _utcnow(),
        })
    return _upsert(TABLE_LAB_ORDERS, normalized)


def _sync_pharmacy(rows: list[dict[str, Any]]) -> int:
    normalized: list[dict[str, Any]] = []
    for row in rows:
        external_id = _safe_str(row.get("order_id") or row.get("id"))
        patient_id = _patient_id_by_external(_safe_str(row.get("patient_id")))
        if not external_id or not patient_id:
            continue
        encounter_id = _ensure_external_encounter(patient_id, f"pharmacy:{external_id}", department="Pharmacy")
        if not encounter_id:
            continue
        normalized.append({
            "encounter_id": encounter_id,
            "patient_id": patient_id,
            "drug_name": _safe_str(row.get("drug") or row.get("drug_name")) or "Imported prescription",
            "dosage": "as directed",
            "frequency": "as directed",
            "quantity": row.get("quantity") or 1,
            "unit": _safe_str(row.get("unit")) or "unit",
            "prescribed_by": "hope_sync",
            "status": _status(row.get("status"), {"pending", "dispensed", "partially_dispensed", "cancelled", "returned"}, "pending"),
            "external_source": EXTERNAL_SOURCE,
            "external_id": external_id,
            "external_updated_at": _safe_str(row.get("updated_at") or row.get("ordered_at")) or _utcnow(),
        })
    return _upsert(TABLE_PRESCRIPTIONS, normalized)


def _sync_billing(rows: list[dict[str, Any]]) -> int:
    normalized: list[dict[str, Any]] = []
    for row in rows:
        external_id = _safe_str(row.get("invoice_id") or row.get("id"))
        patient_id = _patient_id_by_external(_safe_str(row.get("patient_id")))
        if not external_id or not patient_id:
            continue
        encounter_id = _ensure_external_encounter(patient_id, f"billing:{external_id}", department="Billing & Finance")
        if not encounter_id:
            continue
        normalized.append({
            "encounter_id": encounter_id,
            "patient_id": patient_id,
            "bill_number": external_id,
            "miscellaneous": row.get("total_amount") or 0,
            "hmo_covered": row.get("hmo_claim") or 0,
            "status": _status(row.get("status"), {"pending", "partial", "paid", "waived", "disputed", "written_off"}, "pending"),
            "billed_by": "hope_sync",
            "external_source": EXTERNAL_SOURCE,
            "external_id": external_id,
            "external_updated_at": _safe_str(row.get("updated_at") or row.get("created_at")) or _utcnow(),
        })
    return _upsert(TABLE_BILLING, normalized)


SYNC_HANDLERS: dict[str, Callable[[list[dict[str, Any]]], int]] = {
    "patients": _sync_patients,
    "appointments": _sync_appointments,
    "admissions": _sync_admissions,
    "lab": _sync_lab,
    "pharmacy": _sync_pharmacy,
    "billing": _sync_billing,
}


def sync_entity(entity: str, *, limit: int = 200, fetcher: Callable[[str, int], list[dict[str, Any]]] | None = None) -> dict[str, Any]:
    entity = entity.strip().lower()
    if entity not in SUPPORTED_ENTITIES:
        raise ValueError(f"Unsupported Hope sync entity '{entity}'")

    started_at = _utcnow()
    run_row = {
        "entity": entity,
        "status": "started",
        "started_at": started_at,
        "metadata": {"source": EXTERNAL_SOURCE},
    }
    run_id = None
    try:
        inserted = _first(db.table(TABLE_HOPE_SYNC_RUNS).insert(run_row).execute())
        run_id = inserted.get("id") if inserted else None
    except Exception:
        logger.debug("Could not create Hope sync run row", exc_info=True)

    try:
        rows = (fetcher or _fetch_bridge)(entity, limit)
        upserted = SYNC_HANDLERS[entity](rows)
        completed = {
            "status": "success",
            "completed_at": _utcnow(),
            "rows_seen": len(rows),
            "rows_upserted": upserted,
        }
        if run_id:
            db.table(TABLE_HOPE_SYNC_RUNS).update(completed).eq("id", run_id).execute()
        return {"entity": entity, **completed, "run_id": run_id}
    except Exception as exc:
        failed = {
            "status": "failed",
            "completed_at": _utcnow(),
            "error_message": str(exc),
        }
        if run_id:
            try:
                db.table(TABLE_HOPE_SYNC_RUNS).update(failed).eq("id", run_id).execute()
            except Exception:
                pass
        raise
