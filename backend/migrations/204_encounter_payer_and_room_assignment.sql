-- Migration 204: payer on the encounter, and daily consulting-room assignment
-- ============================================================================
--
-- 1. PAYER ON THE ENCOUNTER
-- -------------------------
-- Front desk was asked to choose private vs HMO when putting a patient on the
-- queue: "they need to be able to select whether the patient is private or
-- HMO... if the patient is HMO, that insurance ID number should always appear
-- on the list."
--
-- royan_encounters had nowhere to record that. Today the queue derives it by
-- checking whether the patient has a policy at all — which is a reasonable
-- default but not a decision. A patient WITH cover can still elect to pay
-- privately for a visit, and that choice governs how the visit is billed, so it
-- belongs on the encounter rather than being re-inferred from the patient every
-- time someone asks.
--
-- membership_id is stored alongside deliberately. The number on the card the
-- patient presented today is the number the claim must carry, even if the
-- policy on file is later corrected.
--
-- 2. CONSULTING-ROOM ASSIGNMENT
-- -----------------------------
-- "once the doctor registers and signs up, they are assigned a room by the
-- front desk... the front desk wants that ability to designate what consulting
-- rooms belong to a particular doctor on the ground."
--
-- Modelled per DAY, not as a column on the doctor: room allocation changes with
-- who is on shift, and yesterday's allocation should not silently apply today.
-- ============================================================================

BEGIN;

ALTER TABLE public.royan_encounters
    ADD COLUMN IF NOT EXISTS payer_type    text,
    ADD COLUMN IF NOT EXISTS membership_id text;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'royan_encounters_payer_type_check'
    ) THEN
        ALTER TABLE public.royan_encounters
            ADD CONSTRAINT royan_encounters_payer_type_check
            CHECK (payer_type IS NULL OR payer_type IN ('private', 'hmo'));
    END IF;
END $$;

COMMENT ON COLUMN public.royan_encounters.payer_type IS
  'Who is paying for THIS visit, chosen at registration. NULL on historical rows — the queue falls back to whether the patient holds a policy.';
COMMENT ON COLUMN public.royan_encounters.membership_id IS
  'Membership number as presented at this visit. Kept separately from royan_patient_insurance so a later correction to the policy does not rewrite what was claimed.';

CREATE INDEX IF NOT EXISTS idx_encounters_payer_type
    ON public.royan_encounters (payer_type) WHERE payer_type IS NOT NULL;

-- ---------------------------------------------------------------------------
-- Daily consulting-room assignment
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.royan_room_assignments (
    id           bigserial PRIMARY KEY,
    doctor_id    uuid NOT NULL REFERENCES public.royan_staff(id) ON DELETE CASCADE,
    room         text NOT NULL,
    assigned_on  date NOT NULL DEFAULT CURRENT_DATE,
    assigned_by  uuid REFERENCES public.royan_staff(id) ON DELETE SET NULL,
    notes        text,
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now()
);

-- One doctor holds one room per day, and one room holds one doctor per day.
-- Both directions matter: double-booking a room sends two patients to the same
-- door, and giving a doctor two rooms makes the queue call the wrong one.
CREATE UNIQUE INDEX IF NOT EXISTS uq_room_assignment_doctor_day
    ON public.royan_room_assignments (doctor_id, assigned_on);
CREATE UNIQUE INDEX IF NOT EXISTS uq_room_assignment_room_day
    ON public.royan_room_assignments (lower(room), assigned_on);
CREATE INDEX IF NOT EXISTS idx_room_assignment_day
    ON public.royan_room_assignments (assigned_on DESC);

COMMENT ON TABLE public.royan_room_assignments IS
  'Which consulting room a doctor is working from on a given day. Per-day rather than a column on the doctor, because allocation follows the shift rota.';

COMMIT;

-- Verification:
--   SELECT count(*) FILTER (WHERE payer_type IS NOT NULL) AS chosen,
--          count(*) AS total FROM royan_encounters;
--   \d royan_room_assignments
