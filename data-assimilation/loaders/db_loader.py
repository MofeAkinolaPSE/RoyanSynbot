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
from transformers.pharmacy_catalog import INITIAL_BATCH_NUMBER

logger = logging.getLogger(__name__)

_MYSQL_ZERO_DATES = {"0000-00-00", "0000-00-00 00:00:00", "0000-00-00T00:00:00"}


def _sanitize_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """Replace MySQL zero/invalid-year dates with None before inserting, and
    wrap dict/list values for jsonb columns.

    psycopg2 cannot adapt a bare dict -- it raises "can't adapt type 'dict'"
    per row, which silently emptied the entire 499K-row reference archive on
    its first run. Wrapping here rather than in the transformers keeps those
    pure (no psycopg2 dependency) and covers any future jsonb column.
    """
    out = {}
    for k, v in row.items():
        if isinstance(v, str):
            s = v.strip()
            if s in _MYSQL_ZERO_DATES or s.startswith("0000-"):
                out[k] = None
                continue
        elif isinstance(v, (dict, list)):
            out[k] = psycopg2.extras.Json(v)
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


# Long backfills (100K+ rows) commit in chunks rather than once at the end:
# an interrupted run then keeps everything already written instead of losing
# the whole batch, and re-running simply re-upserts (every loader here is
# idempotent on (external_source, external_id)). Learned the hard way -- a
# killed 183K-row vitals run committed nothing.
_COMMIT_EVERY = 5000


def check_yield(label: str, seen: int, upserted: int, *, min_ratio: float = 0.5) -> None:
    """Shout when a load produced far fewer rows than it consumed.

    _exec_with_savepoint deliberately lets one bad row fail without aborting
    the batch -- but that same property turns a SYSTEMATIC failure into a
    silent one, because a per-row guard cannot tell "one malformed record"
    from "every record is malformed". Three loads this session exited 0 with
    a tidy summary and a zero in it:

      * doctor_schedule_blocks   0/749      -- phantom patient_id column
      * reference_archive        0/499,206  -- unadapted dict for jsonb
      * vitals                   0/183,258  -- killed before its only commit

    Call this after a load so the next one announces itself instead of
    hiding in a summary table.
    """
    if seen == 0:
        return
    ratio = upserted / seen
    if upserted == 0:
        logger.error("LOAD YIELDED NOTHING: %s wrote 0 of %d rows -- treat as FAILED, not empty", label, seen)
        print(f"  !! {label}: 0 of {seen:,} rows written -- LOAD FAILED, not empty", flush=True)
    elif ratio < min_ratio:
        logger.warning("Low yield: %s wrote %d of %d rows (%.0f%%)", label, upserted, seen, ratio * 100)
        print(f"  !  {label}: only {upserted:,} of {seen:,} rows written ({ratio*100:.0f}%) -- check why", flush=True)


def _progress_commit(conn, processed: int, total: int, label: str) -> None:
    if processed % _COMMIT_EVERY == 0:
        conn.commit()
        logger.info("%s: %d/%d committed", label, processed, total)
        print(f"    {label}: {processed:,}/{total:,} committed", flush=True)


def _patient_id_map(cur) -> Dict[str, int]:
    """Whole hope-sourced patient external_id -> royan_patients.id map in one
    query. The per-row _patient_id_by_external() lookup is fine for the small
    loaders but costs one round trip per row -- untenable for the 183K-row
    vitals and 419K-row billing backfills. ~61K entries, trivial in memory.
    """
    cur.execute(
        "SELECT external_id, id FROM royan_patients WHERE external_source = %s AND external_id IS NOT NULL",
        (EXTERNAL_SOURCE,),
    )
    return {str(ext_id): pid for ext_id, pid in cur.fetchall()}


def _staff_id_by_external(cur, hope_staff_id: str) -> Optional[str]:
    cur.execute(
        "SELECT id FROM royan_staff WHERE external_source = %s AND external_id = %s LIMIT 1",
        (EXTERNAL_SOURCE, str(hope_staff_id)),
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


def _exec_with_savepoint_rc(cur, sql: str, vals: list, label: str = "") -> Tuple[bool, int]:
    """As _exec_with_savepoint, but also returns how many rows were affected.

    Needed because cur.rowcount read AFTER _exec_with_savepoint reflects the
    RELEASE SAVEPOINT that runs last, not the statement itself -- so counting
    that way reports 0 for work that succeeded. Capturing it between execute
    and release is the only correct point.
    """
    cur.execute("SAVEPOINT _row_sp")
    try:
        cur.execute(sql, vals)
        affected = cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
        cur.execute("RELEASE SAVEPOINT _row_sp")
        return True, affected
    except Exception as exc:
        cur.execute("ROLLBACK TO SAVEPOINT _row_sp")
        cur.execute("RELEASE SAVEPOINT _row_sp")
        logger.warning("Skipped row %s: %s", label, exc)
        return False, 0


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


def load_staff(conn, rows: List[Dict], dry_run: bool = False) -> Tuple[int, int]:
    """royan_staff.id is a UUID (unlike every other bigint-PK table this
    loader handles), generated server-side -- never supplied explicitly.
    Plain (external_source, external_id) upsert, same pattern as patients.
    """
    if dry_run:
        _print_dry_run("staff", rows)
        return len(rows), 0

    upserted = 0
    with conn.cursor() as cur:
        for row in rows:
            row = _sanitize_row(row)
            cols = [c for c in row if not c.startswith("_")]
            vals = [row[c] for c in cols]
            placeholders = ", ".join(["%s"] * len(cols))
            col_names = ", ".join(cols)
            updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c not in ("external_source", "external_id"))
            sql = f"""
                INSERT INTO royan_staff ({col_names})
                VALUES ({placeholders})
                ON CONFLICT (external_source, external_id)
                WHERE external_source IS NOT NULL AND external_id IS NOT NULL
                DO UPDATE SET {updates}
            """
            if _exec_with_savepoint(cur, sql, vals, label=row.get("full_name", "")):
                upserted += 1

    conn.commit()
    return len(rows), upserted


def _patient_id_by_mrn(cur) -> Dict[str, int]:
    """MRN -> royan_patients.id, in one query.

    The insurance chain lands on an MRN (RH16-1030), not on the Hope patient
    external_id that _patient_id_map() keys on, so it needs its own map.
    """
    cur.execute("SELECT mrn, id FROM royan_patients WHERE mrn IS NOT NULL")
    return {str(mrn): pid for mrn, pid in cur.fetchall()}


def _hmo_id_by_external(cur) -> Dict[str, int]:
    """Hope tariff_standard_id -> royan_hmos.id."""
    cur.execute(
        "SELECT external_id, id FROM royan_hmos WHERE external_source = %s AND external_id IS NOT NULL",
        (EXTERNAL_SOURCE,),
    )
    return {str(ext): hid for ext, hid in cur.fetchall()}


def load_patient_insurance(conn, rows: List[Dict], dry_run: bool = False) -> Tuple[int, int]:
    """Hope new_insurances -> royan_patient_insurance.

    The client asked about missing insurance numbers in both staff meetings.
    They were missing because this table had 0 rows, not because the data was
    absent: new_insurances was staged months ago and never loaded.

    Rows arrive already deduplicated to one per (patient, payer) with exactly
    one marked primary per patient -- royan_patient_insurance carries a unique
    index permitting a single primary active policy per patient, and Hope's
    `priority` column is the literal 'P' on all 162,991 rows so it cannot pick
    a winner. See scripts/load_patient_insurance.py for that logic.

    A row whose payer does not resolve is SKIPPED rather than attached to a
    guessed HMO: a membership number filed against the wrong payer is worse
    than one that is absent.
    """
    if dry_run:
        _print_dry_run("patient_insurance", rows)
        return len(rows), 0

    upserted = 0
    skipped_patient = 0
    skipped_payer = 0
    with conn.cursor() as cur:
        pat = _patient_id_by_mrn(cur)
        hmo = _hmo_id_by_external(cur)
        logger.info("resolution maps: %d patients by MRN, %d HMOs by external id", len(pat), len(hmo))

        for i, row in enumerate(rows, 1):
            patient_id = pat.get(str(row.get("mrn")))
            if not patient_id:
                skipped_patient += 1
                continue
            hmo_id = hmo.get(str(row.get("hope_payer_id")))
            if not hmo_id:
                skipped_payer += 1
                continue

            payload = _sanitize_row({
                "patient_id": patient_id,
                "hmo_id": hmo_id,
                "membership_id": row["membership_id"],
                "status": row.get("status", "active"),
                "is_primary": bool(row.get("is_primary")),
                "source": EXTERNAL_SOURCE,
                "notes": row.get("notes"),
                "external_source": EXTERNAL_SOURCE,
                "external_id": row["external_id"],
            })
            cols = list(payload)
            vals = [payload[c] for c in cols]
            placeholders = ", ".join(["%s"] * len(cols))
            updates = ", ".join(
                f"{c} = EXCLUDED.{c}" for c in cols if c not in ("external_source", "external_id")
            )
            sql = f"""
                INSERT INTO royan_patient_insurance ({", ".join(cols)})
                VALUES ({placeholders})
                ON CONFLICT (external_source, external_id) DO UPDATE SET {updates}
            """
            if _exec_with_savepoint(cur, sql, vals, label=row.get("membership_id", "")):
                upserted += 1
            _progress_commit(conn, i, len(rows), "patient_insurance")

    conn.commit()
    if skipped_patient:
        logger.warning("skipped %d rows: MRN not in royan_patients", skipped_patient)
    if skipped_payer:
        logger.warning("skipped %d rows: Hope payer id not in royan_hmos", skipped_payer)
    check_yield("patient_insurance", len(rows), upserted)
    return len(rows), upserted


