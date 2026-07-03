-- Migration 136: Enterprise Schema Namespacing
-- Implements Blueprint Chapter 14 — formal PostgreSQL schema organization.
-- Creates the named schemas that will house all NEW canonical, workflow,
-- knowledge, integration, and analytics objects going forward.
-- IMPORTANT: Existing public.royan_* tables are NOT moved — they already
-- function as the Silver operational layer and moving them would break
-- all existing code. New tables created after this migration live in the
-- appropriate schema.
-- Safe to re-run: all CREATE SCHEMA use IF NOT EXISTS.

ROLLBACK;
BEGIN;

-- ─────────────────────────────────────────────────────────────────────────────
-- Enterprise schema hierarchy (Blueprint Ch 14.5)
-- ─────────────────────────────────────────────────────────────────────────────

-- Master Data Engine schema
-- Owner: Synbot Master Data Engine (SMEF)
-- Contains: authoritative reference catalogs — departments, staff, lab, drugs,
--           diagnoses, procedures, insurance, tariffs
CREATE SCHEMA IF NOT EXISTS master;
COMMENT ON SCHEMA master IS
    'MDM layer — authoritative reference catalogs. Only SMEF writes here.';

-- Registry schema (canonical clinical entities)
-- Owner: Synbot Domain Framework (SDF)
-- Contains: canonical patients, encounters, lab orders, prescriptions, invoices
CREATE SCHEMA IF NOT EXISTS registry;
COMMENT ON SCHEMA registry IS
    'Canonical clinical registry — single source of truth for patient & encounter records.';

-- Clinical schema (encounter-level clinical detail)
-- Owner: SDF
-- Contains: diagnoses, observations, allergies, medications, care plans, SOAP notes
CREATE SCHEMA IF NOT EXISTS clinical;
COMMENT ON SCHEMA clinical IS
    'Clinical detail layer — encounter-bound observations, diagnoses, notes.';

-- Workflow schema
-- Owner: Synbot Workflow Framework (SWF)
-- Contains: workflow instances, events, tasks, assignments, transitions
CREATE SCHEMA IF NOT EXISTS workflow;
COMMENT ON SCHEMA workflow IS
    'Workflow orchestration — state machines, transitions, audit trail. Only SWF writes here.';

-- Knowledge schema (Enterprise Knowledge Engine)
-- Owner: Enterprise Knowledge Engine (EKE)
-- Contains: patient timelines, summaries, risk profiles, medication histories,
--           department summaries, encounter contexts, executive insights
CREATE SCHEMA IF NOT EXISTS knowledge;
COMMENT ON SCHEMA knowledge IS
    'Knowledge layer — assembled longitudinal views. Only EKE writes here.';

-- Finance schema
-- Owner: SDF
-- Contains: invoices, payments, claims, allocations, discounts, adjustments
CREATE SCHEMA IF NOT EXISTS finance;
COMMENT ON SCHEMA finance IS
    'Financial operations — revenue cycle, payments, insurance claims.';

-- Integration schema (Synbot Integration Framework)
-- Owner: SIF
-- Contains: integration batches, source records, connector configs,
--           migration exceptions, lineage records
CREATE SCHEMA IF NOT EXISTS integration;
COMMENT ON SCHEMA integration IS
    'SIF layer — connector configs, migration batches, source lineage. Only SIF writes here.';

-- Audit schema
-- Owner: Synbot Observability Framework (SOF)
-- Contains: audit events, security events, AI recommendations, config changes, access logs
CREATE SCHEMA IF NOT EXISTS audit;
COMMENT ON SCHEMA audit IS
    'Immutable audit trail — all enterprise operations, AI decisions, access events.';

-- Analytics schema
-- Owner: SOF
-- Contains: materialized views, KPI aggregates, operational metrics, executive dashboards
CREATE SCHEMA IF NOT EXISTS analytics;
COMMENT ON SCHEMA analytics IS
    'Gold layer — denormalized, read-optimized analytical views and KPI aggregates.';

-- Configuration schema
-- Owner: Platform
-- Contains: feature flags, org settings, workflow definitions, AI config,
--           notification templates
CREATE SCHEMA IF NOT EXISTS configuration;
COMMENT ON SCHEMA configuration IS
    'Platform configuration — feature flags, workflow definitions, AI settings.';

-- Security schema
-- Owner: Platform
-- Contains: users, roles, permissions, sessions, MFA, API keys
-- Note: core auth tables already exist in public (royan_users, royan_refresh_tokens)
--       This schema houses any new IAM objects beyond the existing auth tables.
CREATE SCHEMA IF NOT EXISTS security;
COMMENT ON SCHEMA security IS
    'IAM layer — roles, permissions, sessions, API keys. Beyond existing public auth tables.';


