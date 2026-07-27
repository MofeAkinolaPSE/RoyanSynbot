-- Migration 158: Mother-baby patient linkage + vaccine schedule reference data
--
-- Client ask (Post-deployment-mods/promptplan.md, Nurse section): a
-- dedicated "Babies" page with DOB/gender/time-of-delivery, linked to the
-- mother's record. Today royan_newborn_assessment.patient_id is copied
-- straight from the mother's delivery record (mch_obgyn.py:407) — the baby
-- never gets its own royan_patients row, so there's no distinct patient to
-- build a "Babies page" or link immunisation records to. This migration
-- adds the FK; backend/src/routers/mch_obgyn.py's add_newborn_assessment is
-- updated separately to actually create that row.
--
-- Also seeds royan_vaccine_schedule from the client's photographed
-- vaccination-schedule booklet (immunization templates/VAccnination records
-- template and Vaccination schedule.jpeg) — real reference data to drive
-- the "what's due next" auto-fill/dropdown the client explicitly asked for.

ROLLBACK;
BEGIN;

ALTER TABLE public.royan_patients
    ADD COLUMN IF NOT EXISTS mother_patient_id bigint REFERENCES public.royan_patients (id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_royan_patients_mother
    ON public.royan_patients (mother_patient_id)
    WHERE mother_patient_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS public.royan_vaccine_schedule (
    id             bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    age_milestone  text        NOT NULL,   -- "Birth", "6 Weeks", "10 Weeks", ... matches the client's booklet wording
    age_days       int,                    -- approximate age in days, for sorting/"what's due next" comparisons
    vaccine_name   text        NOT NULL,
    dose_number    int,
    notes          text
);

CREATE INDEX IF NOT EXISTS idx_royan_vaccine_schedule_age_days
    ON public.royan_vaccine_schedule (age_days);

INSERT INTO public.royan_vaccine_schedule (age_milestone, age_days, vaccine_name, notes) VALUES
    ('Birth',     0,   'BCG', NULL),
    ('Birth',     0,   'HepB', NULL),
    ('Birth',     0,   'Polio', NULL),
    ('6 Weeks',   42,  'DTaP-HepB-Hib-IPV', NULL),
    ('6 Weeks',   42,  'PCV', NULL),
    ('6 Weeks',   42,  'Rotavirus', NULL),
    ('10 Weeks',  70,  'DTaP-HepB-Hib-IPV', NULL),
    ('10 Weeks',  70,  'PCV', NULL),
    ('10 Weeks',  70,  'Rotavirus', NULL),
    ('14 Weeks',  98,  'DTaP-HepB-Hib-IPV', NULL),
    ('14 Weeks',  98,  'PCV', NULL),
    ('6 Months',  182, 'Vit A', NULL),
    ('6 Months',  182, 'Flu', NULL),
    ('7 Months',  213, 'Flu', NULL),
    ('9 Months',  274, 'Yellow Fever', NULL),
    ('9 Months',  274, 'Measles', NULL),
    ('9 Months',  274, 'Meningococcal Conj. ACYW', NULL),
    ('12 Months', 365, 'Cholera', 'Given as 2 oral doses, 2 weeks apart'),
    ('12 Months', 365, 'Varicella', NULL),
    ('12 Months', 365, 'Vit A', NULL),
    ('12 Months', 365, 'Meningococcal Conj. ACYW', NULL),
    ('12 Months', 365, 'MMR', NULL),
    ('13 Months', 395, 'MMR', NULL),
    ('13 Months', 395, 'Varicella', NULL),
    ('18 Months', 548, 'DTaP-HepB-Hib-IPV', NULL),
    ('18 Months', 548, 'Hep A', NULL),
    ('2 Years',   730, 'Typhoid', NULL),
    ('2 Years',   730, 'Hepatitis A', NULL),
    ('2 Years',   730, 'Flu', NULL),
    ('5 Years',   1825,'DTaP-IPV Booster', NULL),
    ('5 Years',   1825,'Typhoid', NULL),
    ('5 Years',   1825,'MMR', NULL)
ON CONFLICT DO NOTHING;

COMMIT;
