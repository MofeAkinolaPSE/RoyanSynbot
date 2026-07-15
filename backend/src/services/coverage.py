"""Coverage calculation service for RoyanHealth HMO billing.

The service is deliberately rule-driven. Patient HMO data can arrive from
Synbot registration or the read-only Hope overlay, while coverage rules remain
owned by Synbot.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.constants import (
    TABLE_COVERAGE_RULES,
    TABLE_HMO_PLANS,
    TABLE_HMOS,
    TABLE_PATIENT_INSURANCE,
    TABLE_PATIENTS,
    TABLE_SERVICE_CATALOG,
)
from src.db import db


def _rows(result: Any) -> list[dict[str, Any]]:
    return list(getattr(result, "data", None) or [])


def _first(result: Any) -> dict[str, Any] | None:
    rows = _rows(result)
    return rows[0] if rows else None


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _service_lookup(*, service_id: int | None = None, service_code: str | None = None) -> dict[str, Any] | None:
    query = db.table(TABLE_SERVICE_CATALOG).select("*").eq("is_active", True).limit(1)
    if service_id is not None:
        query = query.eq("id", service_id)
    elif service_code:
        query = query.eq("service_code", service_code.strip())
    else:
        return None
    return _first(query.execute())


def _hmo_by_name(name: str | None) -> dict[str, Any] | None:
    if not name:
        return None
    return _first(
        db.table(TABLE_HMOS)
        .select("*")
        .ilike("name", name.strip())
        .eq("is_active", True)
        .limit(1)
        .execute()
    )


def _plan_by_id(plan_id: int | None) -> dict[str, Any] | None:
    if plan_id is None:
        return None
    return _first(db.table(TABLE_HMO_PLANS).select("*").eq("id", plan_id).limit(1).execute())


def get_active_patient_insurance(patient_id: int) -> dict[str, Any] | None:
    """Return the primary active patient policy, falling back to legacy patient HMO fields."""
    policy = _first(
        db.table(TABLE_PATIENT_INSURANCE)
        .select("*")
        .eq("patient_id", patient_id)
        .eq("is_primary", True)
        .eq("status", "active")
        .limit(1)
        .execute()
    )
    if policy:
        hmo = _first(db.table(TABLE_HMOS).select("*").eq("id", policy.get("hmo_id")).limit(1).execute())
        plan = _plan_by_id(policy.get("plan_id"))
        return {
            **policy,
            "hmo_name": (hmo or {}).get("name"),
            "plan_name": (plan or {}).get("name"),
            "legacy_only": False,
        }

    patient = _first(db.table(TABLE_PATIENTS).select("*").eq("id", patient_id).limit(1).execute())
    if not patient or not patient.get("hmo_provider"):
        return None
    hmo = _hmo_by_name(patient.get("hmo_provider"))
    return {
        "patient_id": patient_id,
        "hmo_id": (hmo or {}).get("id"),
        "plan_id": None,
        "membership_id": patient.get("hmo_id"),
        "status": "active",
        "hmo_name": patient.get("hmo_provider"),
        "plan_name": None,
        "legacy_only": True,
    }


def _coverage_rule(hmo_id: int | None, plan_id: int | None, service_id: int | None) -> dict[str, Any] | None:
    if not hmo_id or not service_id:
        return None

    if plan_id:
        exact = _first(
            db.table(TABLE_COVERAGE_RULES)
            .select("*")
            .eq("hmo_id", hmo_id)
            .eq("plan_id", plan_id)
            .eq("service_id", service_id)
            .eq("is_active", True)
            .limit(1)
            .execute()
        )
        if exact:
            return exact

    try:
        return _first(
            db.table(TABLE_COVERAGE_RULES)
            .select("*")
            .eq("hmo_id", hmo_id)
            .is_("plan_id", "null")
            .eq("service_id", service_id)
            .eq("is_active", True)
            .limit(1)
            .execute()
        )
    except Exception:
        return _first(
            db.table(TABLE_COVERAGE_RULES)
            .select("*")
            .eq("hmo_id", hmo_id)
            .eq("service_id", service_id)
            .eq("is_active", True)
            .limit(1)
            .execute()
        )


@dataclass(frozen=True)
class CoverageInput:
    patient_id: int
    service_id: int | None = None
    service_code: str | None = None
    service_name: str | None = None
    category: str = "misc"
    quantity: float = 1.0
    unit_price: float | None = None
    amount: float | None = None
    encounter_id: int | None = None


def calculate_coverage(payload: CoverageInput) -> dict[str, Any]:
    service = _service_lookup(service_id=payload.service_id, service_code=payload.service_code)
    unit_price = (
        _num(payload.unit_price, None) if payload.unit_price is not None
        else _num((service or {}).get("base_price"), 0.0)
    )
    quantity = max(_num(payload.quantity, 1.0), 0.0001)
    gross_amount = _num(payload.amount, quantity * _num(unit_price, 0.0))
    insurance = get_active_patient_insurance(payload.patient_id)

    service_snapshot = {
        "id": (service or {}).get("id") or payload.service_id,
        "service_code": (service or {}).get("service_code") or payload.service_code,
        "name": (service or {}).get("name") or payload.service_name or payload.service_code or "Uncatalogued service",
        "category": (service or {}).get("category") or payload.category or "misc",
        "base_price": _num((service or {}).get("base_price"), 0.0),
    }

    warnings: list[str] = []
    if not insurance:
        return {
            "patient_id": payload.patient_id,
            "encounter_id": payload.encounter_id,
            "service": service_snapshot,
            "insurance": {"active": False},
            "gross_amount": round(gross_amount, 2),
            "covered_amount": 0.0,
            "patient_amount": round(gross_amount, 2),
            "coverage_type": "none",
            "coverage_value": 0.0,
            "requires_approval": False,
            "approval_required_reason": None,
            "limit_type": "none",
            "limit_value": None,
            "limit_exceeded": False,
            "coverage_rule_id": None,
            "warnings": ["no_active_insurance"],
        }

    rule = _coverage_rule(insurance.get("hmo_id"), insurance.get("plan_id"), service_snapshot.get("id"))
    if not rule:
        warnings.append("no_matching_coverage_rule")
        return {
            "patient_id": payload.patient_id,
            "encounter_id": payload.encounter_id,
            "service": service_snapshot,
            "insurance": {
                "active": True,
                "hmo_id": insurance.get("hmo_id"),
                "hmo_name": insurance.get("hmo_name"),
                "plan_id": insurance.get("plan_id"),
                "plan_name": insurance.get("plan_name"),
                "membership_id": insurance.get("membership_id"),
                "legacy_only": bool(insurance.get("legacy_only")),
            },
            "gross_amount": round(gross_amount, 2),
            "covered_amount": 0.0,
            "patient_amount": round(gross_amount, 2),
            "coverage_type": "none",
            "coverage_value": 0.0,
            "requires_approval": False,
            "approval_required_reason": None,
            "limit_type": "none",
            "limit_value": None,
            "limit_exceeded": False,
            "coverage_rule_id": None,
            "warnings": warnings,
        }

    coverage_type = str(rule.get("coverage_type") or "none")
    coverage_value = _num(rule.get("coverage_value"), 0.0)
    if coverage_type == "percent":
        covered = gross_amount * min(max(coverage_value, 0.0), 100.0) / 100.0
    elif coverage_type == "fixed":
        covered = min(coverage_value, gross_amount)
    elif coverage_type == "capitation":
        covered = gross_amount
    else:
        covered = 0.0

    limit_type = str(rule.get("limit_type") or "none")
    limit_value = rule.get("limit_value")
    limit_exceeded = False
    if limit_type != "none" and limit_value is not None and covered > _num(limit_value):
        covered = _num(limit_value)
        limit_exceeded = True
        warnings.append("coverage_limit_applied")

    covered = round(max(0.0, min(covered, gross_amount)), 2)
    patient_amount = round(max(gross_amount - covered, 0.0), 2)
    requires_approval = bool(rule.get("requires_approval"))

    return {
        "patient_id": payload.patient_id,
        "encounter_id": payload.encounter_id,
        "service": service_snapshot,
        "insurance": {
            "active": True,
            "hmo_id": insurance.get("hmo_id"),
            "hmo_name": insurance.get("hmo_name"),
            "plan_id": insurance.get("plan_id"),
            "plan_name": insurance.get("plan_name"),
            "membership_id": insurance.get("membership_id"),
            "legacy_only": bool(insurance.get("legacy_only")),
        },
        "gross_amount": round(gross_amount, 2),
        "covered_amount": covered,
        "patient_amount": patient_amount,
        "coverage_type": coverage_type,
        "coverage_value": coverage_value,
        "requires_approval": requires_approval,
        "approval_required_reason": "pre_authorization_required" if requires_approval else None,
        "limit_type": limit_type,
        "limit_value": _num(limit_value) if limit_value is not None else None,
        "limit_exceeded": limit_exceeded,
        "coverage_rule_id": rule.get("id"),
        "warnings": warnings,
    }


def billing_breakdown_from_quotes(quotes: list[dict[str, Any]]) -> dict[str, float]:
    totals = {
        "consultation_fee": 0.0,
        "lab_charges": 0.0,
        "pharmacy_charges": 0.0,
        "ward_charges": 0.0,
        "procedure_charges": 0.0,
        "miscellaneous": 0.0,
        "hmo_covered": 0.0,
    }
    for quote in quotes:
        gross = _num(quote.get("gross_amount"))
        category = ((quote.get("service") or {}).get("category") or "misc").lower()
        if category == "consultation":
            totals["consultation_fee"] += gross
        elif category == "lab":
            totals["lab_charges"] += gross
        elif category == "pharmacy":
            totals["pharmacy_charges"] += gross
        elif category == "ward":
            totals["ward_charges"] += gross
        elif category in {"procedure", "imaging"}:
            totals["procedure_charges"] += gross
        else:
            totals["miscellaneous"] += gross
        totals["hmo_covered"] += _num(quote.get("covered_amount"))

    return {key: round(value, 2) for key, value in totals.items()}
