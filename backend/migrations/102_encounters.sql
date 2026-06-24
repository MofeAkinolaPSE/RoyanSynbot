-- 102_encounters.sql
-- Royan Hospital: Clinical encounters (visits, triage, consultations)
-- An encounter is one visit episode. One patient may have many encounters.
-- Part of Phase 3 – Hospital Database Schema

ROLLBACK; -- clear any prior aborted transaction
BEGIN;

CREATE TABLE IF NOT EXISTS public.royan_encounters (
    id                  bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    patient_id          bigint      NOT NULL REFERENCES public.royan_patients (id) ON DELETE RESTRICT,
    encounter_type      text        NOT NULL CHECK (encounter_type IN ('outpatient', 'inpatient', 'emergency', 'maternity', 'surgical')),
    status              text        NOT NULL DEFAULT 'patient_registered'
                                    CHECK (status IN (
                                        'patient_registered', 'triaged', 'consulting',
                                        'lab_ordered', 'pharmacy_dispensing', 'billing_pending', 'discharged'
                                    )),
    -- Triage
    triage_level        text        CHECK (triage_level IN ('immediate', 'urgent', 'less_urgent', 'non_urgent')),
    triage_notes        text,
    chief_complaint     text,
    triage_at           timestamptz,
    triage_by           text,
    -- Consultation
    consulting_doctor   text,
    diagnosis_codes     text[],                     -- ICD-10 codes
    diagnosis_notes     text,
    consultation_at     timestamptz,
    -- Discharge
    discharge_summary   text,
    discharge_at        timestamptz,
    discharge_by        text,
    -- Department routing
    department          text        CHECK (department IN (
                                        'A&E', 'OPD', 'Inpatient Ward', 'Laboratory & Diagnostics',
                                        'Pharmacy', 'Billing & Finance', 'Administration',
                                        'Maintenance & Facilities', 'Maternity', 'Surgery'
                                    )),
    ward_id             bigint,                     -- FK populated once royan_wards exists
    bed_id              bigint,                     -- FK populated once royan_beds exists
    -- Audit
    registered_by       text,
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_royan_encounters_patient_id  ON public.royan_encounters (patient_id);
CREATE INDEX IF NOT EXISTS idx_royan_encounters_status      ON public.royan_encounters (status);
CREATE INDEX IF NOT EXISTS idx_royan_encounters_created_at  ON public.royan_encounters (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_royan_encounters_department  ON public.royan_encounters (department);

COMMIT;
