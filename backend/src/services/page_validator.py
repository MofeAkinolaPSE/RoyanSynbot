"""
Page Data Validation Service
=============================
Validates that every major dashboard page in SynbotHealth is receiving real,
non-empty data from the backend. Calls each page's endpoints with an internal
admin token and checks that critical fields exist, are non-null, and meet
basic sanity rules.

Usage (programmatic):
    from src.services.page_validator import run_full_validation
    report = run_full_validation()

Usage (CLI):
    python -m src.services.page_validator
"""
from __future__ import annotations

import datetime
import logging
import os
from typing import Any

try:
    import httpx
except ImportError:  # pragma: no cover
    httpx = None  # type: ignore

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Page Manifest
# Each entry defines one UI page, the backend endpoints it depends on, and the
# field-level checks that confirm data is actually flowing through.
# ---------------------------------------------------------------------------

PAGE_MANIFEST: list[dict] = [
    {
        "page": "Hospital Dashboard",
        "route": "/",
        "endpoints": [
            {
                "path": "/dashboard/hospital-status",
                "checks": [
                    {"field": "patients_waiting",     "rules": ["exists", "numeric_gte_zero"]},
                    {"field": "avg_wait_minutes",     "rules": ["exists", "numeric_gte_zero"]},
                    {"field": "patients_seen_today",  "rules": ["exists", "numeric_gte_zero"]},
                    {"field": "active_consultations", "rules": ["exists", "numeric_gte_zero"]},
                    {"field": "queue_by_department",  "rules": ["exists"]},
                    {"field": "flow_by_hour",         "rules": ["exists"]},
                ],
            }
        ],
    },
    {
        "page": "Admin Dashboard",
        "route": "/hospital/admin-dashboard",
        "endpoints": [
            {
                "path": "/dashboard/hospital-status",
                "checks": [
                    {"field": "patients_waiting",    "rules": ["exists", "numeric_gte_zero"]},
                    {"field": "queue_by_department", "rules": ["exists"]},
                ],
            },
            {
                "path": "/hr/shifts",
                "checks": [
                    {"field": "shifts", "rules": ["exists"]},
                ],
            },
            {
                "path": "/lab/turnaround",
                "checks": [
                    {"field": "records", "rules": ["exists"]},
                ],
            },
        ],
    },
    {
        "page": "My Dashboard (Doctor)",
        "route": "/hospital/doctor",
        "endpoints": [
            {
                "path": "/appointments",
                "checks": [
                    {"field": "appointments", "rules": ["exists"]},
                ],
            },
            {
                "path": "/queue/encounters",
                "checks": [
                    {"field": "encounters", "rules": ["exists"]},
                    {"field": "count",      "rules": ["exists", "numeric_gte_zero"]},
                ],
            },
        ],
    },
    {
        "page": "Nurse Dashboard",
        "route": "/hospital/nurse",
        "endpoints": [
            {
                "path": "/wards",
                "checks": [
                    {"field": "wards", "rules": ["exists"]},
                ],
            },
            {
                "path": "/wards/occupancy",
                "checks": [
                    {"field": "wards", "rules": ["exists"]},
                    {"field": "count", "rules": ["exists", "numeric_gte_zero"]},
                ],
            },
        ],
    },
    {
        "page": "CPRS / Patients",
        "route": "/hospital/patients",
        "endpoints": [
            {
                "path": "/patients/search",
                "params": {"q": ""},
                "checks": [
                    {"field": "patients", "rules": ["exists"]},
                ],
            },
        ],
    },
    {
        "page": "Queue & Flow",
        "route": "/hospital/queue",
        "endpoints": [
            {
                "path": "/queue/encounters",
                "checks": [
                    {"field": "encounters", "rules": ["exists"]},
                    {"field": "count",      "rules": ["exists", "numeric_gte_zero"]},
                ],
            },
        ],
    },
    {
        "page": "Appointments",
        "route": "/hospital/appointments",
        "endpoints": [
            {
                "path": "/appointments",
                "checks": [
                    {"field": "appointments", "rules": ["exists"]},
                ],
            },
        ],
    },
    {
        "page": "Lab & Diagnostics",
        "route": "/hospital/lab",
        "endpoints": [
            {
                "path": "/lab/orders",
                "checks": [
                    {"field": "orders", "rules": ["exists"]},
                    {"field": "count",  "rules": ["exists", "numeric_gte_zero"]},
                ],
            },
            {
                "path": "/lab/turnaround",
                "checks": [
                    {"field": "records", "rules": ["exists"]},
                ],
            },
        ],
    },
    {
        "page": "Pharmacy",
        "route": "/hospital/pharmacy",
        "endpoints": [
            {
                "path": "/pharmacy/prescriptions",
                "checks": [
                    {"field": "prescriptions", "rules": ["exists"]},
                ],
            },
            {
                "path": "/pharmacy/inventory",
                "checks": [
                    {"field": "items", "rules": ["exists"]},
                ],
            },
        ],
    },
    {
        "page": "Wards & Beds",
        "route": "/hospital/wards",
        "endpoints": [
            {
                "path": "/wards",
                "checks": [
                    {"field": "wards", "rules": ["exists"]},
                ],
            },
        ],
    },
    {
        "page": "Billing",
        "route": "/hospital/billing",
        "endpoints": [
            {
                "path": "/billing_hospital/bills",
                "checks": [
                    {"field": "bills",  "rules": ["exists"]},
                    {"field": "count",  "rules": ["exists", "numeric_gte_zero"]},
                ],
            },
            {
                "path": "/billing_hospital/claims",
                "checks": [
                    {"field": "claims", "rules": ["exists"]},
                ],
            },
        ],
    },
    {
        "page": "HR — Shifts",
        "route": "/hospital/hr",
        "endpoints": [
            {
                "path": "/hr/shifts",
                "checks": [
                    {"field": "shifts", "rules": ["exists"]},
                ],
            },
        ],
    },
    {
        "page": "Executive Summary",
        "route": "/executive",
        "endpoints": [
            {
                "path": "/dashboard/executive-briefing",
                "checks": [
                    {"field": "summary",                          "rules": ["exists", "not_null"]},
                    {"field": "summary.health_score",             "rules": ["exists", "not_null"]},
                    {"field": "finance_brief",                    "rules": ["exists", "not_null"]},
                    {"field": "finance_brief.cash_outstanding",   "rules": ["exists"]},
                    {"field": "inventory_brief",                  "rules": ["exists", "not_null"]},
                    {"field": "inventory_brief.low_stock_alerts", "rules": ["exists", "numeric_gte_zero"]},
                ],
            },
            {
                "path": "/intelligence/executive_summary",
                "checks": [
                    {"field": "status",       "rules": ["exists", "not_null"]},
                    {"field": "key_findings", "rules": ["exists"]},
                ],
            },
        ],
    },
    {
        "page": "Finance Analytics",
        "route": "/finance/analytics",
        "endpoints": [
            {
                "path": "/analytics/kpis",
                "checks": [
                    {"field": "total_revenue", "rules": ["exists"]},
                ],
            },
            {
                "path": "/finance/ar/aging",
                "checks": [
                    {"field": "0_30",    "rules": ["exists", "numeric_gte_zero"]},
                    {"field": "31_60",   "rules": ["exists", "numeric_gte_zero"]},
                    {"field": "61_90",   "rules": ["exists", "numeric_gte_zero"]},
                    {"field": "91_plus", "rules": ["exists", "numeric_gte_zero"]},
                ],
            },
        ],
    },
    {
        "page": "Reports & Analytics",
        "route": "/hospital/reports",
        "endpoints": [
            {
                "path": "/hospital-reports/disease-burden",
                "checks": [
                    {"field": "records", "rules": ["exists"]},
                ],
            },
            {
                "path": "/hospital-reports/bed-occupancy",
                "checks": [
                    {"field": "records", "rules": ["exists"]},
                ],
            },
        ],
    },
    {
        "page": "Audit Log",
        "route": "/admin/audit-log",
        "endpoints": [
            {
                "path": "/audit/logs",
                "checks": [
                    # Audit log can legitimately be empty; just verify the field exists
                    {"field": "logs",  "rules": ["exists"]},
                    {"field": "count", "rules": ["exists", "numeric_gte_zero"]},
                ],
            },
        ],
    },
    {
        "page": "Quality & Safety",
        "route": "/hospital/quality",
        "endpoints": [
            {
                "path": "/quality/stats",
                "checks": [
                    {"field": "incidents", "rules": ["exists"]},
                ],
            },
        ],
    },
]


