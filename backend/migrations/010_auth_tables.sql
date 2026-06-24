-- Auth tables for JWT + refresh token rotation
-- SynbotHealth — Royan Hospital

ROLLBACK; -- clear any prior aborted transaction
BEGIN;

create table if not exists royan_users (
    id uuid primary key default gen_random_uuid(),
    email text unique not null,
    hashed_password text not null,
    roles text[] not null default array[]::text[],
    is_active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists royan_refresh_tokens (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references royan_users(id) on delete cascade,
    token_hash text not null unique,
    expires_at timestamptz not null,
    revoked_at timestamptz,
    replaced_by uuid references royan_refresh_tokens(id),
    user_agent text,
    ip_address text,
    created_at timestamptz not null default now()
);

create index if not exists idx_royan_refresh_tokens_user_id on royan_refresh_tokens(user_id);
create index if not exists idx_royan_refresh_tokens_expires_at on royan_refresh_tokens(expires_at);

COMMIT;
