-- 169_specialist_clinics_schema.sql
-- Royan Hospital: create the two tables the Specialist Clinics router/UI
-- have always assumed but never existed live — every request currently
-- 500s. Both router and frontend are otherwise already coherent; this is a
-- from-scratch CREATE TABLE, not a schema-alignment job.

ROLLBACK;
BEGIN;

CREATE TABLE IF NOT EXISTS public.royan_clinic_templates (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    specialty           text NOT NULL,
    template_name       text NOT NULL,
    fields              jsonb NOT NULL DEFAULT '[]'::jsonb,
    default_order_sets  text[] NOT NULL DEFAULT '{}',
    active              boolean NOT NULL DEFAULT true,
    created_by          uuid REFERENCES royan_staff(id) ON DELETE SET NULL,
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz,
    CONSTRAINT royan_clinic_templates_specialty_check CHECK (specialty = ANY (ARRAY[
        'cardiology','ent','ophthalmology','dermatology','orthopaedics','neurology',
        'gastroenterology','urology','pulmonology','endocrinology','psychiatry',
        'paediatrics','oncology','dentistry','general'
    ]))
);
CREATE INDEX IF NOT EXISTS idx_clinic_templates_specialty ON royan_clinic_templates(specialty);

CREATE TABLE IF NOT EXISTS public.royan_specialist_notes (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id    bigint NOT NULL REFERENCES royan_patients(id) ON DELETE CASCADE,
    encounter_id  bigint REFERENCES royan_encounters(id) ON DELETE SET NULL,
    template_id   uuid REFERENCES royan_clinic_templates(id) ON DELETE SET NULL,
    specialty     text NOT NULL,
    note_data     jsonb NOT NULL DEFAULT '{}'::jsonb,
    icd10_codes   text[],
    assessment    text,
    plan          text,
    noted_by      uuid REFERENCES royan_staff(id) ON DELETE SET NULL,
    noted_at      timestamptz NOT NULL DEFAULT now(),
    amended_at    timestamptz,
    amended_by    uuid REFERENCES royan_staff(id) ON DELETE SET NULL,
    CONSTRAINT royan_specialist_notes_specialty_check CHECK (specialty = ANY (ARRAY[
        'cardiology','ent','ophthalmology','dermatology','orthopaedics','neurology',
        'gastroenterology','urology','pulmonology','endocrinology','psychiatry',
        'paediatrics','oncology','dentistry','general'
    ]))
);
CREATE INDEX IF NOT EXISTS idx_specialist_notes_patient   ON royan_specialist_notes(patient_id);
CREATE INDEX IF NOT EXISTS idx_specialist_notes_encounter ON royan_specialist_notes(encounter_id);
CREATE INDEX IF NOT EXISTS idx_specialist_notes_template  ON royan_specialist_notes(template_id);
CREATE INDEX IF NOT EXISTS idx_specialist_notes_specialty ON royan_specialist_notes(specialty);

COMMIT;
