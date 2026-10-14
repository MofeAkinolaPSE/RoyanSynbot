from __future__ import annotations

import pytest

from src.constants import (
    TABLE_COVERAGE_RULES,
    TABLE_HMO_PLANS,
    TABLE_HMOS,
    TABLE_HOPE_SYNC_RUNS,
    TABLE_PATIENT_INSURANCE,
    TABLE_PATIENTS,
    TABLE_SERVICE_CATALOG,
)
from src.services import coverage as coverage_service
from src.services import hope_sync as hope_sync_service


class Result:
    def __init__(self, data=None):
        self.data = data or []
        self.count = len(self.data)


class Query:
    def __init__(self, fake, table):
        self.fake = fake
        self.table = table
        self.filters = []
        self.payload = None
        self.mode = "select"

    def select(self, *_args, **_kwargs):
        self.mode = "select"
        return self

    def eq(self, field, value):
        self.filters.append(("eq", field, value))
        return self

    def ilike(self, field, value):
        self.filters.append(("ilike", field, value))
        return self

    def is_(self, field, value):
        self.filters.append(("is", field, value))
        return self

    def limit(self, *_args):
        return self

    def order(self, *_args, **_kwargs):
        return self

    def insert(self, payload):
        self.mode = "insert"
        self.payload = payload
        return self

    def upsert(self, payload, **_kwargs):
        self.mode = "upsert"
        self.payload = payload
        return self

    def update(self, payload):
        self.mode = "update"
        self.payload = payload
        return self

    def execute(self):
        if self.mode == "insert":
            rows = self.payload if isinstance(self.payload, list) else [self.payload]
            stored = []
            for row in rows:
                materialized = dict(row)
                materialized.setdefault("id", len(self.fake.tables.setdefault(self.table, [])) + 1)
                self.fake.tables.setdefault(self.table, []).append(materialized)
                stored.append(materialized)
            return Result(stored)
        if self.mode == "upsert":
            rows = self.payload if isinstance(self.payload, list) else [self.payload]
            for row in rows:
                self.fake.upserts.append((self.table, dict(row)))
            return Result(rows)
        if self.mode == "update":
            self.fake.updates.append((self.table, dict(self.payload), list(self.filters)))
            return Result([self.payload])
        rows = list(self.fake.tables.get(self.table, []))
        for op, field, value in self.filters:
            if op == "eq":
                rows = [row for row in rows if row.get(field) == value]
            elif op == "ilike":
                needle = str(value).replace("%", "").lower()
                rows = [row for row in rows if needle in str(row.get(field, "")).lower()]
            elif op == "is":
                rows = [row for row in rows if row.get(field) is None and value in (None, "null")]
        return Result(rows)


class FakeDb:
    def __init__(self, tables):
        self.tables = tables
        self.upserts = []
        self.updates = []

    def table(self, table):
        return Query(self, table)

    def rpc(self, name, _payload):
        assert name == "generate_mrn"
        return Result([{"generate_mrn": "RH2026000001"}])


def test_coverage_quote_applies_percent_limit_and_approval(monkeypatch):
    fake = FakeDb({
        TABLE_PATIENT_INSURANCE: [{"id": 1, "patient_id": 10, "hmo_id": 1, "plan_id": None, "membership_id": "AXA-1", "status": "active", "is_primary": True}],
        TABLE_HMOS: [{"id": 1, "name": "AXA Mansard", "is_active": True}],
        TABLE_HMO_PLANS: [],
        TABLE_SERVICE_CATALOG: [{"id": 5, "service_code": "LAB-FBC", "name": "Full Blood Count", "category": "lab", "base_price": 10000, "is_active": True}],
        TABLE_COVERAGE_RULES: [{
            "id": 7,
            "hmo_id": 1,
            "plan_id": None,
            "service_id": 5,
            "coverage_type": "percent",
            "coverage_value": 80,
            "requires_approval": True,
            "limit_type": "per_visit",
            "limit_value": 5000,
            "is_active": True,
        }],
    })
    monkeypatch.setattr(coverage_service, "db", fake)

    quote = coverage_service.calculate_coverage(
        coverage_service.CoverageInput(patient_id=10, service_code="LAB-FBC", quantity=1, unit_price=10000)
    )

    assert quote["gross_amount"] == 10000
    assert quote["covered_amount"] == 5000
    assert quote["patient_amount"] == 5000
    assert quote["requires_approval"] is True
    assert quote["limit_exceeded"] is True


def test_coverage_quote_hmo_without_rule_bills_hmo_in_full(monkeypatch):
    """Royan's practice: an HMO patient pays nothing at the till unless a rule says so (co-pay, %, exclusion)."""
    fake = FakeDb({
        TABLE_PATIENT_INSURANCE: [{"id": 1, "patient_id": 10, "hmo_id": 1, "plan_id": None, "membership_id": "AV-1", "status": "active", "is_primary": True}],
        TABLE_HMOS: [{"id": 1, "name": "AVON", "is_active": True}],
        TABLE_HMO_PLANS: [],
        TABLE_SERVICE_CATALOG: [{"id": 5, "service_code": "CONSULT-GEN", "name": "General Consultation", "category": "consultation", "base_price": 5000, "is_active": True}],
        TABLE_COVERAGE_RULES: [],
    })
    monkeypatch.setattr(coverage_service, "db", fake)

    quote = coverage_service.calculate_coverage(
        coverage_service.CoverageInput(patient_id=10, service_code="CONSULT-GEN", quantity=1, unit_price=5000)
    )

    assert quote["insurance"]["active"] is True
    assert quote["covered_amount"] == 5000
    assert quote["patient_amount"] == 0
    assert quote["coverage_type"] == "default_full"
    assert "hmo_default_full_cover" in quote["warnings"]


def test_coverage_quote_without_insurance_charges_patient(monkeypatch):
    fake = FakeDb({
        TABLE_PATIENT_INSURANCE: [],
        TABLE_PATIENTS: [{"id": 10, "hmo_provider": None, "hmo_id": None}],
        TABLE_SERVICE_CATALOG: [{"id": 5, "service_code": "CONSULT-GEN", "name": "General Consultation", "category": "consultation", "base_price": 3000, "is_active": True}],
    })
    monkeypatch.setattr(coverage_service, "db", fake)

    quote = coverage_service.calculate_coverage(
        coverage_service.CoverageInput(patient_id=10, service_code="CONSULT-GEN", quantity=1, unit_price=3000)
    )

    assert quote["insurance"]["active"] is False
    assert quote["covered_amount"] == 0
    assert quote["patient_amount"] == 3000


def test_hope_sync_patients_normalizes_read_only_bridge_rows(monkeypatch):
    fake = FakeDb({
        TABLE_HOPE_SYNC_RUNS: [],
        TABLE_HMOS: [],
        TABLE_PATIENTS: [],
    })
    monkeypatch.setattr(hope_sync_service, "db", fake)

    result = hope_sync_service.sync_entity(
        "patients",
        fetcher=lambda _entity, _limit: [{
            "patient_id": "P-1",
            "mrn": "RH-1",
            "first_name": "Ada",
            "last_name": "Okafor",
            "gender": "F",
            "phone": "0801",
            "hmo": "Hygeia HMO",
            "updated_at": "2026-01-01T00:00:00Z",
        }],
    )

    assert result["status"] == "success"
    assert result["rows_seen"] == 1
    assert result["rows_upserted"] == 1
    assert any(table == TABLE_PATIENTS and row["external_source"] == "hope" and row["external_id"] == "P-1" for table, row in fake.upserts)
