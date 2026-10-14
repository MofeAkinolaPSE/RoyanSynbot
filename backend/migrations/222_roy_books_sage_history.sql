-- =============================================================================
-- Migration 222 - Roy Books: Royan's Sage 50 history (2009 -> 31 Dec 2024)
-- =============================================================================
-- Royan's Sage company was exported at its 2024 year end (backend/docs/
-- Financial-engine/sage-exports, 13 reports). This migration creates where
-- that history lives; `python -m src.fin.sage_import` loads it.
--
-- What is history and what is books:
--   * The GL trial balance at 31 Dec 2024 is loaded as Roy Books' OPENING
--     journal (the books' real position).
--   * Every Sage GL line 2009 -> 2024 (CRJ / SJ / CDJ / GENJ, ~190k lines) is
--     kept here, line for line. It ties to that trial balance to the kobo
--     (Sage closes P&L into Retained Earnings without journal lines; the
--     balance sheet treats prior-year profit as retained earnings, so equity
--     agrees too).
--   * fin_v_ledger = the Sage history + every Roy Books journal EXCEPT the
--     opening journal the history replaces. Statements, the trial balance,
--     account drill-downs and the Report Center read fin_v_ledger, so any
--     year 2010 -> today can be reported and every figure drills to the
--     Sage line, its voucher, invoice, receipt and customer.
--   * Posting-level work (bank reconciliation, controls, year-end close)
--     keeps reading fin_v_general_ledger: the books only.
-- History never posts and never changes a balance.
-- =============================================================================

ALTER TABLE fin_settings ADD COLUMN IF NOT EXISTS history_replaces_opening BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE suppliers ADD COLUMN IF NOT EXISTS sage_vendor_id TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS uq_suppliers_sage_vendor ON suppliers (sage_vendor_id) WHERE sage_vendor_id IS NOT NULL;

-- Sage customers -> Roy Books debtors. Several Sage customer IDs can be one
-- party (e.g. an HMO keyed twice); match_method says how the link was made.
CREATE TABLE IF NOT EXISTS fin_sage_customers (
    legal_entity_id  UUID NOT NULL REFERENCES fin_legal_entities(id),
    sage_code        TEXT NOT NULL,
    name             TEXT NOT NULL,
    contact          TEXT,
    phone            TEXT,
    customer_id      BIGINT NOT NULL REFERENCES fin_customers(id),
    match_method     TEXT NOT NULL,
    PRIMARY KEY (legal_entity_id, sage_code)
);

-- Every Sage GL line. voucher = the lines Sage posted together
-- (journal + date + reference; CDJ lines without a reference: journal + date + payee).
CREATE TABLE IF NOT EXISTS fin_sage_gl_lines (
    id               BIGSERIAL PRIMARY KEY,
    legal_entity_id  UUID NOT NULL REFERENCES fin_legal_entities(id),
    row_no           INT NOT NULL,                 -- row in the exported General Ledger
    account_code     TEXT NOT NULL,
    account_id       UUID REFERENCES fin_accounts(id),
    txn_date         DATE NOT NULL,
    jrnl             TEXT NOT NULL,                -- CRJ cash receipts, SJ sales, CDJ cash disbursements, GENJ general
    reference        TEXT,
    description      TEXT,
    debit            NUMERIC(20,2) NOT NULL DEFAULT 0,
    credit           NUMERIC(20,2) NOT NULL DEFAULT 0,
    voucher          TEXT NOT NULL,
    customer_id      BIGINT,                       -- fin_customers, when the line is about a debtor
    supplier_id      UUID,
    UNIQUE (legal_entity_id, row_no)
);
CREATE INDEX IF NOT EXISTS idx_sage_gl_account ON fin_sage_gl_lines (account_id, txn_date);
CREATE INDEX IF NOT EXISTS idx_sage_gl_voucher ON fin_sage_gl_lines (legal_entity_id, voucher);
CREATE INDEX IF NOT EXISTS idx_sage_gl_customer ON fin_sage_gl_lines (customer_id) WHERE customer_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_sage_gl_jrnl ON fin_sage_gl_lines (legal_entity_id, jrnl, txn_date);

-- Sage Invoice Register (one row per invoice / credit memo).
CREATE TABLE IF NOT EXISTS fin_sage_invoices (
    id               BIGSERIAL PRIMARY KEY,
    legal_entity_id  UUID NOT NULL REFERENCES fin_legal_entities(id),
    row_no           INT NOT NULL,
    invoice_number   TEXT,
    invoice_date     DATE,
    quote_number     TEXT,
    customer_name    TEXT,
    customer_id      BIGINT,
    amount           NUMERIC(20,2) NOT NULL DEFAULT 0,
    amount_received  NUMERIC(20,2) NOT NULL DEFAULT 0,   -- from the Cash Receipts Journal
    voucher          TEXT,                                 -- its SJ voucher in the GL, when found
    UNIQUE (legal_entity_id, row_no)
);
CREATE INDEX IF NOT EXISTS idx_sage_inv_no ON fin_sage_invoices (legal_entity_id, invoice_number);
CREATE INDEX IF NOT EXISTS idx_sage_inv_customer ON fin_sage_invoices (customer_id, invoice_date);

-- Sage Cash Receipts Journal, as receipts (bank leg + the invoices it settled).
CREATE TABLE IF NOT EXISTS fin_sage_receipts (
    id               BIGSERIAL PRIMARY KEY,
    legal_entity_id  UUID NOT NULL REFERENCES fin_legal_entities(id),
    reference        TEXT NOT NULL,
    receipt_date     DATE NOT NULL,
    payer            TEXT,
    customer_id      BIGINT,
    bank_account_code TEXT,
    bank_account_id  UUID REFERENCES fin_accounts(id),
    amount           NUMERIC(20,2) NOT NULL,
    voucher          TEXT,
    row_no           INT NOT NULL,                 -- row of the bank line in the exported journal
    UNIQUE (legal_entity_id, row_no)
);
CREATE INDEX IF NOT EXISTS idx_sage_rcpt_customer ON fin_sage_receipts (customer_id, receipt_date);

CREATE TABLE IF NOT EXISTS fin_sage_receipt_invoices (
    receipt_id       BIGINT NOT NULL REFERENCES fin_sage_receipts(id) ON DELETE CASCADE,
    invoice_number   TEXT,
    invoice_id       BIGINT REFERENCES fin_sage_invoices(id),
    amount           NUMERIC(20,2) NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sage_ri_invoice ON fin_sage_receipt_invoices (invoice_id);

-- The Sage reports exactly as delivered (balance sheet, cash flow, GL account
-- summary, trial balance, aged receivables, items sold, reconciliation), kept
-- for tie-out against Roy Books and for the auditors.
CREATE TABLE IF NOT EXISTS fin_sage_reports (
    id               BIGSERIAL PRIMARY KEY,
    legal_entity_id  UUID NOT NULL REFERENCES fin_legal_entities(id),
    report_key       TEXT NOT NULL,
    title            TEXT NOT NULL,
    as_of            DATE,
    file_name        TEXT,
    columns          JSONB NOT NULL DEFAULT '[]'::jsonb,
    rows             JSONB NOT NULL DEFAULT '[]'::jsonb,
    loaded_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (legal_entity_id, report_key)
);

-- The last Sage bank reconciliation (Stanbic IBTC, 31 Dec 2024): its open items
-- are the reconciliation baseline Roy Books starts from.
CREATE TABLE IF NOT EXISTS fin_sage_recon_items (
    id               BIGSERIAL PRIMARY KEY,
    legal_entity_id  UUID NOT NULL REFERENCES fin_legal_entities(id),
    account_code     TEXT NOT NULL,
    section          TEXT NOT NULL,     -- DEPOSIT_IN_TRANSIT / OUTSTANDING_CHECK / OTHER
    item_date        DATE,
    reference        TEXT,
    description      TEXT,
    amount           NUMERIC(20,2) NOT NULL
);

-- ---------------------------------------------------------------------------
-- The ledger with its history: same columns as fin_v_general_ledger.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW fin_v_ledger AS
SELECT g.line_id::text AS line_id, g.legal_entity_id, g.journal_id, g.journal_number, g.journal_date, g.period_id,
       g.journal_type, g.source_type, g.source_id, g.source_ref, g.journal_description, g.line_no, g.account_id,
       g.account_code, g.account_name, g.account_type, g.subtype, g.normal_balance, g.description, g.debit, g.credit,
       g.customer_id, g.supplier_id, g.product_sku, g.branch_id, g.department_id, g.cost_centre_id, g.posted_at, g.posted_by,
       'ROY'::text AS origin
FROM fin_v_general_ledger g
LEFT JOIN fin_settings s ON s.legal_entity_id = g.legal_entity_id
WHERE NOT (g.journal_type = 'OPENING' AND g.source_ref = 'SAGE-TB' AND COALESCE(s.history_replaces_opening, FALSE))
UNION ALL
SELECT 'S' || l.id::text, l.legal_entity_id, NULL::uuid, 'SAGE ' || l.jrnl || COALESCE(' ' || NULLIF(l.reference, ''), ''),
       l.txn_date, NULL::uuid, 'HISTORY', 'SAGE_GL', l.voucher, NULLIF(l.reference, ''), l.description, l.row_no, l.account_id,
       a.code, a.name, a.account_type, a.subtype, a.normal_balance, l.description, l.debit, l.credit,
       l.customer_id, l.supplier_id, NULL::text, NULL::uuid, NULL::uuid, NULL::uuid, NULL::timestamptz, 'Sage 50',
       'SAGE'::text
FROM fin_sage_gl_lines l
JOIN fin_accounts a ON a.id = l.account_id
JOIN fin_settings s ON s.legal_entity_id = l.legal_entity_id AND s.history_replaces_opening;
