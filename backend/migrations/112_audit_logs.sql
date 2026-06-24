-- Migration 112: Royan Hospital Audit Log
-- Immutable audit trail for all security-relevant events (NDPA 2023 compliance).
-- Written on INSERT only — no UPDATE/DELETE should ever touch this table.
-- Schema matches the INSERT columns in src/constants.py (TABLE_AUDIT_LOGS).

ROLLBACK; -- clear any prior aborted transaction
BEGIN;

CREATE TABLE IF NOT EXISTS public.royan_audit_logs (
    id              bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    -- Classification
    event_type      text        NOT NULL,   -- e.g. 'auth.login', 'patient.view', 'billing.edit'
    event_class     text        NOT NULL,   -- e.g. 'auth', 'clinical', 'finance', 'admin'
    action          text        NOT NULL,   -- e.g. 'create', 'read', 'update', 'delete', 'login', 'export'
    outcome         text        NOT NULL    -- 'success' | 'failure' | 'denied'
                    CHECK (outcome IN ('success', 'failure', 'denied')),

    -- Context
    reason_code     text,                   -- machine code: 'token_expired', 'invalid_password', etc.
    actor_id        text,                   -- user UUID or 'system'
    actor_role      text,                   -- role at time of action: 'admin', 'doctor', 'nurse', etc.
    subject_type    text,                   -- 'patient', 'billing', 'user', 'appointment', etc.
    subject_id      text,                   -- ID of the affected record
    trace_id        text,                   -- correlation ID for distributed tracing

    -- Approval / attestation (for high-risk actions)
    approval_reason text,                   -- why the actor performed a sensitive action
    attestation_text text,                  -- free-text attestation from actor
    signature_hash_ref text,               -- reference to a stored digital signature if required

    -- Arbitrary payload (IP, user-agent, query params, etc.) — never store raw PII here
    details         jsonb,

    -- Immutable timestamp — no updated_at on purpose
    created_at      timestamptz NOT NULL DEFAULT now()
);

-- Indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_royan_audit_logs_event_type
    ON public.royan_audit_logs (event_type);
CREATE INDEX IF NOT EXISTS idx_royan_audit_logs_actor_id
    ON public.royan_audit_logs (actor_id);
CREATE INDEX IF NOT EXISTS idx_royan_audit_logs_subject
    ON public.royan_audit_logs (subject_type, subject_id);
CREATE INDEX IF NOT EXISTS idx_royan_audit_logs_created_at
    ON public.royan_audit_logs (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_royan_audit_logs_outcome
    ON public.royan_audit_logs (outcome)
    WHERE outcome IN ('failure', 'denied');

-- Row-Level Security: staff see their own actions; compliance/admin see all
ALTER TABLE public.royan_audit_logs ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS audit_logs_admin_all ON public.royan_audit_logs;
CREATE POLICY audit_logs_admin_all ON public.royan_audit_logs
    FOR ALL USING (true) WITH CHECK (true);

COMMIT;