def load_tariff_pricing(conn, rates: List[Dict], base: List[Dict], dry_run: bool = False) -> Dict[str, int]:
    """Hope tariff grid -> base prices on each catalogue + per-payer rates.

    Targets are polymorphic (see scripts/load_tariff_pricing.py):
      service   -> royan_tariff_catalog.external_id -> royan_service_catalog by name
      lab       -> royan_lab_catalog.external_id
      radiology -> royan_radiology_catalog.external_id

    A rate whose target or payer does not resolve is SKIPPED, never guessed: a
    price filed against the wrong service or the wrong HMO is worse than one
    that is absent, because it looks authoritative.
    """
    out = {"base_lab": 0, "base_radiology": 0, "base_service": 0,
           "rates": 0, "skipped_target": 0, "skipped_payer": 0}
    if dry_run:
        return out

    with conn.cursor() as cur:
        # Hope id -> our catalogue id, per kind.
        cur.execute("SELECT external_id, id FROM royan_lab_catalog WHERE external_source = %s", (EXTERNAL_SOURCE,))
        lab_by_hope = {str(e): i for e, i in cur.fetchall()}
        cur.execute("SELECT external_id, id FROM royan_radiology_catalog WHERE external_id IS NOT NULL")
        rad_by_hope = {str(e): i for e, i in cur.fetchall()}
        # Services reach service_catalog through the tariff catalogue's name.
        cur.execute("SELECT external_id, name FROM royan_tariff_catalog WHERE external_id IS NOT NULL")
        name_by_hope = {str(e): n for e, n in cur.fetchall()}
        cur.execute("SELECT lower(name), id FROM royan_service_catalog")
        svc_by_name = {n: i for n, i in cur.fetchall()}
        svc_by_hope = {
            h: svc_by_name[nm.lower()]
            for h, nm in name_by_hope.items()
            if nm and nm.lower() in svc_by_name
        }
        cur.execute(
            "SELECT external_id, id FROM royan_hmos WHERE external_source = %s AND external_id IS NOT NULL",
            (EXTERNAL_SOURCE,),
        )
        hmo_by_hope = {str(e): i for e, i in cur.fetchall()}

        logger.info(
            "target maps: lab %d, radiology %d, service %d (of %d tariff names) | payers %d",
            len(lab_by_hope), len(rad_by_hope), len(svc_by_hope), len(name_by_hope), len(hmo_by_hope),
        )

        target_map = {"lab": lab_by_hope, "radiology": rad_by_hope, "service": svc_by_hope}
        col_for = {"lab": "lab_catalog_id", "radiology": "radiology_catalog_id", "service": "service_id"}

        # --- base prices onto each catalogue --------------------------------
        for b in base:
            tid = target_map[b["kind"]].get(str(b["hope_target_id"]))
            if not tid:
                continue
            if b["kind"] == "lab":
                sql = "UPDATE royan_lab_catalog SET base_price = %s WHERE id = %s"
            elif b["kind"] == "radiology":
                sql = "UPDATE royan_radiology_catalog SET base_price = %s WHERE id = %s"
            else:
                # Only fill a service price that is missing: migration 197
                # already priced many from the tariff catalogue, and the Private
                # tariff should refine rather than overwrite a curated figure.
                sql = "UPDATE royan_service_catalog SET base_price = %s, updated_at = now() WHERE id = %s AND coalesce(base_price, 0) = 0"
            # Count rows AFFECTED, not statements run. The service UPDATE
            # carries an "only if unpriced" guard, so counting executions
            # reported 312 when the true figure was 0.
            _ok, affected = _exec_with_savepoint_rc(cur, sql, [b["price"], tid], label=b["kind"])
            out["base_" + b["kind"]] += affected

        # --- per-payer rates -------------------------------------------------
        for i, r in enumerate(rates, 1):
            tid = target_map[r["kind"]].get(str(r["hope_target_id"]))
            if not tid:
                out["skipped_target"] += 1
                continue
            hmo_id = hmo_by_hope.get(str(r["hope_payer_id"]))
            if not hmo_id:
                out["skipped_payer"] += 1
                continue
            col = col_for[r["kind"]]
            sql = f"""
                INSERT INTO royan_payer_service_prices (hmo_id, {col}, price, source)
                VALUES (%s, %s, %s, 'tariff_amounts')
                ON CONFLICT (hmo_id, {col}) WHERE {col} IS NOT NULL
                DO UPDATE SET price = EXCLUDED.price, source = EXCLUDED.source, updated_at = now()
            """
            if _exec_with_savepoint(cur, sql, [hmo_id, tid, r["price"]], label=r["kind"]):
                out["rates"] += 1
            _progress_commit(conn, i, len(rates), "tariff_rates")

    conn.commit()
    check_yield("tariff_pricing_rates", len(rates), out["rates"])
    return out


def load_pharmacy_catalog(conn, rows: List[Dict], dry_run: bool = False) -> Tuple[int, int]:
    """royan_drug_formulary (catalog identity) + one royan_inventory_batches
    row per drug carrying its Hope stock snapshot. Two inserts per source
    row, chained by the formulary insert's RETURNING id -- can't reuse the
    single-INSERT _exec_with_savepoint helper here since the batch insert
    depends on the formulary row actually having been created.
    """
    if dry_run:
        _print_dry_run("pharmacy_catalog (formulary + initial batch)", rows)
        return len(rows), 0

    upserted = 0
    with conn.cursor() as cur:
        for row in rows:
            row = _sanitize_row(row)
            stock = row.pop("_stock", None)
            opening_stock = row.pop("_opening_stock", None)
            expiry_date = row.pop("_expiry_date", None)
            received_at = row.pop("_received_at", None)
            row.pop("_supplier_id", None)  # no royan_inventory_batches.supplier_id match target yet

            cols = list(row.keys())
            vals = [row[c] for c in cols]
            placeholders = ", ".join(["%s"] * len(cols))
            col_names = ", ".join(cols)
            updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c not in ("external_source", "external_id"))

            cur.execute("SAVEPOINT _row_sp")
            try:
                cur.execute(
                    f"""
                    INSERT INTO royan_drug_formulary ({col_names})
                    VALUES ({placeholders})
                    ON CONFLICT (external_source, external_id)
                    WHERE external_source IS NOT NULL AND external_id IS NOT NULL
                    DO UPDATE SET {updates}
                    RETURNING id
                    """,
                    vals,
                )
                formulary_id = cur.fetchone()[0]

                qty_on_hand = max(stock or 0, 0)
                qty_received = max(opening_stock or 0, qty_on_hand)
                cur.execute(
                    """
                    INSERT INTO royan_inventory_batches
                        (formulary_id, batch_number, quantity_on_hand, quantity_received,
                         unit_cost, received_at, expiry_date, external_source, external_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (formulary_id, lower(batch_number)) DO UPDATE SET
                        quantity_on_hand = EXCLUDED.quantity_on_hand,
                        quantity_received = EXCLUDED.quantity_received,
                        expiry_date = EXCLUDED.expiry_date
                    """,
                    (formulary_id, INITIAL_BATCH_NUMBER, qty_on_hand, qty_received,
                     row.get("unit_cost") or 0, received_at, expiry_date,
                     EXTERNAL_SOURCE, row.get("external_id")),
                )
                cur.execute("RELEASE SAVEPOINT _row_sp")
                upserted += 1
            except Exception as exc:
                cur.execute("ROLLBACK TO SAVEPOINT _row_sp")
                cur.execute("RELEASE SAVEPOINT _row_sp")
                logger.warning("Skipped pharmacy_catalog row %s: %s", row.get("code"), exc)

    conn.commit()
    return len(rows), upserted


