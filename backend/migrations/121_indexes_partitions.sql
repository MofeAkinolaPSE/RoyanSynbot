-- 121_indexes_partitions.sql
-- Compound indexes for Silver tables and audit log partitioning preparation.

BEGIN;

-- ─────────────────────────────────────────────────────────────────────────────
-- COMPOUND INDEXES ON SILVER TABLES
-- Pattern: (patient_id, timestamp DESC) for patient timeline queries
--          (status, timestamp DESC) for workflow/queue queries
-- ─────────────────────────────────────────────────────────────────────────────

-- royan_encounters
CREATE INDEX IF NOT EXISTS idx_royan_enc_patient_created
    ON public.royan_encounters (patient_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_royan_enc_status_created
    ON public.royan_encounters (status, created_at DESC);

-- Partial index: only non-discharged encounters (hot path for queue dashboards)
CREATE INDEX IF NOT EXISTS idx_royan_enc_active
    ON public.royan_encounters (department, status)
    WHERE status NOT IN ('discharged');

-- royan_lab_orders
CREATE INDEX IF NOT EXISTS idx_royan_lab_patient_created
    ON public.royan_lab_orders (patient_id, ordered_at DESC);

CREATE INDEX IF NOT EXISTS idx_royan_lab_status_created
    ON public.royan_lab_orders (status, ordered_at DESC);

-- Partial index: open lab orders (ordered or in-flight)
CREATE INDEX IF NOT EXISTS idx_royan_lab_open
    ON public.royan_lab_orders (patient_id, status)
    WHERE status IN ('ordered', 'sample_collected', 'processing');

-- royan_prescriptions
CREATE INDEX IF NOT EXISTS idx_royan_prescriptions_patient_created
    ON public.royan_prescriptions (patient_id, prescribed_at DESC);

CREATE INDEX IF NOT EXISTS idx_royan_prescriptions_status_created
    ON public.royan_prescriptions (status, prescribed_at DESC);

-- Partial index: pending dispensing queue
CREATE INDEX IF NOT EXISTS idx_royan_prescriptions_pending
    ON public.royan_prescriptions (patient_id, prescribed_at DESC)
    WHERE status = 'pending';

-- royan_billing
CREATE INDEX IF NOT EXISTS idx_royan_billing_patient_created
    ON public.royan_billing (patient_id, billed_at DESC);

CREATE INDEX IF NOT EXISTS idx_royan_billing_status_created
    ON public.royan_billing (status, billed_at DESC);

-- royan_appointments
CREATE INDEX IF NOT EXISTS idx_royan_appt_status_created
    ON public.royan_appointments (status, booked_at DESC);

CREATE INDEX IF NOT EXISTS idx_royan_appt_patient_created
    ON public.royan_appointments (patient_id, booked_at DESC);

-- royan_bill_items
CREATE INDEX IF NOT EXISTS idx_royan_bill_items_service
    ON public.royan_bill_items (service_id, created_at DESC)
    WHERE service_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_royan_bill_items_billing
    ON public.royan_bill_items (billing_id, created_at DESC);

-- royan_operations_events (Gold)
CREATE INDEX IF NOT EXISTS idx_royan_ops_run_id
    ON public.royan_operations_events (run_id)
    WHERE run_id IS NOT NULL;

-- ─────────────────────────────────────────────────────────────────────────────
-- AUDIT LOG RANGE PARTITIONING
--
-- PostgreSQL cannot partition an existing non-partitioned table in place.
-- This creates a partitioned clone (royan_audit_logs_p).
-- Apply the swap (rename) during a maintenance window using the steps below.
--
-- MAINTENANCE WINDOW SWAP STEPS (run manually when ready):
--   1. INSERT INTO public.royan_audit_logs_p SELECT * FROM public.royan_audit_logs;
--   2. ALTER TABLE public.royan_audit_logs RENAME TO royan_audit_logs_old;
--   3. ALTER TABLE public.royan_audit_logs_p RENAME TO royan_audit_logs;
--   4. DROP TABLE public.royan_audit_logs_old;  -- only after verification
-- ─────────────────────────────────────────────────────────────────────────────

-- LIKE INCLUDING ALL copies the id-only PK from the source table, which
-- PostgreSQL rejects on partitioned tables (partition key must be in the PK).
-- Use DEFAULTS only, then add the composite PK manually.
CREATE TABLE IF NOT EXISTS public.royan_audit_logs_p (
    LIKE public.royan_audit_logs INCLUDING DEFAULTS
) PARTITION BY RANGE (created_at);

ALTER TABLE public.royan_audit_logs_p
    ADD CONSTRAINT royan_audit_logs_p_pkey PRIMARY KEY (id, created_at);

CREATE TABLE IF NOT EXISTS public.royan_audit_logs_p_2024
    PARTITION OF public.royan_audit_logs_p
    FOR VALUES FROM ('2024-01-01') TO ('2025-01-01');

CREATE TABLE IF NOT EXISTS public.royan_audit_logs_p_2025
    PARTITION OF public.royan_audit_logs_p
    FOR VALUES FROM ('2025-01-01') TO ('2026-01-01');

CREATE TABLE IF NOT EXISTS public.royan_audit_logs_p_2026
    PARTITION OF public.royan_audit_logs_p
    FOR VALUES FROM ('2026-01-01') TO ('2027-01-01');

CREATE TABLE IF NOT EXISTS public.royan_audit_logs_p_default
    PARTITION OF public.royan_audit_logs_p DEFAULT;

COMMIT;
