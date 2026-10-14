-- =============================================================================
-- Migration 221 - Roy Books: hospital chart template, posting rules, calendar
-- =============================================================================
-- Royan's real chart of accounts lives in its Sage 50 company (the 2024
-- year-end .ptb backup is on file; its exports have not been received yet).
-- Until the Sage transfer loads that chart (Setup > Sage transfer: COA ->
-- trial balance -> open AR/AP), Roy Books runs on this HOSPITAL TEMPLATE so
-- every workflow can post and be tested end to end.
--
-- How the template gives way to the real chart:
--   * the Sage COA loader upserts by code, so any Sage account with the same
--     code simply takes over the template account;
--   * posting rules point at accounts through fin_account_mappings, never by
--     code in Python, so the accountant re-points a rule (Setup > Posting
--     rules) without a code change;
--   * template accounts that end up unused are deactivated, not deleted.
-- Every template account says so in its description, so nobody mistakes it
-- for a figure the accountant signed off.
-- Seeding is skipped entirely when the entity already has accounts.
-- =============================================================================

-- The seed is a function so the golden tests can build the same hospital
-- books on a throwaway entity inside a rolled-back transaction.
CREATE OR REPLACE FUNCTION fin_seed_hospital_template(v_entity UUID, v_year INT DEFAULT 2026) RETURNS VOID AS $$
DECLARE
    v_fy     UUID;
    v_m      INT;
