-- 183_allergen_catalog_schema.sql
-- Hope's per-patient allergy tables (drug_allergies/patient_allergies/
-- env_allergies) are all confirmed empty -- no historical allergy events to
-- backfill into royan_allergies. But allergy_masters (18,926 rows) is a
-- real First Databank-style drug-class allergen reference vocabulary
-- (e.g. "ACE Inhibitors", "Acyclovir And Derivatives") -- genuinely useful
-- as an allergen-name autocomplete catalog even though it's not
-- Nigeria/Royan-specific. New lightweight table since royan_allergies
-- itself is a per-patient event table, not a catalog -- wrong shape to
-- reuse.

ROLLBACK;
BEGIN;

CREATE TABLE IF NOT EXISTS public.royan_allergen_catalog (
    id                  bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name                text        NOT NULL,
    concept_type        text,       -- Hope's NAME | BASE | GROUP (drug allergy taxonomy level)
    is_active           boolean     NOT NULL DEFAULT true,
    external_source     text,
    external_id         text,
    external_updated_at timestamptz,
    created_at          timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_royan_allergen_catalog_external
    ON public.royan_allergen_catalog (external_source, external_id)
    WHERE external_source IS NOT NULL AND external_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_royan_allergen_catalog_name ON public.royan_allergen_catalog (lower(name));

COMMIT;
