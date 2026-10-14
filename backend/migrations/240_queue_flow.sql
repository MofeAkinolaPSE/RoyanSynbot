-- Queue flow as the finance meeting described it (Oct 2026): after the consultation the doctor either ends the visit
-- or asks to see the patient again when the results are back. Only the second sends the patient back for review when
-- the last lab result arrives; otherwise the visit moves on to pharmacy / payment.
ALTER TABLE royan_encounters ADD COLUMN IF NOT EXISTS review_after_results boolean NOT NULL DEFAULT true;
