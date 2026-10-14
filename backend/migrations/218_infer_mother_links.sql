-- Migration 218: link babies to mothers where the evidence supports it
-- ============================================================================
--
-- THE DATA HOPE HELD: NONE
-- ------------------------
-- royan_patients.mother_patient_id was set on 2 of 60,929 rows. Hope's persons
-- table does carry mother_name, mother_first_name, mother_last_name,
-- mother_identifier and guardian_relation — and every one of them is empty on
-- all 60,966 rows. The columns exist; the data never did. guarantors and
-- guardians were checked in an earlier phase and are likewise empty shells.
--
-- So the link cannot be migrated. It can only be INFERRED, and only where the
-- inference is strong enough to be worth making.
--
-- WHY SURNAME ALONE IS NOT ENOUGH
-- -------------------------------
-- Matching an under-5 to adult women sharing a surname gives:
--
--     exactly one candidate     286
--     two to five candidates    369
--     more than five            820   <- useless
--
-- Nigerian surnames are shared widely enough that a lone surname match would
-- attach 820 children to a guessed mother. A wrong mother on an immunisation
-- record is worse than no mother: doses get attributed to the wrong child's
-- schedule and a recall reaches the wrong family.
--
-- THE SIGNAL USED
-- ---------------
-- Surname AND registration within 7 days, requiring EXACTLY ONE candidate.
-- Mother and newborn are registered together, so the pairing is corroborated by
-- two independent facts rather than one. That yields 291 links, 157 of them
-- registered the very same day.
--
-- The remaining ~1,470 children stay unlinked. That is the honest outcome: the
-- evidence to place them does not exist, and front-desk staff can link them as
-- families are seen.
--
-- EVERY LINK RECORDS HOW IT WAS MADE
-- ----------------------------------
-- mother_link_basis stores 'inferred_same_day' or 'inferred_same_week' so an
-- inferred link is never mistaken for one a human confirmed, and so the whole
-- set can be reversed with one statement if Royan disagrees with the method.
-- ============================================================================

BEGIN;

ALTER TABLE public.royan_patients
    ADD COLUMN IF NOT EXISTS mother_link_basis text;

COMMENT ON COLUMN public.royan_patients.mother_link_basis IS
  'How mother_patient_id was established: NULL = entered by staff; inferred_same_day / inferred_same_week = derived in migration 218 from surname plus registration proximity, never confirmed by a human.';

WITH baby AS (
    SELECT id, registered_at,
           upper(split_part(btrim(last_name), ' ',
                 array_length(string_to_array(btrim(last_name), ' '), 1))) AS surname
    FROM public.royan_patients
    WHERE date_of_birth > current_date - interval '5 years'
      AND mother_patient_id IS NULL
      AND btrim(coalesce(last_name, '')) <> ''
),
mum AS (
    SELECT id, registered_at,
           upper(split_part(btrim(last_name), ' ',
                 array_length(string_to_array(btrim(last_name), ' '), 1))) AS surname
    FROM public.royan_patients
    WHERE gender ILIKE 'f%'
      -- 13 is a deliberately low floor: it admits every plausible mother rather
      -- than imposing an assumption about maternal age on real records.
      AND date_of_birth <= current_date - interval '13 years'
      AND btrim(coalesce(last_name, '')) <> ''
),
paired AS (
    SELECT b.id AS baby_id,
           min(m.id) AS mother_id,
           count(*) AS candidates,
           min(abs(extract(epoch FROM (m.registered_at - b.registered_at)) / 86400)) AS day_gap
    FROM baby b
    JOIN mum m
      ON m.surname = b.surname
     AND m.id <> b.id
     AND abs(extract(epoch FROM (m.registered_at - b.registered_at)) / 86400) <= 7
    GROUP BY b.id
)
UPDATE public.royan_patients p
SET mother_patient_id = paired.mother_id,
    mother_link_basis = CASE WHEN paired.day_gap <= 1
                             THEN 'inferred_same_day'
                             ELSE 'inferred_same_week' END,
    updated_at = now()
FROM paired
WHERE p.id = paired.baby_id
  -- Exactly one. Ambiguity is left unlinked rather than resolved by guess.
  AND paired.candidates = 1;

COMMIT;

-- Verification:
--   SELECT coalesce(mother_link_basis,'entered by staff') AS basis, count(*)
--   FROM royan_patients WHERE mother_patient_id IS NOT NULL GROUP BY 1;
--
-- To reverse the whole inferred set:
--   UPDATE royan_patients SET mother_patient_id = NULL, mother_link_basis = NULL
--   WHERE mother_link_basis LIKE 'inferred%';
