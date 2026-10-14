-- Migration 215: discounts on pharmacy dispensing, with the same approval flow
-- ============================================================================
--
-- "they also need to add patients discount for internal staff. So again, in the
-- pharmacy department, we're going to have a column for discounts, just like we
-- did in billing."
--
-- SAME COLUMN NAMES AS royan_billing ON PURPOSE
-- ---------------------------------------------
-- Migration 205 gave royan_billing discount / discount_reason / discount_status
-- / requested_by / requested_at / decided_by / decided_at / decision_note, with
-- an admin approving before the bill can be settled. Reusing the exact names
-- here means the admin approval queue can read both tables through one shape
-- instead of two near-identical code paths that drift apart.
--
-- WHY discount_type EXISTS AND BILLING HAS NO EQUIVALENT
-- ------------------------------------------------------
-- The ask here is specifically a STAFF discount. Recording that as a plain
-- amount would lose the reason, and "how much did we give staff last month" is
-- exactly the question an administrator will ask. Keeping it as a typed field
-- rather than parsing it back out of free text later.
--
-- APPROVAL IS REQUIRED, NOT ADVISORY
-- ----------------------------------
-- discount_status starts 'none'. A discount goes to 'pending' and only an admin
-- moves it to 'approved'. The dispensing endpoint applies nothing until then,
-- so a pharmacist cannot discount a drug on their own authority -- which is the
-- entire point of routing staff discounts through approval.
-- ============================================================================

BEGIN;

ALTER TABLE public.royan_dispensing
    ADD COLUMN IF NOT EXISTS discount              numeric(14,2) NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS discount_type         text,
    ADD COLUMN IF NOT EXISTS discount_reason       text,
    ADD COLUMN IF NOT EXISTS discount_status       text NOT NULL DEFAULT 'none',
    ADD COLUMN IF NOT EXISTS discount_requested_by text,
    ADD COLUMN IF NOT EXISTS discount_requested_at timestamptz,
    ADD COLUMN IF NOT EXISTS discount_decided_by   text,
    ADD COLUMN IF NOT EXISTS discount_decided_at   timestamptz,
    ADD COLUMN IF NOT EXISTS discount_decision_note text;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'royan_dispensing_discount_status_check'
    ) THEN
        ALTER TABLE public.royan_dispensing
            ADD CONSTRAINT royan_dispensing_discount_status_check
            CHECK (discount_status IN ('none', 'pending', 'approved', 'rejected'));
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'royan_dispensing_discount_type_check'
    ) THEN
        ALTER TABLE public.royan_dispensing
            ADD CONSTRAINT royan_dispensing_discount_type_check
            CHECK (discount_type IS NULL OR discount_type IN
                   ('staff', 'staff_dependant', 'goodwill', 'hardship', 'promotional', 'other'));
    END IF;

    -- A discount cannot exceed what is being charged. Without this a typo turns
    -- a sale into a refund, and the total goes negative silently.
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'royan_dispensing_discount_bounds_check'
    ) THEN
        ALTER TABLE public.royan_dispensing
            ADD CONSTRAINT royan_dispensing_discount_bounds_check
            CHECK (discount >= 0 AND (total_cost IS NULL OR discount <= total_cost));
    END IF;
END $$;

-- The admin queue reads pending discounts across both tables; without this it
-- scans 618,450 dispensing rows to find a handful.
CREATE INDEX IF NOT EXISTS idx_dispensing_discount_pending
    ON public.royan_dispensing (discount_status, discount_requested_at)
    WHERE discount_status = 'pending';

COMMENT ON COLUMN public.royan_dispensing.discount_type IS
  'Why the discount was given. Staff discounts are the reason this column exists — "how much went to staff last month" should not require parsing free text.';
COMMENT ON COLUMN public.royan_dispensing.discount_status IS
  'none -> pending -> approved/rejected. Nothing is deducted until approved: a pharmacist cannot discount on their own authority.';

COMMIT;

-- Verification:
--   SELECT discount_status, count(*) FROM royan_dispensing GROUP BY 1;
--   -- expect every existing row at 'none'