def load_encounter_notes(conn, rows: List[Dict], dry_run: bool = False) -> Tuple[int, int]:
    """royan_encounter_notes from Hope's `notes` table. There is no explicit
    per-note encounter link in the source (see transformers/hope_notes.py
    docstring) -- each note is attached to its patient's encounter whose
    created_at is closest to the note's own timestamp. A note whose patient
    doesn't resolve, or who has zero encounters at all, is skipped rather
    than force-attached to a guess.
    """
    if dry_run:
        _print_dry_run("encounter_notes (hope notes)", rows)
        return len(rows), 0

    upserted = 0
    with conn.cursor() as cur:
        for row in rows:
            row = _sanitize_row(row)
            hope_pid = row.get("_hope_patient_id")
            note_at = row.get("_note_at")
            patient_id = _patient_id_by_external(cur, hope_pid) if hope_pid else None
            if not patient_id or not note_at:
                continue

            cur.execute(
                """
                SELECT id FROM royan_encounters
                WHERE patient_id = %s
                ORDER BY ABS(EXTRACT(EPOCH FROM (created_at - %s::timestamptz)))
                LIMIT 1
                """,
                (patient_id, note_at),
            )
            enc_row = cur.fetchone()
            if not enc_row:
                continue
            encounter_id = enc_row[0]

            clean = {k: v for k, v in row.items() if not k.startswith("_")}
            clean["patient_id"] = patient_id
            clean["encounter_id"] = encounter_id

            cols = list(clean.keys())
            vals = [clean[c] for c in cols]
            placeholders = ", ".join(["%s"] * len(cols))
            col_names = ", ".join(cols)
            updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c not in ("external_source", "external_id"))
            sql = f"""
                INSERT INTO royan_encounter_notes ({col_names})
                VALUES ({placeholders})
                ON CONFLICT (external_source, external_id)
                WHERE external_source IS NOT NULL AND external_id IS NOT NULL
                DO UPDATE SET {updates}
            """
            if _exec_with_savepoint(cur, sql, vals, label=f"note:{clean.get('external_id')}"):
                upserted += 1

    conn.commit()
    return len(rows), upserted


def load_purchase_batches(conn, rows: List[Dict], dry_run: bool = False) -> Tuple[int, int]:
    """Historical batch records (real batch_number/expiry_date, quantity_on_hand
    forced to 0 by the transformer -- see transformers/pharmacy_purchase_batches.py)
    linked to an existing royan_drug_formulary row via the Hope item id.
    Rows whose item_id doesn't resolve to a formulary row already loaded by
    load_pharmacy_catalog.py are skipped -- not every purchase-record item_id
    is in the smaller pharmacy_items catalog used for the formulary load.
    """
    if dry_run:
        _print_dry_run("purchase_batches", rows)
        return len(rows), 0

    upserted = 0
    with conn.cursor() as cur:
        for row in rows:
            row = _sanitize_row(row)
            hope_item_id = row.get("_hope_item_id")
            cur.execute(
                "SELECT id FROM royan_drug_formulary WHERE external_source = %s AND external_id = %s LIMIT 1",
                (EXTERNAL_SOURCE, hope_item_id),
            )
            f_row = cur.fetchone()
            if not f_row:
                continue
            formulary_id = f_row[0]

            clean = {k: v for k, v in row.items() if not k.startswith("_")}
            clean["formulary_id"] = formulary_id

            cols = list(clean.keys())
            vals = [clean[c] for c in cols]
            placeholders = ", ".join(["%s"] * len(cols))
            col_names = ", ".join(cols)
            updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c not in ("external_source", "external_id"))
            sql = f"""
                INSERT INTO royan_inventory_batches ({col_names})
                VALUES ({placeholders})
                ON CONFLICT (external_source, external_id)
                WHERE external_source IS NOT NULL AND external_id IS NOT NULL
                DO UPDATE SET {updates}
            """
            if _exec_with_savepoint(cur, sql, vals, label=f"purchase_batch:{clean.get('external_id')}"):
                upserted += 1

    conn.commit()
    return len(rows), upserted


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


def load_lab_hl7_results(conn, rows: List[Dict], dry_run: bool = False) -> Tuple[int, int]:
    """Real per-analyte lab results from Hope's laboratory_hl7_results table
    (see transformers/lab_hl7_results.py). Unlike load_lab_results (one row
    per order, sourced from the largely-empty laboratory_results shell
    table), this is genuinely N rows per order -- one per analyte in a
    panel -- so it upserts on the row's own external_id (migration 177)
    instead of the one-per-order dedup used there. patient_id has no source
    column on this table at all; it's carried over from the resolved
    parent order.
    """
    if dry_run:
        _print_dry_run("lab_hl7_results", rows)
        return len(rows), 0

    upserted = 0
    with conn.cursor() as cur:
        for row in rows:
            row = _sanitize_row(row)
            lab_ext_id = row.get("_hope_lab_order_ext_id")
            if not lab_ext_id:
                continue

            cur.execute(
                "SELECT id, patient_id FROM royan_lab_orders WHERE external_source = %s AND external_id = %s LIMIT 1",
                (EXTERNAL_SOURCE, str(lab_ext_id)),
            )
            lab_row = cur.fetchone()
            if not lab_row:
                continue
            lab_order_id, patient_id = lab_row

            clean = {k: v for k, v in row.items() if not k.startswith("_")}
            clean["lab_order_id"] = lab_order_id
            clean["patient_id"] = patient_id

            if isinstance(clean.get("result_data"), dict):
                clean["result_data"] = json.dumps(clean["result_data"], default=str)

            cols = list(clean.keys())
            vals = [clean[c] for c in cols]
            placeholders = ", ".join(["%s"] * len(cols))
            col_names = ", ".join(cols)
            updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c not in ("external_source", "external_id"))
            sql = f"""
                INSERT INTO royan_lab_results ({col_names})
                VALUES ({placeholders})
                ON CONFLICT (external_source, external_id)
                WHERE external_source IS NOT NULL AND external_id IS NOT NULL
                DO UPDATE SET {updates}
            """
            if _exec_with_savepoint(cur, sql, vals, label=f"lab_hl7_result:{clean.get('external_id')}"):
                upserted += 1

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
    """royan_dispensing has its own (external_source, external_id) unique
    constraint (one row per Hope pharmacy_sales_bill_details line), so this
    is a normal idempotent upsert -- a prescription legitimately has 1..N
    dispensed lines, unlike the old one-per-prescription design.

    Dispensing lines have no patient_id or timestamp of their own in Hope
    (pharmacy_sales_bill_details is a pure line-item table); both are
    resolved from the parent prescription found via `_hope_rx_ext_id`.
    """
    if dry_run:
        _print_dry_run("dispensing", rows)
        return len(rows), 0

    upserted = 0
    with conn.cursor() as cur:
        for row in rows:
            row = _sanitize_row(row)
            rx_ext_id = row.get("_hope_rx_ext_id")
            if not rx_ext_id:
                continue

            cur.execute(
                "SELECT id, patient_id, prescribed_at FROM royan_prescriptions "
                "WHERE external_source = %s AND external_id = %s LIMIT 1",
                (EXTERNAL_SOURCE, str(rx_ext_id)),
            )
            rx_row = cur.fetchone()
            if not rx_row:
                continue
            prescription_id, patient_id, prescribed_at = rx_row

            formulary_id = None
            hope_item_id = row.get("_hope_item_id")
            if hope_item_id:
                cur.execute(
                    "SELECT id FROM royan_drug_formulary WHERE external_source = %s AND external_id = %s LIMIT 1",
                    (EXTERNAL_SOURCE, hope_item_id),
                )
                f_row = cur.fetchone()
                if f_row:
                    formulary_id = f_row[0]

            clean = {k: v for k, v in row.items() if not k.startswith("_")}
            clean["prescription_id"] = prescription_id
            clean["patient_id"] = patient_id
            clean["dispensed_at"] = prescribed_at or utcnow()
            clean["formulary_id"] = formulary_id

            cols = list(clean.keys())
            vals = [clean[c] for c in cols]
            placeholders = ", ".join(["%s"] * len(cols))
            col_names = ", ".join(cols)
            updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c not in ("external_source", "external_id"))
            sql = f"""
                INSERT INTO royan_dispensing ({col_names})
                VALUES ({placeholders})
                ON CONFLICT (external_source, external_id)
                WHERE external_source IS NOT NULL AND external_id IS NOT NULL
                DO UPDATE SET {updates}
            """
            if _exec_with_savepoint(cur, sql, vals, label=f"dispensing:{clean.get('external_id')}"):
                upserted += 1

            cur.execute(
                "UPDATE royan_prescriptions SET status = 'dispensed', dispensed_at = %s WHERE id = %s AND status = 'pending'",
                (clean["dispensed_at"], prescription_id),
            )

    conn.commit()
    return len(rows), upserted


