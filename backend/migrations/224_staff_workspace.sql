-- Staff Workspace: one home for every member of staff (their day, tasks, requests,
-- messages, time clock and progress), connected to HR, Roy Books and the
-- hospital's operational modules. Spec: backend/docs/Staff-workspace/.
--
-- Identity: a person is their login (royan_users). The HR profile (royan_staff)
-- is linked to it by user_id (migration 144), so everyone approved on User Access
-- is on the team and in HR. Nothing here creates a second identity model.
--
-- Time: the clock runs on the server (staff_time_sessions, with breaks); clocking
-- out writes royan_timesheets rows that HR reviews (submitted -> approved/rejected),
-- and approved hours feed payroll. The old clock kept the open shift as a
-- timesheet row with clock_out NULL; there are no such rows (table empty).

BEGIN;

-- ---------------------------------------------------------------- HR profile
ALTER TABLE royan_staff ADD COLUMN IF NOT EXISTS weekly_hours numeric(5,2) NOT NULL DEFAULT 40;
UPDATE royan_staff s SET user_id = u.id FROM royan_users u
 WHERE s.user_id IS NULL AND s.email IS NOT NULL AND lower(u.email) = lower(s.email)
   AND NOT EXISTS (SELECT 1 FROM royan_staff x WHERE x.user_id = u.id);

-- ---------------------------------------------------------------- time clock
CREATE TABLE IF NOT EXISTS staff_time_sessions (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id          uuid NOT NULL REFERENCES royan_users(id) ON DELETE CASCADE,
  staff_id         uuid REFERENCES royan_staff(id) ON DELETE SET NULL,
  started_at       timestamptz NOT NULL DEFAULT now(),
  ended_at         timestamptz,
  break_seconds    integer NOT NULL DEFAULT 0,
  break_started_at timestamptz,
  breaks           integer NOT NULL DEFAULT 0,
  department       text,
  note             text,
  timesheet_id     uuid,
  created_at       timestamptz NOT NULL DEFAULT now()
);
-- one running clock per person
CREATE UNIQUE INDEX IF NOT EXISTS uq_staff_time_open ON staff_time_sessions(user_id) WHERE ended_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_staff_time_user_start ON staff_time_sessions(user_id, started_at DESC);

-- Timesheets become reviewable entries. Several sessions can fall on one day
-- (clock out for a clinic, back in for a night call), so the one-row-per-shift
-- key goes; the session id identifies a clock entry instead.
ALTER TABLE royan_timesheets DROP CONSTRAINT IF EXISTS royan_timesheets_staff_id_date_shift_key;
ALTER TABLE royan_timesheets ADD COLUMN IF NOT EXISTS user_id uuid REFERENCES royan_users(id) ON DELETE SET NULL;
ALTER TABLE royan_timesheets ADD COLUMN IF NOT EXISTS session_id uuid REFERENCES staff_time_sessions(id) ON DELETE SET NULL;
ALTER TABLE royan_timesheets ADD COLUMN IF NOT EXISTS department text;
ALTER TABLE royan_timesheets ADD COLUMN IF NOT EXISTS source text NOT NULL DEFAULT 'manual';
ALTER TABLE royan_timesheets ADD COLUMN IF NOT EXISTS status text NOT NULL DEFAULT 'submitted';
ALTER TABLE royan_timesheets ADD COLUMN IF NOT EXISTS recorded_by text;
ALTER TABLE royan_timesheets ADD COLUMN IF NOT EXISTS approved_by uuid;
ALTER TABLE royan_timesheets ADD COLUMN IF NOT EXISTS approved_at timestamptz;
ALTER TABLE royan_timesheets ADD COLUMN IF NOT EXISTS review_note text;
ALTER TABLE royan_timesheets DROP CONSTRAINT IF EXISTS royan_timesheets_status_check;
ALTER TABLE royan_timesheets ADD CONSTRAINT royan_timesheets_status_check CHECK (status IN ('submitted','approved','rejected'));
ALTER TABLE royan_timesheets DROP CONSTRAINT IF EXISTS royan_timesheets_source_check;
ALTER TABLE royan_timesheets ADD CONSTRAINT royan_timesheets_source_check CHECK (source IN ('clock','manual','hr'));
UPDATE royan_timesheets t SET user_id = s.user_id FROM royan_staff s WHERE t.user_id IS NULL AND s.id = t.staff_id;
UPDATE royan_timesheets SET status = 'approved' WHERE approved AND status = 'submitted';
CREATE INDEX IF NOT EXISTS idx_royan_timesheets_user_date ON royan_timesheets(user_id, date);
CREATE INDEX IF NOT EXISTS idx_royan_timesheets_status ON royan_timesheets(status, date);

