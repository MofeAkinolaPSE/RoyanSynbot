-- Every stock item belongs to a department (pharmacy, lab, urology, immunisation, ward...), so every Stock page can
-- be read department by department. A department store's batches, once counted and put in the books, become products
-- and cost layers like the pharmacy's.
ALTER TABLE fin_products ADD COLUMN IF NOT EXISTS department text NOT NULL DEFAULT 'PHARMACY';
CREATE INDEX IF NOT EXISTS ix_fin_products_department ON fin_products (legal_entity_id, department);
ALTER TABLE royan_department_stock ADD COLUMN IF NOT EXISTS fin_sku text;
ALTER TABLE royan_department_stock ADD COLUMN IF NOT EXISTS fin_batch_id uuid;
-- the department stores Royan runs; a store is listed even before it holds anything, so stock can be added to it
CREATE TABLE IF NOT EXISTS royan_stores (
    code      text PRIMARY KEY,
    name      text NOT NULL,
    sort      int NOT NULL DEFAULT 100,
    is_active boolean NOT NULL DEFAULT true
);
INSERT INTO royan_stores (code, name, sort) VALUES
  ('PHARMACY','Pharmacy',1), ('LAB','Laboratory',2), ('IMMUNISATION','Immunisation',3), ('UROLOGY','Urology',4),
  ('WARD','Ward',5), ('THEATRE','Theatre',6), ('PHYSIOTHERAPY','Physiotherapy',7), ('CENTRAL_STORES','Central stores',8)
ON CONFLICT (code) DO NOTHING;
