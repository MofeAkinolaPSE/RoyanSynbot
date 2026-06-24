-- 106_billing_hospital.sql
-- Royan Hospital: Billing, payments, and insurance/HMO claims
-- Part of Phase 3 – Hospital Database Schema

ROLLBACK; -- clear any prior aborted transaction
BEGIN;

-- Hospital bills (one per encounter)
CREATE TABLE IF NOT EXISTS public.royan_billing (
    id                  bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    encounter_id        bigint      NOT NULL REFERENCES public.royan_encounters (id) ON DELETE RESTRICT,
    patient_id          bigint      NOT NULL REFERENCES public.royan_patients (id) ON DELETE RESTRICT,
    bill_number         text        NOT NULL UNIQUE,        -- e.g. "RHB-2026-000001"
    -- Breakdown
    consultation_fee    numeric     NOT NULL DEFAULT 0,
    lab_charges         numeric     NOT NULL DEFAULT 0,
    pharmacy_charges    numeric     NOT NULL DEFAULT 0,
    ward_charges        numeric     NOT NULL DEFAULT 0,
    procedure_charges   numeric     NOT NULL DEFAULT 0,
    miscellaneous       numeric     NOT NULL DEFAULT 0,
    -- Totals
    subtotal            numeric     GENERATED ALWAYS AS (
                            consultation_fee + lab_charges + pharmacy_charges +
                            ward_charges + procedure_charges + miscellaneous
                        ) STORED,
    discount            numeric     NOT NULL DEFAULT 0,
    hmo_covered         numeric     NOT NULL DEFAULT 0,     -- amount covered by HMO
    patient_balance     numeric     GENERATED ALWAYS AS (
                            (consultation_fee + lab_charges + pharmacy_charges +
                             ward_charges + procedure_charges + miscellaneous)
                            - discount - hmo_covered
                        ) STORED,
    -- Status
    status              text        NOT NULL DEFAULT 'pending'
                                    CHECK (status IN ('pending', 'partial', 'paid', 'waived', 'disputed', 'written_off')),
    payment_method      text        CHECK (payment_method IN ('cash', 'card', 'transfer', 'hmo', 'waiver', 'mixed')),
    billed_by           text,
    billed_at           timestamptz NOT NULL DEFAULT now(),
    paid_at             timestamptz,
    notes               text
);

-- Bill number sequence
CREATE SEQUENCE IF NOT EXISTS royan_bill_seq START 1;

CREATE OR REPLACE FUNCTION public.generate_bill_number()
RETURNS text
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN 'RHB-' || to_char(now(), 'YYYY') || '-' || lpad(nextval('royan_bill_seq')::text, 6, '0');
END;
$$;

-- Payment records (a bill may have multiple partial payments)
CREATE TABLE IF NOT EXISTS public.royan_payments (
    id              bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    billing_id      bigint      NOT NULL REFERENCES public.royan_billing (id) ON DELETE RESTRICT,
    patient_id      bigint      NOT NULL REFERENCES public.royan_patients (id) ON DELETE RESTRICT,
    amount          numeric     NOT NULL CHECK (amount > 0),
    payment_method  text        NOT NULL CHECK (payment_method IN ('cash', 'card', 'transfer', 'hmo', 'waiver')),
    reference       text,                                   -- POS/bank transaction reference
    received_by     text        NOT NULL,
    received_at     timestamptz NOT NULL DEFAULT now(),
    notes           text
);

-- HMO/Insurance claims
CREATE TABLE IF NOT EXISTS public.royan_insurance_claims (
    id              bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    billing_id      bigint      NOT NULL REFERENCES public.royan_billing (id) ON DELETE RESTRICT,
    patient_id      bigint      NOT NULL REFERENCES public.royan_patients (id) ON DELETE RESTRICT,
    hmo_provider    text        NOT NULL,
    hmo_id          text        NOT NULL,                   -- patient's HMO member number
    claim_amount    numeric     NOT NULL CHECK (claim_amount > 0),
    status          text        NOT NULL DEFAULT 'submitted'
                                CHECK (status IN ('submitted', 'pre_authorised', 'approved', 'rejected', 'paid', 'disputed')),
    submitted_at    timestamptz NOT NULL DEFAULT now(),
    authorisation_code text,
    approved_amount numeric,
    settled_at      timestamptz,
    notes           text
);

CREATE INDEX IF NOT EXISTS idx_royan_billing_encounter    ON public.royan_billing (encounter_id);
CREATE INDEX IF NOT EXISTS idx_royan_billing_patient      ON public.royan_billing (patient_id);
CREATE INDEX IF NOT EXISTS idx_royan_billing_status       ON public.royan_billing (status);
CREATE INDEX IF NOT EXISTS idx_royan_billing_billed_at    ON public.royan_billing (billed_at DESC);
CREATE INDEX IF NOT EXISTS idx_royan_payments_billing_id  ON public.royan_payments (billing_id);
CREATE INDEX IF NOT EXISTS idx_royan_claims_billing_id    ON public.royan_insurance_claims (billing_id);
CREATE INDEX IF NOT EXISTS idx_royan_claims_hmo_provider  ON public.royan_insurance_claims (hmo_provider);

COMMIT;
