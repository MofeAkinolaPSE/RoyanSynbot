ROLLBACK;
BEGIN;

ALTER TABLE public.royan_theatre_cases
    ADD COLUMN IF NOT EXISTS operative_notes_verified_by      text,
    ADD COLUMN IF NOT EXISTS operative_notes_verified_at      timestamptz,
    ADD COLUMN IF NOT EXISTS operative_notes_amendment_reason text,
    ADD COLUMN IF NOT EXISTS operative_notes_history          jsonb NOT NULL DEFAULT '[]'::jsonb;

CREATE INDEX IF NOT EXISTS idx_theatre_cases_op_notes_verified_at
    ON public.royan_theatre_cases (operative_notes_verified_at) WHERE operative_notes_verified_at IS NOT NULL;

COMMIT;
