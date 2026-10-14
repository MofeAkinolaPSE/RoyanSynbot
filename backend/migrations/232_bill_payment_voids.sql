-- =============================================================================
-- Migration 232 - Voiding a receipt or a bill, all the way through
-- =============================================================================
-- A receipt keyed wrongly is voided (with a reason) and the right one recorded;
-- the bill's status is worked out again from the receipts that stand, and Roy
-- Books voids its receipt (reversal, unapplied from the invoice, number given
-- back when it was the last). A bill raised wrongly is voided when nothing is
-- paid on it; Roy Books voids its invoice(s) and the orders it charged can be
-- billed again.
-- =============================================================================
ALTER TABLE royan_payments ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'posted';
ALTER TABLE royan_payments ADD COLUMN IF NOT EXISTS voided_at TIMESTAMPTZ;
ALTER TABLE royan_payments ADD COLUMN IF NOT EXISTS voided_by TEXT;
ALTER TABLE royan_payments ADD COLUMN IF NOT EXISTS void_reason TEXT;
ALTER TABLE royan_billing ADD COLUMN IF NOT EXISTS voided_at TIMESTAMPTZ;
ALTER TABLE royan_billing ADD COLUMN IF NOT EXISTS voided_by TEXT;
ALTER TABLE royan_billing ADD COLUMN IF NOT EXISTS void_reason TEXT;
ALTER TABLE royan_billing DROP CONSTRAINT IF EXISTS royan_billing_status_check;
ALTER TABLE royan_billing ADD CONSTRAINT royan_billing_status_check
    CHECK (status = ANY (ARRAY['pending','partial','paid','waived','disputed','written_off','void']));
