-- Migration 192: Accounting ledger archive
--
-- Phase A3 ("finish the job") of the complete-506-table Hope audit. Hope's
-- finance-side ledger, never extracted before. Archive/reference only --
-- like the billing archive (migration 190), these supplement rather than
-- replace royan_billing / royan_payments, which stay untouched.
--
--   account_receipts      50,294   receipts against patient accounts
--   voucher_entries       78,685   double-entry journal (debit/credit legs)
--   patient_cards         29,358   card/cheque/bank payment instruments
--   discount_requests      2,082   discount approval workflow history
--   settlement_billings       302   negotiated settlement line items
--   voucher_payments          526   payments made against vouchers

BEGIN;

CREATE TABLE IF NOT EXISTS public.royan_account_receipts (
    id                bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    patient_id        bigint      REFERENCES public.royan_patients (id) ON DELETE SET NULL,
    receipt_number    text,
    receipt_date      timestamptz,
    amount            numeric(14,2),
    payment_mode      text,
    narration         text,
    external_source   text,
    external_id       text,
    created_at        timestamptz NOT NULL DEFAULT now()
);
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='royan_account_receipts_ext_key') THEN
        ALTER TABLE public.royan_account_receipts
            ADD CONSTRAINT royan_account_receipts_ext_key UNIQUE (external_source, external_id);
    END IF;
END $$;
CREATE INDEX IF NOT EXISTS idx_royan_account_receipts_patient
    ON public.royan_account_receipts (patient_id, receipt_date DESC);


CREATE TABLE IF NOT EXISTS public.royan_voucher_entries (
    id                bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    patient_id        bigint      REFERENCES public.royan_patients (id) ON DELETE SET NULL,
    account_ref       text,
    entry_date        timestamptz,
    debit_amount      numeric(14,2),
    credit_amount     numeric(14,2),
    narration         text,
    entry_type        text,
    batch_identifier  text,
    external_source   text,
    external_id       text,
    created_at        timestamptz NOT NULL DEFAULT now()
);
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='royan_voucher_entries_ext_key') THEN
        ALTER TABLE public.royan_voucher_entries
            ADD CONSTRAINT royan_voucher_entries_ext_key UNIQUE (external_source, external_id);
    END IF;
END $$;
CREATE INDEX IF NOT EXISTS idx_royan_voucher_entries_date
    ON public.royan_voucher_entries (entry_date DESC);


CREATE TABLE IF NOT EXISTS public.royan_patient_card_transactions (
    id                bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    patient_id        bigint      REFERENCES public.royan_patients (id) ON DELETE SET NULL,
    instrument_type   text,       -- card / cheque / bank transfer
    amount            numeric(14,2),
    bank_account_no   text,
    credit_card_no    text,       -- Hope stored last-4/masked values
    cheque_no         text,
    mode_type         text,
    transacted_at     timestamptz,
    external_source   text,
    external_id       text,
    created_at        timestamptz NOT NULL DEFAULT now()
);
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='royan_patient_card_transactions_ext_key') THEN
        ALTER TABLE public.royan_patient_card_transactions
            ADD CONSTRAINT royan_patient_card_transactions_ext_key UNIQUE (external_source, external_id);
    END IF;
END $$;


CREATE TABLE IF NOT EXISTS public.royan_discount_requests (
    id                  bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    patient_id          bigint      REFERENCES public.royan_patients (id) ON DELETE SET NULL,
    patient_name        text,
    request_type        text,
    discount_amount     numeric(14,2),
    discount_percentage numeric(6,2),
    total_amount        numeric(14,2),
    payment_category    text,
    requested_by        text,
    requested_to        text,
    is_approved         boolean,
    is_closed           boolean     NOT NULL DEFAULT false,
    requested_at        timestamptz,
    external_source     text,
    external_id         text,
    created_at          timestamptz NOT NULL DEFAULT now()
);
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='royan_discount_requests_ext_key') THEN
        ALTER TABLE public.royan_discount_requests
            ADD CONSTRAINT royan_discount_requests_ext_key UNIQUE (external_source, external_id);
    END IF;
END $$;


CREATE TABLE IF NOT EXISTS public.royan_settlement_billings (
    id                bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    patient_id        bigint      REFERENCES public.royan_patients (id) ON DELETE SET NULL,
    item_name         text,
    units             numeric(10,2),
    rate              numeric(14,2),
    amount            numeric(14,2),
    settled_at        timestamptz,
    external_source   text,
    external_id       text,
    created_at        timestamptz NOT NULL DEFAULT now()
);
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='royan_settlement_billings_ext_key') THEN
        ALTER TABLE public.royan_settlement_billings
            ADD CONSTRAINT royan_settlement_billings_ext_key UNIQUE (external_source, external_id);
    END IF;
END $$;

COMMIT;
