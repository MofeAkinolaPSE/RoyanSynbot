"""Centralized constants for SynbotHealth.

This module provides a single source of truth for branding, table names,
embedding parameters, disclaimers, environment variable keys, and service
endpoint configuration. Import these instead of scattering literals.
"""

import os

# Branding & Bot Identity
BOT_BRAND = "Royan Hospital"
BOT_NAME = "SynbotHealth"

# Embedding / Retrieval Params
EMBEDDING_DIM = 384
DEFAULT_TOP_K = 3
MATCH_THRESHOLD = 0.78

# Disclaimers (append to every user-visible LLM answer)
# NDPA 2023 — Nigeria Data Protection Act patient data disclaimer
NDPA_DISCLAIMER = (
    "This response is for informational purposes only and does not constitute medical advice. "
    "Always consult a qualified healthcare professional for diagnosis or treatment decisions. "
    "Your data is handled in compliance with the Nigeria Data Protection Act 2023 (NDPA)."
)
# Alias kept for any legacy references during transition
NAFDAC_DISCLAIMER = NDPA_DISCLAIMER

# Supabase / Postgres Tables — royan_ prefix for all hospital-domain tables
TABLE_LEADS = "royan_leads"
TABLE_USERS = "royan_users"
TABLE_REFRESH_TOKENS = "royan_refresh_tokens"
TABLE_ORDERS = "royan_orders"
TABLE_STOCK_CACHE = "royan_stock_cache"
TABLE_INVENTORY_EVENTS = "royan_inventory_events"
TABLE_STAFF = "royan_staff"
TABLE_TIMESHEETS = "royan_timesheets"
TABLE_ALERTS = "royan_alerts"
TABLE_BRIEFINGS = "royan_executive_briefings"
TABLE_TRACKING = "royan_tracking"
TABLE_AUDIT_LOGS = "royan_audit_logs"
TABLE_IMPORT_JOBS = "royan_import_jobs"
TABLE_IMPORT_REJECTIONS = "royan_import_rejections"
TABLE_KPI_PROMOTIONS = "royan_kpi_promotions"
TABLE_DATA_POLICIES = "royan_data_policies"
TABLE_QNA = "qna"  # existing vector table (unchanged)
TABLE_CHAT_HISTORY = "royan_chat_history"
TABLE_CHATS = "royan_chats"
TABLE_PROJECTS = "royan_projects"
TABLE_SCOPE_ITEMS = "royan_scope_items"
TABLE_COST_ITEMS = "royan_cost_items"
TABLE_RISK_REGISTER = "royan_risk_register"
TABLE_CHANGE_REQUESTS = "royan_change_requests"
TABLE_PROCUREMENT_SHIPMENTS = "royan_procurement_shipments"
TABLE_PROCUREMENT_SHIPMENT_EVENTS = "royan_procurement_shipment_events"
TABLE_WEBHOOK_IDEMPOTENCY = "royan_webhook_idempotency"

# --- Hospital clinical tables (Phase 3) ---
TABLE_PATIENTS              = "royan_patients"
TABLE_ENCOUNTERS            = "royan_encounters"
TABLE_WARDS                 = "royan_wards"
TABLE_BEDS                  = "royan_beds"
TABLE_LAB_ORDERS            = "royan_lab_orders"
TABLE_LAB_RESULTS           = "royan_lab_results"
TABLE_PRESCRIPTIONS         = "royan_prescriptions"
TABLE_DISPENSING            = "royan_dispensing"
TABLE_BILLING               = "royan_billing"
TABLE_PAYMENTS              = "royan_payments"
TABLE_INSURANCE_CLAIMS      = "royan_insurance_claims"
TABLE_APPOINTMENT_SLOTS     = "royan_appointment_slots"
TABLE_APPOINTMENTS          = "royan_appointments"
TABLE_HMOS                  = "royan_hmos"
TABLE_HMO_PLANS             = "royan_hmo_plans"
TABLE_PATIENT_INSURANCE     = "royan_patient_insurance"
TABLE_SERVICE_CATALOG       = "royan_service_catalog"
TABLE_COVERAGE_RULES        = "royan_coverage_rules"
TABLE_COVERAGE_AUTHORIZATIONS = "royan_coverage_authorizations"
TABLE_BILL_ITEMS            = "royan_bill_items"
TABLE_HOPE_SYNC_RUNS        = "royan_hope_sync_runs"
TABLE_ENCOUNTER_NOTES       = "royan_encounter_notes"

