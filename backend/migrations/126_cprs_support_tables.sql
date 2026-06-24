-- Migration 126: CPRS support tables
-- Creates: royan_consent_records, royan_icd10_codes, royan_problem_list,
--          royan_mar_entries, royan_replenishment_requests
-- Also: adds recorded_at to royan_fluid_balance (fluid-balance GET orders by it)

ROLLBACK;
BEGIN;

-- ── Fix: fluid_balance missing recorded_at column ─────────────────────────────
ALTER TABLE public.royan_fluid_balance
    ADD COLUMN IF NOT EXISTS recorded_at timestamptz NOT NULL DEFAULT now();


-- ── Consent Records ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.royan_consent_records (
    id           bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    patient_id   bigint      NOT NULL REFERENCES public.royan_patients(id) ON DELETE CASCADE,
    encounter_id bigint      REFERENCES public.royan_encounters(id) ON DELETE SET NULL,
    consent_type text        NOT NULL DEFAULT 'general_treatment',
    consented    boolean     NOT NULL DEFAULT true,
    signed_at    timestamptz NOT NULL DEFAULT now(),
    captured_by  text,
    notes        text,
    witness_name text,
    created_at   timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_royan_consent_patient
    ON public.royan_consent_records (patient_id, signed_at DESC);


-- ── ICD-10 Codes ──────────────────────────────────────────────────────────────
-- Empty table — to be seeded with ICD-10 data separately
CREATE TABLE IF NOT EXISTS public.royan_icd10_codes (
    id          bigint  GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code        text    NOT NULL UNIQUE,
    description text    NOT NULL,
    category    text,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_royan_icd10_code
    ON public.royan_icd10_codes (code);
CREATE INDEX IF NOT EXISTS idx_royan_icd10_desc
    ON public.royan_icd10_codes USING gin (to_tsvector('english', description));


-- ── Problem List ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.royan_problem_list (
    id           bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    patient_id   bigint      NOT NULL REFERENCES public.royan_patients(id) ON DELETE CASCADE,
    encounter_id bigint      REFERENCES public.royan_encounters(id) ON DELETE SET NULL,
    icd10_code   text,
    description  text        NOT NULL,
    onset_date   text,
    status       text        NOT NULL DEFAULT 'active'
                             CHECK (status IN ('active', 'resolved', 'inactive', 'chronic')),
    noted_by     text,
    resolved_at  timestamptz,
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_royan_problems_patient
    ON public.royan_problem_list (patient_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_royan_problems_status
    ON public.royan_problem_list (patient_id, status);

DROP TRIGGER IF EXISTS trg_royan_problem_list_updated_at ON public.royan_problem_list;
CREATE TRIGGER trg_royan_problem_list_updated_at
    BEFORE UPDATE ON public.royan_problem_list
    FOR EACH ROW EXECUTE FUNCTION public.royan_touch_updated_at();


-- ── MAR Entries (Medication Administration Record) ────────────────────────────
CREATE TABLE IF NOT EXISTS public.royan_mar_entries (
    id               bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    encounter_id     bigint      NOT NULL REFERENCES public.royan_encounters(id) ON DELETE CASCADE,
    patient_id       bigint      NOT NULL REFERENCES public.royan_patients(id) ON DELETE CASCADE,
    prescription_id  bigint      REFERENCES public.royan_prescriptions(id) ON DELETE SET NULL,
    drug_name        text        NOT NULL,
    dose             text,
    route            text,
    scheduled_time   text,
    administered_at  text,
    status           text        NOT NULL DEFAULT 'administered'
                                 CHECK (status IN ('scheduled', 'administered', 'held', 'missed', 'refused')),
    notes            text,
    override_reason  text,
    administered_by  text,
    created_at       timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_royan_mar_encounter
    ON public.royan_mar_entries (encounter_id);
CREATE INDEX IF NOT EXISTS idx_royan_mar_patient
    ON public.royan_mar_entries (patient_id);


-- ── Replenishment Requests (inventory workflow) ───────────────────────────────
CREATE TABLE IF NOT EXISTS public.royan_replenishment_requests (
    id            bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku           text        NOT NULL,
    requested_qty numeric     NOT NULL DEFAULT 0,
    status        text        NOT NULL DEFAULT 'recommended'
                              CHECK (status IN ('recommended', 'approved', 'ordered', 'received', 'cancelled')),
    created_by    text,
    notes         text,
    approved_by   text,
    approved_at   timestamptz,
    fulfilled_at  timestamptz,
    created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_royan_replenish_sku_status
    ON public.royan_replenishment_requests (sku, status);

-- Also create replenishment_requests alias (used by workflow/automation.py without prefix)
CREATE TABLE IF NOT EXISTS public.replenishment_requests (
    id            bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku           text        NOT NULL,
    requested_qty numeric     NOT NULL DEFAULT 0,
    status        text        NOT NULL DEFAULT 'recommended',
    created_by    text,
    notes         text,
    created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_replenish_sku_status
    ON public.replenishment_requests (sku, status);

COMMIT;