-- ─────────────────────────────────────────────────────────────────────────────
-- Workflow schema — core tables (Chapter 10 / 8 of implementation guide)
-- These are NEW tables that belong in the workflow schema (not in public)
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS workflow.instances (
    id              BIGSERIAL       PRIMARY KEY,
    -- What this workflow is about
    entity_type     TEXT            NOT NULL
                                    CHECK (entity_type IN (
                                        'encounter', 'lab_order', 'prescription',
                                        'invoice', 'admission', 'appointment'
                                    )),
    entity_id       BIGINT          NOT NULL,           -- FK to the Silver entity
    definition_id   TEXT            NOT NULL,           -- references configuration.workflow_definitions
    -- State
    current_state   TEXT            NOT NULL,
    previous_state  TEXT,
    is_terminal     BOOLEAN         NOT NULL DEFAULT false,
    -- Attribution
    started_by      TEXT            NOT NULL,           -- user_id or 'system'
    organization_id TEXT,
    -- Timestamps
    started_at      TIMESTAMPTZ     NOT NULL DEFAULT now(),
    last_transitioned_at TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    -- Metadata
    context         JSONB           NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_wf_instances_entity
    ON workflow.instances (entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_wf_instances_state
    ON workflow.instances (current_state, is_terminal);
CREATE INDEX IF NOT EXISTS idx_wf_instances_definition
    ON workflow.instances (definition_id);


CREATE TABLE IF NOT EXISTS workflow.events (
    id              BIGSERIAL       PRIMARY KEY,
    instance_id     BIGINT          NOT NULL REFERENCES workflow.instances (id) ON DELETE CASCADE,
    -- Transition
    from_state      TEXT            NOT NULL,
    to_state        TEXT            NOT NULL,
    event_name      TEXT            NOT NULL,           -- e.g. 'START_CONSULTATION'
    -- Attribution
    actor_id        TEXT            NOT NULL,           -- user_id or 'system'
    actor_role      TEXT,
    correlation_id  TEXT,                               -- X-Correlation-ID from HTTP request
    -- Data
    event_data      JSONB           NOT NULL DEFAULT '{}',
    -- Timestamp (immutable)
    occurred_at     TIMESTAMPTZ     NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_wf_events_instance
    ON workflow.events (instance_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_wf_events_correlation
    ON workflow.events (correlation_id)
    WHERE correlation_id IS NOT NULL;


-- ─────────────────────────────────────────────────────────────────────────────
-- Knowledge schema — core tables (Chapter 9 of implementation guide)
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS knowledge.patient_context_cache (
    id              BIGSERIAL       PRIMARY KEY,
    patient_id      INTEGER         NOT NULL,           -- FK to public.royan_patients
    mrn             TEXT            NOT NULL,
    -- Assembled knowledge object (PatientClinicalContext JSON)
    context_data    JSONB           NOT NULL DEFAULT '{}',
    -- Freshness tracking
    assembled_at    TIMESTAMPTZ     NOT NULL DEFAULT now(),
    invalidated_at  TIMESTAMPTZ,                        -- set when a domain event fires
    is_stale        BOOLEAN         NOT NULL DEFAULT false,
    -- Source events that triggered last assembly
    trigger_event   TEXT,
    -- Metadata
    assembly_version TEXT           NOT NULL DEFAULT '1.0'
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_kn_patient_context_mrn
    ON knowledge.patient_context_cache (mrn)
    WHERE is_stale = false;
CREATE INDEX IF NOT EXISTS idx_kn_patient_context_staleness
    ON knowledge.patient_context_cache (is_stale, assembled_at DESC);


CREATE TABLE IF NOT EXISTS knowledge.encounter_context_cache (
    id              BIGSERIAL       PRIMARY KEY,
    encounter_id    INTEGER         NOT NULL UNIQUE,    -- FK to public.royan_encounters
    patient_id      INTEGER         NOT NULL,
    context_data    JSONB           NOT NULL DEFAULT '{}',
    assembled_at    TIMESTAMPTZ     NOT NULL DEFAULT now(),
    is_stale        BOOLEAN         NOT NULL DEFAULT false,
    trigger_event   TEXT
);

CREATE INDEX IF NOT EXISTS idx_kn_encounter_context_stale
    ON knowledge.encounter_context_cache (is_stale, assembled_at DESC);


-- ─────────────────────────────────────────────────────────────────────────────
-- Integration schema — core tables (Chapter 5 of implementation guide)
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS integration.batches (
    id              BIGSERIAL       PRIMARY KEY,
    batch_ref       TEXT            NOT NULL UNIQUE,    -- e.g. 'HOPE-2024-01-15-001'
    source_system   TEXT            NOT NULL DEFAULT 'hope',
    -- Progress tracking
    domains_planned TEXT[]          NOT NULL DEFAULT '{}',
    domains_completed TEXT[]        NOT NULL DEFAULT '{}',
    -- Counts
    total_source_records    INTEGER NOT NULL DEFAULT 0,
    records_imported        INTEGER NOT NULL DEFAULT 0,
    records_rejected        INTEGER NOT NULL DEFAULT 0,
    records_quality_failed  INTEGER NOT NULL DEFAULT 0,
    -- State
    status          TEXT            NOT NULL DEFAULT 'pending'
                                    CHECK (status IN (
                                        'pending', 'running', 'paused',
                                        'completed', 'failed', 'rolled_back'
                                    )),
    -- Quality summary
    avg_quality_score NUMERIC(5,2),
    -- Timestamps
    started_at      TIMESTAMPTZ     NOT NULL DEFAULT now(),
    completed_at    TIMESTAMPTZ,
    last_checkpoint_at TIMESTAMPTZ,
    -- Who triggered it
    triggered_by    TEXT            NOT NULL DEFAULT 'system',
    notes           TEXT
);

CREATE INDEX IF NOT EXISTS idx_int_batches_status
    ON integration.batches (status, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_int_batches_source
    ON integration.batches (source_system, status);


CREATE TABLE IF NOT EXISTS integration.lineage (
    id              BIGSERIAL       PRIMARY KEY,
    batch_id        BIGINT          NOT NULL REFERENCES integration.batches (id) ON DELETE CASCADE,
    -- Source record identity
    source_system   TEXT            NOT NULL,
    source_table    TEXT            NOT NULL,
    source_record_id TEXT           NOT NULL,
    -- Target record identity
    target_schema   TEXT            NOT NULL,
    target_table    TEXT            NOT NULL,
    target_record_id BIGINT         NOT NULL,
    -- Transformation
    canonical_entity_type TEXT      NOT NULL,           -- 'patient', 'encounter', etc.
    transformation_version TEXT     NOT NULL DEFAULT '1.0',
    -- Quality score for this record
    quality_score   NUMERIC(5,2),
    -- Timestamps
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_int_lineage_source
    ON integration.lineage (source_system, source_table, source_record_id);
CREATE INDEX IF NOT EXISTS idx_int_lineage_target
    ON integration.lineage (target_schema, target_table, target_record_id);


-- ─────────────────────────────────────────────────────────────────────────────
-- Configuration schema — workflow definitions (Chapter 8)
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS configuration.workflow_definitions (
    id              TEXT            PRIMARY KEY,        -- e.g. 'encounter.outpatient.v1'
    entity_type     TEXT            NOT NULL,
    version         TEXT            NOT NULL DEFAULT '1.0',
    name            TEXT            NOT NULL,
    description     TEXT,
    -- Full state machine definition (states, transitions, guards)
    definition      JSONB           NOT NULL DEFAULT '{}',
    is_active       BOOLEAN         NOT NULL DEFAULT true,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ     NOT NULL DEFAULT now()
);

-- Seed core clinical workflow definitions
INSERT INTO configuration.workflow_definitions (id, entity_type, version, name, description, definition)
VALUES
(
    'encounter.outpatient.v1',
    'encounter',
    '1.0',
    'Outpatient Visit',
    'Standard outpatient encounter lifecycle',
    '{
        "initial_state": "registered",
        "terminal_states": ["discharged", "closed"],
        "transitions": [
            {"from": "registered",        "event": "QUEUE_PATIENT",         "to": "waiting",          "roles": ["receptionist","nurse","admin"]},
            {"from": "waiting",           "event": "START_TRIAGE",          "to": "in_triage",        "roles": ["nurse"]},
            {"from": "in_triage",         "event": "COMPLETE_TRIAGE",       "to": "consulting",       "roles": ["nurse"]},
            {"from": "waiting",           "event": "CALL_PATIENT",          "to": "consulting",       "roles": ["doctor","nurse"]},
            {"from": "consulting",        "event": "ORDER_LAB",             "to": "awaiting_results", "roles": ["doctor"]},
            {"from": "awaiting_results",  "event": "RESULTS_READY",         "to": "consulting",       "roles": ["doctor","lab_scientist"]},
            {"from": "consulting",        "event": "COMPLETE_CONSULTATION", "to": "billing_pending",  "roles": ["doctor"]},
            {"from": "billing_pending",   "event": "PAYMENT_RECEIVED",      "to": "discharged",       "roles": ["accountant","admin"]},
            {"from": "discharged",        "event": "CLOSE_ENCOUNTER",       "to": "closed",           "roles": ["admin","system"]}
        ]
    }'::jsonb
),
(
    'lab_order.v1',
    'lab_order',
    '1.0',
    'Laboratory Order',
    'Lab order lifecycle from request to verified result',
    '{
        "initial_state": "requested",
        "terminal_states": ["verified", "cancelled"],
        "transitions": [
            {"from": "requested",       "event": "COLLECT_SPECIMEN",   "to": "specimen_collected", "roles": ["nurse","lab_scientist"]},
            {"from": "specimen_collected","event": "BEGIN_PROCESSING", "to": "processing",         "roles": ["lab_scientist"]},
            {"from": "processing",      "event": "RESULT_ENTERED",     "to": "resulted",           "roles": ["lab_scientist"]},
            {"from": "resulted",        "event": "VERIFY_RESULT",      "to": "verified",           "roles": ["lab_scientist","doctor"]},
            {"from": "requested",       "event": "CANCEL",             "to": "cancelled",          "roles": ["doctor","admin"]},
            {"from": "specimen_collected","event": "CANCEL",           "to": "cancelled",          "roles": ["doctor","admin"]}
        ]
    }'::jsonb
),
(
    'prescription.v1',
    'prescription',
    '1.0',
    'Prescription',
    'Prescription lifecycle from issue to administration',
    '{
        "initial_state": "prescribed",
        "terminal_states": ["administered", "cancelled"],
        "transitions": [
            {"from": "prescribed",  "event": "DISPENSE",       "to": "dispensed",    "roles": ["pharmacist"]},
            {"from": "dispensed",   "event": "ADMINISTER",     "to": "administered", "roles": ["nurse","pharmacist"]},
            {"from": "prescribed",  "event": "CANCEL",         "to": "cancelled",    "roles": ["doctor","pharmacist"]}
        ]
    }'::jsonb
),
(
    'invoice.v1',
    'invoice',
    '1.0',
    'Invoice',
    'Billing invoice lifecycle',
    '{
        "initial_state": "draft",
        "terminal_states": ["paid", "voided"],
        "transitions": [
            {"from": "draft",           "event": "SUBMIT",          "to": "submitted",       "roles": ["accountant","admin"]},
            {"from": "submitted",       "event": "PARTIAL_PAYMENT", "to": "partially_paid",  "roles": ["accountant"]},
            {"from": "partially_paid",  "event": "FINAL_PAYMENT",   "to": "paid",            "roles": ["accountant"]},
            {"from": "submitted",       "event": "FULL_PAYMENT",    "to": "paid",            "roles": ["accountant"]},
            {"from": "draft",           "event": "VOID",            "to": "voided",          "roles": ["admin"]},
            {"from": "submitted",       "event": "VOID",            "to": "voided",          "roles": ["admin"]}
        ]
    }'::jsonb
)
ON CONFLICT (id) DO NOTHING;


-- ─────────────────────────────────────────────────────────────────────────────
-- Audit schema — enterprise audit log (beyond existing royan_audit_logs)
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS audit.enterprise_events (
    id              BIGSERIAL       PRIMARY KEY,
    -- What happened
    event_type      TEXT            NOT NULL,           -- e.g. 'PATIENT_REGISTERED'
    entity_type     TEXT,
    entity_id       TEXT,
    -- Who did it
    actor_id        TEXT            NOT NULL,
    actor_role      TEXT,
    -- Traceability
    correlation_id  TEXT,
    session_id      TEXT,
    -- Payload
    before_state    JSONB,
    after_state     JSONB,
    metadata        JSONB           NOT NULL DEFAULT '{}',
    -- When
    occurred_at     TIMESTAMPTZ     NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_audit_ent_events_type
    ON audit.enterprise_events (event_type, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_ent_events_entity
    ON audit.enterprise_events (entity_type, entity_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_ent_events_correlation
    ON audit.enterprise_events (correlation_id)
    WHERE correlation_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_audit_ent_events_actor
    ON audit.enterprise_events (actor_id, occurred_at DESC);


COMMIT;
