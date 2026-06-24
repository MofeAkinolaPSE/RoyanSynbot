-- Migration 111: Hospital operational support tables
-- Staff registry, timesheets, and procurement shipments for Royan Hospital

ROLLBACK; -- clear any prior aborted transaction
BEGIN;

-- ── Staff Registry ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.royan_staff (
    id              uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    staff_number    text        NOT NULL UNIQUE,
    full_name       text        NOT NULL,
    department      text        NOT NULL,
    designation     text        NOT NULL,
    employment_type text        NOT NULL DEFAULT 'full_time'
                    CHECK (employment_type IN ('full_time', 'part_time', 'contract', 'locum')),
    phone           text,
    email           text        UNIQUE,
    is_active       boolean     NOT NULL DEFAULT true,
    joined_at       date        NOT NULL DEFAULT CURRENT_DATE,
    monthly_gross   numeric     NOT NULL DEFAULT 0,
    metadata        jsonb       NOT NULL DEFAULT '{}'::jsonb,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_royan_staff_dept
    ON public.royan_staff (department);
CREATE INDEX IF NOT EXISTS idx_royan_staff_active
    ON public.royan_staff (is_active);

DROP TRIGGER IF EXISTS trg_royan_staff_updated_at ON public.royan_staff;
CREATE TRIGGER trg_royan_staff_updated_at
    BEFORE UPDATE ON public.royan_staff
    FOR EACH ROW EXECUTE FUNCTION public.royan_touch_updated_at();

-- ── Timesheets ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.royan_timesheets (
    id              uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    staff_id        uuid        NOT NULL REFERENCES public.royan_staff(id) ON DELETE CASCADE,
    date            date        NOT NULL,
    shift           text        NOT NULL DEFAULT 'day'
                    CHECK (shift IN ('day', 'night', 'on_call')),
    clock_in        time,
    clock_out       time,
    hours_worked    numeric(5,2),
    overtime_hours  numeric(5,2) NOT NULL DEFAULT 0,
    absent          boolean     NOT NULL DEFAULT false,
    absence_reason  text,
    approved        boolean     NOT NULL DEFAULT false,
    notes           text,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (staff_id, date, shift)
);

CREATE INDEX IF NOT EXISTS idx_royan_timesheets_staff_date
    ON public.royan_timesheets (staff_id, date DESC);
CREATE INDEX IF NOT EXISTS idx_royan_timesheets_date
    ON public.royan_timesheets (date DESC);

-- ── Procurement Shipments ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.royan_procurement_shipments (
    id                  uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    po_number           text        NOT NULL UNIQUE,
    supplier_name       text        NOT NULL,
    supplier_id         text,
    item_description    text        NOT NULL,
    quantity            numeric     NOT NULL DEFAULT 0,
    unit               text        NOT NULL DEFAULT 'units',
    unit_cost           numeric     NOT NULL DEFAULT 0,
    total_value         numeric     GENERATED ALWAYS AS (quantity * unit_cost) STORED,
    currency            text        NOT NULL DEFAULT 'NGN',
    expected_arrival    date,
    actual_arrival      date,
    status              text        NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending', 'in_transit', 'received', 'cancelled', 'partial')),
    avg_delay_days      numeric(8,2),
    rejection_rate      numeric(5,2),
    compliance_score    numeric(5,2),
    total_shipments     integer,
    on_time_rate        numeric(5,2),
    evaluation_period   text,
    notes               text,
    evaluated_by        text,
    metadata            jsonb       NOT NULL DEFAULT '{}'::jsonb,
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_royan_procure_shipments_status
    ON public.royan_procurement_shipments (status);
CREATE INDEX IF NOT EXISTS idx_royan_procure_shipments_supplier
    ON public.royan_procurement_shipments (supplier_id);

COMMIT;
