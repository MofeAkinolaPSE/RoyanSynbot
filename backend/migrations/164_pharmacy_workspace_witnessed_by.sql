-- Migration 164: Pharmacy Workspace — witnessed_by field for MAR administration
--
-- royan_medication_admin.witnessed_by_id is uuid (references royan_staff), but
-- no flow anywhere in this app resolves a free-text staff identity to a real
-- royan_staff UUID (administered_by_id on this exact table is already
-- permanently left NULL for the same reason). Add a free-text witnessed_by
-- column mirroring the table's own administered_by / administered_by_id
-- pairing, rather than building new staff-identity-resolution machinery.
--
-- This is the only structural DB change the Pharmacy Workspace pass needs —
-- every other fix (cumulative dispense math, administer's status-crash bug,
-- MAR auto-insert removal, replenishment-request remap, stats,
-- administration-queue) is application-logic-only against the existing schema.

ROLLBACK;
BEGIN;

ALTER TABLE public.royan_medication_admin
    ADD COLUMN IF NOT EXISTS witnessed_by text;

COMMIT;