# ---------------------------------------------------------------------------
# Payments loader (royan_payments — no external_source/external_id)
# ---------------------------------------------------------------------------

def load_payments(conn, rows: List[Dict], dry_run: bool = False) -> Tuple[int, int]:
    """royan_payments has its own (external_source, external_id) unique
    constraint (one row per Hope service_cash_payments record), so this is
    a normal idempotent upsert -- a bill legitimately has 0..N payments,
    unlike the old one-payment-per-bill design. billing_id is nullable, so
    an unresolved bill reference doesn't block recording the payment.
    """
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
            if not patient_id:
                continue

            billing_id = None
            if bill_ext_id:
                cur.execute(
                    "SELECT id FROM royan_billing WHERE external_source = %s AND external_id = %s LIMIT 1",
                    (EXTERNAL_SOURCE, str(bill_ext_id)),
                )
                bill_row = cur.fetchone()
                billing_id = bill_row[0] if bill_row else None

            clean = {k: v for k, v in row.items() if not k.startswith("_")}
            clean["billing_id"] = billing_id
            clean["patient_id"] = patient_id

            cols = list(clean.keys())
            vals = [clean[c] for c in cols]
            placeholders = ", ".join(["%s"] * len(cols))
            col_names = ", ".join(cols)
            updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c not in ("external_source", "external_id"))
            sql = f"""
                INSERT INTO royan_payments ({col_names})
                VALUES ({placeholders})
                ON CONFLICT (external_source, external_id)
                WHERE external_source IS NOT NULL AND external_id IS NOT NULL
                DO UPDATE SET {updates}
            """
            if _exec_with_savepoint(cur, sql, vals, label=f"payment:{clean.get('external_id')}"):
                upserted += 1

    conn.commit()
    return len(rows), upserted


# ---------------------------------------------------------------------------
# Insurance claims loader (royan_insurance_claims — no external_source/external_id)
# ---------------------------------------------------------------------------

def load_insurance_claims(conn, rows: List[Dict], dry_run: bool = False) -> Tuple[int, int]:
    """royan_insurance_claims has its own (external_source, external_id)
    unique constraint, so this is a normal idempotent upsert. Hope's
    `sub_claims` links to an ENCOUNTER (`_hope_encounter_ext_id`), not a
    bill directly -- billing_id is NOT NULL on royan_insurance_claims, so
    the encounter's patient is resolved first, then the most recent bill
    for that patient is used as the claim's billing reference. A patient
    with no billing row at all can't satisfy the NOT NULL FK and is
    skipped (counted via the seen/upserted gap, same as other unresolved
    rows in this loader).
    """
    if dry_run:
        _print_dry_run("insurance_claims", rows)
        return len(rows), 0

    upserted = 0
    with conn.cursor() as cur:
        for row in rows:
            row = _sanitize_row(row)
            hope_enc_id = row.get("_hope_encounter_ext_id")
            if not hope_enc_id:
                continue

            cur.execute(
                "SELECT patient_id FROM royan_encounters WHERE external_source = %s AND external_id = %s LIMIT 1",
                (EXTERNAL_SOURCE, str(hope_enc_id)),
            )
            enc_row = cur.fetchone()
            if not enc_row:
                continue
            patient_id = enc_row[0]

            cur.execute(
                "SELECT id FROM royan_billing WHERE patient_id = %s ORDER BY billed_at DESC LIMIT 1",
                (patient_id,),
            )
            bill_row = cur.fetchone()
            if not bill_row:
                continue  # NOT NULL billing_id -- nothing to attach this claim to
            billing_id = bill_row[0]

            p_hmo_provider, p_hmo_id = _patient_hmo_info(cur, patient_id)
            hmo_provider = p_hmo_provider or "Unknown HMO"
            hmo_id_val = p_hmo_id or "UNKNOWN"

            clean = {k: v for k, v in row.items() if not k.startswith("_")}
            clean["billing_id"] = billing_id
            clean["patient_id"] = patient_id
            clean["hmo_provider"] = hmo_provider
            clean["hmo_id"] = hmo_id_val

            cols = list(clean.keys())
            vals = [clean[c] for c in cols]
            placeholders = ", ".join(["%s"] * len(cols))
            col_names = ", ".join(cols)
            updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c not in ("external_source", "external_id"))
            sql = f"""
                INSERT INTO royan_insurance_claims ({col_names})
                VALUES ({placeholders})
                ON CONFLICT (external_source, external_id)
                WHERE external_source IS NOT NULL AND external_id IS NOT NULL
                DO UPDATE SET {updates}
            """
            if _exec_with_savepoint(cur, sql, vals, label=f"claim:{clean.get('external_id')}"):
                upserted += 1

    conn.commit()
    return len(rows), upserted


def load_hmos(conn, rows: List[Dict], dry_run: bool = False) -> Tuple[int, int]:
    """royan_hmos from Hope's real payer list (tariff_standards -- see
    transformers/hmo.py for why that's the real source, not the table
    literally named "hmo"/"insurance_companies"). Normal idempotent upsert
    on (external_source, external_id); name also has its own UNIQUE
    constraint, so a name collision with a pre-existing (e.g. demo seed)
    row surfaces as a skipped row rather than a hard failure.
    """
    if dry_run:
        _print_dry_run("hmos", rows)
        return len(rows), 0

    upserted = 0
    with conn.cursor() as cur:
        for row in rows:
            row = _sanitize_row(row)
            cols = list(row.keys())
            vals = [row[c] for c in cols]
            placeholders = ", ".join(["%s"] * len(cols))
            col_names = ", ".join(cols)
            updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c not in ("external_source", "external_id"))
            sql = f"""
                INSERT INTO royan_hmos ({col_names})
                VALUES ({placeholders})
                ON CONFLICT (external_source, external_id)
                WHERE external_source IS NOT NULL AND external_id IS NOT NULL
                DO UPDATE SET {updates}
            """
            if _exec_with_savepoint(cur, sql, vals, label=f"hmo:{row.get('name')}"):
                upserted += 1

    conn.commit()
    return len(rows), upserted


def load_patient_hmo_links(conn, rows: List[Dict], dry_run: bool = False) -> Tuple[int, int]:
    """Tags royan_patients.hmo_provider/patient_type from the real
    corporate_patient_details -> corporate_super_bills -> tariff_standards
    chain (see transformers/hmo.py). Plain UPDATE, not an upsert -- there's
    no per-row external_id to conflict on here, this is a patient-level
    attribute, not its own entity. hmo_id (the patient's own membership
    number with that HMO) is deliberately left untouched: Hope's
    corporate_patient_details has no membership-number field, and
    fabricating one would be worse than leaving it null.
    """
    if dry_run:
        _print_dry_run("patient_hmo_links", rows)
        return len(rows), 0

    updated = 0
    with conn.cursor() as cur:
        for row in rows:
            hope_pid = row.get("_hope_patient_id")
            hmo_name = row.get("hmo_name")
            patient_id = _patient_id_by_external(cur, hope_pid) if hope_pid else None
            if not patient_id or not hmo_name:
                continue

            cur.execute(
                "UPDATE royan_patients SET hmo_provider = %s, patient_type = 'hmo' WHERE id = %s",
                (hmo_name, patient_id),
            )
            if cur.rowcount:
                updated += 1

    conn.commit()
    return len(rows), updated


def load_order_sets(conn, rows: List[Dict], dry_run: bool = False) -> Tuple[int, int]:
    """royan_order_sets from Hope's orderset_masters (see
    transformers/order_sets.py for why only 4 of 44 raw rows survive
    filtering). Normal idempotent upsert on (external_source, external_id).
    """
    if dry_run:
        _print_dry_run("order_sets", rows)
        return len(rows), 0

    upserted = 0
    with conn.cursor() as cur:
        for row in rows:
            row = _sanitize_row(row)
            cols = list(row.keys())
            vals = [row[c] for c in cols]
            placeholders = ", ".join(["%s"] * len(cols))
            col_names = ", ".join(cols)
            updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c not in ("external_source", "external_id"))
            sql = f"""
                INSERT INTO royan_order_sets ({col_names})
                VALUES ({placeholders})
                ON CONFLICT (external_source, external_id)
                WHERE external_source IS NOT NULL AND external_id IS NOT NULL
                DO UPDATE SET {updates}
            """
            if _exec_with_savepoint(cur, sql, vals, label=f"order_set:{row.get('name')}"):
                upserted += 1

    conn.commit()
    return len(rows), upserted


