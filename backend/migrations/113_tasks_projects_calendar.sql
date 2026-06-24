-- Migration 113: Tasks, Projects, and Calendar Events
-- Creates three tables used by the Staff Dashboard, Calendar & Task Manager,
-- and Workflow Engine.  All tables follow the existing snake_case convention
-- and use UUID primary keys consistent with the rest of the schema.

ROLLBACK; -- clear any prior aborted transaction
BEGIN;

-- ============================================================
-- 1. royan_tasks
--    General-purpose task / to-do store.  Tasks can be created
--    by users, workflow triggers, chat agents, or CRM flows.
--    assigned_to is TEXT to support both user UUIDs and role
--    slugs (e.g. 'role:ops', 'role:finance').
-- ============================================================
CREATE TABLE IF NOT EXISTS public.royan_tasks (
    id              uuid        PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Core fields
    title           text        NOT NULL,
    description     text,
    status          text        NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'in_progress', 'completed', 'done', 'cancelled')),
    priority        text        NOT NULL DEFAULT 'medium'
                    CHECK (priority IN ('low', 'medium', 'high', 'urgent')),

    -- Scheduling
    due_date        timestamptz,
    reminder_at     timestamptz,
    completed_at    timestamptz,

    -- Assignment (user UUID or role slug like 'role:ops')
    assigned_to     text,

    -- Provenance
    source          text        NOT NULL DEFAULT 'manual',   -- 'manual' | 'workflow' | 'chat' | 'crm' | ...
    source_ref      text,                                    -- external reference ID (e.g. chat_id, crm_deal_id)

    -- Flexible payload
    tags            jsonb       NOT NULL DEFAULT '[]'::jsonb,
    metadata        jsonb       NOT NULL DEFAULT '{}'::jsonb,

    -- Timestamps
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

-- Indexes for the query patterns used in staff_dashboard and calendar_tasks
CREATE INDEX IF NOT EXISTS idx_royan_tasks_assigned_to
    ON public.royan_tasks (assigned_to);
CREATE INDEX IF NOT EXISTS idx_royan_tasks_status
    ON public.royan_tasks (status);
CREATE INDEX IF NOT EXISTS idx_royan_tasks_priority
    ON public.royan_tasks (priority);
CREATE INDEX IF NOT EXISTS idx_royan_tasks_due_date
    ON public.royan_tasks (due_date);
CREATE INDEX IF NOT EXISTS idx_royan_tasks_created_at
    ON public.royan_tasks (created_at DESC);

-- Auto-update updated_at on every write
CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgname = 'trg_royan_tasks_updated_at'
    ) THEN
        CREATE TRIGGER trg_royan_tasks_updated_at
            BEFORE UPDATE ON public.royan_tasks
            FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
    END IF;
END $$;


-- ============================================================
-- 2. royan_projects
--    Pharma / hospital project tracker.  Supports workflow
--    stages, supplier tracking, QC, and NAFDAC sampling.
--    assigned_staff_id is stored as TEXT so it can hold a raw
--    UUID string without requiring an FK constraint at this
--    stage (matches the SELECT pattern in staff_dashboard.py).
-- ============================================================
CREATE TABLE IF NOT EXISTS public.royan_projects (
    id                      uuid    PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Identity
    name                    text    NOT NULL,
    description             text,

    -- Lifecycle
    status                  text    NOT NULL DEFAULT 'active'
                            CHECK (status IN ('active', 'on_hold', 'completed', 'cancelled', 'planning')),
    workflow_stage          text,   -- e.g. 'procurement', 'clearance', 'qc', 'distribution'
    activity_type           text,   -- e.g. 'import', 'local_purchase', 'manufacturing'

    -- Supplier / regulatory
    supplier_name           text,
    quality_check_status    text,   -- e.g. 'pending', 'passed', 'failed'
    nafdac_sampling_status  text,   -- e.g. 'awaiting', 'sampled', 'approved', 'rejected'

    -- Staff assignment (UUID stored as text; avoids FK dependency on auth table)
    assigned_staff_id       text,

    -- Flexible payload
    metadata                jsonb   NOT NULL DEFAULT '{}'::jsonb,

    -- Timestamps
    created_at              timestamptz NOT NULL DEFAULT now(),
    updated_at              timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_royan_projects_assigned_staff_id
    ON public.royan_projects (assigned_staff_id);
CREATE INDEX IF NOT EXISTS idx_royan_projects_status
    ON public.royan_projects (status);
CREATE INDEX IF NOT EXISTS idx_royan_projects_updated_at
    ON public.royan_projects (updated_at DESC);

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgname = 'trg_royan_projects_updated_at'
    ) THEN
        CREATE TRIGGER trg_royan_projects_updated_at
            BEFORE UPDATE ON public.royan_projects
            FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
    END IF;
END $$;


-- ============================================================
-- 3. royan_calendar_events
--    Shared calendar used by CalendarAgent, EOS service, and
--    the Calendar & Task Manager router.
-- ============================================================
CREATE TABLE IF NOT EXISTS public.royan_calendar_events (
    id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Core fields
    title       text        NOT NULL,
    description text,
    event_type  text        NOT NULL DEFAULT 'meeting',  -- 'meeting' | 'inbound_inventory' | 'qc_inspection' | ...

    -- Scheduling
    start_time  timestamptz NOT NULL,
    end_time    timestamptz,
    all_day     boolean     NOT NULL DEFAULT false,

    -- Location & participants
    location    text,
    attendees   jsonb       NOT NULL DEFAULT '[]'::jsonb,

    -- Flexible payload (batch_expiry, created_via, actor_id, etc.)
    metadata    jsonb       NOT NULL DEFAULT '{}'::jsonb,

    -- Timestamps
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_royan_calendar_events_start_time
    ON public.royan_calendar_events (start_time);
CREATE INDEX IF NOT EXISTS idx_royan_calendar_events_event_type
    ON public.royan_calendar_events (event_type);
CREATE INDEX IF NOT EXISTS idx_royan_calendar_events_created_at
    ON public.royan_calendar_events (created_at DESC);

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgname = 'trg_royan_calendar_events_updated_at'
    ) THEN
        CREATE TRIGGER trg_royan_calendar_events_updated_at
            BEFORE UPDATE ON public.royan_calendar_events
            FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
    END IF;
END $$;


COMMIT;
