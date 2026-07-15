-- 130_master_mdm_tables.sql
-- Master Data Management (MDM) Layer — Chapter 4 of RoyanHealth Blueprint
-- Creates authoritative reference tables for departments, staff, lab catalog,
-- drug formulary, diagnosis catalog, and procedure catalog.
-- Note: royan_hmos, royan_service_catalog, royan_wards, royan_beds already exist
-- from earlier migrations and form part of the MDM layer.

ROLLBACK;
BEGIN;

-- ─────────────────────────────────────────────────────────────────────────────
-- DEPARTMENT MASTER
-- Single source of truth for all hospital departments/units
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.royan_departments (
    id              bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code            text        NOT NULL UNIQUE,                -- e.g. "OPD", "LAB", "PHARM"
    name            text        NOT NULL UNIQUE,                -- e.g. "Outpatient Department"
    short_name      text,                                       -- display abbreviation
    dept_type       text        NOT NULL DEFAULT 'clinical'
                                CHECK (dept_type IN ('clinical', 'diagnostic', 'support', 'administrative', 'financial')),
    parent_id       bigint      REFERENCES public.royan_departments (id) ON DELETE SET NULL,
    is_active       boolean     NOT NULL DEFAULT true,
    notes           text,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_royan_departments_type   ON public.royan_departments (dept_type);
CREATE INDEX IF NOT EXISTS idx_royan_departments_active ON public.royan_departments (is_active);

-- Seed with core hospital departments
INSERT INTO public.royan_departments (code, name, short_name, dept_type) VALUES
    ('OPD',     'Outpatient Department',        'OPD',     'clinical'),
    ('AE',      'Accident & Emergency',         'A&E',     'clinical'),
    ('IPD',     'Inpatient Department',         'IPD',     'clinical'),
    ('LAB',     'Laboratory & Diagnostics',     'LAB',     'diagnostic'),
    ('PHARM',   'Pharmacy',                     'PHARM',   'clinical'),
    ('RAD',     'Radiology & Imaging',          'RAD',     'diagnostic'),
    ('SURG',    'Surgery',                      'SURG',    'clinical'),
    ('MATERN',  'Maternity & Obstetrics',       'MCH',     'clinical'),
    ('PAEDS',   'Paediatrics',                  'PAEDS',   'clinical'),
    ('ICU',     'Intensive Care Unit',          'ICU',     'clinical'),
    ('BILLING', 'Billing & Finance',            'BIL',     'financial'),
    ('ADMIN',   'Administration',               'ADMIN',   'administrative'),
    ('MAINT',   'Maintenance & Facilities',     'MAINT',   'support'),
    ('MORTUARY','Mortuary',                     'MORT',    'clinical'),
    ('DIETETICS','Dietetics & Nutrition',       'DIET',    'clinical'),
    ('PHYSIO',  'Physiotherapy',                'PHYSIO',  'clinical'),
    ('DENTAL',  'Dental',                       'DENTAL',  'clinical'),
    ('OPHTHAL', 'Ophthalmology',                'OPHTHAL', 'clinical'),
    ('ENT',     'Ear, Nose & Throat',           'ENT',     'clinical'),
    ('CARDIO',  'Cardiology',                   'CARDIO',  'clinical')
ON CONFLICT (code) DO NOTHING;


-- ─────────────────────────────────────────────────────────────────────────────
-- STAFF MASTER
-- Authoritative registry for all hospital personnel
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.royan_staff (
    id              bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    staff_code      text        NOT NULL UNIQUE,                -- e.g. "DR001", "NRS042"
    title           text        CHECK (title IN ('Dr', 'Prof', 'Mr', 'Mrs', 'Ms', 'Nurse', 'Pharm', 'Lab', 'Admin')),
    first_name      text        NOT NULL,
    last_name       text        NOT NULL,
    full_name       text        GENERATED ALWAYS AS (
                        COALESCE(title || ' ', '') || first_name || ' ' || last_name
                    ) STORED,
    role            text        NOT NULL
                                CHECK (role IN ('doctor', 'nurse', 'pharmacist', 'lab_scientist',
                                                'radiographer', 'admin', 'receptionist', 'accountant',
                                                'physiotherapist', 'dietitian', 'other')),
    specialty       text,                                       -- clinical specialty (doctors)
    department_id   bigint      REFERENCES public.royan_departments (id) ON DELETE SET NULL,
    user_id         bigint,                                     -- FK to auth users table when linked
    phone           text,
    email           text,
    license_number  text,                                       -- MDCN/PCN/MLSCN registration
    is_active       boolean     NOT NULL DEFAULT true,
    -- MDM lineage
    external_source text,
    external_id     text,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

-- Add MDM lineage columns to existing royan_staff if not already present
ALTER TABLE public.royan_staff
    ADD COLUMN IF NOT EXISTS external_source text,
    ADD COLUMN IF NOT EXISTS external_id     text;

CREATE UNIQUE INDEX IF NOT EXISTS uq_royan_staff_external
    ON public.royan_staff (external_source, external_id)
    WHERE external_source IS NOT NULL AND external_id IS NOT NULL;

-- Guard optional indexes against column absence (existing table may differ from template above)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='royan_staff' AND column_name='department_id') THEN
        EXECUTE 'CREATE INDEX IF NOT EXISTS idx_royan_staff_dept_id ON public.royan_staff (department_id)';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='royan_staff' AND column_name='role') THEN
        EXECUTE 'CREATE INDEX IF NOT EXISTS idx_royan_staff_role ON public.royan_staff (role)';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='royan_staff' AND column_name='last_name') THEN
        EXECUTE 'CREATE INDEX IF NOT EXISTS idx_royan_staff_name ON public.royan_staff (lower(last_name))';
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_royan_staff_active   ON public.royan_staff (is_active);