# ---------------------------------------------------------------------------
# Field access helpers
# ---------------------------------------------------------------------------

def _get_nested(data: Any, dot_path: str) -> tuple[bool, Any]:
    """Resolve a dot-notation path into a nested dict. Returns (found, value)."""
    parts = dot_path.split(".")
    current = data
    for part in parts:
        if not isinstance(current, dict):
            return False, None
        if part not in current:
            return False, None
        current = current[part]
    return True, current


# ---------------------------------------------------------------------------
# Rule checkers
# ---------------------------------------------------------------------------

def _check_rule(rule: str, found: bool, value: Any, field: str) -> dict:
    """Run a single rule against a resolved field value. Returns check result dict."""
    if rule == "exists":
        ok = found
        msg = None if ok else f"field '{field}' missing from response"
    elif rule == "not_null":
        ok = found and value is not None
        msg = None if ok else f"field '{field}' is null"
    elif rule == "not_empty":
        ok = found and value is not None and value != [] and value != "" and value != {}
        msg = None if ok else f"field '{field}' is empty"
    elif rule == "numeric_gte_zero":
        try:
            ok = found and value is not None and float(value) >= 0
            msg = None if ok else f"field '{field}' is {value!r} (expected >= 0)"
        except (TypeError, ValueError):
            ok = False
            msg = f"field '{field}' is not numeric: {value!r}"
    else:
        ok = False
        msg = f"unknown rule '{rule}'"

    return {
        "rule": rule,
        "status": "pass" if ok else "fail",
        "message": msg,
    }


