-- ============================================================================
-- 197 — Populate royan_service_catalog from royan_tariff_catalog
-- ============================================================================
--
-- WHY
-- ---
-- royan_service_catalog shipped with 5 seed rows, every one at base_price = 0.
-- It is the table the HMO Service Catalog tab reads, the table
-- royan_coverage_rules FKs into, and the table services/coverage.py prices a
-- quote from. calculate_coverage() therefore computed every quote against zero:
-- covered amount 0, patient amount 0. The engine was structurally complete and
-- functionally inert, and rules could only be written against those 5 rows.
--
-- Migration 188 loaded 396 real priced services into royan_tariff_catalog and
-- nothing has ever read them.
--
-- THE CATEGORY MAPPING WAS TESTED, NOT ASSUMED
-- --------------------------------------------
-- Hope left service_group NULL on all 396 rows, so the category has to be
-- inferred from the service name alone. The first draft of this mapping put
-- 255 of 396 (64%) into 'misc'. Dry-running it against the real data and
-- iterating produced the version below, which yields:
--
--     procedure 144 · consultation 72 · pharmacy 50 · ward 42
--     lab 38 · imaging 36 · misc 14
--
-- The 14 remaining are genuinely miscellaneous — ambulance, registration
-- charges, medical reports, and a row literally named "Miscellaneous".
--
-- Three bugs the dry run caught, worth recording because they are easy to
-- reintroduce:
--
--   1. Postgres POSIX regex uses backslash-y for a word boundary, NOT the
--      backslash-b familiar from PCRE. Every abbreviation rule written the
--      PCRE way matched nothing whatsoever, silently — MRI, PCV, CTG and
--      E/U/CR all fell through to misc.
--   2. "views?$" matched the tail of "re-VIEW", filing all seven
--      "... RESULT REVIEW" consultations as imaging.
--   3. Ordering: "PROSTATE BIOPSY (ULTRASOUND GUIDED)" is a biopsy, not an
--      ultrasound. Interventional procedures are matched before modalities —
--      the same trap the radiology modality inference hit earlier.
--
-- Note lab has 38 services but only 4 priced: Hope did not carry lab pricing in
-- this tariff table. That is a source-data gap, not a load failure.
--
-- KNOWN LIMITATION, RECORDED DELIBERATELY
-- ---------------------------------------
-- Hope's pricing was PER PAYER (tariff_amounts.tariff_standard_id -> the same
-- tariff_standards loaded as royan_hmos). Migration 188 flattened that to one
-- representative charge, so this backfill gives every HMO the same base price.
-- Per-payer pricing is addressed separately in migration 198.
-- ============================================================================

BEGIN;

