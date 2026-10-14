-- Migration 214: name Hope's service categories, so revenue can be split by them
-- ============================================================================
--
-- "we should also be able to separate the HMO services so that we know what
-- services went to HMO and at what cost, what services went to private and at
-- what cost."
--
-- royan_billing cannot answer that: hmo_covered is 0 on all 259,072 rows and the
-- per-category columns (lab_charges, ward_charges...) are empty except on the
-- five bills raised natively. The migration never populated them.
--
-- royan_billing_transactions can. Its `payment_category` column holds a mix of
-- labels ("Finalbill", "Approved Discount") and BARE NUMERIC IDs -- 3, 23, 26,
-- 63 -- which are Hope's service_categories.id, the same discriminator found
-- behind tariff_amounts.tariff_list_id in Phase D:
--
--      3  Radiology     411,749,601 across  39,901 transactions
--     26  Laboratory    119,256,960 across  11,256
--     63  CONSULTATION    2,473,000 across     155
--     23  Pharmacy           60,333 across 258,623   <- see note below
--
-- Without this table those rows render as "3" and "26" on a finance report.
--
-- ON PHARMACY LOOKING EMPTY
-- -------------------------
-- Category 23 carries 258,623 transactions worth only 60,333 in total. That is
-- not an error in this migration: Hope recorded dispensing lines here with the
-- money settled on the parent "Finalbill" row instead. Reports must not present
-- that as "pharmacy earned 60,333" -- the endpoint reports transaction COUNT
-- alongside value so the shape is visible rather than misleading.
-- ============================================================================

BEGIN;

CREATE TABLE IF NOT EXISTS public.royan_service_categories (
    id          bigint PRIMARY KEY,          -- Hope's own id, kept as the key
    name        text NOT NULL,
    alias       text,
    service_type text,
    is_active   boolean NOT NULL DEFAULT true,
    created_at  timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE public.royan_service_categories IS
  'Hope service_categories, keyed by Hope id because royan_billing_transactions.payment_category stores that id as bare text.';

INSERT INTO public.royan_service_categories (id, name) VALUES
    (3,  'Radiology'),
    (20, 'Surgery'),
    (23, 'Pharmacy'),
    (26, 'Laboratory'),
    (30, 'Other Services'),
    (39, 'Clinical Services'),
    (40, 'Immunization'),
    (41, 'Mandatory Services'),
    (43, 'Room Tariff'),
    (44, 'Feeding'),
    (45, 'Admission Deposit'),
    (46, 'Patient Registration'),
    (48, 'Blood'),
    (49, 'Family Planning'),
    (50, 'Theatre Fees'),
    (51, 'Anaesthesia'),
    (52, 'Anaesthetic Agent'),
    (53, 'Gynaecology / Obstetrics'),
    (54, 'Paediatrics'),
    (55, 'Hospitalisation (Accommodation & Feeding)'),
    (60, 'Maternity'),
    (61, 'Operation Theatre Charge'),
    (63, 'Consultation'),
    (65, 'Other'),
    (66, 'Physiotherapy'),
    (69, 'Service Group'),
    (70, 'Special Services')
ON CONFLICT (id) DO NOTHING;

-- payment_category is text and holds both ids and labels, so the join is on the
-- text form of the id. Indexed because the finance report groups by it.
CREATE INDEX IF NOT EXISTS idx_billing_tx_category
    ON public.royan_billing_transactions (payment_category);
CREATE INDEX IF NOT EXISTS idx_billing_tx_mode
    ON public.royan_billing_transactions (mode_of_payment);

COMMIT;

-- Verification:
--   SELECT c.name, count(*) AS txns, round(sum(t.amount)::numeric,0) AS value
--   FROM royan_billing_transactions t
--   JOIN royan_service_categories c ON c.id::text = t.payment_category
--   GROUP BY c.name ORDER BY value DESC;
