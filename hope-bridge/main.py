"""
hope-bridge/main.py
-------------------
FastAPI bridge service — runs on the Windows PC alongside DRM Hope.
Exposes a REST API that the SynHealth backend calls over the LAN.

  HOPE_MOCK=1  →  all routes return static sample data (dev/demo)
  HOPE_MOCK=0  →  all routes call ODBC stubs in odbc_client.py (site visit required)

Start (dev):
    uvicorn main:app --host 0.0.0.0 --port 7070 --reload

Install as Windows service (production):
    See install-service.ps1 in this directory.
"""
from __future__ import annotations

import hmac
import logging
import os
from typing import Any

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")

HOPE_MOCK              = os.getenv("HOPE_MOCK", "1") == "1"
BRIDGE_API_KEY         = os.getenv("BRIDGE_API_KEY", "")
SYNHEALTH_BACKEND_URL  = os.getenv("SYNHEALTH_BACKEND_URL", "http://localhost:8000")
SYNHEALTH_WEBHOOK_SECRET = os.getenv("SYNHEALTH_WEBHOOK_SECRET", "")

if HOPE_MOCK:
    log.info("HOPE_MOCK=1 — returning sample data (no ODBC connection)")
else:
    log.info("HOPE_MOCK=0 — ODBC mode (ensure HOPE_ODBC_DSN is set)")

app = FastAPI(
    title="Hope Bridge Service",
    description=(
        "Lightweight FastAPI service that exposes DRM Hope data to the "
        "SynHealth backend over the hospital LAN. Runs as a Windows service "
        "on the Hope PC."
    ),
    version="0.1.0",
    docs_url="/docs",
    redoc_url=None,
)

# Restrict CORS to the SynHealth backend only — bridge is not public-facing
app.add_middleware(
    CORSMiddleware,
    allow_origins=[SYNHEALTH_BACKEND_URL],
    allow_methods=["GET", "POST"],
    allow_headers=["X-Bridge-Key"],
)


# ── Authentication ────────────────────────────────────────────────────────────

def verify_bridge_key(x_bridge_key: str = Header(...)) -> None:
    """Validate the shared HMAC secret on every request."""
    if not BRIDGE_API_KEY:
        raise HTTPException(500, "BRIDGE_API_KEY is not configured on the bridge.")
    if not hmac.compare_digest(x_bridge_key, BRIDGE_API_KEY):
        raise HTTPException(403, "Invalid bridge key.")


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health", tags=["ops"])
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "mock_mode": HOPE_MOCK,
        "service": "hope-bridge",
    }


# ── Patients ──────────────────────────────────────────────────────────────────

@app.get("/patients", tags=["hope"])
def get_patients(
    limit:  int = Query(100, ge=1, le=500),
    offset: int = Query(0,   ge=0),
    _auth: None = None,  # dependency injected via Depends below
) -> list[dict[str, Any]]:
    if HOPE_MOCK:
        from mock_data import MOCK_PATIENTS
        return MOCK_PATIENTS[offset : offset + limit]

    from odbc_client import fetch_patients  # real ODBC call
    return fetch_patients(limit=limit, offset=offset)


# Override to add auth dependency without polluting the signature
get_patients.__wrapped__ = get_patients


from fastapi import Depends  # noqa: E402 (must be after app creation)

app.routes.clear()

# Re-register routes with proper auth dependency
@app.get("/health", tags=["ops"])
def health_check() -> dict[str, Any]:
    return {"status": "ok", "mock_mode": HOPE_MOCK, "service": "hope-bridge"}


@app.get("/patients", tags=["hope"], dependencies=[Depends(verify_bridge_key)])
def patients(
    limit:  int = Query(100, ge=1, le=500),
    offset: int = Query(0,   ge=0),
) -> list[dict[str, Any]]:
    if HOPE_MOCK:
        from mock_data import MOCK_PATIENTS
        return MOCK_PATIENTS[offset : offset + limit]
    from odbc_client import fetch_patients
    return fetch_patients(limit=limit, offset=offset)


