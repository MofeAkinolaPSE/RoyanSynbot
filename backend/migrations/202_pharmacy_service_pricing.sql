-- Migration 202: price the pharmacy half of the service catalogue
-- ============================================================================
--
-- WHY
-- ---
-- royan_service_catalog held 1,221 services with 316 priced. 822 of the 905
-- unpriced are pharmacy -- 91% of the entire pricing gap. Every one of those
-- quotes as N0 through calculate_coverage, which looks like "free" rather than
-- "we do not know".
--
-- The prices were already in the database. royan_pharmacy_item_rates (2,005
-- rows, 1,976 with mrp > 0) carries per-batch pricing for 778 formulary drugs.
-- No dump read was needed for any of this.
--
-- WHY LATEST BATCH, NOT max(mrp)
-- ------------------------------
-- The obvious aggregate is max(). It is wrong, and RANFERON CAP shows why --
-- it has five rates:
--
--     714,286,000,000.00   batch med-262    expired 2017   <- a typo
--                125.00    batch A14        expires 2026
--                 95.00    batch 333        expires 2024
--                 38.00    batch IVES-261   expired 2017
--                 30.00    batch dist-260   expired 2017
--
-- max() picks the typo and prices an iron supplement at N714 billion. The
-- current batch (latest expiry) gives N125, which is the price actually in
-- force. That is what this uses.
--
-- A blanket price cap would have been the wrong fix too: Pembrolizumab
-- (Keytruda) at N2,400,000 and Bevacizumab at N645,100 are REAL oncology
-- prices, not errors, and a cap low enough to catch the typos would have
-- discarded them.
--
-- TWO ROWS DELIBERATELY EXCLUDED
-- ------------------------------
--   GLOVE STERILE 7.5                 N10,001,000  -- single rate, no sane
--                                                     alternative to fall back
--                                                     to; a typo we cannot fix
--   LEVAMISOLE TAB (KETRAX) 47.2MG    N0.20        -- below any plausible price
--
-- Left unpriced rather than loaded wrong. An absent price prompts someone to
-- enter one; a wrong price bills a patient.
-- ============================================================================

BEGIN;

WITH current_rate AS (
    -- One rate per drug: the batch with the furthest expiry is the one in
    -- force. id DESC breaks ties for rows with no expiry recorded.
    SELECT DISTINCT ON (formulary_id)
           formulary_id, mrp
    FROM public.royan_pharmacy_item_rates
    WHERE mrp > 0 AND formulary_id IS NOT NULL
    ORDER BY formulary_id, expiry_date DESC NULLS LAST, id DESC
),
matched AS (
    SELECT s.id AS service_id, r.mrp
    FROM public.royan_service_catalog s
    JOIN public.royan_drug_formulary f
      ON lower(btrim(s.name)) IN (
             lower(btrim(f.generic_name)),
             lower(btrim(coalesce(f.brand_name, '')))
         )
    JOIN current_rate r ON r.formulary_id = f.id
    WHERE s.category = 'pharmacy'
      AND coalesce(s.base_price, 0) = 0
      -- The two outliers above. Not a general cap: N5m keeps real oncology
      -- pricing (Keytruda N2.4m) while excluding the N10m glove.
      AND r.mrp >= 1
      AND r.mrp <= 5000000
)
UPDATE public.royan_service_catalog s
SET base_price = m.mrp,
    updated_at = now()
FROM matched m
WHERE s.id = m.service_id;

COMMIT;

-- Verification:
--   SELECT category, count(*) AS total, count(*) FILTER (WHERE base_price > 0) AS priced
--   FROM royan_service_catalog GROUP BY category ORDER BY 2 DESC;
--
--   -- Should be ~1,091 of 1,221 priced (89%), up from 316 (26%).
--   -- The ~130 still unpriced are non-drug pharmacy lines (blood products,
--   -- "Prescription Medicine", consumables) with no formulary match, plus the
--   -- two excluded outliers.
