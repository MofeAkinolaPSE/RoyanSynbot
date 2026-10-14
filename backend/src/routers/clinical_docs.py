"""Clinical Documentation Router — ICD-10 lookup + Problem List."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.constants import (
    TABLE_ENCOUNTERS,
    POSTING_SEVERITY_ALLOWED,
    POSTING_TYPE_ALLOWED,
    TABLE_ACCOUNT_RECEIPTS,
    TABLE_ALLERGEN_CATALOG,
    TABLE_DISCOUNT_REQUESTS,
    TABLE_DOCTOR_SCHEDULE_BLOCKS,
    TABLE_HOPE_REFERENCE_ARCHIVE,
    TABLE_PATIENT_CARD_TRANSACTIONS,
    TABLE_SETTLEMENT_BILLINGS,
    TABLE_VOUCHER_ENTRIES,
    TABLE_BILLING_SUMMARIES,
    TABLE_BILLING_TRANSACTIONS,
    TABLE_CLINICAL_REMINDERS,
    TABLE_DEPARTMENTS,
    TABLE_DIAGNOSIS_CATALOG,
    TABLE_DRUG_FORMULARY,
    TABLE_ENCOUNTER_NOTES,
    TABLE_EXAM_TEMPLATE_FINDINGS,
    TABLE_EXAM_TEMPLATES,
    TABLE_ICD10_CODES,
    TABLE_MEDICATION_ADMIN,
    TABLE_NOTE_ADDENDA,
    TABLE_NOTE_TEMPLATE_TEXTS,
    TABLE_NOTE_TEMPLATES,
    TABLE_NOTE_TITLES,
    TABLE_NURSING_FLOWSHEET,
    TABLE_ORDER_SET_ITEMS,
    TABLE_ORDER_SETS,
    TABLE_PATIENT_DOCUMENTS_IDX,
    TABLE_PATIENT_POSTINGS,
    TABLE_PATIENTS,
    TABLE_PROBLEM_LIST,
    TABLE_RADIOLOGY_CATALOG,
    TABLE_SMART_PHRASE_OPTIONS,
    TABLE_SMART_PHRASES,
    TABLE_SURGERY_CATALOG,
    TABLE_TARIFF_CATALOG,
    TABLE_WARD_STAY_HISTORY,
)
from src.db import audit_event, db
from src.middleware import verify_jwt
from src.services.patient_context import invalidate_patient_context
from src.services.clinical_reminders import evaluate_reminders
from src.services.staff_ops import get_staff_by_email

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/clinical", tags=["Clinical Documentation"])

PROBLEM_STATUS_ALLOWED = {"active", "resolved", "inactive", "chronic"}


# ─── Schemas ─────────────────────────────────────────────────────────────────

class ProblemCreate(BaseModel):
    icd10_code: Optional[str] = None
    description: str = Field(..., min_length=1)
    encounter_id: Optional[int] = None
    onset_date: Optional[str] = None
    status: str = "active"

    model_config = {"extra": "ignore"}


class ProblemUpdate(BaseModel):
    status: Optional[str] = None
    description: Optional[str] = None
    resolved_at: Optional[str] = None

    model_config = {"extra": "ignore"}


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _get_patient(patient_id: int) -> dict:
    r = db.table(TABLE_PATIENTS).select("id,mrn").eq("id", patient_id).execute()
    if not r.data:
        raise HTTPException(status_code=404, detail=f"Patient {patient_id} not found")
    return r.data[0]


# ─── ICD-10 Search ───────────────────────────────────────────────────────────

@router.get("/icd10")
def search_icd10(
    q: str = Query(..., min_length=2, description="Code prefix or diagnosis keyword"),
    limit: int = Query(20, ge=1, le=50),
    user=Depends(verify_jwt),
):
    """Search ICD-10 codes by code prefix or description keyword."""
    q = q.strip()
    try:
        results = (
            db.table(TABLE_ICD10_CODES)
            .select("code,description,category")
            .or_(f"code.ilike.{q}%,description.ilike.%{q}%")
            .order("code")
            .limit(limit)
            .execute()
        )
        return {"codes": results.data or [], "count": len(results.data or [])}
    except Exception as exc:
        logger.error("ICD-10 search failed: %s", exc)
        return {"codes": [], "count": 0}


_ICD_STOP = {
    "patient", "patients", "complain", "complains", "complained", "complaint", "complaints", "history", "presents", "presented",
    "presenting", "with", "without", "since", "about", "days", "weeks", "months", "years", "year", "hours", "today", "yesterday",
    "also", "that", "this", "there", "their", "they", "have", "been", "were", "which", "when", "what", "from", "into", "after",
    "before", "while", "some", "more", "less", "very", "noted", "note", "left", "right", "both", "mild", "severe", "moderate",
    "associated", "following", "known", "case", "review", "examination", "exam", "normal", "plan", "assessment", "likely",
}


@router.get("/icd10/suggest")
def suggest_icd10(
    text: str = Query(..., min_length=3, description="What the doctor has written: complaint, history, assessment"),
    limit: int = Query(10, ge=1, le=25),
    user=Depends(verify_jwt),
):
    """ICD-10 suggestions read from the doctor's own words, so the diagnosis is pre-filled rather than looked up.
    Royan's most-common diagnoses rank first, then the full ICD-10 book; the more of the note's words a diagnosis
    matches, the higher it ranks. The doctor still chooses - nothing is applied without a tick."""
    import re
    from src.fin.db import q as _q, tx as _tx
    words: list[str] = []
    for w in re.findall(r"[a-zA-Z]{4,}", text.lower()):
        if w not in _ICD_STOP and w not in words:
            words.append(w)
    words = words[:10]
    if not words:
        return {"codes": [], "words": []}
    try:
        with _tx() as conn:
            rows = _q(conn, """
                SELECT code, description, source, hits FROM (
                    SELECT icd_code AS code, description, 'common' AS source,
                           (SELECT COUNT(*) FROM unnest(%s::text[]) t WHERE description ILIKE '%%' || t || '%%') AS hits
                    FROM royan_diagnosis_catalog WHERE is_active AND icd_code IS NOT NULL
                    UNION ALL
                    SELECT code, description, 'icd10',
                           (SELECT COUNT(*) FROM unnest(%s::text[]) t WHERE description ILIKE '%%' || t || '%%')
                    FROM royan_icd10_codes
                ) x WHERE hits > 0
                ORDER BY hits DESC, (source = 'common') DESC, length(description), code
                LIMIT %s""", (words, words, limit * 3))
    except Exception as exc:
        logger.error("ICD-10 suggestion failed: %s", exc)
        return {"codes": [], "words": words}
    seen, out = set(), []
    for r in rows:
        if r["code"] in seen:
            continue
        seen.add(r["code"])
        out.append({"code": r["code"], "description": r["description"], "source": r["source"], "matches": r["hits"]})
        if len(out) >= limit:
            break
    return {"codes": out, "words": words}


# ─── Note Titles (Notes Master) ───────────────────────────────────────────────

@router.get("/note-titles")
def list_note_titles(
    department: Optional[str] = Query(None, description="Department code, e.g. OPD"),
    user=Depends(verify_jwt),
):
    """Department-scoped note title catalog. Never errors — returns [] so the
    frontend can gracefully fall back to free-text note entry if unseeded."""
    try:
        dept_id = None
        if department:
            dept = db.table(TABLE_DEPARTMENTS).select("id").eq("code", department.strip().upper()).execute()
            if dept.data:
                dept_id = dept.data[0]["id"]

        query = db.table(TABLE_NOTE_TITLES).select("*").eq("is_active", True)
        if dept_id is not None:
            query = query.or_(f"department_id.is.null,department_id.eq.{dept_id}")
        else:
            query = query.is_("department_id", None)
        rows = query.order("sort_order").execute().data or []

        user_roles = set(user.get("roles") or user.get("permissions") or [])
        visible = [
            r for r in rows
            if "admin" in user_roles or not r.get("allowed_roles") or user_roles.intersection(r["allowed_roles"])
        ]
        return {"titles": visible, "count": len(visible)}
    except Exception as exc:
        logger.error("Note title lookup failed: %s", exc)
        return {"titles": [], "count": 0}


# ─── Drug Formulary Search ─────────────────────────────────────────────────────

@router.get("/drugs")
def search_drugs(
    q: str = Query(..., min_length=2, description="Generic name, brand name, or drug code"),
    limit: int = Query(20, ge=1, le=50),
    user=Depends(verify_jwt),
):
    """Search the drug formulary. Returns [] until real formulary data is
    imported — this is prepared search logic, not fake data (the table exists
    via migration 130 but is not yet seeded)."""
    q = q.strip()
    try:
        results = (
            db.table(TABLE_DRUG_FORMULARY)
            .select("id,code,generic_name,brand_name,drug_class,form,strength,unit,route,requires_prescription,is_controlled")
            .eq("is_active", True)
            .or_(f"generic_name.ilike.%{q}%,brand_name.ilike.%{q}%,code.ilike.{q}%")
            .order("generic_name")
            .limit(limit)
            .execute()
        )
        return {"drugs": results.data or [], "count": len(results.data or [])}
    except Exception as exc:
        logger.error("Drug formulary search failed: %s", exc)
        return {"drugs": [], "count": 0}


# ─── Problem List ─────────────────────────────────────────────────────────────

@router.post("/patients/{patient_id}/problems", status_code=201)
def add_problem(patient_id: int, payload: ProblemCreate, user=Depends(verify_jwt)):
    """Add a problem to a patient's problem list."""
    _get_patient(patient_id)
    if payload.status not in PROBLEM_STATUS_ALLOWED:
        raise HTTPException(status_code=422, detail=f"status must be one of {sorted(PROBLEM_STATUS_ALLOWED)}")

    data = {
        "patient_id": patient_id,
        "icd10_code": payload.icd10_code,
        "description": payload.description,
        "encounter_id": payload.encounter_id,
        "onset_date": payload.onset_date,
        "status": payload.status,
        "noted_by": user.get("sub") or user.get("email"),
    }
    try:
        result = db.table(TABLE_PROBLEM_LIST).insert(data).execute()
    except Exception as exc:
        logger.error("Problem insert failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to add problem")

    problem = (result.data or [data])[0]
    audit_event(
        "problem_added",
        {"icd10_code": payload.icd10_code, "description": payload.description},
        actor_id=user.get("sub"),
        subject_type="patient",
        subject_id=str(patient_id),
    )
    return {"ok": True, "problem": problem}


