-- A Scancare walk-in (or any client billed without a hospital visit) has a bill but no encounter.
ALTER TABLE royan_billing ALTER COLUMN encounter_id DROP NOT NULL;
ALTER TABLE royan_bill_items ALTER COLUMN encounter_id DROP NOT NULL;
