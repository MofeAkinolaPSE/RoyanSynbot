-- Migration 194: Radiology catalog, surgery catalog, and the Hope
--                 reference archive (final Phase A3 schema)
--
-- Closes out the complete-506-table Hope audit. Two real catalogs get
-- proper tables because they have clear semantics and a live consumer;
-- the long tail goes to a single queryable archive rather than ~60
-- migrations for tables of 5-200 rows that nothing references yet.
--
-- 1. royan_radiology_catalog  <- Hope `radiologies` (211 real rows, e.g.
--    "ULTRASOUND FOLLICULAR TRACKING ONE SESSION"). Mirrors the existing
--    royan_lab_catalog. Directly powers the radiology-order autocomplete
--    the client asked for -- until now radiology orders carried a free-text
--    test_name with no catalog behind it.
--
-- 2. royan_surgery_catalog    <- Hope `surgeries` (112) + surgery_categories
--    (9) + surgery_subcategories (14). Named procedures with surgeon fees.
--
-- 3. royan_hope_reference_archive <- EVERY remaining staged Hope table not
--    otherwise loaded, one row per source row, full payload as jsonb.
--    Rationale: the user's directive was to extract everything "so we don't
--    have to come back to it", including low-value data. Inventing a bespoke
--    schema for each of ~60 small reference tables (and for large but
--    consumer-less ones like ndc_masters/accounts/voucher_logs) would be
--    schema nobody asked for and nobody maintains. This keeps 100% of the
--    content, queryable via jsonb operators, and lets any of it be promoted
--    to a real table later if a consumer appears.

BEGIN;

-- ── Radiology test catalog ─────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.royan_radiology_catalog (
    id                bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name              text        NOT NULL,
    modality          text,
    test_group_ref    text,
    service_group_ref text,
    is_active         boolean     NOT NULL DEFAULT true,
    external_source   text,
    external_id       text,
    created_at        timestamptz NOT NULL DEFAULT now()
);
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='royan_radiology_catalog_ext_key') THEN
        ALTER TABLE public.royan_radiology_catalog
            ADD CONSTRAINT royan_radiology_catalog_ext_key UNIQUE (external_source, external_id);
    END IF;
END $$;
CREATE INDEX IF NOT EXISTS idx_royan_radiology_catalog_name
    ON public.royan_radiology_catalog (lower(name));


-- ── Surgery / procedure catalog ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.royan_surgery_catalog (
    id                bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name              text        NOT NULL,
    description       text,
    category_name     text,
    sub_category_name text,
    surgeon_fee       numeric(14,2),
    is_active         boolean     NOT NULL DEFAULT true,
    external_source   text,
    external_id       text,
    created_at        timestamptz NOT NULL DEFAULT now()
);
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='royan_surgery_catalog_ext_key') THEN
        ALTER TABLE public.royan_surgery_catalog
            ADD CONSTRAINT royan_surgery_catalog_ext_key UNIQUE (external_source, external_id);
    END IF;
END $$;
CREATE INDEX IF NOT EXISTS idx_royan_surgery_catalog_name
    ON public.royan_surgery_catalog (lower(name));


-- ── Generic Hope reference archive ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.royan_hope_reference_archive (
    id                bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_table      text        NOT NULL,   -- Hope table name
    source_row_id     text,                   -- Hope row id where one exists
    payload           jsonb       NOT NULL,   -- the full source row
    external_source   text,
    external_id       text,                   -- "{source_table}:{source_row_id}"
    created_at        timestamptz NOT NULL DEFAULT now()
);
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='royan_hope_reference_archive_ext_key') THEN
        ALTER TABLE public.royan_hope_reference_archive
            ADD CONSTRAINT royan_hope_reference_archive_ext_key UNIQUE (external_source, external_id);
    END IF;
END $$;
CREATE INDEX IF NOT EXISTS idx_royan_hope_ref_archive_table
    ON public.royan_hope_reference_archive (source_table);
CREATE INDEX IF NOT EXISTS idx_royan_hope_ref_archive_payload
    ON public.royan_hope_reference_archive USING gin (payload);

COMMIT;
