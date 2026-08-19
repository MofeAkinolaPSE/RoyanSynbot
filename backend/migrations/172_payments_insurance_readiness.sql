-- 172_payments_insurance_readiness.sql
-- Data-readiness pass: royan_payments and royan_insurance_claims are
-- currently empty because the ETL pipeline never targeted their real DRM
-- Hope source tables — this migration closes the schema-level gaps found
-- when checking whether the real source shapes would actually load without
-- constraint violations once that pipeline work happens (separately, not
-- this pass).

ROLLBACK;
BEGIN;

-- ── Payments ─────────────────────────────────────────────────────────────
-- Real source: service_cash_payments / account_receipts have nullable bill
-- links; voucher_payments has no billing_id concept at all. None of the
-- three source tables supply a payment_method the way this table expects.
ALTER TABLE royan_payments
    ADD COLUMN IF NOT EXISTS external_source       text,
    ADD COLUMN IF NOT EXISTS external_id            text,
    ADD COLUMN IF NOT EXISTS external_updated_at    timestamptz;

ALTER TABLE royan_payments DROP CONSTRAINT IF EXISTS royan_payments_external_source_external_id_key;
ALTER TABLE royan_payments ADD CONSTRAINT royan_payments_external_source_external_id_key
    UNIQUE (external_source, external_id);

ALTER TABLE royan_payments ALTER COLUMN billing_id DROP NOT NULL;

ALTER TABLE royan_payments DROP CONSTRAINT IF EXISTS royan_payments_payment_method_check;
ALTER TABLE royan_payments ADD CONSTRAINT royan_payments_payment_method_check
    CHECK (payment_method = ANY (ARRAY['cash','card','transfer','hmo','waiver','other']));

-- ── Insurance Claims ─────────────────────────────────────────────────────
-- Fixes a confirmed pre-existing bug: migration 131 tried to add an hmo_id
-- bigint FK but silently no-op'd because hmo_id already existed as text
-- (holding the member number) — its own type-guard skipped the ALTER. This
-- adds a new, separate FK column instead of touching the existing text
-- column, matching the same ETL-only-enrichment convention already shipped
-- for royan_billing.hmo_id (added by the same migration, never populated by
-- the live app either).
ALTER TABLE royan_insurance_claims
    ADD COLUMN IF NOT EXISTS external_source       text,
    ADD COLUMN IF NOT EXISTS external_id            text,
    ADD COLUMN IF NOT EXISTS external_updated_at    timestamptz,
    ADD COLUMN IF NOT EXISTS hmo_provider_id         bigint REFERENCES royan_hmos(id) ON DELETE SET NULL;

ALTER TABLE royan_insurance_claims DROP CONSTRAINT IF EXISTS royan_insurance_claims_external_source_external_id_key;
ALTER TABLE royan_insurance_claims ADD CONSTRAINT royan_insurance_claims_external_source_external_id_key
    UNIQUE (external_source, external_id);

COMMIT;
