-- Migration 216: give on-hand stock a real batch number and an expiry date
-- ============================================================================
--
-- "why don't we have expiring dates? ... lets focus on exposing what we have on
-- hand and all the information along with it. Then we save the expired
-- information as historical data."
--
-- WHY THERE WERE NO EXPIRY DATES
-- ------------------------------
-- Every one of the 536 batches holding stock was named HOPE-INITIAL: a
-- synthetic opening-balance row the migration created from
-- pharmacy_items.stock, which is a running total rather than a batch. Hope's
-- pharmacy_items.expiry_date is empty on every row, so that figure never had an
-- expiry to carry.
--
-- Meanwhile the 16,466 REAL batches all had expiry dates and zero stock: they
-- are the consumed and expired history.
--
-- So the inventory showed 50.7m of stock with no expiry, and 15,157 expired
-- batches with nothing in them. Both halves were accurate and neither was
-- useful.
--
-- WHERE THE MISSING DATES CAME FROM
-- ---------------------------------
-- royan_pharmacy_item_rates (loaded in Phase A for pricing) also carries
-- per-batch stock and expiry. 238 drugs have a rate row with stock AND an
-- unexpired date, and for 222 of them that row's quantity matches the opening
-- balance exactly — meaning one batch accounts for all the stock. Those are
-- upgraded in place: same quantity, now with the real batch number and expiry.
--
-- THE 16 LEFT ALONE, AND WHY
-- --------------------------
-- The other 16 are multi-batch drugs — Atenolol 50mg has 7 batches holding
-- stock, Calcium Gluconate 3 — so no single batch's expiry applies to the whole
-- quantity. Stamping one batch's date on the lot would invent an expiry the
-- data does not support, which is worse than having none. They stay as opening
-- balances until someone counts the shelf.
--
-- Nothing is deleted here. Expired batches remain for reference; the API stops
-- listing them by default (see the endpoint change alongside this migration).
-- ============================================================================

BEGIN;

WITH best AS (
    -- The furthest-dated unexpired batch per drug: if stock is being held, it
    -- is the one that will still be usable.
    SELECT DISTINCT ON (formulary_id)
           formulary_id, batch_number, stock, expiry_date,
           COALESCE(NULLIF(cost_price, 0), NULLIF(purchase_price, 0)) AS cost
    FROM public.royan_pharmacy_item_rates
    WHERE COALESCE(stock, 0) > 0
      AND expiry_date >= CURRENT_DATE
      AND formulary_id IS NOT NULL
    ORDER BY formulary_id, expiry_date DESC
)
UPDATE public.royan_inventory_batches b
SET batch_number = best.batch_number,
    expiry_date  = best.expiry_date,
    -- Only fill a cost that is currently absent: the inventory figure may have
    -- been corrected by hand since the migration.
    unit_cost    = COALESCE(NULLIF(b.unit_cost, 0), best.cost, b.unit_cost),
    notes        = COALESCE(b.notes, '') ||
                   CASE WHEN COALESCE(b.notes, '') = '' THEN '' ELSE ' | ' END ||
                   'Batch and expiry recovered from pharmacy_item_rates (migration 216)',
    updated_at   = now()
FROM best
WHERE b.formulary_id = best.formulary_id
  AND b.batch_number = 'HOPE-INITIAL'
  -- Exact match only. A difference means several batches hold this drug, and
  -- one batch's expiry cannot speak for all of them.
  AND b.quantity_on_hand = best.stock;

COMMIT;

-- Verification:
--   SELECT batch_number = 'HOPE-INITIAL' AS still_synthetic,
--          count(*), count(expiry_date) AS have_expiry
--   FROM royan_inventory_batches WHERE quantity_on_hand > 0 GROUP BY 1;
--   -- expect ~222 real batches with expiry, ~314 still opening balances
