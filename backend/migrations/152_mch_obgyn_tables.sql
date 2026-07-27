-- Migration 152: Create the missing MCH/OB-GYN tables
--
-- backend/src/routers/mch_obgyn.py (ANC registration, visits, partograph,
-- delivery, newborn assessment) has referenced royan_anc_records,
-- royan_anc_visits, royan_partograph, royan_delivery_records, and
-- royan_newborn_assessment since the router was written, but no migration
-- ever created any of them. Every insert/select throws "relation does not
-- exist", caught by a per-endpoint try/except, so the entire module has
-- silently no-op'd since deployment. royan_immunisation (the 6th table this
-- router uses) already exists via migration 148 and is unaffected.
--
-- Column shapes below match the router's Pydantic models exactly (ANCCreate,
-- ANCVisitCreate, PartographEntry, DeliveryRecord, NewbornAssessment).

ROLLBACK;
BEGIN;

CREATE TABLE IF NOT EXISTS public.royan_anc_records (
    id                    bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    patient_id            bigint      NOT NULL REFERENCES public.royan_patients (id) ON DELETE RESTRICT,
    encounter_id          bigint      REFERENCES public.royan_encounters (id) ON DELETE SET NULL,
    gravida               int,
    para                  int,
    lmp                   date,
    edd                   date,
    gestational_age_weeks int,
    blood_group           text,
    rhesus                text,
    hiv_status            text,
    hbsag                 text,
    syphilis              text,
    malaria_prophylaxis   boolean     NOT NULL DEFAULT false,
    tetanus_toxoid        boolean     NOT NULL DEFAULT false,
    iron_folic_acid       boolean     NOT NULL DEFAULT false,
    risk_factors          text,
    referred_from         text,
    notes                 text,
    registered_by         text,
    status                text        NOT NULL DEFAULT 'active'
                                       CHECK (status IN ('active', 'delivered', 'miscarriage', 'referred')),
    created_at             timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_royan_anc_records_patient ON public.royan_anc_records (patient_id);

CREATE TABLE IF NOT EXISTS public.royan_anc_visits (
    id                    bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    anc_id                bigint      NOT NULL REFERENCES public.royan_anc_records (id) ON DELETE CASCADE,
    patient_id            bigint      NOT NULL REFERENCES public.royan_patients (id) ON DELETE RESTRICT,
    visit_date            date,
    gestational_age_weeks int,
    weight_kg             numeric,
    bp_systolic           int,
    bp_diastolic          int,
    fundal_height_cm      numeric,
    fetal_heart_rate      int,
    presentation          text,
    engagement            text,
    oedema                boolean     NOT NULL DEFAULT false,
    proteinuria           boolean     NOT NULL DEFAULT false,
    haemoglobin           numeric,
    malaria_rapid_test    text,
    drugs_given           text,
    counselling_given     text,
    next_visit_date       date,
    clinician_id          text,
    notes                 text,
    recorded_by           text,
    created_at            timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_royan_anc_visits_anc ON public.royan_anc_visits (anc_id);
CREATE INDEX IF NOT EXISTS idx_royan_anc_visits_patient ON public.royan_anc_visits (patient_id);

CREATE TABLE IF NOT EXISTS public.royan_partograph (
    id                       bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    anc_id                   bigint      NOT NULL REFERENCES public.royan_anc_records (id) ON DELETE CASCADE,
    patient_id               bigint      NOT NULL REFERENCES public.royan_patients (id) ON DELETE RESTRICT,
    recorded_at              timestamptz NOT NULL DEFAULT now(),
    cervical_dilation_cm     numeric     CHECK (cervical_dilation_cm >= 0 AND cervical_dilation_cm <= 10),
    fetal_heart_rate         int,
    contractions_per_10min   int         CHECK (contractions_per_10min >= 0 AND contractions_per_10min <= 5),
    contraction_duration_sec int,
    liquor                   text,
    moulding                 text,
    bp_systolic              int,
    bp_diastolic             int,
    pulse                    int,
    temperature              numeric,
    urine_output_ml          int,
    oxytocin_units           numeric,
    analgesics_given         text,
    notes                    text,
    recorded_by              text
);

CREATE INDEX IF NOT EXISTS idx_royan_partograph_anc ON public.royan_partograph (anc_id);

CREATE TABLE IF NOT EXISTS public.royan_delivery_records (
    id                        bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    anc_id                    bigint      NOT NULL UNIQUE REFERENCES public.royan_anc_records (id) ON DELETE CASCADE,
    patient_id                bigint      NOT NULL REFERENCES public.royan_patients (id) ON DELETE RESTRICT,
    delivery_date             date,
    delivery_time             text,
    mode_of_delivery          text        NOT NULL DEFAULT 'svd',
    indication                text,
    duration_of_labour_hours  numeric,
    blood_loss_ml             numeric,
    placenta_complete         boolean     NOT NULL DEFAULT true,
    perineal_tear             text,
    episiotomy                boolean     NOT NULL DEFAULT false,
    maternal_complications    text,
    anaesthesia_type          text,
    attending_clinician       text,
    notes                     text,
    recorded_by               text,
    created_at                timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_royan_delivery_records_patient ON public.royan_delivery_records (patient_id);

CREATE TABLE IF NOT EXISTS public.royan_newborn_assessment (
    id                        bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    delivery_id               bigint      NOT NULL REFERENCES public.royan_delivery_records (id) ON DELETE CASCADE,
    patient_id                bigint      NOT NULL REFERENCES public.royan_patients (id) ON DELETE RESTRICT,
    sex                       text,
    birth_weight_kg           numeric,
    length_cm                 numeric,
    head_circumference_cm     numeric,
    apgar_1min                int         CHECK (apgar_1min >= 0 AND apgar_1min <= 10),
    apgar_5min                int         CHECK (apgar_5min >= 0 AND apgar_5min <= 10),
    apgar_10min                int        CHECK (apgar_10min >= 0 AND apgar_10min <= 10),
    gestational_age_at_birth  int,
    cry_at_birth               boolean    NOT NULL DEFAULT true,
    resuscitation_needed       boolean    NOT NULL DEFAULT false,
    resuscitation_type        text,
    congenital_anomalies       text,
    eye_prophylaxis            boolean    NOT NULL DEFAULT false,
    vitamin_k_given             boolean   NOT NULL DEFAULT false,
    bcg_given                   boolean   NOT NULL DEFAULT false,
    opv0_given                  boolean   NOT NULL DEFAULT false,
    hbv_given                    boolean  NOT NULL DEFAULT false,
    breast_feeding_initiated     boolean  NOT NULL DEFAULT true,
    notes                     text,
    assessed_by               text,
    created_at                timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_royan_newborn_assessment_delivery ON public.royan_newborn_assessment (delivery_id);
CREATE INDEX IF NOT EXISTS idx_royan_newborn_assessment_patient ON public.royan_newborn_assessment (patient_id);

COMMIT;
