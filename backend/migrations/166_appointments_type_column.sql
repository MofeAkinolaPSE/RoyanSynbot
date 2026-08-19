-- 166_appointments_type_column.sql
-- Royan Hospital: Persist appointment_type on royan_appointments.
-- Previously accepted by AppointmentBook but discarded — book_appointment()
-- only ever folded it into `reason` as a last-resort fallback, and
-- _enrich() faked an "appointment_type" field by echoing `reason` back.
-- Nullable, unconstrained text — matches reason/notes on this same table;
-- the frontend's own Select already constrains the value set client-side.

ROLLBACK;
BEGIN;

ALTER TABLE public.royan_appointments
    ADD COLUMN IF NOT EXISTS appointment_type text;

COMMIT;
