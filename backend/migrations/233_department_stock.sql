-- Department stores other than the pharmacy (finance meeting 10 Oct 2026): the lab, urology and other
-- departments hold stock too. Each batch on a department's shelf, like royan_inventory_batches is for the pharmacy.
-- Loaded first from Hope's stores (Lab, Urology); a stock count in Roy Books confirms it before it is put in the
-- ledger, because Hope's department stock was last maintained in 2021.
CREATE TABLE IF NOT EXISTS royan_department_stock (
    id              bigserial PRIMARY KEY,
    department      text NOT NULL,                 -- LAB | UROLOGY | WARD | THEATRE | ...
    item_code       text,
    item_name       text NOT NULL,
    batch_number    text,
    expiry_date     date,
    quantity        numeric(14,3) NOT NULL DEFAULT 0,
    unit_cost       numeric(14,2),
    sale_price      numeric(14,2),
    reorder_level   numeric(14,3),
    source          text NOT NULL DEFAULT 'MANUAL', -- HOPE | MANUAL | COUNT
    source_ref      text,
    source_updated_at timestamptz,
    updated_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (source, source_ref)
);
CREATE INDEX IF NOT EXISTS ix_royan_department_stock_dept ON royan_department_stock (department);
