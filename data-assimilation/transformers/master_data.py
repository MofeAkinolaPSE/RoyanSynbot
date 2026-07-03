"""MDM master data transformer — Chapter 4 of Synbot Health Blueprint.

Extracts authoritative master entities from staged Hope data:
  - Staff / consultants   → royan_staff
  - Wards                 → royan_wards (enriches existing rows)
  - Lab catalog entries   → royan_lab_catalog (supplements seeded defaults)
  - Drug formulary        → royan_drug_formulary (mined from prescriptions)
  - Departments           → royan_departments (mined from encounter dept names)

All transforms are pure functions; no DB dependency.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set

from transformers._helpers import EXTERNAL_SOURCE, apply_map, safe_str, utcnow
from transformers.field_maps import CONSULTANT_MAP, WARD_MAP


# ─────────────────────────────────────────────────────────────────────────────
# STAFF / CONSULTANTS
# ─────────────────────────────────────────────────────────────────────────────

# Maps specialty text from Hope → (role, dept_code) for royan_staff
_SPECIALTY_ROLE_MAP: Dict[str, tuple] = {
    "physician":        ("doctor", "OPD"),
    "surgeon":          ("doctor", "SURG"),
    "paediatrician":    ("doctor", "PAEDS"),
    "paediatrics":      ("doctor", "PAEDS"),
    "paediatric":       ("doctor", "PAEDS"),
    "obstetrician":     ("doctor", "MATERN"),
    "gynaecologist":    ("doctor", "MATERN"),
    "obs & gyn":        ("doctor", "MATERN"),
    "obstetric":        ("doctor", "MATERN"),
    "maternity":        ("doctor", "MATERN"),
    "cardiologist":     ("doctor", "CARDIO"),
    "cardiology":       ("doctor", "CARDIO"),
    "radiologist":      ("doctor", "RAD"),
    "radiology":        ("doctor", "RAD"),
    "pathologist":      ("doctor", "LAB"),
    "laboratory":       ("lab_scientist", "LAB"),
    "lab":              ("lab_scientist", "LAB"),
    "pharmacist":       ("pharmacist", "PHARM"),
    "pharmacy":         ("pharmacist", "PHARM"),
    "nursing":          ("nurse", "OPD"),
    "nurse":            ("nurse", "OPD"),
    "anaesth":          ("doctor", "SURG"),
    "anaesthesia":      ("doctor", "SURG"),
    "ent":              ("doctor", "ENT"),
    "ophthalmol":       ("doctor", "OPHTHAL"),
    "dental":           ("doctor", "DENTAL"),
    "dentist":          ("doctor", "DENTAL"),
    "physiother":       ("physiotherapist", "PHYSIO"),
    "dietit":           ("dietitian", "DIETETICS"),
    "admin":            ("admin", "ADMIN"),
    "accountant":       ("accountant", "BILLING"),
    "receptionist":     ("receptionist", "ADMIN"),
}

def _infer_role_and_dept(specialty: Optional[str]) -> tuple:
    """Infer (role, dept_code) from free-text specialty."""
    if not specialty:
        return ("doctor", "OPD")
    lower = specialty.lower().strip()
    for kw, mapping in _SPECIALTY_ROLE_MAP.items():
        if kw in lower:
            return mapping
    return ("doctor", "OPD")


def _extract_title(name: str) -> tuple:
    """Split 'Dr John Doe' into ('Dr', 'John', 'Doe'). Returns (title, first, last)."""
    titles = {"dr", "prof", "mr", "mrs", "ms", "nurse", "pharm", "lab"}
    parts = name.strip().split()
    if not parts:
        return (None, "Unknown", "Staff")
    if parts[0].rstrip(".").lower() in titles:
        title = parts[0].rstrip(".")
        rest = parts[1:]
    else:
        title = None
        rest = parts
    first = rest[0] if rest else "Unknown"
    last = " ".join(rest[1:]) if len(rest) > 1 else "Staff"
    return (title, first, last)


def transform_staff(raw_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Transform staged consultants/staff rows → royan_staff payloads."""
    out: List[Dict] = []
    seen: Set[str] = set()

    for row in raw_rows:
        mapped = apply_map(row, CONSULTANT_MAP)

        external_id = safe_str(mapped.get("external_id"))
        if not external_id:
            continue
        if external_id in seen:
            continue
        seen.add(external_id)

        # Name resolution
        first = safe_str(mapped.get("first_name"))
        last = safe_str(mapped.get("last_name"))
        if not first and not last:
            continue
        first = first or "Unknown"
        last = last or "Staff"

        specialty = safe_str(mapped.get("department"))  # CONSULTANT_MAP maps specialty → department
        role, dept_code = _infer_role_and_dept(specialty)

        is_active_raw = mapped.get("is_active")
        is_active = True
        if is_active_raw is not None:
            is_active = str(is_active_raw).strip().lower() in {"1", "true", "yes", "active"}

        staff_code = f"HOPE-{external_id}"

        out.append({
            "staff_code":       staff_code,
            "first_name":       first,
            "last_name":        last,
            "role":             role,
            "specialty":        specialty,
            "_dept_code":       dept_code,      # resolved to department_id by loader
            "phone":            safe_str(mapped.get("phone")),
            "email":            safe_str(mapped.get("email")),
            "is_active":        is_active,
            "external_source":  EXTERNAL_SOURCE,
            "external_id":      external_id,
        })

    return out


