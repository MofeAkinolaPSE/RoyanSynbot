-- =============================================================================
-- Migration 223 - Roy Books: who paid (HMO / private / staff / corporate),
--                 Hope <-> Sage reconciliation, and Sage uploads by Finance
-- =============================================================================
-- Royan ran two systems side by side: DRM Hope at the till and on the wards
-- (every charge, with the patient's payer on it) and Sage 50 for the books
-- (HMO invoices in the sales journal, the day's private takings as general
-- journals). Neither alone answers "what went to HMOs and what went to private
-- patients, at what cost" - the split the hospital asked for.
--
--   * fin_hope_payers   one row per Hope payer ("tariff standard"): its type
--                       (PRIVATE / HMO / STAFF / CORPORATE / INTERNAL = services
--                       Royan itself pays for, e.g. Scancare referrals), the hospital HMO
--                       and the Roy Books debtor it is. Finance can re-type a
--                       payer here; every report follows.
--   * fin_hope_charges  every Hope charge line - services, pharmacy, lab,
--                       radiology, ward - with its payer, gross, discount,
--                       what was paid at the till and what was left
--                       (python -m src.fin.hope_charges). Display and
--                       reconciliation only: it never posts.
--   * fin_sage_uploads  Sage exports Finance uploads from Roy Books (2025,
--                       2026 ...): files received, the dry-run tie-out, and the
--                       load. The import itself is src.fin.sage_import.
-- =============================================================================

CREATE TABLE IF NOT EXISTS fin_hope_payers (
    tariff_id     INTEGER PRIMARY KEY,
    name          TEXT NOT NULL,
    payer_type    TEXT NOT NULL CHECK (payer_type IN ('PRIVATE','HMO','STAFF','CORPORATE','INTERNAL')),
    hmo_id        BIGINT REFERENCES royan_hmos(id) ON DELETE SET NULL,
    customer_id   BIGINT REFERENCES fin_customers(id) ON DELETE SET NULL,
    sage_code     TEXT,
    typed_by      TEXT NOT NULL DEFAULT 'rule',      -- 'rule' (by name) or the user who re-typed it
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS fin_hope_charges (
    id            BIGSERIAL PRIMARY KEY,
    source        TEXT NOT NULL CHECK (source IN ('SERVICE','PHARMACY','LAB','RADIOLOGY','WARD')),
    hope_id       BIGINT NOT NULL,
    visit_id      BIGINT,                             -- Hope admission / visit id
    mrn           TEXT,
    patient_id    BIGINT REFERENCES royan_patients(id) ON DELETE SET NULL,
    charge_date   DATE NOT NULL,
    service       TEXT,
    category      TEXT,
    payer_tariff_id INTEGER,
    quantity      NUMERIC(14,2) NOT NULL DEFAULT 1,
    gross         NUMERIC(16,2) NOT NULL DEFAULT 0,
    discount      NUMERIC(16,2) NOT NULL DEFAULT 0,
    paid_cash     NUMERIC(16,2) NOT NULL DEFAULT 0,
    paid_card     NUMERIC(16,2) NOT NULL DEFAULT 0,
    paid          NUMERIC(16,2) NOT NULL DEFAULT 0,
    outstanding   NUMERIC(16,2) GENERATED ALWAYS AS (GREATEST(gross - discount - paid, 0)) STORED,
    reference     TEXT,                               -- order id / bill code
    super_bill_id INTEGER,                            -- Hope's monthly corporate bill it went on
    UNIQUE (source, hope_id)
);
CREATE INDEX IF NOT EXISTS idx_fin_hope_charges_date ON fin_hope_charges (charge_date);
CREATE INDEX IF NOT EXISTS idx_fin_hope_charges_payer ON fin_hope_charges (payer_tariff_id, charge_date);
CREATE INDEX IF NOT EXISTS idx_fin_hope_charges_patient ON fin_hope_charges (patient_id, charge_date);
CREATE INDEX IF NOT EXISTS idx_fin_hope_charges_visit ON fin_hope_charges (visit_id);

-- Charges with their payer. Lines above N50m are mis-keyed in Hope (same rule as
-- fin_v_hope_revenue_monthly) and are left out here, not silently corrected.
CREATE OR REPLACE VIEW fin_v_hope_charges AS
SELECT c.*, COALESCE(p.name, 'Unknown payer') AS payer, COALESCE(p.payer_type, 'PRIVATE') AS payer_type,
       p.hmo_id, p.customer_id
FROM fin_hope_charges c
LEFT JOIN fin_hope_payers p ON p.tariff_id = c.payer_tariff_id
WHERE c.gross <= 50000000;

CREATE TABLE IF NOT EXISTS fin_sage_uploads (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    legal_entity_id UUID NOT NULL,
    status          TEXT NOT NULL DEFAULT 'UPLOADED' CHECK (status IN ('UPLOADED','CHECKED','LOADED','FAILED')),
    note            TEXT,
    files           JSONB NOT NULL DEFAULT '{}'::jsonb,   -- kind -> {file, rows, from, to}
    check_result    JSONB,
    load_result     JSONB,
    created_by      TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    checked_at      TIMESTAMPTZ,
    loaded_by       TEXT,
    loaded_at       TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_fin_sage_uploads_entity ON fin_sage_uploads (legal_entity_id, created_at DESC);

-- A newer Sage trial balance rolls the opening journal forward (the old one is
-- reversed), and once the books are live Sage history stops at the cut-over.
-- Both opening journals and the reversal stay out of the ledger while the
-- history replaces them; history on or after the cut-over never shows.
CREATE OR REPLACE VIEW fin_v_ledger AS
SELECT g.line_id::text AS line_id, g.legal_entity_id, g.journal_id, g.journal_number, g.journal_date, g.period_id,
       g.journal_type, g.source_type, g.source_id, g.source_ref, g.journal_description, g.line_no, g.account_id,
       g.account_code, g.account_name, g.account_type, g.subtype, g.normal_balance, g.description, g.debit, g.credit,
       g.customer_id, g.supplier_id, g.product_sku, g.branch_id, g.department_id, g.cost_centre_id, g.posted_at, g.posted_by,
       'ROY'::text AS origin
FROM fin_v_general_ledger g
LEFT JOIN fin_settings s ON s.legal_entity_id = g.legal_entity_id
WHERE NOT (g.journal_type IN ('OPENING', 'REVERSAL') AND g.source_ref = 'SAGE-TB' AND COALESCE(s.history_replaces_opening, FALSE))
UNION ALL
SELECT 'S' || l.id::text, l.legal_entity_id, NULL::uuid, 'SAGE ' || l.jrnl || COALESCE(' ' || NULLIF(l.reference, ''), ''),
       l.txn_date, NULL::uuid, 'HISTORY', 'SAGE_GL', l.voucher, NULLIF(l.reference, ''), l.description, l.row_no, l.account_id,
       a.code, a.name, a.account_type, a.subtype, a.normal_balance, l.description, l.debit, l.credit,
       l.customer_id, l.supplier_id, NULL::text, NULL::uuid, NULL::uuid, NULL::uuid, NULL::timestamptz, 'Sage 50',
       'SAGE'::text
FROM fin_sage_gl_lines l
JOIN fin_accounts a ON a.id = l.account_id
JOIN fin_settings s ON s.legal_entity_id = l.legal_entity_id AND s.history_replaces_opening
WHERE s.cutover_date IS NULL OR l.txn_date < s.cutover_date;

-- A Hope payer can have several Sage accounts (Mansard was billed both as an HMO
-- and under NHIS); each Sage account belongs to one payer. Reports reconcile per
-- payer across all its accounts.
CREATE TABLE IF NOT EXISTS fin_hope_payer_accounts (
    customer_id   BIGINT PRIMARY KEY REFERENCES fin_customers(id) ON DELETE CASCADE,
    tariff_id     INTEGER NOT NULL REFERENCES fin_hope_payers(tariff_id) ON DELETE CASCADE,
    match_method  TEXT NOT NULL,
    linked_by     TEXT NOT NULL DEFAULT 'rule'
);
CREATE INDEX IF NOT EXISTS idx_fin_hope_payer_accounts_payer ON fin_hope_payer_accounts (tariff_id);

-- Credit Control's alert rules and the alerts they raise (the page and its API
-- existed; the tables never did, so the Alerts tab always failed).
CREATE TABLE IF NOT EXISTS fin_ar_alert_rules (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    threshold_amount  NUMERIC(16,2) NOT NULL CHECK (threshold_amount > 0),
    days_overdue_min  INTEGER NOT NULL DEFAULT 30,
    customer_id       TEXT,
    description       TEXT,
    notify_emails     TEXT[] NOT NULL DEFAULT '{}',
    is_active         BOOLEAN NOT NULL DEFAULT TRUE,
    created_by        TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS fin_ar_alert_events (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rule_id             UUID REFERENCES fin_ar_alert_rules(id) ON DELETE CASCADE,
    customer_id         TEXT,
    customer_name       TEXT,
    outstanding_balance NUMERIC(16,2),
    days_overdue        INTEGER,
    triggered_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    acknowledged        BOOLEAN NOT NULL DEFAULT FALSE,
    acknowledged_by     TEXT,
    acknowledged_at     TIMESTAMPTZ
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_fin_ar_alert_open ON fin_ar_alert_events (rule_id, customer_id) WHERE NOT acknowledged;
