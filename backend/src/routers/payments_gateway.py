"""
Payments Router — RoyanHealth / Royan Hospital
=================================================
Paystack, Flutterwave, and Stripe payment gateway integration with stub
fallback. All payment transactions are persisted to royan_payment_transactions.
Used for both direct patient billing and HMO claim settlement (item 20).

Endpoints:
  POST  /payments/initiate                – Initiate a payment (Paystack, Flutterwave, or Stripe)
  GET   /payments/{reference}             – Verify / check payment status
  GET   /payments                         – List payment transactions
  POST  /payments/webhook/paystack        – Paystack webhook handler
  POST  /payments/webhook/flutterwave     – Flutterwave webhook handler
  POST  /payments/webhook/stripe          – Stripe webhook handler
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
STRIPE_SECRET_KEY      = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET  = os.getenv("STRIPE_WEBHOOK_SECRET", "")
PAYSTACK_BASE          = "https://api.paystack.co"
FLUTTERWAVE_BASE       = "https://api.flutterwave.com/v3"
STRIPE_BASE            = "https://api.stripe.com/v1"

_STUB_MODE = not (PAYSTACK_SECRET_KEY or FLUTTERWAVE_SECRET_KEY or STRIPE_SECRET_KEY)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class PaymentInitiate(BaseModel):
    gateway:        str   = Field("paystack", description="paystack | flutterwave | stripe")
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


async def _stripe_initiate(payload: PaymentInitiate, reference: str) -> dict:
    """Create a Stripe Checkout Session. Stripe's API takes form-encoded
    bodies (not JSON) — bracket notation builds the nested line_items/
    metadata params."""
    if _STUB_MODE:
        return {
            "url":       f"https://checkout.stripe.com/stub/{reference}",
            "id":        f"cs_stub_{reference[:16]}",
            "reference": reference,
            "stub":      True,
        }
    callback = payload.callback_url or "https://royan.hospital/payment/callback"
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"{STRIPE_BASE}/checkout/sessions",
            headers={"Authorization": f"Bearer {STRIPE_SECRET_KEY}"},
            data={
                "mode":                                            "payment",
                "success_url":                                     f"{callback}?reference={reference}",
                "cancel_url":                                      callback,
                "customer_email":                                  payload.email,
                "client_reference_id":                              reference,
                "line_items[0][price_data][currency]":              payload.currency.lower(),
                "line_items[0][price_data][product_data][name]":    payload.description or "Royan Hospital Payment",
                "line_items[0][price_data][unit_amount]":           str(int(round(payload.amount * 100))),
                "line_items[0][quantity]":                          "1",
                "metadata[reference]":                              reference,
                "metadata[patient_id]":                             str(payload.patient_id or ""),
                "metadata[encounter_id]":                           str(payload.encounter_id or ""),
                "metadata[bill_id]":                                str(payload.bill_id or ""),
            },
        )
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Stripe error: {resp.text}")
    return resp.json()


async def _stripe_verify(session_id: str) -> dict:
    if _STUB_MODE:
        return {"payment_status": "paid", "amount_total": 0, "stub": True}
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"{STRIPE_BASE}/checkout/sessions/{session_id}",
            headers={"Authorization": f"Bearer {STRIPE_SECRET_KEY}"},
        )
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Stripe verify error: {resp.text}")
    return resp.json()


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
    elif payload.gateway == "stripe":
        gw_data = await _stripe_initiate(payload, reference)
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
    elif gateway == "stripe":
        session_id = (record.get("gateway_data") or {}).get("id", reference)
        gw_result = await _stripe_verify(str(session_id))
        new_status = "success" if gw_result.get("payment_status") == "paid" else "pending"
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


@router.post("/webhook/stripe", status_code=200)
async def stripe_webhook(request: Request, stripe_signature: Optional[str] = Header(None, alias="Stripe-Signature")):
    body = await request.body()

    if STRIPE_WEBHOOK_SECRET and stripe_signature:
        # Stripe-Signature: "t=<timestamp>,v1=<hex hmac>" — verify
        # hmac_sha256(secret, f"{t}.{body}") matches v1 before trusting the payload.
        parts = dict(p.split("=", 1) for p in stripe_signature.split(",") if "=" in p)
        timestamp, v1 = parts.get("t"), parts.get("v1")
        if not timestamp or not v1:
            raise HTTPException(status_code=400, detail="Malformed Stripe-Signature header")
        signed_payload = f"{timestamp}.{body.decode('utf-8')}".encode()
        expected = hmac.new(STRIPE_WEBHOOK_SECRET.encode(), signed_payload, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, v1):
            raise HTTPException(status_code=401, detail="Invalid Stripe signature")

    try:
        event = (await request.json())
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    evt_type = event.get("type", "")
    session = event.get("data", {}).get("object", {})
    reference = session.get("client_reference_id") or (session.get("metadata") or {}).get("reference", "")

    if evt_type == "checkout.session.completed" and session.get("payment_status") == "paid" and reference:
        db.table(TABLE_PAYMENT_TRANSACTIONS).update({
            "status":       "success",
            "verified_at":  _now(),
            "webhook_data": session,
        }).eq("reference", reference).execute()
        audit_event("payment_webhook_success", {"gateway": "stripe"},
                    actor_id="webhook", subject_type="payment", subject_id=reference)

    return {"ok": True}
