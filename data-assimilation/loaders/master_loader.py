"""MDM master data loader — Chapter 4 of Synbot Health Blueprint.

Upserts all master reference entities to PostgreSQL before operational
entities are loaded. Returns lookup maps used by enrichment_loader to
resolve free-text FK references to integer IDs.

Lookup maps returned:
  dept_by_code    : {dept_code: royan_departments.id}
  dept_by_name    : {lower(dept_name): royan_departments.id}
  staff_by_ext    : {hope_external_id: royan_staff.id}
  staff_by_name   : {lower(full_name): royan_staff.id}
  lab_by_code     : {test_code: royan_lab_catalog.id}
  drug_by_code    : {drug_code: royan_drug_formulary.id}
  drug_by_name    : {lower(generic_name): royan_drug_formulary.id}
  hmo_by_name     : {lower(hmo_name): royan_hmos.id}
  ward_by_name    : {lower(ward_name): royan_wards.id}
  ward_by_ext     : {hope_external_id: royan_wards.id}
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import psycopg2
import psycopg2.extras

from transformers._helpers import EXTERNAL_SOURCE

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Duplicate detection
# ─────────────────────────────────────────────────────────────────────────────

def _normalize(s: str) -> str:
    """Lower-case, collapse whitespace, strip punctuation for fuzzy compare."""
    import re
    return re.sub(r"[^a-z0-9 ]", "", s.lower().strip()).strip()


def detect_duplicates(
    conn,
    entity_type: str,
    name_field: str,
    candidates: List[Dict[str, Any]],
    threshold: float = 0.85,
) -> List[Dict[str, Any]]:
    """Compare candidate names against existing DB records using trigram similarity.

    Returns a list of suspected duplicates: each entry has 'candidate', 'existing_id',
    'existing_name', 'similarity'. These are logged but NOT blocked — the loader
    proceeds; the warnings surface in the pipeline run log.
    """
    from difflib import SequenceMatcher

    table_map = {
        "staff":             ("royan_staff",           "lower(first_name || ' ' || last_name)"),
        "lab_catalog":       ("royan_lab_catalog",     "lower(name)"),
        "drug_formulary":    ("royan_drug_formulary",  "lower(generic_name)"),
        "diagnosis_catalog": ("royan_diagnosis_catalog","lower(description)"),
        "procedure_catalog": ("royan_procedure_catalog","lower(name)"),
        "department":        ("royan_departments",     "lower(name)"),
    }
    if entity_type not in table_map:
        return []

    table, name_expr = table_map[entity_type]
    with conn.cursor() as cur:
        cur.execute(f"SELECT id, {name_expr} AS nm FROM public.{table} WHERE is_active = true")
        existing = cur.fetchall()  # [(id, name_lower), ...]

    suspected: List[Dict[str, Any]] = []
    for candidate in candidates:
        cname = _normalize(str(candidate.get(name_field, "")))
        if not cname:
            continue
        for existing_id, existing_name in existing:
            if not existing_name:
                continue
            ratio = SequenceMatcher(None, cname, existing_name).ratio()
            if ratio >= threshold:
                msg = (
                    f"[DUPLICATE SUSPECT] {entity_type} '{cname}' ≈ existing #{existing_id} "
                    f"'{existing_name}' (similarity={ratio:.2f})"
                )
                logger.warning(msg)
                suspected.append({
                    "candidate": cname,
                    "existing_id": existing_id,
                    "existing_name": existing_name,
                    "similarity": round(ratio, 3),
                })

    return suspected


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _exec(cur, sql: str, params: tuple = ()) -> None:
    try:
        cur.execute(sql, params)
    except psycopg2.errors.UniqueViolation:
        cur.connection.rollback()
        logger.debug("Duplicate skip: %s", params[:2] if params else "")
    except Exception as exc:
        cur.connection.rollback()
        logger.warning("MDM upsert error: %s — %s", exc, params[:2] if params else "")


def _fetch_all_as_dict(cur, sql: str) -> List[Dict[str, Any]]:
    cur.execute(sql)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


# ─────────────────────────────────────────────────────────────────────────────
# Departments
# ─────────────────────────────────────────────────────────────────────────────

def load_departments(conn) -> Dict[str, int]:
    """Return {dept_code: id} map. Departments seeded in migration 130."""
    with conn.cursor() as cur:
        cur.execute("SELECT id, code, name FROM public.royan_departments WHERE is_active = true")
        rows = cur.fetchall()

    by_code: Dict[str, int] = {}
    by_name: Dict[str, int] = {}
    for row_id, code, name in rows:
        by_code[code] = row_id
        by_name[name.lower()] = row_id

    logger.info("MDM: loaded %d departments", len(by_code))
    return by_code, by_name


# ─────────────────────────────────────────────────────────────────────────────
# Staff
# ─────────────────────────────────────────────────────────────────────────────

def load_staff(
    conn,
    payloads: List[Dict[str, Any]],
    dept_by_code: Dict[str, int],
) -> tuple:
    """Upsert staff payloads and return (staff_by_ext, staff_by_name) maps."""
    staff_by_ext: Dict[str, int] = {}
    staff_by_name: Dict[str, int] = {}

    with conn.cursor() as cur:
        for p in payloads:
            dept_code = p.pop("_dept_code", None)
            dept_id = dept_by_code.get(dept_code) if dept_code else None

            cur.execute("""
                INSERT INTO public.royan_staff
                    (staff_code, first_name, last_name, role, specialty,
                     department_id, phone, email, is_active,
                     external_source, external_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (external_source, external_id)
                    WHERE external_source IS NOT NULL AND external_id IS NOT NULL
                DO UPDATE SET
                    first_name    = EXCLUDED.first_name,
                    last_name     = EXCLUDED.last_name,
                    role          = EXCLUDED.role,
                    specialty     = EXCLUDED.specialty,
                    department_id = COALESCE(EXCLUDED.department_id, royan_staff.department_id),
                    is_active     = EXCLUDED.is_active,
                    updated_at    = now()
                RETURNING id
            """, (
                p["staff_code"],
                p["first_name"],
                p["last_name"],
                p["role"],
                p.get("specialty"),
                dept_id,
                p.get("phone"),
                p.get("email"),
                p.get("is_active", True),
                EXTERNAL_SOURCE,
                p["external_id"],
            ))
            row = cur.fetchone()
            if row:
                db_id = row[0]
                staff_by_ext[p["external_id"]] = db_id
                full_lower = f"{p['first_name']} {p['last_name']}".lower()
                staff_by_name[full_lower] = db_id

        conn.commit()

    # Also build map from existing DB rows (covers pre-seeded data)
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, external_id, lower(first_name || ' ' || last_name) AS full_name
            FROM public.royan_staff
        """)
        for row_id, ext_id, full_name in cur.fetchall():
            if ext_id:
                staff_by_ext[ext_id] = row_id
            if full_name:
                staff_by_name[full_name] = row_id

    logger.info("MDM: upserted %d staff records", len(payloads))
    return staff_by_ext, staff_by_name


