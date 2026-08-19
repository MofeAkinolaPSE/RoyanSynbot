-- 168_quality_safety_schema_alignment.sql
-- Royan Hospital: align royan_incident_reports / royan_infection_control /
-- royan_hefamaa_checklist with the healthcare-specific vocabulary and field
-- set the Quality & Safety router/UI already assumed but the live schema
-- never caught up to. All three tables confirmed empty (0 rows) at the time
-- of writing, so the CHECK-constraint rewrite is zero-risk.

ROLLBACK;
BEGIN;

-- ── Incidents ────────────────────────────────────────────────────────────
-- Replace the generic ITIL-style severity/status vocab with the healthcare-
-- specific one already built into constants.py / the router / the frontend
-- (near-miss and sentinel-event are real, distinct clinical-safety concepts
-- a generic low/medium/high/critical scale can't represent).
ALTER TABLE public.royan_incident_reports
    DROP CONSTRAINT IF EXISTS royan_incident_reports_severity_check,
    DROP CONSTRAINT IF EXISTS royan_incident_reports_status_check;

ALTER TABLE public.royan_incident_reports
    ALTER COLUMN severity SET DEFAULT 'minor',
    ALTER COLUMN status   SET DEFAULT 'reported';

ALTER TABLE public.royan_incident_reports
    ADD CONSTRAINT royan_incident_reports_severity_check
        CHECK (severity = ANY (ARRAY['near_miss','minor','moderate','major','sentinel'])),
    ADD CONSTRAINT royan_incident_reports_status_check
        CHECK (status = ANY (ARRAY['reported','under_review','investigated','escalated','closed'])),
    ADD CONSTRAINT royan_incident_reports_category_check
        CHECK (category = ANY (ARRAY[
            'medication_error','patient_fall','pressure_injury','surgical_complication',
            'equipment_failure','infection','documentation_error','delay_in_treatment',
            'violence_aggression','other'
        ]));

ALTER TABLE public.royan_incident_reports
    ADD COLUMN IF NOT EXISTS encounter_id                       bigint REFERENCES royan_encounters(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS incident_date                      date NOT NULL DEFAULT CURRENT_DATE,
    ADD COLUMN IF NOT EXISTS incident_time                      time,
    ADD COLUMN IF NOT EXISTS immediate_action_taken             text,
    ADD COLUMN IF NOT EXISTS witnesses                          text,
    ADD COLUMN IF NOT EXISTS equipment_involved                 text,
    ADD COLUMN IF NOT EXISTS contributing_factors               text,
    ADD COLUMN IF NOT EXISTS investigation_contributing_factors text,
    ADD COLUMN IF NOT EXISTS status_notes                       text,
    ADD COLUMN IF NOT EXISTS closed_at                          timestamptz,
    ADD COLUMN IF NOT EXISTS root_cause                         text,
    ADD COLUMN IF NOT EXISTS corrective_actions                 text,
    ADD COLUMN IF NOT EXISTS preventive_actions                 text,
    ADD COLUMN IF NOT EXISTS investigated_by                    uuid REFERENCES royan_staff(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS outcome                             text,
    ADD COLUMN IF NOT EXISTS investigation_completed_at         timestamptz;

CREATE INDEX IF NOT EXISTS idx_incident_reports_encounter ON royan_incident_reports(encounter_id);

-- ── Infection Control ───────────────────────────────────────────────────
ALTER TABLE public.royan_infection_control
    ADD COLUMN IF NOT EXISTS encounter_id           bigint REFERENCES royan_encounters(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS specimen_type          text,
    ADD COLUMN IF NOT EXISTS culture_result         text,
    ADD COLUMN IF NOT EXISTS onset_date             date NOT NULL DEFAULT CURRENT_DATE,
    ADD COLUMN IF NOT EXISTS antibiotic_resistant   boolean NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS antibiotics_prescribed text,
    ADD COLUMN IF NOT EXISTS isolation_precautions  text,
    ADD COLUMN IF NOT EXISTS outcome                text;

CREATE INDEX IF NOT EXISTS idx_infection_control_encounter ON royan_infection_control(encounter_id);

-- ── HEFAMAA ─────────────────────────────────────────────────────────────
-- domain_scores (jsonb) stays the store for the 19 checklist booleans,
-- nested by section — a deliberate flexible design, not migrated to columns.
ALTER TABLE public.royan_hefamaa_checklist
    ADD COLUMN IF NOT EXISTS department      text,
    ADD COLUMN IF NOT EXISTS observations    text,
    ADD COLUMN IF NOT EXISTS recommendations text,
    ADD COLUMN IF NOT EXISTS follow_up_date  date;

CREATE INDEX IF NOT EXISTS idx_hefamaa_department ON royan_hefamaa_checklist(department);

COMMIT;
