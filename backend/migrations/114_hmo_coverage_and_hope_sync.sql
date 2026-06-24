-- 114_hmo_coverage_and_hope_sync.sql
-- Synbot Health Core MVP: configurable HMO coverage engine + read-only Hope sync metadata

BEGIN;

-- Attach external-source identifiers to existing hospital-domain records so
-- read-only legacy sync can be idempotent without making Hope authoritative.
ALTER TABLE public.royan_patients
    ADD COLUMN IF NOT EXISTS external_source text,
    ADD COLUMN IF NOT EXISTS external_id text,
    ADD COLUMN IF NOT EXISTS external_updated_at timestamptz;

ALTER TABLE public.royan_encounters
    ADD COLUMN IF NOT EXISTS external_source text,
    ADD COLUMN IF NOT EXISTS external_id text,
    ADD COLUMN IF NOT EXISTS external_updated_at timestamptz;

ALTER TABLE public.royan_lab_orders
    ADD COLUMN IF NOT EXISTS external_source text,
    ADD COLUMN IF NOT EXISTS external_id text,
    ADD COLUMN IF NOT EXISTS external_updated_at timestamptz;

ALTER TABLE public.royan_prescriptions
    ADD COLUMN IF NOT EXISTS external_source text,
    ADD COLUMN IF NOT EXISTS external_id text,
    ADD COLUMN IF NOT EXISTS external_updated_at timestamptz;

ALTER TABLE public.royan_billing
    ADD COLUMN IF NOT EXISTS external_source text,
    ADD COLUMN IF NOT EXISTS external_id text,
    ADD COLUMN IF NOT EXISTS external_updated_at timestamptz;

ALTER TABLE public.royan_appointments
    ADD COLUMN IF NOT EXISTS external_source text,
    ADD COLUMN IF NOT EXISTS external_id text,
    ADD COLUMN IF NOT EXISTS external_updated_at timestamptz;

ALTER TABLE public.royan_appointment_slots
    ADD COLUMN IF NOT EXISTS external_source text,
    ADD COLUMN IF NOT EXISTS external_id text,
    ADD COLUMN IF NOT EXISTS external_updated_at timestamptz;

