-- 171_clinical_notes_readiness.sql
-- Data-readiness pass: prepares royan_encounter_notes to hold real incoming
-- clinical notes (SOAP sections, diagnosis codes, vitals link, single
-- resolved signer) — "core clinical fields only" per user decision, not the
-- source system's full ~115-column legacy object or its 2-3 tier
-- resident/registrar/consultant sign-off chain.

ROLLBACK;
BEGIN;

ALTER TABLE royan_encounter_notes
    ADD COLUMN IF NOT EXISTS subjective  text,
    ADD COLUMN IF NOT EXISTS objective   text,
    ADD COLUMN IF NOT EXISTS assessment  text,
    ADD COLUMN IF NOT EXISTS plan        text,
    ADD COLUMN IF NOT EXISTS icd10_codes text[],
    ADD COLUMN IF NOT EXISTS vitals_id   bigint REFERENCES royan_vitals(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS signed_by   uuid REFERENCES royan_staff(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS signed_at   timestamptz;

ALTER TABLE royan_encounter_notes DROP CONSTRAINT IF EXISTS royan_encounter_notes_note_type_check;
ALTER TABLE royan_encounter_notes ADD CONSTRAINT royan_encounter_notes_note_type_check
    CHECK (note_type = ANY (ARRAY[
        'general','assessment','plan','soap','progress','discharge',
        'nursing','handover','referral_letter','soap_summary'
    ]));

-- Twin constraint — the Notes-Master title catalog resolves note_type from a
-- title's category, so it must accept the same widened vocabulary or the
-- catalog path can never offer these new types.
ALTER TABLE royan_note_titles DROP CONSTRAINT IF EXISTS royan_note_titles_category_check;
ALTER TABLE royan_note_titles ADD CONSTRAINT royan_note_titles_category_check
    CHECK (category = ANY (ARRAY[
        'general','assessment','plan','soap','progress','discharge',
        'nursing','handover','referral_letter','soap_summary'
    ]));

COMMIT;
