-- 180_diagnosis_catalog_external_tracking.sql
-- royan_diagnosis_catalog (130_master_mdm_tables.sql) ships a ~26-row
-- hand-seeded ICD-10 quick-pick list but has no external_source/external_id,
-- so Hope's real coded diagnosis catalog (diagnosis_masters, 184 rows --
-- confirmed via direct sample to be the genuine SNOMED/ICD-linked catalog,
-- not the misleadingly-named 256K-row "diagnoses" table, which turned out
-- to be an unrelated per-appointment TB-screening intake form) had no way
-- to upsert idempotently or dedupe against the existing seed.

ROLLBACK;
BEGIN;

ALTER TABLE public.royan_diagnosis_catalog
    ADD COLUMN IF NOT EXISTS external_source     text,
    ADD COLUMN IF NOT EXISTS external_id         text,
    ADD COLUMN IF NOT EXISTS external_updated_at timestamptz;

CREATE UNIQUE INDEX IF NOT EXISTS uq_royan_diagnosis_catalog_external
    ON public.royan_diagnosis_catalog (external_source, external_id)
    WHERE external_source IS NOT NULL AND external_id IS NOT NULL;

COMMIT;
