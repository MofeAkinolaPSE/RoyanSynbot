-- Migration 189: Ward stay history (ADT log)
--
-- Complete-506-table Hope dump audit follow-up, Phase A2-P1: Hope's
-- `ward_patients` (11,317 real rows) is a historical admit/discharge log
-- (patient_id, ward_id, room_id, bed_id, in_date, out_date, readmitted).
-- Doesn't fit the existing royan_beds table (migration 103) -- that models
-- LIVE bed occupancy (current_patient_id/status), not a historical log,
-- and is a small (24-bed), manually-curated table today, not Hope-sourced.
--
-- Confirmed by direct content check: Hope's `wards` table (5 real rows --
-- "First Floor", "Ground Floor", "Stepdown Unit", "NEONATAL",
-- "COT/Mothersbedside") exactly matches 5 of the 6 already-seeded
-- royan_wards rows by name, so ward_id CAN be resolved by name match at
-- load time. Hope's `rooms`/`beds` (17/185 rows) have no equivalent
-- match against the live system's 24 beds (a much smaller, currently
-- in-use configuration) -- room/bed are kept as descriptive text, not FKs,
-- so historical detail isn't lost or forced onto the wrong live row.

BEGIN;

CREATE TABLE IF NOT EXISTS public.royan_ward_stay_history (
    id              bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    patient_id      bigint      NOT NULL REFERENCES public.royan_patients (id) ON DELETE CASCADE,
    ward_id         bigint      REFERENCES public.royan_wards (id) ON DELETE SET NULL,
    ward_name       text,
    room_name       text,
    bed_label       text,
    admitted_at     timestamptz NOT NULL,
    discharged_at   timestamptz,
    is_discharged   boolean     NOT NULL DEFAULT false,
    readmitted      boolean     NOT NULL DEFAULT false,
    external_source text,
    external_id     text,
    created_at      timestamptz NOT NULL DEFAULT now()
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'royan_ward_stay_history_external_source_external_id_key'
    ) THEN
        ALTER TABLE public.royan_ward_stay_history
            ADD CONSTRAINT royan_ward_stay_history_external_source_external_id_key
            UNIQUE (external_source, external_id);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_royan_ward_stay_history_patient
    ON public.royan_ward_stay_history (patient_id, admitted_at DESC);

COMMIT;
