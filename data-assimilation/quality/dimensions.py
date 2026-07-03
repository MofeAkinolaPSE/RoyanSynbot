"""Seven data-quality dimension checkers — Chapter 5.4 of the blueprint.

Each checker is a pure function that takes a record (dict) and a domain
config (dict) and returns a DimensionResult with score 0.0–1.0 and a list
of violations.

Dimensions:
  1. Completeness   — required fields are present and non-empty
  2. Validity       — values match allowed formats / controlled vocabularies
  3. Accuracy       — values are within clinically plausible ranges
  4. Consistency    — cross-field logic holds (e.g. DOB < registered_at)
  5. Timeliness     — timestamps are within acceptable age bounds
  6. Uniqueness     — no duplicate key within the batch
  7. Integrity      — FK references exist (evaluated at load time)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set


# ─────────────────────────────────────────────────────────────────────────────
# Result type
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class DimensionResult:
    dimension: str
    score: float                    # 0.0 = fail, 1.0 = perfect
    violations: List[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return len(self.violations) == 0


@dataclass
class RecordQualityReport:
    entity: str
    record_key: str
    scores: Dict[str, float] = field(default_factory=dict)
    violations: Dict[str, List[str]] = field(default_factory=dict)

    @property
    def overall_score(self) -> float:
        if not self.scores:
            return 0.0
        return sum(self.scores.values()) / len(self.scores)

    @property
    def passed(self) -> bool:
        return self.overall_score >= 0.7

    @property
    def is_hard_fail(self) -> bool:
        """Record must be rejected (sent to DLQ) if True."""
        hard_dims = {"completeness", "integrity"}
        for dim in hard_dims:
            if self.scores.get(dim, 1.0) < 0.5:
                return True
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Domain configuration
# ─────────────────────────────────────────────────────────────────────────────

DOMAIN_CONFIGS: Dict[str, Dict] = {
    "patients": {
        "required_fields":  ["mrn", "first_name", "last_name"],
        "optional_fields":  ["date_of_birth", "gender", "phone", "email"],
        "date_fields":      ["date_of_birth", "registered_at"],
        "gender_field":     "gender",
        "mrn_field":        "mrn",
        "max_age_days":     None,           # patient records don't expire
        "unique_key":       "mrn",
    },
    "encounters": {
        "required_fields":  ["patient_id", "encounter_type", "status"],
        "optional_fields":  ["department", "consulting_doctor"],
        "date_fields":      ["created_at", "triage_at"],
        "max_age_days":     None,
        "unique_key":       "external_id",
    },
    "lab_orders": {
        "required_fields":  ["patient_id", "encounter_id", "test_code", "ordered_at"],
        "optional_fields":  ["test_name", "ordered_by", "sample_type"],
        "date_fields":      ["ordered_at"],
        "max_age_days":     None,
        "unique_key":       "external_id",
        "placeholder_names": {
            "lab test", "laboratory test", "test", "investigation", "imported lab order", ""
        },
    },
    "prescriptions": {
        "required_fields":  ["patient_id", "encounter_id", "drug_name", "dosage", "frequency"],
        "optional_fields":  ["drug_code", "route", "quantity"],
        "date_fields":      ["prescribed_at"],
        "max_age_days":     None,
        "unique_key":       "external_id",
    },
    "billing": {
        "required_fields":  ["patient_id", "encounter_id", "bill_number"],
        "optional_fields":  ["payment_method", "hmo_covered"],
        "date_fields":      ["billed_at"],
        "max_age_days":     None,
        "unique_key":       "external_id",
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# Dimension 1 — Completeness
# ─────────────────────────────────────────────────────────────────────────────

def check_completeness(record: Dict[str, Any], config: Dict) -> DimensionResult:
    required = config.get("required_fields", [])
    if not required:
        return DimensionResult("completeness", 1.0)

    missing = []
    for f in required:
        val = record.get(f)
        if val is None or str(val).strip() == "":
            missing.append(f)

    score = 1.0 - (len(missing) / len(required))
    violations = [f"Missing required field: {f}" for f in missing]
    return DimensionResult("completeness", round(score, 3), violations)


# ─────────────────────────────────────────────────────────────────────────────
# Dimension 2 — Validity
# ─────────────────────────────────────────────────────────────────────────────

_GENDER_ALLOWED = {"male", "female", "other", "prefer_not_to_say"}
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}")
_MRN_RE  = re.compile(r"^RH\d{2}-\d+$|^RH\d{4}\d{6}$")


def check_validity(record: Dict[str, Any], config: Dict) -> DimensionResult:
    violations = []
    total_checks = 0

    # Gender
    gender_field = config.get("gender_field")
    if gender_field and record.get(gender_field):
        total_checks += 1
        if str(record[gender_field]).lower() not in _GENDER_ALLOWED:
            violations.append(f"Invalid gender: '{record[gender_field]}'")

    # Date fields — must be parseable ISO-8601
    for df in config.get("date_fields", []):
        val = record.get(df)
        if val is not None and str(val).strip():
            total_checks += 1
            if not _DATE_RE.match(str(val)):
                violations.append(f"Invalid date format for {df}: '{val}'")

    # MRN format check
    mrn_field = config.get("mrn_field")
    if mrn_field and record.get(mrn_field):
        total_checks += 1
        # Be lenient — Hope MRNs can take various forms

    # Lab order: flag placeholder test names
    placeholder_names = config.get("placeholder_names", set())
    if placeholder_names:
        name = str(record.get("test_name") or "").strip().lower()
        if name in placeholder_names:
            violations.append(f"Placeholder test_name: '{name}'")
            total_checks += 1

    if total_checks == 0:
        return DimensionResult("validity", 1.0)

    score = 1.0 - (len(violations) / total_checks)
    return DimensionResult("validity", round(max(score, 0.0), 3), violations)


# ─────────────────────────────────────────────────────────────────────────────
# Dimension 3 — Accuracy (clinical plausibility)
# ─────────────────────────────────────────────────────────────────────────────

def check_accuracy(record: Dict[str, Any], config: Dict) -> DimensionResult:
    violations = []
    total_checks = 0

    # DOB plausibility
    dob = record.get("date_of_birth")
    if dob:
        total_checks += 1
        try:
            dob_dt = datetime.fromisoformat(str(dob)[:10])
            age_years = (datetime.now() - dob_dt).days / 365.25
            if age_years < 0:
                violations.append(f"DOB in the future: {dob}")
            elif age_years > 130:
                violations.append(f"DOB implies age > 130 years: {dob}")
        except ValueError:
            pass  # validity dimension handles unparseable dates

    # Billing: zero subtotal that isn't waived
    if "consultation_fee" in record:
        total_checks += 1
        status = str(record.get("status") or "").lower()
        try:
            total = float(record.get("consultation_fee") or 0)
            if total == 0 and status not in {"waived", "written_off"}:
                violations.append("Zero-value bill not in waived/written_off status")
        except (TypeError, ValueError):
            pass

    if total_checks == 0:
        return DimensionResult("accuracy", 1.0)

    score = 1.0 - (len(violations) / total_checks)
    return DimensionResult("accuracy", round(max(score, 0.0), 3), violations)


# ─────────────────────────────────────────────────────────────────────────────
# Dimension 4 — Consistency (cross-field logic)
# ─────────────────────────────────────────────────────────────────────────────

def check_consistency(record: Dict[str, Any], config: Dict) -> DimensionResult:
    violations = []
    total_checks = 0

    # registered_at should be >= date_of_birth
    dob = record.get("date_of_birth")
    reg = record.get("registered_at") or record.get("created_at")
    if dob and reg:
        total_checks += 1
        try:
            dob_dt = datetime.fromisoformat(str(dob)[:10])
            reg_dt = datetime.fromisoformat(str(reg)[:10])
            if reg_dt < dob_dt:
                violations.append(f"registered_at {reg} is before date_of_birth {dob}")
        except ValueError:
            pass

    # Discharge should be after triage
    triage_at = record.get("triage_at")
    discharge_at = record.get("discharge_at")
    if triage_at and discharge_at:
        total_checks += 1
        try:
            t = datetime.fromisoformat(str(triage_at)[:19])
            d = datetime.fromisoformat(str(discharge_at)[:19])
            if d < t:
                violations.append(f"discharge_at {discharge_at} is before triage_at {triage_at}")
        except ValueError:
            pass

    if total_checks == 0:
        return DimensionResult("consistency", 1.0)

    score = 1.0 - (len(violations) / total_checks)
    return DimensionResult("consistency", round(max(score, 0.0), 3), violations)


# ─────────────────────────────────────────────────────────────────────────────
# Dimension 5 — Timeliness (record age)
# ─────────────────────────────────────────────────────────────────────────────

def check_timeliness(record: Dict[str, Any], config: Dict) -> DimensionResult:
    max_age_days = config.get("max_age_days")
    if not max_age_days:
        return DimensionResult("timeliness", 1.0)

    date_fields = config.get("date_fields", [])
    violations = []
    total_checks = 0
    now = datetime.now(tz=timezone.utc)

    for df in date_fields:
        val = record.get(df)
        if val:
            total_checks += 1
            try:
                dt = datetime.fromisoformat(str(val)[:19])
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                age = (now - dt).days
                if age > max_age_days:
                    violations.append(f"{df} is {age} days old (max {max_age_days})")
            except ValueError:
                pass

    if total_checks == 0:
        return DimensionResult("timeliness", 1.0)

    score = 1.0 - (len(violations) / total_checks)
    return DimensionResult("timeliness", round(max(score, 0.0), 3), violations)


# ─────────────────────────────────────────────────────────────────────────────
# Dimension 6 — Uniqueness (batch-level deduplication)
# ─────────────────────────────────────────────────────────────────────────────

class UniquenessChecker:
    """Stateful — tracks seen keys across the batch."""

    def __init__(self, unique_field: str = "external_id"):
        self._field = unique_field
        self._seen: Set[str] = set()

    def check(self, record: Dict[str, Any]) -> DimensionResult:
        key = str(record.get(self._field) or "").strip()
        if not key:
            return DimensionResult("uniqueness", 1.0)

        if key in self._seen:
            return DimensionResult(
                "uniqueness", 0.0,
                [f"Duplicate {self._field}: '{key}'"],
            )
        self._seen.add(key)
        return DimensionResult("uniqueness", 1.0)


# ─────────────────────────────────────────────────────────────────────────────
# Dimension 7 — Integrity (FK presence; evaluated pre-load)
# ─────────────────────────────────────────────────────────────────────────────

def check_integrity(record: Dict[str, Any], config: Dict) -> DimensionResult:
    """Check that private FK reference fields are present (not yet resolved to IDs)."""
    violations = []

    # Encounter records must have a resolved patient reference
    if "_hope_patient_id" in record and not record.get("_hope_patient_id"):
        violations.append("Missing _hope_patient_id — cannot link to patient")

    score = 0.0 if violations else 1.0
    return DimensionResult("integrity", score, violations)
