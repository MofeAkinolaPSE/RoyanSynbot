-- ============================================================================
-- 198 — Per-payer service pricing
-- ============================================================================
--
-- WHY
-- ---
-- Migration 188 loaded Hope's tariffs but flattened them: it kept one
-- representative charge per service (the max observed non_nabh_charges) and
-- dropped the payer dimension entirely. Migration 197 therefore gives every HMO
-- the same base price, which is wrong for a hospital whose whole HMO
-- relationship is built on differential rates.
--
-- The payer dimension was not lost, only unread. `pharmacy_tariff_amounts`
-- (91,036 rows) went into royan_hope_reference_archive during the Phase A
-- sweep, and it is exactly the grid: tariff_standard_id x item_rate_id -> mrp.
--
-- WHAT RESOLVES (measured, not estimated)
-- ---------------------------------------
--   110 of 112 payers          resolve to royan_hmos.external_id
--   84,994 of 91,036 rows (93%) resolve to royan_pharmacy_item_rates.external_id
--   Full chain to a service:   82,478 rows / 110 payers / 792 services
--
-- The chain is:
--   pharmacy_tariff_amounts.item_rate_id
--     -> royan_pharmacy_item_rates.external_id
--     -> .formulary_id -> royan_drug_formulary.generic_name
--     -> royan_service_catalog.name
--
-- SCOPE, STATED PLAINLY
-- ---------------------
-- This covers PHARMACY pricing only. Hope's general `tariff_amounts` table was
-- never staged and is not in the archive, so per-payer pricing for consultations,
-- procedures, imaging and ward services cannot be rebuilt from what we hold.
-- Those continue to use royan_service_catalog.base_price for every payer, and
-- the coverage engine falls back to it automatically.
--
-- Recovering the rest means another Hope dump read for `tariff_amounts`.
-- ============================================================================

BEGIN;

CREATE TABLE IF NOT EXISTS public.royan_payer_service_prices (
    id          bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    hmo_id      bigint      NOT NULL REFERENCES public.royan_hmos(id) ON DELETE CASCADE,
    service_id  bigint      NOT NULL REFERENCES public.royan_service_catalog(id) ON DELETE CASCADE,
    price       numeric(14,2) NOT NULL CHECK (price >= 0),
    -- Which Hope stream this came from, so a later general-tariff load can be
    -- told apart from this pharmacy one.
    source      text        NOT NULL DEFAULT 'pharmacy_tariff_amounts',
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (hmo_id, service_id)
);

COMMENT ON TABLE public.royan_payer_service_prices IS
  'Per-HMO price overrides. A missing row means the payer pays royan_service_catalog.base_price.';

CREATE INDEX IF NOT EXISTS idx_payer_service_prices_service
    ON public.royan_payer_service_prices (service_id);

-- Populate. DISTINCT ON keeps the most recently created row per (payer,
-- service): several item_rate rows exist per drug, one per batch, and the
-- latest is the price actually in force.
INSERT INTO public.royan_payer_service_prices (hmo_id, service_id, price, source)
SELECT DISTINCT ON (h.id, sc.id)
    h.id, sc.id, (pt.mrp)::numeric, 'pharmacy_tariff_amounts'
FROM (
    SELECT payload->>'tariff_standard_id' AS std,
           payload->>'item_rate_id'       AS rate,
           payload->>'mrp'                AS mrp,
           payload->>'create_time'        AS created,
           payload->>'is_deleted'         AS deleted
    FROM public.royan_hope_reference_archive
    WHERE source_table = 'pharmacy_tariff_amounts'
) pt
JOIN public.royan_hmos                h  ON h.external_id  = pt.std
JOIN public.royan_pharmacy_item_rates r  ON r.external_id  = pt.rate
JOIN public.royan_drug_formulary      f  ON f.id           = r.formulary_id
JOIN public.royan_service_catalog     sc ON lower(sc.name) = lower(f.generic_name)
WHERE coalesce(pt.deleted, '0') <> '1'
  -- mrp arrives as text and is blank on some rows; only take real numbers.
  AND pt.mrp ~ '^[0-9]+(\.[0-9]+)?$'
  AND (pt.mrp)::numeric > 0
ORDER BY h.id, sc.id, pt.created DESC NULLS LAST
ON CONFLICT (hmo_id, service_id) DO UPDATE
SET price      = EXCLUDED.price,
    source     = EXCLUDED.source,
    updated_at = now();

COMMIT;

-- Verification:
--   SELECT count(*) AS overrides,
--          count(DISTINCT hmo_id) AS payers,
--          count(DISTINCT service_id) AS services
--   FROM royan_payer_service_prices;
--
--   -- Spread for one drug across payers, i.e. proof the dimension is back:
--   SELECT h.name, p.price
--   FROM royan_payer_service_prices p
--   JOIN royan_hmos h ON h.id = p.hmo_id
--   WHERE p.service_id = (SELECT service_id FROM royan_payer_service_prices
--                         GROUP BY service_id ORDER BY count(*) DESC LIMIT 1)
--   ORDER BY p.price DESC LIMIT 10;