# --- Hospital Phase 1 additions ---
TABLE_CONSENT_RECORDS       = "royan_consent_records"
TABLE_ICD10_CODES           = "royan_icd10_codes"
TABLE_PROBLEM_LIST          = "royan_problem_list"
TABLE_FEE_SCHEDULE          = "royan_fee_schedule"
TABLE_INPATIENT_BILL_LINES  = "royan_inpatient_bill_lines"

# --- Hospital Phase 2 additions ---
TABLE_LAB_REFERENCE_RANGES  = "royan_lab_reference_ranges"
TABLE_DRUG_INVENTORY        = "royan_drug_inventory"
TABLE_DRUG_INTERACTIONS     = "royan_drug_interactions"
TABLE_ALLERGIES             = "royan_allergies"
TABLE_REPLENISHMENT_REQUESTS = "royan_replenishment_requests"
TABLE_VITALS                = "royan_vitals"
TABLE_NURSING_CARE_PLANS    = "royan_nursing_care_plans"
TABLE_FLUID_BALANCE         = "royan_fluid_balance"
TABLE_MAR_ENTRIES           = "royan_mar_entries"

MAR_STATUS_ALLOWED          = {"scheduled", "administered", "held", "missed", "refused"}

# --- Hospital Phase 3 — Radiology ---
TABLE_RADIOLOGY_ORDERS      = "royan_radiology_orders"

# --- Hospital Phase 4 — Surgical Theatre ---
TABLE_THEATRE_CASES         = "royan_theatre_cases"

# --- Hospital Phase 5 — MCH / OB-GYN ---
TABLE_ANC_RECORDS           = "royan_anc_records"
TABLE_ANC_VISITS            = "royan_anc_visits"
TABLE_PARTOGRAPH            = "royan_partograph"
TABLE_DELIVERY_RECORDS      = "royan_delivery_records"
TABLE_NEWBORN_ASSESSMENT    = "royan_newborn_assessment"
TABLE_IMMUNISATION          = "royan_immunisation"

# Radiology workflow constants
RADIOLOGY_MODALITIES_ALLOWED = {"xray", "ultrasound", "ct", "mri", "ecg", "echo", "fluoroscopy", "mammography", "endoscopy", "other"}
RADIOLOGY_STATUS_ALLOWED     = {"ordered", "scheduled", "in_progress", "reported", "cancelled"}
RADIOLOGY_STATUS_TRANSITIONS = {
    "ordered":     {"scheduled", "in_progress", "cancelled"},
    "scheduled":   {"in_progress", "cancelled"},
    "in_progress": {"reported", "cancelled"},
    "reported":    set(),
    "cancelled":   set(),
}

# Theatre workflow constants
THEATRE_STATUS_ALLOWED = {"scheduled", "pre_op", "in_theatre", "recovery", "completed", "cancelled"}
THEATRE_STATUS_TRANSITIONS = {
    "scheduled":   {"pre_op", "cancelled"},
    "pre_op":      {"in_theatre", "cancelled"},
    "in_theatre":  {"recovery"},
    "recovery":    {"completed"},
    "completed":   set(),
    "cancelled":   set(),
}
THEATRE_URGENCY_ALLOWED = {"elective", "urgent", "emergency"}

# --- Hospital Phase 6 — SMS / Digital Engagement ---
TABLE_NOTIFICATION_LOGS      = "royan_notification_logs"
TABLE_SMS_TEMPLATES          = "royan_sms_templates"
TABLE_TELEMEDICINE_SESSIONS  = "royan_telemedicine_sessions"

