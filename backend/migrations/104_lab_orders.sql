-- 104_lab_orders.sql
-- Royan Hospital: Laboratory orders and results
-- Part of Phase 3 – Hospital Database Schema

ROLLBACK; -- clear any prior aborted transaction
BEGIN;

-- Lab Orders
CREATE TABLE IF NOT EXISTS public.royan_lab_orders (
    id              bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    encounter_id    bigint      NOT NULL REFERENCES public.royan_encounters (id) ON DELETE RESTRICT,
    patient_id      bigint      NOT NULL REFERENCES public.royan_patients (id) ON DELETE RESTRICT,
    test_name       text        NOT NULL,                   -- e.g. "FBC", "Malaria RDT", "LFT", "HIV Screening"
    test_code       text,                                   -- internal or LOINC code
    urgency         text        NOT NULL DEFAULT 'routine'
                                CHECK (urgency IN ('routine', 'urgent', 'stat')),
    status          text        NOT NULL DEFAULT 'ordered'
                                CHECK (status IN (
                                    'ordered', 'sample_collected', 'processing', 'resulted', 'cancelled'
                                )),
    ordered_by      text        NOT NULL,                   -- doctor username/id
    ordered_at      timestamptz NOT NULL DEFAULT now(),
    sample_type     text,                                   -- e.g. "blood", "urine", "stool", "sputum"
    sample_collected_at timestamptz,
    notes           text,
    updated_at      timestamptz NOT NULL DEFAULT now()
);

-- Lab Results (one result per order; multi-analyte results use result_data JSONB)
CREATE TABLE IF NOT EXISTS public.royan_lab_results (
    id              bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    lab_order_id    bigint      NOT NULL REFERENCES public.royan_lab_orders (id) ON DELETE CASCADE,
    patient_id      bigint      NOT NULL REFERENCES public.royan_patients (id) ON DELETE RESTRICT,
    result_data     jsonb,                                  -- flexible: {"haemoglobin": "12.4 g/dL", ...}
    result_summary  text,                                   -- human-readable summary line
    reference_range text,
    interpretation  text        CHECK (interpretation IN ('normal', 'abnormal', 'critical', 'inconclusive')),
    resulted_by     text,                                   -- lab scientist username/id
    resulted_at     timestamptz NOT NULL DEFAULT now(),
    verified_by     text,                                   -- senior scientist who verified result
    verified_at     timestamptz,
    is_critical     boolean     NOT NULL DEFAULT false,     -- triggers immediate notification when true
    notes           text
);

-- Turnaround view: minutes from order to result
CREATE OR REPLACE VIEW public.royan_lab_turnaround AS
SELECT
    lo.id               AS order_id,
    lo.test_name,
    lo.urgency,
    lo.ordered_at,
    lr.resulted_at,
    EXTRACT(EPOCH FROM (lr.resulted_at - lo.ordered_at)) / 60 AS turnaround_minutes
FROM public.royan_lab_orders lo
JOIN public.royan_lab_results lr ON lr.lab_order_id = lo.id
WHERE lr.resulted_at IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_royan_lab_orders_encounter  ON public.royan_lab_orders (encounter_id);
CREATE INDEX IF NOT EXISTS idx_royan_lab_orders_patient    ON public.royan_lab_orders (patient_id);
CREATE INDEX IF NOT EXISTS idx_royan_lab_orders_status     ON public.royan_lab_orders (status);
CREATE INDEX IF NOT EXISTS idx_royan_lab_results_order     ON public.royan_lab_results (lab_order_id);
CREATE INDEX IF NOT EXISTS idx_royan_lab_results_critical  ON public.royan_lab_results (is_critical) WHERE is_critical = true;

COMMIT;
