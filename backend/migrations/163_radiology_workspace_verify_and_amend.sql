-- Migration 163: Radiology Workspace — verify sign-off + amendment trail
--
-- Unlike Lab, radiology has no physical specimen phase between order and
-- report — report/impression/findings/radiologist_id/reported_at have lived
-- as denormalized columns directly on royan_radiology_orders since migration
-- 139, and there is only ever one *current* report per order. So this adds
-- the verify/amend columns straight onto the order row rather than moving
-- anything into a second table: a JSONB history array is enough to capture
-- prior versions when a verified report is corrected, mirroring what
-- royan_lab_results' amends_result_id/amendment_reason (migration 161) do
-- relationally for Lab. royan_radiology_results (migration 137) has zero
-- references anywhere in the app and stays dead — there's nothing physical
-- to move into it (see the Radiology Workspace plan for the full reasoning).

ROLLBACK;
BEGIN;

ALTER TABLE public.royan_radiology_orders
    ADD COLUMN IF NOT EXISTS verified_by       text,
    ADD COLUMN IF NOT EXISTS verified_at       timestamptz,
    ADD COLUMN IF NOT EXISTS amendment_reason  text,
    ADD COLUMN IF NOT EXISTS report_history    jsonb NOT NULL DEFAULT '[]'::jsonb;

CREATE INDEX IF NOT EXISTS idx_radiology_orders_verified_at
    ON public.royan_radiology_orders (verified_at) WHERE verified_at IS NOT NULL;

COMMIT;
