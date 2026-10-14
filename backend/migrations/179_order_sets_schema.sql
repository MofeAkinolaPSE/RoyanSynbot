-- 179_order_sets_schema.sql
-- Real "treatment templates" -- Hope has a genuine Order Set subsystem
-- (orderset_masters + order_subcategories, ~32 clinically real templates
-- with structured drug/lab/radiology line items) that was never migrated.
-- royan_clinic_templates.default_order_sets (migration 169) is a bare
-- text[] of decorative labels with no dosage/route/frequency/qty structure
-- and no external_source/external_id -- doesn't fit either Hope's real data
-- or this pipeline's idempotent-upsert convention, so this is a new
-- dedicated schema rather than force-fitting into that column.
--
-- Column names on royan_order_set_items deliberately mirror
-- royan_prescriptions (105_prescriptions.sql) where the item is a
-- medication, so "apply this order set" can become a straightforward
-- per-item insert into royan_prescriptions / royan_lab_orders /
-- royan_radiology_orders later, keyed by item_type.

ROLLBACK;
BEGIN;

CREATE TABLE IF NOT EXISTS public.royan_order_sets (
    id                  bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name                text        NOT NULL,
    description         text,
    created_by          uuid        REFERENCES public.royan_staff(id) ON DELETE SET NULL,
    is_shared           boolean     NOT NULL DEFAULT true,
    department          text,
    specialty           text,
    is_active           boolean     NOT NULL DEFAULT true,
    external_source     text,
    external_id         text,
    external_updated_at timestamptz,
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_royan_order_sets_external
    ON public.royan_order_sets (external_source, external_id)
    WHERE external_source IS NOT NULL AND external_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_royan_order_sets_name ON public.royan_order_sets (lower(name));
CREATE INDEX IF NOT EXISTS idx_royan_order_sets_active ON public.royan_order_sets (is_active) WHERE is_active = true;

CREATE TABLE IF NOT EXISTS public.royan_order_set_items (
    id                   bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_set_id         bigint      NOT NULL REFERENCES public.royan_order_sets(id) ON DELETE CASCADE,
    item_type            text        NOT NULL CHECK (item_type = ANY (ARRAY[
                              'medication','lab','radiology','procedure','diet',
                              'activity','patient_care','vital_signs','iv_solution',
                              'communication','intake_output','allergy','other'
                          ])),
    name                 text        NOT NULL,       -- drug/test/procedure name
    dosage               text,
    strength             text,
    dose_form            text,
    route                text,
    frequency            text,
    duration             text,
    quantity             numeric,
    prn                  boolean     NOT NULL DEFAULT false,
    dispense             boolean     NOT NULL DEFAULT false,
    instruction          text,       -- Hope's order_sentence / free-text instruction
    sort_order           int         NOT NULL DEFAULT 0,
    external_source      text,
    external_id          text,
    created_at           timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_royan_order_set_items_external
    ON public.royan_order_set_items (external_source, external_id)
    WHERE external_source IS NOT NULL AND external_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_royan_order_set_items_set ON public.royan_order_set_items (order_set_id, sort_order);

COMMIT;
