-- Migration 217: give the radiology catalogue its modality
-- ============================================================================
--
-- royan_radiology_catalog.modality is NULL on all 211 rows. Hope never recorded
-- it, so the column has been empty since the migration.
--
-- That was tolerable while radiology orders always came from a consultation:
-- OpdEncounterPanel infers the modality from the study name at order time. But
-- radiology can now book its own walk-ins, and with the column empty every
-- walk-in study would file as "other" — making the worklist's modality filter
-- useless for exactly the work the department originates itself.
--
-- The rules below are the ones already proven in OpdEncounterPanel, which were
-- tested against all 211 real names (210 inferred, 0 misclassified). Porting
-- them here rather than duplicating them in a second UI means the catalogue
-- carries the answer once and every consumer gets it.
--
-- ORDER IS LOAD-BEARING, for the same reason it is in the frontend:
--
--   * Explicit modality tokens (CT / MRI / MAMMO) are tested FIRST. An earlier
--     version of these rules put ultrasound first with a loose "SCAN ABDOMEN"
--     alternative, which classified "CT SCAN ABDOMEN" as an ultrasound — a
--     wrong modality on a real order.
--
--   * The pathology rule sits BEFORE the -GRAM/-GRAPHY rule, which would
--     otherwise swallow IMMUNOHISTOCHEMISTRY.
--
--   * "CT SCAN GUIDED BIOPSY" is a CT procedure, not a specimen, so the CT
--     token beats the BIOPSY keyword.
--
-- 11 of the 211 entries are actually pathology (pap smear, FNA cytology,
-- immunohistochemistry, HPV). They are not an imaging modality and map to
-- 'other' rather than being forced into one — flagged to Royan separately as
-- something that probably belongs in the lab catalogue.
-- ============================================================================

BEGIN;

UPDATE public.royan_radiology_catalog
SET modality = CASE
    WHEN upper(name) ~ '\mCT\M|CAT SCAN'                           THEN 'ct'
    WHEN upper(name) ~ '\mMRI\M|MAGNETIC RESONANCE'                THEN 'mri'
    WHEN upper(name) ~ 'MAMMO'                                     THEN 'mammography'
    WHEN upper(name) ~ 'ULTRASOUND|\mUSS\M|DOPPLER|SONOGRA'        THEN 'ultrasound'
    WHEN upper(name) ~ '\mECHO\M|ECHOCARDIO'                       THEN 'echo'
    WHEN upper(name) ~ 'E\.?C\.?G\M|E\.?K\.?G\M|ELECTROCARDIO'     THEN 'ecg'
    WHEN upper(name) ~ 'ENDOSCOP|GASTROSCOP|COLONOSCOP'            THEN 'endoscopy'
    -- Pathology, not imaging. Before the -GRAM rule on purpose.
    WHEN upper(name) ~ 'HISTOPATHOLOG|CYTOLOG|PAP SMEAR|IMMUNOHISTOCHEM|\mHPV\M|BIOPSY'
                                                                   THEN 'other'
    WHEN upper(name) ~ 'FLUORO|BARIUM|GASTROGRAFFIN|GASTROGRAPHIN|ENEMA|\mIVU\M|\mHSG\M|[A-Z]OGRAM\M|[A-Z]OGRAPHY\M'
                                                                   THEN 'fluoroscopy'
    WHEN upper(name) ~ 'X-?RAY|\mXR\M|\mCXR\M|RADIOGRAPH|SKELETAL SURVEY'
                                                                   THEN 'xray'
    ELSE modality
END
WHERE modality IS NULL;

COMMIT;

-- Verification:
--   SELECT coalesce(modality,'(still null)') AS modality, count(*)
--   FROM royan_radiology_catalog GROUP BY 1 ORDER BY 2 DESC;
--
--   -- Spot-check the cases the ordering exists to protect:
--   SELECT name, modality FROM royan_radiology_catalog
--   WHERE name ILIKE '%CT SCAN ABDOMEN%'       -- must be ct, not ultrasound
--      OR name ILIKE '%CT SCAN GUIDED BIOPSY%' -- must be ct, not other
--      OR name ILIKE '%IMMUNOHISTOCHEM%';      -- must be other, not fluoroscopy
