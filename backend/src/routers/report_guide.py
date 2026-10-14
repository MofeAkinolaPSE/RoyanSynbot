"""Thin routers for the reportGUide.md modules - each handler checks the role and calls the hub service.

  /procurement/*        Procurement & Stores (services/stock_orders.py)          s6
  /relations/*          Patient Relations - HMO & corporate accounts              s7
                        (services/payer_relations.py)
  /calendar/hospital    the calendar over records (services/hospital_calendar.py) s10
  /reports/catalog ...  reports about one record (services/report_subjects.py,    s12
                        services/record_reports.py)
"""
from __future__ import annotations

import datetime as dt
import io
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse

from src.cache import drop_shared_response, shared_response
from src.middleware import verify_jwt
from src.services import hospital_calendar, payer_relations, quality_hub, record_reports, report_subjects, stock_orders

log = logging.getLogger(__name__)

PROCURE_READ = {"pharmacist", "ops", "finance", "quality_assurance", "management", "admin"}
PROCURE_RAISE = {"pharmacist", "ops", "nurse", "doctor", "management", "admin"}
PROCURE_PLACE = {"pharmacist", "ops", "management", "admin"}
RELATIONS = {"finance", "management", "admin"}

procurement = APIRouter(prefix="/procurement", tags=["procurement"])
relations = APIRouter(prefix="/relations", tags=["patient-relations"])
calendar = APIRouter(prefix="/calendar/hospital", tags=["calendar"])
reports = APIRouter(prefix="/reports", tags=["reports"])
quality = APIRouter(prefix="/quality", tags=["quality"])

QUALITY_READ = {"quality_assurance", "ops", "management", "admin"}
PHARMACY_QC = {"pharmacist", "quality_assurance", "ops", "management", "admin"}


def _need(allowed: set, what: str):
    def dep(request: Request) -> Dict[str, Any]:
        u = verify_jwt(request)
        if not {str(r).lower() for r in (u.get("roles") or [])} & allowed:
            raise HTTPException(403, f"{what} is not open to your role")
        return u
    return dep


# The heavy read-only views, shared by every worker (src/cache.shared_response) and dropped on the
# writes that change them.
_PROCUREMENT_VIEWS = ("procurement:overview", "procurement:plan")
_RELATIONS_VIEWS = ("relations:overview", "relations:payers")


async def _call_dropping(views, fn, *a, **k):
    out = await _call(fn, *a, **k)
    drop_shared_response(*views)
    return out


async def _call(fn, *a, **k):
    try:
        return await run_in_threadpool(fn, *a, **k)
    except HTTPException:
        raise
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except LookupError as e:
        raise HTTPException(404, str(e))
    except (ValueError, stock_orders.OrderError, payer_relations.RelationsError) as e:
        raise HTTPException(400, str(e))
    except record_reports.ReportError as e:
        raise HTTPException(503, str(e))


def _date(v: Optional[str], name: str) -> dt.date:
    try:
        return dt.date.fromisoformat(str(v)[:10])
    except (TypeError, ValueError):
        raise HTTPException(400, f"{name} must be a date (YYYY-MM-DD)")


# ---------------------------------------------------------------------------
# Procurement & Stores
# ---------------------------------------------------------------------------

@procurement.get("/overview")
async def procurement_overview(u=Depends(_need(PROCURE_READ, "Procurement"))):
    return await _call(shared_response, "procurement:overview", 60, stock_orders.summary)


@procurement.get("/reorder-plan")
async def procurement_plan(refresh: bool = False, u=Depends(_need(PROCURE_READ, "Procurement"))):
    return await _call(shared_response, "procurement:plan", 120, lambda: stock_orders.reorder_plan(refresh), refresh)


@procurement.get("/orders")
async def procurement_orders(status: Optional[str] = None, u=Depends(_need(PROCURE_READ, "Procurement"))):
    return await _call(stock_orders.orders, status)


@procurement.post("/orders", status_code=201)
async def procurement_raise(payload: Dict[str, Any] = Body(...), u=Depends(_need(PROCURE_RAISE, "Raising a stock order"))):
    return await _call_dropping(_PROCUREMENT_VIEWS, stock_orders.raise_order, u, payload)


@procurement.post("/orders/{oid}/approve")
async def procurement_approve(oid: int, u=Depends(_need(PROCURE_READ, "Procurement"))):
    return await _call_dropping(_PROCUREMENT_VIEWS, stock_orders.approve, u, oid)


@procurement.post("/orders/{oid}/place")
async def procurement_place(oid: int, payload: Dict[str, Any] = Body(...), u=Depends(_need(PROCURE_PLACE, "Placing a stock order"))):
    return await _call_dropping(_PROCUREMENT_VIEWS, stock_orders.place, u, oid, payload)


@procurement.post("/orders/{oid}/cancel")
async def procurement_cancel(oid: int, payload: Dict[str, Any] = Body(...), u=Depends(_need(PROCURE_PLACE, "Cancelling a stock order"))):
    return await _call_dropping(_PROCUREMENT_VIEWS, stock_orders.cancel, u, oid, payload.get("reason") or "")


@procurement.get("/suppliers")
async def procurement_suppliers(u=Depends(_need(PROCURE_READ, "Procurement"))):
    return await _call(stock_orders.suppliers)


