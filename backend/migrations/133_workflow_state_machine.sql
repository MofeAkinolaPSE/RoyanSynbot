-- Migration 133: Clinical Workflow State Machine
-- Implements Blueprint Chapter 10 — encounter lifecycle transitions with
-- prerequisite gates, role enforcement, and immutable audit trail.
-- Also extends the encounters status CHECK constraint and the clinical
-- event log event_type CHECK constraint with new workflow-aligned values.
-- Safe to re-run: all objects use IF NOT EXISTS / IF EXISTS guards.

ROLLBACK;
BEGIN;

-- ─────────────────────────────────────────────────────────────────────────────
-- 1. Extend royan_encounters.status CHECK constraint
--    Adds statuses required by the blueprint workflow model.
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE public.royan_encounters
    DROP CONSTRAINT IF EXISTS royan_encounters_status_check;

ALTER TABLE public.royan_encounters
    ADD CONSTRAINT royan_encounters_status_check CHECK (status IN (
        -- Legacy / existing values (kept for backwards compat)
        'patient_registered',
        'triaged',
        'nurse_assessment',
        'called',
        'consulting',
        'lab_ordered',
        'pharmacy_dispensing',
        'billing_pending',
        'discharged',
        -- New blueprint-aligned values
        'waiting',          -- queued in reception, not yet called
        'in_triage',        -- being assessed by triage nurse
        'in_consultation',  -- with doctor
        'awaiting_results', -- investigations pending
        'admitted',         -- admitted to inpatient ward
        'closed'            -- encounter fully closed after discharge + billing settled
    ));


-- ─────────────────────────────────────────────────────────────────────────────
-- 2. Extend royan_clinical_event_log.event_type CHECK constraint
--    Adds new event types for workflow transitions and patient registration.
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE public.royan_clinical_event_log
    DROP CONSTRAINT IF EXISTS royan_clinical_event_log_event_type_check;

ALTER TABLE public.royan_clinical_event_log
    ADD CONSTRAINT royan_clinical_event_log_event_type_check
    CHECK (event_type IN (
        -- Encounter lifecycle (existing)
        'ENCOUNTER_CREATED', 'ENCOUNTER_TRIAGED', 'ENCOUNTER_CONSULTING',
        'ENCOUNTER_DISCHARGED', 'ENCOUNTER_ADMITTED', 'ENCOUNTER_TRANSFERRED',
        -- Lab (existing)
        'LAB_ORDER_CREATED', 'LAB_SAMPLE_COLLECTED', 'LAB_RESULT_READY',
        'LAB_RESULT_CRITICAL', 'LAB_RESULT_VERIFIED',
        -- Medication (existing)
        'PRESCRIPTION_ISSUED', 'MEDICATION_DISPENSED', 'MEDICATION_ADMINISTERED',
        -- Finance (existing)
        'BILL_GENERATED', 'PAYMENT_RECEIVED', 'INSURANCE_CLAIM_SUBMITTED',
        -- Clinical (existing)
        'DIAGNOSIS_RECORDED', 'REFERRAL_SENT', 'VITALS_RECORDED',
        'TRIAGE_COMPLETED', 'DISCHARGE_COMPLETED', 'CONSENT_OBTAINED',
        -- System (existing)
        'ALERT_TRIGGERED', 'SYSTEM_EVENT',
        -- NEW — workflow state machine transitions
        'ENCOUNTER_QUEUED',         -- patient moves from registered → waiting
        'ENCOUNTER_CLOSED',         -- encounter fully closed
        'CONSULTATION_COMPLETED',   -- doctor marks consultation done
        'PATIENT_REGISTERED',       -- new patient record created
        'CLINICAL_NOTE_AUTHORED',   -- SOAP / progress note saved
        'SPECIMEN_COLLECTED'        -- synonym for LAB_SAMPLE_COLLECTED (compat)
    ));


-- ─────────────────────────────────────────────────────────────────────────────
-- 3. Workflow transitions — authoritative state machine definition
--    Each row defines one legal encounter state transition.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.royan_workflow_transitions (
    id              SERIAL          PRIMARY KEY,
    from_state      TEXT            NOT NULL,
    to_state        TEXT            NOT NULL,
    transition_name TEXT            NOT NULL,
    allowed_roles   TEXT[]          NOT NULL DEFAULT '{}',
    prerequisites   JSONB           NOT NULL DEFAULT '[]',
    auto_emit_event TEXT,           -- event_type written to royan_clinical_event_log on success
    description     TEXT,
    is_active       BOOLEAN         NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT now(),
    UNIQUE (from_state, to_state)
);

CREATE INDEX IF NOT EXISTS idx_wf_transition_from ON public.royan_workflow_transitions (from_state);
CREATE INDEX IF NOT EXISTS idx_wf_transition_active ON public.royan_workflow_transitions (is_active);

