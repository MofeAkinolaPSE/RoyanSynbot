"""Shared normalization helpers (ported from backend/src/services/hope_sync.py).

These are pure functions with no DB dependency — safe to import anywhere.
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Optional

HOSPITAL_DEPARTMENTS = {
    "A&E",
    "OPD",
    "Inpatient Ward",
    "Laboratory & Diagnostics",
    "Pharmacy",
    "Billing & Finance",
    "Administration",
    "Maintenance & Facilities",
    "Maternity",
    "Surgery",
}

EXTERNAL_SOURCE = "hope"


def utcnow() -> str:
    return dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


_MYSQL_ZERO_DATES = frozenset({
    "0000-00-00", "0000-00-00 00:00:00", "0000-00-00t00:00:00",
})


def safe_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def normalize_text(text: Optional[str]) -> Optional[str]:
    """Hope's free-text fields frequently carry literal "\\r\\n" escape
    sequences (not real line breaks) rather than actual newlines. Collapses
    those to real newlines and strips per-line whitespace/blank lines."""
    if not text:
        return text
    lines = [ln.strip() for ln in text.replace("\\r\\n", "\n").replace("\\n", "\n").splitlines()]
    return "\n".join(ln for ln in lines if ln) or None


def safe_date(value: Any) -> Optional[str]:
    """Like safe_str but treats MySQL zero/invalid-year dates as None."""
    s = safe_str(value)
    if not s:
        return None
    if s.lower() in _MYSQL_ZERO_DATES:
        return None
    # Catch year-zero variants: "0000-08-29", "0000-01-01", etc.
    if s.startswith("0000-"):
        return None
    return s


def gender(value: Any) -> Optional[str]:
    text = str(value or "").strip().lower()
    if text in {"m", "male"}:
        return "male"
    if text in {"f", "female"}:
        return "female"
    if text in {"other", "prefer_not_to_say"}:
        return text
    return None


_BLOOD_GROUP_MAP = {
    "a+": "A+", "a positive": "A+", "a pos": "A+",
    "a-": "A-", "a negative": "A-", "a neg": "A-",
    "b+": "B+", "b positive": "B+", "b pos": "B+",
    "b-": "B-", "b negative": "B-", "b neg": "B-",
    "ab+": "AB+", "ab positive": "AB+", "ab pos": "AB+",
    "ab-": "AB-", "ab negative": "AB-", "ab neg": "AB-",
    "o+": "O+", "o positive": "O+", "o pos": "O+",
    "o-": "O-", "o negative": "O-", "o neg": "O-",
}

_GENOTYPE_MAP = {
    "aa": "AA", "as": "AS", "ss": "SS",
    "ac": "AC", "sc": "SC",
    "sickle cell": "SS", "sickle": "SS",
}


def blood_group(value: Any) -> Optional[str]:
    """Normalise Hope blood group strings to the CHECK-constraint allowed values."""
    s = str(value or "").strip()
    return _BLOOD_GROUP_MAP.get(s.lower()) or ("unknown" if s else None)


def genotype(value: Any) -> Optional[str]:
    """Normalise Hope genotype strings to the CHECK-constraint allowed values."""
    s = str(value or "").strip()
    return _GENOTYPE_MAP.get(s.lower()) or ("unknown" if s else None)


def department(value: Any, fallback: str = "OPD") -> str:
    text = safe_str(value) or fallback
    return text if text in HOSPITAL_DEPARTMENTS else fallback


def status(value: Any, allowed: set, fallback: str) -> str:
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "pending":   "booked",      # for appointments
        "scheduled": "booked",
        "part_paid": "partial",
        "collected": "sample_collected",
        # "active" intentionally omitted: falls through to fallback so each
        # entity gets its own correct default (lab→ordered, billing→pending, etc.)
        "new":       "ordered",
        "done":      "resulted",
        "completed": "resulted",
        "dispensed": "dispensed",
        "cancelled": "cancelled",
        "canceled":  "cancelled",
        "paid":      "paid",
        "unpaid":    "pending",
        "settled":   "paid",
        "waived":    "waived",
    }
    text = aliases.get(text, text)
    return text if text in allowed else fallback


def apply_map(raw_row: dict, field_map: dict) -> dict:
    """Apply a field_map dict to a raw row. Handles __split__ and renames."""
    out: dict = {}
    raw_lower = {k.lower(): v for k, v in raw_row.items()}

    for src_col, tgt_field in field_map.items():
        if src_col not in raw_lower:
            continue
        val = raw_lower[src_col]
        if tgt_field == "__split__":
            # Only populate first_name / last_name if we get a non-empty value
            # AND the field hasn't already been set by an earlier, higher-priority mapping.
            # This prevents an empty full_name column from erasing a valid lookup_name split.
            parts = str(val or "").strip().split(" ", 1) if val else []
            fn = parts[0].strip() if parts else None
            ln = (parts[1].strip() or None) if len(parts) > 1 else None
            if fn and "first_name" not in out:
                out["first_name"] = fn
            if ln and "last_name" not in out:
                out["last_name"] = ln
        elif tgt_field == "__patient_lookup__":
            out["_hope_patient_id"] = safe_str(val)  # resolved later by loader
        else:
            if tgt_field not in out:  # first match wins
                out[tgt_field] = val

    return out


def generate_mrn_fallback() -> str:
    return f"RH{dt.datetime.utcnow():%Y%m%d%H%M%S}"
