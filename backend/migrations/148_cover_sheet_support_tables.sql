-- Migration 148: CPRS Cover Sheet support tables
-- Creates: royan_immunisation, royan_patient_postings, royan_clinical_reminders
--
-- royan_immunisation closes a pre-existing gap: routers/mch_obgyn.py has had a
-- full immunisation CRUD (log_immunisation / get_immunisation_history) since
-- before this migration, referencing TABLE_IMMUNISATION = "royan_immunisation"
-- (constants.py) — but no migration ever created the table, so that endpoint
-- has been dead code. Columns here match ImmunisationRecord exactly.

ROLLBACK;
BEGIN;

-- ── Immunisation ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.royan_immunisation (
    id              bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    patient_id      bigint      NOT NULL REFERENCES public.royan_patients(id) ON DELETE CASCADE,
    vaccine_name    text        NOT NULL,
    dose_number     integer,
    date_given      date        NOT NULL DEFAULT CURRENT_DATE,
    batch_number    text,
    site            text,
    administered_by text,
    next_due_date   date,
    reaction        text,
    notes           text,
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_royan_immunisation_patient
    ON public.royan_immunisation (patient_id, date_given DESC);


-- ── Patient Postings (clinical flags/notices — CPRS "Postings" analog) ───────
CREATE TABLE IF NOT EXISTS public.royan_patient_postings (
    id           bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    patient_id   bigint      NOT NULL REFERENCES public.royan_patients(id) ON DELETE CASCADE,
    posting_type text        NOT NULL DEFAULT 'alert'
                             CHECK (posting_type IN ('alert', 'precaution', 'directive', 'note')),
    message      text        NOT NULL,
    severity     text        NOT NULL DEFAULT 'info'
                             CHECK (severity IN ('info', 'warning', 'critical')),
    created_by   text,
    created_at   timestamptz NOT NULL DEFAULT now(),
    resolved_at  timestamptz,
    resolved_by  text
);

CREATE INDEX IF NOT EXISTS idx_royan_postings_patient
    ON public.royan_patient_postings (patient_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_royan_postings_active
    ON public.royan_patient_postings (patient_id) WHERE resolved_at IS NULL;


-- ── Clinical Reminders (patient-specific due/overdue care-gap alerts) ────────
CREATE TABLE IF NOT EXISTS public.royan_clinical_reminders (
    id           bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    patient_id   bigint      NOT NULL REFERENCES public.royan_patients(id) ON DELETE CASCADE,
    rule_key     text        NOT NULL,
    message      text        NOT NULL,
    due_since    timestamptz,
    severity     text        NOT NULL DEFAULT 'warning'
                             CHECK (severity IN ('info', 'warning', 'critical')),
    dismissed_at timestamptz,
    dismissed_by text,
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now(),
    UNIQUE (patient_id, rule_key)
);

CREATE INDEX IF NOT EXISTS idx_royan_reminders_active
    ON public.royan_clinical_reminders (patient_id) WHERE dismissed_at IS NULL;

DROP TRIGGER IF EXISTS trg_royan_clinical_reminders_updated_at ON public.royan_clinical_reminders;
CREATE TRIGGER trg_royan_clinical_reminders_updated_at
    BEFORE UPDATE ON public.royan_clinical_reminders
    FOR EACH ROW EXECUTE FUNCTION public.royan_touch_updated_at();

COMMIT;