NOTIFICATION_CHANNELS_ALLOWED = {"sms", "whatsapp", "email"}
NOTIFICATION_STATUS_ALLOWED   = {"queued", "sent", "delivered", "failed"}
TELEMEDICINE_STATUS_ALLOWED   = {"scheduled", "active", "completed", "cancelled", "no_show"}

# --- Hospital Phase 7 — Quality / Safety + HR ---
TABLE_INCIDENT_REPORTS       = "royan_incident_reports"
TABLE_INFECTION_CONTROL      = "royan_infection_control"
TABLE_HEFAMAA_CHECKLIST      = "royan_hefamaa_checklist"
TABLE_STAFF_SHIFTS           = "royan_staff_shifts"
TABLE_LEAVE_REQUESTS         = "royan_leave_requests"
TABLE_PAYROLL_RECORDS        = "royan_payroll_records"

INCIDENT_SEVERITY_ALLOWED    = {"near_miss", "minor", "moderate", "major", "sentinel"}
INCIDENT_STATUS_ALLOWED      = {"reported", "under_review", "investigated", "closed", "escalated"}
INCIDENT_CATEGORY_ALLOWED    = {
    "medication_error", "patient_fall", "pressure_injury", "surgical_complication",
    "equipment_failure", "infection", "documentation_error", "delay_in_treatment",
    "violence_aggression", "other"
}
SHIFT_TYPE_ALLOWED           = {"morning", "afternoon", "night", "on_call", "split"}
LEAVE_TYPE_ALLOWED           = {"annual", "sick", "maternity", "paternity", "compassionate", "study", "unpaid"}
LEAVE_STATUS_ALLOWED         = {"pending", "approved", "rejected", "cancelled"}

# --- Hospital Phase 8 — Reporting / Integrations / Payments ---
TABLE_PAYMENT_TRANSACTIONS   = "royan_payment_transactions"
TABLE_PACS_STUDIES           = "royan_pacs_studies"
TABLE_KIOSK_CHECKINS         = "royan_kiosk_checkins"

PAYMENT_GATEWAY_ALLOWED      = {"paystack", "flutterwave"}
PAYMENT_TXN_STATUS_ALLOWED   = {"initiated", "pending", "success", "failed", "reversed"}
PACS_STATUS_ALLOWED          = {"pending", "sent", "available", "error"}

# --- Hospital Phase 9 — Specialist Clinic Templates ---
TABLE_CLINIC_TEMPLATES       = "royan_clinic_templates"
TABLE_SPECIALIST_NOTES       = "royan_specialist_notes"

SPECIALTY_ALLOWED = {
    "cardiology", "ent", "ophthalmology", "dermatology", "orthopaedics",
    "neurology", "gastroenterology", "urology", "pulmonology", "endocrinology",
    "psychiatry", "paediatrics", "oncology", "dentistry", "general",
}


