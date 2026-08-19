-- 175_queue_nurse_and_patient_type.sql
-- Hope-parity pass: the Outpatient Dashboard screenshots show a per-patient
-- nurse-assignment dropdown and a Tariff (payer type) column that this app
-- has no schema for at all. Adds both.

ROLLBACK;
BEGIN;

ALTER TABLE royan_encounters
    ADD COLUMN IF NOT EXISTS assigned_nurse_id uuid REFERENCES royan_staff(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_royan_encounters_assigned_nurse ON royan_encounters(assigned_nurse_id);

-- Patient Type (Cash / Private / HMO) — confirmed as a real 3-way category
-- on Hope's Patient Card screen ("Patient Type: Cash"), distinct from
-- whether an HMO/insurance record is attached.
ALTER TABLE royan_patients
    ADD COLUMN IF NOT EXISTS patient_type text;
ALTER TABLE royan_patients DROP CONSTRAINT IF EXISTS royan_patients_patient_type_check;
ALTER TABLE royan_patients ADD CONSTRAINT royan_patients_patient_type_check
    CHECK (patient_type IS NULL OR patient_type = ANY (ARRAY['cash','private','hmo']));

COMMIT;
