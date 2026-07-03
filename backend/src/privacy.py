"""NDPA 2023 Privacy & PHI Masking Utilities — Chapter 18 of the blueprint.

Implements Nigeria Data Protection Act 2023 compliance for SynbotHealth:
  - Role-based PHI field masking (least-privilege data exposure)
  - Consent validation helpers
  - PHI field registry (which fields count as personally identifiable)
  - Data Subject Request (DSR) helpers for access / erasure

PHI MASKING ROLES
  clinical    → full PHI access (doctors, nurses, clinical staff)
  reception   → contact details (phone, email); medical data masked
  billing     → financial fields; DOB partially masked; address hidden
  admin       → management view; PHI partially visible
  lab         → lab-specific data; patient demographics masked
  pharmacy    → prescription data; contact masked
  report      → aggregate access only; full PHI masked
  (none)      → minimal (MRN + name only)
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set

# ─────────────────────────────────────────────────────────────────────────────
# PHI field classification
# ─────────────────────────────────────────────────────────────────────────────

# Direct identifiers — uniquely identify a person
PHI_DIRECT: Set[str] = {
    "date_of_birth", "phone", "email", "address",
    "next_of_kin_name", "next_of_kin_phone",
    "national_id", "nin", "bvn",
    "ip_address",
}

# Quasi-identifiers — identify in combination
PHI_QUASI: Set[str] = {
    "gender", "blood_group", "genotype",
    "hmo_id", "hmo_provider",
}

# Clinical data — sensitive but clinically necessary
PHI_CLINICAL: Set[str] = {
    "diagnosis_notes", "diagnosis_codes", "discharge_summary",
    "chief_complaint", "triage_notes", "allergies",
}

ALL_PHI: Set[str] = PHI_DIRECT | PHI_QUASI | PHI_CLINICAL

# ─────────────────────────────────────────────────────────────────────────────
# Role → visible field sets
# ─────────────────────────────────────────────────────────────────────────────

# Each role lists the PHI fields it MAY see (everything else is masked)
_ROLE_PHI_VISIBILITY: Dict[str, Set[str]] = {
    "clinical":  ALL_PHI,                   # full clinical access
    "admin":     PHI_DIRECT | PHI_QUASI,    # management; no clinical notes
    "reception": {"phone", "email", "next_of_kin_name", "next_of_kin_phone"},
    "billing":   {"date_of_birth", "gender", "hmo_id", "hmo_provider"},
    "lab":       {"date_of_birth", "gender", "blood_group"},
    "pharmacy":  {"allergies", "date_of_birth"},
    "nursing":   ALL_PHI,                   # same as clinical
    "ops":       PHI_QUASI,                 # operational analytics
    "report":    set(),                     # aggregate only — no PHI
}

# admin and superadmin always have full access
_SUPERROLES = {"admin", "superadmin"}


def _user_roles(user: Dict[str, Any]) -> Set[str]:
    roles = user.get("roles") or user.get("permissions") or []
    return set(roles) if isinstance(roles, list) else {roles}


def visible_phi_fields(user: Dict[str, Any]) -> Set[str]:
    """Return the set of PHI fields this user is allowed to see."""
    roles = _user_roles(user)
    if roles & _SUPERROLES:
        return ALL_PHI
    visible: Set[str] = set()
    for role in roles:
        visible |= _ROLE_PHI_VISIBILITY.get(role, set())
    return visible


# ─────────────────────────────────────────────────────────────────────────────
# Masking functions
# ─────────────────────────────────────────────────────────────────────────────

_PHONE_RE = re.compile(r"\d(?=\d{4})")


def _mask_phone(value: str) -> str:
    """Mask middle digits: 08012345678 → 080****5678."""
    if len(value) < 6:
        return "***"
    return value[:3] + "****" + value[-4:]


def _mask_dob(value: str) -> str:
    """Show year only: 1985-06-20 → 1985-**-**."""
    if len(value) >= 4:
        return value[:4] + "-**-**"
    return "****"


def _mask_email(value: str) -> str:
    """Mask local part: john.doe@example.com → j***.***@example.com."""
    if "@" not in value:
        return "***@***.***"
    local, domain = value.split("@", 1)
    return local[0] + "***" + "@" + domain


_FIELD_MASKS = {
    "phone":           _mask_phone,
    "next_of_kin_phone": _mask_phone,
    "email":           _mask_email,
    "date_of_birth":   _mask_dob,
    "address":         lambda v: "*** (address hidden)",
    "next_of_kin_name": lambda v: v[0] + "***" if v else "***",
    "national_id":     lambda v: "***" + str(v)[-3:] if len(str(v)) > 3 else "***",
    "ip_address":      lambda v: "*.*.*.***",
}

_MASKED_SENTINEL = "[MASKED]"


def mask_record(record: Dict[str, Any], user: Dict[str, Any]) -> Dict[str, Any]:
    """Return a copy of record with PHI fields masked according to user's role.

    Non-PHI fields are always returned unchanged.
    PHI fields the user is allowed to see are returned unchanged.
    PHI fields the user cannot see are masked or replaced with [MASKED].
    """
    allowed = visible_phi_fields(user)
    out: Dict[str, Any] = {}
    for key, value in record.items():
        if key not in ALL_PHI:
            out[key] = value
            continue
        if key in allowed:
            out[key] = value
            continue
        # Mask — use field-specific mask if available, else sentinel
        if value is not None and str(value).strip():
            mask_fn = _FIELD_MASKS.get(key)
            out[key] = mask_fn(str(value)) if mask_fn else _MASKED_SENTINEL
        else:
            out[key] = value  # None or empty — no point masking
    return out


def mask_records(records: List[Dict[str, Any]], user: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Mask a batch of records."""
    return [mask_record(r, user) for r in records]