# Clinical patient journey workflow stages
HOSPITAL_DEPARTMENTS = {
    "A&E",
    "OPD",
    "Inpatient Ward",
    "Laboratory & Diagnostics",
    "Pharmacy",
    "Billing & Finance",
    "Administration",
    "Maintenance & Facilities",
    "Maternity",
    "Surgery",
}
ENCOUNTER_TYPES = {"outpatient", "inpatient", "emergency", "maternity", "surgical"}
TRIAGE_LEVELS = {"immediate", "urgent", "less_urgent", "non_urgent"}
ENCOUNTER_STATUS_ALLOWED = {
    "patient_registered",
    "triaged",
    "nurse_assessment",
    "called",
    "consulting",
    "lab_ordered",
    "pharmacy_dispensing",
    "billing_pending",
    "discharged",
}
ENCOUNTER_STATUS_TRANSITIONS = {
    "patient_registered": {"triaged", "nurse_assessment"},
    "triaged":            {"nurse_assessment", "consulting", "patient_registered"},
    "nurse_assessment":   {"called", "consulting"},
    "called":             {"consulting"},
    "consulting":         {"lab_ordered", "pharmacy_dispensing", "billing_pending"},
    "lab_ordered":        {"consulting", "pharmacy_dispensing", "billing_pending"},
    "pharmacy_dispensing": {"billing_pending"},
    "billing_pending":    {"discharged", "consulting"},
    "discharged":         set(),
}
APPOINTMENT_STATUS_ALLOWED = {"booked", "confirmed", "arrived", "completed", "no_show", "cancelled", "rescheduled"}
LAB_ORDER_STATUS_ALLOWED = {"ordered", "sample_collected", "processing", "resulted", "sent_out", "cancelled"}
LAB_URGENCY_ALLOWED = {"routine", "urgent", "stat"}
LAB_INTERPRETATION_ALLOWED = {"normal", "abnormal", "critical", "inconclusive"}
PRESCRIPTION_STATUS_ALLOWED = {"pending", "dispensed", "partially_dispensed", "cancelled", "returned"}
PRESCRIPTION_ROUTES_ALLOWED = {"oral", "iv", "im", "topical", "inhaled", "sublingual", "rectal", "other"}
BILL_STATUS_ALLOWED = {"pending", "partial", "paid", "waived", "disputed", "written_off"}
CLAIM_STATUS_ALLOWED = {"submitted", "pre_authorised", "approved", "rejected", "paid", "disputed"}
PAYMENT_METHODS_ALLOWED = {"cash", "card", "transfer", "hmo", "waiver"}
COVERAGE_TYPES_ALLOWED = {"percent", "fixed", "none", "capitation"}
LIMIT_TYPES_ALLOWED = {"none", "per_visit", "per_month"}

# Backward-compatible aliases used by the first hospital router pass.
PROJECT_STATUS_ALLOWED = {"active", "on_hold", "completed", "cancelled"}
PROJECT_WORKFLOW_STAGES = ENCOUNTER_STATUS_ALLOWED
PROJECT_QC_STATUS_ALLOWED = {"pending", "in_review", "passed", "failed", "waived"}
PROJECT_QC_APPROVED_STATUSES = {"passed", "waived"}
PROJECT_QC_GATED_STAGES = {"consulting", "discharged"}

PROJECT_STAGE_TRANSITIONS = ENCOUNTER_STATUS_TRANSITIONS
SCOPE_STATUS_ALLOWED = {"planned", "in_progress", "done", "deferred", "cancelled"}
COST_STATUS_ALLOWED = {"planned", "approved", "committed", "actual", "cancelled"}
RISK_STATUS_ALLOWED = {"open", "monitoring", "mitigating", "accepted", "closed"}
CHANGE_STATUS_ALLOWED = {"proposed", "under_review", "approved", "rejected", "implemented"}

# --- Order status workflow ---
ORDER_STATUS_ALLOWED = {"received", "packed", "dispatched", "delivered", "cancelled"}
ORDER_STATUS_TRANSITIONS = {
    "received": {"packed", "cancelled"},
    "packed": {"dispatched", "cancelled"},
    "dispatched": {"delivered", "cancelled"},
    "delivered": set(),
    "cancelled": set(),
}

CHANGE_STATUS_TRANSITIONS = {
    "proposed": {"under_review", "rejected"},
    "under_review": {"approved", "rejected"},
    "approved": {"implemented"},
    "rejected": {"under_review"},
    "implemented": set(),
}

SCOPE_STATUS_TRANSITIONS = {
    "planned": {"in_progress", "deferred", "cancelled"},
    "in_progress": {"done", "deferred", "cancelled"},
    "deferred": {"planned", "in_progress", "cancelled"},
    "done": set(),
    "cancelled": set(),
}

COST_STATUS_TRANSITIONS = {
    "planned": {"approved", "cancelled"},
    "approved": {"committed", "cancelled"},
    "committed": {"actual", "cancelled"},
    "actual": set(),
    "cancelled": set(),
}