-- Seed: standard OPD clinical lifecycle
INSERT INTO public.royan_workflow_transitions
    (from_state, to_state, transition_name, allowed_roles, prerequisites, auto_emit_event, description)
VALUES
    ('patient_registered', 'waiting',
     'queue_patient',
     '{receptionist,nurse,admin,doctor}',
     '[]',
     'ENCOUNTER_QUEUED',
     'Reception queues registered patient to waiting area'),

    ('waiting', 'called',
     'call_patient',
     '{receptionist,nurse,admin}',
     '[]',
     'SYSTEM_EVENT',
     'Patient called from waiting area to consultation'),

    ('called', 'in_triage',
     'start_triage',
     '{nurse,doctor}',
     '[]',
     'ENCOUNTER_TRIAGED',
     'Triage nurse begins vital signs and assessment'),

    ('in_triage', 'in_consultation',
     'start_consultation',
     '{doctor}',
     '[{"check":"triage_complete"}]',
     'ENCOUNTER_CONSULTING',
     'Doctor opens consultation after triage is complete'),

    ('triaged', 'in_consultation',
     'start_consultation_from_triaged',
     '{doctor}',
     '[]',
     'ENCOUNTER_CONSULTING',
     'Legacy path: triaged → consultation'),

    ('nurse_assessment', 'in_consultation',
     'start_consultation_from_assessment',
     '{doctor}',
     '[]',
     'ENCOUNTER_CONSULTING',
     'Doctor opens consultation after nurse assessment'),

    ('in_consultation', 'awaiting_results',
     'order_investigations',
     '{doctor}',
     '[]',
     'SYSTEM_EVENT',
     'Doctor orders investigations; encounter waits for results'),

    ('lab_ordered', 'in_consultation',
     'results_reviewed_legacy',
     '{doctor}',
     '[]',
     'SYSTEM_EVENT',
     'Legacy path: lab_ordered → consultation after review'),

    ('awaiting_results', 'in_consultation',
     'results_reviewed',
     '{doctor}',
     '[{"check":"all_labs_resulted"}]',
     'SYSTEM_EVENT',
     'All pending investigations completed; doctor reviews'),

    ('in_consultation', 'billing_pending',
     'complete_consultation',
     '{doctor}',
     '[{"check":"diagnosis_recorded"}]',
     'CONSULTATION_COMPLETED',
     'Doctor completes consultation; bill is generated'),

    ('consulting', 'billing_pending',
     'complete_consultation_legacy',
     '{doctor,admin}',
     '[]',
     'CONSULTATION_COMPLETED',
     'Legacy consulting state → billing'),

    ('pharmacy_dispensing', 'billing_pending',
     'pharmacy_to_billing',
     '{pharmacist,admin}',
     '[]',
     'SYSTEM_EVENT',
     'Pharmacy dispensing complete; proceed to billing'),

    ('billing_pending', 'discharged',
     'discharge',
     '{doctor,admin,nurse}',
     '[{"check":"bill_settled_or_waived"}]',
     'DISCHARGE_COMPLETED',
     'Patient discharged after bill is settled or waived'),

    ('discharged', 'closed',
     'close_encounter',
     '{admin}',
     '[]',
     'ENCOUNTER_CLOSED',
     'Encounter administratively closed'),

    -- Emergency bypass: skip triage/waiting for A&E
    ('patient_registered', 'in_consultation',
     'emergency_bypass',
     '{doctor}',
     '[]',
     'ENCOUNTER_CONSULTING',
     'Emergency: skip queue/triage and go directly to consultation'),

    -- Inpatient admission
    ('in_consultation', 'admitted',
     'admit_patient',
     '{doctor,admin}',
     '[{"check":"bed_assigned"}]',
     'ENCOUNTER_ADMITTED',
     'Patient admitted to inpatient ward')

ON CONFLICT (from_state, to_state) DO NOTHING;


-- ─────────────────────────────────────────────────────────────────────────────
-- 4. Transition audit log
--    Immutable record of every attempted state transition (pass or fail).
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.royan_transition_audit (
    id              BIGSERIAL       PRIMARY KEY,
    encounter_id    INTEGER         NOT NULL REFERENCES public.royan_encounters (id) ON DELETE CASCADE,
    from_state      TEXT            NOT NULL,
    to_state        TEXT            NOT NULL,
    transition_name TEXT,
    performed_by    TEXT,
    gate_results    JSONB           NOT NULL DEFAULT '{}',
    outcome         TEXT            NOT NULL CHECK (outcome IN ('success', 'blocked', 'error')),
    block_reason    TEXT,
    occurred_at     TIMESTAMPTZ     NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_transition_audit_encounter
    ON public.royan_transition_audit (encounter_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_transition_audit_outcome
    ON public.royan_transition_audit (outcome, occurred_at DESC);

COMMIT;
