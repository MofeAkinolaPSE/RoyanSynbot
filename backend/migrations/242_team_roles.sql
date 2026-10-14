-- New team roles (Oct 2026): HMO officer, billing & cashier, stores, auditor. Must equal constants.STAFF_ROLES.
ALTER TABLE royan_staff DROP CONSTRAINT IF EXISTS chk_staff_role;
ALTER TABLE royan_staff ADD CONSTRAINT chk_staff_role CHECK (role IS NULL OR role = ANY (ARRAY[
  'admin','management','doctor','nurse','pharmacist','lab','radiology','receptionist','physiotherapist','finance','hr',
  'ops','quality_assurance','hmo','cashier','store','auditor']));
DO $$
DECLARE c text;
BEGIN
  SELECT conname INTO c FROM pg_constraint WHERE conrelid = 'royan_staff_registrations'::regclass AND contype = 'c'
    AND pg_get_constraintdef(oid) LIKE '%receptionist%';
  IF c IS NOT NULL THEN EXECUTE format('ALTER TABLE royan_staff_registrations DROP CONSTRAINT %I', c); END IF;
END $$;
ALTER TABLE royan_staff_registrations ADD CONSTRAINT royan_staff_registrations_role_check CHECK (role = ANY (ARRAY[
  'admin','management','doctor','nurse','pharmacist','lab','radiology','receptionist','physiotherapist','finance','hr',
  'ops','quality_assurance','hmo','cashier','store','auditor']));
