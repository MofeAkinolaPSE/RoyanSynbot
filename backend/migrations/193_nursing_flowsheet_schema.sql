-- Migration 193: ICU nursing observation flowsheet
--
-- Phase A3 of the complete-506-table Hope audit. Hope's
-- `review_patient_details` (48,815 rows) is a real per-hour ICU nursing
-- observation chart, decoded through its three lookup tables (all staged
-- by extract_final_sweep.py):
--
--   review_categories (5)              "Adult ICU Quick View",
--                                      "Adult ICU Systems Assessment",
--                                      "Adult ICU Lines-Devices",
--                                      "Intake and Output"
--     -> review_sub_categories (60)    "Vital Signs", "Ventilator Subset", ...
--       -> review_sub_categories_options (317)
--                                      "Temperature Oral" (DegC),
--                                      "Pressure Bladder", ...
--
-- The column comment in Hope calls `values` "serialized data for every
-- hour for the day", but the actual content is a plain scalar per row
-- ("36.7", "170/90", "lying", "20") -- verified directly, not assumed.
-- Stored as text with a parsed numeric alongside where the value is
-- genuinely numeric ("170/90" is not, and stays text-only).
--
-- KEYING NOTE: every one of the 48,815 rows has id = 0 -- Hope's table has
-- no AUTO_INCREMENT and the dump export did not preserve a primary key.
-- external_id is therefore a deterministic composite
-- (patient/option/date/hourslot/actualtime, plus an occurrence counter for
-- the 217 rows where even that repeats), which keeps the load idempotent.

BEGIN;

CREATE TABLE IF NOT EXISTS public.royan_nursing_flowsheet (
    id                bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    patient_id        bigint      NOT NULL REFERENCES public.royan_patients (id) ON DELETE CASCADE,
    category_name     text,
    sub_category_name text,
    observation_name  text        NOT NULL,
    unit              text,
    value_text        text        NOT NULL,
    value_numeric     numeric(14,4),
    observed_date     date,
    hour_slot         text,
    actual_time       text,
    is_edited         boolean     NOT NULL DEFAULT false,
    external_source   text,
    external_id       text,
    created_at        timestamptz NOT NULL DEFAULT now()
);

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='royan_nursing_flowsheet_ext_key') THEN
        ALTER TABLE public.royan_nursing_flowsheet
            ADD CONSTRAINT royan_nursing_flowsheet_ext_key UNIQUE (external_source, external_id);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_royan_nursing_flowsheet_patient
    ON public.royan_nursing_flowsheet (patient_id, observed_date DESC, hour_slot);
CREATE INDEX IF NOT EXISTS idx_royan_nursing_flowsheet_observation
    ON public.royan_nursing_flowsheet (observation_name);

COMMIT;
