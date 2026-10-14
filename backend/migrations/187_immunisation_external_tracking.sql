-- Migration 187: retarget immunization backfill to the real royan_immunisation table
--
-- Migration 185 created a new royan_immunization_records table without
-- checking for an existing home first. royan_immunisation (migration 148)
-- already exists with an identical shape and is already wired into
-- backend/src/routers/mch_obgyn.py's log_immunisation/get_immunisation_history
-- endpoints (dead code today for lack of data, not for lack of a table).
-- Dropping the duplicate (still empty, nothing lost) and retrofitting the
-- real table with external tracking instead -- same pattern already used
-- for royan_diagnosis_catalog (migration 180) and royan_lab_results
-- (migration 177).

BEGIN;

DROP TABLE IF EXISTS public.royan_immunization_records;

ALTER TABLE public.royan_immunisation
    ADD COLUMN IF NOT EXISTS external_source text,
    ADD COLUMN IF NOT EXISTS external_id     text;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'royan_immunisation_external_source_external_id_key'
    ) THEN
        ALTER TABLE public.royan_immunisation
            ADD CONSTRAINT royan_immunisation_external_source_external_id_key
            UNIQUE (external_source, external_id);
    END IF;
END $$;

COMMIT;
