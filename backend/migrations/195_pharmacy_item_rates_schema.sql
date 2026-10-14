-- Migration 195: Pharmacy per-batch pricing (mrp / cost / sale)
--
-- Pulled in at the user's explicit request ("Pull that in as well. We might
-- need it later") after being flagged as the one deliberate loose end.
--
-- Hope's `pharmacy_item_rates` (2,006 rows) turned out richer than the
-- tariff-resolution errand that prompted it: each row carries a real
-- per-batch pricing set -- mrp, purchase_price, cost_price, sale_price --
-- plus batch_number, expiry_date and stock, with item_id resolving
-- 855/855 (100%) against the loaded royan_drug_formulary.
--
-- royan_inventory_batches (migration 174) was considered as the target but
-- only has a single `unit_cost` column -- it has nowhere to put mrp /
-- sale_price / cost_price, which is the whole point of this data. A
-- dedicated table keeps the full margin picture instead of discarding
-- three of the four price points.
--
-- NOTE on the original errand: `pharmacy_tariff_amounts` (91,036 rows, the
-- per-payer MRP grid) references 5,883 distinct item_rate_ids, of which
-- only 2,004 (34%) exist in pharmacy_item_rates -- the rest were purged
-- from Hope before this dump. That table therefore goes to the reference
-- archive rather than a resolved schema; the 34% that do resolve can be
-- joined through this table when needed.

BEGIN;

CREATE TABLE IF NOT EXISTS public.royan_pharmacy_item_rates (
    id                bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    formulary_id      bigint      REFERENCES public.royan_drug_formulary (id) ON DELETE SET NULL,
    item_ref          text,
    batch_number      text,
    expiry_date       date,
    mrp               numeric(14,2),   -- maximum retail price
    purchase_price    numeric(14,2),   -- what Royan paid
    cost_price        numeric(14,2),
    sale_price        numeric(14,2),
    stock             numeric(12,2),
    loose_stock       numeric(12,2),
    vat_class_name    text,
    is_active         boolean     NOT NULL DEFAULT true,
    external_source   text,
    external_id       text,
    created_at        timestamptz NOT NULL DEFAULT now()
);

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='royan_pharmacy_item_rates_ext_key') THEN
        ALTER TABLE public.royan_pharmacy_item_rates
            ADD CONSTRAINT royan_pharmacy_item_rates_ext_key UNIQUE (external_source, external_id);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_royan_pharmacy_item_rates_formulary
    ON public.royan_pharmacy_item_rates (formulary_id);
CREATE INDEX IF NOT EXISTS idx_royan_pharmacy_item_rates_expiry
    ON public.royan_pharmacy_item_rates (expiry_date);

COMMIT;