CREATE UNIQUE INDEX IF NOT EXISTS uq_royan_patients_external
    ON public.royan_patients (external_source, external_id)
    WHERE external_source IS NOT NULL AND external_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_royan_encounters_external
    ON public.royan_encounters (external_source, external_id)
    WHERE external_source IS NOT NULL AND external_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_royan_lab_orders_external
    ON public.royan_lab_orders (external_source, external_id)
    WHERE external_source IS NOT NULL AND external_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_royan_prescriptions_external
    ON public.royan_prescriptions (external_source, external_id)
    WHERE external_source IS NOT NULL AND external_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_royan_billing_external
    ON public.royan_billing (external_source, external_id)
    WHERE external_source IS NOT NULL AND external_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_royan_appointments_external
    ON public.royan_appointments (external_source, external_id)
    WHERE external_source IS NOT NULL AND external_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_royan_appointment_slots_external
    ON public.royan_appointment_slots (external_source, external_id)
    WHERE external_source IS NOT NULL AND external_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS public.royan_hmos (
    id              bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name            text        NOT NULL UNIQUE,
    code            text        UNIQUE,
    contact_phone   text,
    contact_email   text,
    is_active       boolean     NOT NULL DEFAULT true,
    notes           text,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.royan_hmo_plans (
    id              bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    hmo_id          bigint      NOT NULL REFERENCES public.royan_hmos (id) ON DELETE CASCADE,
    name            text        NOT NULL,
    plan_code       text,
    is_active       boolean     NOT NULL DEFAULT true,
    notes           text,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (hmo_id, name)
);

CREATE TABLE IF NOT EXISTS public.royan_patient_insurance (
    id              bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    patient_id      bigint      NOT NULL REFERENCES public.royan_patients (id) ON DELETE CASCADE,
    hmo_id          bigint      NOT NULL REFERENCES public.royan_hmos (id) ON DELETE RESTRICT,
    plan_id         bigint      REFERENCES public.royan_hmo_plans (id) ON DELETE SET NULL,
    membership_id   text        NOT NULL,
    status          text        NOT NULL DEFAULT 'active'
                                CHECK (status IN ('active', 'expired', 'suspended', 'inactive')),
    valid_from      date,
    valid_to        date,
    is_primary      boolean     NOT NULL DEFAULT true,
    source          text        NOT NULL DEFAULT 'synbot',
    notes           text,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_royan_patient_insurance_primary
    ON public.royan_patient_insurance (patient_id)
    WHERE is_primary = true AND status = 'active';

CREATE INDEX IF NOT EXISTS idx_royan_patient_insurance_hmo
    ON public.royan_patient_insurance (hmo_id);

CREATE TABLE IF NOT EXISTS public.royan_service_catalog (
    id              bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    service_code    text        NOT NULL UNIQUE,
    name            text        NOT NULL,
    category        text        NOT NULL
                                CHECK (category IN ('consultation', 'lab', 'pharmacy', 'ward', 'procedure', 'imaging', 'misc')),
    base_price      numeric     NOT NULL DEFAULT 0 CHECK (base_price >= 0),
    is_active       boolean     NOT NULL DEFAULT true,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.royan_coverage_rules (
    id                  bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    hmo_id              bigint      NOT NULL REFERENCES public.royan_hmos (id) ON DELETE CASCADE,
    plan_id             bigint      REFERENCES public.royan_hmo_plans (id) ON DELETE CASCADE,
    service_id          bigint      NOT NULL REFERENCES public.royan_service_catalog (id) ON DELETE CASCADE,
    coverage_type       text        NOT NULL DEFAULT 'none'
                                    CHECK (coverage_type IN ('percent', 'fixed', 'none', 'capitation')),
    coverage_value      numeric     NOT NULL DEFAULT 0 CHECK (coverage_value >= 0),
    requires_approval   boolean     NOT NULL DEFAULT false,
    limit_type          text        NOT NULL DEFAULT 'none'
                                    CHECK (limit_type IN ('none', 'per_visit', 'per_month')),
    limit_value         numeric     CHECK (limit_value IS NULL OR limit_value >= 0),
    is_active           boolean     NOT NULL DEFAULT true,
    notes               text,
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    UNIQUE (hmo_id, plan_id, service_id)
);

CREATE INDEX IF NOT EXISTS idx_royan_coverage_rules_lookup
    ON public.royan_coverage_rules (hmo_id, plan_id, service_id)
    WHERE is_active = true;

CREATE TABLE IF NOT EXISTS public.royan_coverage_authorizations (
    id                  bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    patient_id          bigint      NOT NULL REFERENCES public.royan_patients (id) ON DELETE CASCADE,
    encounter_id        bigint      REFERENCES public.royan_encounters (id) ON DELETE SET NULL,
    coverage_rule_id    bigint      REFERENCES public.royan_coverage_rules (id) ON DELETE SET NULL,
    service_id          bigint      REFERENCES public.royan_service_catalog (id) ON DELETE SET NULL,
    status              text        NOT NULL DEFAULT 'requested'
                                    CHECK (status IN ('requested', 'approved', 'rejected', 'expired', 'cancelled')),
    requested_amount    numeric     NOT NULL DEFAULT 0,
    approved_amount     numeric,
    authorization_code  text,
    requested_by        text,
    decided_by          text,
    requested_at        timestamptz NOT NULL DEFAULT now(),
    decided_at          timestamptz,
    notes               text
);

CREATE INDEX IF NOT EXISTS idx_royan_coverage_authorizations_patient
    ON public.royan_coverage_authorizations (patient_id, status);

CREATE TABLE IF NOT EXISTS public.royan_bill_items (
    id                  bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    billing_id          bigint      NOT NULL REFERENCES public.royan_billing (id) ON DELETE CASCADE,
    encounter_id        bigint      NOT NULL REFERENCES public.royan_encounters (id) ON DELETE RESTRICT,
    patient_id          bigint      NOT NULL REFERENCES public.royan_patients (id) ON DELETE RESTRICT,
    service_id          bigint      REFERENCES public.royan_service_catalog (id) ON DELETE SET NULL,
    service_code        text,
    description         text        NOT NULL,
    category            text        NOT NULL DEFAULT 'misc',
    quantity            numeric     NOT NULL DEFAULT 1 CHECK (quantity > 0),
    unit_price          numeric     NOT NULL DEFAULT 0 CHECK (unit_price >= 0),
    gross_amount        numeric     GENERATED ALWAYS AS (quantity * unit_price) STORED,
    covered_amount      numeric     NOT NULL DEFAULT 0,
    patient_amount      numeric     NOT NULL DEFAULT 0,
    requires_approval   boolean     NOT NULL DEFAULT false,
    approval_required_reason text,
    coverage_rule_id    bigint      REFERENCES public.royan_coverage_rules (id) ON DELETE SET NULL,
    coverage_snapshot   jsonb,
    created_at          timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_royan_bill_items_billing
    ON public.royan_bill_items (billing_id);

CREATE TABLE IF NOT EXISTS public.royan_hope_sync_runs (
    id              bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    entity          text        NOT NULL,
    status          text        NOT NULL CHECK (status IN ('started', 'success', 'failed')),
    started_at      timestamptz NOT NULL DEFAULT now(),
    completed_at    timestamptz,
    rows_seen       int         NOT NULL DEFAULT 0,
    rows_upserted   int         NOT NULL DEFAULT 0,
    error_message   text,
    metadata        jsonb       NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_royan_hope_sync_runs_entity
    ON public.royan_hope_sync_runs (entity, started_at DESC);

INSERT INTO public.royan_service_catalog (service_code, name, category, base_price)
VALUES
    ('CONSULT-GEN', 'General Consultation', 'consultation', 0),
    ('LAB-FBC', 'Full Blood Count', 'lab', 0),
    ('PHARM-GENERIC', 'Prescription Medicine', 'pharmacy', 0),
    ('WARD-DAY', 'Ward Bed Day', 'ward', 0),
    ('PROC-GENERAL', 'General Procedure', 'procedure', 0)
ON CONFLICT (service_code) DO NOTHING;

COMMIT;
