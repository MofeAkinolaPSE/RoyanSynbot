-- 101_patients.sql
-- Royan Hospital: Patient registry with MRN (Medical Record Number), demographics, registration
-- Part of Phase 3 – Hospital Database Schema

ROLLBACK; -- clear any prior aborted transaction
BEGIN;

CREATE TABLE IF NOT EXISTS public.royan_patients (
    id              bigint          GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    mrn             text            NOT NULL UNIQUE,               -- Medical Record Number (hospital-issued)
    first_name      text            NOT NULL,
    last_name       text            NOT NULL,
    date_of_birth   date,
    gender          text            CHECK (gender IN ('male', 'female', 'other', 'prefer_not_to_say')),
    phone           text,
    email           text,
    address         text,
    next_of_kin_name  text,
    next_of_kin_phone text,
    blood_group     text            CHECK (blood_group IN ('A+','A-','B+','B-','AB+','AB-','O+','O-','unknown')),
    genotype        text            CHECK (genotype IN ('AA','AS','SS','AC','SC','unknown')),
    allergies       text[],                                        -- list of known allergen strings
    hmo_provider    text,                                          -- Health Maintenance Organisation name
    hmo_id          text,                                          -- HMO member number
    is_active       boolean         NOT NULL DEFAULT true,
    registered_by   text,                                          -- staff username/id who registered
    registered_at   timestamptz     NOT NULL DEFAULT now(),
    updated_at      timestamptz     NOT NULL DEFAULT now()
);

-- Unique sequential MRN generator helper (prefix RH + year + 6-digit seq)
CREATE SEQUENCE IF NOT EXISTS royan_mrn_seq START 1;

CREATE OR REPLACE FUNCTION public.generate_mrn()
RETURNS text
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN 'RH' || to_char(now(), 'YYYY') || lpad(nextval('royan_mrn_seq')::text, 6, '0');
END;
$$;

-- Index for fast lookup by phone/name/hmo
CREATE INDEX IF NOT EXISTS idx_royan_patients_mrn        ON public.royan_patients (mrn);
CREATE INDEX IF NOT EXISTS idx_royan_patients_phone      ON public.royan_patients (phone);
CREATE INDEX IF NOT EXISTS idx_royan_patients_last_name  ON public.royan_patients (lower(last_name));
CREATE INDEX IF NOT EXISTS idx_royan_patients_hmo_id     ON public.royan_patients (hmo_id) WHERE hmo_id IS NOT NULL;

COMMIT;