@router.get("/patients/{patient_id}/problems")
def list_problems(
    patient_id: int,
    status: Optional[str] = Query(None),
    user=Depends(verify_jwt),
):
    """List all problems on a patient's problem list."""
    _get_patient(patient_id)
    query = (
        db.table(TABLE_PROBLEM_LIST)
        .select("*")
        .eq("patient_id", patient_id)
        .order("created_at", desc=True)
    )
    if status:
        query = query.eq("status", status)
    result = query.execute()
    return {"problems": result.data or [], "count": len(result.data or [])}


@router.patch("/problems/{problem_id}")
def update_problem(problem_id: int, payload: ProblemUpdate, user=Depends(verify_jwt)):
    """Update a problem status or description."""
    r = db.table(TABLE_PROBLEM_LIST).select("id,patient_id").eq("id", problem_id).execute()
    if not r.data:
        raise HTTPException(status_code=404, detail=f"Problem {problem_id} not found")

    updates = payload.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    if "status" in updates and updates["status"] not in PROBLEM_STATUS_ALLOWED:
        raise HTTPException(status_code=422, detail=f"status must be one of {sorted(PROBLEM_STATUS_ALLOWED)}")

    try:
        db.table(TABLE_PROBLEM_LIST).update(updates).eq("id", problem_id).execute()
    except Exception as exc:
        logger.error("Problem update failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to update problem")

    audit_event(
        "problem_updated",
        {"problem_id": problem_id, "fields": list(updates.keys())},
        actor_id=user.get("sub"),
        subject_type="patient",
        subject_id=str(r.data[0]["patient_id"]),
    )
    return {"ok": True, "problem_id": problem_id, "updated_fields": list(updates.keys())}


@router.delete("/problems/{problem_id}", status_code=200)
def delete_problem(problem_id: int, user=Depends(verify_jwt)):
    """Remove a problem from the problem list."""
    r = db.table(TABLE_PROBLEM_LIST).select("id,patient_id").eq("id", problem_id).execute()
    if not r.data:
        raise HTTPException(status_code=404, detail=f"Problem {problem_id} not found")
    patient_id = r.data[0]["patient_id"]
    try:
        db.table(TABLE_PROBLEM_LIST).update({"status": "inactive"}).eq("id", problem_id).execute()
    except Exception as exc:
        logger.error("Problem delete failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to remove problem")

    audit_event(
        "problem_removed",
        {"problem_id": problem_id},
        actor_id=user.get("sub"),
        subject_type="patient",
        subject_id=str(patient_id),
    )
    return {"ok": True, "problem_id": problem_id}


# ─── Patient Postings (CPRS "Postings" cover-sheet card) ──────────────────────
# Patient-specific clinical flags/notices a clinician should see immediately —
# e.g. "Fall risk", "NPO after midnight", "DNR — see advance directive".
# Deliberately not the same thing as VistA's sysadmin broadcast messages
# (which have no per-patient equivalent here); this mirrors the Problem List
# shape above almost verbatim since it's the same kind of small patient-list
# adjunct.

class PostingCreate(BaseModel):
    posting_type: str = "alert"
    message: str = Field(..., min_length=1)
    severity: str = "info"

    model_config = {"extra": "ignore"}


@router.post("/patients/{patient_id}/postings", status_code=201)
def add_posting(patient_id: int, payload: PostingCreate, user=Depends(verify_jwt)):
    """Add a clinical posting/flag to a patient's chart."""
    _get_patient(patient_id)
    if payload.posting_type not in POSTING_TYPE_ALLOWED:
        raise HTTPException(status_code=422, detail=f"posting_type must be one of {sorted(POSTING_TYPE_ALLOWED)}")
    if payload.severity not in POSTING_SEVERITY_ALLOWED:
        raise HTTPException(status_code=422, detail=f"severity must be one of {sorted(POSTING_SEVERITY_ALLOWED)}")

    data = {
        "patient_id": patient_id,
        "posting_type": payload.posting_type,
        "message": payload.message,
        "severity": payload.severity,
        "created_by": user.get("sub") or user.get("email"),
    }
    try:
        result = db.table(TABLE_PATIENT_POSTINGS).insert(data).execute()
    except Exception as exc:
        logger.error("Posting insert failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to add posting")

    posting = (result.data or [data])[0]
    invalidate_patient_context(patient_id)
    audit_event(
        "posting_added",
        {"posting_type": payload.posting_type, "message": payload.message},
        actor_id=user.get("sub"),
        subject_type="patient",
        subject_id=str(patient_id),
    )
    return {"ok": True, "posting": posting}


