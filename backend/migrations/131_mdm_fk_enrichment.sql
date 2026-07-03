-- 131_mdm_fk_enrichment.sql
-- MDM FK Enrichment — Chapter 4 / Blueprint Phase 1B
-- Adds nullable FK columns to existing operational tables linking them to master
-- tables created in migration 130. Text columns are preserved for backwards
-- compatibility; FK columns are populated during the DrM enrichment ETL pass.
-- All operations are idempotent (IF NOT EXISTS / DO blocks).

BEGIN;

-- ─────────────────────────────────────────────────────────────────────────────
-- royan_encounters: add department_id + doctor_id FKs
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE public.royan_encounters
    ADD COLUMN IF NOT EXISTS department_id      bigint,
    ADD COLUMN IF NOT EXISTS doctor_id          uuid;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_encounters_department'
          AND conrelid = 'public.royan_encounters'::regclass
    ) THEN
        ALTER TABLE public.royan_encounters
            ADD CONSTRAINT fk_encounters_department
            FOREIGN KEY (department_id) REFERENCES public.royan_departments (id)
            ON DELETE SET NULL NOT VALID;
    END IF;
END;
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_encounters_doctor'
          AND conrelid = 'public.royan_encounters'::regclass
    ) THEN
        ALTER TABLE public.royan_encounters
            ADD CONSTRAINT fk_encounters_doctor
            FOREIGN KEY (doctor_id) REFERENCES public.royan_staff (id)
            ON DELETE SET NULL NOT VALID;
    END IF;
END;
$$;

CREATE INDEX IF NOT EXISTS idx_royan_encounters_dept_id   ON public.royan_encounters (department_id);
CREATE INDEX IF NOT EXISTS idx_royan_encounters_doctor_id ON public.royan_encounters (doctor_id);


-- ─────────────────────────────────────────────────────────────────────────────
-- royan_lab_orders: add catalog_id + ordered_by_id FKs
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE public.royan_lab_orders
    ADD COLUMN IF NOT EXISTS catalog_id         bigint,
    ADD COLUMN IF NOT EXISTS ordered_by_id      uuid;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_lab_orders_catalog'
          AND conrelid = 'public.royan_lab_orders'::regclass
    ) THEN
        ALTER TABLE public.royan_lab_orders
            ADD CONSTRAINT fk_lab_orders_catalog
            FOREIGN KEY (catalog_id) REFERENCES public.royan_lab_catalog (id)
            ON DELETE SET NULL NOT VALID;
    END IF;
END;
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_lab_orders_ordered_by'
          AND conrelid = 'public.royan_lab_orders'::regclass
    ) THEN
        ALTER TABLE public.royan_lab_orders
            ADD CONSTRAINT fk_lab_orders_ordered_by
            FOREIGN KEY (ordered_by_id) REFERENCES public.royan_staff (id)
            ON DELETE SET NULL NOT VALID;
    END IF;
END;
$$;

CREATE INDEX IF NOT EXISTS idx_royan_lab_orders_catalog_id     ON public.royan_lab_orders (catalog_id);
CREATE INDEX IF NOT EXISTS idx_royan_lab_orders_ordered_by_id  ON public.royan_lab_orders (ordered_by_id);


-- ─────────────────────────────────────────────────────────────────────────────
-- royan_prescriptions: add formulary_id + prescribed_by_id FKs
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE public.royan_prescriptions
    ADD COLUMN IF NOT EXISTS formulary_id       bigint,
    ADD COLUMN IF NOT EXISTS prescribed_by_id   uuid;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_prescriptions_formulary'
          AND conrelid = 'public.royan_prescriptions'::regclass
    ) THEN
        ALTER TABLE public.royan_prescriptions
            ADD CONSTRAINT fk_prescriptions_formulary
            FOREIGN KEY (formulary_id) REFERENCES public.royan_drug_formulary (id)
            ON DELETE SET NULL NOT VALID;
    END IF;
END;
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_prescriptions_prescribed_by'
          AND conrelid = 'public.royan_prescriptions'::regclass
    ) THEN
        ALTER TABLE public.royan_prescriptions
            ADD CONSTRAINT fk_prescriptions_prescribed_by
            FOREIGN KEY (prescribed_by_id) REFERENCES public.royan_staff (id)
            ON DELETE SET NULL NOT VALID;
    END IF;
END;
$$;

CREATE INDEX IF NOT EXISTS idx_royan_prescriptions_formulary_id     ON public.royan_prescriptions (formulary_id);
CREATE INDEX IF NOT EXISTS idx_royan_prescriptions_prescribed_by_id ON public.royan_prescriptions (prescribed_by_id);