-- ---------------------------------------------------------------- tasks, reminders, notes
-- assigned_to / created_by stay text: other writers store role targets such as
-- 'role:regulatory'. The workspace stores login ids there.
ALTER TABLE royan_tasks ADD COLUMN IF NOT EXISTS created_by text;
ALTER TABLE royan_tasks ADD COLUMN IF NOT EXISTS kind text NOT NULL DEFAULT 'task';
ALTER TABLE royan_tasks ADD COLUMN IF NOT EXISTS department text;
ALTER TABLE royan_tasks ADD COLUMN IF NOT EXISTS entity_type text;
ALTER TABLE royan_tasks ADD COLUMN IF NOT EXISTS entity_id text;
ALTER TABLE royan_tasks ADD COLUMN IF NOT EXISTS entity_label text;
ALTER TABLE royan_tasks ADD COLUMN IF NOT EXISTS link text;
ALTER TABLE royan_tasks ADD COLUMN IF NOT EXISTS checklist jsonb NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE royan_tasks ADD COLUMN IF NOT EXISTS waiting_on text;
ALTER TABLE royan_tasks ADD COLUMN IF NOT EXISTS started_at timestamptz;
ALTER TABLE royan_tasks ADD COLUMN IF NOT EXISTS completed_by text;
ALTER TABLE royan_tasks ADD COLUMN IF NOT EXISTS request_id uuid;
ALTER TABLE royan_tasks ADD COLUMN IF NOT EXISTS recurrence text;
ALTER TABLE royan_tasks ADD COLUMN IF NOT EXISTS recurrence_until date;
ALTER TABLE royan_tasks ADD COLUMN IF NOT EXISTS series_id uuid;
ALTER TABLE royan_tasks ADD COLUMN IF NOT EXISTS escalation_level integer NOT NULL DEFAULT 0;
ALTER TABLE royan_tasks ADD COLUMN IF NOT EXISTS escalated_at timestamptz;
ALTER TABLE royan_tasks ADD COLUMN IF NOT EXISTS escalated_to text;
ALTER TABLE royan_tasks DROP CONSTRAINT IF EXISTS royan_tasks_kind_check;
ALTER TABLE royan_tasks ADD CONSTRAINT royan_tasks_kind_check CHECK (kind IN ('task','reminder','note'));
ALTER TABLE royan_tasks DROP CONSTRAINT IF EXISTS royan_tasks_status_check;
ALTER TABLE royan_tasks ADD CONSTRAINT royan_tasks_status_check
  CHECK (status IN ('pending','in_progress','waiting','blocked','completed','done','cancelled'));
ALTER TABLE royan_tasks DROP CONSTRAINT IF EXISTS royan_tasks_priority_check;
ALTER TABLE royan_tasks ADD CONSTRAINT royan_tasks_priority_check CHECK (priority IN ('low','medium','high','urgent','critical'));
-- one open task per operational item (the "Take it" button is idempotent)
CREATE UNIQUE INDEX IF NOT EXISTS uq_royan_tasks_open_operational ON royan_tasks(source_ref)
  WHERE source = 'operational' AND status NOT IN ('completed','done','cancelled');
