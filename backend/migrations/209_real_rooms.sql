-- Migration 209: real rooms, seeded from Hope's own ward history
-- ============================================================================
--
-- "The wards and beds doesn't expose the rooms as Room101, Room102 as specified
-- in the DB — let's update that so we actually represent the actual room names."
--
-- WHERE THE ROOM NAMES COME FROM
-- ------------------------------
-- royan_ward_stay_history holds 11,313 migrated admissions carrying the real
-- ward / room / bed structure Royan actually used:
--
--     First Floor         10 rooms, 13 beds   (Room101 .. Room108)
--     Ground Floor         6 rooms, 13 beds   (Room1-3, General ward R1/R2)
--     NEONATAL             2 rooms,  7 beds
--     COT/Mothersbedside   2 rooms,  8 beds
--     Stepdown Unit        1 room,   1 bed
--
-- Ward names match royan_wards exactly, so rooms link without guesswork. The
-- live configuration had 24 placeholder beds numbered 1-10 within each ward and
-- no room identity at all — which is why the Wards page showed "bed 3" rather
-- than "Room104".
--
-- Migration 208 put the nightly rate on the bed/ward because rooms did not
-- exist. They do now, so the rate belongs on the room: 15 of the 17 room names
-- are already priced in royan_service_catalog (Room102 = 40,000, Room108 =
-- 35,000, General ward R1 = 10,500...). Bed and ward rates are kept as
-- fallbacks rather than removed, so nothing that already worked stops working.
--
-- WHY THE UNIQUE CONSTRAINT HAD TO CHANGE
-- ---------------------------------------
-- royan_beds was UNIQUE (ward_id, bed_number). Real rooms break that: First
-- Floor has a "bed 1" in Room101 AND in Room104. Bed identity is (room, number),
-- so the constraint moves. coalesce(room_id, 0) keeps it meaningful for beds
-- that have no room yet — a plain multi-column unique index would treat every
-- NULL room as distinct and allow duplicates straight back in.
--
-- EXISTING BEDS ARE NOT DELETED
-- -----------------------------
-- One bed is currently occupied. Placeholder beds are matched onto their real
-- room where the ward and number line up; anything left over keeps working
-- unroomed rather than being removed under a patient.
-- ============================================================================

BEGIN;

CREATE TABLE IF NOT EXISTS public.royan_rooms (
    id          bigserial PRIMARY KEY,
    ward_id     bigint NOT NULL REFERENCES public.royan_wards(id) ON DELETE CASCADE,
    name        text NOT NULL,
    room_type   text,
    daily_rate  numeric(14,2),
    is_active   boolean NOT NULL DEFAULT true,
    notes       text,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_room_ward_name
    ON public.royan_rooms (ward_id, lower(btrim(name)));

COMMENT ON TABLE public.royan_rooms IS
  'Real rooms, seeded from the ward/room/bed structure in royan_ward_stay_history (11,313 migrated admissions). Not invented.';
COMMENT ON COLUMN public.royan_rooms.daily_rate IS
  'Nightly charge for a bed in this room. Takes precedence over the ward rate; a bed-level rate still overrides both.';

ALTER TABLE public.royan_beds
    ADD COLUMN IF NOT EXISTS room_id bigint REFERENCES public.royan_rooms(id) ON DELETE SET NULL;

-- ── Seed the rooms ──────────────────────────────────────────────────────────
INSERT INTO public.royan_rooms (ward_id, name)
SELECT DISTINCT w.id, btrim(h.room_name)
FROM public.royan_ward_stay_history h
JOIN public.royan_wards w ON lower(btrim(w.name)) = lower(btrim(h.ward_name))
WHERE h.room_name IS NOT NULL AND btrim(h.room_name) <> ''
ON CONFLICT DO NOTHING;

-- ── Price them from the service catalogue ───────────────────────────────────
-- Space-insensitive: Hope writes "Room101" while the catalogue has "Room 101".
UPDATE public.royan_rooms r
SET daily_rate = s.base_price,
    updated_at = now()
FROM public.royan_service_catalog s
WHERE s.category = 'ward'
  AND s.base_price > 0
  AND replace(lower(btrim(s.name)), ' ', '') = replace(lower(btrim(r.name)), ' ', '')
  AND r.daily_rate IS NULL;

-- ── Bed identity is (room, number), not (ward, number) ──────────────────────
ALTER TABLE public.royan_beds
    DROP CONSTRAINT IF EXISTS royan_beds_ward_id_bed_number_key;

CREATE UNIQUE INDEX IF NOT EXISTS uq_bed_room_number
    ON public.royan_beds (ward_id, coalesce(room_id, 0), bed_number);

-- ── Attach existing placeholder beds to a room where it is unambiguous ──────
-- Only when the ward has exactly ONE room carrying that bed number. Where
-- several rooms share it (First Floor "bed 1" exists in Room101 and Room104),
-- the bed is left unroomed for staff to place rather than assigned by guess.
WITH candidate AS (
    SELECT w.id AS ward_id, btrim(h.bed_label) AS bed_number,
           min(r.id) AS room_id, count(DISTINCT r.id) AS room_count
    FROM public.royan_ward_stay_history h
    JOIN public.royan_wards w ON lower(btrim(w.name)) = lower(btrim(h.ward_name))
    JOIN public.royan_rooms r ON r.ward_id = w.id
                             AND lower(btrim(r.name)) = lower(btrim(h.room_name))
    WHERE h.bed_label IS NOT NULL AND btrim(h.bed_label) <> ''
    GROUP BY 1, 2
)
UPDATE public.royan_beds b
SET room_id = c.room_id, updated_at = now()
FROM candidate c
WHERE b.room_id IS NULL
  AND b.ward_id = c.ward_id
  AND btrim(b.bed_number) = c.bed_number
  AND c.room_count = 1;

-- ── Create the beds Hope describes that do not exist yet ────────────────────
INSERT INTO public.royan_beds (ward_id, room_id, bed_number, bed_type, status)
SELECT DISTINCT r.ward_id, r.id, btrim(h.bed_label), 'standard', 'available'
FROM public.royan_ward_stay_history h
JOIN public.royan_wards w ON lower(btrim(w.name)) = lower(btrim(h.ward_name))
JOIN public.royan_rooms r ON r.ward_id = w.id
                         AND lower(btrim(r.name)) = lower(btrim(h.room_name))
WHERE h.bed_label IS NOT NULL AND btrim(h.bed_label) <> ''
  AND NOT EXISTS (
        SELECT 1 FROM public.royan_beds b
        WHERE b.ward_id = r.ward_id AND b.room_id = r.id
          AND btrim(b.bed_number) = btrim(h.bed_label)
  )
ON CONFLICT DO NOTHING;

COMMIT;

-- Verification:
--   SELECT w.name AS ward, count(DISTINCT r.id) AS rooms, count(b.id) AS beds
--   FROM royan_wards w
--   LEFT JOIN royan_rooms r ON r.ward_id = w.id
--   LEFT JOIN royan_beds  b ON b.room_id = r.id
--   GROUP BY 1 ORDER BY 1;
--
--   SELECT name, daily_rate FROM royan_rooms ORDER BY ward_id, name;
--   SELECT count(*) FROM royan_beds WHERE room_id IS NULL;  -- unplaced beds
