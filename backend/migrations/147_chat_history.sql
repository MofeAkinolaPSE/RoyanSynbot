-- Migration 147: Create the missing royan_chat_history table
--
-- backend/src/db.py::save_chat_history/get_chat_history have referenced this
-- table since before this migration existed, but no migration ever created
-- it — every save/load has been silently failing (caught by a bare
-- except/logging.error, so the app never crashed) since Roy's per-user
-- "remembers your last few turns" conversational memory was added.
--
-- This failure mode had a real side effect: Postgres logs the full statement
-- text alongside any ERROR by default (log_min_error_statement='error', a
-- stock default, not a special verbose-logging config), and because the app
-- sends fully value-interpolated SQL rather than true server-side bound
-- parameters, the logged "failed" INSERT statements contained complete
-- plaintext chat transcripts in the royan_db container's own log stream.
-- Creating the table stops the errors, which stops this leak at the source.

ROLLBACK;
BEGIN;

CREATE TABLE IF NOT EXISTS public.royan_chat_history (
    id         uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    uuid        REFERENCES public.royan_users (id) ON DELETE CASCADE,
    question   text        NOT NULL,
    answer     text        NOT NULL,
    sources    jsonb        NOT NULL DEFAULT '[]'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_royan_chat_history_user_created
    ON public.royan_chat_history (user_id, created_at DESC);

COMMIT;
