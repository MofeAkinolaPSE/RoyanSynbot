"""Patient Context Engine — the aggregation heart of the Synbot Data
Intelligence Layer (SDIL).

Builds one complete, cached, longitudinal patient object — demographics,
insurance, encounters, vitals, clinical notes, labs, radiology, prescriptions,
billing, payments, claims, discharge — so the frontend, Roy (the AI
assistant), and reports consume a single verified patient-centric view
instead of piecing together dozens of per-table queries.

Extracted from routers/patient_registration.py's _load_patient_profile
(which covered encounters/labs/prescriptions/bills only) and extended with
the remaining clinical sections. The router's GET /patients/{mrn}/profile
is now a thin wrapper over build_patient_context().

Cached per patient via ttl_cache's callable-tags support: any write path for
a patient can call invalidate_patient_context(patient_id) to evict just that
patient's snapshot.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from ..db import db
from ..cache import ttl_cache, invalidate_cache_tags

logger = logging.getLogger("patient_context")

_SECTION_LIMIT = 50

# Column lists per section — keep these explicit (not SELECT *) so the payload
# stays bounded and stable for frontend/AI consumers.
_ENC_COLS   = "id,patient_id,status,department,encounter_type,created_at,discharge_at,triage_level,consulting_doctor,ward_id,chief_complaint,notes,external_source,external_id"
_LAB_COLS   = "id,patient_id,encounter_id,test_name,status,ordered_at,urgency,sample_type,notes,ordered_by,external_source,external_id"
_RX_COLS    = "id,patient_id,encounter_id,drug_name,dosage,frequency,duration,route,quantity,unit,special_instructions,status,prescribed_at,dispensed_at,prescribed_by,external_source,external_id"
_BILL_COLS  = "id,patient_id,encounter_id,bill_number,subtotal,patient_balance,status,billed_at,payment_method,notes,external_source,external_id"
_RAD_COLS   = "id,patient_id,encounter_id,test_name,modality,body_part,status,urgency,ordered_at,reported_at,impression,external_source,external_id"
_VITAL_COLS = "id,patient_id,encounter_id,temperature,pulse,respiratory_rate,bp_systolic,bp_diastolic,spo2,weight,height,bmi,gcs,pain_score,blood_glucose,notes,recorded_by,recorded_at"
_NOTE_COLS  = ("id,encounter_id,patient_id,note_type,note_title,content,"
               "subjective,objective,assessment,plan,icd10_codes,vitals_id,"
               "author_id,author_name,signed_by,signed_at,created_at,updated_at")
_DISCH_COLS = "id,encounter_id,patient_id,discharge_condition,discharge_diagnosis,discharge_summary,follow_up_date,discharged_by,discharged_at"
_INS_COLS   = "id,patient_id,hmo_id,plan_id,membership_id,status,valid_from,valid_to,is_primary"
_AUTH_COLS  = "id,patient_id,encounter_id,status,requested_amount,approved_amount,authorization_code,requested_at,decided_at"
_PAY_COLS   = "id,billing_id,patient_id,amount,payment_method,reference,received_by,received_at"
_CLAIM_COLS = "id,billing_id,patient_id,hmo_provider,claim_amount,status,submitted_at,approved_amount,settled_at"
_POSTING_COLS = "id,patient_id,posting_type,message,severity,created_by,created_at,resolved_at,resolved_by"
_IMMUNISATION_COLS = "id,patient_id,vaccine_name,dose_number,date_given,batch_number,site,administered_by,next_due_date,reaction,notes"

_NOTES_SECTION_LIMIT = 300  # notes need real full-history headroom, not the default 50

# (table, columns, order_by column, timeline event type or None, limit override or None)
_SECTIONS: List[tuple] = [
    ("encounters",       "royan_encounters",              _ENC_COLS,   "created_at",   "encounter",       None),
    ("lab_orders",       "royan_lab_orders",              _LAB_COLS,   "ordered_at",   "lab_order",       None),
    ("prescriptions",    "royan_prescriptions",           _RX_COLS,    "prescribed_at","prescription",    None),
    ("bills",            "royan_billing",                 _BILL_COLS,  "billed_at",    "bill",            None),
    ("radiology",        "royan_radiology_orders",        _RAD_COLS,   "ordered_at",   "radiology_order", None),
    ("vitals",           "royan_vitals",                  _VITAL_COLS, "recorded_at",  "vitals",          None),
    ("clinical_notes",   "royan_encounter_notes",         _NOTE_COLS,  "created_at",   "clinical_note",   _NOTES_SECTION_LIMIT),
    ("discharges",       "royan_discharge_records",       _DISCH_COLS, "discharged_at","discharge",       None),
    ("insurance",        "royan_patient_insurance",       _INS_COLS,   "created_at",   None,              None),
    ("coverage_authorizations", "royan_coverage_authorizations", _AUTH_COLS, "requested_at", None,        None),
    ("payments",         "royan_payments",                _PAY_COLS,   "received_at",  "payment",         None),
    ("insurance_claims", "royan_insurance_claims",        _CLAIM_COLS, "submitted_at", "insurance_claim", None),
    ("postings",         "royan_patient_postings",        _POSTING_COLS, "created_at", None,              None),
    ("immunisations",    "royan_immunisation",            _IMMUNISATION_COLS, "date_given", None,         None),
]

# timeline timestamp field per section (matches the order_by column)
_TIMELINE_TS = {
    "encounter": "created_at", "lab_order": "ordered_at", "prescription": "prescribed_at",
    "bill": "billed_at", "radiology_order": "ordered_at", "vitals": "recorded_at",
    "clinical_note": "created_at", "discharge": "discharged_at",
    "payment": "received_at", "insurance_claim": "submitted_at",
}


def _patient_tags(patient_id: int, *args: Any, **kwargs: Any) -> List[str]:
    return [f"patient:{patient_id}", "patient_context"]


@ttl_cache(ttl_seconds=300, tags=_patient_tags)
def build_patient_context(patient_id: int) -> Dict[str, Any]:
    """Assemble the complete clinical record for one patient.

    Every section degrades gracefully to an empty list if its table is
    missing or the query fails — one broken module must never take down the
    whole patient view.
    """
    sections: Dict[str, List[Dict[str, Any]]] = {}
    timeline: List[Dict[str, Any]] = []

    for key, table, cols, order_col, timeline_type, limit_override in _SECTIONS:
        try:
            rows = (
                db.table(table)
                .select(cols)
                .eq("patient_id", patient_id)
                .order(order_col, desc=True)
                .limit(limit_override or _SECTION_LIMIT)
                .execute()
            ).data or []
        except Exception as exc:
            logger.warning("patient_context: %s query failed for patient %s: %s", table, patient_id, exc)
            rows = []

        if key == "encounters":
            # Exclude synbot_repair ancillary buckets — synthetic rows the
            # 2026-07 encounter-key-collision repair created purely to hold
            # orphaned lab/pharmacy/billing links, not real clinical visits.
            # Must never be counted as a "visit" by any consumer of this
            # context (Roy, reports, the Appointments/Visits cover-sheet
            # card) — same exclusion already applied to the live queue and
            # CPRS active-encounter lookup elsewhere in this codebase.
            rows = [r for r in rows if r.get("external_source") != "synbot_repair"]

        sections[key] = rows

        if timeline_type:
            ts_field = _TIMELINE_TS[timeline_type]
            for row in rows:
                timeline.append({
                    "type": timeline_type,
                    "timestamp": row.get(ts_field),
                    "record": row,
                })

    # clinical_notes.signed_by is a raw royan_staff.id — batch-resolve to a
    # display name once here rather than making every consumer (frontend,
    # Roy, reports) do its own staff lookup. Same batch-enrichment idiom as
    # every other _enrich_with_staff this session (HR/Quality/Specialist/
    # Facility passes), just inlined since this file has no per-router
    # helper module of its own.
    try:
        signer_ids = list({r["signed_by"] for r in sections.get("clinical_notes", []) if r.get("signed_by")})
        if signer_ids:
            signers = db.table("royan_staff").select("id,full_name").in_("id", signer_ids).execute().data or []
            signer_names = {s["id"]: s["full_name"] for s in signers}
            for note_row in sections["clinical_notes"]:
                if note_row.get("signed_by"):
                    note_row["signed_by_name"] = signer_names.get(note_row["signed_by"])
    except Exception as exc:
        logger.warning("patient_context: signed_by enrichment failed for patient %s: %s", patient_id, exc)

    # royan_lab_orders carries no result value at all — real results live in a
    # separate royan_lab_results table (already keyed by patient_id, no join
    # needed). Splice them onto the matching lab_orders row by lab_order_id so
    # existing consumers of sections["lab_orders"] (the Labs tab, the Cover
    # Sheet's Recent Lab Results card) see result_summary/reference_range/
    # interpretation without any further wiring.
    try:
        result_rows = (
            db.table("royan_lab_results")
            .select("lab_order_id,result_summary,reference_range,interpretation,resulted_at,resulted_by,verified_by,verified_at,is_critical,notes")
            .eq("patient_id", patient_id)
            .execute()
        ).data or []
        by_order_id = {r["lab_order_id"]: r for r in result_rows if r.get("lab_order_id") is not None}
        for order_row in sections.get("lab_orders", []):
            result = by_order_id.get(order_row.get("id"))
            if result:
                order_row["result_summary"] = result.get("result_summary")
                order_row["reference_range"] = result.get("reference_range")
                order_row["interpretation"] = result.get("interpretation")
                order_row["resulted_at"] = result.get("resulted_at")
                order_row["resulted_by"] = result.get("resulted_by")
                order_row["verified_by"] = result.get("verified_by")
                order_row["verified_at"] = result.get("verified_at")
                order_row["is_critical"] = result.get("is_critical")
                order_row["result_notes"] = result.get("notes")
    except Exception as exc:
        logger.warning("patient_context: lab_results merge failed for patient %s: %s", patient_id, exc)

    # royan_dispensing carries no encounter_id, only prescription_id — splice
    # each prescription's dispensing history onto it (as a list; a partial
    # dispense can leave more than one row per prescription) so the Meds tab
    # can show batch/dispensed-by/cost detail instead of just the order.
    try:
        rx_ids = [r["id"] for r in sections.get("prescriptions", []) if r.get("id") is not None]
        disp_rows: List[Dict[str, Any]] = []
        if rx_ids:
            disp_rows = (
                db.table("royan_dispensing")
                .select("id,prescription_id,quantity_dispensed,unit,batch_number,expiry_date,dispensed_by,dispensed_at,unit_cost,total_cost,counselling_given,notes")
                .in_("prescription_id", rx_ids)
                .execute()
            ).data or []
        disp_by_rx: Dict[Any, List[Dict[str, Any]]] = {}
        for d in disp_rows:
            disp_by_rx.setdefault(d.get("prescription_id"), []).append(d)
        for rx_row in sections.get("prescriptions", []):
            rx_row["dispensing"] = disp_by_rx.get(rx_row.get("id"), [])
    except Exception as exc:
        logger.warning("patient_context: dispensing merge failed for patient %s: %s", patient_id, exc)

    # Appointments: real table, but needs the slot-info join _enrich() already
    # does in routers/appointments.py — reuse it rather than re-deriving the
    # join or its ui_status mapping. (Cross-module import of a `_`-prefixed
    # helper is deliberate reuse here, not an accident.)
    try:
        from ..routers.appointments import _enrich as _enrich_appointments
        appt_rows = (
            db.table("royan_appointments")
            .select("*")
            .eq("patient_id", patient_id)
            .order("booked_at", desc=True)
            .limit(_SECTION_LIMIT)
            .execute()
        ).data or []
        sections["appointments"] = _enrich_appointments(appt_rows)
    except Exception as exc:
        logger.warning("patient_context: appointments query failed for patient %s: %s", patient_id, exc)
        sections["appointments"] = []

    timeline.sort(key=lambda item: str(item.get("timestamp") or ""), reverse=True)

    return {
        "patient_id": patient_id,
        **sections,
        "timeline": timeline,
        "section_counts": {k: len(v) for k, v in sections.items()},
    }


def invalidate_patient_context(patient_id: int) -> None:
    """Evict one patient's cached context — call after any write for them."""
    invalidate_cache_tags(f"patient:{patient_id}")
