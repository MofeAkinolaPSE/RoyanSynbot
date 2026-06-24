"""PostgreSQL bulk loader for RoyanHealth.

Connects directly to the local Docker PostgreSQL instance via psycopg2.
Uses ON CONFLICT (external_source, external_id) DO UPDATE for safe idempotent
upserts — running the script twice produces the same result.

Also resolves _hope_patient_id references to actual royan_patients.id values,
and creates temporary encounter shells for lab, pharmacy, and billing records
(mirroring the behaviour of hope_sync.py).

Additional functions (Bronze/Gold layer):
  load_operations_events  — upserts to royan_operations_events
  load_to_dlq             — records rejected rows in royan_ingest_dlq
  update_watermark        — upserts the per-entity high-water mark
  get_watermark           — reads the stored watermark for incremental mode
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import psycopg2
import psycopg2.extras

from transformers._helpers import EXTERNAL_SOURCE, safe_str, utcnow

logger = logging.getLogger(__name__)

_MYSQL_ZERO_DATES = {"0000-00-00", "0000-00-00 00:00:00", "0000-00-00T00:00:00"}


def _sanitize_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """Replace MySQL zero/invalid-year dates with None before inserting."""
    out = {}
    for k, v in row.items():
        if isinstance(v, str):
            s = v.strip()
            if s in _MYSQL_ZERO_DATES or s.startswith("0000-"):
                out[k] = None
                continue
        out[k] = v
    return out


# ---------------------------------------------------------------------------
# Connection helper
# ---------------------------------------------------------------------------

def get_conn(database_url: str) -> psycopg2.extensions.connection:
    conn = psycopg2.connect(database_url)
    conn.autocommit = False
    return conn


# ---------------------------------------------------------------------------
# Patient ID / HMO resolution helpers
# ---------------------------------------------------------------------------

def _patient_id_by_external(cur, hope_patient_id: str) -> Optional[int]:
    cur.execute(
        "SELECT id FROM royan_patients WHERE external_source = %s AND external_id = %s LIMIT 1",
        (EXTERNAL_SOURCE, str(hope_patient_id)),
    )
    row = cur.fetchone()
    return row[0] if row else None


def _patient_hmo_info(cur, patient_id: int) -> Tuple[Optional[str], Optional[str]]:
    """Return (hmo_provider, hmo_id) for a royan_patients row by PK."""
    cur.execute(
        "SELECT hmo_provider, hmo_id FROM royan_patients WHERE id = %s LIMIT 1",
        (patient_id,),
    )
    row = cur.fetchone()
    return (row[0], row[1]) if row else (None, None)


# ---------------------------------------------------------------------------
# Ward / bed FK resolution
# ---------------------------------------------------------------------------

def _resolve_ward_and_bed(
    cur,
    ward_name: Optional[str],
    bed_label: Optional[str],
) -> Tuple[Optional[int], Optional[int]]:
    """Look up royan_wards.id and royan_beds.id by name/label (case-insensitive).
    Returns (ward_id, bed_id) — either or both may be None if not found.
    """
    if not ward_name:
        return None, None

    cur.execute(
        "SELECT id FROM royan_wards WHERE lower(name) = lower(%s) LIMIT 1",
        (ward_name,),
    )
    row = cur.fetchone()
    ward_id: Optional[int] = row[0] if row else None

    if not ward_id or not bed_label:
        return ward_id, None

    cur.execute(
        "SELECT id FROM royan_beds WHERE ward_id = %s AND lower(bed_number) = lower(%s) LIMIT 1",
        (ward_id, bed_label),
    )
    row = cur.fetchone()
    bed_id: Optional[int] = row[0] if row else None
    return ward_id, bed_id


# ---------------------------------------------------------------------------
# HMO shell creation
# ---------------------------------------------------------------------------

def _ensure_hmo(cur, name: Optional[str]) -> None:
    if not name:
        return
    cur.execute("SELECT id FROM royan_hmos WHERE lower(name) = lower(%s) LIMIT 1", (name,))
    if cur.fetchone():
        return
    try:
        cur.execute(
            "INSERT INTO royan_hmos (name, notes) VALUES (%s, %s) ON CONFLICT (name) DO NOTHING",
            (name, "Created from Hope bulk import"),
        )
    except Exception:
        logger.debug("Could not create HMO shell: %s", name, exc_info=True)


# ---------------------------------------------------------------------------
# Encounter shell creation (for lab, pharmacy, billing)
# ---------------------------------------------------------------------------

def _ensure_encounter(cur, patient_id: int, encounter_key: str, *, department: str = "OPD") -> Optional[int]:
    cur.execute(
        "SELECT id FROM royan_encounters WHERE external_source = %s AND external_id = %s LIMIT 1",
        (EXTERNAL_SOURCE, encounter_key),
    )
    row = cur.fetchone()
    if row:
        return row[0]
    cur.execute(
        """
        INSERT INTO royan_encounters
            (patient_id, encounter_type, status, department, registered_by,
             external_source, external_id, external_updated_at)
        VALUES (%s, 'outpatient', 'consulting', %s, 'hope_ingest', %s, %s, %s)
        RETURNING id
        """,
        (patient_id, department, EXTERNAL_SOURCE, encounter_key, utcnow()),
    )
    row = cur.fetchone()
    return row[0] if row else None


# ---------------------------------------------------------------------------
# Per-entity loaders
# ---------------------------------------------------------------------------

def _exec_with_savepoint(cur, sql: str, vals: list, label: str = "") -> bool:
    """Execute sql/vals inside a savepoint so a single bad row never aborts the batch.
    Returns True on success, False on any exception (logs a warning)."""
    cur.execute("SAVEPOINT _row_sp")
    try:
        cur.execute(sql, vals)
        cur.execute("RELEASE SAVEPOINT _row_sp")
        return True
    except Exception as exc:
        cur.execute("ROLLBACK TO SAVEPOINT _row_sp")
        cur.execute("RELEASE SAVEPOINT _row_sp")
        logger.warning("Skipped row %s: %s", label, exc)
        return False


def load_patients(conn, rows: List[Dict], dry_run: bool = False) -> Tuple[int, int]:
    if dry_run:
        _print_dry_run("patients", rows)
        return len(rows), 0

    upserted = 0
    with conn.cursor() as cur:
        for row in rows:
            row = _sanitize_row(row)
            _ensure_hmo(cur, row.get("hmo_provider"))
            cols = [c for c in row if not c.startswith("_")]
            vals = [row[c] for c in cols]
            placeholders = ", ".join(["%s"] * len(cols))
            col_names = ", ".join(cols)
            updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c not in ("external_source", "external_id"))
            sql = f"""
                INSERT INTO royan_patients ({col_names})
                VALUES ({placeholders})
                ON CONFLICT (external_source, external_id)
                WHERE external_source IS NOT NULL AND external_id IS NOT NULL
                DO UPDATE SET {updates}
            """
            if _exec_with_savepoint(cur, sql, vals, label=row.get("mrn", "")):
                upserted += 1
    conn.commit()
    return len(rows), upserted


def load_appointments(conn, slot_rows: List[Dict], appt_rows: List[Dict], dry_run: bool = False) -> Tuple[int, int]:
    if dry_run:
        _print_dry_run("appointment_slots", slot_rows)
        _print_dry_run("appointments", appt_rows)
        return len(appt_rows), 0

    upserted = 0
    # slot_id_map: slot external_id → royan_appointment_slots.id
    # Needed because DO NOTHING on duplicate (doctor_name, slot_date, slot_time)
    # means the RETURNING id is empty; we look up existing row instead.
    slot_id_map: Dict[str, int] = {}

    with conn.cursor() as cur:
        # 1. Upsert slots — deduplicate by (doctor_name, slot_date, slot_time)
        for row in slot_rows:
            row = _sanitize_row(row)
            cols = [c for c in row if not c.startswith("_")]
            vals = [row[c] for c in cols]
            placeholders = ", ".join(["%s"] * len(cols))
            col_names = ", ".join(cols)
            ext_id = row.get("external_id")
            doctor = row.get("doctor_name")
            s_date = row.get("slot_date")
            s_time = row.get("slot_time")
            # Skip slots where date is null (MySQL zero-date sanitized to None)
            if not s_date:
                continue
            # Use (doctor_name, slot_date, slot_time) as the dedup key so that
            # Hope's double-bookings collapse into a single slot row.
            sql = f"""
                INSERT INTO royan_appointment_slots ({col_names})
                VALUES ({placeholders})
                ON CONFLICT (doctor_name, slot_date, slot_time) DO NOTHING
            """
            _exec_with_savepoint(cur, sql, vals, label=f"slot:{ext_id}")
            # Resolve slot id (whether just inserted or already existed)
            cur.execute(
                "SELECT id FROM royan_appointment_slots WHERE doctor_name = %s AND slot_date = %s AND slot_time = %s LIMIT 1",
                (doctor, s_date, s_time),
            )
            slot_row = cur.fetchone()
            if slot_row and ext_id:
                slot_id_map[str(ext_id)] = slot_row[0]

        # 2. Upsert appointments (need to resolve slot_id and patient_id)
        for row in appt_rows:
            row = _sanitize_row(row)
            hope_pid = row.get("_hope_patient_id")
            slot_ext_id = row.get("_slot_external_id")
            patient_id = _patient_id_by_external(cur, hope_pid) if hope_pid else None
            if not patient_id:
                continue
            slot_id = slot_id_map.get(str(slot_ext_id)) if slot_ext_id else None
            if not slot_id:
                continue

            clean = {k: v for k, v in row.items() if not k.startswith("_")}
            clean["patient_id"] = patient_id
            clean["slot_id"] = slot_id

            cols = list(clean.keys())
            vals = [clean[c] for c in cols]
            placeholders = ", ".join(["%s"] * len(cols))
            col_names = ", ".join(cols)
            updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c not in ("external_source", "external_id"))
            sql = f"""
                INSERT INTO royan_appointments ({col_names})
                VALUES ({placeholders})
                ON CONFLICT (external_source, external_id)
                WHERE external_source IS NOT NULL AND external_id IS NOT NULL
                DO UPDATE SET {updates}
            """
            if _exec_with_savepoint(cur, sql, vals, label=row.get("external_id", "")):
                upserted += 1

    conn.commit()
    return len(appt_rows), upserted


def load_admissions(conn, rows: List[Dict], dry_run: bool = False) -> Tuple[int, int]:
    if dry_run:
        _print_dry_run("encounters (admissions)", rows)
        return len(rows), 0

    upserted = 0
    with conn.cursor() as cur:
        for row in rows:
            row = _sanitize_row(row)
            hope_pid = row.get("_hope_patient_id")
            patient_id = _patient_id_by_external(cur, hope_pid) if hope_pid else None
            if not patient_id:
                continue

            # Resolve ward/bed names → integer FKs
            ward_id, bed_id = _resolve_ward_and_bed(
                cur,
                row.get("_ward_name"),
                row.get("_bed_label"),
            )

            # Strip all private helper keys; inject resolved FKs
            clean = {k: v for k, v in row.items() if not k.startswith("_")}
            clean["patient_id"] = patient_id
            if ward_id is not None:
                clean["ward_id"] = ward_id
            if bed_id is not None:
                clean["bed_id"] = bed_id

            # diagnosis_codes: pass as Python list — psycopg2 maps it to text[]
            if clean.get("diagnosis_codes") is not None and not isinstance(clean["diagnosis_codes"], list):
                clean["diagnosis_codes"] = list(clean["diagnosis_codes"])

            cols = list(clean.keys())
            vals = [clean[c] for c in cols]
            placeholders = ", ".join(["%s"] * len(cols))
            col_names = ", ".join(cols)
            updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c not in ("external_source", "external_id"))
            sql = f"""
                INSERT INTO royan_encounters ({col_names})
                VALUES ({placeholders})
                ON CONFLICT (external_source, external_id)
                WHERE external_source IS NOT NULL AND external_id IS NOT NULL
                DO UPDATE SET {updates}
            """
            if _exec_with_savepoint(cur, sql, vals, label=row.get("external_id", "")):
                upserted += 1

    conn.commit()
    return len(rows), upserted


def load_lab(conn, rows: List[Dict], dry_run: bool = False) -> Tuple[int, int]:
    if dry_run:
        _print_dry_run("lab_orders", rows)
        return len(rows), 0

    upserted = 0
    with conn.cursor() as cur:
        for row in rows:
            row = _sanitize_row(row)
            hope_pid = row.get("_hope_patient_id")
            enc_key = row.get("_encounter_key")
            patient_id = _patient_id_by_external(cur, hope_pid) if hope_pid else None
            if not patient_id:
                continue
            encounter_id = _ensure_encounter(cur, patient_id, enc_key, department="Laboratory & Diagnostics")
            if not encounter_id:
                continue
            clean = {k: v for k, v in row.items() if not k.startswith("_")}
            clean["patient_id"] = patient_id
            clean["encounter_id"] = encounter_id

            cols = list(clean.keys())
            vals = [clean[c] for c in cols]
            placeholders = ", ".join(["%s"] * len(cols))
            col_names = ", ".join(cols)
            updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c not in ("external_source", "external_id"))
            sql = f"""
                INSERT INTO royan_lab_orders ({col_names})
                VALUES ({placeholders})
                ON CONFLICT (external_source, external_id)
                WHERE external_source IS NOT NULL AND external_id IS NOT NULL
                DO UPDATE SET {updates}
            """
            if _exec_with_savepoint(cur, sql, vals, label=row.get("external_id", "")):
                upserted += 1

    conn.commit()
    return len(rows), upserted


def load_pharmacy(conn, rows: List[Dict], dry_run: bool = False) -> Tuple[int, int]:
    if dry_run:
        _print_dry_run("prescriptions", rows)
        return len(rows), 0

    upserted = 0
    with conn.cursor() as cur:
        for row in rows:
            row = _sanitize_row(row)
            hope_pid = row.get("_hope_patient_id")
            enc_key = row.get("_encounter_key")
            patient_id = _patient_id_by_external(cur, hope_pid) if hope_pid else None
            if not patient_id:
                continue
            encounter_id = _ensure_encounter(cur, patient_id, enc_key, department="Pharmacy")
            if not encounter_id:
                continue
            clean = {k: v for k, v in row.items() if not k.startswith("_")}
            clean["patient_id"] = patient_id
            clean["encounter_id"] = encounter_id

            cols = list(clean.keys())
            vals = [clean[c] for c in cols]
            placeholders = ", ".join(["%s"] * len(cols))
            col_names = ", ".join(cols)
            updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c not in ("external_source", "external_id"))
            sql = f"""
                INSERT INTO royan_prescriptions ({col_names})
                VALUES ({placeholders})
                ON CONFLICT (external_source, external_id)
                WHERE external_source IS NOT NULL AND external_id IS NOT NULL
                DO UPDATE SET {updates}
            """
            if _exec_with_savepoint(cur, sql, vals, label=row.get("external_id", "")):
                upserted += 1

    conn.commit()
    return len(rows), upserted


def load_billing(conn, rows: List[Dict], dry_run: bool = False) -> Tuple[int, int]:
    if dry_run:
        _print_dry_run("billing", rows)
        return len(rows), 0

    upserted = 0
    with conn.cursor() as cur:
        for row in rows:
            row = _sanitize_row(row)
            hope_pid = row.get("_hope_patient_id")
            enc_key = row.get("_encounter_key")
            patient_id = _patient_id_by_external(cur, hope_pid) if hope_pid else None
            if not patient_id:
                continue
            encounter_id = _ensure_encounter(cur, patient_id, enc_key, department="Billing & Finance")
            if not encounter_id:
                continue
            clean = {k: v for k, v in row.items() if not k.startswith("_")}
            clean["patient_id"] = patient_id
            clean["encounter_id"] = encounter_id

            cols = list(clean.keys())
            vals = [clean[c] for c in cols]
            placeholders = ", ".join(["%s"] * len(cols))
            col_names = ", ".join(cols)
            updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c not in ("external_source", "external_id"))
            sql = f"""
                INSERT INTO royan_billing ({col_names})
                VALUES ({placeholders})
                ON CONFLICT (external_source, external_id)
                WHERE external_source IS NOT NULL AND external_id IS NOT NULL
                DO UPDATE SET {updates}
            """
            if _exec_with_savepoint(cur, sql, vals, label=row.get("external_id", "")):
                upserted += 1

    conn.commit()
    return len(rows), upserted


# ---------------------------------------------------------------------------
# Lab results loader (royan_lab_results — no external_source/external_id)
# ---------------------------------------------------------------------------

def load_lab_results(conn, rows: List[Dict], dry_run: bool = False) -> Tuple[int, int]:
    if dry_run:
        _print_dry_run("lab_results", rows)
        return len(rows), 0

    upserted = 0
    with conn.cursor() as cur:
        for row in rows:
            row = _sanitize_row(row)
            hope_pid = row.get("_hope_patient_id")
            lab_ext_id = row.get("_hope_lab_order_ext_id")
            patient_id = _patient_id_by_external(cur, hope_pid) if hope_pid else None
            if not patient_id or not lab_ext_id:
                continue

            # Look up the royan_lab_orders PK
            cur.execute(
                "SELECT id FROM royan_lab_orders WHERE external_source = %s AND external_id = %s LIMIT 1",
                (EXTERNAL_SOURCE, str(lab_ext_id)),
            )
            lab_row = cur.fetchone()
            if not lab_row:
                continue
            lab_order_id = lab_row[0]

            # Skip if a result already exists for this order
            cur.execute(
                "SELECT 1 FROM royan_lab_results WHERE lab_order_id = %s LIMIT 1",
                (lab_order_id,),
            )
            if cur.fetchone():
                continue

            clean = {k: v for k, v in row.items() if not k.startswith("_")}
            clean["lab_order_id"] = lab_order_id
            clean["patient_id"] = patient_id

            # result_data: convert dict → JSON string for psycopg2
            if isinstance(clean.get("result_data"), dict):
                clean["result_data"] = json.dumps(clean["result_data"], default=str)

            cols = list(clean.keys())
            vals = [clean[c] for c in cols]
            placeholders = ", ".join(["%s"] * len(cols))
            col_names = ", ".join(cols)
            sql = f"INSERT INTO royan_lab_results ({col_names}) VALUES ({placeholders})"
            if _exec_with_savepoint(cur, sql, vals, label=f"lab_result:{lab_ext_id}"):
                upserted += 1

            # Mark the lab order as 'resulted'
            cur.execute(
                "UPDATE royan_lab_orders SET status = 'resulted', updated_at = now() WHERE id = %s AND status != 'resulted'",
                (lab_order_id,),
            )

    conn.commit()
    return len(rows), upserted


# ---------------------------------------------------------------------------
# Dispensing loader (royan_dispensing — no external_source/external_id)
# ---------------------------------------------------------------------------

def load_dispensing(conn, rows: List[Dict], dry_run: bool = False) -> Tuple[int, int]:
    if dry_run:
        _print_dry_run("dispensing", rows)
        return len(rows), 0

    upserted = 0
    with conn.cursor() as cur:
        for row in rows:
            row = _sanitize_row(row)
            hope_pid = row.get("_hope_patient_id")
            rx_ext_id = row.get("_hope_rx_ext_id")
            patient_id = _patient_id_by_external(cur, hope_pid) if hope_pid else None
            if not patient_id or not rx_ext_id:
                continue

            cur.execute(
                "SELECT id FROM royan_prescriptions WHERE external_source = %s AND external_id = %s LIMIT 1",
                (EXTERNAL_SOURCE, str(rx_ext_id)),
            )
            rx_row = cur.fetchone()
            if not rx_row:
                continue
            prescription_id = rx_row[0]

            # Skip if dispensing record already exists for this prescription
            cur.execute(
                "SELECT 1 FROM royan_dispensing WHERE prescription_id = %s LIMIT 1",
                (prescription_id,),
            )
            if cur.fetchone():
                continue

            clean = {k: v for k, v in row.items() if not k.startswith("_")}
            clean["prescription_id"] = prescription_id
            clean["patient_id"] = patient_id

            cols = list(clean.keys())
            vals = [clean[c] for c in cols]
            placeholders = ", ".join(["%s"] * len(cols))
            col_names = ", ".join(cols)
            sql = f"INSERT INTO royan_dispensing ({col_names}) VALUES ({placeholders})"
            if _exec_with_savepoint(cur, sql, vals, label=f"dispensing:{rx_ext_id}"):
                upserted += 1

            # Mark the prescription as 'dispensed'
            cur.execute(
                "UPDATE royan_prescriptions SET status = 'dispensed', updated_at = now() WHERE id = %s AND status = 'pending'",
                (prescription_id,),
            )

    conn.commit()
    return len(rows), upserted


# ---------------------------------------------------------------------------
# Payments loader (royan_payments — no external_source/external_id)
# ---------------------------------------------------------------------------

def load_payments(conn, rows: List[Dict], dry_run: bool = False) -> Tuple[int, int]:
    if dry_run:
        _print_dry_run("payments", rows)
        return len(rows), 0

    upserted = 0
    with conn.cursor() as cur:
        for row in rows:
            row = _sanitize_row(row)
            hope_pid = row.get("_hope_patient_id")
            bill_ext_id = row.get("_hope_billing_ext_id")
            patient_id = _patient_id_by_external(cur, hope_pid) if hope_pid else None
            if not patient_id or not bill_ext_id:
                continue

            cur.execute(
                "SELECT id FROM royan_billing WHERE external_source = %s AND external_id = %s LIMIT 1",
                (EXTERNAL_SOURCE, str(bill_ext_id)),
            )
            bill_row = cur.fetchone()
            if not bill_row:
                continue
            billing_id = bill_row[0]

            # Skip if a payment already exists for this billing record
            cur.execute(
                "SELECT 1 FROM royan_payments WHERE billing_id = %s LIMIT 1",
                (billing_id,),
            )
            if cur.fetchone():
                continue

            clean = {k: v for k, v in row.items() if not k.startswith("_")}
            clean["billing_id"] = billing_id
            clean["patient_id"] = patient_id

            cols = list(clean.keys())
            vals = [clean[c] for c in cols]
            placeholders = ", ".join(["%s"] * len(cols))
            col_names = ", ".join(cols)
            sql = f"INSERT INTO royan_payments ({col_names}) VALUES ({placeholders})"
            if _exec_with_savepoint(cur, sql, vals, label=f"payment:{bill_ext_id}"):
                upserted += 1

    conn.commit()
    return len(rows), upserted


# ---------------------------------------------------------------------------
# Insurance claims loader (royan_insurance_claims — no external_source/external_id)
# ---------------------------------------------------------------------------

def load_insurance_claims(conn, rows: List[Dict], dry_run: bool = False) -> Tuple[int, int]:
    if dry_run:
        _print_dry_run("insurance_claims", rows)
        return len(rows), 0

    upserted = 0
    with conn.cursor() as cur:
        for row in rows:
            row = _sanitize_row(row)
            hope_pid = row.get("_hope_patient_id")
            bill_ext_id = row.get("_hope_billing_ext_id")
            patient_id = _patient_id_by_external(cur, hope_pid) if hope_pid else None
            if not patient_id or not bill_ext_id:
                continue

            cur.execute(
                "SELECT id FROM royan_billing WHERE external_source = %s AND external_id = %s LIMIT 1",
                (EXTERNAL_SOURCE, str(bill_ext_id)),
            )
            bill_row = cur.fetchone()
            if not bill_row:
                continue
            billing_id = bill_row[0]

            # Skip if claim already exists for this bill
            cur.execute(
                "SELECT 1 FROM royan_insurance_claims WHERE billing_id = %s LIMIT 1",
                (billing_id,),
            )
            if cur.fetchone():
                continue

            # Enrich hmo_provider / hmo_id from the patient record if not in billing row
            hmo_provider = safe_str(row.get("_hmo_provider_hint"))
            hmo_id_val = safe_str(row.get("_hmo_id_hint"))
            if not hmo_provider or not hmo_id_val:
                p_hmo_provider, p_hmo_id = _patient_hmo_info(cur, patient_id)
                hmo_provider = hmo_provider or p_hmo_provider or "Unknown HMO"
                hmo_id_val = hmo_id_val or p_hmo_id or "UNKNOWN"

            clean = {k: v for k, v in row.items() if not k.startswith("_")}
            clean["billing_id"] = billing_id
            clean["patient_id"] = patient_id
            clean["hmo_provider"] = hmo_provider
            clean["hmo_id"] = hmo_id_val

            cols = list(clean.keys())
            vals = [clean[c] for c in cols]
            placeholders = ", ".join(["%s"] * len(cols))
            col_names = ", ".join(cols)
            sql = f"INSERT INTO royan_insurance_claims ({col_names}) VALUES ({placeholders})"
            if _exec_with_savepoint(cur, sql, vals, label=f"claim:{bill_ext_id}"):
                upserted += 1

    conn.commit()
    return len(rows), upserted


# ---------------------------------------------------------------------------
# Sync run logging
# ---------------------------------------------------------------------------

def log_run(conn, entity: str, rows_seen: int, rows_upserted: int,
            error: Optional[str] = None) -> None:
    status = "failed" if error else "success"
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO royan_hope_sync_runs
                    (entity, status, started_at, completed_at, rows_seen, rows_upserted, error_message, ingest_mode)
                VALUES (%s, %s, %s, %s, %s, %s, %s, 'bulk_import')
                """,
                (entity, status, utcnow(), utcnow(), rows_seen, rows_upserted, error),
            )
        conn.commit()
    except Exception as exc:
        # Table may not exist yet — log and reset the transaction so the
        # caller's connection stays usable for subsequent entities.
        logger.warning("log_run skipped for '%s' (schema missing?): %s", entity, exc)
        try:
            conn.rollback()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Operations events loader (Gold layer)
