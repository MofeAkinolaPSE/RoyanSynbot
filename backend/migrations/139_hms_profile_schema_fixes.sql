-- Migration 139: Schema drift fixes surfaced by live HMS testing
-- Adds columns/tables that application code (routers/services) already
-- reads and writes but were never created by an earlier migration.
-- Safe to re-run (IF NOT EXISTS everywhere).

BEGIN;

-- ── royan_encounters: patient-profile timeline expects a general notes field ──
ALTER TABLE public.royan_encounters
    ADD COLUMN IF NOT EXISTS notes text;

-- ── royan_prescriptions: pharmacy dispensing records the dispense timestamp
--    directly on the prescription (in addition to royan_dispensing rows) ──────
ALTER TABLE public.royan_prescriptions
    ADD COLUMN IF NOT EXISTS dispensed_at timestamptz;

-- ── royan_radiology_orders: migration 137 only created a bare skeleton;
--    the radiology router (src/routers/radiology.py) reads/writes a much
--    richer set of columns that were never added. ordered_at replaces the
--    unused `order_date` (date-only) with a precise timestamp used for
--    worklist sorting and TAT-in-minutes calculation. ────────────────────────
ALTER TABLE public.royan_radiology_orders
    ADD COLUMN IF NOT EXISTS modality             text,
    ADD COLUMN IF NOT EXISTS body_part            text,
    ADD COLUMN IF NOT EXISTS clinical_indication  text,
    ADD COLUMN IF NOT EXISTS urgency              text DEFAULT 'routine',
    ADD COLUMN IF NOT EXISTS ordered_by           text,
    ADD COLUMN IF NOT EXISTS notes                text,
    ADD COLUMN IF NOT EXISTS pacs_study_uid       text,
    ADD COLUMN IF NOT EXISTS ordered_at           timestamptz NOT NULL DEFAULT now(),
    ADD COLUMN IF NOT EXISTS scheduled_at         timestamptz,
    ADD COLUMN IF NOT EXISTS started_at           timestamptz,
    ADD COLUMN IF NOT EXISTS reported_at          timestamptz,
    ADD COLUMN IF NOT EXISTS report               text,
    ADD COLUMN IF NOT EXISTS impression           text,
    ADD COLUMN IF NOT EXISTS radiologist_id       text,
    ADD COLUMN IF NOT EXISTS findings             text,
    ADD COLUMN IF NOT EXISTS tat_minutes          numeric;

CREATE INDEX IF NOT EXISTS idx_radiology_orders_ordered_at ON public.royan_radiology_orders (ordered_at DESC);

