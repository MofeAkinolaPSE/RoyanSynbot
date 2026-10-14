-- Migration 201: retire demo HMOs, record the HMO-code finding, wire departments
-- ============================================================================
--
-- 1. THE DEMO HMOs
-- ----------------
-- royan_hmos holds 7,356 rows. Only 162 are real Royan payers (external_source
-- = 'hope'); the rest arrived with the vendor's demo data and are US insurers --
-- AETNA, BLUE CROSS OF TX, CIGNA -- carrying fake numbers like 8003673636 and
-- contact_email test@drmhope.com.
--
-- The client reported that "all we currently have are just phone numbers" on
-- the HMO dashboard. Those fake numbers are what they were seeing.
--
-- Only 46 of the 7,194 were still active. Deactivating rather than deleting, per
-- the decision taken: verified first that ZERO patient policies and ZERO payer
-- rates reference any of them, so deletion would have been safe -- but a
-- reversible change costs nothing and an irreversible one cannot be undone if a
-- reference is found later.
--
-- 2. HMO CODES DO NOT EXIST IN HOPE
-- ---------------------------------
-- The client asked: "what about the code? So let's check for the code as well."
-- Checked. Hope's tariff_standards table has 170 rows in which ONLY `name` is
-- populated -- payer_id, type, contact, org_ext_id and code_name are empty on
-- every real row. (The one apparently-populated row is a CSV header
-- accidentally imported as data: name='name', type='Type'. It was correctly
-- filtered out before loading and is not present here.)
--
-- So there is no code to import. Codes must be entered by hospital staff, and
-- the UI already supports editing them. Recording this as a column comment so
-- nobody re-runs this hunt.
--
-- 3. DEPARTMENTS
-- --------------
-- royan_departments holds a clean 20-row master, but royan_encounters.department_id
-- is populated on 0 of 313,904 rows while the free-text `department` column has
-- only four distinct values. This backfills the FK from that text so department
-- reporting -- which the client asked for -- has something to group by.
-- ============================================================================

BEGIN;

-- 1. Demo payers out of every dropdown, rows retained.
UPDATE public.royan_hmos
SET is_active = false,
    updated_at = now()
WHERE external_source IS NULL
  AND is_active;

COMMENT ON COLUMN public.royan_hmos.code IS
  'Hospital-assigned payer code. NOT available from Hope: tariff_standards holds names only, with payer_id/type/code_name empty on all 170 rows. Entered by staff.';

-- 3. Departments: map the four real text values onto the master, then backfill.
UPDATE public.royan_encounters e
SET department_id = d.id
FROM public.royan_departments d
WHERE e.department_id IS NULL
  AND e.department IS NOT NULL
  AND (
        (e.department = 'OPD'                     AND d.code = 'OPD')
     OR (e.department = 'Laboratory & Diagnostics' AND d.code = 'LAB')
     OR (e.department = 'Pharmacy'                AND d.code = 'PHARM')
     OR (e.department = 'Billing & Finance'        AND d.code = 'BILLING')
  );

COMMIT;

-- Verification:
--   SELECT count(*) FILTER (WHERE is_active) AS active_hmos,
--          count(*) FILTER (WHERE is_active AND external_source = 'hope') AS active_real
--   FROM royan_hmos;   -- the two should now be equal
--
--   SELECT count(*) FILTER (WHERE department_id IS NOT NULL) AS linked,
--          count(*) FILTER (WHERE department IS NOT NULL)    AS has_text
--   FROM royan_encounters;
