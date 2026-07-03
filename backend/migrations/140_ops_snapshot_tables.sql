-- Migration 140: Ops import snapshot tables (src/services/intelligence.py reads
-- these for the finance/ops dashboard; src/db.py insert_snapshot() + app.py's
-- ops-import job write them). Neither was ever created by an earlier migration.
-- Safe to re-run (IF NOT EXISTS everywhere).

CREATE TABLE IF NOT EXISTS ops_orders_snapshot (
    id            BIGSERIAL   PRIMARY KEY,
    batch_id      TEXT        NOT NULL,
    imported_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    order_id      TEXT,
    created_at    TIMESTAMPTZ,
    fulfilled_at  TIMESTAMPTZ,
    sku           TEXT,
    quantity      NUMERIC
);
CREATE INDEX IF NOT EXISTS idx_ops_orders_snapshot_batch_id    ON ops_orders_snapshot (batch_id);
CREATE INDEX IF NOT EXISTS idx_ops_orders_snapshot_imported_at ON ops_orders_snapshot (imported_at DESC);

CREATE TABLE IF NOT EXISTS ops_downtime_snapshot (
    id            BIGSERIAL   PRIMARY KEY,
    batch_id      TEXT        NOT NULL,
    imported_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    machine_id    TEXT,
    started_at    TIMESTAMPTZ,
    ended_at      TIMESTAMPTZ,
    minutes       NUMERIC
);
CREATE INDEX IF NOT EXISTS idx_ops_downtime_snapshot_batch_id    ON ops_downtime_snapshot (batch_id);
CREATE INDEX IF NOT EXISTS idx_ops_downtime_snapshot_imported_at ON ops_downtime_snapshot (imported_at DESC);