BEGIN

    -- -----------------------------------------------------------------------
    -- Departments (dimension on journal lines) mirror royan_departments.
    -- -----------------------------------------------------------------------
    INSERT INTO fin_departments (legal_entity_id, code, name)
    SELECT v_entity, d.code, d.name FROM royan_departments d WHERE d.code IS NOT NULL
    ON CONFLICT (legal_entity_id, code) DO NOTHING;

    IF EXISTS (SELECT 1 FROM fin_accounts WHERE legal_entity_id=v_entity) THEN
        RAISE NOTICE 'Roy Books: chart already present, template not seeded';
        RETURN;
    END IF;

    -- -----------------------------------------------------------------------
    -- Chart of accounts (Sage-style 5-digit codes)
    -- -----------------------------------------------------------------------
    INSERT INTO fin_accounts (legal_entity_id, code, name, account_type, subtype, normal_balance, is_control, description, created_by)
    SELECT v_entity, a.code, a.name, a.t, a.s, a.nb, a.ctl,
           'Roy Books hospital template - confirm against the Sage chart', 'migration-221'
    FROM (VALUES
        -- Cash & bank
        ('10100','Cash - Main Cashier',                 'ASSET','CASH','DEBIT',FALSE),
        ('10150','Petty Cash',                          'ASSET','CASH','DEBIT',FALSE),
        ('10200','POS / Card Settlement',               'ASSET','CASH','DEBIT',FALSE),
        ('10300','Bank - Main Operating Account',       'ASSET','CASH','DEBIT',FALSE),
        -- Receivables
        ('11000','Accounts Receivable - Patients',      'ASSET','RECEIVABLE','DEBIT',TRUE),
        ('11100','Accounts Receivable - HMOs & Insurers','ASSET','RECEIVABLE','DEBIT',TRUE),
        ('11500','Staff Advances & Loans',              'ASSET','OTHER_CURRENT_ASSET','DEBIT',FALSE),
        ('11600','Withholding Tax Receivable',          'ASSET','OTHER_CURRENT_ASSET','DEBIT',FALSE),
        -- Stock
        ('12000','Inventory - Pharmacy',                'ASSET','INVENTORY','DEBIT',TRUE),
        ('12100','Inventory - Medical Consumables',     'ASSET','INVENTORY','DEBIT',TRUE),
        ('12200','Inventory - Laboratory Reagents',     'ASSET','INVENTORY','DEBIT',TRUE),
        ('12990','Stock on Loan',                       'ASSET','OTHER_CURRENT_ASSET','DEBIT',FALSE),
        ('13000','Prepayments',                         'ASSET','OTHER_CURRENT_ASSET','DEBIT',FALSE),
        ('13900','Suspense Account',                    'ASSET','OTHER_CURRENT_ASSET','DEBIT',FALSE),
        -- Fixed assets
        ('15000','Land & Buildings',                    'ASSET','FIXED_ASSET','DEBIT',FALSE),
        ('15100','Medical Equipment',                   'ASSET','FIXED_ASSET','DEBIT',FALSE),
        ('15200','Furniture & Fittings',                'ASSET','FIXED_ASSET','DEBIT',FALSE),
        ('15300','Office & IT Equipment',               'ASSET','FIXED_ASSET','DEBIT',FALSE),
        ('15400','Motor Vehicles & Ambulances',         'ASSET','FIXED_ASSET','DEBIT',FALSE),
        ('15500','Plant & Machinery (Generators)',      'ASSET','FIXED_ASSET','DEBIT',FALSE),
        ('17000','Accum. Depreciation - Buildings',     'ASSET','ACCUMULATED_DEPRECIATION','CREDIT',FALSE),
        ('17100','Accum. Depreciation - Medical Equipment','ASSET','ACCUMULATED_DEPRECIATION','CREDIT',FALSE),
        ('17200','Accum. Depreciation - Furniture',     'ASSET','ACCUMULATED_DEPRECIATION','CREDIT',FALSE),
        ('17300','Accum. Depreciation - Office & IT',   'ASSET','ACCUMULATED_DEPRECIATION','CREDIT',FALSE),
        ('17400','Accum. Depreciation - Vehicles',      'ASSET','ACCUMULATED_DEPRECIATION','CREDIT',FALSE),
        ('17500','Accum. Depreciation - Plant',         'ASSET','ACCUMULATED_DEPRECIATION','CREDIT',FALSE),
        -- Liabilities
        ('20000','Accounts Payable - Suppliers',        'LIABILITY','PAYABLE','CREDIT',TRUE),
        ('21000','Accrued Expenses',                    'LIABILITY','OTHER_CURRENT_LIABILITY','CREDIT',FALSE),
        ('21100','Goods Received Not Invoiced',         'LIABILITY','OTHER_CURRENT_LIABILITY','CREDIT',FALSE),
        ('21500','Patient Deposits & Advances',         'LIABILITY','OTHER_CURRENT_LIABILITY','CREDIT',FALSE),
        ('22000','Consultant Fees Payable',             'LIABILITY','OTHER_CURRENT_LIABILITY','CREDIT',FALSE),
        ('23000','PAYE Payable',                        'LIABILITY','OTHER_CURRENT_LIABILITY','CREDIT',FALSE),
        ('23100','Pension Payable',                     'LIABILITY','OTHER_CURRENT_LIABILITY','CREDIT',FALSE),
        ('23200','NHF Payable',                         'LIABILITY','OTHER_CURRENT_LIABILITY','CREDIT',FALSE),
        ('23700','Withholding Tax Payable',             'LIABILITY','OTHER_CURRENT_LIABILITY','CREDIT',FALSE),
        ('23800','VAT Payable',                         'LIABILITY','OTHER_CURRENT_LIABILITY','CREDIT',FALSE),
        ('24000','Salaries Payable',                    'LIABILITY','OTHER_CURRENT_LIABILITY','CREDIT',FALSE),
        ('27000','Long-term Loans',                     'LIABILITY','LONG_TERM_LIABILITY','CREDIT',FALSE),
        -- Equity
        ('30000','Share Capital',                       'EQUITY','EQUITY','CREDIT',FALSE),
        ('39004','Opening Balance Equity',              'EQUITY','EQUITY','CREDIT',FALSE),
        ('39005','Retained Earnings',                   'EQUITY','RETAINED_EARNINGS','CREDIT',FALSE),
        -- Revenue by service line
        ('40100','Consultation Fees',                   'REVENUE','SALES','CREDIT',FALSE),
        ('40200','Laboratory Income',                   'REVENUE','SALES','CREDIT',FALSE),
        ('40300','Radiology & Imaging Income',          'REVENUE','SALES','CREDIT',FALSE),
        ('40400','Pharmacy Sales',                      'REVENUE','SALES','CREDIT',FALSE),
        ('40500','Ward & Accommodation Income',         'REVENUE','SALES','CREDIT',FALSE),
        ('40600','Nursing Care Income',                 'REVENUE','SALES','CREDIT',FALSE),
        ('40700','Surgery & Procedure Income',          'REVENUE','SALES','CREDIT',FALSE),
        ('40800','Maternity & Delivery Income',         'REVENUE','SALES','CREDIT',FALSE),
        ('40900','Other Medical Services',              'REVENUE','SALES','CREDIT',FALSE),
        ('48000','Sales Returns & Allowances',          'REVENUE','SALES','CREDIT',FALSE),
        ('49000','Discounts Allowed',                   'REVENUE','SALES','CREDIT',FALSE),
        ('49100','HMO Disallowances',                   'REVENUE','SALES','CREDIT',FALSE),
        ('41000','Other Income',                        'REVENUE','OTHER_INCOME','CREDIT',FALSE),
        ('41100','Interest Income',                     'REVENUE','OTHER_INCOME','CREDIT',FALSE),
        -- Cost of sales
        ('50000','Cost of Drugs Dispensed',             'EXPENSE','COST_OF_SALES','DEBIT',FALSE),
        ('50100','Cost of Consumables Used',            'EXPENSE','COST_OF_SALES','DEBIT',FALSE),
        ('50200','Laboratory Reagents Used',            'EXPENSE','COST_OF_SALES','DEBIT',FALSE),
        ('58500','Stock Adjustments & Write-offs',      'EXPENSE','COST_OF_SALES','DEBIT',FALSE),
        -- Operating expenses
        ('60000','Salaries & Wages',                    'EXPENSE','OPERATING_EXPENSE','DEBIT',FALSE),
        ('60100','Pension - Employer Contribution',     'EXPENSE','OPERATING_EXPENSE','DEBIT',FALSE),
        ('60200','Consultant & Locum Fees',             'EXPENSE','OPERATING_EXPENSE','DEBIT',FALSE),
        ('61000','Rent & Rates',                        'EXPENSE','OPERATING_EXPENSE','DEBIT',FALSE),
        ('61100','Electricity & Diesel',                'EXPENSE','OPERATING_EXPENSE','DEBIT',FALSE),
        ('61200','Water',                               'EXPENSE','OPERATING_EXPENSE','DEBIT',FALSE),
        ('61300','Repairs & Maintenance',               'EXPENSE','OPERATING_EXPENSE','DEBIT',FALSE),
        ('61400','Medical Equipment Maintenance',       'EXPENSE','OPERATING_EXPENSE','DEBIT',FALSE),
        ('62000','Cleaning & Laundry',                  'EXPENSE','OPERATING_EXPENSE','DEBIT',FALSE),
        ('62100','Catering - Patient Meals',            'EXPENSE','OPERATING_EXPENSE','DEBIT',FALSE),
        ('62200','Bank Charges',                        'EXPENSE','OPERATING_EXPENSE','DEBIT',FALSE),
        ('62300','Telephone & Internet',                'EXPENSE','OPERATING_EXPENSE','DEBIT',FALSE),
        ('62400','Insurance',                           'EXPENSE','OPERATING_EXPENSE','DEBIT',FALSE),
        ('62500','Professional Fees (Audit & Legal)',   'EXPENSE','OPERATING_EXPENSE','DEBIT',FALSE),
        ('62600','Advertising & Business Promotion',    'EXPENSE','OPERATING_EXPENSE','DEBIT',FALSE),
        ('62700','Transport & Travel',                  'EXPENSE','OPERATING_EXPENSE','DEBIT',FALSE),
        ('62800','Printing & Stationery',               'EXPENSE','OPERATING_EXPENSE','DEBIT',FALSE),
        ('62900','Licences & Regulatory Fees',          'EXPENSE','OPERATING_EXPENSE','DEBIT',FALSE),
        ('63000','Patient Waivers & Charity Care',      'EXPENSE','OPERATING_EXPENSE','DEBIT',FALSE),
        ('63100','Bad Debts Written Off',               'EXPENSE','OPERATING_EXPENSE','DEBIT',FALSE),
        ('64000','Depreciation - Buildings',            'EXPENSE','OPERATING_EXPENSE','DEBIT',FALSE),
        ('64100','Depreciation - Medical Equipment',    'EXPENSE','OPERATING_EXPENSE','DEBIT',FALSE),
        ('64200','Depreciation - Furniture',            'EXPENSE','OPERATING_EXPENSE','DEBIT',FALSE),
        ('64300','Depreciation - Office & IT',          'EXPENSE','OPERATING_EXPENSE','DEBIT',FALSE),
        ('64400','Depreciation - Vehicles',             'EXPENSE','OPERATING_EXPENSE','DEBIT',FALSE),
        ('64500','Depreciation - Plant',                'EXPENSE','OPERATING_EXPENSE','DEBIT',FALSE),
        ('69000','Miscellaneous Expenses',              'EXPENSE','OPERATING_EXPENSE','DEBIT',FALSE),
        ('90000','Gain / Loss on Asset Disposal',       'EXPENSE','OTHER_EXPENSE','DEBIT',FALSE),
        ('91000','Interest Expense',                    'EXPENSE','OTHER_EXPENSE','DEBIT',FALSE)
    ) AS a(code, name, t, s, nb, ctl);

    -- -----------------------------------------------------------------------
    -- Posting rules: business event -> account (rules.MAPPING_KEYS)
    -- -----------------------------------------------------------------------
    INSERT INTO fin_account_mappings (legal_entity_id, mapping_key, account_id, note, updated_by)
    SELECT v_entity, m.k, a.id, 'Hospital template default', 'migration-221'
    FROM (VALUES
        ('AR_CONTROL','11000'), ('AR_HMO','11100'), ('AP_CONTROL','20000'),
        ('REVENUE_CONSULTATION','40100'), ('REVENUE_LAB','40200'), ('REVENUE_RADIOLOGY','40300'),
        ('REVENUE_PHARMACY','40400'), ('REVENUE_WARD','40500'), ('REVENUE_NURSING','40600'),
        ('REVENUE_PROCEDURE','40700'), ('REVENUE_MATERNITY','40800'), ('REVENUE_OTHER','40900'),
        ('SALES_DEFAULT','40400'), ('SERVICE_INCOME','40900'),
        ('DELIVERY_INCOME','41000'), ('OTHER_CHARGE_INCOME','41000'),
        ('SALES_DISCOUNT','49000'), ('SALES_RETURNS','48000'), ('HMO_DISALLOWANCE','49100'),
        ('PATIENT_WAIVERS','63000'), ('BAD_DEBTS','63100'),
        ('INVENTORY_DEFAULT','12000'), ('COGS_DEFAULT','50000'), ('CONSUMABLES_EXPENSE','50100'),
        ('INVENTORY_ADJUSTMENT','58500'), ('STOCK_ON_LOAN','12990'),
        ('PURCHASE_EXPENSE_DEFAULT','69000'), ('GOODS_RECEIVED_NOT_INVOICED','21100'),
        ('WHT_SUFFERED','11600'), ('WHT_PAYABLE','23700'), ('BANK_CHARGES','62200'),
        ('RETAINED_EARNINGS','39005'), ('OPENING_BALANCE_EQUITY','39004'), ('ASSET_DISPOSAL','90000')
    ) AS m(k, code)
    JOIN fin_accounts a ON a.legal_entity_id=v_entity AND a.code=m.code;

    -- -----------------------------------------------------------------------
    -- Bank / cash accounts, and which one each cashier method lands in
    -- -----------------------------------------------------------------------
    INSERT INTO fin_bank_accounts (legal_entity_id, gl_account_id, name, kind)
    SELECT v_entity, a.id, b.name, b.kind
    FROM (VALUES ('10100','Cash - Main Cashier','CASH'), ('10150','Petty Cash','PETTY_CASH'),
                 ('10200','POS / Card Settlement','BANK'), ('10300','Bank - Main Operating Account','BANK')) AS b(code, name, kind)
    JOIN fin_accounts a ON a.legal_entity_id=v_entity AND a.code=b.code;

    UPDATE fin_settings s SET receipt_accounts = jsonb_build_object(
            'cash',     (SELECT b.id FROM fin_bank_accounts b JOIN fin_accounts a ON a.id=b.gl_account_id WHERE b.legal_entity_id=v_entity AND a.code='10100'),
            'card',     (SELECT b.id FROM fin_bank_accounts b JOIN fin_accounts a ON a.id=b.gl_account_id WHERE b.legal_entity_id=v_entity AND a.code='10200'),
            'transfer', (SELECT b.id FROM fin_bank_accounts b JOIN fin_accounts a ON a.id=b.gl_account_id WHERE b.legal_entity_id=v_entity AND a.code='10300'),
            'other',    (SELECT b.id FROM fin_bank_accounts b JOIN fin_accounts a ON a.id=b.gl_account_id WHERE b.legal_entity_id=v_entity AND a.code='10300'))
     WHERE s.legal_entity_id=v_entity;

    -- -----------------------------------------------------------------------
    -- Fixed-asset categories
    -- -----------------------------------------------------------------------
    INSERT INTO fin_asset_categories (legal_entity_id, code, name, asset_account_id, accum_dep_account_id,
                                      dep_expense_account_id, default_life_months, depreciable)
    SELECT v_entity, c.code, c.name, a.id, ad.id, de.id, c.life, c.dep
    FROM (VALUES ('BUILD','Buildings','15000','17000','64000',600,TRUE),
                 ('MEDEQ','Medical equipment','15100','17100','64100',84,TRUE),
                 ('FURN','Furniture & fittings','15200','17200','64200',60,TRUE),
                 ('OFFEQ','Office & IT equipment','15300','17300','64300',36,TRUE),
                 ('MV','Motor vehicles & ambulances','15400','17400','64400',48,TRUE),
                 ('PM','Plant & machinery','15500','17500','64500',60,TRUE)) AS c(code, name, asset, accum, exp, life, dep)
    JOIN fin_accounts a  ON a.legal_entity_id=v_entity AND a.code=c.asset
    JOIN fin_accounts ad ON ad.legal_entity_id=v_entity AND ad.code=c.accum
    JOIN fin_accounts de ON de.legal_entity_id=v_entity AND de.code=c.exp;

    -- -----------------------------------------------------------------------
    -- Fiscal calendar: FY2026, twelve monthly periods, all open
    -- -----------------------------------------------------------------------
    INSERT INTO fin_fiscal_years (legal_entity_id, name, start_date, end_date)
    VALUES (v_entity, 'FY' || v_year, make_date(v_year, 1, 1), make_date(v_year, 12, 31))
    ON CONFLICT (legal_entity_id, start_date) DO NOTHING
    RETURNING id INTO v_fy;
    IF v_fy IS NOT NULL THEN
        FOR v_m IN 1..12 LOOP
            INSERT INTO fin_periods (legal_entity_id, fiscal_year_id, period_number, name, start_date, end_date)
            VALUES (v_entity, v_fy, v_m, to_char(make_date(v_year, v_m, 1), 'Mon YYYY'),
                    make_date(v_year, v_m, 1), (make_date(v_year, v_m, 1) + INTERVAL '1 month - 1 day')::date);
        END LOOP;
    END IF;
