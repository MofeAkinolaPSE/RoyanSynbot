-- Migration 135: Analytics Gold Layer — Complete Fact Tables
-- Implements Blueprint Chapter 12 — star schema fact tables for billing,
-- lab investigations, prescriptions, and admissions.
-- Also creates royan_kpi_snapshots for daily computed KPIs.
-- dim_* and fact_queue_visits already exist from migration 120.
-- Safe to re-run: all CREATE TABLE use IF NOT EXISTS.

ROLLBACK;
BEGIN;

-- ─────────────────────────────────────────────────────────────────────────────
-- 1. fact_billings — one row per billing episode
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.fact_billings (
    sk                  BIGSERIAL       PRIMARY KEY,
    -- Dimension keys
    patient_id          INTEGER         REFERENCES public.royan_patients (id) ON DELETE SET NULL,
    encounter_id        INTEGER,
    department_id       INTEGER         REFERENCES public.royan_departments (id) ON DELETE SET NULL,
    -- Time
    bill_date           DATE            NOT NULL,
    -- Measures
    total_billed        NUMERIC(14, 2)  NOT NULL DEFAULT 0,
    total_paid          NUMERIC(14, 2)  NOT NULL DEFAULT 0,
    hmo_covered_amount  NUMERIC(14, 2)  NOT NULL DEFAULT 0,
    -- Attributes
    payment_method      TEXT,
    hmo_covered         BOOLEAN         NOT NULL DEFAULT FALSE,
    bill_status         TEXT,
    source_bill_id      INTEGER,                -- FK to royan_billing (soft; no FK constraint for perf)
    -- ETL metadata
    loaded_at           TIMESTAMPTZ     NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_fact_bill_date       ON public.fact_billings (bill_date DESC);
CREATE INDEX IF NOT EXISTS idx_fact_bill_patient    ON public.fact_billings (patient_id, bill_date DESC);
CREATE INDEX IF NOT EXISTS idx_fact_bill_source     ON public.fact_billings (source_bill_id);


-- ─────────────────────────────────────────────────────────────────────────────
-- 2. fact_lab_investigations — one row per lab test ordered
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.fact_lab_investigations (
    sk                  BIGSERIAL       PRIMARY KEY,
    -- Dimension keys
    patient_id          INTEGER,
    encounter_id        INTEGER,
    department_id       INTEGER,
    -- Time
    ordered_date        DATE            NOT NULL,
    resulted_date       DATE,
    -- Measures
    tat_hours           NUMERIC(8, 2),          -- computed by ETL from order/result timestamps
    -- Attributes
    test_code           TEXT,
    urgency             TEXT,
    is_abnormal         BOOLEAN         NOT NULL DEFAULT FALSE,
    is_critical         BOOLEAN         NOT NULL DEFAULT FALSE,
    result_status       TEXT,
    source_order_id     INTEGER,
    -- ETL metadata
    loaded_at           TIMESTAMPTZ     NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_fact_lab_date        ON public.fact_lab_investigations (ordered_date DESC);
CREATE INDEX IF NOT EXISTS idx_fact_lab_test_code   ON public.fact_lab_investigations (test_code, ordered_date DESC);
CREATE INDEX IF NOT EXISTS idx_fact_lab_patient     ON public.fact_lab_investigations (patient_id, ordered_date DESC);
CREATE INDEX IF NOT EXISTS idx_fact_lab_critical    ON public.fact_lab_investigations (is_critical) WHERE is_critical = TRUE;


-- ─────────────────────────────────────────────────────────────────────────────
-- 3. fact_prescriptions — one row per prescription episode
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.fact_prescriptions (
    sk                  BIGSERIAL       PRIMARY KEY,
    -- Dimension keys
    patient_id          INTEGER,
    encounter_id        INTEGER,
    department_id       INTEGER,
    -- Time
    prescribed_date     DATE            NOT NULL,
    dispensed_date      DATE,
    administered_date   DATE,
    -- Attributes
    drug_name           TEXT,
    drug_code           TEXT,
    drug_class          TEXT,
    route               TEXT,
    was_dispensed       BOOLEAN         NOT NULL DEFAULT FALSE,
    was_administered    BOOLEAN         NOT NULL DEFAULT FALSE,
    rx_status           TEXT,
    source_rx_id        INTEGER,
    -- ETL metadata
    loaded_at           TIMESTAMPTZ     NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_fact_rx_date         ON public.fact_prescriptions (prescribed_date DESC);
CREATE INDEX IF NOT EXISTS idx_fact_rx_drug_code    ON public.fact_prescriptions (drug_code, prescribed_date DESC);
CREATE INDEX IF NOT EXISTS idx_fact_rx_patient      ON public.fact_prescriptions (patient_id, prescribed_date DESC);


-- ─────────────────────────────────────────────────────────────────────────────
-- 4. fact_admissions — one row per inpatient admission episode
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.fact_admissions (
    sk                  BIGSERIAL       PRIMARY KEY,
    -- Dimension keys
    patient_id          INTEGER,
    encounter_id        INTEGER,
    ward_id             INTEGER,
    bed_id              INTEGER,
    department_id       INTEGER,
    -- Time
    admitted_date       DATE            NOT NULL,
    discharged_date     DATE,
    -- Measures
    los_days            INTEGER         GENERATED ALWAYS AS (
                            COALESCE(discharged_date - admitted_date, 0)
                        ) STORED,
    -- Attributes
    discharge_condition TEXT,
    admission_type      TEXT,           -- emergency / elective / maternity
    source_encounter_id INTEGER,
    -- ETL metadata
    loaded_at           TIMESTAMPTZ     NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_fact_adm_date        ON public.fact_admissions (admitted_date DESC);
CREATE INDEX IF NOT EXISTS idx_fact_adm_patient     ON public.fact_admissions (patient_id, admitted_date DESC);
CREATE INDEX IF NOT EXISTS idx_fact_adm_ward        ON public.fact_admissions (ward_id, admitted_date DESC);


-- ─────────────────────────────────────────────────────────────────────────────
-- 5. royan_kpi_snapshots — daily computed KPI store
--    Replaces ad-hoc SQL in observability.py for trend queries.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.royan_kpi_snapshots (
    id              BIGSERIAL       PRIMARY KEY,
    snapshot_date   DATE            NOT NULL,
    kpi_key         TEXT            NOT NULL,   -- e.g. 'avg_wait_min', 'bed_occupancy_pct'
    kpi_value       NUMERIC(14, 4),
    kpi_unit        TEXT,                       -- e.g. 'minutes', 'percent', 'count'
    department_id   INTEGER         REFERENCES public.royan_departments (id) ON DELETE SET NULL,
    department_code TEXT,                       -- denorm for fast filtering
    metadata        JSONB           NOT NULL DEFAULT '{}',
    computed_at     TIMESTAMPTZ     NOT NULL DEFAULT now()
);

-- Unique: one value per KPI per department per day
-- NULL department_id = hospital-wide KPI
CREATE UNIQUE INDEX IF NOT EXISTS idx_kpi_snap_unique
    ON public.royan_kpi_snapshots (snapshot_date, kpi_key, COALESCE(department_id, 0));

CREATE INDEX IF NOT EXISTS idx_kpi_snap_date        ON public.royan_kpi_snapshots (snapshot_date DESC);
CREATE INDEX IF NOT EXISTS idx_kpi_snap_key         ON public.royan_kpi_snapshots (kpi_key, snapshot_date DESC);


-- ─────────────────────────────────────────────────────────────────────────────
-- 6. ETL run log — tracks each gold ETL execution for idempotency
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.royan_gold_etl_runs (
    id              BIGSERIAL       PRIMARY KEY,
    run_date        DATE            NOT NULL,
    target_table    TEXT            NOT NULL,
    rows_inserted   INTEGER         NOT NULL DEFAULT 0,
    rows_skipped    INTEGER         NOT NULL DEFAULT 0,
    duration_ms     INTEGER,
    status          TEXT            NOT NULL DEFAULT 'success'
                                    CHECK (status IN ('success', 'partial', 'failed')),
    error_message   TEXT,
    ran_at          TIMESTAMPTZ     NOT NULL DEFAULT now(),
    UNIQUE (run_date, target_table)
);

COMMIT;