RISK_STATUS_TRANSITIONS = {
    "open": {"monitoring", "mitigating", "accepted", "closed"},
    "monitoring": {"mitigating", "accepted", "closed"},
    "mitigating": {"monitoring", "accepted", "closed"},
    "accepted": {"monitoring", "closed"},
    "closed": {"monitoring"},
}

HIGH_IMPACT_SCOPE_LEVELS = {"major", "critical"}
HIGH_IMPACT_COST_THRESHOLD = 1_000_000.0
HIGH_IMPACT_SCHEDULE_DAYS_THRESHOLD = 14
HIGH_IMPACT_APPROVAL_REASONS = {
    "regulatory",
    "budget_override",
    "timeline_exception",
    "scope_expansion",
    "risk_acceptance",
    "executive_override",
}

RISK_SCORE_MITIGATION_THRESHOLD = 15
RISK_SCORE_OWNER_THRESHOLD = 20

# Environment Variable Keys
ENV_SUPABASE_URL = "SUPABASE_URL"
ENV_SUPABASE_KEY = "SUPABASE_KEY"
ENV_EMAIL_FROM = "EMAIL_FROM"
ENV_EMAIL_PASS = "EMAIL_PASS"
ENV_LLM_PROVIDER = "LLM_PROVIDER"  # which brain implementation to use: "deepseek" or "service"
ENV_LLM_SERVICE_URL = "LLM_SERVICE_URL"  # microservice endpoint for LLM completions
ENV_LLM_API_KEY = "LLM_API_KEY"  # optional auth for microservice
ENV_LLM_SPACE_URL = "LLM_SPACE_URL"  # optional: HF Space for generation (alternative to microservice)
ENV_LLM_SPACE_API_NAME = "LLM_SPACE_API_NAME"  # e.g. /predict or /predict_js
ENV_LLM_SPACE_API_KEY = "LLM_SPACE_API_KEY"  # optional bearer for private Space

# DeepSeek-specific env (current default brain)
ENV_DEEPSEEK_API_KEY = "DEEPSEEK_API_KEY"
ENV_DEEPSEEK_MODEL = "DEEPSEEK_MODEL"

ENV_SAGE_MOCK = "SAGE_MOCK"  # if set truthy -> use mock adapter
ENV_JWT_SECRET = "JWT_SECRET"  # for signing/verifying admin/user tokens
ENV_RATE_LIMIT = "RATE_LIMIT"  # requests per minute per key/ip (default 60)
ENV_DEV_TOKEN_ENABLED = "DEV_TOKEN_ENABLED"  # allow issuing dev tokens via API
ENV_CORS_ALLOW_ORIGINS = "CORS_ALLOW_ORIGINS"  # comma-separated list of origins
ENV_AT_REST_KEY = "AT_REST_KEY"  # base64-encoded 32-byte key for AES-256-GCM at-rest encryption
ENV_JWT_AUDIENCE = "JWT_AUDIENCE"  # optional audience claim to validate
ENV_AUTH0_DOMAIN = "AUTH0_DOMAIN"  # Auth0 tenant domain (e.g., your-tenant.eu.auth0.com)
ENV_AUTH0_AUDIENCE = "AUTH0_AUDIENCE"  # Auth0 API audience identifier
ENV_WIDGET_SITE_KEYS = "WIDGET_SITE_KEYS"  # comma-separated public site keys allowed for anonymous widget chat
ENV_ACCESS_TOKEN_MINUTES = "ACCESS_TOKEN_MINUTES"
ENV_REFRESH_TOKEN_DAYS = "REFRESH_TOKEN_DAYS"
ENV_WEBSOCKET_ENABLED = "WEBSOCKET_ENABLED"
ENV_PROCUREMENT_CLEARANCE_DELAY_DAYS = "PROCUREMENT_CLEARANCE_DELAY_DAYS"
ENV_PROCUREMENT_DAILY_DELAY_COST = "PROCUREMENT_DAILY_DELAY_COST"

# Optional future integrations
ENV_SAGE_API_KEY = "SAGE_API_KEY"
ENV_HF_API_URL = "HF_API_URL"
ENV_HF_API_KEY = "HF_API_KEY"