# ─────────────────────────────────────────────────────────────────────────────
# Wards
# ─────────────────────────────────────────────────────────────────────────────

def load_wards(
    conn,
    payloads: List[Dict[str, Any]],
    dept_by_code: Dict[str, int],
) -> tuple:
    """Upsert ward payloads and return (ward_by_ext, ward_by_name) maps."""
    ward_by_ext: Dict[str, int] = {}
    ward_by_name: Dict[str, int] = {}

    with conn.cursor() as cur:
        for p in payloads:
            cur.execute("""
                INSERT INTO public.royan_wards
                    (name, ward_type, total_beds, is_active, notes,
                     external_source, external_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (name) DO UPDATE SET
                    ward_type   = EXCLUDED.ward_type,
                    total_beds  = GREATEST(royan_wards.total_beds, EXCLUDED.total_beds),
                    is_active   = EXCLUDED.is_active,
                    notes       = EXCLUDED.notes
                RETURNING id, name
            """, (
                p["name"],
                p["ward_type"],
                p.get("total_beds", 0),
                p.get("is_active", True),
                p.get("notes"),
                EXTERNAL_SOURCE,
                p["external_id"],
            ))
            row = cur.fetchone()
            if row:
                db_id, ward_name = row
                ward_by_ext[p["external_id"]] = db_id
                ward_by_name[ward_name.lower()] = db_id

        conn.commit()

    # Also load existing wards
    with conn.cursor() as cur:
        cur.execute("SELECT id, external_id, lower(name) FROM public.royan_wards")
        for row_id, ext_id, name_lower in cur.fetchall():
            if ext_id:
                ward_by_ext[ext_id] = row_id
            if name_lower:
                ward_by_name[name_lower] = row_id

    logger.info("MDM: upserted %d wards", len(payloads))
    return ward_by_ext, ward_by_name


# ─────────────────────────────────────────────────────────────────────────────
# Lab Catalog
# ─────────────────────────────────────────────────────────────────────────────

