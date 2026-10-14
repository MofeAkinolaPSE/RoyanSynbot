-- Migration 185: Smart Phrases + Immunization Records
--
-- Complete-506-table Hope dump audit (2026-08-21) found two real data
-- sources with no home in the current schema:
--
-- 1. Hope's `smart_phrases`/`smart_phrase_multiple` -- a third, separate
--    dot-phrase/macro system distinct from the note_templates (migration
--    181) and order_sets (migration 179) families already loaded. Invoked
--    by typing a shorthand trigger (e.g. "NEXANKLES") rather than picking
--    from a section dropdown; phrase_text can carry a parameterized
--    placeholder token (e.g. "{side:15002::both sides}") whose selectable
--    values live in smart_phrase_multiple, keyed by list_name.
--
-- 2. Hope's `imunizations` table (~18K real rows, the typo'd table --
--    not its 257-row correctly-spelled sibling) -- actual per-patient
--    vaccine administration history. Migration 158 already seeded
--    royan_vaccine_schedule (what's due, by age) but there was never a
--    table to record what a patient actually received.

BEGIN;

-- ── Smart Phrases ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.royan_smart_phrases (
    id              bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    phrase          text        NOT NULL,   -- shorthand trigger, e.g. "NEXANKLES"
    synonyms        text,
    phrase_text     text        NOT NULL,   -- expansion; may contain {token:id::default} placeholders
    is_nursing      boolean     NOT NULL DEFAULT false,
    is_shared       boolean     NOT NULL DEFAULT true,
    owner_staff_id  uuid        REFERENCES public.royan_staff (id) ON DELETE SET NULL,
    department      text,
    is_active       boolean     NOT NULL DEFAULT true,
    external_source text,
    external_id     text,
    created_at      timestamptz NOT NULL DEFAULT now()
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'royan_smart_phrases_external_source_external_id_key'
    ) THEN
        ALTER TABLE public.royan_smart_phrases
            ADD CONSTRAINT royan_smart_phrases_external_source_external_id_key
            UNIQUE (external_source, external_id);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_royan_smart_phrases_phrase ON public.royan_smart_phrases (lower(phrase));
CREATE INDEX IF NOT EXISTS idx_royan_smart_phrases_owner ON public.royan_smart_phrases (owner_staff_id);

-- Not a per-phrase FK: Hope's phrase_id column here actually references the
-- {token:id::default} placeholder id embedded inside a phrase_text, which a
-- single option list can serve across many different phrases (e.g. a "side"
-- token reused in several exam templates) -- kept as the raw token id.
CREATE TABLE IF NOT EXISTS public.royan_smart_phrase_options (
    id              bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    token_id        text        NOT NULL,
    list_name       text        NOT NULL,
    option_text     text        NOT NULL,
    sort_order      int         NOT NULL DEFAULT 0,
    external_source text,
    external_id     text
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'royan_smart_phrase_options_external_source_external_id_key'
    ) THEN
        ALTER TABLE public.royan_smart_phrase_options
            ADD CONSTRAINT royan_smart_phrase_options_external_source_external_id_key
            UNIQUE (external_source, external_id);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_royan_smart_phrase_options_token
    ON public.royan_smart_phrase_options (token_id, list_name);


-- ── Immunization Records (actual administration history) ───────────────────
CREATE TABLE IF NOT EXISTS public.royan_immunization_records (
    id                 bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    patient_id         bigint      NOT NULL REFERENCES public.royan_patients (id) ON DELETE CASCADE,
    vaccine_schedule_id bigint     REFERENCES public.royan_vaccine_schedule (id) ON DELETE SET NULL,
    vaccine_name       text        NOT NULL,
    dose_number        int,
    administered_at    date,
    administered_by    text,
    batch_number       text,
    notes              text,
    external_source    text,
    external_id        text,
    created_at         timestamptz NOT NULL DEFAULT now()
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'royan_immunization_records_external_source_external_id_key'
    ) THEN
        ALTER TABLE public.royan_immunization_records
            ADD CONSTRAINT royan_immunization_records_external_source_external_id_key
            UNIQUE (external_source, external_id);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_royan_immunization_records_patient
    ON public.royan_immunization_records (patient_id, administered_at DESC);

COMMIT;