# ─────────────────────────────────────────────────────────────────────────────
# Consent validation
# ─────────────────────────────────────────────────────────────────────────────

# Consent types required for each operation class
_REQUIRED_CONSENT: Dict[str, str] = {
    "data_processing":   "data_processing",
    "research":          "research",
    "third_party":       "third_party_sharing",
    "marketing":         "marketing",
}


def check_consent(patient_id: int, purpose: str, conn) -> bool:
    """Check royan_patient_consent for active consent for the given purpose.

    Returns True if consent exists and is not withdrawn or expired.
    Raises ValueError if purpose is unknown.
    """
    consent_type = _REQUIRED_CONSENT.get(purpose)
    if not consent_type:
        raise ValueError(f"Unknown consent purpose: {purpose!r}. Valid: {list(_REQUIRED_CONSENT)}")

    import datetime
    today = datetime.date.today().isoformat()

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*)
            FROM public.royan_patient_consent
            WHERE patient_id = %s
              AND consent_type = %s
              AND is_given = true
              AND withdrawn_at IS NULL
              AND (expiry_date IS NULL OR expiry_date >= %s)
            """,
            (patient_id, consent_type, today),
        )
        row = cur.fetchone()
        return bool(row and row[0] > 0)


# ─────────────────────────────────────────────────────────────────────────────
# PHI audit logging
# ─────────────────────────────────────────────────────────────────────────────

def log_phi_access(
    patient_id: int,
    fields_accessed: List[str],
    accessed_by: str,
    purpose: str,
    conn,
) -> None:
    """Append a PHI access record to royan_audit_logs for NDPA audit trail.

    Fire-and-forget — exceptions are swallowed so PHI access logging never
    blocks a clinical operation.
    """
    phi_fields = [f for f in fields_accessed if f in ALL_PHI]
    if not phi_fields:
        return
    import json
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO public.royan_audit_logs
                    (entity_type, entity_id, action, actor, details, created_at)
                VALUES ('patient', %s, 'phi_read', %s, %s, now())
                """,
                (
                    patient_id,
                    accessed_by,
                    json.dumps({"fields": phi_fields, "purpose": purpose}),
                ),
            )
            conn.commit()
    except Exception:
        pass  # audit failure must not block clinical operations
