-- Migration 207: discount approval workflow, and receipt numbers
-- ============================================================================
--
-- 1. DISCOUNTS NEED A SECOND PAIR OF EYES
-- ---------------------------------------
-- "the cashier can add a discount and then admin can then confirm or reject
-- that discount. So admin will have a UI card in their dashboard that shows
-- them that there is a new discount waiting for approval."
--
-- royan_billing already had a `discount` column, but nothing recorded WHO
-- applied it, WHY, or whether anyone agreed. A cashier could discount any bill
-- to zero and nothing would ever surface it.
--
-- Modelled as a separate axis from bill `status`, for the same reason
-- prescription approval was: a bill can be pending payment AND have an approved
-- discount, or be part-paid with a discount still under review. Folding the two
-- together would make those states unrepresentable.
--
-- Default 'none' rather than 'pending': the overwhelming majority of bills carry
-- no discount, and defaulting to pending would put every historical bill on the
-- admin's approval queue.
--
-- 2. RECEIPTS ARE NOT INVOICES
-- ----------------------------
-- "the receipt number should be auto-generated and should be printable, so it
-- prints the receipts and not just the invoice."
--
-- royan_payments had `reference` — a free-text field for the payer's own
-- reference (a transfer ref, a POS slip number). That is the payer's number,
-- not ours, and it is not unique. A receipt number is the hospital's own
-- sequential record of money received, and it has to be unique to be worth
-- anything in an audit.
--
-- Sequence mirrors generate_bill_number (RHB-YYYY-NNNNNN) so the two read as
-- one family: RHR-YYYY-NNNNNN.
-- ============================================================================

BEGIN;

-- ── 1. Discount approval ────────────────────────────────────────────────────
ALTER TABLE public.royan_billing
    ADD COLUMN IF NOT EXISTS discount_status      text NOT NULL DEFAULT 'none',
    ADD COLUMN IF NOT EXISTS discount_reason      text,
    ADD COLUMN IF NOT EXISTS discount_requested_by text,
    ADD COLUMN IF NOT EXISTS discount_requested_at timestamptz,
    ADD COLUMN IF NOT EXISTS discount_decided_by  text,
    ADD COLUMN IF NOT EXISTS discount_decided_at  timestamptz,
    ADD COLUMN IF NOT EXISTS discount_decision_note text;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'royan_billing_discount_status_check'
    ) THEN
        ALTER TABLE public.royan_billing
            ADD CONSTRAINT royan_billing_discount_status_check
            CHECK (discount_status IN ('none', 'pending', 'approved', 'rejected'));
    END IF;
END $$;

COMMENT ON COLUMN public.royan_billing.discount_status IS
  'Approval state of any discount on this bill, independent of payment status. none (default) | pending | approved | rejected. A bill with a pending discount must not be settled.';

-- The admin card reads exactly this, and pending discounts are a tiny fraction
-- of 259k bills.
CREATE INDEX IF NOT EXISTS idx_billing_discount_pending
    ON public.royan_billing (discount_requested_at DESC)
    WHERE discount_status = 'pending';

-- ── 2. Receipt numbers ──────────────────────────────────────────────────────
CREATE SEQUENCE IF NOT EXISTS public.royan_receipt_seq;

CREATE OR REPLACE FUNCTION public.generate_receipt_number()
RETURNS text
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN 'RHR-' || to_char(now(), 'YYYY') || '-' ||
           lpad(nextval('royan_receipt_seq')::text, 6, '0');
END;
$$;

ALTER TABLE public.royan_payments
    ADD COLUMN IF NOT EXISTS receipt_number text;

-- Partial: historical payments have no receipt number and must not collide on
-- NULL, but every number we issue from here has to be unique or it is not a
-- receipt number.
CREATE UNIQUE INDEX IF NOT EXISTS uq_payments_receipt_number
    ON public.royan_payments (receipt_number)
    WHERE receipt_number IS NOT NULL;

COMMENT ON COLUMN public.royan_payments.receipt_number IS
  'Hospital-issued receipt number (RHR-YYYY-NNNNNN). Distinct from `reference`, which holds the PAYER''s own reference (transfer ref, POS slip) and is neither ours nor unique.';

COMMIT;

-- Verification:
--   SELECT discount_status, count(*) FROM royan_billing GROUP BY 1;
--   -- everything should be 'none' immediately after this migration
--   SELECT generate_receipt_number();
