-- Patient signatures (claims forms, drug collection) live in the database, so the one database dump carries
-- everything the hospital needs when the app moves to a server (no separate files to copy). Oct 2026.
CREATE TABLE IF NOT EXISTS royan_signatures (
    name         text PRIMARY KEY,           -- the file name in the URL /pharmacy/signatures/{name}
    content      bytea NOT NULL,
    content_type text NOT NULL DEFAULT 'image/png',
    created_at   timestamptz NOT NULL DEFAULT now()
);