def load_order_set_items(conn, rows: List[Dict], dry_run: bool = False) -> Tuple[int, int]:
    """royan_order_set_items -- resolves _hope_master_ext_id to the
    already-loaded royan_order_sets row (load_order_sets must run first),
    then upserts on the item's own (external_source, external_id).
    """
    if dry_run:
        _print_dry_run("order_set_items", rows)
        return len(rows), 0

    upserted = 0
    with conn.cursor() as cur:
        for row in rows:
            row = _sanitize_row(row)
            hope_master_id = row.get("_hope_master_ext_id")
            if not hope_master_id:
                continue

            cur.execute(
                "SELECT id FROM royan_order_sets WHERE external_source = %s AND external_id = %s LIMIT 1",
                (EXTERNAL_SOURCE, hope_master_id),
            )
            master_row = cur.fetchone()
            if not master_row:
                continue
            order_set_id = master_row[0]

            clean = {k: v for k, v in row.items() if not k.startswith("_")}
            clean["order_set_id"] = order_set_id

            cols = list(clean.keys())
            vals = [clean[c] for c in cols]
            placeholders = ", ".join(["%s"] * len(cols))
            col_names = ", ".join(cols)
            updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c not in ("external_source", "external_id"))
            sql = f"""
                INSERT INTO royan_order_set_items ({col_names})
                VALUES ({placeholders})
                ON CONFLICT (external_source, external_id)
                WHERE external_source IS NOT NULL AND external_id IS NOT NULL
                DO UPDATE SET {updates}
            """
            if _exec_with_savepoint(cur, sql, vals, label=f"order_set_item:{clean.get('name')}"):
                upserted += 1

    conn.commit()
    return len(rows), upserted


def load_diagnosis_catalog(conn, rows: List[Dict], dry_run: bool = False) -> Tuple[int, int]:
    """royan_diagnosis_catalog from Hope's diagnosis_masters (see
    transformers/diagnosis_catalog.py). icd_code also carries its own
    UNIQUE(icd_code) constraint from the pre-existing 26-row hand seed;
    Hope's SNOMED-style numeric ids don't collide with that seed's
    dotted ICD-10 codes, but a genuine collision would still correctly
    surface as a skipped row via the savepoint rather than corrupting data.
    """
    if dry_run:
        _print_dry_run("diagnosis_catalog", rows)
        return len(rows), 0

    upserted = 0
    with conn.cursor() as cur:
        for row in rows:
            row = _sanitize_row(row)
            cols = list(row.keys())
            vals = [row[c] for c in cols]
            placeholders = ", ".join(["%s"] * len(cols))
            col_names = ", ".join(cols)
            updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c not in ("external_source", "external_id"))
            sql = f"""
                INSERT INTO royan_diagnosis_catalog ({col_names})
                VALUES ({placeholders})
                ON CONFLICT (external_source, external_id)
                WHERE external_source IS NOT NULL AND external_id IS NOT NULL
                DO UPDATE SET {updates}
            """
            if _exec_with_savepoint(cur, sql, vals, label=f"diagnosis:{row.get('description')}"):
                upserted += 1

    conn.commit()
    return len(rows), upserted


def load_note_templates(conn, rows: List[Dict], dry_run: bool = False) -> Tuple[int, int]:
    """royan_note_templates from Hope's note_templates (system) and
    doctor_templates (personal) -- see transformers/note_templates.py.
    owner_staff_id is resolved from _hope_owner_id when present (personal
    templates); left null for system templates. Normal idempotent upsert.
    """
    if dry_run:
        _print_dry_run("note_templates", rows)
        return len(rows), 0

    upserted = 0
    with conn.cursor() as cur:
        for row in rows:
            row = _sanitize_row(row)
            hope_owner_id = row.get("_hope_owner_id")
            clean = {k: v for k, v in row.items() if not k.startswith("_")}
            clean["owner_staff_id"] = _staff_id_by_external(cur, hope_owner_id) if hope_owner_id else None

            cols = list(clean.keys())
            vals = [clean[c] for c in cols]
            placeholders = ", ".join(["%s"] * len(cols))
            col_names = ", ".join(cols)
            updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c not in ("external_source", "external_id"))
            sql = f"""
                INSERT INTO royan_note_templates ({col_names})
                VALUES ({placeholders})
                ON CONFLICT (external_source, external_id)
                WHERE external_source IS NOT NULL AND external_id IS NOT NULL
                DO UPDATE SET {updates}
            """
            if _exec_with_savepoint(cur, sql, vals, label=f"note_template:{clean.get('name')}"):
                upserted += 1

    conn.commit()
    return len(rows), upserted


def load_note_template_texts(conn, rows: List[Dict], dry_run: bool = False) -> Tuple[int, int]:
    """royan_note_template_texts -- resolves _hope_master_ext_id to the
    already-loaded royan_note_templates row (load_note_templates must run
    first), then upserts on the text row's own (external_source, external_id).
    """
    if dry_run:
        _print_dry_run("note_template_texts", rows)
        return len(rows), 0

    upserted = 0
    with conn.cursor() as cur:
        for row in rows:
            row = _sanitize_row(row)
            hope_master_ext_id = row.get("_hope_master_ext_id")
            if not hope_master_ext_id:
                continue

            cur.execute(
                "SELECT id FROM royan_note_templates WHERE external_source = %s AND external_id = %s LIMIT 1",
                (EXTERNAL_SOURCE, hope_master_ext_id),
            )
            master_row = cur.fetchone()
            if not master_row:
                continue
            template_id = master_row[0]

            clean = {k: v for k, v in row.items() if not k.startswith("_")}
            clean["template_id"] = template_id

            cols = list(clean.keys())
            vals = [clean[c] for c in cols]
            placeholders = ", ".join(["%s"] * len(cols))
            col_names = ", ".join(cols)
            updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c not in ("external_source", "external_id"))
            sql = f"""
                INSERT INTO royan_note_template_texts ({col_names})
                VALUES ({placeholders})
                ON CONFLICT (external_source, external_id)
                WHERE external_source IS NOT NULL AND external_id IS NOT NULL
                DO UPDATE SET {updates}
            """
            if _exec_with_savepoint(cur, sql, vals, label=f"note_template_text:{clean.get('text','')[:30]}"):
                upserted += 1

    conn.commit()
    return len(rows), upserted


def load_radiology_results(conn, rows: List[Dict], dry_run: bool = False) -> Tuple[int, int]:
    """UPDATE-shaped: matches the already-loaded royan_radiology_orders row
    by its existing (external_source, external_id) and populates the
    denormalized report/impression/radiologist_id/reported_at columns (see
    transformers/radiology_results.py -- royan_radiology_results itself is
    confirmed dead, migration 163's own comment). Never inserts a new row.
    """
    if dry_run:
        _print_dry_run("radiology_results", rows)
        return len(rows), 0

    updated = 0
    with conn.cursor() as cur:
        for row in rows:
            row = _sanitize_row(row)
            order_ext_id = row.get("_hope_order_ext_id")
            if not order_ext_id:
                continue

            radiologist_id = None
            hope_radiologist_id = row.get("_hope_radiologist_id")
            if hope_radiologist_id:
                radiologist_id = _staff_id_by_external(cur, hope_radiologist_id)

            cur.execute(
                """
                UPDATE royan_radiology_orders
                SET report = %s, impression = %s, radiologist_id = %s, reported_at = %s
                WHERE external_source = %s AND external_id = %s
                """,
                (row.get("report"), row.get("impression"), radiologist_id, row.get("reported_at"),
                 EXTERNAL_SOURCE, order_ext_id),
            )
            if cur.rowcount:
                updated += 1

    conn.commit()
    return len(rows), updated


def load_radiology_report_templates(conn, rows: List[Dict], dry_run: bool = False) -> Tuple[int, int]:
    """royan_radiology_report_templates from Hope's radiology_templates --
    see transformers/radiology_report_templates.py. Normal idempotent upsert.
    """
    if dry_run:
        _print_dry_run("radiology_report_templates", rows)
        return len(rows), 0

    upserted = 0
    with conn.cursor() as cur:
        for row in rows:
            row = _sanitize_row(row)
            cols = list(row.keys())
            vals = [row[c] for c in cols]
            placeholders = ", ".join(["%s"] * len(cols))
            col_names = ", ".join(cols)
            updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c not in ("external_source", "external_id"))
            sql = f"""
                INSERT INTO royan_radiology_report_templates ({col_names})
                VALUES ({placeholders})
                ON CONFLICT (external_source, external_id)
                WHERE external_source IS NOT NULL AND external_id IS NOT NULL
                DO UPDATE SET {updates}
            """
            if _exec_with_savepoint(cur, sql, vals, label=f"radiology_template:{row.get('section')}"):
                upserted += 1

    conn.commit()
    return len(rows), upserted


