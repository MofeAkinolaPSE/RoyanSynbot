-- 173_doctor_info_readiness.sql
-- Data-readiness pass: specialty/license_number were designed (present in
-- migration 130's CREATE TABLE template) but that template was a documented
-- no-op — only external_source/external_id actually got appended to the
-- live royan_staff table via a separate ALTER. These columns have never
-- existed live; specialty currently only hides inside an unqueryable
-- metadata jsonb blob populated at staff registration.

ROLLBACK;
BEGIN;

ALTER TABLE royan_staff
    ADD COLUMN IF NOT EXISTS specialty      text,
    ADD COLUMN IF NOT EXISTS license_number text;

COMMIT;