# ---------------------------------------------------------------------------
# Patient Relations
# ---------------------------------------------------------------------------

@relations.get("/overview")
async def relations_overview(u=Depends(_need(RELATIONS, "Patient relations"))):
    return await _call(shared_response, "relations:overview", 300, payer_relations.overview)


@relations.get("/payers")
async def relations_directory(u=Depends(_need(RELATIONS, "Patient relations"))):
    return await _call(shared_response, "relations:payers", 300, payer_relations.directory)


@relations.get("/payers/{payer_id}")
async def relations_profile(payer_id: int, u=Depends(_need(RELATIONS, "Patient relations"))):
    return await _call(payer_relations.profile, payer_id)


@relations.post("/payers/{payer_id}/contacts", status_code=201)
async def relations_contact(payer_id: int, payload: Dict[str, Any] = Body(...), u=Depends(_need(RELATIONS, "Patient relations"))):
    return await _call_dropping(_RELATIONS_VIEWS, payer_relations.log_contact, u, payer_id, payload)


@relations.post("/contacts/{contact_id}/done")
async def relations_done(contact_id: str, u=Depends(_need(RELATIONS, "Patient relations"))):
    return await _call_dropping(_RELATIONS_VIEWS, payer_relations.complete_follow_up, u, contact_id)


# ---------------------------------------------------------------------------
# Calendar over the records
# ---------------------------------------------------------------------------

@calendar.get("")
async def calendar_feed(request: Request, start: str = Query(..., alias="from"), end: str = Query(..., alias="to"),
                        sources: Optional[str] = None):
    u = verify_jwt(request)
    return await _call(hospital_calendar.feed, u, _date(start, "from"), _date(end, "to"),
                       [s for s in (sources or "").split(",") if s] or None)


@calendar.post("/reschedule")
async def calendar_reschedule(request: Request, payload: Dict[str, Any] = Body(...)):
    u = verify_jwt(request)
    return await _call(hospital_calendar.reschedule, u, str(payload.get("source") or ""), str(payload.get("id") or ""),
                       _date(payload.get("date"), "date"))


# ---------------------------------------------------------------------------
# Reports about one record
# ---------------------------------------------------------------------------

@reports.get("/catalog")
def report_catalog(request: Request):
    u = verify_jwt(request)
    return report_subjects.catalog(u.get("roles"))


@reports.get("/subjects/{kind}")
async def report_subject_list(kind: str, request: Request, search: str = ""):
    u = verify_jwt(request)
    return {"items": await _call(report_subjects.list_subjects, u.get("roles"), kind, search)}


@reports.get("/dossier")
async def report_dossier(request: Request, report_type: str, kind: str, id: str):
    u = verify_jwt(request)
    d = await _call(report_subjects.dossier, u.get("roles"), report_type, kind, id)
    return {**d, "sections": [s["title"] for s in report_subjects.sections_for(report_type, kind)],
            "needs_signoff": bool(report_subjects.TYPE_BY_KEY[report_type].get("needs_signoff"))}


@reports.post("/from-record", status_code=201)
async def report_from_record(request: Request, payload: Dict[str, Any] = Body(...)):
    u = verify_jwt(request)
    return await _call(record_reports.generate, u, str(payload.get("report_type") or ""), str(payload.get("kind") or ""),
                       str(payload.get("id") or ""), payload.get("notes"))


@reports.get("/library")
async def report_library(request: Request, kind: Optional[str] = None, subject_id: Optional[str] = None):
    u = verify_jwt(request)
    return {"reports": await _call(record_reports.library, u, kind, subject_id)}


@reports.get("/record/{rid}")
async def report_get(rid: str, request: Request):
    u = verify_jwt(request)
    return await _call(record_reports.get, u, rid)


@reports.post("/record/{rid}/approve")
async def report_approve(rid: str, request: Request):
    u = verify_jwt(request)
    return await _call(record_reports.approve, u, rid)


@reports.get("/record/{rid}/docx")
async def report_docx(rid: str, request: Request):
    u = verify_jwt(request)
    r = await _call(record_reports.get, u, rid)
    from src.routers.reports import _build_report_docx
    try:
        data = _build_report_docx(r["full_report"], r["title"], r["report_type"])
    except RuntimeError as exc:
        raise HTTPException(501, str(exc))
    name = f"royan_{r['report_type']}_{r['created_at']:%Y%m%d}.docx"
    return StreamingResponse(io.BytesIO(data), media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                             headers={"Content-Disposition": f'attachment; filename="{name}"'})


# ---------------------------------------------------------------------------
# Compliance and pharmacy QC (quality_hub) - these pages used to call /compliance/* and /qc/*,
# routes from the pharma product that this hospital never had.
# ---------------------------------------------------------------------------

@quality.get("/compliance-overview")
async def quality_compliance(u=Depends(_need(QUALITY_READ, "Compliance"))):
    return await _call(quality_hub.compliance)


@quality.get("/pharmacy-qc")
async def quality_pharmacy_qc(u=Depends(_need(PHARMACY_QC, "Pharmacy quality control"))):
    return await _call(quality_hub.pharmacy_qc)


ROUTERS = (procurement, relations, calendar, reports, quality)
