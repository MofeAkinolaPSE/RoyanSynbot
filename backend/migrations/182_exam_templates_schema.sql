-- 182_exam_templates_schema.sql
-- Review-of-Systems / Physical-Exam finding picker -- confirmed real data:
-- template_categories (3: "Review Of System", "Physical Examination", "HPI")
-- -> templates (151 real organ-system rows: "Eyes", "Constitutional
-- Symptoms", "Ears, nose, mouth and throat", etc.) -> template_sub_categories
-- (45,665 real selectable finding phrases per organ system, e.g. "Negative",
-- "Fever", "Negative except HPI"). Matches the meeting's Objective/exam
-- template ask (specialty-specific exam pre-population) at the
-- organ-system/finding-checklist level.
--
-- template_type_contents (2,679 rows) is deliberately NOT part of this
-- schema -- it's historical per-patient applied selections stored as raw
-- PHP serialize() blobs, not reference/catalog data, and out of scope for
-- "give doctors real dropdown content" (same priority call already made
-- for other historical-backfill-vs-catalog tradeoffs in this project).

ROLLBACK;
BEGIN;

CREATE TABLE IF NOT EXISTS public.royan_exam_templates (
    id                  bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    category            text        NOT NULL,   -- Review of Systems | Physical Examination | HPI
    organ_system        text        NOT NULL,   -- e.g. "Eyes", "Constitutional Symptoms"
    is_female_only       boolean     NOT NULL DEFAULT false,
    sort_order          int         NOT NULL DEFAULT 0,
    is_active           boolean     NOT NULL DEFAULT true,
    external_source     text,
    external_id         text,
    external_updated_at timestamptz,
    created_at          timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_royan_exam_templates_external
    ON public.royan_exam_templates (external_source, external_id)
    WHERE external_source IS NOT NULL AND external_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_royan_exam_templates_lookup
    ON public.royan_exam_templates (category, sort_order);

CREATE TABLE IF NOT EXISTS public.royan_exam_template_findings (
    id                  bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    exam_template_id    bigint      NOT NULL REFERENCES public.royan_exam_templates(id) ON DELETE CASCADE,
    finding             text        NOT NULL,   -- e.g. "Negative", "Fever"
    is_default          boolean     NOT NULL DEFAULT false,
    sort_order          int         NOT NULL DEFAULT 0,
    external_source     text,
    external_id         text,
    created_at          timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_royan_exam_template_findings_external
    ON public.royan_exam_template_findings (external_source, external_id)
    WHERE external_source IS NOT NULL AND external_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_royan_exam_template_findings_lookup
    ON public.royan_exam_template_findings (exam_template_id, sort_order);

COMMIT;