INSERT INTO public.royan_service_catalog (service_code, name, category, base_price, is_active)
SELECT
    'TARIFF-' || t.id            AS service_code,
    t.name                       AS name,
    CASE
      -- 1. Authoritative: already present in a catalog we trust.
      WHEN EXISTS (SELECT 1 FROM royan_radiology_catalog c WHERE lower(c.name) = lower(t.name)) THEN 'imaging'
      WHEN EXISTS (SELECT 1 FROM royan_lab_catalog       c WHERE lower(c.name) = lower(t.name)) THEN 'lab'
      WHEN EXISTS (SELECT 1 FROM royan_surgery_catalog   c WHERE lower(c.name) = lower(t.name)) THEN 'procedure'

      -- 2. Dispensed goods: vaccines, blood products, drugs, consumables.
      WHEN lower(t.name) ~ '(vaccine|immunis|immuniz|immunoglobulin|rhogam|anti-?d\y|pneumo ?[0-9]|\yhpv\y|hepatitis [ab]\y)' THEN 'pharmacy'
      WHEN lower(t.name) ~ '(packed red|platelet|fresh frozen|cryoprecip|whole blood)' THEN 'pharmacy'
      WHEN lower(t.name) ~ '(injection|infusion|nebulis|nebuliz|instillation|podophylin|pharmarcy|pharmacy|drug|tablet|capsule|syrup)' THEN 'pharmacy'
      WHEN lower(t.name) ~ '(gown|syringe|glove|dressing|bandage|consumable|silicone|cannula|giving set|brace\y|catheter \(|central line)' THEN 'pharmacy'

      -- 3. Hotel and ward services: a bed, a room, a cot, a meal, a nurse.
      WHEN lower(t.name) ~ '(^cot\y|room ?[0-9]|^room|\yward\y|\ybed\y|admission|accommodat|incubator|stepdown|step down|intensive care|observation|breakfast|lunch|dinner|\ymeal|liquid diet|soft drink|per day|per night|nursing fee)' THEN 'ward'

      -- 3b. Interventional procedures that NAME their guidance modality.
      --     Must precede imaging: "PROSTATE BIOPSY (ULTRASOUND GUIDED)" is a
      --     biopsy, not an ultrasound.
      WHEN lower(t.name) ~ '(biopsy|aspirat|guided|drainage|\yfnac?\y)' THEN 'procedure'

      -- 4. Imaging. Radiographic view notation is as reliable as the modality.
      WHEN lower(t.name) ~ '(x[- ]?ray|xray|ultrasound|sonograph|\yscan\y|-scan|\ymri\y|\yct\y|radiolog|imaging|\yecho|doppler|mammog|barium|fluorosc|\yctg\y|gram\y|ap ?& ?lat|\ypa,|lateral|oblique|\(straight\)|\yviews?$|abdomen for)' THEN 'imaging'

      -- 5. Lab. Nigerian lab shorthand is heavily abbreviated, so the
      --    abbreviations carry more signal than the words.
      WHEN lower(t.name) ~ '(\yfbc\y|\ycbc\y|\yesr\y|\yaptt\y|\ypcv\y|\yinr\y|e/u/cr|\ylft\y|\yrft\y|\ycea\y|\ypsa\y|\ymp\y|\yhvs\y|m/c/s|hba1c|electrolyte|urea|creat|bilirubin|amylase|phosphat|lipid|profile|antigen|antibod|serolog|haemat|hematol|biochem|histopath|histolog|cytolog|culture|\yurine\y|\yblood group|grouping|xmatch|genotype|widal|sugar|glucose|clotting|thrombo|screen|\ytest\y|\ylab\y|analysis|smear|function test|rhesus)' THEN 'lab'

      -- 6. Procedures. Surgical suffixes catch far more than any list of
      --    procedure names could.
      WHEN lower(t.name) ~ '(ectomy|[a-z]tomy|ostomy|plasty|oscopy|scopy|centesis|rrhaphy|pexy|paxy|desis|tripsy|lithopaxy)' THEN 'procedure'
      WHEN lower(t.name) ~ '(surger|operat|theatre|theater|\yot charge|procedure|biopsy|suture|excision|repair|caeser|delivery|episiotom|circumcis|cerclage|ligation|catheteris|drainage|anaesthe|anesthe|laparot|laparat|laparoscop|resection|incision|amputat|graft|implant|insertion|removal|dilatation|curettage|evacuation|transfusion|ventilation|intubat|reduction|aspirat|enema|piercing|placement|irrigation|decompress|lavage|exploration|release|ripening|ectopic|suction|epidural|deroof|\ycpap\y|\ytah\y|\ybso\y)' THEN 'procedure'

      -- 7. Consultation: a clinician's time.
      WHEN lower(t.name) ~ '(consult|follow ?-? ?up|visit|review|reviw|clinic\y|opinion|surgeon|physician|specialist|ologist|opthamolog|ophthalmolog|paediatr|pediatr|gynae|obstetric|dentist|optometr|physiotherap|nutrition|counsel)' THEN 'consultation'

      ELSE 'misc'
    END AS category,
    coalesce(t.charge_amount, 0) AS base_price,
    coalesce(t.is_active, true)  AS is_active