def load_radiology_report_template_texts(conn, rows: List[Dict], dry_run: bool = False) -> Tuple[int, int]:
    """royan_radiology_report_template_texts -- resolves _hope_template_ext_id
    to the already-loaded royan_radiology_report_templates row (
    load_radiology_report_templates must run first), then upserts on the
    text row's own (external_source, external_id).
    """
    if dry_run:
        _print_dry_run("radiology_report_template_texts", rows)
        return len(rows), 0

    upserted = 0
    with conn.cursor() as cur:
        for row in rows:
            row = _sanitize_row(row)
            hope_template_id = row.get("_hope_template_ext_id")
            if not hope_template_id:
                continue

            cur.execute(
                "SELECT id FROM royan_radiology_report_templates WHERE external_source = %s AND external_id = %s LIMIT 1",
                (EXTERNAL_SOURCE, hope_template_id),
            )
            template_row = cur.fetchone()
            if not template_row:
                continue
            template_id = template_row[0]

            clean = {k: v for k, v in row.items() if not k.startswith("_")}
            clean["template_id"] = template_id

            cols = list(clean.keys())
            vals = [clean[c] for c in cols]
            placeholders = ", ".join(["%s"] * len(cols))
            col_names = ", ".join(cols)
            updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c not in ("external_source", "external_id"))
            sql = f"""
                INSERT INTO royan_radiology_report_template_texts ({col_names})
                VALUES ({placeholders})
                ON CONFLICT (external_source, external_id)
                WHERE external_source IS NOT NULL AND external_id IS NOT NULL
                DO UPDATE SET {updates}
            """
            if _exec_with_savepoint(cur, sql, vals, label=f"radiology_template_text:{clean.get('text','')[:30]}"):
                upserted += 1

    conn.commit()
    return len(rows), upserted


def load_discharge_records(conn, rows: List[Dict], dry_run: bool = False) -> Tuple[int, int]:
    """royan_discharge_records from Hope's discharge_details (see
    transformers/discharge_records.py). No explicit encounter link in the
    source -- same nearest-created_at-timestamp resolution as
    load_encounter_notes. encounter_id has its own UNIQUE constraint (one
    discharge record per encounter); a second discharge event resolving to
    an already-recorded encounter is safely skipped via the savepoint
    rather than corrupting the first one.
    """
    if dry_run:
        _print_dry_run("discharge_records", rows)
        return len(rows), 0

    upserted = 0
    with conn.cursor() as cur:
        for row in rows:
            row = _sanitize_row(row)
            hope_pid = row.get("_hope_patient_id")
            discharge_at = row.get("_discharge_at")
            patient_id = _patient_id_by_external(cur, hope_pid) if hope_pid else None
            if not patient_id or not discharge_at:
                continue

            cur.execute(
                """
                SELECT id FROM royan_encounters
                WHERE patient_id = %s
                ORDER BY ABS(EXTRACT(EPOCH FROM (created_at - %s::timestamptz)))
                LIMIT 1
                """,
                (patient_id, discharge_at),
            )
            enc_row = cur.fetchone()
            if not enc_row:
                continue
            encounter_id = enc_row[0]

            clean = {k: v for k, v in row.items() if not k.startswith("_")}
            clean["patient_id"] = patient_id
            clean["encounter_id"] = encounter_id

            cols = list(clean.keys())
            vals = [clean[c] for c in cols]
            placeholders = ", ".join(["%s"] * len(cols))
            col_names = ", ".join(cols)
            updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c not in ("external_source", "external_id"))
            sql = f"""
                INSERT INTO royan_discharge_records ({col_names})
                VALUES ({placeholders})
                ON CONFLICT (external_source, external_id)
                WHERE external_source IS NOT NULL AND external_id IS NOT NULL
                DO UPDATE SET {updates}
            """
            if _exec_with_savepoint(cur, sql, vals, label=f"discharge:{clean.get('external_id')}"):
                upserted += 1

    conn.commit()
    return len(rows), upserted


def load_allergen_catalog(conn, rows: List[Dict], dry_run: bool = False) -> Tuple[int, int]:
    """royan_allergen_catalog from Hope's allergy_masters (see
    transformers/allergen_catalog.py). Normal idempotent upsert.
    """
    if dry_run:
        _print_dry_run("allergen_catalog", rows)
        return len(rows), 0

    upserted = 0
    with conn.cursor() as cur:
        for row in rows:
            row = _sanitize_row(row)
            cols = list(row.keys())
            vals = [row[c] for c in cols]
            placeholders = ", ".join(["%s"] * len(cols))
            col_names = ", ".join(cols)
            updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c not in ("external_source", "external_id"))
            sql = f"""
                INSERT INTO royan_allergen_catalog ({col_names})
                VALUES ({placeholders})
                ON CONFLICT (external_source, external_id)
                WHERE external_source IS NOT NULL AND external_id IS NOT NULL
                DO UPDATE SET {updates}
            """
            if _exec_with_savepoint(cur, sql, vals, label=f"allergen:{row.get('name')}"):
                upserted += 1

    conn.commit()
    return len(rows), upserted


def load_exam_templates(conn, rows: List[Dict], dry_run: bool = False) -> Tuple[int, int]:
    """royan_exam_templates from Hope's templates (organ-system rows) --
    see transformers/exam_templates.py. Normal idempotent upsert.
    """
    if dry_run:
        _print_dry_run("exam_templates", rows)
        return len(rows), 0

    upserted = 0
    with conn.cursor() as cur:
        for row in rows:
            row = _sanitize_row(row)
            cols = list(row.keys())
            vals = [row[c] for c in cols]
            placeholders = ", ".join(["%s"] * len(cols))
            col_names = ", ".join(cols)
            updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c not in ("external_source", "external_id"))
            sql = f"""
                INSERT INTO royan_exam_templates ({col_names})
                VALUES ({placeholders})
                ON CONFLICT (external_source, external_id)
                WHERE external_source IS NOT NULL AND external_id IS NOT NULL
                DO UPDATE SET {updates}
            """
            if _exec_with_savepoint(cur, sql, vals, label=f"exam_template:{row.get('organ_system')}"):
                upserted += 1

    conn.commit()
    return len(rows), upserted


def load_exam_template_findings(conn, rows: List[Dict], dry_run: bool = False) -> Tuple[int, int]:
    """royan_exam_template_findings -- resolves _hope_template_ext_id to the
    already-loaded royan_exam_templates row (load_exam_templates must run
    first), then upserts on the finding's own (external_source, external_id).
    """
    if dry_run:
        _print_dry_run("exam_template_findings", rows)
        return len(rows), 0

    upserted = 0
    with conn.cursor() as cur:
        for row in rows:
            row = _sanitize_row(row)
            hope_template_id = row.get("_hope_template_ext_id")
            if not hope_template_id:
                continue

            cur.execute(
                "SELECT id FROM royan_exam_templates WHERE external_source = %s AND external_id = %s LIMIT 1",
                (EXTERNAL_SOURCE, hope_template_id),
            )
            template_row = cur.fetchone()
            if not template_row:
                continue
            exam_template_id = template_row[0]

            clean = {k: v for k, v in row.items() if not k.startswith("_")}
            clean["exam_template_id"] = exam_template_id

            cols = list(clean.keys())
            vals = [clean[c] for c in cols]
            placeholders = ", ".join(["%s"] * len(cols))
            col_names = ", ".join(cols)
            updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c not in ("external_source", "external_id"))
            sql = f"""
                INSERT INTO royan_exam_template_findings ({col_names})
                VALUES ({placeholders})
                ON CONFLICT (external_source, external_id)
                WHERE external_source IS NOT NULL AND external_id IS NOT NULL
                DO UPDATE SET {updates}
            """
            if _exec_with_savepoint(cur, sql, vals, label=f"exam_finding:{clean.get('finding')}"):
                upserted += 1

    conn.commit()
    return len(rows), upserted


def load_lab_catalog(conn, rows: List[Dict], dry_run: bool = False) -> Tuple[int, int]:
    """royan_lab_catalog from Hope's laboratories (see
    transformers/lab_catalog.py). Normal idempotent upsert. `code` is
    globally UNIQUE (not scoped to external_source) -- a rare collision
    against the 20 hand-seeded rows is skipped via the savepoint, not fatal.
    """
    if dry_run:
        _print_dry_run("lab_catalog", rows)
        return len(rows), 0

    upserted = 0
    with conn.cursor() as cur:
        for row in rows:
            row = _sanitize_row(row)
            cols = list(row.keys())
            vals = [row[c] for c in cols]
            placeholders = ", ".join(["%s"] * len(cols))
            col_names = ", ".join(cols)
            updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c not in ("external_source", "external_id"))
            sql = f"""
                INSERT INTO royan_lab_catalog ({col_names})
                VALUES ({placeholders})
                ON CONFLICT (external_source, external_id)
                WHERE external_source IS NOT NULL AND external_id IS NOT NULL
                DO UPDATE SET {updates}
            """
            if _exec_with_savepoint(cur, sql, vals, label=f"lab_catalog:{row.get('name')}"):
                upserted += 1

    conn.commit()
    return len(rows), upserted


