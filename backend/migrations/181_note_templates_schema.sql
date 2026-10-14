-- 181_note_templates_schema.sql
-- Per-SOAP-section note templates -- the single most-requested item from
-- the client meeting: doctors want a dropdown per SOAP section (Subjective/
-- Objective/Assessment/Plan) offering both shared system templates and
-- their own personally-authored ones, shareable between doctors. Hope has
-- real data for exactly this in two related but distinct families:
--   note_templates/note_template_texts   -- shared dot-phrase library,
--     context_type cleanly covers subjective/objective/assessment/plan
--     (98.7% of 8,094 real rows) plus a few bonus categories (Review of
--     Systems, Chief Complaint) that also match meeting asks.
--   doctor_templates/doctor_template_texts -- personal, doctor-authored,
--     full-paragraph templates (a whole HPI/history block, not a short
--     phrase) -- matches the meeting's "doctor built his own custom
--     template" requirement directly. Real category taxonomy (diagnosis,
--     examine, care_plan, etc.), not test/junk data.
-- Unified into one schema since both are conceptually "reusable note
-- content a doctor can select", differentiated by owner_staff_id
-- (null = shared system template, set = personal doctor template).

ROLLBACK;
BEGIN;

CREATE TABLE IF NOT EXISTS public.royan_note_templates (
    id                  bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name                text        NOT NULL,
    scope               text        NOT NULL DEFAULT 'system' CHECK (scope = ANY (ARRAY['system','personal'])),
    category            text,       -- Hope's template_type (e.g. diagnosis, examine, care_plan)
    owner_staff_id      uuid        REFERENCES public.royan_staff(id) ON DELETE SET NULL,
    is_shared           boolean     NOT NULL DEFAULT true,
    department          text,
    is_active           boolean     NOT NULL DEFAULT true,
    external_source     text,
    external_id         text,
    external_updated_at timestamptz,
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_royan_note_templates_external
    ON public.royan_note_templates (external_source, external_id)
    WHERE external_source IS NOT NULL AND external_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_royan_note_templates_active ON public.royan_note_templates (is_active) WHERE is_active = true;
CREATE INDEX IF NOT EXISTS idx_royan_note_templates_owner ON public.royan_note_templates (owner_staff_id);

CREATE TABLE IF NOT EXISTS public.royan_note_template_texts (
    id                   bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    template_id          bigint      NOT NULL REFERENCES public.royan_note_templates(id) ON DELETE CASCADE,
    context_type         text        NOT NULL DEFAULT 'general' CHECK (context_type = ANY (ARRAY[
                              'subjective','objective','assessment','plan','general',
                              'chief_complaint','review_of_systems'
                          ])),
    text                 text        NOT NULL,
    sort_order           int         NOT NULL DEFAULT 0,
    external_source      text,
    external_id          text,
    created_at           timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_royan_note_template_texts_external
    ON public.royan_note_template_texts (external_source, external_id)
    WHERE external_source IS NOT NULL AND external_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_royan_note_template_texts_lookup
    ON public.royan_note_template_texts (template_id, context_type, sort_order);

COMMIT;
