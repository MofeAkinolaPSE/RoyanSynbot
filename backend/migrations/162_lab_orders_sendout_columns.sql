-- Migration 162: royan_lab_orders send-out columns
--
-- Confirmed live-DB bug found while smoke-testing the Laboratory Workspace
-- pass: POST /lab/orders/{id}/send-out has always written external_lab and
-- sent_out_at onto royan_lab_orders, and Laboratory.tsx has always read them
-- back — but neither column exists on the live table. Every send-out call
-- has been throwing a 500 (UndefinedColumn) since this endpoint was built.

ROLLBACK;
BEGIN;

ALTER TABLE public.royan_lab_orders ADD COLUMN IF NOT EXISTS external_lab text;
ALTER TABLE public.royan_lab_orders ADD COLUMN IF NOT EXISTS sent_out_at timestamptz;

COMMIT;
