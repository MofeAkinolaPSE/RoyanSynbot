-- Migration 143: Hard-delete the quarantined Sage customer/debtor contamination
--
-- Migration 141 quarantined ~2,297 rows in royan_staff that turned out to be
-- Sage customer/debtor export data, not hospital staff (see that migration's
-- comment for the full investigation). The user has now confirmed deletion
-- rather than continued quarantine, since a new self-service registration +
-- admin-approval flow is replacing this table's population method entirely
-- and should start from a clean table.
--
-- Safe to delete: every FK referencing royan_staff(id) added in migrations
-- 111/120/131/132/138 is ON DELETE CASCADE or ON DELETE SET NULL — nothing
-- RESTRICTs, and the quarantined rows have zero real payroll/clinical activity
-- (monthly_gross = 0, no encounters/prescriptions/lab orders reference them
-- since they were never real staff to begin with).

ROLLBACK;
BEGIN;

DELETE FROM public.royan_staff WHERE quarantined_at IS NOT NULL;

COMMIT;
