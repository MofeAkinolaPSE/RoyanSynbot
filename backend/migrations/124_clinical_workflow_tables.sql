-- Migration 124: Clinical workflow tables
-- Creates: royan_encounter_notes, royan_vitals, royan_nursing_care_plans,
--          royan_fluid_balance, royan_allergies
-- These are referenced by the queue_clinical, nursing, and consent routers.

ROLLBACK;
BEGIN;

-- ── Encounter Notes ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.royan_encounter_notes (
    id          bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    encounter_id bigint     NOT NULL REFERENCES public.royan_encounters(id) ON DELETE CASCADE,
    patient_id  bigint      NOT NULL REFERENCES public.royan_patients(id) ON DELETE CASCADE,
    note_type   text        NOT NULL DEFAULT 'general'
                            CHECK (note_type IN ('general', 'assessment', 'plan', 'soap', 'progress', 'discharge')),
    content     text        NOT NULL,
    author_id   text,
    author_name text,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_royan_enc_notes_encounter
    ON public.royan_encounter_notes (encounter_id, created_at);
CREATE INDEX IF NOT EXISTS idx_royan_enc_notes_patient
    ON public.royan_encounter_notes (patient_id);

DROP TRIGGER IF EXISTS trg_royan_enc_notes_updated_at ON public.royan_encounter_notes;
CREATE TRIGGER trg_royan_enc_notes_updated_at
    BEFORE UPDATE ON public.royan_encounter_notes
    FOR EACH ROW EXECUTE FUNCTION public.royan_touch_updated_at();


-- ── Vitals ────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.royan_vitals (
    id               bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    patient_id       bigint      NOT NULL REFERENCES public.royan_patients(id) ON DELETE CASCADE,
    encounter_id     bigint      REFERENCES public.royan_encounters(id) ON DELETE SET NULL,
    temperature      numeric(5,2),                         -- Celsius
    pulse            integer,                              -- bpm
    respiratory_rate integer,                              -- breaths/min
    bp_systolic      integer,                              -- mmHg
    bp_diastolic     integer,                              -- mmHg
    spo2             numeric(5,2),                         -- %
    weight           numeric(6,2),                         -- kg
    height           numeric(6,2),                         -- cm
    bmi              numeric(5,2),
    pain_score       integer     CHECK (pain_score >= 0 AND pain_score <= 10),
    gcs              integer     CHECK (gcs >= 3 AND gcs <= 15),
    blood_glucose    numeric(6,2),                         -- mmol/L
    notes            text,
    recorded_by      text,
    recorded_at      timestamptz NOT NULL DEFAULT now(),
    created_at       timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_royan_vitals_patient
    ON public.royan_vitals (patient_id, recorded_at DESC);
CREATE INDEX IF NOT EXISTS idx_royan_vitals_encounter
    ON public.royan_vitals (encounter_id);


-- ── Nursing Care Plans ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.royan_nursing_care_plans (
    id          bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    patient_id  bigint      NOT NULL REFERENCES public.royan_patients(id) ON DELETE CASCADE,
    encounter_id bigint     REFERENCES public.royan_encounters(id) ON DELETE SET NULL,
    problem     text        NOT NULL,
    goal        text,
    interventions text,
    evaluation  text,
    priority    text        NOT NULL DEFAULT 'medium'
                            CHECK (priority IN ('low', 'medium', 'high', 'critical')),
    status      text        NOT NULL DEFAULT 'active'
                            CHECK (status IN ('active', 'resolved', 'deferred', 'discontinued')),
    assigned_to text,
    review_date text,
    created_by  text,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_royan_care_plans_patient
    ON public.royan_nursing_care_plans (patient_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_royan_care_plans_encounter
    ON public.royan_nursing_care_plans (encounter_id);

DROP TRIGGER IF EXISTS trg_royan_care_plans_updated_at ON public.royan_nursing_care_plans;
CREATE TRIGGER trg_royan_care_plans_updated_at
    BEFORE UPDATE ON public.royan_nursing_care_plans
    FOR EACH ROW EXECUTE FUNCTION public.royan_touch_updated_at();


-- ── Fluid Balance ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.royan_fluid_balance (
    id           bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    patient_id   bigint      NOT NULL REFERENCES public.royan_patients(id) ON DELETE CASCADE,
    encounter_id bigint      NOT NULL REFERENCES public.royan_encounters(id) ON DELETE CASCADE,
    fluid_type   text        NOT NULL CHECK (fluid_type IN ('intake', 'output')),
    route        text,                                     -- oral|iv|ng|urine|drain|vomit
    volume_ml    numeric(8,2) NOT NULL CHECK (volume_ml > 0),
    fluid_name   text,
    notes        text,
    recorded_by  text,
    created_at   timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_royan_fluid_encounter
    ON public.royan_fluid_balance (encounter_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_royan_fluid_patient
    ON public.royan_fluid_balance (patient_id);


-- ── Patient Allergies ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.royan_allergies (
    id          bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    patient_id  bigint      NOT NULL REFERENCES public.royan_patients(id) ON DELETE CASCADE,
    allergen    text        NOT NULL,
    reaction    text,
    severity    text        CHECK (severity IN ('mild', 'moderate', 'severe', 'unknown')),
    status      text        NOT NULL DEFAULT 'active'
                            CHECK (status IN ('active', 'inactive', 'resolved')),
    recorded_by text,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_royan_allergies_patient
    ON public.royan_allergies (patient_id);

COMMIT;
