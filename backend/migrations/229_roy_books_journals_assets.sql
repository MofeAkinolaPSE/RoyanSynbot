-- =============================================================================
-- Migration 229 - Roy Books: journals by type, delete entry, assets from payments
-- =============================================================================
-- From the ACE Books -> Roy Books implementation standard (Oct 2026):
--   * fin_journal_code(): the book of original entry (Sage journal code) of every
--     posting - one table, the same as src/fin/journal_map.py (a test keeps them equal).
--   * fin_v_ledger gains `jrnl` (Sage's own code on history lines, fin_journal_code on
--     Roy Books postings) so the General Ledger's Jrnl column and the eight Journals
--     by type read one answer, and `hidden`: a posted journal deleted by a same-day
--     reversal ("Delete entry") and that reversal are left out of ledger detail. They
--     still net to nil in every balance and stay in Journal entries and the audit trail.
--   * fin_fixed_assets.source_line: the payment / voucher line an asset was bought on,
--     so a purchase is registered once and the register entry opens its payment.
-- =============================================================================

CREATE OR REPLACE FUNCTION fin_journal_code(p_source_type TEXT, p_source_id TEXT) RETURNS TEXT
LANGUAGE sql STABLE AS $$
  SELECT CASE WHEN p_source_type='CASH_VOUCHER' THEN COALESCE((SELECT CASE v.kind WHEN 'SPEND' THEN 'CDJ' WHEN 'RECEIVE' THEN 'CRJ' WHEN 'TRANSFER' THEN 'GENJ' END
              FROM fin_cash_vouchers v WHERE v.id::text = p_source_id), 'CDJ')
         ELSE CASE COALESCE(p_source_type, '') WHEN 'SALES_INVOICE' THEN 'SJ' WHEN 'CREDIT_NOTE' THEN 'SJ' WHEN 'CUSTOMER_RECEIPT' THEN 'CRJ' WHEN 'SUPPLIER_BILL' THEN 'PJ' WHEN 'DEBIT_NOTE' THEN 'PJ' WHEN 'PHARMACY_RECEIPT' THEN 'PJ' WHEN 'SUPPLIER_PAYMENT' THEN 'CDJ' WHEN 'CUSTOMER_REFUND' THEN 'CDJ' WHEN 'PAYROLL_PAYMENT' THEN 'CDJ' WHEN 'CASH_VOUCHER' THEN 'CDJ' WHEN 'DISPENSING' THEN 'COGS' WHEN 'DISPENSE_RETURN' THEN 'COGS' WHEN 'STOCK_ADJUSTMENT' THEN 'INAJ' WHEN 'STOCK_COUNT' THEN 'INAJ' WHEN 'STOCK_LOAN' THEN 'INAJ' WHEN 'STOCK_LOAN_RETURN' THEN 'INAJ' WHEN 'STOCK_LOAN_WRITEOFF' THEN 'INAJ' WHEN 'PHARMACY_ADJUST' THEN 'INAJ' WHEN 'FIXED_ASSET' THEN 'FA' WHEN 'DEPRECIATION_RUN' THEN 'FA' WHEN 'FIXED_ASSET_DISPOSAL' THEN 'FA' WHEN 'MANUAL_JOURNAL' THEN 'GENJ' WHEN 'MIGRATION' THEN 'GENJ' WHEN 'YEAR_END' THEN 'GENJ' WHEN 'PAYROLL' THEN 'GENJ' WHEN 'DATA_CORRECTION' THEN 'ADJ' ELSE 'GENJ' END END
$$;

CREATE OR REPLACE VIEW fin_v_ledger AS
SELECT g.line_id::text AS line_id, g.legal_entity_id, g.journal_id, g.journal_number, g.journal_date, g.period_id,
       g.journal_type, g.source_type, g.source_id, g.source_ref, g.journal_description, g.line_no, g.account_id,
       g.account_code, g.account_name, g.account_type, g.subtype, g.normal_balance, g.description, g.debit, g.credit,
       g.customer_id, g.supplier_id, g.product_sku, g.branch_id, g.department_id, g.cost_centre_id, g.posted_at, g.posted_by,
       'ROY'::text AS origin,
       fin_journal_code(g.source_type, g.source_id::text) AS jrnl,
       (EXISTS (SELECT 1 FROM fin_journals o JOIN fin_journals r ON r.id = o.reversed_by_id
                WHERE o.id = g.journal_id AND r.journal_date = o.journal_date)
        OR EXISTS (SELECT 1 FROM fin_journals r JOIN fin_journals o ON o.id = r.reversal_of_id
                   WHERE r.id = g.journal_id AND r.journal_date = o.journal_date)) AS hidden
FROM fin_v_general_ledger g
LEFT JOIN fin_settings s ON s.legal_entity_id = g.legal_entity_id
WHERE NOT (g.journal_type IN ('OPENING', 'REVERSAL') AND g.source_ref = 'SAGE-TB' AND COALESCE(s.history_replaces_opening, FALSE))
UNION ALL
SELECT 'S' || l.id::text, l.legal_entity_id, NULL::uuid, 'SAGE ' || l.jrnl || COALESCE(' ' || NULLIF(l.reference, ''), ''),
       l.txn_date, NULL::uuid, 'HISTORY', 'SAGE_GL', l.voucher, NULLIF(l.reference, ''), l.description, l.row_no, l.account_id,
       a.code, a.name, a.account_type, a.subtype, a.normal_balance, l.description, l.debit, l.credit,
       l.customer_id, l.supplier_id, NULL::text, NULL::uuid, NULL::uuid, NULL::uuid, NULL::timestamptz, 'Sage 50',
       'SAGE'::text, l.jrnl, FALSE
FROM fin_sage_gl_lines l
JOIN fin_accounts a ON a.id = l.account_id
JOIN fin_settings s ON s.legal_entity_id = l.legal_entity_id AND s.history_replaces_opening
WHERE s.cutover_date IS NULL OR l.txn_date < s.cutover_date;

ALTER TABLE fin_fixed_assets ADD COLUMN IF NOT EXISTS source_line TEXT;
ALTER TABLE fin_fixed_assets ADD COLUMN IF NOT EXISTS funding TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS uq_fin_fixed_assets_source_line ON fin_fixed_assets (legal_entity_id, source_line)
    WHERE source_line IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_fin_sage_gl_lines_jrnl ON fin_sage_gl_lines (legal_entity_id, jrnl, txn_date);
CREATE INDEX IF NOT EXISTS idx_fin_sage_gl_lines_acct_date ON fin_sage_gl_lines (account_id, txn_date);