def load_lab_catalog(
    conn,
    mined_entries: List[Dict[str, Any]],
) -> Dict[str, int]:
    """Upsert mined lab catalog entries and return {test_code: id} map."""
    detect_duplicates(conn, "lab_catalog", "name", mined_entries)
    with conn.cursor() as cur:
        for p in mined_entries:
            cur.execute("""
                INSERT INTO public.royan_lab_catalog
                    (code, name, category, specimen_type, turnaround_hours,
                     base_price, is_active, external_source, external_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (code) DO NOTHING
            """, (
                p["code"],
                p["name"],
                p.get("category", "other"),
                p.get("specimen_type", "blood"),
                p.get("turnaround_hours", 24),
                p.get("base_price", 0),
                p.get("is_active", True),
                EXTERNAL_SOURCE,
                p["external_id"],
            ))

        conn.commit()

    # Build full lookup from DB
    lab_by_code: Dict[str, int] = {}
    with conn.cursor() as cur:
        cur.execute("SELECT id, code FROM public.royan_lab_catalog WHERE is_active = true")
        for row_id, code in cur.fetchall():
            lab_by_code[code] = row_id

    logger.info("MDM: lab catalog has %d entries", len(lab_by_code))
    return lab_by_code


# ─────────────────────────────────────────────────────────────────────────────
# Drug Formulary
# ─────────────────────────────────────────────────────────────────────────────

def load_drug_formulary(
    conn,
    mined_entries: List[Dict[str, Any]],
) -> tuple:
    """Upsert mined drug formulary and return (drug_by_code, drug_by_name)."""
    detect_duplicates(conn, "drug_formulary", "generic_name", mined_entries)
    with conn.cursor() as cur:
        for p in mined_entries:
            cur.execute("""
                INSERT INTO public.royan_drug_formulary
                    (code, generic_name, drug_class, form, unit, is_active,
                     external_source, external_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (code) DO NOTHING
            """, (
                p["code"],
                p["generic_name"],
                p.get("drug_class", "other"),
                p.get("form", "tablet"),
                p.get("unit", "tablet"),
                p.get("is_active", True),
                EXTERNAL_SOURCE,
                p["external_id"],
            ))

        conn.commit()

    drug_by_code: Dict[str, int] = {}
    drug_by_name: Dict[str, int] = {}
    with conn.cursor() as cur:
        cur.execute("SELECT id, code, lower(generic_name) FROM public.royan_drug_formulary")
        for row_id, code, name_lower in cur.fetchall():
            drug_by_code[code] = row_id
            drug_by_name[name_lower] = row_id

    logger.info("MDM: drug formulary has %d entries", len(drug_by_code))
    return drug_by_code, drug_by_name


# ─────────────────────────────────────────────────────────────────────────────
# HMO lookup (already seeded by hmo.py pipeline; just build the map)
# ─────────────────────────────────────────────────────────────────────────────

def load_hmo_map(conn) -> Dict[str, int]:
    """Return {lower(hmo_name): royan_hmos.id} map."""
    hmo_by_name: Dict[str, int] = {}
    hmo_by_ext: Dict[str, int] = {}
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, lower(name), external_id
            FROM public.royan_hmos
        """)
        for row_id, name_lower, ext_id in cur.fetchall():
            hmo_by_name[name_lower] = row_id
            if ext_id:
                hmo_by_ext[ext_id] = row_id

    logger.info("MDM: HMO registry has %d entries", len(hmo_by_name))
    return hmo_by_name, hmo_by_ext


# ─────────────────────────────────────────────────────────────────────────────
# Master bootstrap — run all MDM loads in dependency order
# ─────────────────────────────────────────────────────────────────────────────

def bootstrap_all_master_data(
    conn,
    staff_payloads: List[Dict],
    ward_payloads: List[Dict],
    lab_catalog_entries: List[Dict],
    drug_formulary_entries: List[Dict],
) -> Dict[str, Any]:
    """Load all MDM in correct order. Return consolidated lookup maps."""

    dept_by_code, dept_by_name = load_departments(conn)
    staff_by_ext, staff_by_name = load_staff(conn, staff_payloads, dept_by_code)
    ward_by_ext, ward_by_name = load_wards(conn, ward_payloads, dept_by_code)
    lab_by_code = load_lab_catalog(conn, lab_catalog_entries)
    drug_by_code, drug_by_name = load_drug_formulary(conn, drug_formulary_entries)
    hmo_by_name, hmo_by_ext = load_hmo_map(conn)

    logger.info(
        "MDM bootstrap complete — depts:%d staff:%d wards:%d lab:%d drugs:%d hmos:%d",
        len(dept_by_code), len(staff_by_ext), len(ward_by_ext),
        len(lab_by_code), len(drug_by_code), len(hmo_by_name),
    )

    return {
        "dept_by_code":  dept_by_code,
        "dept_by_name":  dept_by_name,
        "staff_by_ext":  staff_by_ext,
        "staff_by_name": staff_by_name,
        "ward_by_ext":   ward_by_ext,
        "ward_by_name":  ward_by_name,
        "lab_by_code":   lab_by_code,
        "drug_by_code":  drug_by_code,
        "drug_by_name":  drug_by_name,
        "hmo_by_name":   hmo_by_name,
        "hmo_by_ext":    hmo_by_ext,
    }
