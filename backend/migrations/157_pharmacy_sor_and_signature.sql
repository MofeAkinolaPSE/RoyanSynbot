-- Migration 157: Sales-on-Return (SOR) + drug-collection signature capture
--
-- Client asks (Post-deployment-mods/promptplan.md item 23):
--   - "SOR- sales on return" — no existing concept in the schema.
--   - Signature pad tied to the pharmacy patient-history page, confirming
--     drugs were actually collected — royan_dispensing had no field to hold
--     the resulting signature image URL.

ROLLBACK;
BEGIN;

CREATE TABLE IF NOT EXISTS public.royan_sales_returns (
    id                  bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    dispensing_id       bigint      NOT NULL REFERENCES public.royan_dispensing (id) ON DELETE RESTRICT,
    patient_id          bigint      NOT NULL REFERENCES public.royan_patients (id) ON DELETE RESTRICT,
    quantity_returned   numeric     NOT NULL CHECK (quantity_returned > 0),
    reason              text,
    restocked           boolean     NOT NULL DEFAULT false,
    processed_by        text,
    processed_at        timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_royan_sales_returns_dispensing
    ON public.royan_sales_returns (dispensing_id);
CREATE INDEX IF NOT EXISTS idx_royan_sales_returns_patient
    ON public.royan_sales_returns (patient_id);

ALTER TABLE public.royan_dispensing
    ADD COLUMN IF NOT EXISTS signature_url text;

COMMIT;
