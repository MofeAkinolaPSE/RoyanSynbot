-- Migration 138: Missing operational tables for SynbotHealth HMS
-- Safe to re-run (IF NOT EXISTS on all tables)

-- Quality & Incident Management
CREATE TABLE IF NOT EXISTS royan_incident_reports (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    category    TEXT NOT NULL,
    severity    TEXT NOT NULL DEFAULT 'low' CHECK (severity IN ('low','medium','high','critical')),
    status      TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','investigating','resolved','closed')),
    ward        TEXT,
    patient_id  BIGINT REFERENCES royan_patients(id) ON DELETE SET NULL,
    reported_by UUID REFERENCES royan_staff(id) ON DELETE SET NULL,
    description TEXT NOT NULL,
    investigation_notes TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_incident_reports_status    ON royan_incident_reports(status);
CREATE INDEX IF NOT EXISTS idx_incident_reports_severity  ON royan_incident_reports(severity);
CREATE INDEX IF NOT EXISTS idx_incident_reports_patient   ON royan_incident_reports(patient_id);

CREATE TABLE IF NOT EXISTS royan_infection_control (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_type            TEXT NOT NULL,
    healthcare_associated BOOLEAN NOT NULL DEFAULT FALSE,
    pathogen              TEXT,
    ward                  TEXT,
    patient_id            BIGINT REFERENCES royan_patients(id) ON DELETE SET NULL,
    reported_by           UUID REFERENCES royan_staff(id) ON DELETE SET NULL,
    notes                 TEXT,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_infection_control_event_type ON royan_infection_control(event_type);
CREATE INDEX IF NOT EXISTS idx_infection_control_ward       ON royan_infection_control(ward);

CREATE TABLE IF NOT EXISTS royan_hefamaa_checklist (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    overall_score NUMERIC(5,2) NOT NULL CHECK (overall_score >= 0 AND overall_score <= 100),
    domain_scores JSONB NOT NULL DEFAULT '{}',
    assessor      UUID REFERENCES royan_staff(id) ON DELETE SET NULL,
    assessment_date DATE NOT NULL DEFAULT CURRENT_DATE,
    notes         TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_hefamaa_assessment_date ON royan_hefamaa_checklist(assessment_date);

-- HR: Shifts, Leave, Payroll
CREATE TABLE IF NOT EXISTS royan_staff_shifts (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    staff_id    UUID NOT NULL REFERENCES royan_staff(id) ON DELETE CASCADE,
    department  TEXT,
    shift_type  TEXT NOT NULL CHECK (shift_type IN ('morning','afternoon','night','on_call')),
    shift_date  DATE NOT NULL,
    start_time  TIME NOT NULL,
    end_time    TIME NOT NULL,
    status      TEXT NOT NULL DEFAULT 'scheduled' CHECK (status IN ('scheduled','completed','missed','swapped')),
    notes       TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_staff_shifts_staff_id   ON royan_staff_shifts(staff_id);
CREATE INDEX IF NOT EXISTS idx_staff_shifts_shift_date ON royan_staff_shifts(shift_date);

CREATE TABLE IF NOT EXISTS royan_leave_requests (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    staff_id    UUID NOT NULL REFERENCES royan_staff(id) ON DELETE CASCADE,
    leave_type  TEXT NOT NULL CHECK (leave_type IN ('annual','sick','maternity','paternity','emergency','unpaid')),
    start_date  DATE NOT NULL,
    end_date    DATE NOT NULL,
    days_count  NUMERIC(5,1) NOT NULL DEFAULT 1,
    status      TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','approved','rejected','cancelled')),
    approved_by UUID REFERENCES royan_staff(id) ON DELETE SET NULL,
    reason      TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_leave_requests_staff_id   ON royan_leave_requests(staff_id);
CREATE INDEX IF NOT EXISTS idx_leave_requests_status     ON royan_leave_requests(status);
CREATE INDEX IF NOT EXISTS idx_leave_requests_start_date ON royan_leave_requests(start_date);

CREATE TABLE IF NOT EXISTS royan_payroll_records (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    staff_id       UUID NOT NULL REFERENCES royan_staff(id) ON DELETE CASCADE,
    period_month   SMALLINT NOT NULL CHECK (period_month BETWEEN 1 AND 12),
    period_year    SMALLINT NOT NULL CHECK (period_year >= 2000),
    gross_salary   NUMERIC(14,2) NOT NULL DEFAULT 0,
    overtime_hours NUMERIC(8,2) NOT NULL DEFAULT 0,
    overtime_rate  NUMERIC(10,2) NOT NULL DEFAULT 0,
    deductions     NUMERIC(14,2) NOT NULL DEFAULT 0,
    net_salary     NUMERIC(14,2) NOT NULL DEFAULT 0,
    status         TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','approved','paid')),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (staff_id, period_month, period_year)
);
CREATE INDEX IF NOT EXISTS idx_payroll_staff_id ON royan_payroll_records(staff_id);
CREATE INDEX IF NOT EXISTS idx_payroll_period   ON royan_payroll_records(period_year, period_month);

-- AI Workflow Intents
CREATE TABLE IF NOT EXISTS royan_intents (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    intent_type    TEXT NOT NULL,
    payload        JSONB NOT NULL DEFAULT '{}',
    recommendation TEXT,
    status         TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','approved','rejected','actioned')),
    actor_id       UUID REFERENCES royan_staff(id) ON DELETE SET NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_intents_intent_type ON royan_intents(intent_type);
CREATE INDEX IF NOT EXISTS idx_intents_status      ON royan_intents(status);

-- Inventory
CREATE TABLE IF NOT EXISTS inventory_items (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sku           TEXT NOT NULL UNIQUE,
    name          TEXT NOT NULL,
    category      TEXT,
    unit          TEXT NOT NULL DEFAULT 'unit',
    unit_cost     NUMERIC(12,2) NOT NULL DEFAULT 0,
    reorder_level NUMERIC(10,2) NOT NULL DEFAULT 0,
    is_active     BOOLEAN NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_inventory_items_sku      ON inventory_items(sku);
CREATE INDEX IF NOT EXISTS idx_inventory_items_category ON inventory_items(category);

CREATE TABLE IF NOT EXISTS royan_inventory_events (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sku             TEXT NOT NULL,
    item_id         UUID REFERENCES inventory_items(id) ON DELETE SET NULL,
    quantity_change NUMERIC(12,3) NOT NULL,
    event_type      TEXT NOT NULL CHECK (event_type IN ('restock','dispensed','adjustment','expired','transferred')),
    reference       TEXT,
    performed_by    UUID REFERENCES royan_staff(id) ON DELETE SET NULL,
    notes           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_inventory_events_sku        ON royan_inventory_events(sku);
CREATE INDEX IF NOT EXISTS idx_inventory_events_item_id    ON royan_inventory_events(item_id);
CREATE INDEX IF NOT EXISTS idx_inventory_events_event_type ON royan_inventory_events(event_type);
CREATE INDEX IF NOT EXISTS idx_inventory_events_created_at ON royan_inventory_events(created_at);
