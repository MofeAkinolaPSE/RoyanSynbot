-- 226: front desk check-in records what the desk decided: how urgent the patient looked on arrival,
-- and (optionally) the doctor and consulting room they were sent to. Additive only.
BEGIN;
ALTER TABLE royan_encounters
    ADD COLUMN IF NOT EXISTS arrival_priority text
        CHECK (arrival_priority IS NULL OR arrival_priority IN ('normal', 'urgent', 'emergency'));
COMMIT;
