-- 105_prescriptions.sql
-- Royan Hospital: Prescriptions and pharmacy dispensing
-- Part of Phase 3 – Hospital Database Schema

ROLLBACK; -- clear any prior aborted transaction
BEGIN;

-- Prescriptions (written by doctor during encounter)
CREATE TABLE IF NOT EXISTS public.royan_prescriptions (
    id              bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    encounter_id    bigint      NOT NULL REFERENCES public.royan_encounters (id) ON DELETE RESTRICT,
    patient_id      bigint      NOT NULL REFERENCES public.royan_patients (id) ON DELETE RESTRICT,
    drug_name       text        NOT NULL,
    drug_code       text,                                   -- formulary code / NAFDAC number
    dosage          text        NOT NULL,                   -- e.g. "500mg"
    frequency       text        NOT NULL,                   -- e.g. "8-hourly", "once daily"
    duration        text,                                   -- e.g. "5 days", "2 weeks"
    route           text        NOT NULL DEFAULT 'oral'
                                CHECK (route IN ('oral', 'iv', 'im', 'topical', 'inhaled', 'sublingual', 'rectal', 'other')),
    quantity        numeric     NOT NULL DEFAULT 1 CHECK (quantity > 0),
    unit            text        NOT NULL DEFAULT 'tablet',  -- tablet, capsule, vial, sachet, etc.
    special_instructions text,
    prescribed_by   text        NOT NULL,                   -- doctor username/id
    prescribed_at   timestamptz NOT NULL DEFAULT now(),
    status          text        NOT NULL DEFAULT 'pending'
                                CHECK (status IN ('pending', 'dispensed', 'partially_dispensed', 'cancelled', 'returned')),
    notes           text
);

-- Dispensing records (one per prescription line dispensed)
CREATE TABLE IF NOT EXISTS public.royan_dispensing (
    id                  bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    prescription_id     bigint      NOT NULL REFERENCES public.royan_prescriptions (id) ON DELETE RESTRICT,
    patient_id          bigint      NOT NULL REFERENCES public.royan_patients (id) ON DELETE RESTRICT,
    drug_name           text        NOT NULL,
    batch_number        text,
    expiry_date         date,
    quantity_dispensed  numeric     NOT NULL CHECK (quantity_dispensed > 0),
    unit                text        NOT NULL DEFAULT 'tablet',
    dispensed_by        text        NOT NULL,               -- pharmacist username/id
    dispensed_at        timestamptz NOT NULL DEFAULT now(),
    unit_cost           numeric     DEFAULT 0,
    total_cost          numeric     GENERATED ALWAYS AS (quantity_dispensed * unit_cost) STORED,
    counselling_given   boolean     NOT NULL DEFAULT false,
    notes               text
);

CREATE INDEX IF NOT EXISTS idx_royan_prescriptions_encounter  ON public.royan_prescriptions (encounter_id);
CREATE INDEX IF NOT EXISTS idx_royan_prescriptions_patient    ON public.royan_prescriptions (patient_id);
CREATE INDEX IF NOT EXISTS idx_royan_prescriptions_status     ON public.royan_prescriptions (status);
CREATE INDEX IF NOT EXISTS idx_royan_dispensing_prescription  ON public.royan_dispensing (prescription_id);
CREATE INDEX IF NOT EXISTS idx_royan_dispensing_patient       ON public.royan_dispensing (patient_id);
CREATE INDEX IF NOT EXISTS idx_royan_dispensing_dispensed_at  ON public.royan_dispensing (dispensed_at DESC);

COMMIT;
