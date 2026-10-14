-- Migration 200: price lab and radiology, and make payer pricing polymorphic
-- ============================================================================
--
-- WHAT THE FINAL DUMP PASS ACTUALLY ESTABLISHED
-- ---------------------------------------------
-- The hypothesis going in was that `tariff_lists` had been truncated (434 rows
-- staged against 1,578 referenced). A full re-read of the 654 MB dump returned
-- 434 rows again: the table was never truncated. That hypothesis was wrong.
--
-- But the rows that would not resolve were is_deleted='0' with create_times as
-- recent as the ones that did, which does not fit "references deleted services"
-- either. Testing further showed why:
--
--   tariff_amounts.tariff_list_id IS POLYMORPHIC, keyed by service_category_id
--
--     category 3  (Radiology) -> radiologies.id    7,519 rows, 100% resolve
--     category 26 (Laboratory)-> laboratories.id   9,584 rows,  74% resolve
--     everything else         -> tariff_lists.id   6,872 rows
--
-- Resolution therefore goes from 6,872 (28%) to 21,463 of 24,273 (88%),
-- covering 113 payers and 807 services -- without extracting a single new row.
--
-- BASE PRICE NOW MEANS SOMETHING
-- ------------------------------
-- Migration 188 used "the max observed non_nabh_charges" as the list price
-- because the payer dimension had been flattened. Hope actually has an explicit
-- self-pay tariff: tariff_standard_id = 7, "Private". That is the real list
-- price, and it is what this migration uses -- 247 of 271 lab tests and 334 of
-- 434 general services carry one.
--
-- Radiology has NO Private row at all (0 of 211), so its base price cannot be
-- sourced the same way. It is left to the loader, which uses the modal price
-- across payers and records that it did so. Inventing a Private price that Hope
-- never recorded would be worse than an honest approximation.
-- ============================================================================

BEGIN;

-- Radiology had no price column anywhere; the client asked to see study costs.
ALTER TABLE public.royan_radiology_catalog
    ADD COLUMN IF NOT EXISTS base_price numeric(14,2);

COMMENT ON COLUMN public.royan_radiology_catalog.base_price IS
  'Representative list price. Hope holds no Private (self-pay) tariff for radiology, so this is the modal price across payers, not an exact list price.';

-- ---------------------------------------------------------------------------
-- royan_payer_service_prices becomes polymorphic, mirroring Hope.
--
-- Lab tests and radiology studies live in their own catalogues, not in
-- royan_service_catalog, so a single service_id FK cannot express their payer
-- rates. Rather than duplicate ~500 catalogue rows into service_catalog purely
-- to hang a price on them -- which would leave two competing definitions of the
-- same test -- the price table points at whichever catalogue owns the row.
-- ---------------------------------------------------------------------------
ALTER TABLE public.royan_payer_service_prices
    ADD COLUMN IF NOT EXISTS lab_catalog_id       bigint REFERENCES public.royan_lab_catalog(id) ON DELETE CASCADE,
    ADD COLUMN IF NOT EXISTS radiology_catalog_id bigint REFERENCES public.royan_radiology_catalog(id) ON DELETE CASCADE;

-- service_id was NOT NULL; it must now be optional so the other two can be used.
ALTER TABLE public.royan_payer_service_prices
    ALTER COLUMN service_id DROP NOT NULL;

-- The old UNIQUE (hmo_id, service_id) cannot express the other two targets.
ALTER TABLE public.royan_payer_service_prices
    DROP CONSTRAINT IF EXISTS royan_payer_service_prices_hmo_id_service_id_key;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'royan_payer_service_prices_one_target'
    ) THEN
        ALTER TABLE public.royan_payer_service_prices
            ADD CONSTRAINT royan_payer_service_prices_one_target
            CHECK (num_nonnulls(service_id, lab_catalog_id, radiology_catalog_id) = 1);
    END IF;
END $$;

-- One rate per payer per target, enforced per target kind.
CREATE UNIQUE INDEX IF NOT EXISTS uq_payer_price_service
    ON public.royan_payer_service_prices (hmo_id, service_id)   WHERE service_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_payer_price_lab
    ON public.royan_payer_service_prices (hmo_id, lab_catalog_id) WHERE lab_catalog_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_payer_price_radiology
    ON public.royan_payer_service_prices (hmo_id, radiology_catalog_id) WHERE radiology_catalog_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_payer_price_lab_target
    ON public.royan_payer_service_prices (lab_catalog_id) WHERE lab_catalog_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_payer_price_rad_target
    ON public.royan_payer_service_prices (radiology_catalog_id) WHERE radiology_catalog_id IS NOT NULL;

COMMIT;

-- Verification:
--   SELECT source,
--          count(*) FILTER (WHERE service_id IS NOT NULL)           AS service_rates,
--          count(*) FILTER (WHERE lab_catalog_id IS NOT NULL)       AS lab_rates,
--          count(*) FILTER (WHERE radiology_catalog_id IS NOT NULL) AS radiology_rates
--   FROM royan_payer_service_prices GROUP BY source;
--
--   SELECT count(*) FILTER (WHERE base_price > 0) AS priced, count(*) FROM royan_lab_catalog;
