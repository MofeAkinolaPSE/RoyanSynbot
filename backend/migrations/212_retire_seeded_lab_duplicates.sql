-- Migration 212: retire seeded lab tests that duplicate a real Hope test
-- ============================================================================
--
-- royan_lab_catalog holds 288 tests: 268 migrated from Hope and 20 hand-seeded
-- during early development. Ten of the seeded ones duplicate a Hope test that
-- carries the real, negotiated pricing.
--
-- WHY THIS MATTERS BEYOND TIDINESS
-- --------------------------------
-- The seeded copies are cheaper and carry NO payer rates, so ordering the wrong
-- one under-bills:
--
--     Liver Function Test        seeded  5,000   Hope 15,000  (85 payer rates)
--     Prostate Specific Antigen  seeded  5,000   Hope 28,500  (payer rates)
--     C-Reactive Protein         seeded  3,000   Hope 14,000  (payer rates)
--     Lipid Profile              seeded  5,000   Hope 14,500  (payer rates)
--
-- Two entries also split a test's history: a patient's LFTs land under whichever
-- entry the clinician happened to pick, so neither shows the full series.
--
-- DEACTIVATED, NOT DELETED
-- ------------------------
-- Orders already reference these by NAME (royan_lab_orders.catalog_id is null on
-- all 203,525 rows), so deleting would orphan nothing structurally but would
-- erase the row a historical order's name still points at. is_active = false
-- removes them from every picker while leaving the record intact.
--
-- TWO SEEDED TESTS DELIBERATELY KEPT
-- ----------------------------------
-- An automated "retire anything with a similar Hope name" rule got both wrong,
-- which is why this migration lists each retirement explicitly instead:
--
--   Random Blood Sugar — Hope has only TIMED variants ("@ 3am",
--     "@ 12 MID-NIGHT"). Retiring the general test would leave the lab unable
--     to order an ordinary random blood sugar, which is the common case.
--
--   Widal Test — Hope has only panels ("FBC/MP/ WIDAL", "MALARIA AND WIDAL"),
--     no standalone Widal. It also carries 640 orders of its own.
--
-- Blood Group & Genotype is superseded by BLOOD GROUP AND GENOTYPE (id 21), not
-- by BLOOD GROUP (id 181) — the shorter name drops the genotype half, and a
-- name-similarity rule preferred it because it had more payer rates.
-- ============================================================================

BEGIN;

UPDATE public.royan_lab_catalog SET is_active = false, updated_at = now()
WHERE external_source IS NULL AND id IN (
     1,  -- Full Blood Count            -> FBC (184, 87 payer rates)
     2,  -- Packed Cell Volume          -> PACKED CELL VOLUME (PCV) (132)
     3,  -- Blood Group & Genotype      -> BLOOD GROUP AND GENOTYPE (21, 58 rates)
     7,  -- Hepatitis B Surface Antigen -> HEPATITIS B SURFACE ANTIGEN (115, 88)
    10,  -- Fasting Blood Sugar         -> FASTING BLOOD SUGAR (33, 84)
    12,  -- Liver Function Test         -> LIVER FUNCTION TEST (80, 85)
    14,  -- Lipid Profile               -> LIPID PROFILE (CHOLESTEROL...) (27)
    15,  -- Urinalysis                  -> URINALYSIS (147, 86)
    17,  -- C-Reactive Protein          -> C-Reactive Proteins (Quantitative) (99)
    18,  -- Prostate Specific Antigen   -> Prostate Specific Antigen (PSA) (37)
    20   -- Troponin I                  -> Troponin I (SERUM) (143)
);

COMMIT;

-- Verification:
--   SELECT count(*) FILTER (WHERE is_active) AS active,
--          count(*) FILTER (WHERE NOT is_active) AS retired
--   FROM royan_lab_catalog WHERE external_source IS NULL;
--   -- expect 9 active (incl. Random Blood Sugar and Widal Test), 11 retired
--
--   -- every retired test must still have a live equivalent to order instead:
--   SELECT name FROM royan_lab_catalog WHERE NOT is_active;
