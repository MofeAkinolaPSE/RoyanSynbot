-- 228: indexes for the queries every page load makes, sized for 30-50 laptops at once.
-- Live screens read only the hospital's own rows (external_source IS NULL); the Hope import added
-- hundreds of thousands of historical rows those screens filter out one by one. Partial indexes over
-- the native rows make the sidebar badges and worklists index lookups. Trigram indexes let patient
-- search (ILIKE '%term%' on name, MRN, phone, HMO ID) and the MCH department match use an index
-- instead of scanning every patient / encounter. Additive only; ANALYZE because the tables had never
-- been analysed since the import, so the planner was guessing.
BEGIN;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX IF NOT EXISTS ix_lab_orders_native_status ON royan_lab_orders (status, ordered_at DESC) WHERE external_source IS NULL;
CREATE INDEX IF NOT EXISTS ix_lab_orders_native_recent ON royan_lab_orders (ordered_at DESC) WHERE external_source IS NULL;
CREATE INDEX IF NOT EXISTS ix_prescriptions_native_status ON royan_prescriptions (status, prescribed_at DESC) WHERE external_source IS NULL;
CREATE INDEX IF NOT EXISTS ix_prescriptions_native_recent ON royan_prescriptions (prescribed_at DESC) WHERE external_source IS NULL;
CREATE INDEX IF NOT EXISTS ix_encounters_native_status ON royan_encounters (status, created_at DESC) WHERE external_source IS NULL;
CREATE INDEX IF NOT EXISTS ix_encounters_native_recent ON royan_encounters (created_at DESC) WHERE external_source IS NULL;

CREATE INDEX IF NOT EXISTS ix_patients_first_trgm ON royan_patients USING gin (first_name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS ix_patients_last_trgm ON royan_patients USING gin (last_name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS ix_patients_mrn_trgm ON royan_patients USING gin (mrn gin_trgm_ops);
CREATE INDEX IF NOT EXISTS ix_patients_phone_trgm ON royan_patients USING gin (phone gin_trgm_ops);
CREATE INDEX IF NOT EXISTS ix_patients_hmo_trgm ON royan_patients USING gin (hmo_id gin_trgm_ops);
CREATE INDEX IF NOT EXISTS ix_encounters_department_trgm ON royan_encounters USING gin (department gin_trgm_ops);
COMMIT;

ANALYZE;
