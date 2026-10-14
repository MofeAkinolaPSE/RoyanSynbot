-- Migration 205: front-desk approval gate on prescriptions
-- ============================================================================
--
-- "when a patient is prescribed a particular drug, sometimes front desk needs to
-- approve that drug before it can be dispensed... there will be a pop-up that
-- says request front desk approval, so now all the pharmacy needs to do is push
-- that to the front desk page... once they approve that drug, pharmacy can
-- dispense."
--
-- Modelled as a SEPARATE axis from `status`, not another status value. A
-- prescription's status tracks dispensing progress (pending → dispensed);
-- approval tracks a payment/authorisation decision. They move independently:
-- a prescription can be approved and still undispensed, or dispensed without
-- ever having needed approval. Folding approval into status would make
-- "partially_dispensed and awaiting approval" unrepresentable.
--
-- Default is 'not_required'. Most prescriptions never need this, and a default
-- of 'pending' would freeze every existing prescription behind an approval
-- nobody asked for.
-- ============================================================================

BEGIN;

ALTER TABLE public.royan_prescriptions
    ADD COLUMN IF NOT EXISTS approval_status text NOT NULL DEFAULT 'not_required',
    ADD COLUMN IF NOT EXISTS approval_requested_at  timestamptz,
    ADD COLUMN IF NOT EXISTS approval_requested_by  text,
    ADD COLUMN IF NOT EXISTS approval_decided_at    timestamptz,
    ADD COLUMN IF NOT EXISTS approval_decided_by    text,
    ADD COLUMN IF NOT EXISTS approval_note          text;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'royan_prescriptions_approval_status_check'
    ) THEN
        ALTER TABLE public.royan_prescriptions
            ADD CONSTRAINT royan_prescriptions_approval_status_check
            CHECK (approval_status IN ('not_required', 'pending', 'approved', 'rejected'));
    END IF;
END $$;

COMMENT ON COLUMN public.royan_prescriptions.approval_status IS
  'Front-desk authorisation, independent of dispensing status. not_required (default) | pending | approved | rejected. Pharmacy must not dispense while pending or rejected.';

-- Partial index: the front-desk card only ever asks for the pending ones, and
-- they are a tiny fraction of 258k prescriptions.
CREATE INDEX IF NOT EXISTS idx_prescriptions_approval_pending
    ON public.royan_prescriptions (approval_requested_at DESC)
    WHERE approval_status = 'pending';

COMMIT;

-- Verification:
--   SELECT approval_status, count(*) FROM royan_prescriptions GROUP BY 1;
--   -- expect everything in 'not_required' immediately after this migration
