-- 167_payroll_line_items.sql
-- Royan Hospital: add the line-item columns the HR Payroll UI/router already
-- assumed but royan_payroll_records never had (migration 138 only defined
-- gross_salary/overtime_hours/overtime_rate/deductions/net_salary — every
-- payroll creation was failing on these missing columns). period_month/
-- period_year, the overtime hours*rate shape, and the draft/approved/paid
-- status are kept as-is (already coherent designs) — only the genuinely
-- missing fields are added here.

ROLLBACK;
BEGIN;

ALTER TABLE public.royan_payroll_records
    ADD COLUMN IF NOT EXISTS allowances     numeric(14,2) NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS tax            numeric(14,2) NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS pension        numeric(14,2) NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS payment_date   date,
    ADD COLUMN IF NOT EXISTS payment_method text,
    ADD COLUMN IF NOT EXISTS notes          text;

COMMIT;
