-- Migration 153: Per-test structured result templates
--
-- Client ask (Post-deployment-mods/promptplan.md item 19): each lab test
-- should have a defined template of named analytes (e.g. "Serum Bilirubin"
-- expands into "Total Bilirubin" / "Direct Bilirubin", each with its own
-- observed value / unit / normal range / abnormal flag — see
-- hope-page-templates/LAb result page.jpeg). royan_lab_results.result_data
-- was already a flexible jsonb blob (fine, no schema change needed there),
-- but nothing defined *what* analytes a given test_name expects — attendants
-- had no structured entry surface to transcribe Mindray readings into.
--
-- royan_lab_catalog already exists (migration 130) with a single flat
-- reference_range string per test and is governed via the existing MDM
-- change-request workflow (mdm_governance.py) — this migration does not
-- touch it. royan_lab_test_templates is a separate, additive concept: one
-- row per test_name+version, holding the analyte list. catalog_id is a soft
-- link (nullable) since royan_lab_orders.test_name is free text, not FK'd to
-- the catalog.

ROLLBACK;
BEGIN;

CREATE TABLE IF NOT EXISTS public.royan_lab_test_templates (
    id          bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    test_name   text        NOT NULL,
    catalog_id  bigint      REFERENCES public.royan_lab_catalog (id) ON DELETE SET NULL,
    version     int         NOT NULL DEFAULT 1,
    -- analytes: [{"name": "Total Bilirubin", "unit": "mg/dl",
    --             "normal_low": 0, "normal_high": 13.3,
    --             "critical_low": null, "critical_high": null}, ...]
    analytes    jsonb       NOT NULL,
    is_active   boolean     NOT NULL DEFAULT true,
    created_by  text,
    created_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (test_name, version)
);

CREATE INDEX IF NOT EXISTS idx_royan_lab_test_templates_active_name
    ON public.royan_lab_test_templates (test_name)
    WHERE is_active;

-- Ties a recorded result back to the exact template version used at entry
-- time, so a later template edit never silently reinterprets old results.
ALTER TABLE public.royan_lab_results
    ADD COLUMN IF NOT EXISTS template_id bigint REFERENCES public.royan_lab_test_templates (id) ON DELETE SET NULL;

COMMIT;