@router.get("/patients/{patient_id}/postings")
def list_postings(
    patient_id: int,
    active_only: bool = Query(True),
    user=Depends(verify_jwt),
):
    """List clinical postings for a patient — unresolved only by default."""
    _get_patient(patient_id)
    query = (
        db.table(TABLE_PATIENT_POSTINGS)
        .select("*")
        .eq("patient_id", patient_id)
        .order("created_at", desc=True)
    )
    if active_only:
        query = query.is_("resolved_at", None)
    result = query.execute()
    return {"postings": result.data or [], "count": len(result.data or [])}


@router.patch("/postings/{posting_id}/resolve")
def resolve_posting(posting_id: int, user=Depends(verify_jwt)):
    """Mark a posting as resolved/acknowledged."""
    r = db.table(TABLE_PATIENT_POSTINGS).select("id,patient_id").eq("id", posting_id).execute()
    if not r.data:
        raise HTTPException(status_code=404, detail=f"Posting {posting_id} not found")
    patient_id = r.data[0]["patient_id"]

    try:
        db.table(TABLE_PATIENT_POSTINGS).update({
            "resolved_at": datetime.now(timezone.utc).isoformat(),
            "resolved_by": user.get("sub") or user.get("email"),
        }).eq("id", posting_id).execute()
    except Exception as exc:
        logger.error("Posting resolve failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to resolve posting")

    invalidate_patient_context(patient_id)
    audit_event(
        "posting_resolved",
        {"posting_id": posting_id},
        actor_id=user.get("sub"),
        subject_type="patient",
        subject_id=str(patient_id),
    )
    return {"ok": True, "posting_id": posting_id}


# ─── Clinical Reminders (CPRS "Clinical Reminders" cover-sheet card) ──────────
# Evaluated fresh on every GET rather than cached — small, cheap queries, and
# staff dismissing one should be reflected immediately, not after a TTL.

@router.get("/patients/{patient_id}/reminders")
def list_reminders(patient_id: int, user=Depends(verify_jwt)):
    """Evaluate and return active (non-dismissed) clinical reminders for a patient."""
    _get_patient(patient_id)
    reminders = evaluate_reminders(patient_id)
    return {"reminders": reminders, "count": len(reminders)}


@router.patch("/reminders/{reminder_id}/dismiss")
def dismiss_reminder(reminder_id: int, user=Depends(verify_jwt)):
    """Dismiss/acknowledge a clinical reminder."""
    r = db.table(TABLE_CLINICAL_REMINDERS).select("id,patient_id").eq("id", reminder_id).execute()
    if not r.data:
        raise HTTPException(status_code=404, detail=f"Reminder {reminder_id} not found")
    patient_id = r.data[0]["patient_id"]

    try:
        db.table(TABLE_CLINICAL_REMINDERS).update({
            "dismissed_at": datetime.now(timezone.utc).isoformat(),
            "dismissed_by": user.get("sub") or user.get("email"),
        }).eq("id", reminder_id).execute()
    except Exception as exc:
        logger.error("Reminder dismiss failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to dismiss reminder")

    invalidate_patient_context(patient_id)
    audit_event(
        "reminder_dismissed",
        {"reminder_id": reminder_id},
        actor_id=user.get("sub"),
        subject_type="patient",
        subject_id=str(patient_id),
    )
    return {"ok": True, "reminder_id": reminder_id}


# ═════════════════════════════════════════════════════════════════════════════
# PHASE B0 — expose the migrated Hope data (migrations 179-195)
#
# 5.2M rows landed in Phase A across 51 tables, but 17 of those tables had no
# endpoint at all — the data was in Postgres and unreachable from the browser.
# Everything below follows the house pattern set by search_icd10 above:
# explicit column lists, bounded limits, verify_jwt, a {"<plural>": [...],
# "count": n} envelope, and a never-throws except so an unseeded table degrades
# to [] instead of 500ing.
# ═════════════════════════════════════════════════════════════════════════════

# ─── SOAP section templates ──────────────────────────────────────────────────
# A template is a BUNDLE OF SELECTABLE PHRASES, not a text blob. Each phrase
# carries a context_type, so the SAME template opened from the Assessment
# button yields only its assessment phrases, and from Plan only its plan
# phrases. That routing is the whole point of the per-section picker.

# Visibility: system templates and shared personal ones are visible to everyone;
# a private personal template only to its owner. Every migrated personal
# template is is_shared=true, so this hides nothing that was visible before.
# Doctors can author their own (POST/PUT/DELETE below); only the owner can
# change or remove one, and system templates are read-only.

NOTE_TEMPLATE_CONTEXTS = (
    "subjective", "objective", "assessment", "plan", "general",
    "chief_complaint", "review_of_systems",
)
NOTE_TEMPLATE_AUTHOR_ROLES = {"doctor", "admin"}
_TEMPLATE_SCAN_LIMIT = 2000  # visibility is filtered in Python, so read past `limit` first


def _actor_staff_id(user: dict) -> Optional[str]:
    email = (user or {}).get("email")
    if not email:
        return None
    try:
        staff = get_staff_by_email(email)
    except Exception as exc:
        logger.warning("Staff lookup for template owner failed: %s", exc)
        return None
    return str(staff["id"]) if staff and staff.get("id") else None


def _template_visible(row: dict, me: Optional[str]) -> bool:
    if row.get("scope") != "personal" or row.get("is_shared"):
        return True
    return bool(me) and str(row.get("owner_staff_id") or "") == me


def _decorate_template(row: dict, me: Optional[str]) -> dict:
    return {**row, "is_mine": bool(me) and str(row.get("owner_staff_id") or "") == me}


@router.get("/note-templates")
def list_note_templates(
    context_type: Optional[str] = Query(None, description="subjective|objective|assessment|plan|chief_complaint|review_of_systems|general"),
    scope: Optional[str] = Query(None, description="system|personal"),
    q: Optional[str] = Query(None, description="Filter by template name"),
    mine: bool = Query(False, description="Only templates the caller owns"),
    limit: int = Query(200, ge=1, le=500),
    user=Depends(verify_jwt),
):
    """Note-template catalog for the per-SOAP-section pickers.

    When context_type is given, only templates that actually own >=1 phrase of
    that type are returned — otherwise a doctor opening the Assessment picker
    would scroll 528 templates to find the ~90 with assessment content.
    Each row carries is_mine so the picker can list the caller's own first and
    offer Edit/Delete on them.
    """
    try:
        me = _actor_staff_id(user)
        query = (
            db.table(TABLE_NOTE_TEMPLATES)
            .select("id,name,scope,category,owner_staff_id,is_shared,department")
            .eq("is_active", True)
        )
        if scope:
            query = query.eq("scope", scope.strip().lower())
        if q and q.strip():
            query = query.ilike("name", f"%{q.strip()}%")
        if mine:
            if not me:
                return {"templates": [], "count": 0}
            query = query.eq("owner_staff_id", me)
        rows = query.order("name").limit(_TEMPLATE_SCAN_LIMIT).execute().data or []
        rows = [_decorate_template(r, me) for r in rows if _template_visible(r, me)]

        if context_type:
            ctx = context_type.strip().lower()
            texts = (
                db.table(TABLE_NOTE_TEMPLATE_TEXTS)
                .select("template_id")
                .eq("context_type", ctx)
                .execute()
                .data
                or []
            )
            with_ctx = {t["template_id"] for t in texts}
            rows = [r for r in rows if r["id"] in with_ctx]

        rows = rows[:limit]
        return {"templates": rows, "count": len(rows)}
    except Exception as exc:
        logger.error("Note template list failed: %s", exc)
        return {"templates": [], "count": 0}


