-- HMO desk: the patient's signature for the visit's claims form (signed once, on the pad at the HMO desk or the
-- pharmacy), and the HMO officer's check of the claim before it goes to the HMO.
ALTER TABLE royan_encounters ADD COLUMN IF NOT EXISTS claim_signature_url text;
ALTER TABLE royan_encounters ADD COLUMN IF NOT EXISTS claim_signed_at timestamptz;
ALTER TABLE royan_encounters ADD COLUMN IF NOT EXISTS claim_signed_by text;
ALTER TABLE royan_encounters ADD COLUMN IF NOT EXISTS hmo_verified_at timestamptz;
ALTER TABLE royan_encounters ADD COLUMN IF NOT EXISTS hmo_verified_by text;
ALTER TABLE royan_encounters ADD COLUMN IF NOT EXISTS hmo_verify_note text;
-- the patient list reads A-Z by the name as shown (first name, then surname)
CREATE INDEX IF NOT EXISTS idx_royan_patients_name_az ON royan_patients (upper(first_name), upper(last_name), id);