# ---------------------------------------------------------------------------

def load_operations_events(
    conn,
    rows: List[Dict],
    dry_run: bool = False,
) -> tuple[int, int]:
    """Upsert rows into royan_operations_events."""
    if dry_run:
        _print_dry_run("royan_operations_events", rows)
        return len(rows), 0

    upserted = 0
    with conn.cursor() as cur:
        for row in rows:
            # Strip private helper keys
            clean = {k: v for k, v in row.items() if not k.startswith("_")}
            # Convert metadata dict → JSON string if needed
            if "metadata" in clean and isinstance(clean["metadata"], dict):
                clean["metadata"] = json.dumps(clean["metadata"], default=str)

            cols = list(clean.keys())
            vals = [clean[c] for c in cols]
            placeholders = ", ".join(["%s"] * len(cols))
            col_names = ", ".join(cols)
            updates = ", ".join(
                f"{c} = EXCLUDED.{c}"
                for c in cols
                if c not in ("external_source", "external_id")
            )
            sql = f"""
                INSERT INTO public.royan_operations_events ({col_names})
                VALUES ({placeholders})
                ON CONFLICT (external_source, external_id)
                WHERE external_source IS NOT NULL AND external_id IS NOT NULL
                DO UPDATE SET {updates}
            """
            if _exec_with_savepoint(cur, sql, vals, label=clean.get("external_id", "")):
                upserted += 1
    conn.commit()
    return len(rows), upserted


