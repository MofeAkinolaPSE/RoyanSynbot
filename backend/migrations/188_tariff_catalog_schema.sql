-- Migration 188: real service tariff/price catalog
--
-- Complete-506-table Hope dump audit (2026-08-21): Hope's `tariff_lists`
-- (434 real rows -- service names/categories) and `tariff_amounts` (56,732
-- rows -- pricing) were never extracted. tariff_amounts.cost_price (the
-- literal "unit cost" field, hoped to directly answer the original billing
-- question from earlier this session) turned out to be populated on only
-- 870/56,732 rows (1.5%) -- real where present, but too sparse to be the
-- primary signal. non_nabh_charges (24,281/56,732 populated) is the far
-- more complete real pricing signal and is what this catalog is built on.
--
-- tariff_amounts.tariff_standard_id is a per-payer pricing grid FK into the
-- same tariff_standards table already loaded into royan_hmos earlier this
-- project (see transformers/hmo.py) -- i.e. this is "price of service X
-- under payer Y's schedule", not a single flat price. Modeling the full
-- payer-specific grid is out of scope for this pass; one representative
-- charge_amount per service (max observed non_nabh_charges) is kept
-- instead, with cost_price carried through where Hope did populate it.

BEGIN;

CREATE TABLE IF NOT EXISTS public.royan_tariff_catalog (
    id              bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name            text        NOT NULL,
    service_group   text,
    service_type    text,
    charge_amount   numeric(14,2),
    cost_price      numeric(14,2),
    is_active       boolean     NOT NULL DEFAULT true,
    external_source text,
    external_id     text,
    created_at      timestamptz NOT NULL DEFAULT now()
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'royan_tariff_catalog_external_source_external_id_key'
    ) THEN
        ALTER TABLE public.royan_tariff_catalog
            ADD CONSTRAINT royan_tariff_catalog_external_source_external_id_key
            UNIQUE (external_source, external_id);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_royan_tariff_catalog_name ON public.royan_tariff_catalog (lower(name));

COMMIT;
