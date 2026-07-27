-- Migration 150: Create the missing royan_agent_memory table
--
-- backend/src/services/agent_memory.py's AgentMemory class (store/recall/
-- score_and_prune/_evict_if_over_limit) has referenced this table since it
-- was written, but no migration ever created it — every insert/select/
-- update/delete has been silently failing (each call site catches its own
-- exception and no-ops), so the "agents get smarter over time" memory layer
-- has never actually persisted anything.

ROLLBACK;
BEGIN;

CREATE TABLE IF NOT EXISTS public.royan_agent_memory (
    id            bigint           GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    agent_name    text             NOT NULL,
    memory_type   text             NOT NULL DEFAULT 'finding',
    content       text             NOT NULL,
    quality_score double precision NOT NULL DEFAULT 0,
    used_count    int              NOT NULL DEFAULT 0,
    embedding     double precision[],
    created_at    timestamptz      NOT NULL DEFAULT now(),
    last_used_at  timestamptz
);

CREATE INDEX IF NOT EXISTS idx_royan_agent_memory_agent_created
    ON public.royan_agent_memory (agent_name, created_at DESC);

COMMIT;