@router.get("/note-templates/{template_id}/texts")
def list_note_template_texts(
    template_id: int,
    context_type: Optional[str] = Query(None),
    limit: int = Query(300, ge=1, le=1000),
    user=Depends(verify_jwt),
):
    """The selectable phrases inside one template, optionally narrowed to the
    SOAP section that asked for them."""
    try:
        tpl = (
            db.table(TABLE_NOTE_TEMPLATES)
            .select("id,scope,owner_staff_id,is_shared")
            .eq("id", template_id)
            .execute()
            .data
            or []
        )
        if tpl and not _template_visible(tpl[0], _actor_staff_id(user)):
            return {"texts": [], "count": 0}
        query = (
            db.table(TABLE_NOTE_TEMPLATE_TEXTS)
            .select("id,template_id,context_type,text,sort_order")
            .eq("template_id", template_id)
        )
        if context_type:
            query = query.eq("context_type", context_type.strip().lower())
        rows = query.order("sort_order").limit(limit).execute().data or []
        return {"texts": rows, "count": len(rows)}
    except Exception as exc:
        logger.error("Note template text lookup failed: %s", exc)
        return {"texts": [], "count": 0}


class NoteTemplatePhrase(BaseModel):
    context_type: str
    text: str = Field(..., min_length=1, max_length=2000)