# ---------------------------------------------------------------------------
# QMS / Compliance Table Names
# ---------------------------------------------------------------------------
TABLE_SOP_REGISTRY          = "sop_registry"
TABLE_AUDIT_SCHEDULE        = "audit_schedule"
TABLE_COMPLIANCE_ACTIVITY   = "compliance_activity_log"
TABLE_EQUIPMENT_REGISTRY    = "equipment_registry"
TABLE_MAINTENANCE_SCHEDULE  = "maintenance_schedule"
TABLE_DEVIATION_REPORTS     = "deviation_reports"
TABLE_RECALL_CASES          = "recall_cases"
TABLE_DOCUMENT_ARCHIVE      = "document_archive"

# Reliability / Maintenance Agent tables
TABLE_MAINTENANCE_ASSETS         = "royan_maintenance_assets"
TABLE_MAINTENANCE_TASKS          = "royan_maintenance_tasks"
TABLE_INCIDENT_LOG               = "royan_incident_log"
TABLE_REMEDIATION_ACTIONS        = "royan_remediation_actions"
TABLE_FAILURE_PATTERN_LIBRARY    = "royan_failure_pattern_library"

# Digital Twin tables (migration 075)
TABLE_TWIN_NODES                 = "royan_twin_nodes"
TABLE_TWIN_STATE_HISTORY         = "royan_twin_state_history"
TABLE_TWIN_ANOMALY_EVENTS        = "royan_twin_anomaly_events"
TABLE_TWIN_DEPENDENCY_EDGES      = "royan_twin_dependency_edges"

# Capability Discovery tables (migration 076)
TABLE_CAPABILITY_SIGNALS         = "royan_capability_signals"
TABLE_CAPABILITY_PROPOSALS       = "royan_capability_proposals"
TABLE_CAPABILITY_STATUS_HISTORY  = "royan_capability_status_history"

# Reliability rollout mode: when True, all auto-fix playbooks are skipped and
# the agent only observes/records without mutating state.
RELIABILITY_OBSERVE_ONLY: bool = os.getenv("RELIABILITY_OBSERVE_ONLY", "false").lower() == "true"

# ── Knowledge Engine tables (migration 073) ──────────────────────────────────
TABLE_INGESTED_DOCUMENTS    = "ingested_documents"
TABLE_KNOWLEDGE_CHUNKS      = "knowledge_chunks"
TABLE_KNOWLEDGE_GAPS        = "knowledge_gaps"
TABLE_SYNBOT_MEMORY         = "synbot_memory"

# Deviation report ID prefix sequence helper (format: DEV-YYYY-NNN)
DEVIATION_ID_PREFIX = "DEV"
RECALL_ID_PREFIX    = "RECALL"

# Document storage backend (local | supabase | s3)
DOCUMENT_STORAGE_BACKEND  = os.getenv("DOCUMENT_STORAGE_BACKEND", "local")
DOCUMENT_STORAGE_BUCKET   = os.getenv("DOCUMENT_STORAGE_BUCKET", "compliance-documents")
DOCUMENT_LOCAL_PATH       = os.path.join(os.path.dirname(__file__), "..", "static", "documents")

# QMS / Compliance role permission sets
COMPLIANCE_ALL_ROLES  = {"admin", "quality_assurance", "qa", "management", "operations", "ops", "staff"}
COMPLIANCE_QA_ROLES   = {"admin", "quality_assurance", "qa"}
COMPLIANCE_MGMT_ROLES = {"admin", "management"}
COMPLIANCE_OPS_ROLES  = {"admin", "quality_assurance", "qa", "operations", "ops", "management"}

# Deviation & Recall status workflows
DEVIATION_STATUS_ALLOWED      = {"open", "under_investigation", "closed", "escalated"}
RECALL_STATUS_ALLOWED         = {"initiated", "in_progress", "completed", "closed"}
AUDIT_STATUS_ALLOWED          = {"scheduled", "in_progress", "completed", "overdue", "skipped"}
ACTIVITY_STATUS_ALLOWED       = {"scheduled", "completed", "missed", "overdue", "deferred"}
MAINTENANCE_STATUS_ALLOWED    = {"scheduled", "completed", "overdue", "cancelled"}

