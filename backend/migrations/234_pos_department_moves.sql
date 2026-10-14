-- POS is how most of Royan's patients pay: its own payment method (it posts like card - to the POS bank account).
ALTER TABLE royan_payments DROP CONSTRAINT IF EXISTS royan_payments_payment_method_check;
ALTER TABLE royan_payments ADD CONSTRAINT royan_payments_payment_method_check
    CHECK (payment_method = ANY (ARRAY['cash','card','pos','transfer','hmo','waiver','other']));

-- Department stores (lab, urology...): every change to a batch is a movement with its reason, so the store has its
-- own ledger. Once finance confirms a department's count it is put in the books (in_books) and from then on every
-- movement posts a journal.
ALTER TABLE royan_department_stock ADD COLUMN IF NOT EXISTS in_books boolean NOT NULL DEFAULT false;
ALTER TABLE royan_department_stock ADD COLUMN IF NOT EXISTS is_active boolean NOT NULL DEFAULT true;
CREATE TABLE IF NOT EXISTS royan_department_stock_moves (
    id            bigserial PRIMARY KEY,
    stock_id      bigint NOT NULL REFERENCES royan_department_stock(id),
    department    text NOT NULL,
    move_type     text NOT NULL CHECK (move_type IN ('RECEIVE','ISSUE','COUNT','EXPIRED','DAMAGED','RETURN_TO_SUPPLIER','CORRECTION','CONFIRM')),
    quantity      numeric(14,3) NOT NULL,        -- signed change
    quantity_after numeric(14,3) NOT NULL,
    unit_cost     numeric(14,2),
    value         numeric(16,2),
    reason        text,
    journal_id    uuid,
    created_by    text,
    created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_dept_stock_moves_stock ON royan_department_stock_moves (stock_id, created_at);