class NoteTemplateWrite(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    category: Optional[str] = Field(None, max_length=60)
    is_shared: bool = False
    phrases: list[NoteTemplatePhrase] = Field(..., min_length=1, max_length=200)


def _require_template_author(user: dict) -> str:
    roles = {str(r).lower() for r in (user.get("roles") or [])}
    if not roles & NOTE_TEMPLATE_AUTHOR_ROLES:
        raise HTTPException(status_code=403, detail="Only doctors can create note templates.")
    me = _actor_staff_id(user)
    if not me:
        raise HTTPException(
            status_code=400,
            detail="Your login is not linked to a staff record, so a template cannot be saved under your name. Ask an administrator.",
        )
    return me


def _clean_template_payload(payload: NoteTemplateWrite) -> tuple[str, list[dict]]:
    name = " ".join(payload.name.split())
    phrases: list[dict] = []
    for i, p in enumerate(payload.phrases):
        ctx = p.context_type.strip().lower()
        if ctx not in NOTE_TEMPLATE_CONTEXTS:
            raise HTTPException(status_code=422, detail=f"Unknown section '{p.context_type}'.")
        text = p.text.strip()
        if text:
            phrases.append({"context_type": ctx, "text": text, "sort_order": i})
    if not name:
        raise HTTPException(status_code=422, detail="Give the template a name.")
    if not phrases:
        raise HTTPException(status_code=422, detail="Add at least one phrase.")
    return name, phrases


def _assert_unique_name(name: str, me: str, exclude_id: Optional[int] = None) -> None:
    rows = (
        db.table(TABLE_NOTE_TEMPLATES)
        .select("id,name")
        .eq("owner_staff_id", me)
        .eq("is_active", True)
        .execute()
        .data
        or []
    )
    if any(r["name"].strip().lower() == name.lower() and r["id"] != exclude_id for r in rows):
        raise HTTPException(status_code=409, detail=f"You already have a template called '{name}'.")


def _owned_template(template_id: int, me: str) -> dict:
    rows = (
        db.table(TABLE_NOTE_TEMPLATES)
        .select("id,name,scope,owner_staff_id,is_active")
        .eq("id", template_id)
        .execute()
        .data
        or []
    )
    if not rows or not rows[0].get("is_active"):
        raise HTTPException(status_code=404, detail="Template not found.")
    tpl = rows[0]
    if tpl.get("scope") != "personal":
        raise HTTPException(status_code=403, detail="Shared hospital templates cannot be changed.")
    if str(tpl.get("owner_staff_id") or "") != me:
        raise HTTPException(status_code=403, detail="You can only change your own templates.")
    return tpl


@router.post("/note-templates", status_code=201)
def create_note_template(payload: NoteTemplateWrite, user=Depends(verify_jwt)):
    """Save a doctor's own template: a name plus phrases, each tagged with the
    SOAP section it belongs to. Private unless is_shared."""
    me = _require_template_author(user)
    name, phrases = _clean_template_payload(payload)
    _assert_unique_name(name, me)
    try:
        tpl = (
            db.table(TABLE_NOTE_TEMPLATES)
            .insert({
                "name": name,
                "scope": "personal",
                "category": (payload.category or "").strip() or None,
                "owner_staff_id": me,
                "is_shared": payload.is_shared,
                "is_active": True,
            })
            .execute()
            .data
            or []
        )[0]
        db.table(TABLE_NOTE_TEMPLATE_TEXTS).insert(
            [{**p, "template_id": tpl["id"]} for p in phrases]
        ).execute()
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Note template create failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to save the template.")
    audit_event(
        "note_template_created",
        {"name": name, "phrases": len(phrases), "is_shared": payload.is_shared},
        actor_id=user.get("sub"),
        subject_type="note_template",
        subject_id=str(tpl["id"]),
    )
    return {"ok": True, "template": _decorate_template(tpl, me), "phrases": len(phrases)}


@router.put("/note-templates/{template_id}")
def update_note_template(template_id: int, payload: NoteTemplateWrite, user=Depends(verify_jwt)):
    """Replace the name, sharing and phrases of one of the caller's templates.
    Notes already written from it are plain text and are not affected."""
    me = _require_template_author(user)
    _owned_template(template_id, me)
    name, phrases = _clean_template_payload(payload)
    _assert_unique_name(name, me, exclude_id=template_id)
    try:
        old_ids = [
            r["id"] for r in (
                db.table(TABLE_NOTE_TEMPLATE_TEXTS).select("id").eq("template_id", template_id).execute().data or []
            )
        ]
        # New phrases go in before the old ones come out, so a failure part-way
        # leaves the template with its previous content rather than empty.
        db.table(TABLE_NOTE_TEMPLATE_TEXTS).insert(
            [{**p, "template_id": template_id} for p in phrases]
        ).execute()
        if old_ids:
            db.table(TABLE_NOTE_TEMPLATE_TEXTS).delete().in_("id", old_ids).execute()
        db.table(TABLE_NOTE_TEMPLATES).update({
            "name": name,
            "category": (payload.category or "").strip() or None,
            "is_shared": payload.is_shared,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", template_id).execute()
    except Exception as exc:
        logger.error("Note template update failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to update the template.")
    audit_event(
        "note_template_updated",
        {"name": name, "phrases": len(phrases), "is_shared": payload.is_shared},
        actor_id=user.get("sub"),
        subject_type="note_template",
        subject_id=str(template_id),
    )
    return {"ok": True, "id": template_id, "phrases": len(phrases)}


@router.delete("/note-templates/{template_id}")
def delete_note_template(template_id: int, user=Depends(verify_jwt)):
    """Remove one of the caller's templates from the pickers. Soft delete:
    the row stays for the audit trail."""
    me = _require_template_author(user)
    tpl = _owned_template(template_id, me)
    try:
        db.table(TABLE_NOTE_TEMPLATES).update({
            "is_active": False,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", template_id).execute()
    except Exception as exc:
        logger.error("Note template delete failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to delete the template.")
    audit_event(
        "note_template_deleted",
        {"name": tpl.get("name")},
        actor_id=user.get("sub"),
        subject_type="note_template",
        subject_id=str(template_id),
    )
    return {"ok": True, "id": template_id}


# ─── ROS / physical-exam finding builder ─────────────────────────────────────

# Hope left a handful of authoring test rows in the exam-template table
# ("TestTempROS1" has 4 findings where real organ systems have 1,259-7,502;
# "TestTempPE1"/"TestTempPE2"/"TEST PE" likewise). They sort to the top, so an
# unfiltered ROS picker opens on "TestTempROS1" and reads as broken. Filtered
# by name here rather than deleted from the table, so the migrated data stays
# a faithful copy of the source.
_EXAM_TEMPLATE_TEST_MARKERS = ("testtemp", "test pe", "test ros")


def _is_test_exam_template(organ_system: Optional[str]) -> bool:
    s = (organ_system or "").strip().lower()
    return any(m in s for m in _EXAM_TEMPLATE_TEST_MARKERS)


@router.get("/exam-templates")
def list_exam_templates(
    category: Optional[str] = Query(None, description="'Review Of System' | 'Physical Examination' | 'HPI'"),
    patient_sex: Optional[str] = Query(None, description="Filters out female-only templates for male patients"),
    include_test: bool = Query(False, description="Include Hope's authoring test rows (debug only)"),
    user=Depends(verify_jwt),
):
    """Organ-system templates for the Objective/ROS builders.

    Physical Examination templates legitimately carry far fewer findings than
    Review Of System ones (452 total vs 41,385) — PE findings are full prose
    sentences, ROS findings are short symptom toggles. A small PE template is
    normal, not a data gap.
    """
    try:
        query = db.table(TABLE_EXAM_TEMPLATES).select(
            "id,category,organ_system,is_female_only,sort_order"
        ).eq("is_active", True)
        if category:
            query = query.eq("category", category.strip())
        rows = query.order("sort_order").execute().data or []

        if not include_test:
            rows = [r for r in rows if not _is_test_exam_template(r.get("organ_system"))]

        if patient_sex and patient_sex.strip().lower().startswith("m"):
            rows = [r for r in rows if not r.get("is_female_only")]

        return {"templates": rows, "count": len(rows)}
    except Exception as exc:
        logger.error("Exam template list failed: %s", exc)
        return {"templates": [], "count": 0}


@router.get("/exam-templates/{template_id}/findings")
def list_exam_template_findings(
    template_id: int,
    q: Optional[str] = Query(None, description="Substring filter — required in practice for large systems"),
    defaults_only: bool = Query(False, description="Return only is_default findings"),
    limit: int = Query(100, ge=1, le=300),
    user=Depends(verify_jwt),
):
    """Findings for one organ system.

    HARD-CAPPED ON PURPOSE. royan_exam_template_findings holds 44,405 rows —
    ~2,760 per organ system for Review Of System. Fetching a system's full set
    would freeze the panel, and the problem does not reproduce against a small
    dev stub. The UI shows is_default + the first page until the user types.
    """
    try:
        query = (
            db.table(TABLE_EXAM_TEMPLATE_FINDINGS)
            .select("id,exam_template_id,finding,is_default,sort_order")
            .eq("exam_template_id", template_id)
        )
        if defaults_only:
            query = query.eq("is_default", True)
        if q and q.strip():
            query = query.ilike("finding", f"%{q.strip()}%")
        rows = query.order("sort_order").limit(limit).execute().data or []
        return {"findings": rows, "count": len(rows), "capped": len(rows) >= limit}
    except Exception as exc:
        logger.error("Exam finding lookup failed: %s", exc)
        return {"findings": [], "count": 0, "capped": False}


# ─── Smart phrases (dot-phrase macros) ───────────────────────────────────────

@router.get("/smart-phrases")
def search_smart_phrases(
    q: Optional[str] = Query(None, description="Trigger prefix, e.g. 'NEXANK'"),
    is_nursing: Optional[bool] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    user=Depends(verify_jwt),
):
    """Dot-phrase macros. phrase_text may embed {token:id::default} placeholders
    whose selectable values come from /clinical/smart-phrase-options."""
    try:
        query = (
            db.table(TABLE_SMART_PHRASES)
            .select("id,phrase,synonyms,phrase_text,is_nursing,is_shared,owner_staff_id,department")
            .eq("is_active", True)
        )
        if is_nursing is not None:
            query = query.eq("is_nursing", is_nursing)
        if q and q.strip():
            s = q.strip()
            query = query.or_(f"phrase.ilike.{s}%,synonyms.ilike.%{s}%")
        rows = query.order("phrase").limit(limit).execute().data or []
        return {"phrases": rows, "count": len(rows)}
    except Exception as exc:
        logger.error("Smart phrase search failed: %s", exc)
        return {"phrases": [], "count": 0}


@router.get("/smart-phrase-options")
def list_smart_phrase_options(
    token_id: str = Query(..., description="The id inside {label:token_id::default}"),
    user=Depends(verify_jwt),
):
    """Selectable values for one placeholder token (e.g. token 15002 =
    GEN LATERALITY -> Right / Left / Bilateral / Both / both sides).

    Keyed by token_id, NOT by phrase — one option list is reused across many
    phrases, which is why this is a standalone lookup.
    """
    try:
        rows = (
            db.table(TABLE_SMART_PHRASE_OPTIONS)
            .select("id,token_id,list_name,option_text,sort_order")
            .eq("token_id", str(token_id).strip())
            .order("sort_order")
            .execute()
            .data
            or []
        )
        return {"options": rows, "count": len(rows)}
    except Exception as exc:
        logger.error("Smart phrase option lookup failed: %s", exc)
        return {"options": [], "count": 0}


# ─── Order sets ──────────────────────────────────────────────────────────────

@router.get("/order-sets")
def list_order_sets(user=Depends(verify_jwt)):
    """Condition-scoped order bundles — 'select a template, bulk-fill the
    standard orders'. Only 4 survived Phase A's content check; the rest of
    Hope's order sets held autocomplete test junk and were deliberately
    excluded (see migration 179)."""
    try:
        rows = (
            db.table(TABLE_ORDER_SETS)
            .select("id,name,description,department,specialty,is_shared")
            .eq("is_active", True)
            .order("name")
            .execute()
            .data
            or []
        )
        return {"order_sets": rows, "count": len(rows)}
    except Exception as exc:
        logger.error("Order set list failed: %s", exc)
        return {"order_sets": [], "count": 0}


@router.get("/order-sets/{order_set_id}/items")
def list_order_set_items(order_set_id: int, user=Depends(verify_jwt)):
    """Line items for one order set. `route` is a raw Hope numeric code with no
    lookup table anywhere in the dump — surfaced as-is rather than guessed at."""
    try:
        rows = (
            db.table(TABLE_ORDER_SET_ITEMS)
            .select("id,order_set_id,item_type,name,dosage,strength,dose_form,route,"
                    "frequency,duration,quantity,prn,dispense,instruction,sort_order")
            .eq("order_set_id", order_set_id)
            .order("sort_order")
            .execute()
            .data
            or []
        )
        return {"items": rows, "count": len(rows)}
    except Exception as exc:
        logger.error("Order set item lookup failed: %s", exc)
        return {"items": [], "count": 0}


# ─── Plan-section catalogs ───────────────────────────────────────────────────

@router.get("/radiology-catalog")
def search_radiology_catalog(
    q: Optional[str] = Query(None),
    limit: int = Query(30, ge=1, le=100),
    user=Depends(verify_jwt),
):
    """Radiology test catalog. Until now radiology orders carried a free-text
    test_name with no catalog behind them."""
    try:
        # base_price added in migration 200 (209 of 211 studies priced). Without
        # it every study reads as unpriced in a picker, and a walk-in gets
        # quoted nothing.
        query = db.table(TABLE_RADIOLOGY_CATALOG).select(
            "id,name,modality,base_price,test_group_ref,service_group_ref"
        ).eq("is_active", True)
        if q and q.strip():
            query = query.ilike("name", f"%{q.strip()}%")
        rows = query.order("name").limit(limit).execute().data or []
        return {"tests": rows, "count": len(rows)}
    except Exception as exc:
        logger.error("Radiology catalog search failed: %s", exc)
        return {"tests": [], "count": 0}


@router.get("/surgery-catalog")
def search_surgery_catalog(
    q: Optional[str] = Query(None),
    limit: int = Query(30, ge=1, le=100),
    user=Depends(verify_jwt),
):
    """Named procedures with surgeon fees — powers the Plan 'Procedure' button."""
    try:
        query = db.table(TABLE_SURGERY_CATALOG).select(
            "id,name,description,category_name,sub_category_name,surgeon_fee"
        ).eq("is_active", True)
        if q and q.strip():
            query = query.ilike("name", f"%{q.strip()}%")
        rows = query.order("name").limit(limit).execute().data or []
        return {"procedures": rows, "count": len(rows)}
    except Exception as exc:
        logger.error("Surgery catalog search failed: %s", exc)
        return {"procedures": [], "count": 0}


@router.get("/allergens")
def search_allergens(
    q: str = Query(..., min_length=2, description="Allergen name"),
    limit: int = Query(20, ge=1, le=50),
    user=Depends(verify_jwt),
):
    """Allergen name typeahead (18,926 entries) so allergy capture stops being
    free text. Requires q — an unfiltered list of 18k rows helps nobody."""
    try:
        rows = (
            db.table(TABLE_ALLERGEN_CATALOG)
            .select("id,name,concept_type")
            .eq("is_active", True)
            .ilike("name", f"%{q.strip()}%")
            .order("name")
            .limit(limit)
            .execute()
            .data
            or []
        )
        return {"allergens": rows, "count": len(rows)}
    except Exception as exc:
        logger.error("Allergen search failed: %s", exc)
        return {"allergens": [], "count": 0}


@router.get("/diagnosis-catalog")
def search_diagnosis_catalog(
    q: Optional[str] = Query(None),
    limit: int = Query(30, ge=1, le=100),
    user=Depends(verify_jwt),
):
    """Royan's own curated diagnosis list — the 'MOST COMMON DIAGNOSES' quick-pick
    table in the legacy Diagnosis Search modal. Complements the full 12,542-row
    ICD-10 search at /clinical/icd10, it does not replace it."""
    try:
        query = db.table(TABLE_DIAGNOSIS_CATALOG).select("id,icd_code,description,category")
        if q and q.strip():
            s = q.strip()
            query = query.or_(f"description.ilike.%{s}%,icd_code.ilike.{s}%")
        rows = query.order("description").limit(limit).execute().data or []
        return {"diagnoses": rows, "count": len(rows)}
    except Exception as exc:
        logger.error("Diagnosis catalog search failed: %s", exc)
        return {"diagnoses": [], "count": 0}


@router.get("/tariff-catalog")
def search_tariff_catalog(
    q: Optional[str] = Query(None),
    limit: int = Query(30, ge=1, le=100),
    user=Depends(verify_jwt),
):
    """Service price catalog. charge_amount is the reliable figure; cost_price
    was populated on only 1.5% of Hope's rows (see migration 188)."""
    try:
        query = db.table(TABLE_TARIFF_CATALOG).select(
            "id,name,service_group,service_type,charge_amount,cost_price"
        ).eq("is_active", True)
        if q and q.strip():
            query = query.ilike("name", f"%{q.strip()}%")
        rows = query.order("name").limit(limit).execute().data or []
        return {"services": rows, "count": len(rows)}
    except Exception as exc:
        logger.error("Tariff catalog search failed: %s", exc)
        return {"services": [], "count": 0}


# ─── Patient-scoped migrated history ─────────────────────────────────────────
# These back the new patient-chart cards. Each is capped and newest-first.

@router.get("/patients/{patient_id}/flowsheet")
def list_patient_flowsheet(
    patient_id: int,
    limit: int = Query(200, ge=1, le=1000),
    user=Depends(verify_jwt),
):
    """ICU nursing observation flowsheet — decoded from Hope's per-hour chart
    into category / sub_category / observation / value+unit."""
    _get_patient(patient_id)
    try:
        rows = (
            db.table(TABLE_NURSING_FLOWSHEET)
            .select("id,category_name,sub_category_name,observation_name,unit,"
                    "value_text,value_numeric,observed_date,hour_slot,actual_time")
            .eq("patient_id", patient_id)
            .order("observed_date", desc=True)
            .limit(limit)
            .execute()
            .data
            or []
        )
        return {"observations": rows, "count": len(rows)}
    except Exception as exc:
        logger.error("Flowsheet lookup failed: %s", exc)
        return {"observations": [], "count": 0}


@router.get("/patients/{patient_id}/encounters")
def list_patient_encounters(
    patient_id: int,
    limit: int = Query(100, ge=1, le=500),
    user=Depends(verify_jwt),
):
    """Every visit this patient has made, migrated ones included.

    WHY THIS EXISTS RATHER THAN REUSING /queue/encounters
    -----------------------------------------------------
    That endpoint filters external_source IS NULL, and correctly so: it drives
    the live worklist, and 269,416 migrated Hope encounters would bury today's
    patients. But it means a patient-history view built on it shows nothing for
    anyone who predates go-live -- patient 94398 has 65 visits and that endpoint
    returns 0.

    The HMO panel asks the opposite question ("what has this patient's account
    done"), so history is the point rather than the problem. Same split already
    made for radiology: a worklist and a chart want different rows.
    """
    try:
        rows = (
            db.table(TABLE_ENCOUNTERS)
            .select("id,patient_id,encounter_type,department,status,chief_complaint,"
                    "queue_number,created_at,triage_at,consultation_at,discharge_at,"
                    "consulting_doctor,payer_type,membership_id,external_source")
            .eq("patient_id", patient_id)
            .order("created_at", desc=True)
            .limit(limit).execute().data or []
        )
    except Exception as exc:
        logger.warning("Patient encounter history failed for %s: %s", patient_id, exc)
        return {"encounters": [], "count": 0, "migrated": 0, "native": 0}

    for r in rows:
        # Stated on the row rather than left to be inferred from a null column:
        # a visit from before go-live has thinner detail, and a clinician
        # should know that is why, not assume the record is incomplete.
        r["is_migrated"] = bool(r.get("external_source"))

    return {
        "encounters": rows,
        "count": len(rows),
        "migrated": sum(1 for r in rows if r["is_migrated"]),
        "native": sum(1 for r in rows if not r["is_migrated"]),
    }


@router.get("/patients/{patient_id}/notes")
def list_patient_notes(
    patient_id: int,
    note_type: Optional[str] = Query(None, description="e.g. nursing | soap | progress"),
    limit: int = Query(100, ge=1, le=500),
    user=Depends(verify_jwt),
):
    """All notes for a patient, across every encounter, newest first.

    The only note listing that existed was encounter-scoped
    (GET /queue/encounters/{id}/notes), which is right for a consultation but
    useless at the Nurse Station — a nurse looking after a patient wants that
    patient's nursing record, not one visit's slice of it. 72,774 migrated
    nursing notes across 6,379 patients were unreachable without this.

    Addenda are attached inline for the same reason as the encounter route: a
    correction must never be read apart from the text it corrects.
    """
    _get_patient(patient_id)
    try:
        query = (
            db.table(TABLE_ENCOUNTER_NOTES)
            .select("id,encounter_id,note_type,note_title,content,subjective,objective,"
                    "assessment,plan,icd10_codes,author_id,author_name,signed_by,signed_at,created_at")
            .eq("patient_id", patient_id)
        )
        if note_type:
            query = query.eq("note_type", note_type.strip().lower())
        notes = query.order("created_at", desc=True).limit(limit).execute().data or []

        if notes:
            try:
                addenda = (
                    db.table(TABLE_NOTE_ADDENDA)
                    .select("id,note_id,content,reason,author_name,created_at")
                    .in_("note_id", [n["id"] for n in notes])
                    .order("created_at")
                    .execute()
                    .data
                    or []
                )
                by_note: dict = {}
                for a in addenda:
                    by_note.setdefault(a["note_id"], []).append(a)
                for n in notes:
                    n["addenda"] = by_note.get(n["id"], [])
            except Exception as exc:
                logger.error("Addendum fetch failed for patient %s: %s", patient_id, exc)
                for n in notes:
                    n.setdefault("addenda", [])

        return {"notes": notes, "count": len(notes)}
    except Exception as exc:
        logger.error("Patient note listing failed: %s", exc)
        return {"notes": [], "count": 0}


@router.get("/notes/recent")
def list_recent_notes(
    note_type: Optional[str] = Query(None),
    limit: int = Query(25, ge=1, le=100),
    user=Depends(verify_jwt),
):
    """Recent notes across all patients — the ward's activity, not one chart's.

    Every existing note listing is scoped to a patient or an encounter, which is
    right for a chart but useless at a nursing station: a nurse coming on shift
    wants to know what has been written on the ward since they left, without
    opening twenty patients one at a time.

    Native rows only. The 72,774 migrated Hope notes would bury today's entries
    under a decade of history, the same rule the lab and radiology worklists
    already apply.
    """
    try:
        query = (
            db.table(TABLE_ENCOUNTER_NOTES)
            .select("id,patient_id,encounter_id,note_type,note_title,content,"
                    "subjective,objective,assessment,plan,author_name,"
                    "signed_by,signed_at,created_at")
            .is_("external_source", None)
        )
        if note_type:
            query = query.eq("note_type", note_type.strip().lower())
        notes = query.order("created_at", desc=True).limit(limit).execute().data or []

        # Attach patient names in one lookup rather than one per note.
        pids = list({n["patient_id"] for n in notes if n.get("patient_id")})
        if pids:
            try:
                patients = (
                    db.table(TABLE_PATIENTS)
                    .select("id,first_name,last_name,mrn")
                    .in_("id", pids)
                    .execute()
                    .data
                    or []
                )
                by_id = {p["id"]: p for p in patients}
                for n in notes:
                    p = by_id.get(n.get("patient_id"))
                    if p:
                        n["patient_name"] = f"{p.get('first_name','')} {p.get('last_name','')}".strip()
                        n["patient_mrn"] = p.get("mrn")
            except Exception as exc:
                logger.error("Patient name lookup failed for recent notes: %s", exc)

        return {"notes": notes, "count": len(notes)}
    except Exception as exc:
        logger.error("Recent note listing failed: %s", exc)
        return {"notes": [], "count": 0}


@router.get("/patients/{patient_id}/ward-stays")
def list_patient_ward_stays(patient_id: int, user=Depends(verify_jwt)):
    """Admit/discharge/transfer history. No patient-centric ward view existed
    before — royan_beds models live occupancy only, not history."""
    _get_patient(patient_id)
    try:
        rows = (
            db.table(TABLE_WARD_STAY_HISTORY)
            .select("id,ward_name,room_name,bed_label,admitted_at,discharged_at,"
                    "is_discharged,readmitted")
            .eq("patient_id", patient_id)
            .order("admitted_at", desc=True)
            .execute()
            .data
            or []
        )
        return {"stays": rows, "count": len(rows)}
    except Exception as exc:
        logger.error("Ward stay lookup failed: %s", exc)
        return {"stays": [], "count": 0}


@router.get("/patients/{patient_id}/documents")
def list_patient_documents_index(patient_id: int, user=Depends(verify_jwt)):
    """Historical document INDEX. is_migrated is false throughout: Hope's binary
    file column was not carried across, so these rows say a document exists and
    describe it, but cannot serve it. Surfacing them beats pretending the
    history is empty."""
    _get_patient(patient_id)
    try:
        rows = (
            db.table(TABLE_PATIENT_DOCUMENTS_IDX)
            .select("id,filename,mime_type,size_bytes,description,comment,"
                    "document_date,is_migrated")
            .eq("patient_id", patient_id)
            .order("document_date", desc=True)
            .execute()
            .data
            or []
        )
        return {"documents": rows, "count": len(rows)}
    except Exception as exc:
        logger.error("Patient document index lookup failed: %s", exc)
        return {"documents": [], "count": 0}


@router.get("/patients/{patient_id}/medication-administration")
def list_patient_medication_admin(patient_id: int, user=Depends(verify_jwt)):
    """Migrated MAR history.

    NOTE: distinct from GET /nursing/mar/{encounter_id}, which serves the live
    royan_mar_entries table. Both are real; this one is the Hope archive.
    nurse_data is Hope's undocumented pipe-delimited blob ('1||250||18||1||2')
    — no decode key exists anywhere in the dump, so it is passed through raw
    rather than guessed at.
    """
    _get_patient(patient_id)
    try:
        rows = (
            db.table(TABLE_MEDICATION_ADMIN)
            .select("id,performed_at,performed_by,pain_intensity,not_given,"
                    "is_signed,nurse_data")
            .eq("patient_id", patient_id)
            .order("performed_at", desc=True)
            .execute()
            .data
            or []
        )
        return {"administrations": rows, "count": len(rows)}
    except Exception as exc:
        logger.error("MAR history lookup failed: %s", exc)
        return {"administrations": [], "count": 0}


@router.get("/patients/{patient_id}/billing-history")
def list_patient_billing_history(
    patient_id: int,
    limit: int = Query(100, ge=1, le=500),
    user=Depends(verify_jwt),
):
    """Migrated billing archive — 419k transactions + 334k encounter summaries
    spanning 2016-2025, covering 93% of patients.

    This SUPPLEMENTS royan_billing (which the live billing module owns); it
    does not replace or reconcile with it. Per the user's explicit decision
    when the archive was loaded.
    """
    _get_patient(patient_id)
    try:
        txns = (
            db.table(TABLE_BILLING_TRANSACTIONS)
            .select("id,bill_number,transaction_date,payment_category,mode_of_payment,"
                    "amount,total_amount,amount_paid,amount_pending,discount_amount,remark")
            .eq("patient_id", patient_id)
            .order("transaction_date", desc=True)
            .limit(limit)
            .execute()
            .data
            or []
        )
        summaries = (
            db.table(TABLE_BILLING_SUMMARIES)
            .select("id,bill_number,bill_date,total_amount,amount_paid,amount_pending,"
                    "discount,claim_status,discharge_date")
            .eq("patient_id", patient_id)
            .order("bill_date", desc=True)
            .limit(limit)
            .execute()
            .data
            or []
        )
        # Receipts and card/cheque instruments complete the money story: the
        # transactions say what was billed, these say what was actually
        # collected and how. 50,820 receipts + 29,357 card transactions were
        # loaded in Phase A3 and had no reader until now.
        receipts = (
            db.table(TABLE_ACCOUNT_RECEIPTS)
            .select("id,receipt_number,receipt_date,amount,payment_mode,narration")
            .eq("patient_id", patient_id)
            .order("receipt_date", desc=True)
            .limit(limit)
            .execute()
            .data
            or []
        )
        cards = (
            db.table(TABLE_PATIENT_CARD_TRANSACTIONS)
            .select("id,instrument_type,amount,mode_type,bank_account_no,cheque_no,transacted_at")
            .eq("patient_id", patient_id)
            .order("transacted_at", desc=True)
            .limit(limit)
            .execute()
            .data
            or []
        )

        return {
            "transactions": txns,
            "summaries": summaries,
            "receipts": receipts,
            "card_transactions": cards,
            "count": len(txns) + len(summaries),
        }
    except Exception as exc:
        logger.error("Billing history lookup failed: %s", exc)
        return {"transactions": [], "summaries": [], "receipts": [], "card_transactions": [], "count": 0}


@router.get("/patients/{patient_id}/financial-ledger")
def list_patient_financial_ledger(
    patient_id: int,
    limit: int = Query(100, ge=1, le=500),
    user=Depends(verify_jwt),
):
    """Accounting-side records for one patient: journal entries, discount
    requests and settlement lines.

    Separate from /billing-history (which is the patient-facing bill and
    payment view) because this is the finance department's ledger, not the
    clinical chart's. 78,672 voucher entries, 2,082 discount requests and 302
    settlement lines came across in Phase A3.
    """
    _get_patient(patient_id)
    try:
        vouchers = (
            db.table(TABLE_VOUCHER_ENTRIES)
            .select("id,account_ref,entry_date,debit_amount,credit_amount,narration,entry_type")
            .eq("patient_id", patient_id)
            .order("entry_date", desc=True)
            .limit(limit)
            .execute()
            .data
            or []
        )
        discounts = (
            db.table(TABLE_DISCOUNT_REQUESTS)
            .select("id,request_type,discount_amount,discount_percentage,total_amount,"
                    "payment_category,is_approved,is_closed,requested_at")
            .eq("patient_id", patient_id)
            .order("requested_at", desc=True)
            .limit(limit)
            .execute()
            .data
            or []
        )
        settlements = (
            db.table(TABLE_SETTLEMENT_BILLINGS)
            .select("id,item_name,units,rate,amount,settled_at")
            .eq("patient_id", patient_id)
            .order("settled_at", desc=True)
            .limit(limit)
            .execute()
            .data
            or []
        )
        return {
            "voucher_entries": vouchers,
            "discount_requests": discounts,
            "settlements": settlements,
            "count": len(vouchers) + len(discounts) + len(settlements),
        }
    except Exception as exc:
        logger.error("Financial ledger lookup failed: %s", exc)
        return {"voucher_entries": [], "discount_requests": [], "settlements": [], "count": 0}


@router.get("/doctor-schedule")
def list_doctor_schedule(
    doctor_ref: Optional[str] = Query(None, description="Hope doctor id"),
    limit: int = Query(200, ge=1, le=500),
    user=Depends(verify_jwt),
):
    """Migrated doctor availability / blocked periods (749 rows, e.g. a
    recurring 17:00-18:30 'walk - in time'). Historical reference for building
    clinic timetables."""
    try:
        query = db.table(TABLE_DOCTOR_SCHEDULE_BLOCKS).select(
            "id,staff_id,doctor_ref,purpose,starts_at,ends_at,start_time,end_time,"
            "is_blocked,is_all_day,is_recurring"
        )
        if doctor_ref:
            query = query.eq("doctor_ref", str(doctor_ref).strip())
        rows = query.order("starts_at", desc=True).limit(limit).execute().data or []
        return {"blocks": rows, "count": len(rows)}
    except Exception as exc:
        logger.error("Doctor schedule lookup failed: %s", exc)
        return {"blocks": [], "count": 0}


@router.get("/hope-archive")
def search_hope_archive(
    source_table: Optional[str] = Query(None, description="Hope table name"),
    limit: int = Query(50, ge=1, le=200),
    user=Depends(verify_jwt),
):
    """Lookup into the Hope reference archive (501,227 rows / 105 source tables).

    Everything extracted from the legacy dump that had no dedicated schema is
    preserved here verbatim as jsonb. Without this endpoint the archive is a
    black box that can only be read with direct SQL — this makes it at least
    inspectable from the app when someone asks "what did Hope hold for X?".
    Listing with no source_table returns the available table names rather than
    half a million rows.
    """
    try:
        if not source_table:
            # Needs a real DISTINCT. Selecting a page and de-duplicating in
            # Python returned 2 tables out of 105 — the first 5,000 of 501,227
            # rows all belong to the same source. Raw SQL via the shared pool,
            # same pattern as services/relationship_auditor.py.
            conn = db.pool.getconn()
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        f"SELECT source_table, COUNT(*) FROM {TABLE_HOPE_REFERENCE_ARCHIVE} "
                        "GROUP BY source_table ORDER BY source_table"
                    )
                    rows = cur.fetchall()
            finally:
                db.pool.putconn(conn)
            return {
                "source_tables": [{"source_table": t, "rows": n} for t, n in rows],
                "count": len(rows),
            }

        rows = (
            db.table(TABLE_HOPE_REFERENCE_ARCHIVE)
            .select("id,source_table,source_row_id,payload")
            .eq("source_table", source_table.strip())
            .limit(limit)
            .execute()
            .data
            or []
        )
        return {"rows": rows, "count": len(rows), "source_table": source_table}
    except Exception as exc:
        logger.error("Hope archive lookup failed: %s", exc)
        return {"rows": [], "count": 0}