FROM public.royan_tariff_catalog t
WHERE t.name IS NOT NULL
  AND btrim(t.name) <> ''
  -- Do not shadow the hand-seeded rows with a same-named duplicate; those
  -- carry codes other configuration may already reference.
  AND NOT EXISTS (
      SELECT 1 FROM public.royan_service_catalog s
      WHERE lower(s.name) = lower(t.name)
        AND s.service_code NOT LIKE 'TARIFF-%'
  )
ON CONFLICT (service_code) DO UPDATE
SET name       = EXCLUDED.name,
    category   = EXCLUDED.category,
    base_price = EXCLUDED.base_price,
    is_active  = EXCLUDED.is_active,
    updated_at = now();

-- Price the 5 seed rows from a same-named tariff row where one exists;
-- migration 188 ships an index on lower(name) for exactly this.
UPDATE public.royan_service_catalog s
SET base_price = t.charge_amount,
    updated_at = now()
FROM public.royan_tariff_catalog t
WHERE lower(s.name) = lower(t.name)
  AND s.service_code NOT LIKE 'TARIFF-%'
  AND s.base_price = 0
  AND coalesce(t.charge_amount, 0) > 0;


-- ---------------------------------------------------------------------------
-- Re-categorise the rows a previous load filed as 'misc'.
--
-- royan_service_catalog was NOT 5 seed rows as first surveyed: an earlier load
-- had already created 1,215 HOPE-* services. Its drug rows (819) are correctly
-- categorised as pharmacy, but 212 rows landed in 'misc' that plainly are not —
-- "PENTAVALENT VACCINE", "General ward R1", "FULL ELECTROLYTES",
-- "CT SCAN ANKLE JOINT (LEFT)", "PHYSIOTHERAPY ... PER SESSION".
--
-- Only 'misc' is touched. Rows already categorised are left alone: a load that
-- got them right should not be second-guessed by a name-matching heuristic.
-- ---------------------------------------------------------------------------
UPDATE public.royan_service_catalog s
SET category = (CASE
      -- 1. Authoritative: already present in a catalog we trust.
      WHEN EXISTS (SELECT 1 FROM royan_radiology_catalog c WHERE lower(c.name) = lower(s.name)) THEN 'imaging'
      WHEN EXISTS (SELECT 1 FROM royan_lab_catalog       c WHERE lower(c.name) = lower(s.name)) THEN 'lab'
      WHEN EXISTS (SELECT 1 FROM royan_surgery_catalog   c WHERE lower(c.name) = lower(s.name)) THEN 'procedure'

      -- 2. Dispensed goods: vaccines, blood products, drugs, consumables.
      WHEN lower(s.name) ~ '(vaccine|immunis|immuniz|immunoglobulin|rhogam|anti-?d\y|pneumo ?[0-9]|\yhpv\y|hepatitis [ab]\y)' THEN 'pharmacy'
      WHEN lower(s.name) ~ '(packed red|platelet|fresh frozen|cryoprecip|whole blood)' THEN 'pharmacy'
      WHEN lower(s.name) ~ '(injection|infusion|nebulis|nebuliz|instillation|podophylin|pharmarcy|pharmacy|drug|tablet|capsule|syrup)' THEN 'pharmacy'
      WHEN lower(s.name) ~ '(gown|syringe|glove|dressing|bandage|consumable|silicone|cannula|giving set|brace\y|catheter \(|central line)' THEN 'pharmacy'

      -- 3. Hotel and ward services: a bed, a room, a cot, a meal, a nurse.
      WHEN lower(s.name) ~ '(^cot\y|room ?[0-9]|^room|\yward\y|\ybed\y|admission|accommodat|incubator|stepdown|step down|intensive care|observation|breakfast|lunch|dinner|\ymeal|liquid diet|soft drink|per day|per night|nursing fee)' THEN 'ward'

      -- 3b. Interventional procedures that NAME their guidance modality.
      --     Must precede imaging: "PROSTATE BIOPSY (ULTRASOUND GUIDED)" is a
      --     biopsy, not an ultrasound.
      WHEN lower(s.name) ~ '(biopsy|aspirat|guided|drainage|\yfnac?\y)' THEN 'procedure'

      -- 4. Imaging. Radiographic view notation is as reliable as the modality.
      WHEN lower(s.name) ~ '(x[- ]?ray|xray|ultrasound|sonograph|\yscan\y|-scan|\ymri\y|\yct\y|radiolog|imaging|\yecho|doppler|mammog|barium|fluorosc|\yctg\y|gram\y|ap ?& ?lat|\ypa,|lateral|oblique|\(straight\)|\yviews?$|abdomen for)' THEN 'imaging'

      -- 5. Lab. Nigerian lab shorthand is heavily abbreviated, so the
      --    abbreviations carry more signal than the words.
      WHEN lower(s.name) ~ '(\yfbc\y|\ycbc\y|\yesr\y|\yaptt\y|\ypcv\y|\yinr\y|e/u/cr|\ylft\y|\yrft\y|\ycea\y|\ypsa\y|\ymp\y|\yhvs\y|m/c/s|hba1c|electrolyte|urea|creat|bilirubin|amylase|phosphat|lipid|profile|antigen|antibod|serolog|haemat|hematol|biochem|histopath|histolog|cytolog|culture|\yurine\y|\yblood group|grouping|xmatch|genotype|widal|sugar|glucose|clotting|thrombo|screen|\ytest\y|\ylab\y|analysis|smear|function test|rhesus)' THEN 'lab'

      -- 6. Procedures. Surgical suffixes catch far more than any list of
      --    procedure names could.
      WHEN lower(s.name) ~ '(ectomy|[a-z]tomy|ostomy|plasty|oscopy|scopy|centesis|rrhaphy|pexy|paxy|desis|tripsy|lithopaxy)' THEN 'procedure'
      WHEN lower(s.name) ~ '(surger|operat|theatre|theater|\yot charge|procedure|biopsy|suture|excision|repair|caeser|delivery|episiotom|circumcis|cerclage|ligation|catheteris|drainage|anaesthe|anesthe|laparot|laparat|laparoscop|resection|incision|amputat|graft|implant|insertion|removal|dilatation|curettage|evacuation|transfusion|ventilation|intubat|reduction|aspirat|enema|piercing|placement|irrigation|decompress|lavage|exploration|release|ripening|ectopic|suction|epidural|deroof|\ycpap\y|\ytah\y|\ybso\y)' THEN 'procedure'

      -- 7. Consultation: a clinician's time.
      WHEN lower(s.name) ~ '(consult|follow ?-? ?up|visit|review|reviw|clinic\y|opinion|surgeon|physician|specialist|ologist|opthamolog|ophthalmolog|paediatr|pediatr|gynae|obstetric|dentist|optometr|physiotherap|nutrition|counsel)' THEN 'consultation'

      ELSE 'misc'
    END),
    updated_at = now()
