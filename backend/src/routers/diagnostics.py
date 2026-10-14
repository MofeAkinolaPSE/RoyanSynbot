"""
Diagnostics Router
==================
Exposes a single endpoint that runs the full page data validation suite and
returns a structured JSON report. Protected by admin role.

Endpoint:
  GET /diagnostics/full   — Run all page checks, return per-page results
  GET /diagnostics/page/{page_name} — Run checks for a single page (URL-encoded name)
"""
from __future__ import annotations

import logging
import os
import urllib.parse
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request

from src.middleware import verify_jwt

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/diagnostics", tags=["Diagnostics"])


def _require_admin(request: Request) -> Dict[str, Any]:
    payload = verify_jwt(request)
    roles = payload.get("roles", [])
    if "admin" not in roles:
        raise HTTPException(status_code=403, detail="Admin role required for diagnostics")
    return payload


def _get_base_url() -> str:
    return os.environ.get("SELF_BASE_URL", "http://localhost:8000")


def _get_internal_token() -> str:
    from src.auth_utils import create_access_token
    token, _ = create_access_token(user_id="diagnostics-agent", roles=["admin"])
    return token


@router.get("/full")
def full_diagnostics(user: Dict[str, Any] = Depends(_require_admin)):
    """
    Run data validation checks across all dashboard pages and return a
    structured report showing which pages have healthy data and which are broken.
    """
    try:
        from src.services.page_validator import run_full_validation
        report = run_full_validation(
            base_url=_get_base_url(),
            token=_get_internal_token(),
        )
        return report
    except Exception as exc:
        logger.error("Diagnostics run failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Diagnostics failed: {exc}")


@router.get("/page/{page_name}")
def single_page_diagnostics(
    page_name: str,
    user: Dict[str, Any] = Depends(_require_admin),
):
    """
    Run validation checks for a single named page only.
    page_name should match the 'page' field in PAGE_MANIFEST (URL-encoded).
    Example: /diagnostics/page/Hospital%20Dashboard
    """
    try:
        from src.services.page_validator import PAGE_MANIFEST, run_full_validation
        decoded = urllib.parse.unquote(page_name)

        matching = [p for p in PAGE_MANIFEST if p["page"].lower() == decoded.lower()]
        if not matching:
            available = [p["page"] for p in PAGE_MANIFEST]
            raise HTTPException(
                status_code=404,
                detail=f"Page '{decoded}' not found. Available: {available}",
            )

        from src.services.page_validator import (
            _get_nested, _check_rule, _validate_endpoint
        )
        import httpx
        import datetime

        token = _get_internal_token()
        base_url = _get_base_url()
        page = matching[0]
        endpoint_results = []

        with httpx.Client() as client:
            for ep in page["endpoints"]:
                endpoint_results.append(
                    _validate_endpoint(client, base_url, token, ep)
                )

        page_overall = "pass" if all(e["overall"] == "pass" for e in endpoint_results) else "fail"

        return {
            "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
            "page": page["page"],
            "route": page.get("route", ""),
            "overall": page_overall,
            "endpoints": endpoint_results,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Single-page diagnostics failed for '%s': %s", page_name, exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Diagnostics failed: {exc}")


@router.get("/summary")
def diagnostics_summary(user: Dict[str, Any] = Depends(_require_admin)):
    """
    Lightweight version: runs all checks but returns only the summary
    (total/passed/failed counts and list of failed pages) without full field detail.
    """
    try:
        from src.services.page_validator import run_full_validation
        report = run_full_validation(
            base_url=_get_base_url(),
            token=_get_internal_token(),
        )
        return report.get("summary", {}) | {"generated_at": report.get("generated_at")}
    except Exception as exc:
        logger.error("Diagnostics summary failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Diagnostics failed: {exc}")
