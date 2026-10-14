-- Scancare is its own company: its bills and receipts have their own numbers, so Royan's bill (RHB-) and receipt (RHR-)
-- sequences stay unbroken.
CREATE SEQUENCE IF NOT EXISTS scancare_bill_seq;
CREATE SEQUENCE IF NOT EXISTS scancare_receipt_seq;
CREATE OR REPLACE FUNCTION generate_scancare_bill_number() RETURNS text LANGUAGE plpgsql AS $$
BEGIN
    RETURN 'SCB-' || to_char(now(), 'YYYY') || '-' || lpad(nextval('scancare_bill_seq')::text, 6, '0');
END $$;
CREATE OR REPLACE FUNCTION generate_scancare_receipt_number() RETURNS text LANGUAGE plpgsql AS $$
BEGIN
    RETURN 'SCR-' || to_char(now(), 'YYYY') || '-' || lpad(nextval('scancare_receipt_seq')::text, 6, '0');
END $$;
