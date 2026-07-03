-- Migration 146: Link appointment slots to royan_staff via a real FK
--
-- royan_appointment_slots has only ever stored the assigned doctor as a
-- free-text doctor_name/provider_name string — there is no way to query
-- "this doctor's upcoming appointments" without a fragile name-match join.
-- Follows the exact FK-enrichment pattern already used in migration 131 for
-- royan_encounters/royan_lab_orders/etc: add a nullable FK column, backfill
-- opportunistically by name match, keep the text column for display/back-compat.

ROLLBACK;
BEGIN;

ALTER TABLE public.royan_appointment_slots
    ADD COLUMN IF NOT EXISTS doctor_id uuid;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_appointment_slots_doctor'
          AND conrelid = 'public.royan_appointment_slots'::regclass
    ) THEN
        ALTER TABLE public.royan_appointment_slots
            ADD CONSTRAINT fk_appointment_slots_doctor
            FOREIGN KEY (doctor_id) REFERENCES public.royan_staff (id)
            ON DELETE SET NULL NOT VALID;
    END IF;
END;
$$;

CREATE INDEX IF NOT EXISTS idx_appointment_slots_doctor_id
    ON public.royan_appointment_slots (doctor_id);

-- Opportunistic backfill by exact name match; anything unmatched stays NULL
-- and continues to display via the existing doctor_name text column.
UPDATE public.royan_appointment_slots s
SET doctor_id = st.id
FROM public.royan_staff st
WHERE s.doctor_id IS NULL
  AND lower(st.full_name) = lower(s.doctor_name);

COMMIT;