# SOP categories
SOP_CATEGORY_LABELS = {
    "storage":       "Storage & Handling",
    "qc":            "Quality Control & Regulatory",
    "distribution":  "Distribution",
    "warehouse":     "Warehouse Operations",
    "equipment":     "Equipment & Calibration",
    "deviation":     "Deviation & CAPA",
    "recall":        "Recall Management",
    "hr":            "HR & Training",
}

# Webhook shared secret (HMAC) for provider callbacks
ENV_WEBHOOK_SECRET = "WEBHOOK_SECRET"

# --- Financial Data Pipeline Config ---
# GL account code that holds the cash/bank balance (used by kpis() to derive cash position).
# Change this to match the account code in the customer's Sage chart of accounts.
CASH_GL_ACCOUNT_CODE: str = os.getenv("CASH_GL_ACCOUNT_CODE", "1000")

# Revenue accounts: any GL account_code cast to int in this range is treated as revenue (credit side).
REVENUE_GL_ACCOUNT_MIN: int = 4000
REVENUE_GL_ACCOUNT_MAX: int = 4999

# Cost/expense accounts: debit-side rows in this range feed total_cost.
COST_GL_ACCOUNT_MIN: int = 5000
COST_GL_ACCOUNT_MAX: int = 6999

# How many hours before a missing/unchanged Sage import triggers stale_pipeline_alert on /health.
PIPELINE_STALE_HOURS: int = int(os.getenv("PIPELINE_STALE_HOURS", "48"))

# ---------------------------------------------------------------------------
# Hope Bridge (DRM Hope integration layer)
# ---------------------------------------------------------------------------
ENV_HOPE_BRIDGE_URL            = "HOPE_BRIDGE_URL"
ENV_HOPE_BRIDGE_KEY            = "HOPE_BRIDGE_KEY"
ENV_HOPE_BRIDGE_WEBHOOK_SECRET = "HOPE_BRIDGE_WEBHOOK_SECRET"
ENV_HOPE_MOCK                  = "HOPE_MOCK"

HOPE_BRIDGE_DEFAULT_PORT    = 7070      # Windows service listening port
HOPE_BRIDGE_TIMEOUT_SECONDS = 10        # HTTP timeout for all bridge calls
HOPE_BRIDGE_URL             = os.getenv(ENV_HOPE_BRIDGE_URL, f"http://localhost:{HOPE_BRIDGE_DEFAULT_PORT}")
HOPE_BRIDGE_KEY             = os.getenv(ENV_HOPE_BRIDGE_KEY, "")
HOPE_MOCK                   = os.getenv(ENV_HOPE_MOCK, "1") not in ("0", "false", "False")

# ---------------------------------------------------------------------------
# SynHealth auth roles
# ---------------------------------------------------------------------------
ROLES: list[str] = [
    "admin",
    "doctor",
    "nurse",
    "pharmacist",
    "receptionist",
    "lab_tech",
    "radiographer",
    "physiotherapist",
    "finance",
]

JWT_ALGORITHM               = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv(ENV_ACCESS_TOKEN_MINUTES if "ENV_ACCESS_TOKEN_MINUTES" in dir() else "ACCESS_TOKEN_MINUTES", "15"))
REFRESH_TOKEN_EXPIRE_DAYS   = int(os.getenv(ENV_REFRESH_TOKEN_DAYS if "ENV_REFRESH_TOKEN_DAYS" in dir() else "REFRESH_TOKEN_DAYS", "30"))

# ---------------------------------------------------------------------------
# Questionnaire intake table (added for SynHealth onboarding flow)
# ---------------------------------------------------------------------------
TABLE_QUESTIONNAIRE     = "synhealth_questionnaire_responses"
TABLE_SCHEMA_MIGRATIONS = "schema_migrations"

