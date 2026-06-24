-- 103_beds_wards.sql
-- Royan Hospital: Wards and bed occupancy management
-- Part of Phase 3 – Hospital Database Schema

ROLLBACK; -- clear any prior aborted transaction
BEGIN;

-- Wards
CREATE TABLE IF NOT EXISTS public.royan_wards (
    id          bigint  GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name        text    NOT NULL UNIQUE,                    -- e.g. "Medical Ward A", "Surgical Ward", "ICU"
    ward_type   text    NOT NULL CHECK (ward_type IN (
                    'general', 'surgical', 'icu', 'maternity', 'paediatric',
                    'isolation', 'emergency', 'private'
                )),
    floor       text,
    total_beds  int     NOT NULL DEFAULT 0 CHECK (total_beds >= 0),
    is_active   boolean NOT NULL DEFAULT true,
    notes       text,
    created_at  timestamptz NOT NULL DEFAULT now()
);

-- Beds (each bed belongs to one ward)
CREATE TABLE IF NOT EXISTS public.royan_beds (
    id              bigint  GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ward_id         bigint  NOT NULL REFERENCES public.royan_wards (id) ON DELETE CASCADE,
    bed_number      text    NOT NULL,                       -- e.g. "A-01", "ICU-3"
    bed_type        text    NOT NULL DEFAULT 'standard'
                            CHECK (bed_type IN ('standard', 'icu', 'isolation', 'maternity', 'recovery')),
    status          text    NOT NULL DEFAULT 'available'
                            CHECK (status IN ('available', 'occupied', 'reserved', 'maintenance')),
    current_patient_id  bigint REFERENCES public.royan_patients (id) ON DELETE SET NULL,
    current_encounter_id bigint,                            -- FK to royan_encounters; added after that table exists
    admitted_at     timestamptz,
    notes           text,
    updated_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (ward_id, bed_number)
);

-- Add FK from encounters to wards/beds now that both tables exist
-- Wrapped in DO blocks so re-running is safe (idempotent).
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_encounters_ward'
          AND conrelid = 'public.royan_encounters'::regclass
    ) THEN
        ALTER TABLE public.royan_encounters
            ADD CONSTRAINT fk_encounters_ward
            FOREIGN KEY (ward_id) REFERENCES public.royan_wards (id) ON DELETE SET NULL
            NOT VALID;
    END IF;
END;
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_encounters_bed'
          AND conrelid = 'public.royan_encounters'::regclass
    ) THEN
        ALTER TABLE public.royan_encounters
            ADD CONSTRAINT fk_encounters_bed
            FOREIGN KEY (bed_id) REFERENCES public.royan_beds (id) ON DELETE SET NULL
            NOT VALID;
    END IF;
END;
$$;

-- View: live bed occupancy summary per ward
CREATE OR REPLACE VIEW public.royan_bed_occupancy AS
SELECT
    w.id            AS ward_id,
    w.name          AS ward_name,
    w.ward_type,
    w.total_beds,
    COUNT(b.id)                                             AS registered_beds,
    COUNT(b.id) FILTER (WHERE b.status = 'available')      AS available_beds,
    COUNT(b.id) FILTER (WHERE b.status = 'occupied')       AS occupied_beds,
    COUNT(b.id) FILTER (WHERE b.status = 'maintenance')    AS maintenance_beds,
    ROUND(
        100.0 * COUNT(b.id) FILTER (WHERE b.status = 'occupied')
        / NULLIF(COUNT(b.id), 0), 1
    ) AS occupancy_pct
FROM public.royan_wards w
LEFT JOIN public.royan_beds b ON b.ward_id = w.id
GROUP BY w.id, w.name, w.ward_type, w.total_beds;

CREATE INDEX IF NOT EXISTS idx_royan_beds_ward_id  ON public.royan_beds (ward_id);
CREATE INDEX IF NOT EXISTS idx_royan_beds_status   ON public.royan_beds (status);

COMMIT;
