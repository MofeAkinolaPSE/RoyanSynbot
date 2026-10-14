-- Migration 206: doctor-to-nurse admission requests
-- ============================================================================
--
-- "when a doctor requests admission for a particular patient, the nurse's
-- dashboard needs to have a card that pops up that says, one patient waiting
-- admission... The nurse then clicks on that admission ticket and it moves them
-- to the wards."
--
-- No such mechanism existed. There is no royan_admissions table at all — only
-- royan_wards / royan_beds (live occupancy) and royan_ward_stay_history
-- (migrated Hope history). A doctor wanting a patient admitted had to tell
-- somebody verbally.
--
-- WHY A REQUEST TABLE RATHER THAN AN ENCOUNTER STATUS
-- ---------------------------------------------------
-- "Admission requested" is not a queue position. The patient is still under the
-- doctor, still on the clinical queue, possibly still having tests. Adding it to
-- ENCOUNTER_STATUS_TRANSITIONS would force the encounter out of whatever state
-- it is genuinely in, and there is no path back if the nurse declines.
--
-- A request also has its own lifecycle and its own author, decided by a
-- different person from the one who raised it. That is a record, not a flag.
-- ============================================================================

BEGIN;

CREATE TABLE IF NOT EXISTS public.royan_admission_requests (
    id             bigserial PRIMARY KEY,
    encounter_id   bigint NOT NULL REFERENCES public.royan_encounters(id) ON DELETE CASCADE,
    patient_id     bigint NOT NULL REFERENCES public.royan_patients(id) ON DELETE CASCADE,

    requested_by   text,
    requested_at   timestamptz NOT NULL DEFAULT now(),
    ward_preference text,
    reason         text,
    urgency        text NOT NULL DEFAULT 'routine',

    -- pending -> admitted | declined | cancelled
    status         text NOT NULL DEFAULT 'pending',
    decided_by     text,
    decided_at     timestamptz,
    decision_note  text,
    -- Set when the nurse actually puts the patient in a bed, so the request
    -- links to where they went rather than just saying "admitted".
    bed_id         bigint REFERENCES public.royan_beds(id) ON DELETE SET NULL,

    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT royan_admission_requests_status_check
        CHECK (status IN ('pending', 'admitted', 'declined', 'cancelled')),
    CONSTRAINT royan_admission_requests_urgency_check
        CHECK (urgency IN ('routine', 'urgent', 'immediate'))
);

-- One live request per encounter. Without this a doctor clicking twice puts two
-- tickets on the nurses' board for the same patient, and the count on the card
-- stops meaning "patients waiting".
CREATE UNIQUE INDEX IF NOT EXISTS uq_admission_request_open_per_encounter
    ON public.royan_admission_requests (encounter_id)
    WHERE status = 'pending';

-- The nurses' card reads exactly this.
CREATE INDEX IF NOT EXISTS idx_admission_requests_pending
    ON public.royan_admission_requests (requested_at)
    WHERE status = 'pending';

CREATE INDEX IF NOT EXISTS idx_admission_requests_patient
    ON public.royan_admission_requests (patient_id, requested_at DESC);

COMMENT ON TABLE public.royan_admission_requests IS
  'A doctor asking for a patient to be admitted, and the nurse decision on it. Separate from encounter status because the patient stays on the clinical queue while the request is open, and a decline must leave them where they were.';

COMMIT;

-- Verification:
--   SELECT status, count(*) FROM royan_admission_requests GROUP BY 1;
--   -- a second pending request for the same encounter must fail:
--   -- ERROR: duplicate key value violates unique constraint
--   --        "uq_admission_request_open_per_encounter"
