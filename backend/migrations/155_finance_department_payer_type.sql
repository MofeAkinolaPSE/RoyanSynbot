-- Migration 155: Department + payer-type finance segregation, HMO identity data
--
-- Client ask (Post-deployment-mods/promptplan.md item 15): "Each department
-- is their own business, RoyanLab, RoyanPharma, RoyanRadiology (Scancare) —
-- the MD wants to track the finances between all departments with the
-- toggle of a button. Also the Drugs/Services provided per which one went
-- into HMO, or Staff or private Patient."
--
-- royan_bill_items already carries a `category` column (consultation/lab/
-- pharmacy/ward/procedure/imaging/misc, sourced from royan_service_catalog)
-- but nothing mapped that to a department the MD would recognize, and
-- nothing tagged which payer footed each line. department is populated by
-- billing_hospital.py from a category->department mapping at bill-item
-- creation time; payer_type is auto-derived from the coverage quote
-- (insurance.active) with an explicit override for 'staff', since nothing
-- in the schema identifies a patient as hospital staff today.
--
-- Item 18: "each HMO comes with the Identity data, we'll get the exact data
-- later" — identity_data is a flexible jsonb bucket so the registration flow
-- can ship now without a schema change once the client provides the exact
-- per-HMO fields.

ROLLBACK;
BEGIN;

ALTER TABLE public.royan_bill_items
    ADD COLUMN IF NOT EXISTS department text,
    ADD COLUMN IF NOT EXISTS payer_type text CHECK (payer_type IN ('hmo', 'staff', 'private'));

CREATE INDEX IF NOT EXISTS idx_royan_bill_items_department ON public.royan_bill_items (department);
CREATE INDEX IF NOT EXISTS idx_royan_bill_items_payer_type ON public.royan_bill_items (payer_type);

ALTER TABLE public.royan_patient_insurance
    ADD COLUMN IF NOT EXISTS identity_data jsonb NOT NULL DEFAULT '{}'::jsonb;

COMMIT;
