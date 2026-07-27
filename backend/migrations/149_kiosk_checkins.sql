-- Migration 149: Create the missing royan_kiosk_checkins table
--
-- backend/src/routers/integrations.py's kiosk self-service endpoints
-- (POST /integrations/kiosk/checkin, GET /integrations/kiosk/queue-status,
-- GET /integrations/kiosk/checkins) have referenced TABLE_KIOSK_CHECKINS
-- ("royan_kiosk_checkins") since those routes were added, but no migration
-- ever created the table. Every insert/select against it has been silently
-- failing (local_db.py logs the error and returns empty/None rather than
-- raising), so kiosk check-in has never actually recorded a visit and
-- "checkins_today" on the queue-status board has always read 0.

ROLLBACK;
BEGIN;

CREATE TABLE IF NOT EXISTS public.royan_kiosk_checkins (
    id             bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    patient_id     bigint      NOT NULL REFERENCES public.royan_patients (id) ON DELETE CASCADE,
    mrn            text,
    appointment_id bigint      REFERENCES public.royan_appointments (id) ON DELETE SET NULL,
    checkin_type   text        NOT NULL DEFAULT 'walk_in',
    checkin_time   timestamptz NOT NULL DEFAULT now(),
    checkin_date   date        NOT NULL DEFAULT current_date,
    status         text        NOT NULL DEFAULT 'checked_in'
);

CREATE INDEX IF NOT EXISTS idx_royan_kiosk_checkins_date
    ON public.royan_kiosk_checkins (checkin_date);

CREATE INDEX IF NOT EXISTS idx_royan_kiosk_checkins_patient
    ON public.royan_kiosk_checkins (patient_id);

COMMIT;
