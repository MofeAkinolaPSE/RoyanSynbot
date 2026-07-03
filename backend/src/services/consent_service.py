"""NDPA Consent Gate Service — Blueprint Ch 11.3 / 18.

Provides two integration points for consent enforcement:

1. `require_consent_for(purpose)` — FastAPI dependency factory.
   Use as: `Depends(require_consent_for("research"))` on any endpoint
   that handles PHI for a specific purpose. Extracts patient_id from
   path parameters, queries royan_patient_consent, and returns HTTP 403
   with `consent_required` detail if consent is missing.

2. `check_patient_consent(patient_id, purpose)` — plain async helper
   for use inside route handlers when you need a bool result rather than
   an automatic 403 (e.g., to decide whether to include optional data).

Both functions use the existing `check_consent()` from src.privacy so
the actual SQL lives in one place.

Purpose ↔ consent_type mapping (matches royan_patient_consent CHECK):
  "data_processing"   → data_processing   (default treatment consent)
  "research"          → research
  "third_party"       → third_party_sharing
  "marketing"         → marketing
  "telemedicine"      → telemedicine
  "surgery"           → surgical
  "photography"       → photography
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import Depends, HTTPException, Path
from fastapi.requests import Request

from src.db import db
from src.privacy import check_consent

logger = logging.getLogger(__name__)

# Maps caller-facing purpose names → consent_type values in the DB CHECK constraint
_PURPOSE_MAP = {
    "data_processing":  "data_processing",
    "research":         "research",
    "third_party":      "third_party_sharing",
    "marketing":        "marketing",
    "telemedicine":     "telemedicine",
    "surgery":          "surgical",
    "photography":      "photography",
    "treatment":        "treatment",
}

VALID_PURPOSES = set(_PURPOSE_MAP.keys())


def require_consent_for(purpose: str):
    """Return a FastAPI Depends-compatible async function that gates on consent.

    The dependency expects a `patient_id` path parameter in the route.
    On missing consent it raises HTTP 403 with actionable detail.

    Usage:
        @router.get("/research/export/{patient_id}",
                    dependencies=[Depends(require_consent_for("research"))])
    """
    if purpose not in _PURPOSE_MAP:
        raise ValueError(f"Unknown consent purpose '{purpose}'. Valid: {sorted(VALID_PURPOSES)}")

    async def _gate(request: Request) -> None:
        patient_id_raw = request.path_params.get("patient_id")
        if not patient_id_raw:
            # No patient_id in path — cannot check consent, allow through
            # (endpoint is responsible for consent check at the business logic level)
            return

        try:
            patient_id = int(patient_id_raw)
        except (TypeError, ValueError):
            return

        conn = db.pool.getconn()
        try:
            granted = check_consent(patient_id, _PURPOSE_MAP[purpose], conn)
        except Exception as exc:
            logger.warning("Consent check error for patient=%s purpose=%s: %s", patient_id, purpose, exc)
            # Fail-safe: deny access on unexpected error
            db.pool.putconn(conn)
            raise HTTPException(
                status_code=503,
                detail={"error": "consent_check_unavailable", "purpose": purpose},
            )
        finally:
            try:
                db.pool.putconn(conn)
            except Exception:
                pass

        if not granted:
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "consent_required",
                    "message": (
                        f"Patient {patient_id} has not granted '{purpose}' consent. "
                        "Obtain consent via POST /api/v1/privacy/consent/{patient_id} "
                        f"with consent_type='{_PURPOSE_MAP[purpose]}' before proceeding."
                    ),
                    "consent_type": _PURPOSE_MAP[purpose],
                    "patient_id": patient_id,
                },
            )

    _gate.__name__ = f"require_{purpose}_consent"
    return _gate


async def check_patient_consent(patient_id: int, purpose: str) -> bool:
    """Async helper that returns True/False without raising.

    Use when you want to conditionally include data rather than hard-block.

    Example:
        if await check_patient_consent(patient_id, "research"):
            record["research_flags"] = ...
    """
    if purpose not in _PURPOSE_MAP:
        raise ValueError(f"Unknown consent purpose '{purpose}'.")

    conn = db.pool.getconn()
    try:
        return check_consent(patient_id, _PURPOSE_MAP[purpose], conn)
    except Exception as exc:
        logger.warning("check_patient_consent error: %s", exc)
        return False
    finally:
        db.pool.putconn(conn)
