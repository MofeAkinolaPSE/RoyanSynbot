-- Migration 137: Radiology tables + external tracking for vitals & notes
-- Adds external_source/external_id to royan_vitals and royan_encounter_notes
-- so Hope data extraction scripts are idempotent (ON CONFLICT DO NOTHING).
-- Creates royan_radiology_orders and royan_radiology_results for P3-B.

BEGIN;

-- ── Extend royan_vitals with external source tracking ─────────────────────────
ALTER TABLE public.royan_vitals
    ADD COLUMN IF NOT EXISTS external_source text,
    ADD COLUMN IF NOT EXISTS external_id     text;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'royan_vitals_external_source_external_id_key'
    ) THEN
        ALTER TABLE public.royan_vitals
            ADD CONSTRAINT royan_vitals_external_source_external_id_key
            UNIQUE (external_source, external_id);
    END IF;
END $$;

-- ── Extend royan_encounter_notes with external source tracking ────────────────
ALTER TABLE public.royan_encounter_notes
    ADD COLUMN IF NOT EXISTS external_source text,
    ADD COLUMN IF NOT EXISTS external_id     text;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'royan_encounter_notes_external_source_external_id_key'
    ) THEN
        ALTER TABLE public.royan_encounter_notes
            ADD CONSTRAINT royan_encounter_notes_external_source_external_id_key
            UNIQUE (external_source, external_id);
    END IF;
END $$;

-- ── Radiology orders ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.royan_radiology_orders (
    id                   SERIAL PRIMARY KEY,
    external_source      text,
    external_id          text,
    patient_id           bigint NOT NULL REFERENCES public.royan_patients(id) ON DELETE CASCADE,
    encounter_id         bigint REFERENCES public.royan_encounters(id) ON DELETE SET NULL,
    test_name            text,
    radiology_catalog_id text,
    ordering_doctor      text,
    order_date           date,
    status               text DEFAULT 'ordered',
    created_at           timestamptz DEFAULT now(),
    updated_at           timestamptz DEFAULT now(),
    UNIQUE (external_source, external_id)
);

CREATE INDEX IF NOT EXISTS idx_radiology_orders_patient
    ON public.royan_radiology_orders (patient_id);
CREATE INDEX IF NOT EXISTS idx_radiology_orders_encounter
    ON public.royan_radiology_orders (encounter_id);

-- ── Radiology results ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.royan_radiology_results (
    id           SERIAL PRIMARY KEY,
    order_id     int NOT NULL REFERENCES public.royan_radiology_orders(id) ON DELETE CASCADE,
    report_text  text,
    resulted_by  text,
    resulted_at  timestamptz,
    created_at   timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_radiology_results_order
    ON public.royan_radiology_results (order_id);

COMMIT;
