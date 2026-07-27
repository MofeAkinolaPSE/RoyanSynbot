-- Migration 154: Radiology report text-snippet templates
--
-- Client ask (Post-deployment-mods/promptplan.md preamble + SCANCARE
-- TEMPLATES/ folder, ~40 .docx files): each study type has a canned
-- normal-findings boilerplate report (organ-by-organ narrative with blanks
-- for specific measurements) that the radiologist loads, edits per-patient,
-- and submits. This is a text-snippet library, not a structured numeric
-- form like the lab templates in migration 153 — royan_radiology_orders'
-- existing free-text report/impression/findings columns are untouched; a
-- template just pre-fills them client-side before editing.

ROLLBACK;
BEGIN;

CREATE TABLE IF NOT EXISTS public.royan_report_templates (
    id            bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    modality      text        NOT NULL,   -- matches RADIOLOGY_MODALITIES_ALLOWED (xray, ultrasound, ecg, ...)
    body_part     text,                   -- best-effort; the picker is name-search first, not a strict taxonomy
    variant_name  text        NOT NULL,   -- e.g. "ABDOMINO-PELVIC FEMALE" vs "ABDOMEN IN PREGNANCY" — same
                                           -- general study, different canned findings
    template_text text        NOT NULL,
    source_file   text,                   -- original .docx filename, for traceability back to the client's source
    is_active     boolean     NOT NULL DEFAULT true,
    created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_royan_report_templates_modality
    ON public.royan_report_templates (modality) WHERE is_active;

COMMIT;
