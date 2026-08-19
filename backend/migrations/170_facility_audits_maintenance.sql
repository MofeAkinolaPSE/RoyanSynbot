-- 170_facility_audits_maintenance.sql
-- Royan Hospital: new, genuinely hospital-native Audits & Maintenance
-- feature — NOT a reuse of the pharma QMS tables from migration 070
-- (audit_schedule/equipment_registry/maintenance_schedule) nor the
-- platform-reliability tables from migration 110 (royan_maintenance_assets/
-- royan_maintenance_tasks, which track SynBot's own infrastructure health,
-- not biomedical equipment). Both were investigated and ruled out as reuse
-- targets — see the department-12 plan for the full trace.

ROLLBACK;
BEGIN;

CREATE TABLE IF NOT EXISTS public.royan_facility_audits (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    audit_title     text NOT NULL,
    department      text NOT NULL,
    scheduled_date  date NOT NULL,
    risk_level      text NOT NULL DEFAULT 'medium',
    status          text NOT NULL DEFAULT 'scheduled',
    findings        text,
    recommendations text,
    score           numeric(5,2),
    created_by      uuid REFERENCES royan_staff(id) ON DELETE SET NULL,
    started_at      timestamptz,
    completed_at    timestamptz,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz,
    CONSTRAINT royan_facility_audits_risk_level_check CHECK (risk_level = ANY (ARRAY['low','medium','high','critical'])),
    CONSTRAINT royan_facility_audits_status_check CHECK (status = ANY (ARRAY['scheduled','in_progress','completed'])),
    CONSTRAINT royan_facility_audits_score_check CHECK (score IS NULL OR (score >= 0 AND score <= 100))
);
CREATE INDEX IF NOT EXISTS idx_facility_audits_status ON royan_facility_audits(status);
CREATE INDEX IF NOT EXISTS idx_facility_audits_scheduled_date ON royan_facility_audits(scheduled_date);

-- Flat, denormalized on purpose — the UI never browses/manages equipment as
-- its own entity, only displays equipment_name as a per-task label. A
-- separate asset-registry table would be unrequested scope.
CREATE TABLE IF NOT EXISTS public.royan_equipment_maintenance (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    equipment_name    text NOT NULL,
    equipment_type    text,
    location          text,
    maintenance_type  text NOT NULL DEFAULT 'preventive',
    description       text,
    due_date          date NOT NULL,
    status            text NOT NULL DEFAULT 'pending',
    completed_by      uuid REFERENCES royan_staff(id) ON DELETE SET NULL,
    completed_at      timestamptz,
    completion_notes  text,
    next_due_date     date,
    created_by        uuid REFERENCES royan_staff(id) ON DELETE SET NULL,
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz,
    CONSTRAINT royan_equipment_maintenance_type_check CHECK (maintenance_type = ANY (ARRAY['preventive','corrective','calibration','emergency'])),
    CONSTRAINT royan_equipment_maintenance_status_check CHECK (status = ANY (ARRAY['pending','completed']))
);
CREATE INDEX IF NOT EXISTS idx_equipment_maintenance_status ON royan_equipment_maintenance(status);
CREATE INDEX IF NOT EXISTS idx_equipment_maintenance_due_date ON royan_equipment_maintenance(due_date);

COMMIT;
