-- Migration 161: Laboratory Workspace — schema-drift fixes + amendment trail
--
-- Two confirmed live-DB bugs fixed here (checked directly against the
-- running Postgres instance, not just the migration files):
--   1. royan_lab_orders_status_check never included 'sent_out', even though
--      POST /lab/orders/{id}/send-out sets exactly that status — calling it
--      today throws a CHECK violation.
--   2. royan_lab_results has no report_file_url column, yet
--      POST /lab/orders/{id}/report-upload writes to it whenever a result
--      row already exists for the order.
--
-- Also adds the amendment-trail columns needed for the Laboratory Workspace's
-- verify/authenticate step: SHAS-104's rule that authenticated results are
-- immutable — corrections insert a new row referencing the one they
-- supersede, rather than overwriting verified_by/verified_at in place.

ROLLBACK;
BEGIN;

ALTER TABLE public.royan_lab_orders DROP CONSTRAINT IF EXISTS royan_lab_orders_status_check;
ALTER TABLE public.royan_lab_orders
    ADD CONSTRAINT royan_lab_orders_status_check
    CHECK (status IN ('ordered', 'sample_collected', 'processing', 'resulted', 'sent_out', 'cancelled'));

ALTER TABLE public.royan_lab_results ADD COLUMN IF NOT EXISTS report_file_url text;

ALTER TABLE public.royan_lab_results ADD COLUMN IF NOT EXISTS amends_result_id bigint
    REFERENCES public.royan_lab_results (id) ON DELETE SET NULL;
ALTER TABLE public.royan_lab_results ADD COLUMN IF NOT EXISTS amendment_reason text;

COMMIT;
