-- Migration 203: bridge lab and imaging prices into the service catalogue
-- ============================================================================
--
-- royan_lab_catalog is now 281 of 288 priced and royan_radiology_catalog 209 of
-- 211 (migration 200). But royan_service_catalog holds its OWN lab and imaging
-- rows -- duplicates of the same tests -- and those were still at zero: 4 of 40
-- lab, 9 of 31 imaging.
--
-- That split matters because the two catalogues feed different things.
-- calculate_coverage() and the HMO service catalogue read
-- royan_service_catalog; the Laboratory and Radiology worklists read their own.
-- A test priced in one and zero in the other quotes N0 depending on where the
-- question came from, which is worse than being unpriced in both.
--
-- 28 of the 58 unpriced rows match a priced catalogue row by exact name. The
-- other 30 do not and are left alone: fuzzy-matching test names is how a
-- "FULL BLOOD COUNT" ends up billed as a "BLOOD CULTURE".
--
-- The duplication itself is a modelling problem, not a data one, and is
-- recorded in EXTRACTION_FINDINGS.md rather than papered over here.
-- ============================================================================

BEGIN;

UPDATE public.royan_service_catalog s
SET base_price = c.base_price,
    updated_at = now()
FROM public.royan_lab_catalog c
WHERE s.category = 'lab'
  AND coalesce(s.base_price, 0) = 0
  AND c.base_price > 0
  AND lower(btrim(c.name)) = lower(btrim(s.name));

UPDATE public.royan_service_catalog s
SET base_price = c.base_price,
    updated_at = now()
FROM public.royan_radiology_catalog c
WHERE s.category = 'imaging'
  AND coalesce(s.base_price, 0) = 0
  AND c.base_price > 0
  AND lower(btrim(c.name)) = lower(btrim(s.name));

COMMIT;

-- Verification:
--   SELECT category, count(*), count(*) FILTER (WHERE base_price > 0) AS priced
--   FROM royan_service_catalog GROUP BY category ORDER BY 2 DESC;