END $$ LANGUAGE plpgsql;

-- Seed Royan Hospital's own books.
DO $$
DECLARE
    v_entity UUID;
BEGIN
    SELECT e.id INTO v_entity FROM fin_legal_entities e JOIN fin_organizations o ON o.id=e.organization_id
     WHERE o.code='ROYAN' AND e.code='RHL';
    IF v_entity IS NULL THEN
        RAISE EXCEPTION 'Royan legal entity missing - apply 220_fin_modules.sql first';
    END IF;
    PERFORM fin_seed_hospital_template(v_entity, 2026);
END $$;

-- ---------------------------------------------------------------------------
-- Legacy history from Hope (display and lineage only - never posts, never
-- changes a balance; the same rule ACE applies to Sage history).
-- Loaded by `python -m src.fin.hope_history` from the Hope staging database.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS fin_hist_purchase_lines (
    id               BIGSERIAL PRIMARY KEY,
    legal_entity_id  UUID NOT NULL REFERENCES fin_legal_entities(id),
    source           TEXT NOT NULL DEFAULT 'HOPE',
    source_line_id   TEXT NOT NULL,
    po_number        TEXT,
    grn_number       TEXT,
    supplier_invoice TEXT,
    supplier_id      UUID REFERENCES suppliers(id),
    supplier_name    TEXT,
    received_date    DATE,
    sku              TEXT,             -- fin_products.sku when the item is matched
    description      TEXT,
    batch_number     TEXT,
    expiry_date      DATE,
    quantity         NUMERIC(18,4),
    unit_cost        NUMERIC(20,6),
    amount           NUMERIC(20,2),
    UNIQUE (source, source_line_id)
);
CREATE INDEX IF NOT EXISTS idx_fin_hist_purch_supplier ON fin_hist_purchase_lines (supplier_id, received_date);
CREATE INDEX IF NOT EXISTS idx_fin_hist_purch_sku ON fin_hist_purchase_lines (sku, received_date);