# Medical disclaimer — append to every user-visible LLM answer
MEDICAL_DISCLAIMER = NDPA_DISCLAIMER


# --- Executive Summary Thresholds ---
# AR overdue count above this threshold triggers a key_finding. Set to 0 so any overdue invoice fires.
EXEC_SUMMARY_AR_OVERDUE_THRESHOLD: int = int(os.getenv("EXEC_SUMMARY_AR_OVERDUE_THRESHOLD", "0"))

# Defaults / Derived
LLM_PROVIDER = os.getenv(ENV_LLM_PROVIDER, "deepseek").lower()
LLM_SERVICE_URL = os.getenv(ENV_LLM_SERVICE_URL, "")
LLM_API_KEY = os.getenv(ENV_LLM_API_KEY, "")
LLM_SPACE_URL = os.getenv(ENV_LLM_SPACE_URL, "")
LLM_SPACE_API_NAME = os.getenv(ENV_LLM_SPACE_API_NAME, "/predict")
LLM_SPACE_API_KEY = os.getenv(ENV_LLM_SPACE_API_KEY, "")
DEEPSEEK_API_KEY = os.getenv(ENV_DEEPSEEK_API_KEY, "")
SAGE_MOCK = os.getenv(ENV_SAGE_MOCK, "1") not in ("0", "false", "False")
JWT_SECRET = os.getenv(ENV_JWT_SECRET, "")
if not JWT_SECRET or len(JWT_SECRET) < 32:
    raise RuntimeError(
        "JWT_SECRET env var must be set and at least 32 characters. "
        "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
    )

# Webhook secret used to verify provider callbacks (HMAC-SHA256)
WEBHOOK_SECRET = os.getenv(ENV_WEBHOOK_SECRET, "")
RATE_LIMIT = int(os.getenv(ENV_RATE_LIMIT, "60"))
DEV_TOKEN_ENABLED = os.getenv(ENV_DEV_TOKEN_ENABLED, "1") not in ("0", "false", "False")
CORS_ALLOW_ORIGINS = [o.strip() for o in os.getenv(ENV_CORS_ALLOW_ORIGINS, "*").split(",") if o.strip()] or ["*"]
AT_REST_KEY = os.getenv(ENV_AT_REST_KEY, "")
JWT_AUDIENCE = os.getenv(ENV_JWT_AUDIENCE, "")
AUTH0_DOMAIN = os.getenv(ENV_AUTH0_DOMAIN, "")
AUTH0_AUDIENCE = os.getenv(ENV_AUTH0_AUDIENCE, "")
WIDGET_SITE_KEYS = [k.strip() for k in os.getenv(ENV_WIDGET_SITE_KEYS, "").split(",") if k.strip()]
AUTH0_ISSUER = f"https://{AUTH0_DOMAIN}/" if AUTH0_DOMAIN else ""
ACCESS_TOKEN_MINUTES = int(os.getenv(ENV_ACCESS_TOKEN_MINUTES, "45"))
REFRESH_TOKEN_DAYS = int(os.getenv(ENV_REFRESH_TOKEN_DAYS, "7"))
WEBSOCKET_ENABLED = os.getenv(ENV_WEBSOCKET_ENABLED, "1") not in ("0", "false", "False")
PROCUREMENT_CLEARANCE_DELAY_DAYS = int(os.getenv(ENV_PROCUREMENT_CLEARANCE_DELAY_DAYS, "5"))
PROCUREMENT_DAILY_DELAY_COST = float(os.getenv(ENV_PROCUREMENT_DAILY_DELAY_COST, "250000"))

def append_disclaimer(text: str) -> str:
    """Ensure the NDPA 2023 disclaimer is appended exactly once."""
    if not text:
        return NDPA_DISCLAIMER
    norm = text.strip()
    if NDPA_DISCLAIMER.lower() in norm.lower():
        return norm
    return f"{norm}\n\n{NDPA_DISCLAIMER}"