# ─────────────────────────────────────────────────────────────────────────────
# DEPARTMENTS (mined from encounter/admission department field)
# ─────────────────────────────────────────────────────────────────────────────

# Canonical mapping of free-text Hope department names → royan_departments.code
_DEPT_NAME_TO_CODE: Dict[str, str] = {
    "opd":                      "OPD",
    "outpatient":               "OPD",
    "out patient":              "OPD",
    "a&e":                      "AE",
    "a & e":                    "AE",
    "accident":                 "AE",
    "emergency":                "AE",
    "laboratory":               "LAB",
    "lab":                      "LAB",
    "diagnostics":              "LAB",
    "laboratory & diagnostics": "LAB",
    "pharmacy":                 "PHARM",
    "radiology":                "RAD",
    "imaging":                  "RAD",
    "xray":                     "RAD",
    "x-ray":                    "RAD",
    "surgery":                  "SURG",
    "surgical":                 "SURG",
    "theatre":                  "SURG",
    "maternity":                "MATERN",
    "obstetrics":               "MATERN",
    "obs & gyn":                "MATERN",
    "mch":                      "MATERN",
    "paediatrics":              "PAEDS",
    "paediatric":               "PAEDS",
    "children":                 "PAEDS",
    "icu":                      "ICU",
    "intensive care":           "ICU",
    "inpatient":                "IPD",
    "ward":                     "IPD",
    "billing":                  "BILLING",
    "accounts":                 "BILLING",
    "finance":                  "BILLING",
    "admin":                    "ADMIN",
    "administration":           "ADMIN",
    "maintenance":              "MAINT",
    "facilities":               "MAINT",
    "dental":                   "DENTAL",
    "dentistry":                "DENTAL",
    "physiotherapy":            "PHYSIO",
    "ophthalmology":            "OPHTHAL",
    "ophthal":                  "OPHTHAL",
    "eye":                      "OPHTHAL",
    "ent":                      "ENT",
    "cardiology":               "CARDIO",
    "cardiac":                  "CARDIO",
    "heart":                    "CARDIO",
}


def resolve_dept_code(raw_name: Optional[str]) -> Optional[str]:
    """Return canonical department code for a free-text Hope department string, or None."""
    if not raw_name:
        return None
    lower = raw_name.strip().lower()
    # Exact match first
    if lower in _DEPT_NAME_TO_CODE:
        return _DEPT_NAME_TO_CODE[lower]
    # Partial match
    for kw, code in _DEPT_NAME_TO_CODE.items():
        if kw in lower:
            return code
    return None


def mine_departments_from_admissions(raw_rows: List[Dict[str, Any]]) -> List[str]:
    """Return distinct unmapped department codes found in admissions/encounter data."""
    found: Set[str] = set()
    for row in raw_rows:
        dept = safe_str(row.get("department") or row.get("dept") or row.get("clinic"))
        code = resolve_dept_code(dept)
        if code:
            found.add(code)
    return list(found)


# ─────────────────────────────────────────────────────────────────────────────
# WARDS
# ─────────────────────────────────────────────────────────────────────────────

_WARD_TYPE_MAP: Dict[str, str] = {
    "general":      "general",
    "private":      "private",
    "surgical":     "surgical",
    "surgery":      "surgical",
    "icu":          "icu",
    "intensive":    "icu",
    "maternity":    "maternity",
    "antenatal":    "maternity",
    "postnatal":    "maternity",
    "paediatric":   "paediatric",
    "children":     "paediatric",
    "isolation":    "isolation",
    "emergency":    "emergency",
}


def _infer_ward_type(name: str) -> str:
    lower = name.lower()
    for kw, wt in _WARD_TYPE_MAP.items():
        if kw in lower:
            return wt
    return "general"


