-- Migration 141: Quarantine non-staff rows contaminating royan_staff
--
-- Investigation (2026-07-03): royan_staff contains ~2,297 rows that are not
-- hospital staff. They carry a "C-N" / "D-N" staff_number pattern (Sage
-- customer/debtor codes, not the "STF-NNN" scheme used by real staff),
-- monthly_gross = 0, no external_source/external_id lineage, and full_name
-- values that are clearly pharma-customer business/PHC names (e.g.
-- "PRECIOUS SPARKVIEW HOSPITAL"). department and designation were both
-- blanket-defaulted to 'General' because the source data (a Sage customer/
-- debtor export) has no such fields — this is what produced the "all staff
-- are General" symptom on the HR workforce dashboard. The importer that
-- wrote these rows is no longer in the codebase, so we cannot repair the
-- data; we quarantine it instead of deleting so it can be reviewed/restored
-- to a proper CRM table later.
--
-- This migration only flags rows matching the contamination fingerprint; it
-- does not touch any row that has real payroll, lineage, or a staff_number
-- outside the C-/D- pattern.

ROLLBACK;
BEGIN;

ALTER TABLE public.royan_staff
    ADD COLUMN IF NOT EXISTS quarantined_at     timestamptz,
    ADD COLUMN IF NOT EXISTS quarantine_reason  text;

CREATE INDEX IF NOT EXISTS idx_royan_staff_quarantined
    ON public.royan_staff (quarantined_at)
    WHERE quarantined_at IS NOT NULL;

UPDATE public.royan_staff
SET is_active          = false,
    quarantined_at      = now(),
    quarantine_reason   = 'Suspected Sage customer/debtor import contamination: '
                          || 'staff_number matches customer-code pattern, department and '
                          || 'designation both defaulted to General, zero payroll, no MDM lineage.'
WHERE quarantined_at IS NULL
  AND department = 'General'
  AND designation = 'General'
  AND monthly_gross = 0
  AND external_source IS NULL
  AND staff_number ~ '^[A-Z]-[0-9]+$';

COMMIT;
