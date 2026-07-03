-- Migration 134: MDM Governance Workflow
-- Implements Blueprint Chapter 4.3–4.11 — lifecycle management for all
-- Master Data Management (MDM) entities. Provides a change request /
-- approval workflow so that no master data change reaches production
-- without review.
-- MDM entity tables themselves were created in migration 130.
-- Safe to re-run: uses IF NOT EXISTS guards.

ROLLBACK;
BEGIN;

-- ─────────────────────────────────────────────────────────────────────────────
-- 1. MDM Change Request table
--    All proposed creates, updates, or deprecations start as a draft here.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.royan_mdm_change_requests (
    id              SERIAL          PRIMARY KEY,
    -- What is being changed
    entity_type     TEXT            NOT NULL
                                    CHECK (entity_type IN (
                                        'department', 'staff', 'lab_catalog',
                                        'drug_formulary', 'diagnosis_catalog',
                                        'procedure_catalog', 'service_catalog',
                                        'ward', 'hmo'
                                    )),
    entity_id       INTEGER,                        -- NULL for 'create' actions
    action          TEXT            NOT NULL
                                    CHECK (action IN (
                                        'create', 'update', 'deprecate', 'reactivate'
                                    )),
    -- The proposed data (full record for create; diff patch for update)
    proposed_data   JSONB           NOT NULL DEFAULT '{}',
    -- Lifecycle state
    status          TEXT            NOT NULL DEFAULT 'draft'
                                    CHECK (status IN (
                                        'draft', 'pending_review',
                                        'approved', 'rejected',
                                        'published', 'withdrawn'
                                    )),
    -- Attribution
    requested_by    TEXT            NOT NULL,
    request_notes   TEXT,
    reviewed_by     TEXT,
    review_notes    TEXT,
    -- Timestamps
    submitted_at    TIMESTAMPTZ,                    -- when moved draft→pending_review
    reviewed_at     TIMESTAMPTZ,
    published_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ     NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_mdm_cr_type_status
    ON public.royan_mdm_change_requests (entity_type, status);
CREATE INDEX IF NOT EXISTS idx_mdm_cr_requester
    ON public.royan_mdm_change_requests (requested_by, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_mdm_cr_pending
    ON public.royan_mdm_change_requests (status)
    WHERE status IN ('pending_review', 'approved');


-- ─────────────────────────────────────────────────────────────────────────────
-- 2. Add governance columns to existing MDM tables (if not already present)
--    deprecated_at / deprecated_by let us soft-delete master records without
--    breaking historical FK references.
-- ─────────────────────────────────────────────────────────────────────────────

-- royan_departments
ALTER TABLE public.royan_departments
    ADD COLUMN IF NOT EXISTS deprecated_at  TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS deprecated_by  TEXT,
    ADD COLUMN IF NOT EXISTS version        INTEGER NOT NULL DEFAULT 1;

-- royan_staff
ALTER TABLE public.royan_staff
    ADD COLUMN IF NOT EXISTS deprecated_at  TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS deprecated_by  TEXT,
    ADD COLUMN IF NOT EXISTS version        INTEGER NOT NULL DEFAULT 1;

-- royan_lab_catalog
ALTER TABLE public.royan_lab_catalog
    ADD COLUMN IF NOT EXISTS deprecated_at  TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS deprecated_by  TEXT,
    ADD COLUMN IF NOT EXISTS version        INTEGER NOT NULL DEFAULT 1;

-- royan_drug_formulary
ALTER TABLE public.royan_drug_formulary
    ADD COLUMN IF NOT EXISTS deprecated_at  TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS deprecated_by  TEXT,
    ADD COLUMN IF NOT EXISTS version        INTEGER NOT NULL DEFAULT 1;

-- royan_diagnosis_catalog
ALTER TABLE public.royan_diagnosis_catalog
    ADD COLUMN IF NOT EXISTS deprecated_at  TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS deprecated_by  TEXT,
    ADD COLUMN IF NOT EXISTS version        INTEGER NOT NULL DEFAULT 1;


-- ─────────────────────────────────────────────────────────────────────────────
-- 3. MDM Audit log — immutable record of every published change
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.royan_mdm_audit (
    id              BIGSERIAL       PRIMARY KEY,
    change_request_id INTEGER        REFERENCES public.royan_mdm_change_requests (id) ON DELETE SET NULL,
    entity_type     TEXT            NOT NULL,
    entity_id       INTEGER,
    action          TEXT            NOT NULL,
    before_data     JSONB           DEFAULT '{}',
    after_data      JSONB           DEFAULT '{}',
    performed_by    TEXT            NOT NULL,
    occurred_at     TIMESTAMPTZ     NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_mdm_audit_entity
    ON public.royan_mdm_audit (entity_type, entity_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_mdm_audit_time
    ON public.royan_mdm_audit (occurred_at DESC);

COMMIT;
