-- 116_bronze_watermarks_dlq.sql
-- Bronze layer: incremental sync watermarks and dead letter queue

BEGIN;

-- ---------------------------------------------------------------------------
-- Watermark table: tracks the latest external_updated_at seen per entity.
-- Used by pipeline.py incremental mode to skip rows already ingested.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.royan_ingest_watermarks (
    id                          bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    entity                      text        NOT NULL UNIQUE,
    last_run_id                 text        NOT NULL,
    max_external_updated_at     timestamptz,            -- NULL on first full run
    rows_processed              int         NOT NULL DEFAULT 0,
    full_run_at                 timestamptz,            -- last full run timestamp
    incremental_run_at          timestamptz,            -- last incremental run timestamp
    updated_at                  timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE public.royan_ingest_watermarks IS
    'Tracks per-entity high-water marks for incremental data ingestion from DRM Hope.';

-- ---------------------------------------------------------------------------
-- Dead Letter Queue: rows that failed Pydantic contract validation or the
-- PostgreSQL upsert. NEVER silently dropped — always recorded here for review.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.royan_ingest_dlq (
    id              bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id          text        NOT NULL,
    entity          text        NOT NULL,
    external_id     text,
    source_table    text,
    raw_row         jsonb       NOT NULL,
    failure_stage   text        NOT NULL
                    CHECK (failure_stage IN ('extract', 'contract', 'transform', 'load')),
    failure_reason  text        NOT NULL,
    error_detail    jsonb,
    retry_count     int         NOT NULL DEFAULT 0,
    resolved        boolean     NOT NULL DEFAULT false,
    resolved_at     timestamptz,
    resolved_by     text,
    created_at      timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE public.royan_ingest_dlq IS
    'Dead letter queue for rows rejected during Hope data ingestion. '
    'failure_stage indicates where the row was rejected: '
    'extract=parse error, contract=Pydantic validation, transform=transformer error, load=DB upsert error.';

CREATE INDEX IF NOT EXISTS idx_royan_ingest_dlq_entity
    ON public.royan_ingest_dlq (entity, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_royan_ingest_dlq_run_id
    ON public.royan_ingest_dlq (run_id);

CREATE INDEX IF NOT EXISTS idx_royan_ingest_dlq_unresolved
    ON public.royan_ingest_dlq (entity, resolved)
    WHERE resolved = false;

COMMIT;