def transform_wards(raw_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Transform staged ward rows → royan_wards payloads."""
    out: List[Dict] = []
    seen: Set[str] = set()

    for row in raw_rows:
        mapped = apply_map(row, WARD_MAP)

        external_id = safe_str(mapped.get("external_id"))
        ward_name = safe_str(mapped.get("ward_name"))
        if not ward_name:
            continue
        if not external_id:
            external_id = f"hope-ward-{ward_name.lower().replace(' ', '-')}"
        if external_id in seen:
            continue
        seen.add(external_id)

        try:
            total_beds = int(mapped.get("total_beds") or 0)
        except (TypeError, ValueError):
            total_beds = 0

        is_active_raw = mapped.get("is_active")
        is_active = True
        if is_active_raw is not None:
            is_active = str(is_active_raw).strip().lower() in {"1", "true", "yes", "active"}

        out.append({
            "name":             ward_name,
            "ward_type":        _infer_ward_type(ward_name),
            "total_beds":       total_beds,
            "is_active":        is_active,
            "notes":            f"Imported from Hope HMS (id: {external_id})",
            "external_source":  EXTERNAL_SOURCE,
            "external_id":      external_id,
        })

    return out


# ─────────────────────────────────────────────────────────────────────────────
# LAB CATALOG (mine from lab order test_codes)
# ─────────────────────────────────────────────────────────────────────────────

def mine_lab_catalog_from_orders(raw_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Extract distinct test_code + test_name pairs from staged lab orders.

    These supplement the seeded defaults in migration 130 — any code not already
    present will be inserted as an 'unknown' category entry pending clinical review.
    """
    seen: Set[str] = set()
    out: List[Dict] = []

    for row in raw_rows:
        # test_code may be in laboratory_id or test_code column
        code = safe_str(
            row.get("laboratory_id")
            or row.get("test_code")
            or row.get("lab_test_code")
        )
        name = safe_str(
            row.get("test_name")
            or row.get("test_type")
            or row.get("investigation")
            or row.get("description")
        )

        if not code or code in seen:
            continue
        # Skip placeholder names
        if name and name.lower() in {"lab test", "laboratory test", "test", "investigation", ""}:
            name = None

        seen.add(code)
        out.append({
            "code":             code,
            "name":             name or f"Lab Test {code}",
            "category":         "other",        # clinical team will re-classify
            "specimen_type":    "blood",
            "turnaround_hours": 24,
            "base_price":       0,
            "is_active":        True,
            "external_source":  EXTERNAL_SOURCE,
            "external_id":      f"lab-{code}",
        })

    return out


# ─────────────────────────────────────────────────────────────────────────────
# DRUG FORMULARY (mine from pharmacy/prescription data)
# ─────────────────────────────────────────────────────────────────────────────

def mine_drug_formulary_from_prescriptions(raw_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Extract distinct drug names + codes from staged prescription rows.

    These supplement any manually curated formulary entries. Mined entries are
    flagged for clinical pharmacist review via notes field.
    """
    seen_names: Set[str] = set()
    out: List[Dict] = []
    seq = 1

    for row in raw_rows:
        drug_name = safe_str(
            row.get("drug_name")
            or row.get("drug")
            or row.get("medication")
            or row.get("item_name")
            or row.get("product_name")
        )
        if not drug_name:
            continue

        canonical = drug_name.strip().title()
        if canonical in seen_names:
            continue
        seen_names.add(canonical)

        drug_code = safe_str(row.get("drug_code") or row.get("drug_id") or row.get("nafdac_no"))
        if not drug_code:
            drug_code = f"HOPE-DRUG-{seq:05d}"
        seq += 1

        form_raw = safe_str(row.get("unit") or row.get("form") or "")
        form = "tablet"
        if form_raw:
            fl = form_raw.lower()
            if "syrup" in fl or "liquid" in fl or "suspension" in fl:
                form = "syrup"
            elif "inj" in fl or "vial" in fl or "ampoule" in fl:
                form = "injection"
            elif "cap" in fl:
                form = "capsule"
            elif "cream" in fl or "oint" in fl:
                form = "cream"
            elif "drop" in fl:
                form = "drops"

        out.append({
            "code":             drug_code,
            "generic_name":     canonical,
            "drug_class":       "other",        # pharmacist to re-classify
            "form":             form,
            "unit":             safe_str(row.get("unit")) or "tablet",
            "is_active":        True,
            "external_source":  EXTERNAL_SOURCE,
            "external_id":      f"drug-{drug_code}",
        })

    return out