WHERE s.category = 'misc'
  AND (CASE
      -- 1. Authoritative: already present in a catalog we trust.
      WHEN EXISTS (SELECT 1 FROM royan_radiology_catalog c WHERE lower(c.name) = lower(s.name)) THEN 'imaging'
      WHEN EXISTS (SELECT 1 FROM royan_lab_catalog       c WHERE lower(c.name) = lower(s.name)) THEN 'lab'
      WHEN EXISTS (SELECT 1 FROM royan_surgery_catalog   c WHERE lower(c.name) = lower(s.name)) THEN 'procedure'

      -- 2. Dispensed goods: vaccines, blood products, drugs, consumables.
      WHEN lower(s.name) ~ '(vaccine|immunis|immuniz|immunoglobulin|rhogam|anti-?d\y|pneumo ?[0-9]|\yhpv\y|hepatitis [ab]\y)' THEN 'pharmacy'
      WHEN lower(s.name) ~ '(packed red|platelet|fresh frozen|cryoprecip|whole blood)' THEN 'pharmacy'
      WHEN lower(s.name) ~ '(injection|infusion|nebulis|nebuliz|instillation|podophylin|pharmarcy|pharmacy|drug|tablet|capsule|syrup)' THEN 'pharmacy'
      WHEN lower(s.name) ~ '(gown|syringe|glove|dressing|bandage|consumable|silicone|cannula|giving set|brace\y|catheter \(|central line)' THEN 'pharmacy'

      -- 3. Hotel and ward services: a bed, a room, a cot, a meal, a nurse.
      WHEN lower(s.name) ~ '(^cot\y|room ?[0-9]|^room|\yward\y|\ybed\y|admission|accommodat|incubator|stepdown|step down|intensive care|observation|breakfast|lunch|dinner|\ymeal|liquid diet|soft drink|per day|per night|nursing fee)' THEN 'ward'

      -- 3b. Interventional procedures that NAME their guidance modality.
      --     Must precede imaging: "PROSTATE BIOPSY (ULTRASOUND GUIDED)" is a
      --     biopsy, not an ultrasound.
      WHEN lower(s.name) ~ '(biopsy|aspirat|guided|drainage|\yfnac?\y)' THEN 'procedure'

      -- 4. Imaging. Radiographic view notation is as reliable as the modality.
      WHEN lower(s.name) ~ '(x[- ]?ray|xray|ultrasound|sonograph|\yscan\y|-scan|\ymri\y|\yct\y|radiolog|imaging|\yecho|doppler|mammog|barium|fluorosc|\yctg\y|gram\y|ap ?& ?lat|\ypa,|lateral|oblique|\(straight\)|\yviews?$|abdomen for)' THEN 'imaging'

      -- 5. Lab. Nigerian lab shorthand is heavily abbreviated, so the
      --    abbreviations carry more signal than the words.
      WHEN lower(s.name) ~ '(\yfbc\y|\ycbc\y|\yesr\y|\yaptt\y|\ypcv\y|\yinr\y|e/u/cr|\ylft\y|\yrft\y|\ycea\y|\ypsa\y|\ymp\y|\yhvs\y|m/c/s|hba1c|electrolyte|urea|creat|bilirubin|amylase|phosphat|lipid|profile|antigen|antibod|serolog|haemat|hematol|biochem|histopath|histolog|cytolog|culture|\yurine\y|\yblood group|grouping|xmatch|genotype|widal|sugar|glucose|clotting|thrombo|screen|\ytest\y|\ylab\y|analysis|smear|function test|rhesus)' THEN 'lab'

      -- 6. Procedures. Surgical suffixes catch far more than any list of
      --    procedure names could.
      WHEN lower(s.name) ~ '(ectomy|[a-z]tomy|ostomy|plasty|oscopy|scopy|centesis|rrhaphy|pexy|paxy|desis|tripsy|lithopaxy)' THEN 'procedure'
      WHEN lower(s.name) ~ '(surger|operat|theatre|theater|\yot charge|procedure|biopsy|suture|excision|repair|caeser|delivery|episiotom|circumcis|cerclage|ligation|catheteris|drainage|anaesthe|anesthe|laparot|laparat|laparoscop|resection|incision|amputat|graft|implant|insertion|removal|dilatation|curettage|evacuation|transfusion|ventilation|intubat|reduction|aspirat|enema|piercing|placement|irrigation|decompress|lavage|exploration|release|ripening|ectopic|suction|epidural|deroof|\ycpap\y|\ytah\y|\ybso\y)' THEN 'procedure'

      -- 7. Consultation: a clinician's time.
      WHEN lower(s.name) ~ '(consult|follow ?-? ?up|visit|review|reviw|clinic\y|opinion|surgeon|physician|specialist|ologist|opthamolog|ophthalmolog|paediatr|pediatr|gynae|obstetric|dentist|optometr|physiotherap|nutrition|counsel)' THEN 'consultation'

      ELSE 'misc'
    END) <> 'misc';

COMMIT;

-- Verification:
--   SELECT category, count(*), count(*) FILTER (WHERE base_price > 0) AS priced
--   FROM royan_service_catalog GROUP BY category ORDER BY 2 DESC;
