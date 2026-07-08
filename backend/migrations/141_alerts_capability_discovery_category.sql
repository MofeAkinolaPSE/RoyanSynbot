-- Migration 141: royan_alerts.category was missing "capability_discovery",
-- needed so run_discovery_cycle() (backend/src/services/capability_engine.py)
-- can notify a human via create_alert() when a new capability proposal is
-- generated (including from the new log_error signal type). Safe to re-run.

ALTER TABLE public.royan_alerts DROP CONSTRAINT IF EXISTS royan_alerts_category_check;
ALTER TABLE public.royan_alerts
    ADD CONSTRAINT royan_alerts_category_check
    CHECK (category IN ('clinical', 'finance', 'pharmacy', 'lab', 'hr', 'system', 'inventory', 'workforce', 'capability_discovery'));
