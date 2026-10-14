-- Hope's purchase history (purchase orders / goods received, 2016-2026): what was bought from whom, on which supplier
-- invoice. Royan's Sage paid suppliers straight from the cash book (no purchases journal), so this is the only record
-- of purchases by supplier before go-live. History for Purchases and the supplier ledgers - not posted to the books.
CREATE TABLE IF NOT EXISTS fin_hope_purchases (
    hope_id          bigint PRIMARY KEY,
    po_number        text,
    grn_number       text,
    supplier_hope_id bigint,
    supplier_name    text,
    supplier_id      uuid,                  -- the matching supplier in suppliers, when the name matches
    supplier_invoice text,
    order_date       date,
    received_date    date,
    status           text,
    store            text,
    total            numeric(16,2),
    vat              numeric(16,2),
    discount         numeric(16,2),
    net_amount       numeric(16,2)
);
CREATE INDEX IF NOT EXISTS ix_fin_hope_purchases_date ON fin_hope_purchases (received_date);
CREATE INDEX IF NOT EXISTS ix_fin_hope_purchases_supplier ON fin_hope_purchases (supplier_name);
CREATE TABLE IF NOT EXISTS fin_hope_purchase_items (
    hope_id        bigint PRIMARY KEY,
    purchase_id    bigint NOT NULL,
    product_name   text,
    batch_number   text,
    expiry_date    date,
    quantity       numeric(14,3),
    free_quantity  numeric(14,3),
    unit_price     numeric(14,2),
    amount         numeric(16,2)
);
CREATE INDEX IF NOT EXISTS ix_fin_hope_purchase_items_po ON fin_hope_purchase_items (purchase_id);
