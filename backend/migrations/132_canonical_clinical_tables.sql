-- 132_canonical_clinical_tables.sql
-- Canonical Clinical Data Architecture — Chapter 3 & 7 of the Blueprint
-- Creates the missing clinical domain tables that complete the 7-domain model:
--   Triage, Structured Diagnoses, Discharge Records, Lab Specimens,
--   Medication Administration (MAR), Clinical Referrals, Clinical Event Log
--
-- Note: royan_vitals, royan_encounter_notes, royan_nursing_care_plans,
--       royan_fluid_balance, royan_allergies already exist (migration 124).

ROLLBACK;
BEGIN;

-- ─────────────────────────────────────────────────────────────────────────────
-- TRIAGE RECORDS
-- Dedicated triage entity (triage is currently embedded in encounters).
-- New encounters should populate this instead of the inline triage columns.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.royan_triage (
    id              bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    encounter_id    bigint      NOT NULL REFERENCES public.royan_encounters (id) ON DELETE CASCADE,
    patient_id      bigint      NOT NULL REFERENCES public.royan_patients (id) ON DELETE RESTRICT,
    -- Vital signs at triage
    bp_systolic     int,                            -- mmHg
    bp_diastolic    int,                            -- mmHg
    temperature     numeric(5,2),                   -- °C
    pulse           int,                            -- bpm
    respiratory_rate int,                           -- breaths/min
    spo2            numeric(5,2),                   -- %
    weight          numeric(6,2),                   -- kg
    height          numeric(6,2),                   -- cm
    pain_score      int         CHECK (pain_score >= 0 AND pain_score <= 10),
    -- Clinical assessment
    chief_complaint text        NOT NULL DEFAULT '',
    triage_level    text        CHECK (triage_level IN ('immediate', 'urgent', 'less_urgent', 'non_urgent', 'see_and_treat')),
    triage_notes    text,
    -- Audit
    recorded_by     text,
    recorded_by_id  uuid        REFERENCES public.royan_staff (id) ON DELETE SET NULL,
    recorded_at     timestamptz NOT NULL DEFAULT now(),
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_royan_triage_encounter ON public.royan_triage (encounter_id);
CREATE INDEX IF NOT EXISTS idx_royan_triage_patient   ON public.royan_triage (patient_id);
CREATE INDEX IF NOT EXISTS idx_royan_triage_level     ON public.royan_triage (triage_level);
CREATE INDEX IF NOT EXISTS idx_royan_triage_recorded  ON public.royan_triage (recorded_at DESC);


-- ─────────────────────────────────────────────────────────────────────────────
-- CLINICAL DIAGNOSES
-- Structured per-diagnosis records linked to the diagnosis catalog.
-- Complements the encounter-level diagnosis_codes[] and diagnosis_notes.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.royan_clinical_diagnoses (
    id              bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    encounter_id    bigint      NOT NULL REFERENCES public.royan_encounters (id) ON DELETE CASCADE,
    patient_id      bigint      NOT NULL REFERENCES public.royan_patients (id) ON DELETE RESTRICT,
    -- Catalog FK (preferred) + free-text fallback for uncoded diagnoses
    catalog_id      bigint      REFERENCES public.royan_diagnosis_catalog (id) ON DELETE SET NULL,
    icd_code        text,                           -- ICD-10 code (from catalog or free-text)
    description     text        NOT NULL,           -- diagnosis description
    diagnosis_type  text        NOT NULL DEFAULT 'primary'
                                CHECK (diagnosis_type IN ('primary', 'secondary', 'complication', 'provisional', 'differential')),
    -- Attribution
    diagnosed_by    text,                           -- doctor name (free-text, legacy)
    diagnosed_by_id uuid        REFERENCES public.royan_staff (id) ON DELETE SET NULL,
    diagnosed_at    timestamptz NOT NULL DEFAULT now(),
    notes           text,
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_royan_clin_dx_encounter  ON public.royan_clinical_diagnoses (encounter_id);
CREATE INDEX IF NOT EXISTS idx_royan_clin_dx_patient    ON public.royan_clinical_diagnoses (patient_id);
CREATE INDEX IF NOT EXISTS idx_royan_clin_dx_catalog    ON public.royan_clinical_diagnoses (catalog_id);
CREATE INDEX IF NOT EXISTS idx_royan_clin_dx_icd        ON public.royan_clinical_diagnoses (icd_code);


-- ─────────────────────────────────────────────────────────────────────────────
-- DISCHARGE RECORDS
-- Formal discharge documentation separate from the brief encounter discharge_summary.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.royan_discharge_records (
    id                  bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    encounter_id        bigint      NOT NULL UNIQUE REFERENCES public.royan_encounters (id) ON DELETE CASCADE,
    patient_id          bigint      NOT NULL REFERENCES public.royan_patients (id) ON DELETE RESTRICT,
    -- Discharge assessment
    discharge_condition text        NOT NULL DEFAULT 'stable'
                                    CHECK (discharge_condition IN (
                                        'stable', 'improved', 'deteriorated', 'transferred',
                                        'absconded', 'against_medical_advice', 'deceased'
                                    )),
    discharge_diagnosis text,       -- final discharge diagnosis (narrative)
    discharge_summary   text,       -- full discharge summary
    -- Follow-up plan
    follow_up_instructions text,
    follow_up_date      date,
    referred_to         text,       -- if transferred/referred out
    -- Discharge medications (summary; full list in prescriptions)
    discharge_medications text,
    -- Attribution
    discharged_by       text,
    discharged_by_id    uuid        REFERENCES public.royan_staff (id) ON DELETE SET NULL,
    approved_by_id      uuid        REFERENCES public.royan_staff (id) ON DELETE SET NULL,
    discharged_at       timestamptz NOT NULL DEFAULT now(),
    -- MDM lineage
    external_source     text,
    external_id         text,
    created_at          timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_royan_discharge_external
    ON public.royan_discharge_records (external_source, external_id)
    WHERE external_source IS NOT NULL AND external_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_royan_discharge_patient     ON public.royan_discharge_records (patient_id);
CREATE INDEX IF NOT EXISTS idx_royan_discharge_condition   ON public.royan_discharge_records (discharge_condition);
CREATE INDEX IF NOT EXISTS idx_royan_discharge_at          ON public.royan_discharge_records (discharged_at DESC);


-- ─────────────────────────────────────────────────────────────────────────────
-- LAB SPECIMENS
-- Tracks specimen collection as a distinct clinical event.
-- One lab order may require one or more specimens.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.royan_lab_specimens (
    id              bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    lab_order_id    bigint      NOT NULL REFERENCES public.royan_lab_orders (id) ON DELETE CASCADE,
    patient_id      bigint      NOT NULL REFERENCES public.royan_patients (id) ON DELETE RESTRICT,
    specimen_type   text        NOT NULL DEFAULT 'blood'
                                CHECK (specimen_type IN (
                                    'blood', 'urine', 'stool', 'sputum', 'csf', 'swab',
                                    'tissue', 'serum', 'plasma', 'other'
                                )),
    specimen_label  text,                           -- barcode/label
    volume          text,                           -- e.g. "5 mL"
    container       text,                           -- e.g. "EDTA tube", "plain tube"
    status          text        NOT NULL DEFAULT 'collected'
                                CHECK (status IN ('collected', 'received', 'processing', 'rejected')),
    rejection_reason text,
    collected_by    text,
    collected_by_id uuid        REFERENCES public.royan_staff (id) ON DELETE SET NULL,
    collected_at    timestamptz NOT NULL DEFAULT now(),
    received_at     timestamptz,
    notes           text,
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_royan_specimens_order   ON public.royan_lab_specimens (lab_order_id);
CREATE INDEX IF NOT EXISTS idx_royan_specimens_patient ON public.royan_lab_specimens (patient_id);
CREATE INDEX IF NOT EXISTS idx_royan_specimens_status  ON public.royan_lab_specimens (status);


-- ─────────────────────────────────────────────────────────────────────────────
-- MEDICATION ADMINISTRATION RECORDS (MAR)
-- Tracks each individual dose of medication given to a patient.
-- Basis for inpatient nursing medication rounds.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.royan_medication_admin (
    id                  bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    prescription_id     bigint      NOT NULL REFERENCES public.royan_prescriptions (id) ON DELETE RESTRICT,
    patient_id          bigint      NOT NULL REFERENCES public.royan_patients (id) ON DELETE RESTRICT,
    encounter_id        bigint      REFERENCES public.royan_encounters (id) ON DELETE SET NULL,
    -- What was given
    drug_name           text        NOT NULL,           -- copy from prescription (denorm for audit)
    dose_given          text        NOT NULL,           -- e.g. "500mg"
    route               text        NOT NULL DEFAULT 'oral'
                                    CHECK (route IN ('oral', 'iv', 'im', 'topical', 'inhaled',
                                                     'sublingual', 'rectal', 'other')),
    site                text,                           -- e.g. "left deltoid" for injections
    -- Outcome
    status              text        NOT NULL DEFAULT 'given'
                                    CHECK (status IN ('given', 'refused', 'held', 'not_available', 'omitted')),
    omission_reason     text,
    -- Attribution
    administered_by     text,
    administered_by_id  uuid        REFERENCES public.royan_staff (id) ON DELETE SET NULL,
    admin_time          timestamptz NOT NULL DEFAULT now(),
    witnessed_by_id     uuid        REFERENCES public.royan_staff (id) ON DELETE SET NULL,
    notes               text,
    created_at          timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_royan_med_admin_prescription ON public.royan_medication_admin (prescription_id);
CREATE INDEX IF NOT EXISTS idx_royan_med_admin_patient      ON public.royan_medication_admin (patient_id);
CREATE INDEX IF NOT EXISTS idx_royan_med_admin_encounter    ON public.royan_medication_admin (encounter_id);
CREATE INDEX IF NOT EXISTS idx_royan_med_admin_time         ON public.royan_medication_admin (admin_time DESC);


-- ─────────────────────────────────────────────────────────────────────────────
-- CLINICAL REFERRALS
-- Tracks referrals between departments or to external facilities.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.royan_referrals (
    id                  bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    encounter_id        bigint      NOT NULL REFERENCES public.royan_encounters (id) ON DELETE CASCADE,
    patient_id          bigint      NOT NULL REFERENCES public.royan_patients (id) ON DELETE RESTRICT,
    -- Referral details
    referral_type       text        NOT NULL DEFAULT 'internal'
                                    CHECK (referral_type IN ('internal', 'external', 'specialist')),
    referred_to_dept_id bigint      REFERENCES public.royan_departments (id) ON DELETE SET NULL,
    referred_to_dept    text,                           -- free-text for external facilities
    referred_to_facility text,                          -- external hospital/clinic name
    referred_to_doctor  text,                           -- receiving doctor name
    urgency             text        NOT NULL DEFAULT 'routine'
                                    CHECK (urgency IN ('routine', 'urgent', 'emergency')),
    reason              text        NOT NULL,
    clinical_summary    text,
    status              text        NOT NULL DEFAULT 'sent'
                                    CHECK (status IN ('sent', 'accepted', 'declined', 'completed', 'cancelled')),
    -- Attribution
    referred_by         text,
    referred_by_id      uuid        REFERENCES public.royan_staff (id) ON DELETE SET NULL,
    referred_at         timestamptz NOT NULL DEFAULT now(),
    accepted_at         timestamptz,
    completed_at        timestamptz,
    response_notes      text,
    created_at          timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_royan_referrals_encounter ON public.royan_referrals (encounter_id);
CREATE INDEX IF NOT EXISTS idx_royan_referrals_patient   ON public.royan_referrals (patient_id);
CREATE INDEX IF NOT EXISTS idx_royan_referrals_dept      ON public.royan_referrals (referred_to_dept_id);
CREATE INDEX IF NOT EXISTS idx_royan_referrals_status    ON public.royan_referrals (status);


-- ─────────────────────────────────────────────────────────────────────────────
-- CLINICAL EVENT LOG
-- Immutable append-only ledger of all significant clinical events.
-- Implements the Event Sourcing principles from Chapter 3.8-3.9.
-- Every service-layer mutation should emit an event here.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.royan_clinical_event_log (
    id              bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    -- Event classification
    event_type      text        NOT NULL
                                CHECK (event_type IN (
                                    'ENCOUNTER_CREATED', 'ENCOUNTER_TRIAGED', 'ENCOUNTER_CONSULTING',
                                    'ENCOUNTER_DISCHARGED', 'ENCOUNTER_ADMITTED', 'ENCOUNTER_TRANSFERRED',
                                    'LAB_ORDER_CREATED', 'LAB_SAMPLE_COLLECTED', 'LAB_RESULT_READY',
                                    'LAB_RESULT_CRITICAL', 'LAB_RESULT_VERIFIED',
                                    'PRESCRIPTION_ISSUED', 'MEDICATION_DISPENSED', 'MEDICATION_ADMINISTERED',
                                    'BILL_GENERATED', 'PAYMENT_RECEIVED', 'INSURANCE_CLAIM_SUBMITTED',
                                    'DIAGNOSIS_RECORDED', 'REFERRAL_SENT', 'VITALS_RECORDED',
                                    'TRIAGE_COMPLETED', 'DISCHARGE_COMPLETED', 'CONSENT_OBTAINED',
                                    'ALERT_TRIGGERED', 'SYSTEM_EVENT'
                                )),
    -- Context
    encounter_id    bigint      REFERENCES public.royan_encounters (id) ON DELETE SET NULL,
    patient_id      bigint      REFERENCES public.royan_patients (id) ON DELETE SET NULL,
    entity_type     text,                               -- e.g. "lab_order", "prescription", "billing"
    entity_id       bigint,                             -- PK of the referenced entity
    -- Attribution
    performed_by    text,                               -- staff name (free-text, from JWT)
    performed_by_id uuid        REFERENCES public.royan_staff (id) ON DELETE SET NULL,
    department_id   bigint      REFERENCES public.royan_departments (id) ON DELETE SET NULL,
    -- Payload
    event_data      jsonb       NOT NULL DEFAULT '{}',  -- structured context (keys vary by event_type)
    outcome         text        NOT NULL DEFAULT 'success'
                                CHECK (outcome IN ('success', 'failure', 'warning', 'info')),
    notes           text,
    -- Immutable timestamp
    occurred_at     timestamptz NOT NULL DEFAULT now()
);

-- Events are immutable — no UPDATE/DELETE. Partition by month for performance.
-- Indexes optimized for patient timeline and encounter event queries.
CREATE INDEX IF NOT EXISTS idx_clin_event_encounter ON public.royan_clinical_event_log (encounter_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_clin_event_patient   ON public.royan_clinical_event_log (patient_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_clin_event_type      ON public.royan_clinical_event_log (event_type, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_clin_event_entity    ON public.royan_clinical_event_log (entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_clin_event_time      ON public.royan_clinical_event_log (occurred_at DESC);

-- GIN index for event_data JSONB queries
CREATE INDEX IF NOT EXISTS idx_clin_event_data_gin ON public.royan_clinical_event_log USING GIN (event_data);


-- ─────────────────────────────────────────────────────────────────────────────
-- PATIENT CONSENT RECORDS — Chapter 18 (NDPA 2023 compliance)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.royan_patient_consent (
    id              bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    patient_id      bigint      NOT NULL REFERENCES public.royan_patients (id) ON DELETE RESTRICT,
    consent_type    text        NOT NULL
                                CHECK (consent_type IN (
                                    'data_processing', 'marketing', 'research',
                                    'treatment', 'surgical', 'telemedicine',
                                    'third_party_sharing', 'photography'
                                )),
    is_given        boolean     NOT NULL DEFAULT true,
    given_at        timestamptz NOT NULL DEFAULT now(),
    withdrawn_at    timestamptz,
    expiry_date     date,
    notes           text,
    recorded_by     text,
    ip_address      text,
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_royan_consent_patient ON public.royan_patient_consent (patient_id, consent_type);
CREATE INDEX IF NOT EXISTS idx_royan_consent_active  ON public.royan_patient_consent (patient_id)
    WHERE is_given = true AND withdrawn_at IS NULL;

COMMIT;
