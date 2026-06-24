-- 128_compensating_external_columns.sql
-- Idempotent catch-up migration for databases where 114 and 115 were not applied.
-- Adds external_source/external_id/external_updated_at columns to all hospital
-- tables, creates royan_hope_sync_runs, and adds the ingest_mode column.
-- Safe to run even if the migrations were already applied (IF NOT EXISTS everywhere).

BEGIN;

-- ── royan_patients ────────────────────────────────────────────────────────────
ALTER TABLE public.royan_patients
    ADD COLUMN IF NOT EXISTS external_source     text,
    ADD COLUMN IF NOT EXISTS external_id         text,
    ADD COLUMN IF NOT EXISTS external_updated_at timestamptz;

CREATE UNIQUE INDEX IF NOT EXISTS uq_royan_patients_external
    ON public.royan_patients (external_source, external_id)
    WHERE external_source IS NOT NULL AND external_id IS NOT NULL;

-- ── royan_encounters ─────────────────────────────────────────────────────────
ALTER TABLE public.royan_encounters
    ADD COLUMN IF NOT EXISTS external_source     text,
    ADD COLUMN IF NOT EXISTS external_id         text,
    ADD COLUMN IF NOT EXISTS external_updated_at timestamptz;

CREATE UNIQUE INDEX IF NOT EXISTS uq_royan_encounters_external
    ON public.royan_encounters (external_source, external_id)
    WHERE external_source IS NOT NULL AND external_id IS NOT NULL;

-- ── royan_lab_orders ─────────────────────────────────────────────────────────
ALTER TABLE public.royan_lab_orders
    ADD COLUMN IF NOT EXISTS external_source     text,
    ADD COLUMN IF NOT EXISTS external_id         text,
    ADD COLUMN IF NOT EXISTS external_updated_at timestamptz;

CREATE UNIQUE INDEX IF NOT EXISTS uq_royan_lab_orders_external
    ON public.royan_lab_orders (external_source, external_id)
    WHERE external_source IS NOT NULL AND external_id IS NOT NULL;

-- ── royan_prescriptions ──────────────────────────────────────────────────────
ALTER TABLE public.royan_prescriptions
    ADD COLUMN IF NOT EXISTS external_source     text,
    ADD COLUMN IF NOT EXISTS external_id         text,
    ADD COLUMN IF NOT EXISTS external_updated_at timestamptz;

CREATE UNIQUE INDEX IF NOT EXISTS uq_royan_prescriptions_external
    ON public.royan_prescriptions (external_source, external_id)
    WHERE external_source IS NOT NULL AND external_id IS NOT NULL;

-- ── royan_billing ────────────────────────────────────────────────────────────
ALTER TABLE public.royan_billing
    ADD COLUMN IF NOT EXISTS external_source     text,
    ADD COLUMN IF NOT EXISTS external_id         text,
    ADD COLUMN IF NOT EXISTS external_updated_at timestamptz;

CREATE UNIQUE INDEX IF NOT EXISTS uq_royan_billing_external
    ON public.royan_billing (external_source, external_id)
    WHERE external_source IS NOT NULL AND external_id IS NOT NULL;

-- ── royan_appointments ───────────────────────────────────────────────────────
ALTER TABLE public.royan_appointments
    ADD COLUMN IF NOT EXISTS external_source     text,
    ADD COLUMN IF NOT EXISTS external_id         text,
    ADD COLUMN IF NOT EXISTS external_updated_at timestamptz;

CREATE UNIQUE INDEX IF NOT EXISTS uq_royan_appointments_external
    ON public.royan_appointments (external_source, external_id)
    WHERE external_source IS NOT NULL AND external_id IS NOT NULL;

-- ── royan_appointment_slots ──────────────────────────────────────────────────
ALTER TABLE public.royan_appointment_slots
    ADD COLUMN IF NOT EXISTS external_source     text,
    ADD COLUMN IF NOT EXISTS external_id         text,
    ADD COLUMN IF NOT EXISTS external_updated_at timestamptz;

CREATE UNIQUE INDEX IF NOT EXISTS uq_royan_appointment_slots_external
    ON public.royan_appointment_slots (external_source, external_id)
    WHERE external_source IS NOT NULL AND external_id IS NOT NULL;

-- ── royan_hope_sync_runs (migration 114) ─────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.royan_hope_sync_runs (
    id              bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    entity          text        NOT NULL,
    status          text        NOT NULL CHECK (status IN ('started', 'success', 'failed')),
    started_at      timestamptz NOT NULL DEFAULT now(),
    completed_at    timestamptz,
    rows_seen       int         NOT NULL DEFAULT 0,
    rows_upserted   int         NOT NULL DEFAULT 0,
    error_message   text,
    metadata        jsonb       NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_royan_hope_sync_runs_entity
    ON public.royan_hope_sync_runs (entity, started_at DESC);

-- ── ingest_mode column (migration 115) ───────────────────────────────────────
ALTER TABLE public.royan_hope_sync_runs
    ADD COLUMN IF NOT EXISTS ingest_mode text
        CHECK (ingest_mode IN ('bulk_import', 'live_bridge'))
        DEFAULT 'live_bridge';

COMMIT;