-- Revenue history by month and service line, read straight from the Hope
-- billing lines already in the database (no copy). Lines above N50m are
-- excluded as mis-keyed (the 2020 spike is a handful of such lines) and
-- counted separately so the exclusion is visible, not silent.
CREATE OR REPLACE VIEW fin_v_hope_revenue_monthly AS
SELECT date_trunc('month', t.transaction_date)::date AS month,
       COALESCE(c.name, 'Uncategorised') AS service_line,
       COUNT(*) FILTER (WHERE t.amount <= 50000000)                  AS lines,
       COALESCE(SUM(t.amount) FILTER (WHERE t.amount <= 50000000),0) AS amount,
       COALESCE(SUM(t.discount_amount) FILTER (WHERE t.amount <= 50000000),0) AS discount,
       COUNT(*) FILTER (WHERE t.amount > 50000000)                   AS excluded_lines,
       COALESCE(SUM(t.amount) FILTER (WHERE t.amount > 50000000),0)  AS excluded_amount
FROM royan_billing_transactions t
LEFT JOIN royan_service_categories c ON c.id::text = t.payment_category
WHERE t.transaction_date IS NOT NULL AND t.amount > 0
GROUP BY 1, 2;

-- Money received per month and channel from Hope (receipts + cashier payments).
CREATE OR REPLACE VIEW fin_v_hope_receipts_monthly AS
SELECT date_trunc('month', p.received_at)::date AS month,
       p.payment_method AS channel,
       COUNT(*) AS receipts,
       SUM(p.amount) AS amount
FROM royan_payments p
WHERE p.external_source = 'hope' AND p.amount <= 50000000
GROUP BY 1, 2;
