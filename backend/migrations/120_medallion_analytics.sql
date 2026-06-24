-- 120_medallion_analytics.sql
-- Gold Layer: Polymorphic operations events, Star Schema (dim/fact tables),
-- and materialized views for the RoyanHealth analytics layer.

BEGIN;

-- ─────────────────────────────────────────────────────────────────────────────
-- POLYMORPHIC OPERATIONS EVENTS
-- Merges fumigation_records, maintenance_records, deviations, audit_records,
-- and recall_events from DRM Hope into one extensible table.
-- source_table preserves full data lineage back to the original Hope table.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.royan_operations_events (
    id              bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_type      text        NOT NULL
                    CHECK (event_type IN ('audit', 'deviation', 'maintenance', 'fumigation', 'recall', 'radiology', 'theatre')),
    event_date      date        NOT NULL,
    title           text        NOT NULL,
    status          text        NOT NULL DEFAULT 'open'
                    CHECK (status IN ('open', 'in_progress', 'resolved', 'closed', 'cancelled', 'scheduled', 'completed')),
    severity        text
                    CHECK (severity IN ('low', 'medium', 'high', 'critical')),
    performed_by    text,
    department      text,
    metadata        jsonb       NOT NULL DEFAULT '{}'::jsonb,
    source_table    text,
    -- Bronze lineage
    run_id          text,
    external_source text,
    external_id     text,
    external_updated_at timestamptz,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE public.royan_operations_events IS
    'Unified operational events table (Gold layer). '
    'Merges fumigation, maintenance, deviation, audit, recall, radiology and theatre from DRM Hope. '
    'Use source_table + external_id for lineage back to the original Hope table.';

CREATE UNIQUE INDEX IF NOT EXISTS uq_royan_ops_events_external
    ON public.royan_operations_events (external_source, external_id)
    WHERE external_source IS NOT NULL AND external_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_royan_ops_events_type_date
    ON public.royan_operations_events (event_type, event_date DESC);

CREATE INDEX IF NOT EXISTS idx_royan_ops_events_dept_date
    ON public.royan_operations_events (department, event_date DESC)
    WHERE department IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_royan_ops_events_status
    ON public.royan_operations_events (status, event_date DESC);

-- ─────────────────────────────────────────────────────────────────────────────
-- DIMENSION TABLES (Gold Layer)
-- ─────────────────────────────────────────────────────────────────────────────

-- dim_patient: denormalised, analytics-optimised patient snapshot
-- SCD Type 2 ready (valid_from / valid_to pattern)
CREATE TABLE IF NOT EXISTS public.dim_patient (
    patient_sk      bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    patient_id      bigint      NOT NULL REFERENCES public.royan_patients(id) ON DELETE CASCADE,
    mrn             text        NOT NULL,
    full_name       text        NOT NULL,
    gender          text,
    age_band        text,       -- derived: '0-5','6-17','18-40','41-60','60+'
    hmo_provider    text,
    is_active       boolean     NOT NULL DEFAULT true,
    valid_from      timestamptz NOT NULL DEFAULT now(),
    valid_to        timestamptz,                        -- NULL = current record
    UNIQUE (patient_id)
);

COMMENT ON COLUMN public.dim_patient.age_band IS
    'Computed age band at time of last dim refresh. Ranges: 0-5, 6-17, 18-40, 41-60, 60+.';

CREATE INDEX IF NOT EXISTS idx_dim_patient_mrn ON public.dim_patient (mrn);
CREATE INDEX IF NOT EXISTS idx_dim_patient_hmo ON public.dim_patient (hmo_provider)
    WHERE hmo_provider IS NOT NULL;

-- dim_service: service catalog snapshot for analytics joins
CREATE TABLE IF NOT EXISTS public.dim_service (
    service_sk      bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    service_id      bigint      REFERENCES public.royan_service_catalog(id) ON DELETE SET NULL,
    service_code    text        NOT NULL,
    service_name    text        NOT NULL,
    category        text        NOT NULL,
    base_price      numeric(14,2) NOT NULL DEFAULT 0,
    UNIQUE (service_code)
);

-- dim_staff: staff snapshot for analytics
CREATE TABLE IF NOT EXISTS public.dim_staff (
    staff_sk        bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    staff_id        uuid        REFERENCES public.royan_staff(id) ON DELETE SET NULL,
    staff_number    text        NOT NULL,
    full_name       text        NOT NULL,
    department      text        NOT NULL,
    designation     text        NOT NULL,
    employment_type text        NOT NULL,
    UNIQUE (staff_number)
);

-- dim_time: date spine for time-intelligence queries (2020–2030)
CREATE TABLE IF NOT EXISTS public.dim_time (
    date_day            date        PRIMARY KEY,
    day_of_week         int         NOT NULL,   -- 0=Sunday ... 6=Saturday
    day_name            text        NOT NULL,
    week_of_year        int         NOT NULL,
    month_num           int         NOT NULL,
    month_name          text        NOT NULL,
    quarter             int         NOT NULL,
    year                int         NOT NULL,
    is_weekend          boolean     NOT NULL,
    is_nigerian_holiday boolean     NOT NULL DEFAULT false
);

COMMENT ON TABLE public.dim_time IS
    'Date spine pre-populated 2020-01-01 to 2030-12-31. '
    'Set is_nigerian_holiday=true for public holidays as required.';

-- Populate dim_time for 2020–2030
INSERT INTO public.dim_time (
    date_day, day_of_week, day_name, week_of_year,
    month_num, month_name, quarter, year,
    is_weekend, is_nigerian_holiday
)
SELECT
    d::date                                                   AS date_day,
    EXTRACT(DOW FROM d)::int                                  AS day_of_week,
    TRIM(TO_CHAR(d, 'Day'))                                   AS day_name,
    EXTRACT(WEEK FROM d)::int                                 AS week_of_year,
    EXTRACT(MONTH FROM d)::int                                AS month_num,
    TRIM(TO_CHAR(d, 'Month'))                                 AS month_name,
    EXTRACT(QUARTER FROM d)::int                              AS quarter,
    EXTRACT(YEAR FROM d)::int                                 AS year,
    EXTRACT(DOW FROM d) IN (0, 6)                             AS is_weekend,
    false                                                     AS is_nigerian_holiday
FROM generate_series('2020-01-01'::date, '2030-12-31'::date, '1 day'::interval) d
ON CONFLICT (date_day) DO NOTHING;

-- ─────────────────────────────────────────────────────────────────────────────
-- FACT TABLES (Gold Layer, PARTITION BY RANGE on date column)
-- ─────────────────────────────────────────────────────────────────────────────

-- fact_queue_visits: one row per encounter (queue visit event)
CREATE TABLE IF NOT EXISTS public.fact_queue_visits (
    id                      bigint          GENERATED ALWAYS AS IDENTITY,
    visit_date              date            NOT NULL,
    patient_sk              bigint          REFERENCES public.dim_patient(patient_sk) ON DELETE SET NULL,
    encounter_id            bigint          REFERENCES public.royan_encounters(id) ON DELETE SET NULL,
    encounter_type          text,
    department              text,
    status                  text,
    triage_level            text,
    wait_minutes            numeric(10,2),  -- triage_at - created_at
    consult_minutes         numeric(10,2),  -- consultation_at - triage_at
    total_visit_minutes     numeric(10,2),  -- discharge_at - created_at
    consulting_doctor       text,
    run_id                  text,
    created_at              timestamptz     NOT NULL DEFAULT now(),
    PRIMARY KEY (id, visit_date)
) PARTITION BY RANGE (visit_date);

CREATE TABLE IF NOT EXISTS public.fact_queue_visits_2024
    PARTITION OF public.fact_queue_visits
    FOR VALUES FROM ('2024-01-01') TO ('2025-01-01');

CREATE TABLE IF NOT EXISTS public.fact_queue_visits_2025
    PARTITION OF public.fact_queue_visits
    FOR VALUES FROM ('2025-01-01') TO ('2026-01-01');

CREATE TABLE IF NOT EXISTS public.fact_queue_visits_2026
    PARTITION OF public.fact_queue_visits
    FOR VALUES FROM ('2026-01-01') TO ('2027-01-01');

CREATE TABLE IF NOT EXISTS public.fact_queue_visits_default
    PARTITION OF public.fact_queue_visits DEFAULT;

CREATE INDEX IF NOT EXISTS idx_fqv_patient_date
    ON public.fact_queue_visits (patient_sk, visit_date DESC);

CREATE INDEX IF NOT EXISTS idx_fqv_dept_date
    ON public.fact_queue_visits (department, visit_date DESC);

CREATE INDEX IF NOT EXISTS idx_fqv_enc
    ON public.fact_queue_visits (encounter_id)
    WHERE encounter_id IS NOT NULL;

-- fact_billing_summary: one row per bill, with pre-bucketed charges
CREATE TABLE IF NOT EXISTS public.fact_billing_summary (
    id                  bigint          GENERATED ALWAYS AS IDENTITY,
    billing_date        date            NOT NULL,
    patient_sk          bigint          REFERENCES public.dim_patient(patient_sk) ON DELETE SET NULL,
    billing_id          bigint          REFERENCES public.royan_billing(id) ON DELETE SET NULL,
    encounter_id        bigint          REFERENCES public.royan_encounters(id) ON DELETE SET NULL,
    consultation_fee    numeric(14,2)   NOT NULL DEFAULT 0,
    lab_charges         numeric(14,2)   NOT NULL DEFAULT 0,
    pharmacy_charges    numeric(14,2)   NOT NULL DEFAULT 0,
    ward_charges        numeric(14,2)   NOT NULL DEFAULT 0,
    procedure_charges   numeric(14,2)   NOT NULL DEFAULT 0,
    miscellaneous       numeric(14,2)   NOT NULL DEFAULT 0,
    total_charged       numeric(14,2)   NOT NULL DEFAULT 0,
    hmo_covered         numeric(14,2)   NOT NULL DEFAULT 0,
    patient_balance     numeric(14,2)   NOT NULL DEFAULT 0,
    payment_method      text,
    status              text,
    run_id              text,
    created_at          timestamptz     NOT NULL DEFAULT now(),
    PRIMARY KEY (id, billing_date)
) PARTITION BY RANGE (billing_date);

CREATE TABLE IF NOT EXISTS public.fact_billing_summary_2024
    PARTITION OF public.fact_billing_summary
    FOR VALUES FROM ('2024-01-01') TO ('2025-01-01');

CREATE TABLE IF NOT EXISTS public.fact_billing_summary_2025
    PARTITION OF public.fact_billing_summary
    FOR VALUES FROM ('2025-01-01') TO ('2026-01-01');

CREATE TABLE IF NOT EXISTS public.fact_billing_summary_2026
    PARTITION OF public.fact_billing_summary
    FOR VALUES FROM ('2026-01-01') TO ('2027-01-01');

CREATE TABLE IF NOT EXISTS public.fact_billing_summary_default
    PARTITION OF public.fact_billing_summary DEFAULT;

CREATE INDEX IF NOT EXISTS idx_fbs_patient_date
    ON public.fact_billing_summary (patient_sk, billing_date DESC);

CREATE INDEX IF NOT EXISTS idx_fbs_status_date
    ON public.fact_billing_summary (status, billing_date DESC);

-- ─────────────────────────────────────────────────────────────────────────────
-- MATERIALIZED VIEWS (refreshed via gold_loader.refresh_materialized_views)
-- ─────────────────────────────────────────────────────────────────────────────

-- mv_daily_queue_stats: pre-aggregated daily encounter summary for dashboards
CREATE MATERIALIZED VIEW IF NOT EXISTS public.mv_daily_queue_stats AS
SELECT
    e.created_at::date                                      AS visit_date,
    COALESCE(e.department, 'Unknown')                       AS department,
    COUNT(*)                                                AS total_visits,
    COUNT(*) FILTER (WHERE e.status = 'discharged')         AS completed_visits,
    COUNT(*) FILTER (WHERE e.encounter_type = 'emergency')  AS emergency_visits,
    COUNT(*) FILTER (WHERE e.encounter_type = 'inpatient')  AS inpatient_visits,
    COUNT(*) FILTER (WHERE e.status NOT IN ('discharged'))  AS active_visits,
    ROUND(
        AVG(EXTRACT(EPOCH FROM (e.triage_at - e.created_at)) / 60.0)
        FILTER (WHERE e.triage_at IS NOT NULL AND e.triage_at > e.created_at),
    2)                                                      AS avg_wait_mins,
    ROUND(
        AVG(EXTRACT(EPOCH FROM (e.discharge_at - e.created_at)) / 60.0)
        FILTER (WHERE e.discharge_at IS NOT NULL AND e.discharge_at > e.created_at),
    2)                                                      AS avg_total_mins
FROM public.royan_encounters e
GROUP BY e.created_at::date, COALESCE(e.department, 'Unknown')
WITH DATA;

CREATE UNIQUE INDEX IF NOT EXISTS uidx_mv_daily_queue_stats
    ON public.mv_daily_queue_stats (visit_date, department);

COMMENT ON MATERIALIZED VIEW public.mv_daily_queue_stats IS
    'Daily queue KPIs per department. Refresh with: '
    'REFRESH MATERIALIZED VIEW CONCURRENTLY public.mv_daily_queue_stats';

-- mv_service_utilization: service usage frequency and revenue summary
CREATE MATERIALIZED VIEW IF NOT EXISTS public.mv_service_utilization AS
SELECT
    bi.category                         AS category,
    COALESCE(bi.service_code, 'unknown') AS service_code,
    bi.description                      AS service_description,
    COUNT(*)                            AS usage_count,
    SUM(bi.gross_amount)                AS total_revenue,
    ROUND(AVG(bi.gross_amount), 2)      AS avg_price,
    MIN(bi.created_at)::date            AS first_seen,
    MAX(bi.created_at)::date            AS last_seen
FROM public.royan_bill_items bi
GROUP BY bi.category, COALESCE(bi.service_code, 'unknown'), bi.description
WITH DATA;

CREATE INDEX IF NOT EXISTS idx_mv_service_util_category
    ON public.mv_service_utilization (category, usage_count DESC);

COMMENT ON MATERIALIZED VIEW public.mv_service_utilization IS
    'Service usage and revenue by category. Refresh with: '
    'REFRESH MATERIALIZED VIEW CONCURRENTLY public.mv_service_utilization';

COMMIT;
