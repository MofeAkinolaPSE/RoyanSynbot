-- 178_hmo_external_tracking.sql
-- royan_hmos had no external_source/external_id, and its existing 7,194 rows
-- turned out to be vendor demo/seed data (Medicare/Medicaid-style US payer
-- names, all created at one identical timestamp) with zero real patient or
-- billing references -- confirmed via direct query before this migration
-- was written. This adds the standard external tracking pair so the real
-- Hope payer list (tariff_standards, ~161 usable rows: MANSARD, IHMS, etc.)
-- can be loaded idempotently, matching every other Hope-sourced table.

ROLLBACK;
BEGIN;

ALTER TABLE public.royan_hmos
    ADD COLUMN IF NOT EXISTS external_source     text,
    ADD COLUMN IF NOT EXISTS external_id         text,
    ADD COLUMN IF NOT EXISTS external_updated_at timestamptz;

CREATE UNIQUE INDEX IF NOT EXISTS uq_royan_hmos_external
    ON public.royan_hmos (external_source, external_id)
    WHERE external_source IS NOT NULL AND external_id IS NOT NULL;

COMMIT;
