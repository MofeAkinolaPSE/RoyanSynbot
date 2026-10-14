"""Load Hope's purchase orders / goods received (2016-2026) into fin_hope_purchases (+ items).

Royan's Sage paid suppliers from the cash book without a purchases journal, so Hope's goods-received records are the
only history of what was bought from which supplier. Idempotent (upserts on Hope's ids).

    python scripts/load_hope_purchases.py [path/to/hope_staging.db]
"""
import json
import os
import sqlite3
import sys

import psycopg2
import psycopg2.extras

STAGING = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    os.path.dirname(__file__), "..", "..", "data-assimilation", "staging", "hope_staging.db")


def num(v):
    try:
        return float(v) if v not in (None, "") else None
    except ValueError:
        return None


def day(v):
    v = (v or "")[:10]
    return v if v and not v.startswith("0000") else None


def main():
    src = sqlite3.connect(STAGING)
    rows = lambda t: [json.loads(r[0]) for r in src.execute(f"SELECT data FROM {t}")]
    suppliers = {s["id"]: s["name"].strip() for s in rows("raw_hope_inventory_suppliers")}
    stores = {s["id"]: s["name"].strip() for s in rows("raw_hope_store_locations")}
    lab_products = {p["id"]: p["name"].strip() for p in rows("raw_hope_products")}
    dsn = os.environ.get("DATABASE_URL", "postgresql://postgres:admin1234@localhost:5433/synbot_health")
    with psycopg2.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("SELECT external_id, COALESCE(brand_name, generic_name) FROM royan_drug_formulary WHERE external_id IS NOT NULL")
        drugs = {str(k): v for k, v in cur.fetchall()}
        cur.execute("SELECT id::text, lower(trim(name)) FROM suppliers")
        ours = {n: i for i, n in cur.fetchall()}
        heads = []
        for p in rows("raw_hope_purchase_orders"):
            if p.get("is_deleted") == "1":
                continue
            name = suppliers.get(p.get("supplier_id"))
            heads.append((int(p["id"]), p.get("purchase_order_number"), p.get("grn_no"), int(p["supplier_id"]) if (p.get("supplier_id") or "").isdigit() else None,
                          name, ours.get((name or "").lower()), p.get("party_invoice_number"), day(p.get("order_date")),
                          day(p.get("received_date")), p.get("status"), stores.get(p.get("order_for")), num(p.get("total")),
                          num(p.get("vat")), num(p.get("discount")), num(p.get("net_amount")) or num(p.get("total"))))
        psycopg2.extras.execute_values(cur, """INSERT INTO fin_hope_purchases (hope_id, po_number, grn_number, supplier_hope_id, supplier_name,
                supplier_id, supplier_invoice, order_date, received_date, status, store, total, vat, discount, net_amount) VALUES %s
                ON CONFLICT (hope_id) DO UPDATE SET supplier_name=EXCLUDED.supplier_name, supplier_id=EXCLUDED.supplier_id,
                supplier_invoice=EXCLUDED.supplier_invoice, received_date=EXCLUDED.received_date, status=EXCLUDED.status,
                total=EXCLUDED.total, net_amount=EXCLUDED.net_amount""", heads, page_size=1000)
        items = []
        for i in rows("raw_hope_purchase_order_items"):
            pid = str(i.get("product_id") or "")
            items.append((int(i["id"]), int(i["purchase_order_id"]), drugs.get(pid) or lab_products.get(pid) or f"Hope item {pid}",
                          i.get("batch_number"), day(i.get("expiry_date")), num(i.get("quantity_received")) or num(i.get("quantity_order")),
                          num(i.get("free")), num(i.get("purchase_price")), num(i.get("amount"))))
        psycopg2.extras.execute_values(cur, """INSERT INTO fin_hope_purchase_items (hope_id, purchase_id, product_name, batch_number,
                expiry_date, quantity, free_quantity, unit_price, amount) VALUES %s ON CONFLICT (hope_id) DO UPDATE SET
                product_name=EXCLUDED.product_name, quantity=EXCLUDED.quantity, amount=EXCLUDED.amount""", items, page_size=2000)
        cur.execute("""SELECT COUNT(*), COUNT(supplier_id), MIN(received_date), MAX(received_date), SUM(net_amount),
                              COUNT(DISTINCT supplier_name) FROM fin_hope_purchases""")
        print("purchases, matched to our suppliers, from, to, value, suppliers:", cur.fetchone())
        cur.execute("SELECT COUNT(*), COUNT(*) FILTER (WHERE product_name LIKE 'Hope item%') FROM fin_hope_purchase_items")
        print("items, unnamed:", cur.fetchone())


if __name__ == "__main__":
    main()
