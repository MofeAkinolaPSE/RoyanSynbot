-- Migration 125: Extend royan_encounters.status CHECK constraint
-- Adds nurse_assessment and called to the allowed status values so the
-- nurse-done and call-patient workflow transitions are accepted by the DB.
-- Safe to re-run: drops existing constraint before re-creating.

BEGIN;

ALTER TABLE public.royan_encounters
    DROP CONSTRAINT IF EXISTS royan_encounters_status_check;

ALTER TABLE public.royan_encounters
    ADD CONSTRAINT royan_encounters_status_check CHECK (status IN (
        'patient_registered',
        'triaged',
        'nurse_assessment',
        'called',
        'consulting',
        'lab_ordered',
        'pharmacy_dispensing',
        'billing_pending',
        'discharged'
    ));

COMMIT;
