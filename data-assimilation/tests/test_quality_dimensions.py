"""Unit tests for data-assimilation/quality/dimensions.py — Chapter 19."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Allow direct import from the data-assimilation root
_DA_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_DA_DIR))

from quality.dimensions import (
    DOMAIN_CONFIGS,
    DimensionResult,
    RecordQualityReport,
    UniquenessChecker,
    check_accuracy,
    check_completeness,
    check_consistency,
    check_integrity,
    check_timeliness,
    check_validity,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

_PATIENT_CFG = DOMAIN_CONFIGS["patients"]
_ENCOUNTER_CFG = DOMAIN_CONFIGS["encounters"]
_LAB_CFG = DOMAIN_CONFIGS["lab_orders"]
_BILLING_CFG = DOMAIN_CONFIGS["billing"]


def _full_patient(**overrides):
    base = {
        "mrn": "RH16-12345",
        "first_name": "Amaka",
        "last_name": "Okafor",
        "date_of_birth": "1990-03-15",
        "gender": "female",
        "phone": "08012345678",
        "registered_at": "2020-01-01",
    }
    return {**base, **overrides}


def _full_encounter(**overrides):
    base = {
        "patient_id": 1,
        "encounter_type": "outpatient",
        "status": "waiting",
        "triage_at": "2026-06-27T08:00:00",
        "discharge_at": None,
    }
    return {**base, **overrides}


# ─────────────────────────────────────────────────────────────────────────────
# 1. Completeness
# ─────────────────────────────────────────────────────────────────────────────

class TestCompleteness:
    def test_all_required_present_scores_1(self):
        rec = _full_patient()
        result = check_completeness(rec, _PATIENT_CFG)
        assert result.score == 1.0
        assert result.passed

    def test_missing_one_required_field_reduces_score(self):
        rec = _full_patient()
        del rec["mrn"]
        result = check_completeness(rec, _PATIENT_CFG)
        assert result.score < 1.0
        assert not result.passed
        assert any("mrn" in v.lower() for v in result.violations)

    def test_all_required_missing_scores_0(self):
        rec = {"date_of_birth": "1990-01-01"}
        result = check_completeness(rec, _PATIENT_CFG)
        assert result.score == 0.0
        assert len(result.violations) == 3   # mrn, first_name, last_name

    def test_empty_string_counts_as_missing(self):
        rec = _full_patient(first_name="")
        result = check_completeness(rec, _PATIENT_CFG)
        assert result.score < 1.0
        assert any("first_name" in v for v in result.violations)

    def test_whitespace_only_counts_as_missing(self):
        rec = _full_patient(last_name="   ")
        result = check_completeness(rec, _PATIENT_CFG)
        assert not result.passed

    def test_no_required_fields_scores_1(self):
        result = check_completeness({}, {})
        assert result.score == 1.0

    def test_encounter_missing_patient_id_fails(self):
        rec = _full_encounter(patient_id=None)
        result = check_completeness(rec, _ENCOUNTER_CFG)
        assert result.score < 1.0


# ─────────────────────────────────────────────────────────────────────────────
# 2. Validity
# ─────────────────────────────────────────────────────────────────────────────

class TestValidity:
    def test_valid_patient_record_scores_1(self):
        rec = _full_patient()
        result = check_validity(rec, _PATIENT_CFG)
        assert result.score == 1.0

    def test_invalid_gender_flagged(self):
        rec = _full_patient(gender="unknown_gender")   # not in controlled vocabulary
        result = check_validity(rec, _PATIENT_CFG)
        assert not result.passed
        assert any("gender" in v.lower() for v in result.violations)

    def test_gender_other_is_valid(self):
        rec = _full_patient(gender="other")
        result = check_validity(rec, _PATIENT_CFG)
        assert result.score == 1.0

    def test_bad_date_format_flagged(self):
        rec = _full_patient(date_of_birth="15/03/1990")  # DD/MM/YYYY not ISO
        result = check_validity(rec, _PATIENT_CFG)
        assert any("date" in v.lower() or "date_of_birth" in v for v in result.violations)

    def test_placeholder_lab_test_name_flagged(self):
        rec = {
            "patient_id": 1, "encounter_id": 2,
            "test_code": "FBC", "ordered_at": "2026-01-01",
            "test_name": "Lab Test",
        }
        result = check_validity(rec, _LAB_CFG)
        assert not result.passed
        assert any("placeholder" in v.lower() for v in result.violations)

    def test_empty_test_name_is_also_placeholder(self):
        rec = {
            "patient_id": 1, "encounter_id": 2,
            "test_code": "FBC", "ordered_at": "2026-01-01",
            "test_name": "",
        }
        result = check_validity(rec, _LAB_CFG)
        assert any("placeholder" in v.lower() for v in result.violations)

    def test_missing_optional_gender_not_flagged(self):
        rec = _full_patient()
        del rec["gender"]
        result = check_validity(rec, _PATIENT_CFG)
        assert result.score == 1.0


# ─────────────────────────────────────────────────────────────────────────────
# 3. Accuracy
# ─────────────────────────────────────────────────────────────────────────────

class TestAccuracy:
    def test_valid_dob_scores_1(self):
        rec = {"date_of_birth": "1985-07-20"}
        result = check_accuracy(rec, _PATIENT_CFG)
        assert result.score == 1.0

    def test_future_dob_flagged(self):
        rec = {"date_of_birth": "2090-01-01"}
        result = check_accuracy(rec, _PATIENT_CFG)
        assert not result.passed
        assert any("future" in v.lower() for v in result.violations)

    def test_implausibly_old_dob_flagged(self):
        rec = {"date_of_birth": "1800-01-01"}
        result = check_accuracy(rec, _PATIENT_CFG)
        assert not result.passed
        assert any("130" in v for v in result.violations)

    def test_zero_consultation_fee_not_waived_flagged(self):
        rec = {"consultation_fee": 0, "status": "pending"}
        result = check_accuracy(rec, _BILLING_CFG)
        assert not result.passed
        assert any("zero" in v.lower() for v in result.violations)

    def test_zero_consultation_fee_waived_ok(self):
        rec = {"consultation_fee": 0, "status": "waived"}
        result = check_accuracy(rec, _BILLING_CFG)
        assert result.score == 1.0

    def test_no_accuracy_checks_scores_1(self):
        rec = {"encounter_type": "outpatient", "status": "waiting"}
        result = check_accuracy(rec, _ENCOUNTER_CFG)
        assert result.score == 1.0


# ─────────────────────────────────────────────────────────────────────────────
# 4. Consistency
# ─────────────────────────────────────────────────────────────────────────────

class TestConsistency:
    def test_valid_encounter_no_violations(self):
        rec = _full_encounter(
            triage_at="2026-06-27T08:00:00",
            discharge_at="2026-06-27T14:00:00",
        )
        result = check_consistency(rec, _ENCOUNTER_CFG)
        assert result.score == 1.0

    def test_discharge_before_triage_flagged(self):
        rec = _full_encounter(
            triage_at="2026-06-27T14:00:00",
            discharge_at="2026-06-27T08:00:00",
        )
        result = check_consistency(rec, _ENCOUNTER_CFG)
        assert not result.passed
        assert any("discharge" in v.lower() for v in result.violations)

    def test_registration_before_dob_flagged(self):
        rec = _full_patient(
            date_of_birth="1990-01-01",
            registered_at="1985-06-15",
        )
        result = check_consistency(rec, _PATIENT_CFG)
        assert not result.passed
        assert any("registered_at" in v or "date_of_birth" in v for v in result.violations)

    def test_no_cross_fields_scores_1(self):
        rec = {"patient_id": 1, "encounter_type": "outpatient", "status": "waiting"}
        result = check_consistency(rec, _ENCOUNTER_CFG)
        assert result.score == 1.0

    def test_null_discharge_no_consistency_error(self):
        rec = _full_encounter(triage_at="2026-06-27T08:00:00", discharge_at=None)
        result = check_consistency(rec, _ENCOUNTER_CFG)
        assert result.score == 1.0


# ─────────────────────────────────────────────────────────────────────────────
# 5. Timeliness
# ─────────────────────────────────────────────────────────────────────────────

class TestTimeliness:
    def test_no_max_age_always_passes(self):
        rec = _full_patient(registered_at="2000-01-01")
        result = check_timeliness(rec, _PATIENT_CFG)
        assert result.score == 1.0

    def test_recent_record_within_limit_passes(self):
        cfg = {**_PATIENT_CFG, "max_age_days": 365 * 100}
        rec = _full_patient(registered_at="2026-01-01")
        result = check_timeliness(rec, cfg)
        assert result.score == 1.0

    def test_old_record_outside_limit_flagged(self):
        cfg = {**_PATIENT_CFG, "max_age_days": 1}
        rec = _full_patient(date_of_birth="1990-01-01", registered_at="2000-01-01")
        result = check_timeliness(rec, cfg)
        assert not result.passed


# ─────────────────────────────────────────────────────────────────────────────
# 6. Uniqueness
# ─────────────────────────────────────────────────────────────────────────────

class TestUniqueness:
    def test_first_occurrence_passes(self):
        checker = UniquenessChecker("external_id")
        result = checker.check({"external_id": "ENC-001"})
        assert result.score == 1.0

    def test_duplicate_fails_on_second_check(self):
        checker = UniquenessChecker("external_id")
        checker.check({"external_id": "ENC-001"})
        result = checker.check({"external_id": "ENC-001"})
        assert result.score == 0.0
        assert any("duplicate" in v.lower() for v in result.violations)

    def test_different_keys_both_pass(self):
        checker = UniquenessChecker("external_id")
        r1 = checker.check({"external_id": "ENC-001"})
        r2 = checker.check({"external_id": "ENC-002"})
        assert r1.score == 1.0
        assert r2.score == 1.0

    def test_missing_key_field_passes_without_flagging(self):
        checker = UniquenessChecker("external_id")
        result = checker.check({"some_field": "value"})
        assert result.score == 1.0

    def test_uniqueness_checker_accumulates_across_calls(self):
        checker = UniquenessChecker("mrn")
        for i in range(5):
            checker.check({"mrn": f"RH-{i:03d}"})
        assert len(checker._seen) == 5
        dup_result = checker.check({"mrn": "RH-000"})
        assert dup_result.score == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# 7. Integrity
# ─────────────────────────────────────────────────────────────────────────────

class TestIntegrity:
    def test_record_without_hope_patient_id_key_passes(self):
        rec = {"patient_id": 1, "encounter_type": "outpatient"}
        result = check_integrity(rec, _ENCOUNTER_CFG)
        assert result.score == 1.0

    def test_record_with_none_hope_patient_id_fails(self):
        rec = {"patient_id": None, "_hope_patient_id": None}
        result = check_integrity(rec, _ENCOUNTER_CFG)
        assert result.score == 0.0
        assert any("_hope_patient_id" in v for v in result.violations)

    def test_record_with_set_hope_patient_id_passes(self):
        rec = {"patient_id": 5, "_hope_patient_id": 42}
        result = check_integrity(rec, _ENCOUNTER_CFG)
        assert result.score == 1.0


# ─────────────────────────────────────────────────────────────────────────────
# RecordQualityReport aggregation
# ─────────────────────────────────────────────────────────────────────────────

class TestRecordQualityReport:
    def _report(self, **scores) -> RecordQualityReport:
        r = RecordQualityReport(entity="patients", record_key="RH-001")
        r.scores = scores
        return r

    def test_perfect_scores_overall_1(self):
        r = self._report(completeness=1.0, validity=1.0, accuracy=1.0, consistency=1.0)
        assert r.overall_score == 1.0
        assert r.passed

    def test_overall_score_is_mean(self):
        r = self._report(completeness=0.5, validity=1.0)
        assert r.overall_score == pytest.approx(0.75)

    def test_empty_scores_gives_0(self):
        r = RecordQualityReport(entity="patients", record_key="X")
        assert r.overall_score == 0.0

    def test_is_hard_fail_when_completeness_below_threshold(self):
        r = self._report(completeness=0.3, validity=1.0, integrity=1.0)
        assert r.is_hard_fail

    def test_is_hard_fail_when_integrity_below_threshold(self):
        r = self._report(completeness=1.0, validity=1.0, integrity=0.0)
        assert r.is_hard_fail

    def test_not_hard_fail_when_non_critical_dimension_low(self):
        r = self._report(completeness=1.0, integrity=1.0, accuracy=0.2)
        assert not r.is_hard_fail

    def test_passed_requires_overall_70_percent(self):
        r = self._report(completeness=1.0, validity=0.5, integrity=0.5)
        # mean = 0.667 < 0.7
        assert not r.passed

    def test_passed_at_exactly_70_percent(self):
        r = self._report(completeness=1.0, validity=0.7, integrity=0.4)
        # mean = 0.7
        assert r.passed


# ─────────────────────────────────────────────────────────────────────────────
# DimensionResult helpers
# ─────────────────────────────────────────────────────────────────────────────

class TestDimensionResult:
    def test_no_violations_is_passed(self):
        dr = DimensionResult("completeness", 1.0)
        assert dr.passed

    def test_any_violation_is_not_passed(self):
        dr = DimensionResult("completeness", 0.5, ["Missing mrn"])
        assert not dr.passed

    def test_dimension_name_stored(self):
        dr = DimensionResult("validity", 0.8, [])
        assert dr.dimension == "validity"
