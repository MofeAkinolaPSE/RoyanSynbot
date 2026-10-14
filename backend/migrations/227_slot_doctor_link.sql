-- 227: appointments belong to a doctor by royan_staff.id, not by free text.
-- Hope's slots carried the doctor as a numeric Hope user id in doctor_name; scripts/link_slot_doctors.py
-- resolves each to the doctor's name and HR record. The original code is kept here so the link is
-- reviewable and reversible. Additive only.
BEGIN;
ALTER TABLE royan_appointment_slots ADD COLUMN IF NOT EXISTS hope_doctor_code text;
CREATE INDEX IF NOT EXISTS ix_slots_doctor_date ON royan_appointment_slots (doctor_id, slot_date);
COMMIT;
