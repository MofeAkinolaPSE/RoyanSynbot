-- Migration 145: Staff self-service registration queue
--
-- Public self-registration lands here as 'pending' — no royan_users row is
-- created until an admin approves, so there is deliberately nowhere on
-- royan_users to park pre-approval state. Modeled on the existing
-- royan_mdm_change_requests precedent (migration 134): typed columns for
-- what the admin queue needs to filter/search on, plus a jsonb blob for the
-- free-form per-role KYC fields (kyc_details uses the same key names
-- RoleDetailsForm already writes: specialty, medical_council_number,
-- years_experience — so approval copies it into royan_staff.metadata with
-- no transform).

ROLLBACK;
BEGIN;

CREATE TABLE IF NOT EXISTS public.royan_staff_registrations (
    id                uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    email             text        NOT NULL,
    hashed_password   text        NOT NULL,
    full_name         text        NOT NULL,
    role              text        NOT NULL CHECK (role IN (
                            'admin', 'management', 'doctor', 'nurse', 'pharmacist', 'lab',
                            'radiology', 'receptionist', 'physiotherapist', 'finance', 'hr',
                            'ops', 'quality_assurance'
                        )),
    department        text,
    department_id     bigint      REFERENCES public.royan_departments (id) ON DELETE SET NULL,
    designation       text,
    phone             text,
    kyc_details       jsonb       NOT NULL DEFAULT '{}'::jsonb,
    status            text        NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected')),
    rejection_reason  text,
    reviewed_by       uuid        REFERENCES public.royan_users (id) ON DELETE SET NULL,
    reviewed_at       timestamptz,
    created_staff_id  uuid        REFERENCES public.royan_staff (id) ON DELETE SET NULL,
    created_user_id   uuid        REFERENCES public.royan_users (id) ON DELETE SET NULL,
    submitted_ip      text,
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_staff_registrations_pending_email
    ON public.royan_staff_registrations (lower(email)) WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS idx_staff_registrations_status
    ON public.royan_staff_registrations (status);

DROP TRIGGER IF EXISTS trg_staff_registrations_updated_at ON public.royan_staff_registrations;
CREATE TRIGGER trg_staff_registrations_updated_at
    BEFORE UPDATE ON public.royan_staff_registrations
    FOR EACH ROW EXECUTE FUNCTION public.royan_touch_updated_at();

COMMIT;
