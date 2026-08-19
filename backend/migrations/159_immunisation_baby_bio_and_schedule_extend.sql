-- Migration 159: Baby bio fields + extend the vaccine schedule reference data
--
-- Client ask (backend/docs/Post-deployment-mods/immunization templates/*): the
-- "Vaccination Record" booklet header captures father's/guardian's name and
-- place of birth — neither exists anywhere on royan_patients today. Also the
-- reference schedule seeded in migration 158 only covers Birth through
-- 5 Years; the client's booklet photos show milestones through 10 Years.

ROLLBACK;
BEGIN;

ALTER TABLE public.royan_patients
    ADD COLUMN IF NOT EXISTS father_name    text,
    ADD COLUMN IF NOT EXISTS place_of_birth text;

INSERT INTO public.royan_vaccine_schedule (age_milestone, age_days, vaccine_name, notes) VALUES
    ('3 Years',  1095, 'Flu', 'Yearly flu vaccination'),
    ('4 Years',  1460, 'Flu', 'Yearly flu vaccination'),
    ('5 Years',  1825, 'Flu', 'Yearly flu vaccination'),
    ('9 Years',  3285, 'HPV', NULL),
    ('10 Years', 3650, 'TdaP-IPV', NULL),
    ('10 Years', 3650, 'Yellow Fever', NULL)
ON CONFLICT DO NOTHING;

COMMIT;
