-- Migration 160: Notes Master + Pause/Resume Consultation
--
-- Client ask (backend/docs/NL-Master-guide/*): the client's legacy system
-- (DRM Hope) drives clinical note entry from a department-scoped catalog of
-- note titles ("Urology Note," etc.) rather than free text. Today
-- royan_encounter_notes.note_type is a hardcoded 4-value field with no
-- catalog behind it. This adds that catalog, plus two small non-status
-- columns on royan_encounters to support a Pause/Resume Consultation action
-- (a named Quick Action in the OPD department blueprint with no backing
-- state today) without touching the encounter status state machine.

ROLLBACK;
BEGIN;

CREATE TABLE IF NOT EXISTS public.royan_note_titles (
    id              bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title           text        NOT NULL,
    category        text        NOT NULL DEFAULT 'general'
                                CHECK (category IN ('general','assessment','plan','soap','progress','discharge')),
    department_id   bigint      REFERENCES public.royan_departments (id) ON DELETE SET NULL,  -- NULL = all departments
    template_fields jsonb,                                    -- optional structured fields; NULL = free text
    allowed_roles   text[],                                   -- NULL/empty = all roles
    is_active       boolean     NOT NULL DEFAULT true,
    sort_order      int         NOT NULL DEFAULT 0,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_royan_note_titles_title_dept
    ON public.royan_note_titles (title, COALESCE(department_id, 0));
CREATE INDEX IF NOT EXISTS idx_royan_note_titles_department ON public.royan_note_titles (department_id);
CREATE INDEX IF NOT EXISTS idx_royan_note_titles_active     ON public.royan_note_titles (is_active);

ALTER TABLE public.royan_encounter_notes
    ADD COLUMN IF NOT EXISTS note_title_id bigint REFERENCES public.royan_note_titles(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS note_title    text;   -- denormalized snapshot, survives later title rename/deactivation

ALTER TABLE public.royan_encounters
    ADD COLUMN IF NOT EXISTS paused_at     timestamptz,
    ADD COLUMN IF NOT EXISTS paused_reason text;

INSERT INTO public.royan_note_titles (title, category, department_id, sort_order) VALUES
    ('SOAP Progress Note',     'soap',       NULL, 1),
    ('General Clinical Note',  'general',    NULL, 2),
    ('Assessment Note',        'assessment', NULL, 3),
    ('Plan / Management Note', 'plan',       NULL, 4)
ON CONFLICT DO NOTHING;

INSERT INTO public.royan_note_titles (title, category, department_id, sort_order)
SELECT 'OPD Consultation Note', 'soap', d.id, 5 FROM public.royan_departments d WHERE d.code = 'OPD'
ON CONFLICT DO NOTHING;

COMMIT;
