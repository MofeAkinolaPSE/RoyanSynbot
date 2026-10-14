"""Load Hope's department stores (Lab, Urology) into royan_department_stock.

Hope kept consumables for some departments in their own stores: raw_hope_products (one row per item, with its
store_location_id) and raw_hope_product_rates (one row per batch: stock, purchase price, expiry). The pharmacy's
stock is already in royan_inventory_batches; this brings the other departments' shelves alongside it so Roy Books'
Stock page can show stock by department. Idempotent: re-running updates the same batches (source='HOPE').

    python scripts/load_hope_department_stock.py [path/to/hope_staging.db]
"""
import json
import os
import sqlite3
import sys

import psycopg2

STAGING = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    os.path.dirname(__file__), "..", "..", "data-assimilation", "staging", "hope_staging.db")
DEPARTMENTS = {"lab": "LAB", "urology": "UROLOGY", "ward": "WARD", "ot": "THEATRE", "physiotherapy": "PHYSIOTHERAPY",
               "central stores": "CENTRAL_STORES"}


def num(v):
    try:
        return float(v) if v not in (None, "") else None
    except ValueError:
        return None


def day(v):
    return v if v and not v.startswith("0000") else None


def main():
    src = sqlite3.connect(STAGING)
    rows = lambda t: [json.loads(r[0]) for r in src.execute(f"SELECT data FROM {t}")]
    stores = {s["id"]: s["name"].strip() for s in rows("raw_hope_store_locations")}
    products = {p["id"]: p for p in rows("raw_hope_products") if p.get("is_deleted") != "1"}
    out = []
    for r in rows("raw_hope_product_rates"):
        p = products.get(r["product_id"])
        if not p or r.get("is_deleted") == "1":
            continue
        dept = DEPARTMENTS.get(stores.get(p.get("store_location_id"), "").lower())
        if not dept or (num(r.get("stock")) or 0) <= 0:
            continue
        out.append((dept, p.get("product_code") or None, p["name"].strip(), r.get("batch_number") or None, day(r.get("expiry_date")),
                    num(r["stock"]), num(r.get("purchase_price")) or num(r.get("cost_price")), num(r.get("sale_price")) or num(r.get("mrp")),
                    num(p.get("reorder_level")) or None, f"rate:{r['id']}", p.get("modified_time") or day((p.get("create_time") or "")[:10])))
    dsn = os.environ.get("DATABASE_URL", "postgresql://postgres:admin1234@localhost:5433/synbot_health")
    with psycopg2.connect(dsn) as conn, conn.cursor() as cur:
        for o in out:
            cur.execute("""INSERT INTO royan_department_stock (department, item_code, item_name, batch_number, expiry_date, quantity,
                               unit_cost, sale_price, reorder_level, source, source_ref, source_updated_at)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'HOPE',%s,%s)
                           ON CONFLICT (source, source_ref) DO UPDATE SET department=EXCLUDED.department, item_name=EXCLUDED.item_name,
                               batch_number=EXCLUDED.batch_number, expiry_date=EXCLUDED.expiry_date, quantity=EXCLUDED.quantity,
                               unit_cost=EXCLUDED.unit_cost, sale_price=EXCLUDED.sale_price, updated_at=now()""", o)
        cur.execute("""SELECT department, COUNT(*), SUM(quantity*COALESCE(unit_cost,0)), COUNT(*) FILTER (WHERE expiry_date < current_date)
                       FROM royan_department_stock GROUP BY 1 ORDER BY 1""")
        for d in cur.fetchall():
            print(f"{d[0]}: {d[1]} batches, value {float(d[2] or 0):,.2f}, expired batches {d[3]}")


if __name__ == "__main__":
    main()
