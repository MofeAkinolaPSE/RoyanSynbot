-- Migration 144: Add role, user_id link, and tour_state to royan_staff
--
-- Migration 130 tried to add a `role` CHECK column and a `user_id` link on
-- royan_staff as part of a fresh CREATE TABLE template, but since royan_staff
-- already existed (from migration 111) that was a no-op — the columns were
-- never actually added. This migration finally delivers them, run against a
-- now-empty table (migration 143 ran first) so no backfill/reconciliation
-- logic is needed.
--
-- The CHECK constraint's value list must stay identical to
-- backend/src/constants.py::STAFF_ROLES — see backend/tests/test_role_taxonomy.py
-- which asserts the two never drift apart.

ROLLBACK;
BEGIN;

ALTER TABLE public.royan_staff
    ADD COLUMN IF NOT EXISTS role text;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_staff_role'
          AND conrelid = 'public.royan_staff'::regclass
    ) THEN
        ALTER TABLE public.royan_staff
            ADD CONSTRAINT chk_staff_role CHECK (
                role IS NULL OR role IN (
                    'admin', 'management', 'doctor', 'nurse', 'pharmacist', 'lab',
                    'radiology', 'receptionist', 'physiotherapist', 'finance', 'hr',
                    'ops', 'quality_assurance'
                )
            );
    END IF;
END;
$$;

ALTER TABLE public.royan_staff
    ADD COLUMN IF NOT EXISTS user_id uuid REFERENCES public.royan_users(id) ON DELETE SET NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_royan_staff_user_id
    ON public.royan_staff (user_id) WHERE user_id IS NOT NULL;

ALTER TABLE public.royan_staff
    ADD COLUMN IF NOT EXISTS tour_state jsonb NOT NULL DEFAULT '{}'::jsonb;

CREATE INDEX IF NOT EXISTS idx_royan_staff_role ON public.royan_staff (role);

COMMIT;
