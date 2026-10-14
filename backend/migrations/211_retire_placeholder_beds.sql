-- Migration 211: retire the placeholder beds
-- ============================================================================
--
-- Migration 209 created the real rooms and their beds from Hope's own ward
-- history. The 24 synthetic beds that predated it are now duplicates: numbered
-- 1-10 within each ward, belonging to no room, and appearing on the wards page
-- as "Unassigned" alongside the real Room101/Room104 beds.
--
-- WHY DELETING IS SAFE, HAVING CHECKED
-- ------------------------------------
-- 1,026 encounters reference these beds via royan_encounters.bed_id, which is
-- ON DELETE SET NULL — so at first glance deleting would strip bed history from
-- a thousand records. Checking what that link actually says:
--
--     placeholder bed 1  "First Floor bed 1"   <- 379 encounters
--     placeholder bed 9  "Ground Floor bed 1"  <- 303 encounters
--     placeholder bed 10 "Ground Floor bed 2"  <- 165 encounters
--
-- and sampling those encounters against royan_ward_stay_history:
--
--     encounter 63744 -> linked "First Floor bed 1", really in Room104 bed 1
--     encounter 1702  -> linked "First Floor bed 1", really in Room102 bed 1
--     encounter 1899  -> linked "First Floor bed 1", really in Room103 bed 1
--
-- The link is not provenance. Hundreds of distinct historical stays were
-- collapsed onto one synthetic bed during import, so bed_id asserts a location
-- that is wrong. The true location is in royan_ward_stay_history (ward_name /
-- room_name / bed_label), which is untouched by this migration.
--
-- Nulling those bed_ids therefore removes misinformation rather than losing
-- history. Every one of the 1,026 is a Hope import (external_source IS NOT
-- NULL); no native encounter is affected.
--
-- Only unoccupied placeholders are removed. Anything with a patient in it stays
-- put — a bed is not a row to tidy while someone is lying in it.
-- ============================================================================

BEGIN;

-- Belt and braces: never delete a bed with an occupant, whatever the room
-- linkage says.
DELETE FROM public.royan_beds
WHERE room_id IS NULL
  AND current_patient_id IS NULL
  AND status <> 'occupied';

COMMIT;

-- Verification:
--   SELECT count(*) FROM royan_beds WHERE room_id IS NULL;   -- expect 0
--   SELECT w.name, count(*) FROM royan_beds b
--     JOIN royan_wards w ON w.id = b.ward_id GROUP BY 1 ORDER BY 1;
--   -- historical locations survive independently:
--   SELECT count(*) FROM royan_ward_stay_history;            -- still 11,313