# ---------------------------------------------------------------------------
# Dead Letter Queue
# ---------------------------------------------------------------------------

def load_to_dlq(
    conn,
    run_id: str,
    entity: str,
    failures: List[Dict],
) -> int:
    """Bulk-insert rejected rows into royan_ingest_dlq. Returns count inserted."""
    if not failures:
        return 0

    records = []
    for f in failures:
        records.append((
            run_id,
            entity,
            f.get("external_id"),
            f.get("source_table"),
            json.dumps(f.get("raw_row", {}), default=str),
            f.get("failure_stage", "contract"),
            str(f.get("failure_reason", ""))[:2000],
            json.dumps(f.get("error_detail", {}), default=str) if f.get("error_detail") else None,
        ))

    with conn.cursor() as cur:
        psycopg2.extras.execute_values(
            cur,
            """
            INSERT INTO public.royan_ingest_dlq
                (run_id, entity, external_id, source_table, raw_row,
                 failure_stage, failure_reason, error_detail)
            VALUES %s
            """,
            records,
        )
    conn.commit()
    return len(records)


# ---------------------------------------------------------------------------
# Watermark tracking (incremental sync)
# ---------------------------------------------------------------------------

def update_watermark(
    conn,
    entity: str,
    run_id: str,
    max_updated_at: Optional[str],
    rows_processed: int,
    mode: str = "full",
) -> None:
    """Upsert the per-entity high-water mark in royan_ingest_watermarks."""
    full_run_col = "full_run_at = now()," if mode == "full" else ""
    incremental_col = "incremental_run_at = now()," if mode == "incremental" else ""
    with conn.cursor() as cur:
        cur.execute(
            f"""
            INSERT INTO public.royan_ingest_watermarks
                (entity, last_run_id, max_external_updated_at, rows_processed,
                 full_run_at, incremental_run_at, updated_at)
            VALUES (%s, %s, %s, %s,
                    {'now()' if mode == 'full' else 'NULL'},
                    {'now()' if mode == 'incremental' else 'NULL'},
                    now())
            ON CONFLICT (entity) DO UPDATE SET
                last_run_id             = EXCLUDED.last_run_id,
                max_external_updated_at = GREATEST(
                    royan_ingest_watermarks.max_external_updated_at,
                    EXCLUDED.max_external_updated_at
                ),
                rows_processed = royan_ingest_watermarks.rows_processed + EXCLUDED.rows_processed,
                {full_run_col}
                {incremental_col}
                updated_at = now()
            """,
            (entity, run_id, max_updated_at, rows_processed),
        )
    conn.commit()


def get_watermark(conn, entity: str) -> Optional[str]:
    """Return the stored max_external_updated_at for *entity*, or None."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT max_external_updated_at FROM public.royan_ingest_watermarks WHERE entity = %s",
            (entity,),
        )
        row = cur.fetchone()
        if row and row[0]:
            return row[0].isoformat() if hasattr(row[0], "isoformat") else str(row[0])
    return None


# ---------------------------------------------------------------------------
# Dry-run helper
# ---------------------------------------------------------------------------

def _print_dry_run(table: str, rows: List[Dict]) -> None:
    print(f"\n  [dry-run] {table}: {len(rows)} rows would be upserted")
    if rows:
        print(f"  Sample: {json.dumps({k: v for k, v in list(rows[0].items())[:6]}, default=str)}")