-- ── Surgical Theatre cases (src/routers/theatre.py) ──────────────────────────
CREATE TABLE IF NOT EXISTS public.royan_theatre_cases (
    id                    bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    encounter_id          bigint      NOT NULL REFERENCES public.royan_encounters (id) ON DELETE RESTRICT,
    patient_id            bigint      NOT NULL REFERENCES public.royan_patients (id) ON DELETE RESTRICT,
    theatre_name          text,
    procedure_name        text        NOT NULL,
    case_type             text,
    urgency               text        NOT NULL DEFAULT 'elective',
    scheduled_date        date,
    start_time            text,
    actual_start_time     timestamptz,
    actual_end_time       timestamptz,
    surgeon_id            text,
    anaesthetist_id       text,
    scrub_nurse           text,
    circulating_nurse     text,
    status                text        NOT NULL DEFAULT 'scheduled',
    booked_by             text,
    notes                 text,
    pre_op_checklist      jsonb,
    pre_op_completed_by   text,
    pre_op_completed_at   timestamptz,
    anaesthetic_record    jsonb,
    operative_notes       jsonb,
    operative_notes_by    text,
    post_op_notes         jsonb,
    post_op_by            text,
    post_op_at            timestamptz,
    created_at            timestamptz NOT NULL DEFAULT now(),
    updated_at            timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_theatre_cases_patient        ON public.royan_theatre_cases (patient_id);
CREATE INDEX IF NOT EXISTS idx_theatre_cases_encounter      ON public.royan_theatre_cases (encounter_id);
CREATE INDEX IF NOT EXISTS idx_theatre_cases_scheduled_date ON public.royan_theatre_cases (scheduled_date DESC);
CREATE INDEX IF NOT EXISTS idx_theatre_cases_status         ON public.royan_theatre_cases (status);

-- ── Lab reference ranges (src/routers/lab.py) ────────────────────────────────
CREATE TABLE IF NOT EXISTS public.royan_lab_reference_ranges (
    id             bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    test_name      text        NOT NULL,
    loinc_code     text,
    gender         text,
    age_min        numeric,
    age_max        numeric,
    unit           text,
    normal_low     numeric,
    normal_high    numeric,
    critical_low   numeric,
    critical_high  numeric,
    notes          text,
    active         boolean     NOT NULL DEFAULT true,
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_lab_reference_ranges_test_name ON public.royan_lab_reference_ranges (test_name);

-- ── Telemedicine sessions (src/routers/telemedicine.py) ──────────────────────
CREATE TABLE IF NOT EXISTS public.royan_telemedicine_sessions (
    id                    bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    patient_id            bigint      NOT NULL REFERENCES public.royan_patients (id) ON DELETE RESTRICT,
    encounter_id          bigint      REFERENCES public.royan_encounters (id) ON DELETE SET NULL,
    doctor_id             text        NOT NULL,
    scheduled_date        date        NOT NULL,
    scheduled_time        text        NOT NULL,
    duration_minutes      int         NOT NULL DEFAULT 30,
    visit_type            text        NOT NULL DEFAULT 'consultation',
    chief_complaint       text,
    notes                 text,
    doctor_notes          text,
    prescriptions_issued  boolean     NOT NULL DEFAULT false,
    status                text        NOT NULL DEFAULT 'scheduled',
    meeting_link          text,
    created_by            text,
    started_at            timestamptz,
    ended_at              timestamptz,
    created_at            timestamptz NOT NULL DEFAULT now(),
    updated_at            timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_telemedicine_sessions_patient        ON public.royan_telemedicine_sessions (patient_id);
CREATE INDEX IF NOT EXISTS idx_telemedicine_sessions_doctor         ON public.royan_telemedicine_sessions (doctor_id);
CREATE INDEX IF NOT EXISTS idx_telemedicine_sessions_scheduled_date ON public.royan_telemedicine_sessions (scheduled_date DESC);
CREATE INDEX IF NOT EXISTS idx_telemedicine_sessions_status         ON public.royan_telemedicine_sessions (status);

-- ── Notification logs + SMS templates (src/routers/notifications.py) ────────
CREATE TABLE IF NOT EXISTS public.royan_notification_logs (
    id                    bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    channel               text        NOT NULL DEFAULT 'sms',
    recipient             text        NOT NULL,
    message               text        NOT NULL,
    status                text        NOT NULL DEFAULT 'queued',
    provider_message_id   text,
    patient_id            bigint      REFERENCES public.royan_patients (id) ON DELETE SET NULL,
    appointment_id        bigint,
    template_id           bigint,
    campaign_name         text,
    sent_by               text,
    sent_at               timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_notification_logs_sent_at  ON public.royan_notification_logs (sent_at DESC);
CREATE INDEX IF NOT EXISTS idx_notification_logs_patient  ON public.royan_notification_logs (patient_id);
CREATE INDEX IF NOT EXISTS idx_notification_logs_status   ON public.royan_notification_logs (status);
CREATE INDEX IF NOT EXISTS idx_notification_logs_campaign ON public.royan_notification_logs (campaign_name);

CREATE TABLE IF NOT EXISTS public.royan_sms_templates (
    id           bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name         text        NOT NULL,
    channel      text        NOT NULL DEFAULT 'sms',
    body         text        NOT NULL,
    variables    text,
    category     text,
    active       boolean     NOT NULL DEFAULT true,
    created_by   text,
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_sms_templates_name     ON public.royan_sms_templates (name);
CREATE INDEX IF NOT EXISTS idx_sms_templates_category ON public.royan_sms_templates (category);

-- ── Drug inventory + drug-drug interactions (src/routers/pharmacy_dispensing.py) ──
CREATE TABLE IF NOT EXISTS public.royan_drug_inventory (
    id              bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    drug_name       text        NOT NULL,
    drug_code       text,
    generic_name    text,
    formulation     text,
    strength        text,
    unit            text        NOT NULL DEFAULT 'tablet',
    stock_quantity  numeric     NOT NULL DEFAULT 0,
    reorder_level   numeric     NOT NULL DEFAULT 0,
    unit_cost       numeric     NOT NULL DEFAULT 0,
    supplier        text,
    location        text,
    expiry_date     date,
    batch_number    text,
    notes           text,
    created_by      text,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_drug_inventory_drug_name ON public.royan_drug_inventory (drug_name);

CREATE TABLE IF NOT EXISTS public.royan_drug_interactions (
    id           bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    drug_a       text        NOT NULL,
    drug_b       text        NOT NULL,
    severity     text        NOT NULL DEFAULT 'moderate',
    description  text,
    created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_drug_interactions_drug_a ON public.royan_drug_interactions (drug_a);
CREATE INDEX IF NOT EXISTS idx_drug_interactions_drug_b ON public.royan_drug_interactions (drug_b);

COMMIT;
