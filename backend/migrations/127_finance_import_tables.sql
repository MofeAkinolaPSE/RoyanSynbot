-- ─────────────────────────────────────────────────────────────────────────────
-- 127_finance_import_tables.sql
-- Creates two PlacewareBot/finance tables that are missing from earlier migrations:
--   royan_import_jobs  — ETL / data-ingest job ledger
--   royan_gl_snapshot  — General Ledger P&L line entries
-- ─────────────────────────────────────────────────────────────────────────────

-- ── Import job tracking ───────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS royan_import_jobs (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    domain                TEXT        NOT NULL,
    batch_id              TEXT        NOT NULL,
    status                TEXT        NOT NULL DEFAULT 'running'
                            CHECK (status IN ('running','succeeded','failed','cancelled')),
    schema_version        TEXT,
    policy_version        TEXT,
    retention_days        INTEGER,
    retention_expires_at  TIMESTAMPTZ,
    imported_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at           TIMESTAMPTZ,
    completed_at          TIMESTAMPTZ GENERATED ALWAYS AS (finished_at) STORED,
    idempotency_key       TEXT        UNIQUE,
    metadata              JSONB       DEFAULT '{}'::jsonb,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_import_jobs_domain_status
    ON royan_import_jobs (domain, status, finished_at DESC);

CREATE INDEX IF NOT EXISTS idx_import_jobs_batch_id
    ON royan_import_jobs (batch_id);

-- ── General Ledger snapshot ───────────────────────────────────────────────────
-- Insert path uses: period, account_code, account_name, debit, credit
-- Finance query path uses: posting_date, account_id, debit_amount, credit_amount
-- Generated columns bridge the two naming conventions transparently.
CREATE TABLE IF NOT EXISTS royan_gl_snapshot (
    id            BIGSERIAL   PRIMARY KEY,
    batch_id      TEXT        NOT NULL,
    imported_at   TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Insert-path names (from GLEntry Pydantic model)
    period        TEXT        NOT NULL,
    account_code  TEXT        NOT NULL,
    account_name  TEXT,
    debit         NUMERIC(18,2) NOT NULL DEFAULT 0,
    credit        NUMERIC(18,2) NOT NULL DEFAULT 0,

    -- Finance-query aliases (generated, always consistent with the above)
    posting_date  TEXT GENERATED ALWAYS AS (period)       STORED,
    account_id    TEXT GENERATED ALWAYS AS (account_code) STORED,
    debit_amount  NUMERIC(18,2) GENERATED ALWAYS AS (debit)  STORED,
    credit_amount NUMERIC(18,2) GENERATED ALWAYS AS (credit) STORED,

    -- Additional columns populated by richer integrations
    reference_id  TEXT,
    description   TEXT,
    cost_center   TEXT
);

CREATE INDEX IF NOT EXISTS idx_gl_snapshot_batch_id
    ON royan_gl_snapshot (batch_id);

CREATE INDEX IF NOT EXISTS idx_gl_snapshot_posting_date
    ON royan_gl_snapshot (posting_date);

CREATE INDEX IF NOT EXISTS idx_gl_snapshot_account_id
    ON royan_gl_snapshot (account_id);
