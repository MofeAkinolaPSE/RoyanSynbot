-- 107_appointments.sql
-- Royan Hospital: Appointment scheduling and slot management
-- Part of Phase 3 – Hospital Database Schema

ROLLBACK; -- clear any prior aborted transaction
BEGIN;

-- Appointment slots (doctor/department availability)
CREATE TABLE IF NOT EXISTS public.royan_appointment_slots (
    id              bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    doctor_name     text        NOT NULL,
    department      text        NOT NULL CHECK (department IN (
                                    'A&E', 'OPD', 'Inpatient Ward', 'Laboratory & Diagnostics',
                                    'Pharmacy', 'Billing & Finance', 'Administration',
                                    'Maintenance & Facilities', 'Maternity', 'Surgery'
                                )),
    slot_date       date        NOT NULL,
    slot_time       time        NOT NULL,
    duration_mins   int         NOT NULL DEFAULT 15 CHECK (duration_mins > 0),
    is_available    boolean     NOT NULL DEFAULT true,
    max_patients    int         NOT NULL DEFAULT 1,
    created_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (doctor_name, slot_date, slot_time)
);

-- Appointment bookings (patient ↔ slot)
CREATE TABLE IF NOT EXISTS public.royan_appointments (
    id              bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    patient_id      bigint      NOT NULL REFERENCES public.royan_patients (id) ON DELETE RESTRICT,
    slot_id         bigint      NOT NULL REFERENCES public.royan_appointment_slots (id) ON DELETE RESTRICT,
    encounter_id    bigint      REFERENCES public.royan_encounters (id) ON DELETE SET NULL,
    reason          text,
    status          text        NOT NULL DEFAULT 'booked'
                                CHECK (status IN ('booked', 'confirmed', 'arrived', 'completed', 'no_show', 'cancelled', 'rescheduled')),
    booked_by       text,                                   -- staff or 'patient_self'
    booked_at       timestamptz NOT NULL DEFAULT now(),
    reminder_sent   boolean     NOT NULL DEFAULT false,
    reminder_sent_at timestamptz,
    cancellation_reason text,
    notes           text
);

-- Prevent double-booking: only one booking per slot unless slot has max_patients > 1
-- Enforced via application logic using the slot.is_available flag.

CREATE INDEX IF NOT EXISTS idx_royan_appt_slots_date        ON public.royan_appointment_slots (slot_date, doctor_name);
CREATE INDEX IF NOT EXISTS idx_royan_appt_slots_dept        ON public.royan_appointment_slots (department, slot_date);
CREATE INDEX IF NOT EXISTS idx_royan_appointments_patient   ON public.royan_appointments (patient_id);
CREATE INDEX IF NOT EXISTS idx_royan_appointments_slot      ON public.royan_appointments (slot_id);
CREATE INDEX IF NOT EXISTS idx_royan_appointments_status    ON public.royan_appointments (status);
CREATE INDEX IF NOT EXISTS idx_royan_appointments_booked_at ON public.royan_appointments (booked_at DESC);

COMMIT;
