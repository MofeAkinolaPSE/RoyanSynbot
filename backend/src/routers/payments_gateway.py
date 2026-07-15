"""
Payments Router — RoyanHealth / Royan Hospital
=================================================
Paystack and Flutterwave payment gateway integration with stub fallback.
All payment transactions are persisted to royan_payment_transactions.

Endpoints:
  POST  /payments/initiate                – Initiate a payment (Paystack or Flutterwave)
  GET   /payments/{reference}             – Verify / check payment status
  GET   /payments                         – List payment transactions
  POST  /payments/webhook/paystack        – Paystack webhook handler
  POST  /payments/webhook/flutterwave     – Flutterwave webhook handler
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field

from src.db import db, audit_event
from src.middleware import verify_jwt
from src.constants import (
    TABLE_PAYMENT_TRANSACTIONS,
    PAYMENT_GATEWAY_ALLOWED,
    PAYMENT_TXN_STATUS_ALLOWED,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/payments", tags=["Payment Gateway"])

# ── Env config ──────────────────────────────────────────────────────────────
PAYSTACK_SECRET_KEY    = os.getenv("PAYSTACK_SECRET_KEY", "")
FLUTTERWAVE_SECRET_KEY = os.getenv("FLUTTERWAVE_SECRET_KEY", "")
PAYSTACK_BASE          = "https://api.paystack.co"
FLUTTERWAVE_BASE       = "https://api.flutterwave.com/v3"

_STUB_MODE = not (PAYSTACK_SECRET_KEY or FLUTTERWAVE_SECRET_KEY)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class PaymentInitiate(BaseModel):
    gateway:        str   = Field("paystack", description="paystack | flutterwave")
    amount:         float = Field(..., gt=0, description="Amount in NGN kobo (Paystack) or NGN (Flutterwave)")
    email:          str   = Field(..., min_length=3)
    patient_id:     Optional[int]   = None
    encounter_id:   Optional[int]   = None
    bill_id:        Optional[int]   = None
    currency:       str             = "NGN"
    description:    Optional[str]   = None
    callback_url:   Optional[str]   = None

    model_config = {"extra": "ignore"}


# ---------------------------------------------------------------------------
# Gateway helpers
# ---------------------------------------------------------------------------

async def _paystack_initiate(payload: PaymentInitiate, reference: str) -> dict:
    if _STUB_MODE:
        return {
            "authorization_url": f"https://checkout.paystack.com/stub/{reference}",
            "access_code":       f"stub_{reference[:8]}",
            "reference":         reference,
            "stub":              True,
        }
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"{PAYSTACK_BASE}/transaction/initialize",
            headers={"Authorization": f"Bearer {PAYSTACK_SECRET_KEY}"},
            json={
                "amount":       int(payload.amount),
                "email":        payload.email,
                "reference":    reference,
                "currency":     payload.currency,
                "callback_url": payload.callback_url or "",
                "metadata":     {
                    "patient_id":   payload.patient_id,
                    "encounter_id": payload.encounter_id,
                    "bill_id":      payload.bill_id,
                },
            },
        )
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Paystack error: {resp.text}")
    return resp.json().get("data", {})


async def _paystack_verify(reference: str) -> dict:
    if _STUB_MODE:
        return {"status": "success", "amount": 0, "stub": True}
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"{PAYSTACK_BASE}/transaction/verify/{reference}",
            headers={"Authorization": f"Bearer {PAYSTACK_SECRET_KEY}"},
        )
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Paystack verify error: {resp.text}")
    return resp.json().get("data", {})


async def _flutterwave_initiate(payload: PaymentInitiate, reference: str) -> dict:
    if _STUB_MODE:
        return {
            "link":  f"https://checkout.flutterwave.com/stub/{reference}",
            "tx_ref": reference,
            "stub":  True,
        }
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"{FLUTTERWAVE_BASE}/payments",
            headers={"Authorization": f"Bearer {FLUTTERWAVE_SECRET_KEY}"},
            json={
                "tx_ref":       reference,
                "amount":       payload.amount,
                "currency":     payload.currency,
                "redirect_url": payload.callback_url or "https://royan.hospital/payment/callback",
                "customer":     {"email": payload.email},
                "customizations": {"title": payload.description or "Royan Hospital Payment"},
                "meta":         {
                    "patient_id":   payload.patient_id,
                    "encounter_id": payload.encounter_id,
                    "bill_id":      payload.bill_id,
                },
            },
        )
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Flutterwave error: {resp.text}")
    return resp.json().get("data", {})


async def _flutterwave_verify(tx_id: str) -> dict:
    if _STUB_MODE:
        return {"status": "successful", "amount": 0, "stub": True}
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"{FLUTTERWAVE_BASE}/transactions/{tx_id}/verify",
            headers={"Authorization": f"Bearer {FLUTTERWAVE_SECRET_KEY}"},
        )
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Flutterwave verify error: {resp.text}")
    return resp.json().get("data", {})


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/initiate", status_code=201)
async def initiate_payment(payload: PaymentInitiate, user=Depends(verify_jwt)):
    if payload.gateway not in PAYMENT_GATEWAY_ALLOWED:
        raise HTTPException(status_code=422, detail=f"gateway must be one of {PAYMENT_GATEWAY_ALLOWED}")

    reference = f"ROY-{uuid.uuid4().hex[:12].upper()}"

    if payload.gateway == "paystack":
        gw_data = await _paystack_initiate(payload, reference)
    else:
        gw_data = await _flutterwave_initiate(payload, reference)

    record = {
        "reference":    reference,
        "gateway":      payload.gateway,
        "amount":       payload.amount,
        "currency":     payload.currency,
        "email":        payload.email,
        "patient_id":   payload.patient_id,
        "encounter_id": payload.encounter_id,
        "bill_id":      payload.bill_id,
        "description":  payload.description,
        "status":       "initiated",
        "gateway_data": gw_data,
        "initiated_by": user.get("sub") or "system",
        "initiated_at": _now(),
    }
    try:
        result = db.table(TABLE_PAYMENT_TRANSACTIONS).insert(record).execute()
    except Exception as exc:
        logger.error("Payment record insert failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to save payment record")

    saved = result.data[0] if result.data else record
    audit_event("payment_initiated", {"gateway": payload.gateway, "amount": payload.amount},
                actor_id=user.get("sub"), subject_type="payment", subject_id=reference)
    return {"ok": True, "reference": reference, "gateway_data": gw_data, "id": saved.get("id")}


@router.get("/{reference}")
async def verify_payment(reference: str, user=Depends(verify_jwt)):
    r = db.table(TABLE_PAYMENT_TRANSACTIONS).select("*").eq("reference", reference).execute()
    if not r.data:
        raise HTTPException(status_code=404, detail="Payment reference not found")
    record = r.data[0]

    gateway = record.get("gateway", "paystack")
    if gateway == "paystack":
        gw_result = await _paystack_verify(reference)
        new_status = "success" if gw_result.get("status") == "success" else "pending"
    else:
        tx_id = (record.get("gateway_data") or {}).get("id", reference)
        gw_result = await _flutterwave_verify(str(tx_id))
        new_status = "success" if gw_result.get("status") == "successful" else "pending"

    if new_status != record.get("status"):
        db.table(TABLE_PAYMENT_TRANSACTIONS).update({
            "status":       new_status,
            "verified_at":  _now(),
            "gateway_data": {**(record.get("gateway_data") or {}), "verify_result": gw_result},
        }).eq("reference", reference).execute()
        audit_event("payment_verified", {"status": new_status},
                    actor_id=user.get("sub"), subject_type="payment", subject_id=reference)

    return {"reference": reference, "status": new_status, "gateway_result": gw_result}


@router.get("")
async def list_payments(
    patient_id:   Optional[int] = Query(None),
    encounter_id: Optional[int] = Query(None),
    status:       Optional[str] = Query(None),
    gateway:      Optional[str] = Query(None),
    limit:        int           = Query(50, ge=1, le=200),
    user=Depends(verify_jwt),
):
    q = db.table(TABLE_PAYMENT_TRANSACTIONS).select(
        "id,reference,gateway,amount,currency,email,patient_id,encounter_id,bill_id,status,initiated_at,verified_at"
    ).order("initiated_at", desc=True).limit(limit)
    if patient_id:   q = q.eq("patient_id",   patient_id)
    if encounter_id: q = q.eq("encounter_id", encounter_id)
    if status:       q = q.eq("status",       status)
    if gateway:      q = q.eq("gateway",      gateway)
    result = q.execute()
    return {"transactions": result.data or [], "count": len(result.data or [])}


# ---------------------------------------------------------------------------
# Webhooks
# ---------------------------------------------------------------------------

@router.post("/webhook/paystack", status_code=200)
async def paystack_webhook(request: Request, x_paystack_signature: Optional[str] = Header(None)):
    body = await request.body()

    if PAYSTACK_SECRET_KEY and x_paystack_signature:
        expected = hmac.new(
            PAYSTACK_SECRET_KEY.encode(), body, hashlib.sha512
        ).hexdigest()
        if not hmac.compare_digest(expected, x_paystack_signature):
            raise HTTPException(status_code=401, detail="Invalid Paystack signature")

    try:
        event = (await request.json())
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    evt_type = event.get("event", "")
    data     = event.get("data", {})
    reference = data.get("reference", "")

    if evt_type == "charge.success" and reference:
        db.table(TABLE_PAYMENT_TRANSACTIONS).update({
            "status":       "success",
            "verified_at":  _now(),
            "webhook_data": data,
        }).eq("reference", reference).execute()
        audit_event("payment_webhook_success", {"gateway": "paystack"},
                    actor_id="webhook", subject_type="payment", subject_id=reference)

    return {"ok": True}


@router.post("/webhook/flutterwave", status_code=200)
async def flutterwave_webhook(request: Request, verif_hash: Optional[str] = Header(None)):
    body = await request.body()

    if FLUTTERWAVE_SECRET_KEY and verif_hash:
        if not hmac.compare_digest(verif_hash, FLUTTERWAVE_SECRET_KEY):
            raise HTTPException(status_code=401, detail="Invalid Flutterwave signature")

    try:
        event = (await request.json())
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    data      = event.get("data", {})
    reference = data.get("tx_ref", "")
    status    = data.get("status", "")

    if status == "successful" and reference:
        db.table(TABLE_PAYMENT_TRANSACTIONS).update({
            "status":       "success",
            "verified_at":  _now(),
            "webhook_data": data,
        }).eq("reference", reference).execute()
        audit_event("payment_webhook_success", {"gateway": "flutterwave"},
                    actor_id="webhook", subject_type="payment", subject_id=reference)

    return {"ok": True}
