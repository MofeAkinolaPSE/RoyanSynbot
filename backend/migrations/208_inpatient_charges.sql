-- Migration 208: inpatient bill lines, and a nightly rate for beds
-- ============================================================================
--
-- "we need to make sure that each room has a tariff, so every time a patient is
-- assigned to the room, that is also added to their billing... we can add a new
-- consultant, add a new lab, add a new scan, add drug, and every time you do
-- that for an admitted patient, the bill must also keep track of that."
--
-- TWO THINGS WERE MISSING, ONE OF THEM SILENTLY
-- ---------------------------------------------
-- constants.py has declared TABLE_INPATIENT_BILL_LINES = "royan_inpatient_bill_lines"
-- for some time, and both suggested_bill_items() and get_bill_invoice() query
-- it. The table was never created. Every one of those reads failed, the DB
-- wrapper swallowed the error, and the endpoints returned an empty list — so an
-- admitted patient's bill looked complete while containing none of their stay.
--
-- WHY A RATE ON THE BED RATHER THAN A ROOMS TABLE
-- -----------------------------------------------
-- Hope tracked room_id AND bed_id. Our live config has 24 beds numbered 1-10
-- within each ward and no room identity at all, while royan_service_catalog
-- prices 15 named rooms (Room102, Room107, Neonatal Room3...). Nothing links
-- the two, and no mapping exists to derive one.
--
-- Introducing a rooms table would mean asking Royan to map 24 beds to 15 rooms
-- before ANY inpatient billing works. Putting the nightly rate on the bed —
-- defaulted from its ward — means billing works as soon as six ward rates are
-- entered, and a per-bed override covers private rooms that differ. If Royan
-- later wants true rooms, the rate moves; nothing here blocks that.
--
-- ROOM CHARGES ARE DERIVED, NOT STORED
-- ------------------------------------
-- Nights are computed from admitted_at at read time rather than accrued by a
-- nightly job. A cron that misses a night under-bills silently and one that
-- double-runs over-bills; deriving from the admission timestamp cannot drift
-- from the actual stay. Only ad-hoc charges (consumables, procedures during the
-- stay) are stored as rows.
-- ============================================================================

BEGIN;

-- ── Nightly rate ────────────────────────────────────────────────────────────
ALTER TABLE public.royan_wards
    ADD COLUMN IF NOT EXISTS daily_rate numeric(14,2);

ALTER TABLE public.royan_beds
    ADD COLUMN IF NOT EXISTS daily_rate numeric(14,2);

COMMENT ON COLUMN public.royan_wards.daily_rate IS
  'Default nightly charge for beds in this ward. NULL means not yet priced — the bill shows the stay with a zero rate and flags it, rather than silently charging nothing.';
COMMENT ON COLUMN public.royan_beds.daily_rate IS
  'Overrides the ward rate for this specific bed (a private room in a general ward, say). NULL falls back to the ward.';

-- ── Ad-hoc inpatient charges ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.royan_inpatient_bill_lines (
    id           bigserial PRIMARY KEY,
    encounter_id bigint NOT NULL REFERENCES public.royan_encounters(id) ON DELETE CASCADE,
    patient_id   bigint REFERENCES public.royan_patients(id) ON DELETE SET NULL,

    description  text NOT NULL,
    category     text NOT NULL DEFAULT 'misc',
    quantity     numeric(12,2) NOT NULL DEFAULT 1,
    unit_price   numeric(14,2) NOT NULL DEFAULT 0,
    -- Stored rather than computed so a later price change cannot rewrite what a
    -- patient was already charged.
    total        numeric(14,2) NOT NULL DEFAULT 0,

    -- Where the charge came from, so a line can be traced back and a duplicate
    -- import can be recognised.
    source       text,
    source_id    bigint,

    charged_at   timestamptz NOT NULL DEFAULT now(),
    added_by     text,
    notes        text,
    created_at   timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT royan_inpatient_bill_lines_category_check
        CHECK (category IN ('ward', 'nursing', 'consultation', 'lab', 'imaging',
                            'pharmacy', 'procedure', 'consumable', 'ambulance', 'misc'))
);

CREATE INDEX IF NOT EXISTS idx_inpatient_lines_encounter
    ON public.royan_inpatient_bill_lines (encounter_id, charged_at);

-- One line per source record: re-running an import must update rather than
-- duplicate, or a patient is charged twice for the same drug.
CREATE UNIQUE INDEX IF NOT EXISTS uq_inpatient_line_source
    ON public.royan_inpatient_bill_lines (encounter_id, source, source_id)
    WHERE source IS NOT NULL AND source_id IS NOT NULL;

COMMENT ON TABLE public.royan_inpatient_bill_lines IS
  'Ad-hoc charges accrued during an admission. Room charges are NOT here — they are derived from admitted_at at read time so they cannot drift from the real length of stay.';

COMMIT;

-- Verification:
--   SELECT count(*) FROM royan_inpatient_bill_lines;           -- 0, table now exists
--   SELECT name, daily_rate FROM royan_wards ORDER BY name;    -- all NULL until priced
