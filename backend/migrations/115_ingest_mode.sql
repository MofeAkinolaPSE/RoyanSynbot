-- Migration 115: Add ingest_mode to sync run log
-- Distinguishes bulk import runs (DAL) from live bridge runs (hope-bridge).

ALTER TABLE royan_hope_sync_runs
    ADD COLUMN IF NOT EXISTS ingest_mode text
        CHECK (ingest_mode IN ('bulk_import', 'live_bridge'))
        DEFAULT 'live_bridge';

COMMENT ON COLUMN royan_hope_sync_runs.ingest_mode IS
    'bulk_import = data-assimilation DAL script; live_bridge = hope-bridge ODBC polling';
