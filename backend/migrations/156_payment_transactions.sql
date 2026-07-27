-- Migration 156: Create the missing royan_payment_transactions table
--
-- backend/src/routers/payments_gateway.py (Paystack/Flutterwave/Stripe
-- initiate, verify, and webhook handlers) has referenced this table since
-- the router was written, but no migration ever created it — every
-- initiate/verify/webhook call has failed with "relation does not exist",
-- meaning the entire payment-gateway integration (not just the new Stripe
-- addition) has never actually worked end-to-end.

ROLLBACK;
BEGIN;

CREATE TABLE IF NOT EXISTS public.royan_payment_transactions (
    id            bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    reference     text        NOT NULL UNIQUE,
    gateway       text        NOT NULL CHECK (gateway IN ('paystack', 'flutterwave', 'stripe')),
    amount        numeric     NOT NULL CHECK (amount > 0),
    currency      text        NOT NULL DEFAULT 'NGN',
    email         text,
    patient_id    bigint      REFERENCES public.royan_patients (id) ON DELETE SET NULL,
    encounter_id  bigint      REFERENCES public.royan_encounters (id) ON DELETE SET NULL,
    bill_id       bigint      REFERENCES public.royan_billing (id) ON DELETE SET NULL,
    description   text,
    status        text        NOT NULL DEFAULT 'initiated'
                              CHECK (status IN ('initiated', 'pending', 'success', 'failed')),
    gateway_data  jsonb,
    webhook_data  jsonb,
    initiated_by  text,
    initiated_at  timestamptz NOT NULL DEFAULT now(),
    verified_at   timestamptz
);

CREATE INDEX IF NOT EXISTS idx_royan_payment_transactions_patient
    ON public.royan_payment_transactions (patient_id);
CREATE INDEX IF NOT EXISTS idx_royan_payment_transactions_bill
    ON public.royan_payment_transactions (bill_id);

COMMIT;