CREATE INDEX IF NOT EXISTS idx_royan_tasks_created_by ON royan_tasks(created_by);
CREATE INDEX IF NOT EXISTS idx_royan_tasks_completed ON royan_tasks(completed_by, completed_at);
CREATE INDEX IF NOT EXISTS idx_royan_tasks_series ON royan_tasks(series_id) WHERE series_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS staff_task_activity (
  id         bigserial PRIMARY KEY,
  task_id    uuid NOT NULL REFERENCES royan_tasks(id) ON DELETE CASCADE,
  actor      uuid,
  kind       text NOT NULL,          -- created, status, comment, checklist, assigned, updated, resolved, escalated
  body       text,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_task_activity_task ON staff_task_activity(task_id, created_at);

-- ---------------------------------------------------------------- requests between people / teams
CREATE TABLE IF NOT EXISTS staff_requests (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  from_user        uuid NOT NULL REFERENCES royan_users(id) ON DELETE CASCADE,
  to_user          uuid REFERENCES royan_users(id) ON DELETE SET NULL,
  to_department    text,
  kind             text NOT NULL DEFAULT 'info' CHECK (kind IN ('info','work')),
  subject          text NOT NULL,
  body             text,
  task_id          uuid REFERENCES royan_tasks(id) ON DELETE SET NULL,   -- the requester's related task
  work_task_id     uuid REFERENCES royan_tasks(id) ON DELETE SET NULL,   -- the task a work request created
  due_at           timestamptz,
  status           text NOT NULL DEFAULT 'sent'
                   CHECK (status IN ('sent','acknowledged','in_progress','responded','closed','declined')),
  response         text,
  responded_by     uuid,
  responded_at     timestamptz,
  closed_at        timestamptz,
  escalation_level integer NOT NULL DEFAULT 0,
  escalated_at     timestamptz,
  escalated_to     text,
  created_at       timestamptz NOT NULL DEFAULT now(),
  updated_at       timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT staff_requests_target_check CHECK (to_user IS NOT NULL OR to_department IS NOT NULL)
);
CREATE INDEX IF NOT EXISTS idx_staff_requests_to ON staff_requests(to_user, status);
CREATE INDEX IF NOT EXISTS idx_staff_requests_from ON staff_requests(from_user, status);

CREATE TABLE IF NOT EXISTS staff_request_messages (
  id         bigserial PRIMARY KEY,
  request_id uuid NOT NULL REFERENCES staff_requests(id) ON DELETE CASCADE,
  author     uuid,
  body       text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------- inbox + work journal + preferences
CREATE TABLE IF NOT EXISTS staff_notifications (
  id         bigserial PRIMARY KEY,
  user_id    uuid NOT NULL REFERENCES royan_users(id) ON DELETE CASCADE,
  kind       text NOT NULL,      -- assigned, request, response, mention, comment, completed, reminder, escalation, hr, leave, payroll
  level      text NOT NULL DEFAULT 'info' CHECK (level IN ('critical','action','info','social')),
  title      text NOT NULL,
  body       text,
  link_type  text,               -- task, request, message, page
  link_id    text,
  actor      uuid,
  read_at    timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_staff_notifications_user ON staff_notifications(user_id, read_at, created_at DESC);

CREATE TABLE IF NOT EXISTS staff_work_events (
  id          bigserial PRIMARY KEY,
  user_id     uuid NOT NULL REFERENCES royan_users(id) ON DELETE CASCADE,
  kind        text NOT NULL,     -- clock_in, break, resume, clock_out, task_created, task_started, task_completed, request_sent, request_answered
  summary     text NOT NULL,
  entity_type text,
  entity_id   text,
  occurred_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_staff_work_events_user ON staff_work_events(user_id, occurred_at DESC);

CREATE TABLE IF NOT EXISTS staff_preferences (
  user_id    uuid PRIMARY KEY REFERENCES royan_users(id) ON DELETE CASCADE,
  prefs      jsonb NOT NULL DEFAULT '{}'::jsonb,
  updated_at timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------- escalation chains
-- one chain per (subject, priority); steps = [{"after_hours": n, "to": "assignee|giver|management|recipient|requester"}]
CREATE TABLE IF NOT EXISTS staff_escalation_policy (
  subject    text NOT NULL CHECK (subject IN ('task','request')),
  priority   text NOT NULL,
  steps      jsonb NOT NULL,
  updated_by uuid,
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (subject, priority)
);
INSERT INTO staff_escalation_policy (subject, priority, steps) VALUES
  ('task', 'critical', '[{"after_hours":0,"to":"assignee"},{"after_hours":1,"to":"giver"},{"after_hours":4,"to":"management"}]'),
  ('task', 'urgent',   '[{"after_hours":0,"to":"assignee"},{"after_hours":1,"to":"giver"},{"after_hours":4,"to":"management"}]'),
  ('task', 'high',     '[{"after_hours":0,"to":"assignee"},{"after_hours":12,"to":"giver"},{"after_hours":48,"to":"management"}]'),
  ('task', 'medium',   '[{"after_hours":0,"to":"assignee"},{"after_hours":48,"to":"giver"}]'),
  ('task', 'low',      '[{"after_hours":0,"to":"assignee"}]'),
  ('request', 'all',   '[{"after_hours":0,"to":"recipient"},{"after_hours":12,"to":"requester"},{"after_hours":48,"to":"management"}]')
ON CONFLICT (subject, priority) DO NOTHING;

-- ---------------------------------------------------------------- messages on the existing threads tables
ALTER TABLE threads ADD COLUMN IF NOT EXISTS thread_type text;
ALTER TABLE threads ADD COLUMN IF NOT EXISTS channel_key text;
CREATE UNIQUE INDEX IF NOT EXISTS uq_threads_channel_key ON threads(channel_key) WHERE channel_key IS NOT NULL;
CREATE TABLE IF NOT EXISTS thread_reads (
  thread_id    uuid NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
  user_id      text NOT NULL,
  last_read_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (thread_id, user_id)
);

-- ---------------------------------------------------------------- payroll -> Roy Books
-- A payroll record is drafted by HR, approved (accrued in the books: salaries
-- expense against salaries / PAYE / pension payable) and paid (salaries payable
-- cleared against the bank). Who did each step is kept on the record.
ALTER TABLE royan_payroll_records ADD COLUMN IF NOT EXISTS approved_by text;
ALTER TABLE royan_payroll_records ADD COLUMN IF NOT EXISTS approved_at timestamptz;
ALTER TABLE royan_payroll_records ADD COLUMN IF NOT EXISTS paid_by text;
ALTER TABLE royan_payroll_records ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now();
ALTER TABLE royan_payroll_records ADD COLUMN IF NOT EXISTS source text NOT NULL DEFAULT 'manual';
-- the Roy Books bank/cash account salaries were paid from (fin_bank_accounts.id)
ALTER TABLE royan_payroll_records ADD COLUMN IF NOT EXISTS bank_account_id uuid;

-- Posting rules for payroll, pointed at Royan's own Sage chart (the accountant
-- can re-point them under Roy Books > Setup > Posting rules). Deductions other
-- than PAYE and pension (loans, advances) are left unmapped on purpose: where
-- they go is an accounting decision, and a payroll with such deductions waits
-- in Close & Controls until it is made.
INSERT INTO fin_account_mappings (legal_entity_id, mapping_key, account_id, note, updated_by)
SELECT e.id, m.key, a.id, m.note, 'migration:224'
FROM fin_legal_entities e
JOIN (VALUES ('SALARIES_EXPENSE', '6200', 'Salaries Expense (Sage)'),
             ('SALARIES_PAYABLE', '2005', 'Accounts Payable/Salaries (Sage)'),
             ('PAYE_PAYABLE',     '2350', 'State Payroll Taxes Payable - PAYE is a state tax (Sage)'),
             ('PENSION_PAYABLE',  '2360', 'Pensions Contributions (Sage)')) AS m(key, code, note) ON TRUE
JOIN fin_accounts a ON a.legal_entity_id = e.id AND a.code = m.code AND a.status = 'ACTIVE'
ON CONFLICT (legal_entity_id, mapping_key) DO NOTHING;

COMMIT;
