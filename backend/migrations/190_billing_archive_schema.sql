-- Migration 190: Billing archive (supplement, not a replacement)
--
-- Complete-506-table Hope dump audit follow-up, Phase A2-P4: Hope's
-- `billings` (419K rows, per-transaction) and `final_billings` (334K rows,
-- per-encounter summary) were never extracted. transformers/payments.py's
-- own header comment claims `billings` is "confirmed EMPTY" -- that was
-- wrong, based on the known-unreliable keyword-search candidates cache;
-- direct content sampling confirmed real transactions spanning 2016-2025
-- (real bill numbers like "BL24-E31/108", real patient names in remarks).
--
-- Per explicit user decision (2026-08-21): keep the existing royan_billing
-- (sourced from service_bills/consultant_billings, already live and
-- working) untouched. These are new, separate archive tables -- a richer
-- historical record, not a replacement for or reconciliation with it.

BEGIN;

CREATE TABLE IF NOT EXISTS public.royan_billing_transactions (
    id                bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    patient_id        bigint      NOT NULL REFERENCES public.royan_patients (id) ON DELETE CASCADE,
    bill_number       text,
    transaction_date  timestamptz,
    payment_category  text,
    mode_of_payment   text,
    amount            numeric(14,2),
    total_amount      numeric(14,2),
    amount_paid       numeric(14,2),
    amount_pending    numeric(14,2),
    discount_amount   numeric(14,2),
    remark            text,
    external_source   text,
    external_id       text,
    created_at        timestamptz NOT NULL DEFAULT now()
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'royan_billing_transactions_external_source_external_id_key'
    ) THEN
        ALTER TABLE public.royan_billing_transactions
            ADD CONSTRAINT royan_billing_transactions_external_source_external_id_key
            UNIQUE (external_source, external_id);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_royan_billing_transactions_patient
    ON public.royan_billing_transactions (patient_id, transaction_date DESC);

CREATE TABLE IF NOT EXISTS public.royan_billing_summaries (
    id                     bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    patient_id             bigint      NOT NULL REFERENCES public.royan_patients (id) ON DELETE CASCADE,
    bill_number            text,
    bill_date              timestamptz,
    total_amount           numeric(14,2),
    amount_paid            numeric(14,2),
    amount_pending         numeric(14,2),
    discount               numeric(14,2),
    claim_status           text,
    discharge_date         timestamptz,
    external_source        text,
    external_id            text,
    created_at             timestamptz NOT NULL DEFAULT now()
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'royan_billing_summaries_external_source_external_id_key'
    ) THEN
        ALTER TABLE public.royan_billing_summaries
            ADD CONSTRAINT royan_billing_summaries_external_source_external_id_key
            UNIQUE (external_source, external_id);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_royan_billing_summaries_patient
    ON public.royan_billing_summaries (patient_id, bill_date DESC);

COMMIT;
