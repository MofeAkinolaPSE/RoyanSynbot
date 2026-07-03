-- Migration 142: Wire royan_staff to the royan_departments master table
--
-- Migration 130 defined a department_id FK column as part of a fresh
-- royan_staff template, but since royan_staff already existed (from
-- migration 111) that CREATE TABLE was a no-op and the column was never
-- actually added — unlike royan_encounters, royan_wards, royan_patients,
-- etc. which all got department_id backfilled in migration 131. This
-- migration closes that gap for royan_staff specifically.
--
-- The free-text `department` column is kept (still used for display/back-
-- compat); department_id becomes the authoritative link to the canonical
-- department list. Existing rows are opportunistically matched by name;
-- unmatched rows (including quarantined contamination) are left NULL.

ROLLBACK;
BEGIN;

ALTER TABLE public.royan_staff
    ADD COLUMN IF NOT EXISTS department_id bigint;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_staff_department'
          AND conrelid = 'public.royan_staff'::regclass
    ) THEN
        ALTER TABLE public.royan_staff
            ADD CONSTRAINT fk_staff_department
            FOREIGN KEY (department_id) REFERENCES public.royan_departments (id)
            ON DELETE SET NULL NOT VALID;
    END IF;
END;
$$;

CREATE INDEX IF NOT EXISTS idx_royan_staff_department_id ON public.royan_staff (department_id);

-- Opportunistic backfill: match existing free-text department against the
-- canonical name/short_name/code. Skips quarantined rows on purpose.
UPDATE public.royan_staff s
SET department_id = d.id
FROM public.royan_departments d
WHERE s.department_id IS NULL
  AND s.quarantined_at IS NULL
  AND (
        lower(d.name) = lower(s.department)
     OR lower(d.short_name) = lower(s.department)
     OR lower(d.code) = lower(s.department)
  );

COMMIT;