-- ─────────────────────────────────────────────────────────────────────────────
-- LABORATORY CATALOG
-- Authoritative registry of all laboratory tests
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.royan_lab_catalog (
    id                  bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code                text        NOT NULL UNIQUE,            -- internal test code
    loinc_code          text,                                   -- LOINC standard code
    name                text        NOT NULL,                   -- e.g. "Full Blood Count"
    abbreviation        text,                                   -- e.g. "FBC"
    category            text        NOT NULL DEFAULT 'haematology'
                                    CHECK (category IN (
                                        'haematology', 'biochemistry', 'microbiology',
                                        'immunology', 'serology', 'urinalysis', 'histopathology',
                                        'cytology', 'parasitology', 'endocrinology', 'genetics', 'other'
                                    )),
    specimen_type       text        NOT NULL DEFAULT 'blood'
                                    CHECK (specimen_type IN (
                                        'blood', 'urine', 'stool', 'sputum', 'csf', 'swab',
                                        'tissue', 'serum', 'plasma', 'other'
                                    )),
    unit                text,                                   -- e.g. "g/dL", "mmol/L", "x10^9/L"
    reference_range     text,                                   -- e.g. "12.0 - 17.5 g/dL (male)"
    turnaround_hours    int         NOT NULL DEFAULT 24 CHECK (turnaround_hours > 0),
    base_price          numeric     NOT NULL DEFAULT 0 CHECK (base_price >= 0),
    requires_fasting    boolean     NOT NULL DEFAULT false,
    is_active           boolean     NOT NULL DEFAULT true,
    -- MDM lineage
    external_source     text,
    external_id         text,
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_royan_lab_catalog_external
    ON public.royan_lab_catalog (external_source, external_id)
    WHERE external_source IS NOT NULL AND external_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_royan_lab_catalog_category ON public.royan_lab_catalog (category);
CREATE INDEX IF NOT EXISTS idx_royan_lab_catalog_active   ON public.royan_lab_catalog (is_active);

-- Seed common tests
INSERT INTO public.royan_lab_catalog (code, name, abbreviation, category, specimen_type, unit, reference_range, turnaround_hours, base_price) VALUES
    ('FBC',     'Full Blood Count',                 'FBC',   'haematology',  'blood', 'varies',    'See individual components', 4,  3000),
    ('PCV',     'Packed Cell Volume',               'PCV',   'haematology',  'blood', '%',         'Male: 40-52, Female: 36-48', 2, 1500),
    ('BG',      'Blood Group & Genotype',           'BG',    'haematology',  'blood', 'qualitative','ABO+Rh typing',             4,  2500),
    ('MALRDT',  'Malaria Rapid Test',               'MAL',   'parasitology', 'blood', 'qualitative','Negative',                  1,  1500),
    ('THICKFILM','Malaria Thick Film',              'MPS',   'parasitology', 'blood', 'qualitative','Negative',                  4,  1500),
    ('WIDAL',   'Widal Test',                       'WIDAL', 'serology',     'blood', 'titres',    'Negative (< 1:80)',          6,  2000),
    ('HBsAg',   'Hepatitis B Surface Antigen',      'HBsAg', 'serology',     'blood', 'qualitative','Non-reactive',              6,  3500),
    ('HCV',     'Hepatitis C Antibody',             'HCV',   'serology',     'blood', 'qualitative','Non-reactive',              6,  3500),
    ('HIV',     'HIV 1&2 Rapid Test',               'HIV',   'immunology',   'blood', 'qualitative','Non-reactive',              2,  3500),
    ('FBS',     'Fasting Blood Sugar',              'FBS',   'biochemistry', 'blood', 'mmol/L',    '3.9 - 6.1 mmol/L',         2,  1500),
    ('RBS',     'Random Blood Sugar',               'RBS',   'biochemistry', 'blood', 'mmol/L',    '3.9 - 7.8 mmol/L',         1,  1500),
    ('LFT',     'Liver Function Test',              'LFT',   'biochemistry', 'blood', 'varies',    'See individual components', 6,  5000),
    ('RFT',     'Renal Function Test',              'RFT',   'biochemistry', 'blood', 'varies',    'See individual components', 6,  5000),
    ('LIPID',   'Lipid Profile',                    'LIPID', 'biochemistry', 'blood', 'mmol/L',    'Total Chol < 5.2 mmol/L',  6,  5000),
    ('UA',      'Urinalysis',                       'UA',    'urinalysis',   'urine', 'qualitative','See individual components', 2,  1500),
    ('UCSM',    'Urine Culture & Sensitivity',      'UCSM',  'microbiology', 'urine', 'qualitative','No growth',                48, 4000),
    ('CRP',     'C-Reactive Protein',               'CRP',   'biochemistry', 'blood', 'mg/L',      '< 5 mg/L',                  6,  3000),
    ('PSA',     'Prostate Specific Antigen',        'PSA',   'endocrinology','blood', 'ng/mL',     '< 4 ng/mL',                 8,  5000),
    ('PREG',    'Urine Pregnancy Test',             'UPT',   'immunology',   'urine', 'qualitative','Negative',                  1,  1000),
    ('TROP',    'Troponin I',                       'TROP',  'biochemistry', 'blood', 'ng/mL',     '< 0.04 ng/mL',              4,  8000)
ON CONFLICT (code) DO NOTHING;


-- ─────────────────────────────────────────────────────────────────────────────
-- DRUG FORMULARY
-- Authoritative hospital drug list
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.royan_drug_formulary (
    id              bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code            text        NOT NULL UNIQUE,                -- internal code / NAFDAC number
    generic_name    text        NOT NULL,                       -- INN generic name
    brand_name      text,                                       -- common brand
    drug_class      text        NOT NULL DEFAULT 'other'
                                CHECK (drug_class IN (
                                    'analgesic', 'antibiotic', 'antifungal', 'antiviral', 'antimalarial',
                                    'antihypertensive', 'antidiabetic', 'anticoagulant', 'antiparasitic',
                                    'antacid', 'antihistamine', 'steroid', 'vitamin', 'vaccine',
                                    'cardiovascular', 'respiratory', 'neurological', 'endocrine', 'other'
                                )),
    form            text        NOT NULL DEFAULT 'tablet'
                                CHECK (form IN ('tablet', 'capsule', 'syrup', 'injection', 'cream',
                                                'ointment', 'drops', 'inhaler', 'patch', 'suppository', 'other')),
    strength        text,                                       -- e.g. "500mg", "250mg/5ml"
    unit            text        NOT NULL DEFAULT 'tablet',
    route           text[]      NOT NULL DEFAULT ARRAY['oral'], -- allowed administration routes
    requires_prescription boolean NOT NULL DEFAULT true,
    is_controlled   boolean     NOT NULL DEFAULT false,         -- Schedule II/III narcotic
    storage_condition text,                                     -- e.g. "Room temperature", "Refrigerate 2-8°C"
    unit_cost       numeric     NOT NULL DEFAULT 0 CHECK (unit_cost >= 0),
    is_active       boolean     NOT NULL DEFAULT true,
    -- MDM lineage
    external_source text,
    external_id     text,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_royan_drug_formulary_external
    ON public.royan_drug_formulary (external_source, external_id)
    WHERE external_source IS NOT NULL AND external_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_royan_drug_formulary_class  ON public.royan_drug_formulary (drug_class);
CREATE INDEX IF NOT EXISTS idx_royan_drug_formulary_name   ON public.royan_drug_formulary (lower(generic_name));
CREATE INDEX IF NOT EXISTS idx_royan_drug_formulary_active ON public.royan_drug_formulary (is_active);


-- ─────────────────────────────────────────────────────────────────────────────
-- DIAGNOSIS CATALOG
-- ICD-10 and local clinical diagnosis codes
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.royan_diagnosis_catalog (
    id              bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    icd_code        text        NOT NULL UNIQUE,                -- ICD-10 code, e.g. "J06.9"
    description     text        NOT NULL,                       -- e.g. "Acute upper respiratory infection"
    category        text        NOT NULL,                       -- ICD chapter, e.g. "Respiratory diseases"
    subcategory     text,                                       -- ICD block
    is_clinical_default boolean NOT NULL DEFAULT false,         -- show in quick-pick lists
    is_active       boolean     NOT NULL DEFAULT true,
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_royan_diagnosis_catalog_code     ON public.royan_diagnosis_catalog (icd_code);
CREATE INDEX IF NOT EXISTS idx_royan_diagnosis_catalog_category ON public.royan_diagnosis_catalog (category);
CREATE INDEX IF NOT EXISTS idx_royan_diagnosis_catalog_default  ON public.royan_diagnosis_catalog (is_clinical_default) WHERE is_clinical_default = true;

-- Seed most common diagnoses for Nigerian hospital context
INSERT INTO public.royan_diagnosis_catalog (icd_code, description, category, is_clinical_default) VALUES
    ('A09',   'Infectious diarrhoea',                          'Infectious diseases',        true),
    ('A15.0', 'Pulmonary tuberculosis',                        'Infectious diseases',        true),
    ('A75',   'Typhoid fever',                                 'Infectious diseases',        true),
    ('B50',   'Malaria (Plasmodium falciparum)',               'Parasitic diseases',         true),
    ('B50.0', 'Severe malaria',                                'Parasitic diseases',         true),
    ('E11',   'Type 2 diabetes mellitus',                      'Endocrine diseases',         true),
    ('E14',   'Unspecified diabetes mellitus',                 'Endocrine diseases',         true),
    ('I10',   'Essential hypertension',                        'Cardiovascular diseases',    true),
    ('I25',   'Chronic ischaemic heart disease',               'Cardiovascular diseases',    true),
    ('I50',   'Heart failure',                                 'Cardiovascular diseases',    true),
    ('J06.9', 'Acute upper respiratory infection',             'Respiratory diseases',       true),
    ('J18',   'Pneumonia',                                     'Respiratory diseases',       true),
    ('J45',   'Asthma',                                        'Respiratory diseases',       true),
    ('K21',   'Gastro-oesophageal reflux disease',             'Digestive diseases',         true),
    ('K29',   'Gastritis',                                     'Digestive diseases',         true),
    ('K35',   'Acute appendicitis',                            'Digestive diseases',         true),
    ('K80',   'Cholelithiasis (gallstones)',                   'Digestive diseases',         true),
    ('K92.1', 'Melaena',                                       'Digestive diseases',         false),
    ('N18',   'Chronic kidney disease',                        'Genitourinary diseases',     true),
    ('N39.0', 'Urinary tract infection',                       'Genitourinary diseases',     true),
    ('N40',   'Benign prostatic hyperplasia',                  'Genitourinary diseases',     true),
    ('O00',   'Ectopic pregnancy',                             'Obstetric conditions',       true),
    ('O80',   'Normal spontaneous vaginal delivery',           'Obstetric conditions',       true),
    ('O82',   'Delivery by caesarean section',                 'Obstetric conditions',       true),
    ('R50',   'Fever of unknown origin',                       'Symptoms and signs',         true),
    ('R51',   'Headache',                                      'Symptoms and signs',         true),
    ('R10',   'Abdominal and pelvic pain',                     'Symptoms and signs',         true),
    ('S00-T98','Injuries and trauma',                          'Injuries',                   true),
    ('Z00',   'General health examination',                    'Health services',            true),
    ('Z51',   'Follow-up visit',                               'Health services',            true)
ON CONFLICT (icd_code) DO NOTHING;


-- ─────────────────────────────────────────────────────────────────────────────
-- PROCEDURE CATALOG
-- Authoritative registry of clinical and surgical procedures
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.royan_procedure_catalog (
    id                  bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code                text        NOT NULL UNIQUE,
    name                text        NOT NULL,
    category            text        NOT NULL DEFAULT 'minor'
                                    CHECK (category IN ('minor', 'major', 'surgical', 'diagnostic',
                                                        'therapeutic', 'emergency', 'other')),
    department_id       bigint      REFERENCES public.royan_departments (id) ON DELETE SET NULL,
    duration_minutes    int         CHECK (duration_minutes IS NULL OR duration_minutes > 0),
    requires_anaesthesia boolean    NOT NULL DEFAULT false,
    requires_consent    boolean     NOT NULL DEFAULT true,
    base_price          numeric     NOT NULL DEFAULT 0 CHECK (base_price >= 0),
    is_active           boolean     NOT NULL DEFAULT true,
    -- MDM lineage
    external_source     text,
    external_id         text,
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_royan_procedure_catalog_dept     ON public.royan_procedure_catalog (department_id);
CREATE INDEX IF NOT EXISTS idx_royan_procedure_catalog_category ON public.royan_procedure_catalog (category);
CREATE INDEX IF NOT EXISTS idx_royan_procedure_catalog_active   ON public.royan_procedure_catalog (is_active);

COMMIT;
