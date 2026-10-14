-- Migration 191: Ward service charges, patient documents, ward consumption,
--                 doctor schedule blocks, medication administration
--
-- Phase A3 ("finish the job") of the complete-506-table Hope audit. Each
-- table below was confirmed real by direct content sampling, not by row
-- count or naming alone.
--
-- Deliberately NOT included, after checking actual content:
--   * Hope's `guarantors` (15,522) and `guardians` (15,460) -- ZERO rows
--     carry a first or last name. They are placeholder shells auto-created
--     alongside patient records and never populated. No table built.

BEGIN;

-- ── Ward service charges (Hope ward_patient_services, 34,149 real rows) ─────
-- Per-ward-stay service charges: amount/paid split by cash/card, tariff and
-- ward/room refs. Complements royan_ward_stay_history (migration 189, the
-- stay itself) with what was actually billed during that stay.
CREATE TABLE IF NOT EXISTS public.royan_ward_service_charges (
    id                bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    patient_id        bigint      NOT NULL REFERENCES public.royan_patients (id) ON DELETE CASCADE,
    ward_name         text,
    room_name         text,
    service_date      timestamptz,
    amount            numeric(14,2),
    paid_amount       numeric(14,2),
    paid_by_cash      numeric(14,2),
    paid_by_card      numeric(14,2),
    units             numeric(10,2),
    is_capitation     boolean     NOT NULL DEFAULT false,
    tariff_ref        text,
    external_source   text,
    external_id       text,
    created_at        timestamptz NOT NULL DEFAULT now()
);

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='royan_ward_service_charges_ext_key') THEN
        ALTER TABLE public.royan_ward_service_charges
            ADD CONSTRAINT royan_ward_service_charges_ext_key UNIQUE (external_source, external_id);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_royan_ward_service_charges_patient
    ON public.royan_ward_service_charges (patient_id, service_date DESC);


-- ── Patient documents index (Hope patient_documents, 9,192 real rows) ───────
-- Document METADATA only -- filename, mime type, size, description, and the
-- uploader's comment (e.g. "FBS RESULT" / "GOOD GLYCERMIC CONTROL"). The
-- binary files themselves are not migrated; this is an index so staff can
-- see what historical documents exist for a patient and request them.
CREATE TABLE IF NOT EXISTS public.royan_patient_documents (
    id                bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    patient_id        bigint      NOT NULL REFERENCES public.royan_patients (id) ON DELETE CASCADE,
    filename          text,
    mime_type         text,
    size_bytes        bigint,
    description       text,
    comment           text,
    document_date     timestamptz,
    is_migrated       boolean     NOT NULL DEFAULT false,   -- binary not carried over
    external_source   text,
    external_id       text,
    created_at        timestamptz NOT NULL DEFAULT now()
);

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='royan_patient_documents_ext_key') THEN
        ALTER TABLE public.royan_patient_documents
            ADD CONSTRAINT royan_patient_documents_ext_key UNIQUE (external_source, external_id);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_royan_patient_documents_patient
    ON public.royan_patient_documents (patient_id, document_date DESC);


-- ── Ward stock consumption (Hope direct_consumptions, 8,972 w/ patient) ─────
CREATE TABLE IF NOT EXISTS public.royan_ward_consumption (
    id                bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    patient_id        bigint      REFERENCES public.royan_patients (id) ON DELETE SET NULL,
    formulary_id      bigint      REFERENCES public.royan_drug_formulary (id) ON DELETE SET NULL,
    product_ref       text,
    issued_qty        numeric(12,2),
    issued_at         timestamptz,
    external_source   text,
    external_id       text,
    created_at        timestamptz NOT NULL DEFAULT now()
);

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='royan_ward_consumption_ext_key') THEN
        ALTER TABLE public.royan_ward_consumption
            ADD CONSTRAINT royan_ward_consumption_ext_key UNIQUE (external_source, external_id);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_royan_ward_consumption_patient
    ON public.royan_ward_consumption (patient_id, issued_at DESC);


-- ── Doctor schedule blocks (Hope doctor_chambers, 768 real rows) ────────────
-- Recurring/one-off availability + blocked periods per doctor (e.g.
-- "walk - in time" 17:00-18:30). Historical scheduling reference.
CREATE TABLE IF NOT EXISTS public.royan_doctor_schedule_blocks (
    id                bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    staff_id          uuid        REFERENCES public.royan_staff (id) ON DELETE SET NULL,
    doctor_ref        text,
    purpose           text,
    starts_at         timestamptz,
    ends_at           timestamptz,
    start_time        text,
    end_time          text,
    is_blocked        boolean     NOT NULL DEFAULT false,
    is_all_day        boolean     NOT NULL DEFAULT false,
    is_recurring      boolean     NOT NULL DEFAULT false,
    external_source   text,
    external_id       text,
    created_at        timestamptz NOT NULL DEFAULT now()
);

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='royan_doctor_schedule_blocks_ext_key') THEN
        ALTER TABLE public.royan_doctor_schedule_blocks
            ADD CONSTRAINT royan_doctor_schedule_blocks_ext_key UNIQUE (external_source, external_id);
    END IF;
END $$;


-- ── Medication administration records (Hope MAR, 109 real rows) ─────────────
CREATE TABLE IF NOT EXISTS public.royan_medication_administration (
    id                bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    patient_id        bigint      NOT NULL REFERENCES public.royan_patients (id) ON DELETE CASCADE,
    performed_at      timestamptz,
    performed_by      text,
    pain_intensity    int,
    not_given         boolean     NOT NULL DEFAULT false,
    is_signed         boolean     NOT NULL DEFAULT false,
    nurse_data        text,       -- Hope's raw pipe-delimited blob, kept verbatim
    external_source   text,
    external_id       text,
    created_at        timestamptz NOT NULL DEFAULT now()
);

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='royan_medication_administration_ext_key') THEN
        ALTER TABLE public.royan_medication_administration
            ADD CONSTRAINT royan_medication_administration_ext_key UNIQUE (external_source, external_id);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_royan_medication_administration_patient
    ON public.royan_medication_administration (patient_id, performed_at DESC);

COMMIT;