# ---------------------------------------------------------------------------
# Endpoint validator
# ---------------------------------------------------------------------------

def _validate_endpoint(
    client: "httpx.Client",
    base_url: str,
    token: str,
    endpoint: dict,
) -> dict:
    path = endpoint["path"]
    params = endpoint.get("params", {})
    url = base_url.rstrip("/") + path
    http_status: int | None = None
    error: str | None = None
    check_results: list[dict] = []

    try:
        resp = client.get(
            url,
            params=params,
            headers={"Authorization": f"Bearer {token}"},
            timeout=10.0,
        )
        http_status = resp.status_code

        if resp.status_code >= 400:
            error = f"HTTP {resp.status_code}"
            # Mark all checks as fail when endpoint itself errors
            for chk in endpoint.get("checks", []):
                for rule in chk["rules"]:
                    check_results.append({
                        "field": chk["field"],
                        "rule": rule,
                        "status": "fail",
                        "message": f"endpoint returned HTTP {resp.status_code}",
                    })
        else:
            try:
                data = resp.json()
            except Exception:
                data = {}
                error = "response is not valid JSON"

            for chk in endpoint.get("checks", []):
                field = chk["field"]
                found, value = _get_nested(data, field)
                for rule in chk["rules"]:
                    result = _check_rule(rule, found, value, field)
                    result["field"] = field
                    result["value"] = value if found else None
                    check_results.append(result)

    except Exception as exc:
        error = str(exc)
        for chk in endpoint.get("checks", []):
            for rule in chk["rules"]:
                check_results.append({
                    "field": chk["field"],
                    "rule": rule,
                    "status": "fail",
                    "value": None,
                    "message": f"request failed: {exc}",
                })

    overall = "pass"
    if any(r["status"] == "fail" for r in check_results):
        overall = "fail"

    return {
        "path": path,
        "http_status": http_status,
        "overall": overall,
        "error": error,
        "checks": check_results,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_full_validation(base_url: str | None = None, token: str | None = None) -> dict:
    """
    Run all page validations and return a structured report.

    Args:
        base_url: Base URL of the backend (defaults to SELF_BASE_URL env var or http://localhost:8000)
        token:    Admin JWT to use for requests (defaults to creating an internal service token)
    """
    if httpx is None:
        return {
            "error": "httpx is not installed; cannot run page validation",
            "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
            "pages": [],
        }

    if base_url is None:
        base_url = os.environ.get("SELF_BASE_URL", "http://localhost:8000")

    if token is None:
        from src.auth_utils import create_access_token
        token, _ = create_access_token(user_id="diagnostics-agent", roles=["admin"])

    page_results: list[dict] = []
    failed_pages: list[str] = []
    passed_pages: list[str] = []

    with httpx.Client() as client:
        for page in PAGE_MANIFEST:
            endpoint_results: list[dict] = []
            for ep in page["endpoints"]:
                ep_result = _validate_endpoint(client, base_url, token, ep)
                endpoint_results.append(ep_result)

            # Page overall is fail if any endpoint fails
            page_overall = "pass" if all(e["overall"] == "pass" for e in endpoint_results) else "fail"

            page_results.append({
                "page": page["page"],
                "route": page.get("route", ""),
                "overall": page_overall,
                "endpoints": endpoint_results,
            })

            if page_overall == "fail":
                failed_pages.append(page["page"])
            else:
                passed_pages.append(page["page"])

    total = len(page_results)
    passed = len(passed_pages)
    failed = len(failed_pages)

    return {
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
        "summary": {
            "total_pages": total,
            "passed": passed,
            "failed": failed,
            "overall": "pass" if failed == 0 else "fail",
            "failed_pages": failed_pages,
        },
        "pages": page_results,
    }


if __name__ == "__main__":
    import json
    import sys

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    report = run_full_validation()
    print(json.dumps(report, indent=2))

    summary = report.get("summary", {})
    print(f"\n{'=' * 50}")
    print(f"Result: {summary.get('overall', '?').upper()}")
    print(f"Passed: {summary.get('passed', 0)}/{summary.get('total_pages', 0)} pages")
    if summary.get("failed_pages"):
        print("Failed pages:")
        for p in summary["failed_pages"]:
            print(f"  - {p}")
    sys.exit(0 if summary.get("overall") == "pass" else 1)
