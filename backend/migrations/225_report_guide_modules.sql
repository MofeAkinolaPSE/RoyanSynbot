-- 225: reportGUide.md - reports about a record, stock orders, patient relations.
-- Additive only. Apply: psql -v ON_ERROR_STOP=1 -f 225_report_guide_modules.sql

BEGIN;

-- s12 Reports: one report about one chosen record, written only from its gathered facts.
-- (The report writer's old store, royan_report_memory, was never created in this database.)
CREATE TABLE IF NOT EXISTS royan_record_reports (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    report_type    text NOT NULL,
    subject_kind   text NOT NULL,
    subject_id     text NOT NULL,
    subject_label  text NOT NULL,
    title          text NOT NULL,
    full_report    text NOT NULL,
    sections       jsonb NOT NULL DEFAULT '[]'::jsonb,
    facts          jsonb NOT NULL DEFAULT '{}'::jsonb,     -- the dossier the report was written from
    author_notes   text,
    status         text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'complete', 'approved')),
    needs_signoff  boolean NOT NULL DEFAULT false,           -- clinical documents: a clinician approves
    created_by     text,
    approved_by    text,
    approved_at    timestamptz,
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_record_reports_subject ON royan_record_reports (subject_kind, subject_id);
CREATE INDEX IF NOT EXISTS ix_record_reports_created ON royan_record_reports (created_at DESC);

-- s6 Procurement: a replenishment request is the stock order. It is received by the stock
-- arriving (pharmacy receipt or a Roy Books supplier delivery), never ticked by hand.
ALTER TABLE royan_replenishment_requests
    ADD COLUMN IF NOT EXISTS supplier_id     uuid REFERENCES suppliers(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS expected_date   date,
    ADD COLUMN IF NOT EXISTS ordered_at      timestamptz,
    ADD COLUMN IF NOT EXISTS ordered_by      text,
    ADD COLUMN IF NOT EXISTS received_qty    numeric,
    ADD COLUMN IF NOT EXISTS received_source text,
    ADD COLUMN IF NOT EXISTS received_ref    text,
    ADD COLUMN IF NOT EXISTS cancelled_reason text;
CREATE INDEX IF NOT EXISTS ix_replenishment_open ON royan_replenishment_requests (formulary_id)
    WHERE status IN ('recommended', 'approved', 'ordered');

-- s7 Patient Relations: calls, visits and notes with HMOs / corporate payers, with follow-ups.
-- The payer is Hope's tariff (fin_hope_payers.tariff_id) - the key billing and debt already use.
CREATE TABLE IF NOT EXISTS royan_payer_contacts (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    payer_id      integer NOT NULL,
    kind          text NOT NULL DEFAULT 'note' CHECK (kind IN ('call', 'visit', 'email', 'meeting', 'note')),
    summary       text NOT NULL,
    follow_up_on  date,
    follow_up_done_at timestamptz,
    owner_id      text,
    created_by    text,
    created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_payer_contacts_payer ON royan_payer_contacts (payer_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_payer_contacts_due ON royan_payer_contacts (follow_up_on) WHERE follow_up_done_at IS NULL;

COMMIT;
