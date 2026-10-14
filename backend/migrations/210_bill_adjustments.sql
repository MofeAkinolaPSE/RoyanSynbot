-- Migration 210: the correction pen — auditable bill adjustments and refunds
-- ============================================================================
--
-- "the correction pen feature allows the admin to handle refunds, confirm
-- discounts, and... if a patient was to come into the hospital and request a bag
-- of blood for transfusion, which is about 90k, if the patient now goes ahead
-- and doesn't use that bag of blood, they have to split the bill into three
-- places so that the patient doesn't pay the full bill. Admin also needs to be
-- able to track that."
--
-- WHAT EXISTED
-- ------------
-- Only two whole-bill actions: waive and write-off. Both flip a status, both
-- are all-or-nothing, and neither records WHY or leaves any trail. There was no
-- way to correct one line of a bill, and no way to refund money already taken.
--
-- CORRECTIONS ARE ADDED, NOT APPLIED OVER
-- ---------------------------------------
-- Every adjustment is a new row carrying the amount before and after. The
-- original bill figures are never rewritten. This is the same principle already
-- used for clinical notes (addenda, migration 196) and lab results (amendments,
-- migration 161), and for the same reason: a financial record that can be
-- silently edited is worth nothing in a dispute, and "the bill says 40k now" is
-- useless without "it said 90k until Tuesday, and here is who changed it".
--
-- WHY reallocated_to IS FREE TEXT
-- -------------------------------
-- The worked example splits a charge three ways. Modelling that properly needs
-- a payer model the system does not have — the other parties in that example
-- are not HMOs, they are "the hospital absorbs it" and "the supplier takes it
-- back". Inventing a payer table to hold two strings would be worse than a
-- labelled note, so the destination is recorded as text and the MONEY movement
-- is exact. If real multi-payer splitting is needed later, this table already
-- holds the per-slice rows it would need.
-- ============================================================================

BEGIN;

CREATE TABLE IF NOT EXISTS public.royan_bill_adjustments (
    id            bigserial PRIMARY KEY,
    billing_id    bigint NOT NULL REFERENCES public.royan_billing(id) ON DELETE CASCADE,
    patient_id    bigint REFERENCES public.royan_patients(id) ON DELETE SET NULL,

    -- reduction   : the patient owes less (service not rendered, over-charged)
    -- reallocation: the charge stands but someone else carries part of it
    -- refund      : money already taken is being returned
    -- reversal    : an adjustment made in error is being undone
    adjustment_type text NOT NULL,

    amount        numeric(14,2) NOT NULL,
    -- What the figure was before and after, stored rather than derived so the
    -- trail stays readable even if later corrections stack on top.
    amount_before numeric(14,2),
    amount_after  numeric(14,2),

    -- Which line this touches, when it is line-level rather than whole-bill.
    bill_item_id  bigint,
    line_label    text,

    -- Where the money went, for a reallocation. Deliberately text — see header.
    reallocated_to text,

    -- Not nullable. An adjustment without a reason is indistinguishable from
    -- someone quietly changing a number, which is the thing this table exists
    -- to prevent.
    reason        text NOT NULL,

    adjusted_by   text,
    adjusted_at   timestamptz NOT NULL DEFAULT now(),
    -- Set when this row reverses an earlier one.
    reverses_id   bigint REFERENCES public.royan_bill_adjustments(id) ON DELETE SET NULL,

    created_at    timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT royan_bill_adjustments_type_check
        CHECK (adjustment_type IN ('reduction', 'reallocation', 'refund', 'reversal')),
    CONSTRAINT royan_bill_adjustments_amount_check
        CHECK (amount > 0),
    CONSTRAINT royan_bill_adjustments_reason_check
        CHECK (btrim(reason) <> '')
);

CREATE INDEX IF NOT EXISTS idx_bill_adjustments_bill
    ON public.royan_bill_adjustments (billing_id, adjusted_at DESC);
CREATE INDEX IF NOT EXISTS idx_bill_adjustments_patient
    ON public.royan_bill_adjustments (patient_id, adjusted_at DESC);

COMMENT ON TABLE public.royan_bill_adjustments IS
  'The correction pen. Every change to a bill after issue, as an append-only trail — the original figures are never rewritten.';

-- A refund needs to point at the payment being returned, so the receipt and the
-- refund can be reconciled against each other.
ALTER TABLE public.royan_bill_adjustments
    ADD COLUMN IF NOT EXISTS payment_id bigint REFERENCES public.royan_payments(id) ON DELETE SET NULL;

COMMIT;

-- Verification:
--   SELECT adjustment_type, count(*) FROM royan_bill_adjustments GROUP BY 1;
--   -- an adjustment with a blank reason must fail:
--   -- ERROR: new row violates check constraint "royan_bill_adjustments_reason_check"
