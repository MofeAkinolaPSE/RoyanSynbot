-- 244: the HMO team checks each service on an HMO patient's visit before the claims form goes out.
-- A patient on an HMO may be given services their plan does not cover (a drug, a test). The HMO officer marks each
-- billed service covered or not covered; a service that is not covered moves from the HMO's share to the patient's,
-- the patient pays for it at the cashier before it is given (stage_billing.clearance), and it leaves the claims form.
-- Every decision is a row in royan_hmo_service_reviews, which is what Roy Books posts (BILL_COVER): a credit note on
-- the HMO's invoice and an invoice to the patient (or the reverse when the HMO later confirms cover).
-- Additive only.
BEGIN;
ALTER TABLE royan_bill_items ADD COLUMN IF NOT EXISTS hmo_decision text
    CHECK (hmo_decision IS NULL OR hmo_decision IN ('covered', 'not_covered'));
ALTER TABLE royan_bill_items ADD COLUMN IF NOT EXISTS hmo_decided_by text;
ALTER TABLE royan_bill_items ADD COLUMN IF NOT EXISTS hmo_decided_at timestamptz;
ALTER TABLE royan_bill_items ADD COLUMN IF NOT EXISTS hmo_decision_note text;
-- A service that is not covered but the patient needs: the doctor, cashier or HMO team asks the HMO provider to
-- approve it. While the request is open the service is held; the HMO team records the provider's answer -
-- approved (with the authorisation code) makes it covered again, declined leaves it for the patient to pay.
ALTER TABLE royan_bill_items ADD COLUMN IF NOT EXISTS hmo_approval_status text
    CHECK (hmo_approval_status IS NULL OR hmo_approval_status IN ('requested', 'approved', 'declined'));
ALTER TABLE royan_bill_items ADD COLUMN IF NOT EXISTS hmo_approval_reason text;
ALTER TABLE royan_bill_items ADD COLUMN IF NOT EXISTS hmo_approval_requested_by text;
ALTER TABLE royan_bill_items ADD COLUMN IF NOT EXISTS hmo_approval_requested_at timestamptz;
ALTER TABLE royan_bill_items ADD COLUMN IF NOT EXISTS hmo_approval_code text;
ALTER TABLE royan_bill_items ADD COLUMN IF NOT EXISTS hmo_approval_decided_by text;
ALTER TABLE royan_bill_items ADD COLUMN IF NOT EXISTS hmo_approval_decided_at timestamptz;
CREATE INDEX IF NOT EXISTS ix_bill_items_hmo_approval ON royan_bill_items (hmo_approval_status) WHERE hmo_approval_status = 'requested';

CREATE TABLE IF NOT EXISTS royan_hmo_service_reviews (
    id            bigserial PRIMARY KEY,
    bill_item_id  bigint NOT NULL REFERENCES royan_bill_items(id),
    billing_id    bigint NOT NULL REFERENCES royan_billing(id),
    encounter_id  bigint,
    decision      text NOT NULL CHECK (decision IN ('covered', 'not_covered')),
    amount        numeric(14,2) NOT NULL DEFAULT 0,   -- moved between the HMO and the patient by this decision
    note          text,
    decided_by    text,
    decided_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_hmo_reviews_item ON royan_hmo_service_reviews (bill_item_id, id DESC);
CREATE INDEX IF NOT EXISTS ix_hmo_reviews_encounter ON royan_hmo_service_reviews (encounter_id);
COMMIT;