-- ─────────────────────────────────────────────────────────────────────────────
-- royan_billing: add hmo_id FK (links to authoritative royan_hmos)
-- Complements existing text hmo_provider column
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE public.royan_billing
    ADD COLUMN IF NOT EXISTS hmo_id     bigint;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_billing_hmo'
          AND conrelid = 'public.royan_billing'::regclass
    ) THEN
        ALTER TABLE public.royan_billing
            ADD CONSTRAINT fk_billing_hmo
            FOREIGN KEY (hmo_id) REFERENCES public.royan_hmos (id)
            ON DELETE SET NULL NOT VALID;
    END IF;
END;
$$;

CREATE INDEX IF NOT EXISTS idx_royan_billing_hmo_id ON public.royan_billing (hmo_id);


-- ─────────────────────────────────────────────────────────────────────────────
-- royan_insurance_claims: add hmo_id FK
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE public.royan_insurance_claims
    ADD COLUMN IF NOT EXISTS hmo_id     bigint;

DO $$
BEGIN
    -- Only create FK if hmo_id is bigint (may already exist as text in legacy schema)
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='public' AND table_name='royan_insurance_claims'
          AND column_name='hmo_id' AND data_type='bigint'
    ) AND NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_insurance_claims_hmo'
          AND conrelid = 'public.royan_insurance_claims'::regclass
    ) THEN
        ALTER TABLE public.royan_insurance_claims
            ADD CONSTRAINT fk_insurance_claims_hmo
            FOREIGN KEY (hmo_id) REFERENCES public.royan_hmos (id)
            ON DELETE SET NULL NOT VALID;
    END IF;
END;
$$;

CREATE INDEX IF NOT EXISTS idx_royan_insurance_claims_hmo_id ON public.royan_insurance_claims (hmo_id);


-- ─────────────────────────────────────────────────────────────────────────────
-- royan_patients: add primary_doctor_id (assigned GP / primary physician)
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE public.royan_patients
    ADD COLUMN IF NOT EXISTS primary_doctor_id  uuid,
    ADD COLUMN IF NOT EXISTS primary_dept_id    bigint;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_patients_primary_doctor'
          AND conrelid = 'public.royan_patients'::regclass
    ) THEN
        ALTER TABLE public.royan_patients
            ADD CONSTRAINT fk_patients_primary_doctor
            FOREIGN KEY (primary_doctor_id) REFERENCES public.royan_staff (id)
            ON DELETE SET NULL NOT VALID;
    END IF;
END;
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_patients_primary_dept'
          AND conrelid = 'public.royan_patients'::regclass
    ) THEN
        ALTER TABLE public.royan_patients
            ADD CONSTRAINT fk_patients_primary_dept
            FOREIGN KEY (primary_dept_id) REFERENCES public.royan_departments (id)
            ON DELETE SET NULL NOT VALID;
    END IF;
END;
$$;


-- ─────────────────────────────────────────────────────────────────────────────
-- royan_wards: add department_id FK (link ward to owning department)
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE public.royan_wards
    ADD COLUMN IF NOT EXISTS department_id  bigint;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_wards_department'
          AND conrelid = 'public.royan_wards'::regclass
    ) THEN
        ALTER TABLE public.royan_wards
            ADD CONSTRAINT fk_wards_department
            FOREIGN KEY (department_id) REFERENCES public.royan_departments (id)
            ON DELETE SET NULL NOT VALID;
    END IF;
END;
$$;

CREATE INDEX IF NOT EXISTS idx_royan_wards_department_id ON public.royan_wards (department_id);


-- ─────────────────────────────────────────────────────────────────────────────
-- Populate ward department links for known ward types
-- ─────────────────────────────────────────────────────────────────────────────
UPDATE public.royan_wards w
SET department_id = d.id
FROM public.royan_departments d
WHERE w.department_id IS NULL
  AND (
    (w.ward_type = 'icu'       AND d.code = 'ICU')     OR
    (w.ward_type = 'maternity' AND d.code = 'MATERN')  OR
    (w.ward_type = 'surgical'  AND d.code = 'SURG')    OR
    (w.ward_type = 'paediatric'AND d.code = 'PAEDS')   OR
    (w.ward_type = 'emergency' AND d.code = 'AE')      OR
    (w.ward_type IN ('general','private','isolation') AND d.code = 'IPD')
  );

COMMIT;
