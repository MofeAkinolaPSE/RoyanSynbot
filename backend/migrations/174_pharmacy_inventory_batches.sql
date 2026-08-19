-- 174_pharmacy_inventory_batches.sql
-- Pharmacy Inventory workspace rebuild. royan_drug_formulary (already built,
-- never activated — zero rows) becomes the real drug/vaccine/consumable
-- catalog going forward. royan_inventory_batches adds proper lot/batch/
-- expiry-level stock, something royan_drug_inventory's one-row-per-drug
-- shape can never represent (two concurrently-in-stock batches at different
-- expiries need two rows here, one card in the UI). royan_drug_inventory is
-- left in place, unused/superseded ("legacy") — nothing here drops it, and
-- it also has zero rows, so there is nothing to migrate either way.
--
-- Also lays ETL-readiness groundwork (external_source/external_id + nullable
-- prescription_id on royan_dispensing) for the still-deferred DRM Hope
-- dispensing/inventory backfill pass, whose real source data is
-- bill-line-item shaped with no prescription concept — mirrors the pattern
-- already used for royan_payments/royan_insurance_claims in migration 172.

ROLLBACK;
BEGIN;

-- ── Catalog readiness: category + reorder-math overrides per drug ────────
ALTER TABLE royan_drug_formulary
    ADD COLUMN IF NOT EXISTS category           text,
    ADD COLUMN IF NOT EXISTS lead_time_days      integer,
    ADD COLUMN IF NOT EXISTS safety_stock_days   integer,
    ADD COLUMN IF NOT EXISTS reorder_level       numeric;

ALTER TABLE royan_drug_formulary DROP CONSTRAINT IF EXISTS royan_drug_formulary_category_check;
ALTER TABLE royan_drug_formulary ADD CONSTRAINT royan_drug_formulary_category_check
    CHECK (category IS NULL OR category = ANY (ARRAY['drug','vaccine','consumable','other']));

-- ── New batch/lot-level stock table ───────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.royan_inventory_batches (
    id                   bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    formulary_id         bigint      NOT NULL REFERENCES public.royan_drug_formulary (id) ON DELETE RESTRICT,
    batch_number         text        NOT NULL,
    quantity_on_hand     numeric     NOT NULL DEFAULT 0,
    quantity_received    numeric     NOT NULL DEFAULT 0,
    unit_cost            numeric     NOT NULL DEFAULT 0,
    supplier             text,
    location              text,
    received_at          date        NOT NULL DEFAULT CURRENT_DATE,
    expiry_date          date,
    notes                text,
    created_by           text,
    external_source      text,
    external_id          text,
    external_updated_at  timestamptz,
    created_at           timestamptz NOT NULL DEFAULT now(),
    updated_at           timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT royan_inventory_batches_qty_on_hand_check CHECK (quantity_on_hand >= 0),
    CONSTRAINT royan_inventory_batches_qty_received_check CHECK (quantity_received >= 0),
    CONSTRAINT royan_inventory_batches_unit_cost_check CHECK (unit_cost >= 0)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_inventory_batches_formulary_batch
    ON public.royan_inventory_batches (formulary_id, lower(batch_number));
ALTER TABLE royan_inventory_batches DROP CONSTRAINT IF EXISTS royan_inventory_batches_external_source_external_id_key;
ALTER TABLE royan_inventory_batches ADD CONSTRAINT royan_inventory_batches_external_source_external_id_key
    UNIQUE (external_source, external_id);

CREATE INDEX IF NOT EXISTS idx_inventory_batches_formulary ON public.royan_inventory_batches (formulary_id);
CREATE INDEX IF NOT EXISTS idx_inventory_batches_expiry    ON public.royan_inventory_batches (expiry_date);
CREATE INDEX IF NOT EXISTS idx_inventory_batches_live      ON public.royan_inventory_batches (formulary_id, expiry_date) WHERE quantity_on_hand > 0;

-- ── Dispensing: exact FK for future joins + ETL readiness ────────────────
-- prescription_id goes nullable so a future bulk loader can insert real
-- historical dispensing events that were never tied to a live prescription
-- (per the "bill-line-item shaped, no prescription concept" Hope finding).
ALTER TABLE royan_dispensing ALTER COLUMN prescription_id DROP NOT NULL;
ALTER TABLE royan_dispensing
    ADD COLUMN IF NOT EXISTS formulary_id          bigint REFERENCES royan_drug_formulary(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS batch_id              bigint REFERENCES royan_inventory_batches(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS external_source       text,
    ADD COLUMN IF NOT EXISTS external_id            text,
    ADD COLUMN IF NOT EXISTS external_updated_at    timestamptz;

ALTER TABLE royan_dispensing DROP CONSTRAINT IF EXISTS royan_dispensing_external_source_external_id_key;
ALTER TABLE royan_dispensing ADD CONSTRAINT royan_dispensing_external_source_external_id_key
    UNIQUE (external_source, external_id);

CREATE INDEX IF NOT EXISTS idx_royan_dispensing_formulary ON public.royan_dispensing (formulary_id);

-- ── Replenishment requests: real columns instead of the notes-folding ────
-- workaround the router's own code comment already admits to.
ALTER TABLE royan_replenishment_requests
    ADD COLUMN IF NOT EXISTS formulary_id           bigint REFERENCES royan_drug_formulary(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS ward                   text,
    ADD COLUMN IF NOT EXISTS urgency                text,
    ADD COLUMN IF NOT EXISTS unit                   text,
    ADD COLUMN IF NOT EXISTS risk_tier_at_request    text,
    ADD COLUMN IF NOT EXISTS auto_generated         boolean NOT NULL DEFAULT false;

ALTER TABLE royan_replenishment_requests DROP CONSTRAINT IF EXISTS royan_replenishment_requests_urgency_check;
ALTER TABLE royan_replenishment_requests ADD CONSTRAINT royan_replenishment_requests_urgency_check
    CHECK (urgency IS NULL OR urgency = ANY (ARRAY['routine','urgent','stat']));

COMMIT;
