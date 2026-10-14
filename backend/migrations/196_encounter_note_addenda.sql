-- Migration 196: clinical note addenda (medico-legal amendment trail)
--
-- Phase B0. The MD was emphatic in the post-deployment meeting:
--   "don't alter, no alteration... this is what they are requesting in court.
--    You can't be changing what you have written four, five years ago."
--
-- royan_encounter_notes is already immutable BY OMISSION — there is no PATCH,
-- PUT or DELETE route for it anywhere in the codebase, and notes are signed at
-- insert (queue_clinical.py sets signed_by/signed_at). What was missing is the
-- sanctioned way to CORRECT a signed note: an append-only, separately
-- attributed and timestamped addendum.
--
-- Modelled as a CHILD TABLE rather than extra columns on royan_encounter_notes
-- so that migration 171's note_type CHECK constraint is untouched, a note can
-- carry N addenda over time, and each addendum keeps its own author — the
-- person amending is frequently not the person who signed.
--
-- Hope's own progresstbls carried exactly this shape (addendum / addendum_by /
-- addendum_date, plus reason_to_unsign / unsign_by / unsign_date), which is
-- where the migrated progress notes' addendum text came from.

BEGIN;

CREATE TABLE IF NOT EXISTS public.royan_encounter_note_addenda (
    id           bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    note_id      bigint      NOT NULL REFERENCES public.royan_encounter_notes (id) ON DELETE CASCADE,
    content      text        NOT NULL,
    reason       text,
    author_id    text,
    author_name  text,
    signed_by    uuid        REFERENCES public.royan_staff (id) ON DELETE SET NULL,
    created_at   timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_royan_note_addenda_note
    ON public.royan_encounter_note_addenda (note_id, created_at);

COMMIT;
