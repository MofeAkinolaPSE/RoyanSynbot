-- Migration 199: external tracking on royan_patient_insurance
--
-- WHY
-- ---
-- The client asked about insurance numbers in BOTH staff meetings ("check the
-- database to find out any insurance numbers that are there", "currently there
-- are no insurance numbers being displayed on the HMO dashboard").
--
-- royan_patient_insurance has 0 rows. The data exists: Hope's `new_insurances`
-- (162,991 rows) was extracted months ago and never loaded. It deduplicates to
-- 21,776 (patient, payer) pairs carrying a real membership number across 18,126
-- patients -- values like MH/CONOIL/086/G-C.
--
-- Same retrofit pattern already used for royan_lab_results (177), royan_hmos
-- (178) and royan_immunisation (187).
--
-- A NOTE ON THE PRIMARY-POLICY INDEX
-- ----------------------------------
-- uq_royan_patient_insurance_primary permits ONE primary active policy per
-- patient. Hope has ~4 historical revisions per patient and `priority` is the
-- literal 'P' on all 162,991 rows, so it cannot pick a winner. The loader
-- therefore marks exactly one row primary per patient (highest Hope id = most
-- recent) and loads the rest as non-primary history. The index is left intact
-- deliberately: it is the thing that would catch a loader bug here.
-- ============================================================================

BEGIN;

ALTER TABLE public.royan_patient_insurance
    ADD COLUMN IF NOT EXISTS external_source text,
    ADD COLUMN IF NOT EXISTS external_id     text;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'royan_patient_insurance_external_source_external_id_key'
    ) THEN
        ALTER TABLE public.royan_patient_insurance
            ADD CONSTRAINT royan_patient_insurance_external_source_external_id_key
            UNIQUE (external_source, external_id);
    END IF;
END $$;

COMMENT ON COLUMN public.royan_patient_insurance.external_source IS
  'Legacy system this row came from (hope), NULL for policies created in Synbot.';

-- The HMO dashboard and the OPD queue both look a patient up by membership
-- number, and neither has an index for it today.
CREATE INDEX IF NOT EXISTS idx_royan_patient_insurance_membership
    ON public.royan_patient_insurance (membership_id);

COMMIT;

-- Verification:
--   SELECT count(*) FILTER (WHERE external_source = 'hope') AS from_hope,
--          count(DISTINCT patient_id) AS patients,
--          count(*) FILTER (WHERE is_primary) AS primaries
--   FROM royan_patient_insurance;
--   -- primaries must equal patients, or the loader broke the one-primary rule.