def load_generic(
    conn,
    table: str,
    rows: List[Dict],
    dry_run: bool = False,
    *,
    require_patient: bool = True,
) -> Tuple[int, int]:
    """Generic idempotent upsert for the Phase A3 ("finish the job") tables.

    Ten near-identical per-table loaders would have been ten copies of the
    same twenty lines, so the shared resolution steps live here instead.
    Handles whichever underscore-prefixed hints a payload carries:

      _hope_patient_id  -> royan_patients.id  (bulk map, one query)
      _hope_patient_mrn -> royan_patients.id  via mrn (patient_cards' route,
                           since Hope keys those on person_id -- see
                           transformers/accounting_ledger.py)
      _hope_item_id     -> royan_drug_formulary.id
      _hope_doctor_id   -> royan_staff.id

    require_patient=False keeps rows whose patient doesn't resolve (ledger
    rows are still meaningful without a patient link); True skips them.
    """
    if dry_run:
        _print_dry_run(table, rows)
        return len(rows), 0

    upserted = 0
    with conn.cursor() as cur:
        # Only emit columns the target table actually has. Without this the
        # resolution steps below would blindly add patient_id/formulary_id/
        # staff_id to every table -- which silently killed all 749
        # royan_doctor_schedule_blocks rows (no patient_id column) on the
        # first A3 run.
        cur.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = %s",
            (table,),
        )
        table_cols = {r[0] for r in cur.fetchall()}
        if not table_cols:
            raise ValueError(f"{table} does not exist or has no columns")

        pid_map = _patient_id_map(cur)

        mrn_map: Dict[str, int] = {}
        if any(r.get("_hope_patient_mrn") for r in rows[:1000]):
            cur.execute("SELECT mrn, id FROM royan_patients WHERE mrn IS NOT NULL")
            mrn_map = {str(m): i for m, i in cur.fetchall()}

        formulary_map: Dict[str, int] = {}
        if any(r.get("_hope_item_id") for r in rows[:1000]):
            cur.execute(
                "SELECT external_id, id FROM royan_drug_formulary WHERE external_source = %s",
                (EXTERNAL_SOURCE,),
            )
            formulary_map = {str(e): i for e, i in cur.fetchall()}

        staff_map: Dict[str, str] = {}
        if any(r.get("_hope_doctor_id") for r in rows[:1000]):
            cur.execute(
                "SELECT external_id, id FROM royan_staff WHERE external_source = %s",
                (EXTERNAL_SOURCE,),
            )
            staff_map = {str(e): i for e, i in cur.fetchall()}

        for idx, row in enumerate(rows, 1):
            row = _sanitize_row(row)

            patient_id = None
            if row.get("_hope_patient_id"):
                patient_id = pid_map.get(str(row["_hope_patient_id"]))
            elif row.get("_hope_patient_mrn"):
                patient_id = mrn_map.get(str(row["_hope_patient_mrn"]))
            if require_patient and not patient_id:
                continue

            clean = {k: v for k, v in row.items() if not k.startswith("_")}
            if "patient_id" in table_cols:
                clean["patient_id"] = patient_id
            if row.get("_hope_item_id") and formulary_map and "formulary_id" in table_cols:
                clean["formulary_id"] = formulary_map.get(str(row["_hope_item_id"]))
            if row.get("_hope_doctor_id") and staff_map and "staff_id" in table_cols:
                clean["staff_id"] = staff_map.get(str(row["_hope_doctor_id"]))

            clean = {k: v for k, v in clean.items() if k in table_cols}

            cols = list(clean.keys())
            vals = [clean[c] for c in cols]
            placeholders = ", ".join(["%s"] * len(cols))
            col_names = ", ".join(cols)
            updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c not in ("external_source", "external_id"))
            sql = f"""
                INSERT INTO {table} ({col_names})
                VALUES ({placeholders})
                ON CONFLICT (external_source, external_id)
                WHERE external_source IS NOT NULL AND external_id IS NOT NULL
                DO UPDATE SET {updates}
            """
            if _exec_with_savepoint(cur, sql, vals, label=f"{table}:{clean.get('external_id')}"):
                upserted += 1
            _progress_commit(conn, idx, len(rows), table)

    conn.commit()
    return len(rows), upserted


def load_billing_transactions(conn, rows: List[Dict], dry_run: bool = False) -> Tuple[int, int]:
    """royan_billing_transactions from Hope's billings (see
    transformers/billing_archive.py). Supplement archive, not linked to
    royan_billing. patient_id only (no encounter resolution).
    """
    if dry_run:
        _print_dry_run("billing_transactions", rows)
        return len(rows), 0

    upserted = 0
    with conn.cursor() as cur:
        pid_map = _patient_id_map(cur)
        for idx, row in enumerate(rows, 1):
            row = _sanitize_row(row)
            hope_pid = row.get("_hope_patient_id")
            patient_id = pid_map.get(str(hope_pid)) if hope_pid else None
            if not patient_id:
                continue

            clean = {k: v for k, v in row.items() if not k.startswith("_")}
            clean["patient_id"] = patient_id

            cols = list(clean.keys())
            vals = [clean[c] for c in cols]
            placeholders = ", ".join(["%s"] * len(cols))
            col_names = ", ".join(cols)
            updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c not in ("external_source", "external_id"))
            sql = f"""
                INSERT INTO royan_billing_transactions ({col_names})
                VALUES ({placeholders})
                ON CONFLICT (external_source, external_id)
                WHERE external_source IS NOT NULL AND external_id IS NOT NULL
                DO UPDATE SET {updates}
            """
            if _exec_with_savepoint(cur, sql, vals, label=f"billing_txn:{clean.get('external_id')}"):
                upserted += 1
            _progress_commit(conn, idx, len(rows), "billing_transactions")

    conn.commit()
    return len(rows), upserted


def load_billing_summaries(conn, rows: List[Dict], dry_run: bool = False) -> Tuple[int, int]:
    """royan_billing_summaries from Hope's final_billings (see
    transformers/billing_archive.py). Supplement archive, not linked to
    royan_billing. patient_id only (no encounter resolution).
    """
    if dry_run:
        _print_dry_run("billing_summaries", rows)
        return len(rows), 0

    upserted = 0
    with conn.cursor() as cur:
        pid_map = _patient_id_map(cur)
        for idx, row in enumerate(rows, 1):
            row = _sanitize_row(row)
            hope_pid = row.get("_hope_patient_id")
            patient_id = pid_map.get(str(hope_pid)) if hope_pid else None
            if not patient_id:
                continue

            clean = {k: v for k, v in row.items() if not k.startswith("_")}
            clean["patient_id"] = patient_id

            cols = list(clean.keys())
            vals = [clean[c] for c in cols]
            placeholders = ", ".join(["%s"] * len(cols))
            col_names = ", ".join(cols)
            updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c not in ("external_source", "external_id"))
            sql = f"""
                INSERT INTO royan_billing_summaries ({col_names})
                VALUES ({placeholders})
                ON CONFLICT (external_source, external_id)
                WHERE external_source IS NOT NULL AND external_id IS NOT NULL
                DO UPDATE SET {updates}
            """
            if _exec_with_savepoint(cur, sql, vals, label=f"billing_summary:{clean.get('external_id')}"):
                upserted += 1
            _progress_commit(conn, idx, len(rows), "billing_summaries")

    conn.commit()
    return len(rows), upserted


