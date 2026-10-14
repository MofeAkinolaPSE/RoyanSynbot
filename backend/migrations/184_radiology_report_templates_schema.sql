-- 184_radiology_report_templates_schema.sql
-- Real radiology report section templates from Hope (radiology_templates:
-- 184 rows, one per radiology exam-type x report section [FINDINGS/
-- OPINIONS/IMPRESSION]; radiology_template_texts: 191 real selectable
-- phrase snippets, e.g. genuine Doppler-study finding language). Kept as
-- a new dedicated table rather than forced into the existing
-- royan_report_templates (modality/body_part/variant_name shape, seeded
-- from a separate licensed reference library) since deriving
-- modality/body_part from Hope's radiology_id would need the radiology
-- test catalog extracted too -- not done in this pass, and this data's
-- own exam-type/section structure is a cleaner, more direct fit.

ROLLBACK;
BEGIN;

CREATE TABLE IF NOT EXISTS public.royan_radiology_report_templates (
    id                  bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    exam_type_ref       text,       -- Hope's radiology_id (exam-type reference, not yet resolved to a name)
    section             text        NOT NULL,   -- e.g. FINDINGS, OPINIONS, IMPRESSION
    location_ref        text,       -- Hope's location_id, kept raw since most branch names aren't in this dump
    is_active           boolean     NOT NULL DEFAULT true,
    external_source     text,
    external_id         text,
    external_updated_at timestamptz,
    created_at          timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_royan_radiology_report_templates_external
    ON public.royan_radiology_report_templates (external_source, external_id)
    WHERE external_source IS NOT NULL AND external_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_royan_radiology_report_templates_lookup
    ON public.royan_radiology_report_templates (exam_type_ref, section);

CREATE TABLE IF NOT EXISTS public.royan_radiology_report_template_texts (
    id                   bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    template_id          bigint      NOT NULL REFERENCES public.royan_radiology_report_templates(id) ON DELETE CASCADE,
    text                 text        NOT NULL,
    sort_order           int         NOT NULL DEFAULT 0,
    external_source      text,
    external_id          text,
    created_at           timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_royan_radiology_report_template_texts_external
    ON public.royan_radiology_report_template_texts (external_source, external_id)
    WHERE external_source IS NOT NULL AND external_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_royan_radiology_report_template_texts_lookup
    ON public.royan_radiology_report_template_texts (template_id, sort_order);

COMMIT;
