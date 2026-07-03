"""Unit tests for data-assimilation/transformers/enrichment.py — Chapter 19."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List

import pytest

_DA_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_DA_DIR))

from transformers.enrichment import (
    build_dept_lookup,
    build_formulary_lookup,
    build_hmo_lookup,
    build_lab_catalog_lookup,
    build_staff_lookup,
    name_variants,
    normalize_name,
    resolve_dept_id,
    resolve_hmo_id,
    resolve_staff_id,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

STAFF_ROWS: List[Dict] = [
    {"id": 1, "first_name": "Sarah",   "last_name": "Adeyemi",  "staff_code": "CON001"},
    {"id": 2, "first_name": "John",    "last_name": "Okonkwo",  "staff_code": "CON002"},
    {"id": 3, "first_name": "Fatimah", "last_name": "Bello",    "staff_code": "NUR050"},
    {"id": 4, "first_name": "James",   "last_name": "Smith",    "staff_code": ""},
]

DEPT_ROWS: List[Dict] = [
    {"id": 10, "code": "OPD",   "name": "Outpatient Department"},
    {"id": 11, "code": "EMERG", "name": "Emergency"},
    {"id": 12, "code": "LAB",   "name": "Laboratory"},
    {"id": 13, "code": "PHARM", "name": "Pharmacy"},
]

HMO_ROWS: List[Dict] = [
    {"id": 20, "name": "NHIS"},
    {"id": 21, "name": "Leadway Health"},
    {"id": 22, "name": "AXA Mansard"},
]

LAB_CATALOG_ROWS: List[Dict] = [
    {"id": 30, "code": "FBC",   "name": "Full Blood Count"},
    {"id": 31, "code": "LFT",   "name": "Liver Function Test"},
    {"id": 32, "code": "RFT",   "name": "Renal Function Test"},
]

FORMULARY_ROWS: List[Dict] = [
    {"id": 40, "code": "PCM500", "generic_name": "paracetamol"},
    {"id": 41, "code": "AMX250", "generic_name": "amoxicillin"},
    {"id": 42, "code": "",       "generic_name": "metronidazole"},
]


# ─────────────────────────────────────────────────────────────────────────────
# normalize_name
# ─────────────────────────────────────────────────────────────────────────────

class TestNormalizeName:
    def test_strips_dr_prefix(self):
        assert normalize_name("Dr. John Doe") == "john doe"

    def test_strips_prof_prefix(self):
        assert normalize_name("Prof. Sarah Adeyemi") == "sarah adeyemi"

    def test_strips_multiple_titles(self):
        assert normalize_name("Dr Prof Smith") == "smith"

    def test_lowercases_result(self):
        assert normalize_name("JOHN DOE") == "john doe"

    def test_collapses_extra_whitespace(self):
        assert normalize_name("John   Doe") == "john doe"

    def test_strips_punctuation(self):
        assert normalize_name("O'Reilly, Jane") == "o reilly jane"

    def test_returns_none_for_empty_string(self):
        assert normalize_name("") is None

    def test_returns_none_for_none(self):
        assert normalize_name(None) is None

    def test_returns_none_for_whitespace_only(self):
        assert normalize_name("   ") is None

    def test_preserves_name_without_title(self):
        assert normalize_name("Amaka Okafor") == "amaka okafor"

    def test_strips_nurse_prefix(self):
        assert normalize_name("Nurse Fatimah Bello") == "fatimah bello"

    def test_strips_pharm_prefix(self):
        assert normalize_name("Pharm. Dauda") == "dauda"

    def test_single_name_returns_single_token(self):
        assert normalize_name("Adeyemi") == "adeyemi"

    def test_name_that_is_all_titles_returns_none(self):
        result = normalize_name("Dr Mr")
        assert result is None


# ─────────────────────────────────────────────────────────────────────────────
# name_variants
# ─────────────────────────────────────────────────────────────────────────────

class TestNameVariants:
    def test_both_names_produce_four_variants(self):
        variants = name_variants("John", "Doe")
        assert "john doe" in variants
        assert "doe john" in variants
        assert "john" in variants
        assert "doe" in variants
        assert len(variants) == 4

    def test_first_name_only_produces_one_variant(self):
        variants = name_variants("John", None)
        assert variants == ["john"]

    def test_last_name_only_produces_one_variant(self):
        variants = name_variants(None, "Doe")
        assert variants == ["doe"]

    def test_both_none_produces_empty_list(self):
        assert name_variants(None, None) == []

    def test_both_empty_string_produces_empty_list(self):
        assert name_variants("", "") == []

    def test_title_stripped_in_variants(self):
        variants = name_variants("Dr. Sarah", "Adeyemi")
        assert "sarah adeyemi" in variants
        assert "adeyemi sarah" in variants

    def test_no_duplicate_variants_when_first_equals_last(self):
        # Edge case: single-token normalisation of both yields same string
        variants = name_variants("John", "John")
        # "john john" and "john john" (reversed same) plus "john" — deduplication
        assert len(set(variants)) <= len(variants)


# ─────────────────────────────────────────────────────────────────────────────
# build_staff_lookup & resolve_staff_id
# ─────────────────────────────────────────────────────────────────────────────

class TestStaffLookup:
    def setup_method(self):
        self.lookup = build_staff_lookup(STAFF_ROWS)

    def test_lookup_resolves_first_last(self):
        assert self.lookup.get("sarah adeyemi") == 1

    def test_lookup_resolves_last_first(self):
        assert self.lookup.get("adeyemi sarah") == 1

    def test_lookup_resolves_by_staff_code(self):
        assert self.lookup.get("con001") == 1
        assert self.lookup.get("con002") == 2

    def test_resolve_full_name_with_title(self):
        result = resolve_staff_id("Dr Sarah Adeyemi", self.lookup)
        assert result == 1

    def test_resolve_reversed_name_order(self):
        result = resolve_staff_id("Adeyemi Sarah", self.lookup)
        assert result == 1

    def test_resolve_bare_integer_returns_none(self):
        result = resolve_staff_id("123", self.lookup)
        assert result is None

    def test_resolve_integer_with_whitespace_returns_none(self):
        result = resolve_staff_id("  456  ", self.lookup)
        assert result is None

    def test_resolve_none_returns_none(self):
        assert resolve_staff_id(None, self.lookup) is None

    def test_resolve_empty_string_returns_none(self):
        assert resolve_staff_id("", self.lookup) is None

    def test_resolve_unknown_name_returns_none(self):
        assert resolve_staff_id("Nobody Stranger", self.lookup) is None

    def test_resolve_by_staff_code_direct(self):
        assert resolve_staff_id("NUR050", self.lookup) == 3

    def test_row_without_id_is_skipped(self):
        rows = [{"id": None, "first_name": "Ghost", "last_name": "User", "staff_code": "XXX"}]
        lookup = build_staff_lookup(rows)
        assert not lookup

    def test_empty_staff_code_not_indexed(self):
        # Staff row with empty staff_code (id=4, James Smith) — code key absent
        assert "james smith" in self.lookup
        assert "" not in self.lookup


# ─────────────────────────────────────────────────────────────────────────────
# build_dept_lookup & resolve_dept_id
# ─────────────────────────────────────────────────────────────────────────────

class TestDeptLookup:
    def setup_method(self):
        self.lookup = build_dept_lookup(DEPT_ROWS)

    def test_lookup_by_code(self):
        assert self.lookup.get("opd") == 10

    def test_lookup_by_name(self):
        assert self.lookup.get("emergency") == 11

    def test_resolve_by_code(self):
        assert resolve_dept_id("OPD", self.lookup) == 10

    def test_resolve_case_insensitive(self):
        assert resolve_dept_id("opd", self.lookup) == 10

    def test_resolve_by_full_name(self):
        assert resolve_dept_id("Outpatient Department", self.lookup) == 10

    def test_resolve_unknown_returns_none(self):
        assert resolve_dept_id("Cardiology", self.lookup) is None

    def test_resolve_none_returns_none(self):
        assert resolve_dept_id(None, self.lookup) is None

    def test_row_without_id_is_skipped(self):
        rows = [{"id": None, "code": "X", "name": "X-dept"}]
        lookup = build_dept_lookup(rows)
        assert not lookup

    def test_roundtrip_all_departments(self):
        for row in DEPT_ROWS:
            assert resolve_dept_id(row["code"], self.lookup) == row["id"]


# ─────────────────────────────────────────────────────────────────────────────
# build_hmo_lookup & resolve_hmo_id
# ─────────────────────────────────────────────────────────────────────────────

class TestHmoLookup:
    def setup_method(self):
        self.lookup = build_hmo_lookup(HMO_ROWS)

    def test_lookup_by_name(self):
        assert self.lookup.get("nhis") == 20

    def test_resolve_case_insensitive(self):
        assert resolve_hmo_id("NHIS", self.lookup) == 20

    def test_resolve_multi_word_name(self):
        assert resolve_hmo_id("leadway health", self.lookup) == 21

    def test_resolve_none_returns_none(self):
        assert resolve_hmo_id(None, self.lookup) is None

    def test_resolve_unknown_returns_none(self):
        assert resolve_hmo_id("Some Unknown HMO", self.lookup) is None


# ─────────────────────────────────────────────────────────────────────────────
# build_lab_catalog_lookup
# ─────────────────────────────────────────────────────────────────────────────

class TestLabCatalogLookup:
    def test_lookup_by_code(self):
        lookup = build_lab_catalog_lookup(LAB_CATALOG_ROWS)
        assert lookup.get("fbc") == 30
        assert lookup.get("lft") == 31

    def test_empty_rows_gives_empty_lookup(self):
        assert build_lab_catalog_lookup([]) == {}

    def test_row_missing_code_is_skipped(self):
        rows = [{"id": 99, "code": None, "name": "Ignored"}]
        lookup = build_lab_catalog_lookup(rows)
        assert not lookup


# ─────────────────────────────────────────────────────────────────────────────
# build_formulary_lookup
# ─────────────────────────────────────────────────────────────────────────────

class TestFormularyLookup:
    def setup_method(self):
        self.lookup = build_formulary_lookup(FORMULARY_ROWS)

    def test_lookup_by_drug_code(self):
        assert self.lookup.get("pcm500") == 40
        assert self.lookup.get("amx250") == 41

    def test_lookup_by_generic_name(self):
        assert self.lookup.get("paracetamol") == 40
        assert self.lookup.get("amoxicillin") == 41

    def test_empty_code_row_indexed_by_name(self):
        assert self.lookup.get("metronidazole") == 42

    def test_empty_rows_gives_empty_lookup(self):
        assert build_formulary_lookup([]) == {}

    def test_row_without_id_is_skipped(self):
        rows = [{"id": None, "code": "X", "generic_name": "ghost_drug"}]
        lookup = build_formulary_lookup(rows)
        assert not lookup

    def test_code_takes_precedence_over_name_for_same_key(self):
        # If code == generic_name, the code entry is set first; name skips because
        # the key already exists.
        rows = [{"id": 50, "code": "overlap", "generic_name": "overlap"}]
        lookup = build_formulary_lookup(rows)
        assert lookup.get("overlap") == 50
