-- Migration 213: two further seeded lab duplicates
-- ============================================================================
--
-- Migration 212 retired eleven seeded tests. Cross-checking the nine survivors
-- against every Hope test sharing a leading word — rather than only against
-- close name matches — surfaced two more exact duplicates that the earlier
-- comparison missed because the wording differs:
--
--     Urine Culture & Sensitivity  (seeded,  4,000, 0 payer rates)
--       -> URINE CULTURE AND SENSITIVITY (198, 15,000, 72 payer rates)
--          "&" vs "AND" is the only difference, and the seeded copy under-bills
--          by 11,000 with no payer pricing at all.
--
--     Urine Pregnancy Test         (seeded,  1,000, 0 payer rates)
--       -> URINE BETA HCG (PREGNANCY TEST) (150, 1,000, 39 payer rates)
--          Same test, same price; only the Hope entry can be billed to a payer.
--
-- DELIBERATELY NOT RETIRED — these need a lab decision, not a name match
-- ---------------------------------------------------------------------
-- Three seeded tests have Hope entries that are SIMILAR but not obviously the
-- same test. Whether they are interchangeable is a clinical judgement about
-- methodology, which belongs with the lab rather than in a migration:
--
--   Malaria Rapid Test / Malaria Thick Film  vs  MALARIA PARASITE TEST(MP)
--       An antigen RDT and thick-film microscopy are different methods with
--       different sensitivities. Collapsing them would lose that distinction.
--
--   HIV 1&2 Rapid Test  vs  HIV 1 & II SCREENING
--       Plausibly the same thing, but "screening" may mean ELISA here, and
--       Hope also lists ELISA separately.
--
--   Hepatitis C Antibody  vs  HEPATITIS C QUANTITATIVE ANTIBODY /
--                             HEPATITIS C VIRUS SCREEN (QUALITATIVE)
--       Qualitative and quantitative are not substitutes.
--
-- Renal Function Test has no Hope equivalent at all and stays as-is.
-- ============================================================================

BEGIN;

UPDATE public.royan_lab_catalog SET is_active = false, updated_at = now()
WHERE external_source IS NULL AND id IN (
    16,  -- Urine Culture & Sensitivity -> URINE CULTURE AND SENSITIVITY (198)
    19   -- Urine Pregnancy Test        -> URINE BETA HCG (PREGNANCY TEST) (150)
);

COMMIT;

-- Verification:
--   SELECT name, is_active FROM royan_lab_catalog
--   WHERE external_source IS NULL ORDER BY is_active DESC, name;
--   -- expect 7 active: the three method-ambiguous ones, Random Blood Sugar,
--   -- Renal Function Test, Widal Test, Hepatitis C Antibody
