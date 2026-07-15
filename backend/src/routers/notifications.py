"""
Notifications Router — RoyanHealth / Royan Hospital
======================================================
SMS and WhatsApp outbound messaging via Africa's Talking.
Falls back to stub/log-only mode when AT credentials are absent.

Endpoints:
  POST   /notifications/send               – Send single SMS or WhatsApp
  POST   /notifications/bulk               – Bulk send to list of recipients
  POST   /notifications/appointment-reminder – Trigger reminders for upcoming appointments
  GET    /notifications/logs               – Notification delivery history
  GET    /notifications/logs/{log_id}      – Single log entry

  GET    /notifications/templates          – List SMS templates
  POST   /notifications/templates          – Create template
  PATCH  /notifications/templates/{id}     – Update template
  DELETE /notifications/templates/{id}     – Soft-delete template
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.db import db, audit_event
from src.middleware import verify_jwt
from src.constants import (
    TABLE_NOTIFICATION_LOGS,
    TABLE_SMS_TEMPLATES,
    NOTIFICATION_CHANNELS_ALLOWED,
    NOTIFICATION_STATUS_ALLOWED,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/notifications", tags=["Notifications / SMS"])

# Africa's Talking credentials (optional — stub mode if absent)
AT_API_KEY    = os.getenv("AT_API_KEY", "")
AT_USERNAME   = os.getenv("AT_USERNAME", "sandbox")
AT_SENDER_ID  = os.getenv("AT_SENDER_ID", "ROYAN")
AT_SHORTCODE  = os.getenv("AT_SHORTCODE", "")


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class SendMessage(BaseModel):
    channel: str = "sms"               # sms | whatsapp
    recipient: str = Field(..., min_length=5, max_length=20)
    message: str = Field(..., min_length=1, max_length=1600)
    patient_id: Optional[int] = None
    appointment_id: Optional[int] = None
    template_id: Optional[int] = None

    model_config = {"extra": "ignore"}


class BulkSend(BaseModel):
    channel: str = "sms"
    recipients: List[str] = Field(..., min_length=1)
    message: str = Field(..., min_length=1, max_length=1600)
    campaign_name: Optional[str] = None

    model_config = {"extra": "ignore"}


class ReminderTrigger(BaseModel):
    days_ahead: int = Field(1, ge=0, le=7)   # send for appointments N days from now
    message_template: Optional[str] = None   # override default template

    model_config = {"extra": "ignore"}


class TemplateCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    channel: str = "sms"
    body: str = Field(..., min_length=1, max_length=1600)
    variables: Optional[str] = None   # comma-separated variable names e.g. "patient_name,date,time"
    category: Optional[str] = None    # appointment | discharge | result | general

    model_config = {"extra": "ignore"}


class TemplateUpdate(BaseModel):
    name: Optional[str] = None
    body: Optional[str] = None
    variables: Optional[str] = None
    category: Optional[str] = None
    active: Optional[bool] = None

    model_config = {"extra": "ignore"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _send_via_at(recipient: str, message: str, channel: str = "sms") -> dict:
    """
    Dispatch a message through Africa's Talking.
    Returns a result dict with status and provider_message_id.
    Operates in stub mode when AT_API_KEY is unset.
    """
    if not AT_API_KEY:
        logger.info("[AT STUB] %s → %s: %s", channel.upper(), recipient, message[:60])
        return {"status": "sent", "provider_message_id": "STUB-" + recipient[-4:], "stub": True}

    try:
        import africastalking  # type: ignore
        africastalking.initialize(AT_USERNAME, AT_API_KEY)

        if channel == "whatsapp":
            # Africa's Talking WhatsApp sandbox/prod
            response = africastalking.Application.whatsapp().send(
                message=message,
                recipients=[recipient],
                sender_id=AT_SHORTCODE or AT_SENDER_ID,
            )
            recipients = response.get("SMSMessageData", {}).get("Recipients", [])
        else:
            sms = africastalking.SMS
            response = sms.send(
                message=message,
                recipients=[recipient],
                sender_id=AT_SENDER_ID or None,
            )
            recipients = response.get("SMSMessageData", {}).get("Recipients", [])

        if recipients:
            r = recipients[0]
            return {
                "status": "sent" if r.get("status") == "Success" else "failed",
                "provider_message_id": r.get("messageId", ""),
                "cost": r.get("cost", ""),
            }
        return {"status": "failed", "provider_message_id": ""}
    except ImportError:
        logger.warning("africastalking package not installed — stub mode")
        return {"status": "sent", "provider_message_id": "STUB-NOPKG", "stub": True}
    except Exception as exc:
        logger.error("AT send failed: %s", exc)
        return {"status": "failed", "provider_message_id": "", "error": str(exc)}


def _log_message(
    channel: str,
    recipient: str,
    message: str,
    status: str,
    provider_message_id: str,
    patient_id: Optional[int] = None,
    appointment_id: Optional[int] = None,
    template_id: Optional[int] = None,
    actor_id: Optional[str] = None,
    campaign_name: Optional[str] = None,
) -> dict:
    row = {
        "channel":             channel,
        "recipient":           recipient,
        "message":             message,
        "status":              status,
        "provider_message_id": provider_message_id,
        "sent_at":             _now(),
    }
    if patient_id:    row["patient_id"]    = patient_id
    if appointment_id: row["appointment_id"] = appointment_id
    if template_id:   row["template_id"]   = template_id
    if actor_id:      row["sent_by"]       = actor_id
    if campaign_name: row["campaign_name"] = campaign_name

    try:
        result = db.table(TABLE_NOTIFICATION_LOGS).insert(row).execute()
        return result.data[0] if result.data else row
    except Exception as exc:
        logger.error("Failed to persist notification log: %s", exc)
        return row


# ---------------------------------------------------------------------------
# Send endpoints
# ---------------------------------------------------------------------------

@router.post("/send", status_code=201)
async def send_message(payload: SendMessage, user=Depends(verify_jwt)):
    """Send a single SMS or WhatsApp message."""
    if payload.channel not in NOTIFICATION_CHANNELS_ALLOWED:
        raise HTTPException(status_code=422, detail=f"channel must be one of {NOTIFICATION_CHANNELS_ALLOWED}")

    result = _send_via_at(payload.recipient, payload.message, payload.channel)
    log = _log_message(
        channel=payload.channel,
        recipient=payload.recipient,
        message=payload.message,
        status=result["status"],
        provider_message_id=result.get("provider_message_id", ""),
        patient_id=payload.patient_id,
        appointment_id=payload.appointment_id,
        template_id=payload.template_id,
        actor_id=user.get("sub"),
    )
    audit_event(
        "notification_sent",
        {"channel": payload.channel, "status": result["status"], "recipient_suffix": payload.recipient[-4:]},
        actor_id=user.get("sub"),
        subject_type="notification",
        subject_id=str(log.get("id") or ""),
    )
    return {"ok": True, "status": result["status"], "log": log}


@router.post("/bulk", status_code=201)
async def bulk_send(payload: BulkSend, user=Depends(verify_jwt)):
    """Send the same message to multiple recipients."""
    if payload.channel not in NOTIFICATION_CHANNELS_ALLOWED:
        raise HTTPException(status_code=422, detail=f"channel must be one of {NOTIFICATION_CHANNELS_ALLOWED}")
    if len(payload.recipients) > 500:
        raise HTTPException(status_code=422, detail="Maximum 500 recipients per bulk send")

    results = []
    sent = failed = 0
    for recipient in payload.recipients:
        r = _send_via_at(recipient, payload.message, payload.channel)
        _log_message(
            channel=payload.channel,
            recipient=recipient,
            message=payload.message,
            status=r["status"],
            provider_message_id=r.get("provider_message_id", ""),
            actor_id=user.get("sub"),
            campaign_name=payload.campaign_name,
        )
        results.append({"recipient": recipient, "status": r["status"]})
        if r["status"] == "sent":
            sent += 1
        else:
            failed += 1

    audit_event(
        "bulk_notification_sent",
        {"channel": payload.channel, "total": len(payload.recipients), "sent": sent, "failed": failed, "campaign": payload.campaign_name},
        actor_id=user.get("sub"),
        subject_type="notification_bulk",
        subject_id="",
    )
    return {"ok": True, "total": len(payload.recipients), "sent": sent, "failed": failed, "results": results}


@router.post("/appointment-reminder", status_code=201)
async def send_appointment_reminders(payload: ReminderTrigger, user=Depends(verify_jwt)):
    """
    Query appointments N days ahead and send SMS reminders.
    Looks up patient phone from royan_patients via appointment.patient_id.
    """
    from src.constants import TABLE_APPOINTMENTS
    target_date = (datetime.now(timezone.utc) + timedelta(days=payload.days_ahead)).date().isoformat()

    appt_result = db.table(TABLE_APPOINTMENTS).select(
        "id,patient_id,appointment_date,appointment_time,department,provider_name"
    ).eq("appointment_date", target_date).eq("status", "confirmed").execute()

    appointments = appt_result.data or []
    if not appointments:
        return {"ok": True, "sent": 0, "message": f"No confirmed appointments on {target_date}"}

    default_template = (
        payload.message_template
        or "Dear patient, reminder: you have an appointment at Royan Hospital on {date} at {time} ({department}). Reply STOP to opt out."
    )

    sent = 0
    skipped = 0
    for appt in appointments:
        # Fetch patient phone
        pat = db.table("royan_patients").select("phone,first_name,last_name").eq("id", appt["patient_id"]).execute()
        if not pat.data or not pat.data[0].get("phone"):
            skipped += 1
            continue
        p = pat.data[0]
        phone = p["phone"]
        msg = default_template.format(
            date=appt.get("appointment_date", target_date),
            time=appt.get("appointment_time", ""),
            department=appt.get("department", ""),
            provider=appt.get("provider_name", ""),
            name=f"{p.get('first_name', '')} {p.get('last_name', '')}".strip(),
        )
        r = _send_via_at(phone, msg, "sms")
        _log_message(
            channel="sms",
            recipient=phone,
            message=msg,
            status=r["status"],
            provider_message_id=r.get("provider_message_id", ""),
            patient_id=appt["patient_id"],
            appointment_id=appt["id"],
            actor_id=user.get("sub"),
            campaign_name=f"reminder_{target_date}",
        )
        if r["status"] == "sent":
            sent += 1
        else:
            skipped += 1

    audit_event(
        "appointment_reminders_sent",
        {"date": target_date, "sent": sent, "skipped": skipped},
        actor_id=user.get("sub"),
        subject_type="notification_bulk",
        subject_id="",
    )
    return {"ok": True, "sent": sent, "skipped": skipped, "target_date": target_date}


# ---------------------------------------------------------------------------
# Notification logs
# ---------------------------------------------------------------------------

@router.get("/logs")
async def list_logs(
    channel: Optional[str] = Query(None),
    status: Optional[str]  = Query(None),
    patient_id: Optional[int] = Query(None),
    campaign_name: Optional[str] = Query(None),
    date: Optional[str] = Query(None),   # ISO date prefix filter on sent_at
    limit: int = Query(50, ge=1, le=200),
    user=Depends(verify_jwt),
):
    query = db.table(TABLE_NOTIFICATION_LOGS).select("*").order("sent_at", desc=True).limit(limit)
    if channel:       query = query.eq("channel", channel)
    if status:        query = query.eq("status", status)
    if patient_id:    query = query.eq("patient_id", patient_id)
    if campaign_name: query = query.eq("campaign_name", campaign_name)
    if date:
        query = query.gte("sent_at", date).lt("sent_at", date + "T99")
    result = query.execute()
    return {"logs": result.data or [], "count": len(result.data or [])}


@router.get("/logs/{log_id}")
async def get_log(log_id: int, user=Depends(verify_jwt)):
    r = db.table(TABLE_NOTIFICATION_LOGS).select("*").eq("id", log_id).execute()
    if not r.data:
        raise HTTPException(status_code=404, detail="Notification log not found")
    return {"log": r.data[0]}


# ---------------------------------------------------------------------------
# SMS Templates
# ---------------------------------------------------------------------------

@router.get("/templates")
async def list_templates(
    channel: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    user=Depends(verify_jwt),
):
    query = db.table(TABLE_SMS_TEMPLATES).select("*").eq("active", True).order("name")
    if channel:  query = query.eq("channel", channel)
    if category: query = query.eq("category", category)
    result = query.execute()
    return {"templates": result.data or [], "count": len(result.data or [])}


@router.post("/templates", status_code=201)
async def create_template(payload: TemplateCreate, user=Depends(verify_jwt)):
    data = payload.model_dump(exclude_none=True)
    data["active"]     = True
    data["created_by"] = user.get("sub") or "system"
    try:
        result = db.table(TABLE_SMS_TEMPLATES).insert(data).execute()
    except Exception as exc:
        logger.error("Template creation failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to create template")
    template = result.data[0] if result.data else data
    audit_event("sms_template_created", {"name": payload.name}, actor_id=user.get("sub"), subject_type="sms_template", subject_id=str(template.get("id") or ""))
    return {"ok": True, "template": template}


@router.patch("/templates/{template_id}")
async def update_template(template_id: int, payload: TemplateUpdate, user=Depends(verify_jwt)):
    updates = payload.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=422, detail="No fields to update")
    db.table(TABLE_SMS_TEMPLATES).update(updates).eq("id", template_id).execute()
    return {"ok": True, "template_id": template_id}


@router.delete("/templates/{template_id}")
async def delete_template(template_id: int, user=Depends(verify_jwt)):
    db.table(TABLE_SMS_TEMPLATES).update({"active": False}).eq("id", template_id).execute()
    return {"ok": True, "template_id": template_id}


# ---------------------------------------------------------------------------
# Stats endpoint
# ---------------------------------------------------------------------------

@router.get("/stats")
async def notification_stats(user=Depends(verify_jwt)):
    result = db.table(TABLE_NOTIFICATION_LOGS).select("channel,status,sent_at").execute()
    rows = result.data or []

    today = datetime.now(timezone.utc).date().isoformat()
    total = len(rows)
    sent_today = sum(1 for r in rows if r.get("sent_at", "")[:10] == today)
    by_channel: dict = {}
    by_status: dict = {}
    for r in rows:
        ch = r.get("channel") or "sms"
        st = r.get("status") or "unknown"
        by_channel[ch] = by_channel.get(ch, 0) + 1
        by_status[st]  = by_status.get(st, 0) + 1

    delivery_rate = round(by_status.get("sent", 0) / total * 100, 1) if total else 0

    return {
        "total": total,
        "sent_today": sent_today,
        "delivery_rate_pct": delivery_rate,
        "by_channel": by_channel,
        "by_status": by_status,
    }
