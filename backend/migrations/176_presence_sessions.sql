-- 176_presence_sessions.sql
-- "Who's online" presence tracking: one row per open WebSocket connection
-- (not per user), so a staff member with multiple tabs/devices doesn't drop
-- offline just because one closes. "Online" is computed at read time as
-- last_seen_at within a short staleness window — never relies solely on a
-- clean-disconnect event, since laptop sleep / dropped network can leave a
-- connection half-open without firing one.

ROLLBACK;
BEGIN;

CREATE TABLE IF NOT EXISTS public.royan_presence_sessions (
    id            uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       uuid        NOT NULL REFERENCES public.royan_users(id) ON DELETE CASCADE,
    connected_at  timestamptz NOT NULL DEFAULT now(),
    last_seen_at  timestamptz NOT NULL DEFAULT now(),
    user_agent    text,
    ip_address    text
);

CREATE INDEX IF NOT EXISTS idx_royan_presence_sessions_user      ON public.royan_presence_sessions (user_id);
CREATE INDEX IF NOT EXISTS idx_royan_presence_sessions_last_seen ON public.royan_presence_sessions (last_seen_at);

COMMIT;