@app.get("/appointments", tags=["hope"], dependencies=[Depends(verify_bridge_key)])
def appointments(
    date_from: str | None = Query(None, description="ISO date YYYY-MM-DD"),
    date_to:   str | None = Query(None, description="ISO date YYYY-MM-DD"),
    limit:     int        = Query(200, ge=1, le=1000),
) -> list[dict[str, Any]]:
    if HOPE_MOCK:
        from mock_data import MOCK_APPOINTMENTS
        return MOCK_APPOINTMENTS
    from odbc_client import fetch_appointments
    return fetch_appointments(date_from=date_from, date_to=date_to, limit=limit)


@app.get("/admissions", tags=["hope"], dependencies=[Depends(verify_bridge_key)])
def admissions(active_only: bool = Query(True)) -> list[dict[str, Any]]:
    if HOPE_MOCK:
        from mock_data import MOCK_ADMISSIONS
        return MOCK_ADMISSIONS
    from odbc_client import fetch_admissions
    return fetch_admissions(active_only=active_only)


@app.get("/pharmacy/orders", tags=["hope"], dependencies=[Depends(verify_bridge_key)])
def pharmacy_orders(
    status: str | None = Query(None),
    limit:  int        = Query(200, ge=1, le=1000),
) -> list[dict[str, Any]]:
    if HOPE_MOCK:
        from mock_data import MOCK_PHARMACY_ORDERS
        return MOCK_PHARMACY_ORDERS
    from odbc_client import fetch_pharmacy_orders
    return fetch_pharmacy_orders(status=status, limit=limit)


@app.get("/lab/orders", tags=["hope"], dependencies=[Depends(verify_bridge_key)])
def lab_orders(
    status: str | None = Query(None),
    limit:  int        = Query(200, ge=1, le=1000),
) -> list[dict[str, Any]]:
    if HOPE_MOCK:
        from mock_data import MOCK_LAB_ORDERS
        return MOCK_LAB_ORDERS
    from odbc_client import fetch_lab_orders
    return fetch_lab_orders(status=status, limit=limit)


@app.get("/billing", tags=["hope"], dependencies=[Depends(verify_bridge_key)])
def billing(
    status: str | None = Query(None),
    limit:  int        = Query(200, ge=1, le=1000),
) -> list[dict[str, Any]]:
    if HOPE_MOCK:
        from mock_data import MOCK_BILLING
        return MOCK_BILLING
    from odbc_client import fetch_billing
    return fetch_billing(status=status, limit=limit)


# ── Webhook push (bridge → SynHealth backend) ─────────────────────────────────

@app.post("/push/webhook", tags=["ops"], dependencies=[Depends(verify_bridge_key)])
async def push_webhook(payload: dict[str, Any]) -> dict[str, str]:
    """
    Push a change-detection event to the SynHealth backend webhook endpoint.
    Called by the polling scheduler (see TODO below) when Hope data changes.
    """
    if not SYNHEALTH_WEBHOOK_SECRET:
        raise HTTPException(500, "SYNHEALTH_WEBHOOK_SECRET is not configured.")

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            f"{SYNHEALTH_BACKEND_URL}/hope/webhook",
            json=payload,
            headers={"X-Bridge-Key": SYNHEALTH_WEBHOOK_SECRET},
        )
        resp.raise_for_status()

    return {"status": "forwarded", "backend_status": str(resp.status_code)}


# ── TODO: polling scheduler ───────────────────────────────────────────────────
# After the site visit, add a background APScheduler job here that:
#   1. Polls `SELECT * FROM <patient_table> WHERE UpdatedAt > :last_checked`
#   2. Calls push_webhook() with the changed entity IDs
# Reference: briefing §6.3 (Change Detection — Polling option)