def load_vitals(conn, rows: List[Dict], dry_run: bool = False) -> Tuple[int, int]:
    """royan_vitals from Hope's bmi_results + bmi_bp_results (see
    transformers/vitals.py). encounter_id is nullable on the live table --
    resolved via nearest-timestamp when possible, left null otherwise
    (patient_id is the only hard requirement).
    """
    if dry_run:
        _print_dry_run("vitals", rows)
        return len(rows), 0

    upserted = 0
    with conn.cursor() as cur:
        pid_map = _patient_id_map(cur)
        for idx, row in enumerate(rows, 1):
            row = _sanitize_row(row)
            hope_pid = row.get("_hope_patient_id")
            recorded_at = row.get("_recorded_at")
            patient_id = pid_map.get(str(hope_pid)) if hope_pid else None
            if not patient_id:
                continue

            encounter_id = None
            if recorded_at:
                cur.execute(
                    """
                    SELECT id FROM royan_encounters
                    WHERE patient_id = %s
                    ORDER BY ABS(EXTRACT(EPOCH FROM (created_at - %s::timestamptz)))
                    LIMIT 1
                    """,
                    (patient_id, recorded_at),
                )
                enc_row = cur.fetchone()
                encounter_id = enc_row[0] if enc_row else None

            clean = {k: v for k, v in row.items() if not k.startswith("_")}
            clean["patient_id"] = patient_id
            clean["encounter_id"] = encounter_id

            cols = list(clean.keys())
            vals = [clean[c] for c in cols]
            placeholders = ", ".join(["%s"] * len(cols))
            col_names = ", ".join(cols)
            updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c not in ("external_source", "external_id"))
            sql = f"""
                INSERT INTO royan_vitals ({col_names})
                VALUES ({placeholders})
                ON CONFLICT (external_source, external_id)
                WHERE external_source IS NOT NULL AND external_id IS NOT NULL
                DO UPDATE SET {updates}
            """
            if _exec_with_savepoint(cur, sql, vals, label=f"vitals:{clean.get('external_id')}"):
                upserted += 1
            _progress_commit(conn, idx, len(rows), "vitals")

    conn.commit()
    return len(rows), upserted


def load_ward_stay_history(conn, rows: List[Dict], dry_run: bool = False) -> Tuple[int, int]:
    """royan_ward_stay_history from Hope's ward_patients (see
    transformers/ward_stay_history.py). ward_id resolved by case-insensitive
    name match against the live (small, manually-curated) royan_wards --
    left null (ward_name text still populated) when no match is found.
    """
    if dry_run:
        _print_dry_run("ward_stay_history", rows)
        return len(rows), 0

    upserted = 0
    with conn.cursor() as cur:
        for row in rows:
            row = _sanitize_row(row)
            hope_pid = row.get("_hope_patient_id")
            patient_id = _patient_id_by_external(cur, hope_pid) if hope_pid else None
            if not patient_id:
                continue

            ward_name = row.get("_ward_name")
            ward_id = None
            if ward_name:
                cur.execute("SELECT id FROM royan_wards WHERE lower(name) = lower(%s) LIMIT 1", (ward_name,))
                w_row = cur.fetchone()
                ward_id = w_row[0] if w_row else None

            clean = {k: v for k, v in row.items() if not k.startswith("_")}
            clean["patient_id"] = patient_id
            clean["ward_id"] = ward_id

            cols = list(clean.keys())
            vals = [clean[c] for c in cols]
            placeholders = ", ".join(["%s"] * len(cols))
            col_names = ", ".join(cols)
            updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c not in ("external_source", "external_id"))
            sql = f"""
                INSERT INTO royan_ward_stay_history ({col_names})
                VALUES ({placeholders})
                ON CONFLICT (external_source, external_id)
                WHERE external_source IS NOT NULL AND external_id IS NOT NULL
                DO UPDATE SET {updates}
            """
            if _exec_with_savepoint(cur, sql, vals, label=f"ward_stay:{clean.get('external_id')}"):
                upserted += 1

    conn.commit()
    return len(rows), upserted


def load_tariff_catalog(conn, rows: List[Dict], dry_run: bool = False) -> Tuple[int, int]:
    """royan_tariff_catalog from Hope's tariff_lists + tariff_amounts (see
    transformers/tariff_catalog.py). Normal idempotent upsert.
    """
    if dry_run:
        _print_dry_run("tariff_catalog", rows)
        return len(rows), 0

    upserted = 0
    with conn.cursor() as cur:
        for row in rows:
            row = _sanitize_row(row)
            cols = list(row.keys())
            vals = [row[c] for c in cols]
            placeholders = ", ".join(["%s"] * len(cols))
            col_names = ", ".join(cols)
            updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c not in ("external_source", "external_id"))
            sql = f"""
                INSERT INTO royan_tariff_catalog ({col_names})
                VALUES ({placeholders})
                ON CONFLICT (external_source, external_id)
                WHERE external_source IS NOT NULL AND external_id IS NOT NULL
                DO UPDATE SET {updates}
            """
            if _exec_with_savepoint(cur, sql, vals, label=f"tariff:{row.get('name')}"):
                upserted += 1

    conn.commit()
    return len(rows), upserted


def load_immunisation(conn, rows: List[Dict], dry_run: bool = False) -> Tuple[int, int]:
    """royan_immunisation from Hope's imunizations (see
    transformers/immunisation.py). Resolves _hope_patient_id via the
    canonical remap already applied by the caller. No encounter link
    required (royan_immunisation.patient_id only).
    """
    if dry_run:
        _print_dry_run("immunisation", rows)
        return len(rows), 0

    upserted = 0
    with conn.cursor() as cur:
        for row in rows:
            row = _sanitize_row(row)
            hope_pid = row.get("_hope_patient_id")
            patient_id = _patient_id_by_external(cur, hope_pid) if hope_pid else None
            if not patient_id:
                continue

            clean = {k: v for k, v in row.items() if not k.startswith("_")}
            clean["patient_id"] = patient_id

            cols = list(clean.keys())
            vals = [clean[c] for c in cols]
            placeholders = ", ".join(["%s"] * len(cols))
            col_names = ", ".join(cols)
            updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c not in ("external_source", "external_id"))
            sql = f"""
                INSERT INTO royan_immunisation ({col_names})
                VALUES ({placeholders})
                ON CONFLICT (external_source, external_id)
                WHERE external_source IS NOT NULL AND external_id IS NOT NULL
                DO UPDATE SET {updates}
            """
            if _exec_with_savepoint(cur, sql, vals, label=f"immunisation:{clean.get('vaccine_name')}"):
                upserted += 1

    conn.commit()
    return len(rows), upserted


def load_smart_phrases(conn, rows: List[Dict], dry_run: bool = False) -> Tuple[int, int]:
    """royan_smart_phrases from Hope's smart_phrases -- see
    transformers/smart_phrases.py. owner_staff_id is resolved from
    _hope_doctor_id when present (personal phrases); left null for
    shared/system phrases.
    """
    if dry_run:
        _print_dry_run("smart_phrases", rows)
        return len(rows), 0

    upserted = 0
    with conn.cursor() as cur:
        for row in rows:
            row = _sanitize_row(row)
            hope_doctor_id = row.get("_hope_doctor_id")
            clean = {k: v for k, v in row.items() if not k.startswith("_")}
            clean["owner_staff_id"] = _staff_id_by_external(cur, hope_doctor_id) if hope_doctor_id else None

            cols = list(clean.keys())
            vals = [clean[c] for c in cols]
            placeholders = ", ".join(["%s"] * len(cols))
            col_names = ", ".join(cols)
            updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c not in ("external_source", "external_id"))
            sql = f"""
                INSERT INTO royan_smart_phrases ({col_names})
                VALUES ({placeholders})
                ON CONFLICT (external_source, external_id)
                WHERE external_source IS NOT NULL AND external_id IS NOT NULL
                DO UPDATE SET {updates}
            """
            if _exec_with_savepoint(cur, sql, vals, label=f"smart_phrase:{clean.get('phrase')}"):
                upserted += 1

    conn.commit()
    return len(rows), upserted


def load_smart_phrase_options(conn, rows: List[Dict], dry_run: bool = False) -> Tuple[int, int]:
    """royan_smart_phrase_options -- token-keyed (not a per-phrase FK, see
    transformers/smart_phrases.py). Normal idempotent upsert.
    """
    if dry_run:
        _print_dry_run("smart_phrase_options", rows)
        return len(rows), 0

    upserted = 0
    with conn.cursor() as cur:
        for row in rows:
            row = _sanitize_row(row)
            clean = {k: v for k, v in row.items() if not k.startswith("_")}

            cols = list(clean.keys())
            vals = [clean[c] for c in cols]
            placeholders = ", ".join(["%s"] * len(cols))
            col_names = ", ".join(cols)
            updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c not in ("external_source", "external_id"))
            sql = f"""
                INSERT INTO royan_smart_phrase_options ({col_names})
                VALUES ({placeholders})
                ON CONFLICT (external_source, external_id)
                WHERE external_source IS NOT NULL AND external_id IS NOT NULL
                DO UPDATE SET {updates}
            """
            if _exec_with_savepoint(cur, sql, vals, label=f"smart_phrase_option:{clean.get('option_text','')[:30]}"):
                upserted += 1

    conn.commit()
    return len(rows), upserted


# ---------------------------------------------------------------------------
# Sync run logging
# ---------------------------------------------------------------------------

def log_run(conn, entity: str, rows_seen: int, rows_upserted: int,
            error: Optional[str] = None) -> None:
    # Every driver already calls log_run after a load, so this is the one
    # chokepoint where a zero-yield stream can announce itself.
    if not error:
        check_yield(entity, rows_seen, rows_upserted)
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
