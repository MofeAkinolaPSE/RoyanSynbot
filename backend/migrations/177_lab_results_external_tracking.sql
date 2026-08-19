-- 177_lab_results_external_tracking.sql
-- royan_lab_results had no external_source/external_id, so a bulk import
-- (Hope's laboratory_hl7_results, ~1M granular per-analyte rows) had no way
-- to upsert idempotently or trace a row back to its Hope origin. Every other
-- Hope-sourced table in this schema already carries this pair; this brings
-- royan_lab_results in line so the HL7 ingest can use the same
-- ON CONFLICT (external_source, external_id) pattern as the rest of the
-- pipeline instead of a fragile insert-once dedup.

ROLLBACK;
BEGIN;

ALTER TABLE public.royan_lab_results
    ADD COLUMN IF NOT EXISTS external_source     text,
    ADD COLUMN IF NOT EXISTS external_id         text,
    ADD COLUMN IF NOT EXISTS external_updated_at timestamptz;

CREATE UNIQUE INDEX IF NOT EXISTS uq_royan_lab_results_external
    ON public.royan_lab_results (external_source, external_id)
    WHERE external_source IS NOT NULL AND external_id IS NOT NULL;

COMMIT;
