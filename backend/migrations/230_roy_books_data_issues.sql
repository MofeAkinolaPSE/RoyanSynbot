-- =============================================================================
-- Migration 230 - Roy Books: Data issues register
-- =============================================================================
-- Everything the data leaves unexplained becomes a Data issue (Close & Controls ›
-- Data issues) with its lineage and the ways to resolve it: Sage history that no
-- longer ties, the 2025 gap between Sage and Hope, stock on the pharmacy shelves
-- the books do not carry, payers with no Sage account, Hope vs Sage differences.
-- Detected by src/fin/data_issues.py (refresh after every load and on "Check
-- again"); an issue the data no longer shows closes itself, one that comes back
-- reopens unless it was accepted. Every decision is logged with who, when, why;
-- a correcting journal is numbered FIX-nnnnnn and links both ways.
-- =============================================================================

CREATE TABLE IF NOT EXISTS fin_data_issues (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    legal_entity_id UUID NOT NULL REFERENCES fin_legal_entities(id),
    kind            TEXT NOT NULL,
    key             TEXT NOT NULL,
    title           TEXT NOT NULL,
    summary         TEXT,
    severity        TEXT NOT NULL DEFAULT 'MEDIUM' CHECK (severity IN ('LOW', 'MEDIUM', 'HIGH')),
    amount          NUMERIC(20,2),
    quantity        NUMERIC(18,4),
    as_of           DATE,
    detail          JSONB NOT NULL DEFAULT '{}'::jsonb,
    status          TEXT NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN', 'RESOLVED', 'ACCEPTED')),
    resolution      TEXT,
    resolution_note TEXT,
    resolved_by     TEXT,
    resolved_at     TIMESTAMPTZ,
    first_seen      TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen       TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (legal_entity_id, kind, key)
);
CREATE INDEX IF NOT EXISTS idx_fin_data_issues_status ON fin_data_issues (legal_entity_id, status, kind);

CREATE TABLE IF NOT EXISTS fin_data_issue_actions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    issue_id        UUID NOT NULL REFERENCES fin_data_issues(id) ON DELETE CASCADE,
    legal_entity_id UUID NOT NULL REFERENCES fin_legal_entities(id),
    action          TEXT NOT NULL,
    reference       TEXT,
    note            TEXT,
    payload         JSONB NOT NULL DEFAULT '{}'::jsonb,
    journal_id      UUID REFERENCES fin_journals(id),
    created_by      TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_fin_data_issue_actions ON fin_data_issue_actions (issue_id, created_at);
