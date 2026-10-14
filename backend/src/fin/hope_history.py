"""Load Hope's supplier master and purchase history into Roy Books.

    python -m src.fin.hope_history --staging ../data-assimilation/staging/hope_staging.db [--dry-run]

What it loads (display and lineage only - it never posts and never changes a
balance, the same rule ACE applies to Sage history; Royan's balances come from
its Sage trial balance):

  * suppliers        <- raw_hope_inventory_suppliers (124). One supplier master for
                        Procurement and Roy Books, keyed external_vendor_id = HOPE:<id>.
  * fin_hist_purchase_lines <- raw_hope_purchase_order_items + raw_hope_purchase_orders
                        (~17k goods-received lines, 2016 -> Jan 2026, ~N361m): supplier,
                        PO / GRN, batch, expiry, quantity and unit cost per line.

Each purchase line is tied to its drug through the pharmacy's own batch record
(royan_inventory_batches.external_id = 'po_item:<line id>', written by the Hope
ETL), never by matching names. Lines with no such batch keep their description
and no sku. Re-running replaces nothing it has not seen and duplicates nothing
(upsert on the Hope line id).

The staging database lives on the development machine only; the loaded rows
reach the hospital's server with the database dump, like the Sage transfer.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sqlite3
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Optional

from src.fin import hospital
from src.fin.context import resolve_entity
from src.fin.db import ex, q, q1, tx


def _rows(c: sqlite3.Connection, table: str):
    for (data,) in c.execute(f"SELECT data FROM {table}"):
        yield json.loads(data)


def _dec(v: Any) -> Optional[Decimal]:
    try:
        return Decimal(str(v).replace(",", "")) if v not in (None, "", "None") else None
    except InvalidOperation:
        return None


def _date(v: Any) -> Optional[dt.date]:
    s = str(v or "")[:10]
    if not s or s.startswith("0000"):
        return None
    try:
        return dt.date.fromisoformat(s)
    except ValueError:
        return None


def _clean(v: Any) -> Optional[str]:
    s = str(v).strip() if v is not None else ""
    return s or None


def load_suppliers(conn, c: sqlite3.Connection) -> Dict[str, str]:
    """Hope supplier id -> suppliers.id (created or updated)."""
    out: Dict[str, str] = {}
    for s in _rows(c, "raw_hope_inventory_suppliers"):
        if str(s.get("is_deleted") or "0") == "1" or not _clean(s.get("name")):
            continue
        credit_days = int(s["credit_day"]) if str(s.get("credit_day") or "").isdigit() else None
        row = q1(conn, """
            INSERT INTO suppliers (name, external_vendor_id, phone, contact_email, address, credit_days, payment_terms,
                                   bank_details, status, contact)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'active',%s)
            ON CONFLICT (external_vendor_id) DO UPDATE SET
                name = EXCLUDED.name,
                phone = COALESCE(suppliers.phone, EXCLUDED.phone),
                contact_email = COALESCE(suppliers.contact_email, EXCLUDED.contact_email),
                address = COALESCE(suppliers.address, EXCLUDED.address),
                credit_days = COALESCE(suppliers.credit_days, EXCLUDED.credit_days)
            RETURNING id""",
                 (s["name"].strip(), f"HOPE:{s['id']}", _clean(s.get("mobile")) or _clean(s.get("phone")), _clean(s.get("email")),
                  _clean(s.get("address")), credit_days, f"{credit_days} days" if credit_days else None, _clean(s.get("bank")),
                  json.dumps({"source": "hope", "code": s.get("code")})))
        out[str(s["id"])] = str(row["id"])
    return out


def load_purchase_lines(conn, entity_id: str, c: sqlite3.Connection, suppliers: Dict[str, str]) -> Dict[str, Any]:
    orders = {str(o["id"]): o for o in _rows(c, "raw_hope_purchase_orders") if str(o.get("is_deleted") or "0") != "1"}
    formulary_of = {r["line"]: r["formulary_id"] for r in q(conn, """
        SELECT split_part(external_id, ':', 2) AS line, formulary_id FROM royan_inventory_batches
        WHERE external_id LIKE 'po_item:%%'""")}
    sup_names = {k: q1(conn, "SELECT name FROM suppliers WHERE id=%s", (v,))["name"] for k, v in suppliers.items()}
    sku_of: Dict[int, str] = {}
    loaded = matched = 0
    value = Decimal("0")
    with conn.cursor() as cur:
        for it in _rows(c, "raw_hope_purchase_order_items"):
            po = orders.get(str(it.get("purchase_order_id")))
            if not po:
                continue
            qty_ = _dec(it.get("quantity_received")) or _dec(it.get("quantity_order")) or Decimal("0")
            unit = _dec(it.get("purchase_price")) or Decimal("0")
            amount = _dec(it.get("amount")) or (qty_ * unit)
            if qty_ <= 0 and amount <= 0:
                continue
            fid = formulary_of.get(str(it["id"]))
            sku = None
            if fid:
                if fid not in sku_of:
                    sku_of[fid] = hospital.ensure_product(conn, entity_id, fid)
                sku = sku_of[fid]
                matched += 1
            desc = None
            if fid:
                f = q1(conn, "SELECT generic_name, strength FROM royan_drug_formulary WHERE id=%s", (fid,))
                desc = " ".join(x for x in (f["generic_name"], f["strength"]) if x) if f else None
            sid = str(po.get("supplier_id") or "")
            cur.execute("""
                INSERT INTO fin_hist_purchase_lines (legal_entity_id, source, source_line_id, po_number, grn_number,
                    supplier_invoice, supplier_id, supplier_name, received_date, sku, description, batch_number, expiry_date,
                    quantity, unit_cost, amount)
                VALUES (%s,'HOPE',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (source, source_line_id) DO UPDATE SET sku=EXCLUDED.sku, supplier_id=EXCLUDED.supplier_id,
                    supplier_name=EXCLUDED.supplier_name, description=EXCLUDED.description""",
                (entity_id, str(it["id"]), _clean(po.get("purchase_order_number")), _clean(it.get("grn_no")),
                 _clean(it.get("party_invoice_number")) or _clean(po.get("party_invoice_number")),
                 suppliers.get(sid), sup_names.get(sid), _date(it.get("received_date")) or _date(po.get("order_date")),
                 sku, desc or f"Hope product {it.get('product_id')}", _clean(it.get("batch_number")),
                 None if str(it.get("never_expire")) == "1" else _date(it.get("expiry_date")), qty_, unit, amount))
            loaded += 1
            value += amount
    return {"lines": loaded, "matched_to_drug": matched, "value": str(value.quantize(Decimal("0.01"))), "products": len(sku_of)}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--staging", required=True, help="path to hope_staging.db")
    ap.add_argument("--dry-run", action="store_true", help="load inside a transaction and roll it back")
    args = ap.parse_args()
    c = sqlite3.connect(args.staging)
    with tx() as conn:
        entity = resolve_entity(conn, None)
        sups = load_suppliers(conn, c)
        res = load_purchase_lines(conn, entity, c, sups)
        res["suppliers"] = len(sups)
        ex(conn, """INSERT INTO fin_audit_events (legal_entity_id, actor_id, actor_name, action, entity_type, entity_id, metadata)
                    VALUES (%s,'hope-history','hope-history','HOPE_HISTORY_LOADED','history',%s,%s)""",
           (entity, entity, json.dumps(res)))
        print(json.dumps(res, indent=2))
        if args.dry_run:
            raise SystemExit("dry run - rolled back")


if __name__ == "__main__":
    main()
