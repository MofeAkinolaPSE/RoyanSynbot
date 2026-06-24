"""
Specialist Clinic Templates Router — SynbotHealth / Royan Hospital
====================================================================
14-specialty structured note templates with order sets.
VistA reference: TIU (Text Integration Utilities) document definitions.

Endpoints:
  POST   /specialist/templates                        – Create or seed a template
  GET    /specialist/templates                        – List templates (filter by specialty)
  GET    /specialist/templates/{id}                   – Template detail (full JSONB fields schema)
  PATCH  /specialist/templates/{id}                   – Update template
  DELETE /specialist/templates/{id}                   – Soft-delete (active=False)

  POST   /specialist/notes                            – Submit a completed specialist note
  GET    /specialist/notes                            – List notes (filter: patient, encounter, specialty)
  GET    /specialist/notes/{id}                       – Note detail
  PATCH  /specialist/notes/{id}                       – Amend note

  POST   /specialist/seed                             – Seed all 14 built-in templates (idempotent)
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.db import db, audit_event
from src.middleware import verify_jwt
from src.constants import (
    TABLE_CLINIC_TEMPLATES,
    TABLE_SPECIALIST_NOTES,
    SPECIALTY_ALLOWED,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/specialist", tags=["Specialist Clinics"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Built-in specialty templates
# ---------------------------------------------------------------------------

BUILTIN_TEMPLATES: list[dict] = [
    {
        "specialty": "cardiology",
        "template_name": "Cardiology Consultation",
        "fields": [
            {"key": "presenting_complaint",   "label": "Presenting Complaint",      "type": "textarea"},
            {"key": "chest_pain",             "label": "Chest Pain",                "type": "boolean"},
            {"key": "dyspnoea",               "label": "Dyspnoea on Exertion",      "type": "boolean"},
            {"key": "palpitations",           "label": "Palpitations",              "type": "boolean"},
            {"key": "syncope",                "label": "Syncope / Pre-syncope",     "type": "boolean"},
            {"key": "cardiac_history",        "label": "Cardiac History",           "type": "textarea"},
            {"key": "medications",            "label": "Current Medications",       "type": "textarea"},
            {"key": "bp_mmhg",                "label": "BP (mmHg)",                 "type": "text"},
            {"key": "hr_bpm",                 "label": "HR (bpm)",                  "type": "number"},
            {"key": "ecg_findings",           "label": "ECG Findings",              "type": "textarea"},
            {"key": "echo_findings",          "label": "Echo Findings",             "type": "textarea"},
            {"key": "troponin",               "label": "Troponin Result",           "type": "text"},
            {"key": "assessment",             "label": "Assessment / Diagnosis",    "type": "textarea"},
            {"key": "plan",                   "label": "Management Plan",           "type": "textarea"},
            {"key": "follow_up_weeks",        "label": "Follow-up (weeks)",         "type": "number"},
        ],
        "default_order_sets": ["ECG", "Echo", "FBC", "Troponin", "Lipids", "HbA1c"],
    },
    {
        "specialty": "ent",
        "template_name": "ENT Consultation",
        "fields": [
            {"key": "presenting_complaint",   "label": "Presenting Complaint",      "type": "textarea"},
            {"key": "hearing_loss",           "label": "Hearing Loss",              "type": "boolean"},
            {"key": "tinnitus",               "label": "Tinnitus",                  "type": "boolean"},
            {"key": "vertigo",                "label": "Vertigo",                   "type": "boolean"},
            {"key": "nasal_obstruction",      "label": "Nasal Obstruction",         "type": "boolean"},
            {"key": "epistaxis",              "label": "Epistaxis",                 "type": "boolean"},
            {"key": "dysphagia",              "label": "Dysphagia",                 "type": "boolean"},
            {"key": "audiogram_result",       "label": "Audiogram Result",          "type": "textarea"},
            {"key": "tympanogram",            "label": "Tympanogram Findings",      "type": "textarea"},
            {"key": "rhinoscopy_findings",    "label": "Rhinoscopy Findings",       "type": "textarea"},
            {"key": "throat_exam",            "label": "Throat / Larynx Exam",      "type": "textarea"},
            {"key": "assessment",             "label": "Assessment",                "type": "textarea"},
            {"key": "plan",                   "label": "Plan",                      "type": "textarea"},
        ],
        "default_order_sets": ["Audiogram", "Tympanometry", "PNS X-ray"],
    },
    {
        "specialty": "ophthalmology",
        "template_name": "Ophthalmology Consultation",
        "fields": [
            {"key": "presenting_complaint",   "label": "Presenting Complaint",      "type": "textarea"},
            {"key": "va_right",               "label": "Visual Acuity (Right)",     "type": "text"},
            {"key": "va_left",                "label": "Visual Acuity (Left)",      "type": "text"},
            {"key": "iop_right",              "label": "IOP Right (mmHg)",          "type": "number"},
            {"key": "iop_left",               "label": "IOP Left (mmHg)",           "type": "number"},
            {"key": "fundoscopy",             "label": "Fundoscopy Findings",       "type": "textarea"},
            {"key": "slit_lamp",              "label": "Slit Lamp Findings",        "type": "textarea"},
            {"key": "refraction",             "label": "Refraction",                "type": "textarea"},
            {"key": "assessment",             "label": "Assessment",                "type": "textarea"},
            {"key": "plan",                   "label": "Plan",                      "type": "textarea"},
            {"key": "glasses_prescription",   "label": "Glasses Prescription",      "type": "textarea"},
        ],
        "default_order_sets": ["Fundoscopy", "IOP", "Visual Field", "OCT"],
    },
    {
        "specialty": "dermatology",
        "template_name": "Dermatology Consultation",
        "fields": [
            {"key": "presenting_complaint",   "label": "Presenting Complaint",      "type": "textarea"},
            {"key": "lesion_description",     "label": "Lesion Description",        "type": "textarea"},
            {"key": "distribution",           "label": "Distribution",              "type": "text"},
            {"key": "duration_weeks",         "label": "Duration (weeks)",          "type": "number"},
            {"key": "pruritus",               "label": "Pruritus",                  "type": "boolean"},
            {"key": "scorad_score",           "label": "SCORAD Score (if AD)",      "type": "number"},
            {"key": "allergies",              "label": "Known Allergies",           "type": "textarea"},
            {"key": "biopsy_result",          "label": "Biopsy Result",             "type": "textarea"},
            {"key": "assessment",             "label": "Assessment",                "type": "textarea"},
            {"key": "topical_treatment",      "label": "Topical Treatment",         "type": "textarea"},
            {"key": "systemic_treatment",     "label": "Systemic Treatment",        "type": "textarea"},
            {"key": "plan",                   "label": "Plan",                      "type": "textarea"},
        ],
        "default_order_sets": ["Skin Biopsy", "KOH Prep", "Patch Test", "IgE"],
    },
    {
        "specialty": "orthopaedics",
        "template_name": "Orthopaedic Consultation",
        "fields": [
            {"key": "presenting_complaint",   "label": "Presenting Complaint",      "type": "textarea"},
            {"key": "site_of_injury",         "label": "Site of Injury",            "type": "text"},
            {"key": "mechanism",              "label": "Mechanism of Injury",       "type": "textarea"},
            {"key": "pain_score",             "label": "Pain Score (0-10)",         "type": "number"},
            {"key": "rom_findings",           "label": "Range of Motion",           "type": "textarea"},
            {"key": "neurovascular_status",   "label": "Neurovascular Status",      "type": "textarea"},
            {"key": "xray_findings",          "label": "X-Ray Findings",            "type": "textarea"},
            {"key": "mri_findings",           "label": "MRI Findings",              "type": "textarea"},
            {"key": "assessment",             "label": "Assessment / Fracture Type","type": "textarea"},
            {"key": "management",             "label": "Management",                "type": "textarea"},
            {"key": "surgical_plan",          "label": "Surgical Plan",             "type": "textarea"},
            {"key": "physio_referral",        "label": "Physiotherapy Referral",    "type": "boolean"},
        ],
        "default_order_sets": ["X-ray", "MRI", "FBC", "Group & Screen"],
    },
    {
        "specialty": "neurology",
        "template_name": "Neurology Consultation",
        "fields": [
            {"key": "presenting_complaint",   "label": "Presenting Complaint",      "type": "textarea"},
            {"key": "gcs",                    "label": "GCS Score",                 "type": "number"},
            {"key": "headache",               "label": "Headache",                  "type": "boolean"},
            {"key": "seizure",                "label": "Seizure History",           "type": "boolean"},
            {"key": "weakness",               "label": "Weakness / Paralysis",      "type": "boolean"},
            {"key": "cranial_nerves",         "label": "Cranial Nerve Exam",        "type": "textarea"},
            {"key": "motor_power",            "label": "Motor Power (MRC Grade)",   "type": "textarea"},
            {"key": "sensory_exam",           "label": "Sensory Examination",       "type": "textarea"},
            {"key": "reflexes",               "label": "Reflexes",                  "type": "textarea"},
            {"key": "cerebellar_signs",       "label": "Cerebellar Signs",          "type": "textarea"},
            {"key": "ct_brain_findings",      "label": "CT Brain Findings",         "type": "textarea"},
            {"key": "mri_findings",           "label": "MRI Findings",              "type": "textarea"},
            {"key": "eeg_findings",           "label": "EEG Findings",              "type": "textarea"},
            {"key": "assessment",             "label": "Assessment",                "type": "textarea"},
            {"key": "plan",                   "label": "Plan",                      "type": "textarea"},
        ],
        "default_order_sets": ["CT Brain", "MRI Brain", "EEG", "LP", "FBC", "E/U/Cr"],
    },
    {
        "specialty": "gastroenterology",
        "template_name": "Gastroenterology Consultation",
        "fields": [
            {"key": "presenting_complaint",   "label": "Presenting Complaint",      "type": "textarea"},
            {"key": "dysphagia",              "label": "Dysphagia",                 "type": "boolean"},
            {"key": "heartburn",              "label": "Heartburn / GORD",          "type": "boolean"},
            {"key": "abdominal_pain",         "label": "Abdominal Pain",            "type": "boolean"},
            {"key": "rectal_bleeding",        "label": "Rectal Bleeding",           "type": "boolean"},
            {"key": "weight_loss",            "label": "Weight Loss",               "type": "boolean"},
            {"key": "jaundice",               "label": "Jaundice",                  "type": "boolean"},
            {"key": "endoscopy_findings",     "label": "Endoscopy Findings",        "type": "textarea"},
            {"key": "lft",                    "label": "LFT Interpretation",        "type": "textarea"},
            {"key": "h_pylori",               "label": "H. Pylori Status",          "type": "text"},
            {"key": "biopsy_result",          "label": "Biopsy Result",             "type": "textarea"},
            {"key": "assessment",             "label": "Assessment",                "type": "textarea"},
            {"key": "plan",                   "label": "Plan",                      "type": "textarea"},
        ],
        "default_order_sets": ["Endoscopy", "LFT", "H.Pylori", "USS Abdomen", "FBC"],
    },
    {
        "specialty": "urology",
        "template_name": "Urology Consultation",
        "fields": [
            {"key": "presenting_complaint",   "label": "Presenting Complaint",      "type": "textarea"},
            {"key": "luts",                   "label": "LUTS (storage/voiding)",    "type": "textarea"},
            {"key": "haematuria",             "label": "Haematuria",                "type": "boolean"},
            {"key": "ipss_score",             "label": "IPSS Score",                "type": "number"},
            {"key": "dre_findings",           "label": "DRE Findings",              "type": "textarea"},
            {"key": "psa",                    "label": "PSA (ng/mL)",               "type": "number"},
            {"key": "uss_findings",           "label": "USS KUB Findings",          "type": "textarea"},
            {"key": "urodynamics",            "label": "Urodynamics Results",       "type": "textarea"},
            {"key": "msu_result",             "label": "MSU C&S Result",            "type": "textarea"},
            {"key": "assessment",             "label": "Assessment",                "type": "textarea"},
            {"key": "plan",                   "label": "Plan",                      "type": "textarea"},
        ],
        "default_order_sets": ["PSA", "USS KUB", "MSU C&S", "FBC", "E/U/Cr"],
    },
    {
        "specialty": "pulmonology",
        "template_name": "Pulmonology Consultation",
        "fields": [
            {"key": "presenting_complaint",   "label": "Presenting Complaint",      "type": "textarea"},
            {"key": "dyspnoea_grade",         "label": "MRC Dyspnoea Grade (1-5)",  "type": "number"},
            {"key": "cough",                  "label": "Cough",                     "type": "boolean"},
            {"key": "haemoptysis",            "label": "Haemoptysis",               "type": "boolean"},
            {"key": "wheeze",                 "label": "Wheeze",                    "type": "boolean"},
            {"key": "smoking_pack_years",     "label": "Smoking Pack-Years",        "type": "number"},
            {"key": "spo2_percent",           "label": "SpO2 (%)",                  "type": "number"},
            {"key": "spirometry_fev1",        "label": "FEV1 (L)",                  "type": "number"},
            {"key": "spirometry_fvc",         "label": "FVC (L)",                   "type": "number"},
            {"key": "peak_flow",              "label": "Peak Flow (L/min)",         "type": "number"},
            {"key": "cxr_findings",           "label": "CXR Findings",              "type": "textarea"},
            {"key": "sputum_mc_s",            "label": "Sputum MC&S",               "type": "textarea"},
            {"key": "assessment",             "label": "Assessment",                "type": "textarea"},
            {"key": "plan",                   "label": "Plan",                      "type": "textarea"},
        ],
        "default_order_sets": ["CXR", "Spirometry", "Peak Flow", "Sputum MC&S", "ABG", "FBC"],
    },
    {
        "specialty": "endocrinology",
        "template_name": "Endocrinology Consultation",
        "fields": [
            {"key": "presenting_complaint",   "label": "Presenting Complaint",      "type": "textarea"},
            {"key": "diabetes_type",          "label": "Diabetes Type",             "type": "select", "options": ["Type 1", "Type 2", "MODY", "Gestational", "None"]},
            {"key": "hba1c",                  "label": "HbA1c (%)",                 "type": "number"},
            {"key": "fasting_glucose",        "label": "Fasting Glucose (mmol/L)",  "type": "number"},
            {"key": "thyroid_status",         "label": "Thyroid Status",            "type": "select", "options": ["Euthyroid", "Hypothyroid", "Hyperthyroid", "Unknown"]},
            {"key": "tsh",                    "label": "TSH (mIU/L)",               "type": "number"},
            {"key": "ft4",                    "label": "Free T4",                   "type": "number"},
            {"key": "weight_kg",              "label": "Weight (kg)",               "type": "number"},
            {"key": "bmi",                    "label": "BMI",                       "type": "number"},
            {"key": "current_medications",    "label": "Current Medications",       "type": "textarea"},
            {"key": "complications",          "label": "Diabetic Complications",    "type": "textarea"},
            {"key": "assessment",             "label": "Assessment",                "type": "textarea"},
            {"key": "plan",                   "label": "Plan",                      "type": "textarea"},
        ],
        "default_order_sets": ["HbA1c", "FPG", "TSH", "Free T4", "Lipids", "Renal function"],
    },
    {
        "specialty": "psychiatry",
        "template_name": "Psychiatry Assessment",
        "fields": [
            {"key": "presenting_complaint",   "label": "Presenting Complaint",      "type": "textarea"},
            {"key": "mse_appearance",         "label": "MSE — Appearance",          "type": "textarea"},
            {"key": "mse_speech",             "label": "MSE — Speech",              "type": "textarea"},
            {"key": "mse_mood",               "label": "MSE — Mood",                "type": "textarea"},
            {"key": "mse_thought",            "label": "MSE — Thought",             "type": "textarea"},
            {"key": "mse_perception",         "label": "MSE — Perception",          "type": "textarea"},
            {"key": "mse_cognition",          "label": "MSE — Cognition",           "type": "textarea"},
            {"key": "mse_insight",            "label": "MSE — Insight",             "type": "textarea"},
            {"key": "phq9_score",             "label": "PHQ-9 Score",               "type": "number"},
            {"key": "gad7_score",             "label": "GAD-7 Score",               "type": "number"},
            {"key": "risk_assessment",        "label": "Risk Assessment",           "type": "textarea"},
            {"key": "psychiatric_history",    "label": "Psychiatric History",       "type": "textarea"},
            {"key": "family_history",         "label": "Family Psychiatric History","type": "textarea"},
            {"key": "assessment",             "label": "Provisional Diagnosis",     "type": "textarea"},
            {"key": "plan",                   "label": "Management Plan",           "type": "textarea"},
        ],
        "default_order_sets": ["PHQ-9", "GAD-7", "MSE", "FBC", "TFT"],
    },
    {
        "specialty": "paediatrics",
        "template_name": "Paediatric Consultation",
        "fields": [
            {"key": "presenting_complaint",   "label": "Presenting Complaint",      "type": "textarea"},
            {"key": "age_months",             "label": "Age (months)",              "type": "number"},
            {"key": "weight_kg",              "label": "Weight (kg)",               "type": "number"},
            {"key": "height_cm",              "label": "Height (cm)",               "type": "number"},
            {"key": "waz_score",              "label": "WAZ Score (WHO)",           "type": "number"},
            {"key": "haz_score",              "label": "HAZ Score (WHO)",           "type": "number"},
            {"key": "muac_cm",                "label": "MUAC (cm)",                 "type": "number"},
            {"key": "developmental_milestone","label": "Developmental Milestones",  "type": "textarea"},
            {"key": "immunisation_status",    "label": "Immunisation Status",       "type": "textarea"},
            {"key": "birth_history",          "label": "Birth History",             "type": "textarea"},
            {"key": "fever",                  "label": "Fever",                     "type": "boolean"},
            {"key": "respiratory_distress",   "label": "Respiratory Distress",      "type": "boolean"},
            {"key": "assessment",             "label": "Assessment",                "type": "textarea"},
            {"key": "plan",                   "label": "Plan",                      "type": "textarea"},
        ],
        "default_order_sets": ["FBC", "Malaria RDT", "Urinalysis", "CXR", "Blood C&S"],
    },
    {
        "specialty": "oncology",
        "template_name": "Oncology Consultation",
        "fields": [
            {"key": "presenting_complaint",   "label": "Presenting Complaint",      "type": "textarea"},
            {"key": "tumour_type",            "label": "Tumour Type",               "type": "text"},
            {"key": "staging",                "label": "Staging (TNM)",             "type": "text"},
            {"key": "ecog_score",             "label": "ECOG Performance Score",   "type": "number"},
            {"key": "biopsy_result",          "label": "Biopsy / Histology",        "type": "textarea"},
            {"key": "tumour_markers",         "label": "Tumour Markers",            "type": "textarea"},
            {"key": "imaging_summary",        "label": "Imaging Summary",           "type": "textarea"},
            {"key": "previous_treatment",     "label": "Previous Treatment",        "type": "textarea"},
            {"key": "chemo_protocol",         "label": "Chemotherapy Protocol",     "type": "textarea"},
            {"key": "radiotherapy_plan",      "label": "Radiotherapy Plan",         "type": "textarea"},
            {"key": "assessment",             "label": "Assessment",                "type": "textarea"},
            {"key": "plan",                   "label": "Plan",                      "type": "textarea"},
            {"key": "palliative_care",        "label": "Palliative Care Needs",     "type": "boolean"},
        ],
        "default_order_sets": ["Histology", "CT Chest/Abdomen/Pelvis", "FBC", "LFT", "Tumour markers"],
    },
    {
        "specialty": "dentistry",
        "template_name": "Dental Consultation",
        "fields": [
            {"key": "presenting_complaint",   "label": "Presenting Complaint",      "type": "textarea"},
            {"key": "dental_chart",           "label": "Dental Chart Notes",        "type": "textarea"},
            {"key": "caries_present",         "label": "Caries Present",            "type": "boolean"},
            {"key": "caries_teeth",           "label": "Carious Teeth (FDI)",       "type": "text"},
            {"key": "periodontal_bpe",        "label": "BPE Periodontal Score",     "type": "text"},
            {"key": "gingival_bleeding",      "label": "Gingival Bleeding",         "type": "boolean"},
            {"key": "mobility",               "label": "Tooth Mobility",            "type": "boolean"},
            {"key": "periapical_xray",        "label": "Periapical X-ray Findings", "type": "textarea"},
            {"key": "oral_hygiene",           "label": "Oral Hygiene Status",       "type": "select", "options": ["Good", "Fair", "Poor"]},
            {"key": "assessment",             "label": "Assessment",                "type": "textarea"},
            {"key": "treatment_plan",         "label": "Treatment Plan",            "type": "textarea"},
            {"key": "follow_up_weeks",        "label": "Review (weeks)",            "type": "number"},
        ],
        "default_order_sets": ["OPG X-ray", "Periapical X-ray", "Vitality Test"],
    },
]


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class TemplateCreate(BaseModel):
    specialty:         str
    template_name:     str = Field(..., min_length=3)
    fields:            List[Dict[str, Any]] = Field(default_factory=list)
    default_order_sets: List[str]           = Field(default_factory=list)

    model_config = {"extra": "ignore"}


class TemplateUpdate(BaseModel):
    template_name:      Optional[str]           = None
    fields:             Optional[List[Dict[str, Any]]] = None
    default_order_sets: Optional[List[str]]     = None
    active:             Optional[bool]          = None

    model_config = {"extra": "ignore"}


class SpecialistNote(BaseModel):
    patient_id:    int
    encounter_id:  Optional[int]  = None
    template_id:   Optional[int]  = None
    specialty:     str
    note_data:     Dict[str, Any] = Field(default_factory=dict)
    icd10_codes:   Optional[List[str]] = None
    assessment:    Optional[str]  = None
    plan:          Optional[str]  = None
    noted_by:      Optional[str]  = None

    model_config = {"extra": "ignore"}


class NoteAmend(BaseModel):
    note_data:   Optional[Dict[str, Any]] = None
    icd10_codes: Optional[List[str]]      = None
    assessment:  Optional[str]            = None
    plan:        Optional[str]            = None

    model_config = {"extra": "ignore"}


# ---------------------------------------------------------------------------
# Template Endpoints
# ---------------------------------------------------------------------------

@router.post("/templates", status_code=201)
async def create_template(payload: TemplateCreate, user=Depends(verify_jwt)):
    if payload.specialty not in SPECIALTY_ALLOWED:
        raise HTTPException(status_code=422, detail=f"specialty must be one of {sorted(SPECIALTY_ALLOWED)}")
    data = payload.model_dump()
    data["active"]     = True
    data["created_by"] = user.get("sub") or "system"
    data["created_at"] = _now()
    try:
        result = db.table(TABLE_CLINIC_TEMPLATES).insert(data).execute()
    except Exception as exc:
        logger.error("Template create failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to create template")
    record = result.data[0] if result.data else data
    audit_event("clinic_template_created", {"specialty": payload.specialty},
                actor_id=user.get("sub"), subject_type="clinic_template", subject_id=str(record.get("id", "")))
    return {"ok": True, "template": record}


@router.get("/templates")
async def list_templates(
    specialty: Optional[str] = Query(None),
    active_only: bool        = Query(True),
    user=Depends(verify_jwt),
):
    q = db.table(TABLE_CLINIC_TEMPLATES).select(
        "id,specialty,template_name,default_order_sets,active,created_at"
    ).order("specialty")
    if specialty:    q = q.eq("specialty", specialty)
    if active_only:  q = q.eq("active", True)
    result = q.execute()
    return {"templates": result.data or [], "count": len(result.data or [])}


@router.get("/templates/{template_id}")
async def get_template(template_id: int, user=Depends(verify_jwt)):
    r = db.table(TABLE_CLINIC_TEMPLATES).select("*").eq("id", template_id).execute()
    if not r.data:
        raise HTTPException(status_code=404, detail="Template not found")
    return {"template": r.data[0]}


@router.patch("/templates/{template_id}")
async def update_template(template_id: int, payload: TemplateUpdate, user=Depends(verify_jwt)):
    updates = payload.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=422, detail="No fields to update")
    updates["updated_at"] = _now()
    db.table(TABLE_CLINIC_TEMPLATES).update(updates).eq("id", template_id).execute()
    audit_event("clinic_template_updated", {}, actor_id=user.get("sub"),
                subject_type="clinic_template", subject_id=str(template_id))
    return {"ok": True, "template_id": template_id}


@router.delete("/templates/{template_id}")
async def delete_template(template_id: int, user=Depends(verify_jwt)):
    db.table(TABLE_CLINIC_TEMPLATES).update({"active": False}).eq("id", template_id).execute()
    return {"ok": True, "template_id": template_id}


# ---------------------------------------------------------------------------
# Specialist Notes Endpoints
# ---------------------------------------------------------------------------

@router.post("/notes", status_code=201)
async def submit_note(payload: SpecialistNote, user=Depends(verify_jwt)):
    if payload.specialty not in SPECIALTY_ALLOWED:
        raise HTTPException(status_code=422, detail=f"specialty must be one of {sorted(SPECIALTY_ALLOWED)}")
    data = payload.model_dump(exclude_none=True)
    data["noted_by"]  = payload.noted_by or user.get("sub") or "system"
    data["noted_at"]  = _now()
    try:
        result = db.table(TABLE_SPECIALIST_NOTES).insert(data).execute()
    except Exception as exc:
        logger.error("Specialist note submit failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to save specialist note")
    record = result.data[0] if result.data else data
    audit_event("specialist_note_submitted", {"specialty": payload.specialty},
                actor_id=user.get("sub"), subject_type="specialist_note",
                subject_id=str(record.get("id", "")))
    return {"ok": True, "note": record}


@router.get("/notes")
async def list_notes(
    patient_id:   Optional[int] = Query(None),
    encounter_id: Optional[int] = Query(None),
    specialty:    Optional[str] = Query(None),
    limit:        int           = Query(50, ge=1, le=200),
    user=Depends(verify_jwt),
):
    q = db.table(TABLE_SPECIALIST_NOTES).select(
        "id,patient_id,encounter_id,specialty,assessment,plan,noted_by,noted_at,icd10_codes"
    ).order("noted_at", desc=True).limit(limit)
    if patient_id:   q = q.eq("patient_id",   patient_id)
    if encounter_id: q = q.eq("encounter_id", encounter_id)
    if specialty:    q = q.eq("specialty",    specialty)
    result = q.execute()
    return {"notes": result.data or [], "count": len(result.data or [])}


@router.get("/notes/{note_id}")
async def get_note(note_id: int, user=Depends(verify_jwt)):
    r = db.table(TABLE_SPECIALIST_NOTES).select("*").eq("id", note_id).execute()
    if not r.data:
        raise HTTPException(status_code=404, detail="Note not found")
    return {"note": r.data[0]}


@router.patch("/notes/{note_id}")
async def amend_note(note_id: int, payload: NoteAmend, user=Depends(verify_jwt)):
    updates = payload.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=422, detail="No fields to update")
    updates["amended_at"] = _now()
    updates["amended_by"] = user.get("sub") or "system"
    db.table(TABLE_SPECIALIST_NOTES).update(updates).eq("id", note_id).execute()
    audit_event("specialist_note_amended", {}, actor_id=user.get("sub"),
                subject_type="specialist_note", subject_id=str(note_id))
    return {"ok": True, "note_id": note_id}


# ---------------------------------------------------------------------------
# Seed Endpoint
# ---------------------------------------------------------------------------

@router.post("/seed", status_code=201)
async def seed_templates(user=Depends(verify_jwt)):
    """
    Idempotent: inserts the 14 built-in specialty templates.
    Skips any specialty that already has an active template.
    """
    existing = db.table(TABLE_CLINIC_TEMPLATES).select("specialty").eq("active", True).execute()
    existing_specs = {r["specialty"] for r in (existing.data or [])}

    inserted = []
    skipped  = []

    for tmpl in BUILTIN_TEMPLATES:
        if tmpl["specialty"] in existing_specs:
            skipped.append(tmpl["specialty"])
            continue
        record = {
            **tmpl,
            "active":     True,
            "created_by": user.get("sub") or "seed",
            "created_at": _now(),
        }
        try:
            db.table(TABLE_CLINIC_TEMPLATES).insert(record).execute()
            inserted.append(tmpl["specialty"])
        except Exception as exc:
            logger.error("Seed failed for %s: %s", tmpl["specialty"], exc)

    return {
        "ok":      True,
        "inserted": inserted,
        "skipped":  skipped,
        "total_templates": len(BUILTIN_TEMPLATES),
    }
