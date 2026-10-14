-- =============================================================================
-- Migration 231 - Stage billing: pay at each step, the way Royan works
-- =============================================================================
-- Royan's finance meeting (10 Oct 2026): a patient pays before each service.
--   1. Front desk: registration (new patients) + the consultation fee for the
--      clinic / doctor they are sent to - billed when the encounter is opened.
--   2. Doctor: whatever is ordered (lab, drugs, scans, procedures) is billed as
--      soon as the consultation ends - the cashier takes payment, then the
--      departments serve the patient.
--   3. Admitted patients keep a running bill (unchanged).
-- Imaging belongs to Scancare, a separate business with its own books, so its
-- lines go on a Scancare bill.
--
--   royan_consultation_tariffs      the consultation items per specialty (first visit,
--                                   follow-up, result review), from the tariff
--   royan_doctor_consultation_fees  a doctor's own specialty / fee where it differs
--   royan_bill_items.source/_id     the order a line charges (no line billed twice)
--   royan_billing.entity / stage    ROYAN or SCANCARE; registration / services / inpatient
--   royan_billing.released_*        the cashier lets a part-paid bill's services go ahead
--   royan_service_releases          a supervisor releases one order without payment
-- =============================================================================

CREATE TABLE IF NOT EXISTS royan_consultation_tariffs (
    id                    BIGSERIAL PRIMARY KEY,
    specialty             TEXT NOT NULL UNIQUE,
    department_code       TEXT,
    initial_service_id    BIGINT REFERENCES royan_service_catalog(id),
    follow_up_service_id  BIGINT REFERENCES royan_service_catalog(id),
    review_service_id     BIGINT REFERENCES royan_service_catalog(id),
    follow_up_days        INTEGER NOT NULL DEFAULT 30,
    is_active             BOOLEAN NOT NULL DEFAULT TRUE,
    updated_by            TEXT,
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS royan_doctor_consultation_fees (
    doctor_id        UUID PRIMARY KEY,
    tariff_id        BIGINT REFERENCES royan_consultation_tariffs(id),
    initial_fee      NUMERIC(14,2),
    follow_up_fee    NUMERIC(14,2),
    updated_by       TEXT,
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE royan_bill_items ADD COLUMN IF NOT EXISTS source TEXT;
ALTER TABLE royan_bill_items ADD COLUMN IF NOT EXISTS source_id TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS uq_royan_bill_items_source ON royan_bill_items (source, source_id)
    WHERE source IS NOT NULL AND source_id IS NOT NULL;

ALTER TABLE royan_billing ADD COLUMN IF NOT EXISTS entity TEXT NOT NULL DEFAULT 'ROYAN';
ALTER TABLE royan_billing ADD COLUMN IF NOT EXISTS stage TEXT;
ALTER TABLE royan_billing ADD COLUMN IF NOT EXISTS released_at TIMESTAMPTZ;
ALTER TABLE royan_billing ADD COLUMN IF NOT EXISTS released_by TEXT;
ALTER TABLE royan_billing ADD COLUMN IF NOT EXISTS release_reason TEXT;
DO $$ BEGIN
    ALTER TABLE royan_billing ADD CONSTRAINT royan_billing_entity_check CHECK (entity IN ('ROYAN', 'SCANCARE'));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
CREATE INDEX IF NOT EXISTS idx_royan_billing_encounter_entity ON royan_billing (encounter_id, entity);

CREATE TABLE IF NOT EXISTS royan_service_releases (
    id           BIGSERIAL PRIMARY KEY,
    source       TEXT NOT NULL,
    source_id    TEXT NOT NULL,
    reason       TEXT NOT NULL,
    released_by  TEXT NOT NULL,
    released_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (source, source_id)
);

CREATE TABLE IF NOT EXISTS royan_billing_settings (
    key    TEXT PRIMARY KEY,
    value  TEXT
);
INSERT INTO royan_billing_settings (key, value)
SELECT 'registration_service_id', id::text FROM royan_service_catalog WHERE service_code='HOPE-SVC-1359'
ON CONFLICT (key) DO NOTHING;
INSERT INTO royan_billing_settings (key, value) VALUES ('pay_first', 'private_outpatient') ON CONFLICT (key) DO NOTHING;

-- Specialties from Royan's tariff (Finance edits them in Roy Books › Fee Schedule › Consultation fees).
INSERT INTO royan_consultation_tariffs (specialty, department_code, initial_service_id, follow_up_service_id, review_service_id)
SELECT s.specialty, s.dept,
       (SELECT id FROM royan_service_catalog WHERE upper(name)=upper(s.initial) ORDER BY id LIMIT 1),
       (SELECT id FROM royan_service_catalog WHERE upper(name)=upper(s.follow) ORDER BY id LIMIT 1),
       (SELECT id FROM royan_service_catalog WHERE upper(name)=upper(s.review) ORDER BY id LIMIT 1)
FROM (VALUES
    ('General Practice', 'OPD', 'GENERAL CONSULTATION', 'GENERAL CONSULTATION FOLLOW UP', 'GENERAL CONSULTATION RESULT REVIEW'),
    ('Emergency', 'AE', 'GENERAL CONSULTATION', 'GENERAL CONSULTATION FOLLOW UP', 'GENERAL CONSULTATION RESULT REVIEW'),
    ('Cardiology', 'CARDIO', 'CARDIOLOGIST INTIAL CONSULTATION', 'CARDIOLOGIST FOLLOW UP VISIT', NULL),
    ('Ear, Nose & Throat', 'ENT', 'ENT CONSULTATION', 'ENT RESULT REVIEW', 'ENT RESULT REVIEW'),
    ('Gynaecology', 'MATERN', 'GYNAECOLOGIST CONSULTATION (Initial)', 'GYNAECOLOGIST FOLLOW UP CONSULTATION', 'GYNAECOLOGIST RESULT REVIEW'),
    ('Antenatal', NULL, 'ANTENATAL CONSULTATION -PER PREGNANCY ( INITIAL VISIT)', 'ANTENATAL FOLLOW UP VISIT', NULL),
    ('Paediatrics', 'PAEDS', 'PAEDIATRICIAN CONSULTATION', 'PAEDIATRICIAN FOLLOW UP VISIT', 'PAEDIATRICIAN RESULT REVIEW'),
    ('Physiotherapy', 'PHYSIO', 'PHYSIOTHERAPY CONSULTATION', 'PHYSIOTHERAPY VISIT', NULL),
    ('Surgery', 'SURG', 'SURGEON CONSULTATION (INITIAL VISIT)', 'SURGEON FOLLOW UP VISIT', NULL),
    ('Orthopaedics', NULL, 'ORTHOPEDICS CONSULTATION FIRST VISIT', 'ORTHOPEDICS CONSULTATION FOLLOW UP', 'ORTHOPEDICS RESULT REVIEW'),
    ('Neurology', NULL, 'NEUROLOGY CONSULTATION (INITIAL VISIT)', 'NEUROLOGY CONSULTATION FOLLOW UP', NULL),
    ('Neurosurgery', NULL, 'NEUROSURGERY FIRST VISIT', 'NEUROSURGERY RESULT REVIEW', 'NEUROSURGERY RESULT REVIEW'),
    ('Plastic Surgery', NULL, 'PLASTIC SURGERY INITIAL CONSULTATION', 'PLASTIC SURGERY FOLLOW UP CONSULTATION', NULL),
    ('Psychiatry', NULL, 'PSYCHIATRIST CONSULTATION FIRST VISIT', 'PSYCHIATRIST CONSULTATION FOLLOW UP', NULL),
    ('Urology', NULL, 'UROLOGIST CONSULTATION FIRST VISIT', 'UROLOGIST CONSULTATION FOLLOW UP', 'UROLOGIST RESULT REVIEW'),
    ('Cardiothoracic Surgery', NULL, 'CARDIOTHORACIC CONSULTATION FIRST VISIT', 'CARDIOTHORACIC SURGEON FOLLOW UP', NULL),
    ('Endocrinology', NULL, 'ENDOCRINOLOGY INITIAL CONSULTATION', 'ENDOCRINOLOGY FOLLOW UP CONSULTATION', NULL),
    ('Gastroenterology', NULL, 'GASTROENTEROLOGY CONSULTATION FIRST VISIT', 'GASTROENTEROLOGY CONSULTATION FOLLOW UP', NULL),
    ('Haematology', NULL, 'HEAMATOLOGY CONSULTATION (INITIAL VISIT)', 'HEAMATOLOGY FOLLOW UP', NULL),
    ('Family Planning', NULL, 'FAMILY PLANNING FIRST VISIT', 'FAMILY PLANNING FOLLOW UP CONSULTATION', NULL),
    ('Dental', 'DENTAL', NULL, NULL, NULL),
    ('Ophthalmology', 'OPHTHAL', NULL, NULL, NULL)
) AS s(specialty, dept, initial, follow, review)
ON CONFLICT (specialty) DO NOTHING;

-- Orders placed before pay-first started are not held up (patients already mid-visit on the day it went live).
INSERT INTO royan_billing_settings (key, value) VALUES ('pay_first_since', to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS') || '+00:00')
ON CONFLICT (key) DO NOTHING;
