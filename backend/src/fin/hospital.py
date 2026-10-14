"""Royan-specific masters for Roy Books: products from the pharmacy formulary,
batches linked to the pharmacy's live batches, and the opening pharmacy stock.

One master per fact (ACE-Books.md s4): the formulary stays the drug master and
royan_inventory_batches stays the live shelf. Roy Books keeps the VALUED side
(FIFO cost layers, journals) and links to both by id, never by copying names.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any, Dict, Optional

from src.fin import audit, inventory
from src.fin.db import ex, money, q, q1
from src.fin.errors import FinError, invalid, not_found


def _product_name(f: Dict[str, Any]) -> str:
    parts = [f.get("generic_name") or f.get("brand_name") or f["code"]]
    if f.get("strength"):
        parts.append(str(f["strength"]))
    if f.get("brand_name") and f.get("generic_name") and f["brand_name"] != f["generic_name"]:
        parts.append(f"({f['brand_name']})")
    return " ".join(parts)[:200]


def ensure_product(conn, entity_id: str, formulary_id: Any) -> str:
    """The Roy Books product (sku) for a formulary item, created on first use."""
    fid = int(formulary_id)
    p = q1(conn, "SELECT sku FROM fin_products WHERE legal_entity_id=%s AND formulary_id=%s", (entity_id, fid))
    if p:
        return p["sku"]
    f = q1(conn, "SELECT * FROM royan_drug_formulary WHERE id=%s", (fid,))
    if not f:
        raise not_found("Formulary item", fid)
    sku = str(f["code"]).strip()
    same = q1(conn, "SELECT id, formulary_id FROM fin_products WHERE legal_entity_id=%s AND sku=%s", (entity_id, sku))
    if same and same["formulary_id"] is None:
        ex(conn, "UPDATE fin_products SET formulary_id=%s WHERE id=%s", (fid, same["id"]))
        return sku
    if same:  # the code is taken by another formulary item: keep both, distinguish this one
        sku = f"{sku}-{fid}"
    ex(conn, """INSERT INTO fin_products (legal_entity_id, sku, name, product_type, uom, reorder_level, legacy_class,
                status, formulary_id) VALUES (%s,%s,%s,'INVENTORY',%s,%s,%s,%s,%s)
                ON CONFLICT (legal_entity_id, sku) DO NOTHING""",
       (entity_id, sku, _product_name(f), f.get("unit") or "Each", f.get("reorder_level"), f.get("category") or f.get("drug_class"),
        "ACTIVE" if f.get("is_active", True) else "INACTIVE", fid))
    return sku


def sync_products(conn, ctx) -> Dict[str, Any]:
    """Every formulary item becomes (or updates) a Roy Books product."""
    ctx.require("migration.load")
    created = updated = 0
    for f in q(conn, "SELECT id FROM royan_drug_formulary ORDER BY id"):
        had = q1(conn, "SELECT 1 FROM fin_products WHERE legal_entity_id=%s AND formulary_id=%s", (ctx.entity_id, f["id"]))
        ensure_product(conn, ctx.entity_id, f["id"])
        if had:
            updated += 1
        else:
            created += 1
    ex(conn, """UPDATE fin_products p SET name = sub.name, status = sub.status FROM (
                    SELECT f.id, trim(concat_ws(' ', COALESCE(f.generic_name, f.brand_name), f.strength)) AS name,
                           CASE WHEN f.is_active THEN 'ACTIVE' ELSE 'INACTIVE' END AS status
                    FROM royan_drug_formulary f) sub
                WHERE p.legal_entity_id=%s AND p.formulary_id = sub.id""", (ctx.entity_id,))
    audit.record(conn, ctx, "PRODUCTS_SYNCED", "products", ctx.entity_id, metadata={"created": created, "existing": updated})
    return {"created": created, "existing": updated}


def fin_batch_for_ops(conn, entity_id: str, sku: str, ops_batch_id: Any, batch_number: Optional[str],
                      expiry_date: Any = None) -> Optional[str]:
    """The Roy Books batch that mirrors a pharmacy batch (created and linked on first use)."""
    if ops_batch_id:
        b = q1(conn, "SELECT id FROM fin_batches WHERE legal_entity_id=%s AND ops_batch_id=%s", (entity_id, int(ops_batch_id)))
        if b:
            return str(b["id"])
        ob = q1(conn, "SELECT batch_number, expiry_date FROM royan_inventory_batches WHERE id=%s", (int(ops_batch_id),))
        if ob:
            batch_number = batch_number or ob["batch_number"]
            expiry_date = expiry_date or ob["expiry_date"]
    if not batch_number:
        return None
    exp = expiry_date if isinstance(expiry_date, dt.date) or expiry_date is None else _date(expiry_date)
    bid = inventory.ensure_batch(conn, entity_id, sku, str(batch_number), expiry_date=exp)
    if ops_batch_id:
        ex(conn, "UPDATE fin_batches SET ops_batch_id=%s WHERE id=%s AND ops_batch_id IS NULL", (int(ops_batch_id), bid))
    return bid


def _date(v: Any) -> Optional[dt.date]:
    try:
        return dt.date.fromisoformat(str(v)[:10])
    except (TypeError, ValueError):
        return None


def load_pharmacy_opening_stock(conn, ctx, as_of: dt.date) -> Dict[str, Any]:
    """Value what is on the pharmacy's shelves at cut-over as the books' opening stock.

    Each live batch with stock and a unit cost opens a FIFO layer at that cost,
    in its own batch (expiry kept), so FEFO, recalls and expiry write-offs work
    from day one. Like the Sage transfer, opening stock is SUBLEDGER detail
    behind the trial balance: no journal is posted here. Until Royan's Sage
    trial balance is loaded, Close & Controls will show the inventory GL below
    the valued stock - that difference is the missing opening balance, not an
    error in the stock.
    """
    ctx.require("migration.load")
    if q1(conn, "SELECT 1 FROM fin_inventory_transactions WHERE legal_entity_id=%s AND source_type='PHARMACY_OPENING' LIMIT 1",
          (ctx.entity_id,)):
        raise FinError("DUPLICATE_RESOURCE", "Opening pharmacy stock is already loaded")
    loaded, value, skipped_no_cost = 0, Decimal("0"), []
    for b in q(conn, """SELECT id, formulary_id, batch_number, quantity_on_hand, unit_cost, expiry_date
                        FROM royan_inventory_batches WHERE quantity_on_hand > 0 ORDER BY formulary_id, expiry_date NULLS LAST, id"""):
        if not b["unit_cost"] or Decimal(str(b["unit_cost"])) <= 0:
            skipped_no_cost.append(b["id"])
            continue
        sku = ensure_product(conn, ctx.entity_id, b["formulary_id"])
        bid = fin_batch_for_ops(conn, ctx.entity_id, sku, b["id"], b["batch_number"], b["expiry_date"])
        t = inventory.receive(conn, ctx, sku=sku, quantity=b["quantity_on_hand"], unit_cost=b["unit_cost"],
                              txn_type="OPENING_BALANCE", txn_date=as_of, batch_id=bid, source_type="PHARMACY_OPENING",
                              source_id=str(b["id"]), reference="PHARMACY-OPENING",
                              reason="Opening stock from the pharmacy's live batches", mirror=False)
        loaded += 1
        value += money(t["total_cost"])
    # Batches already past expiry are frozen as EXPIRED so they cannot be dispensed or sold from the books.
    ex(conn, """UPDATE fin_batches SET status='EXPIRED' WHERE legal_entity_id=%s AND status='AVAILABLE'
                AND expiry_date < %s AND ops_batch_id IS NOT NULL""", (ctx.entity_id, as_of))
    audit.record(conn, ctx, "PHARMACY_OPENING_STOCK_LOADED", "inventory", ctx.entity_id,
                 metadata={"batches": loaded, "value": str(value), "as_of": str(as_of), "skipped_no_cost": len(skipped_no_cost)})
    return {"batches": loaded, "value": str(money(value)), "as_of": as_of, "skipped_no_cost": len(skipped_no_cost)}


def party_search(conn, search: str, limit: int = 20):
    """Patients (by name / MRN), HMOs and other debtors - whether or not they owe anything yet.

    A patient or HMO without an AR account is returned with `id` NULL and a
    `patient_id` / `hmo_id`; the forms call /parties/ensure before using it.
    """
    s = f"%{search.strip()}%"
    rows = q(conn, """SELECT id, party_type, name, customer_code, mrn, patient_id, hmo_id, credit_limit, payment_terms_days
                      FROM fin_v_customers WHERE name ILIKE %s OR customer_code ILIKE %s OR mrn ILIKE %s
                      ORDER BY (party_type='PATIENT'), name LIMIT %s""", (s, s, s, limit))
    have_p = {r["patient_id"] for r in rows if r["patient_id"]}
    have_h = {r["hmo_id"] for r in rows if r["hmo_id"]}
    more = limit - len(rows)
    if more > 0 and len(search.strip()) >= 2:
        for h in q(conn, """SELECT id, name, code FROM royan_hmos WHERE is_active AND (name ILIKE %s OR code ILIKE %s)
                            ORDER BY name LIMIT %s""", (s, s, more)):
            if h["id"] not in have_h:
                rows.append({"id": None, "party_type": "HMO", "name": h["name"], "customer_code": h["code"], "mrn": None,
                             "patient_id": None, "hmo_id": h["id"], "credit_limit": 0, "payment_terms_days": 60})
        for p in q(conn, """SELECT id, trim(concat_ws(' ', first_name, last_name)) AS name, mrn FROM royan_patients
                            WHERE mrn ILIKE %s OR (first_name || ' ' || last_name) ILIKE %s ORDER BY last_name LIMIT %s""",
                   (s, s, max(more, 10))):
            if p["id"] not in have_p:
                rows.append({"id": None, "party_type": "PATIENT", "name": p["name"], "customer_code": p["mrn"], "mrn": p["mrn"],
                             "patient_id": p["id"], "hmo_id": None, "credit_limit": 0, "payment_terms_days": 0})
    return rows[:limit]


def ensure_party(conn, ctx, data: Dict[str, Any]) -> Dict[str, Any]:
    from src.fin import sales
    if data.get("patient_id"):
        cid = sales.ensure_patient_customer(conn, data["patient_id"], ctx.actor_id)
    elif data.get("hmo_id"):
        cid = sales.ensure_hmo_customer(conn, data["hmo_id"], ctx.actor_id)
    elif (data.get("name") or "").strip():
        ctx.require("receivables.receipt.create")
        kind = str(data.get("party_type") or "CORPORATE").upper()
        if kind not in ("CORPORATE", "OTHER"):
            raise invalid("A new finance-only debtor is CORPORATE or OTHER; patients and HMOs come from their registers")
        row = q1(conn, """INSERT INTO fin_customers (party_type, name, customer_code, credit_limit, payment_terms_days, created_by)
                          VALUES (%s,%s,%s,%s,%s,%s) RETURNING id""",
                 (kind, data["name"].strip(), data.get("customer_code") or None, data.get("credit_limit") or 0,
                  data.get("payment_terms_days") or 30, ctx.actor_id))
        cid = row["id"]
        audit.record(conn, ctx, "DEBTOR_CREATED", "customer", cid, ref=data["name"].strip())
    else:
        raise invalid("Choose a patient, an HMO or name a corporate debtor")
    return sales.customer(conn, cid)


def update_party_terms(conn, ctx, customer_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
    """Credit limit and payment terms are finance-owned (e.g. an HMO's contract terms)."""
    from src.fin import sales
    ctx.require("sales.credit.override") if "credit_limit" in data else ctx.require("receivables.receipt.create")
    before = sales.customer(conn, customer_id)
    fields = {k: data[k] for k in ("credit_limit", "payment_terms_days", "status", "notes") if k in data}
    if not fields:
        return before
    sets = ", ".join(f"{k}=%s" for k in fields)
    ex(conn, f"UPDATE fin_customers SET {sets} WHERE id=%s", list(fields.values()) + [int(customer_id)])
    audit.record(conn, ctx, "DEBTOR_TERMS_UPDATED", "customer", customer_id, ref=before["name"],
                 before={k: before.get(k) for k in fields}, after=fields)
    return sales.customer(conn, customer_id)


# ---------------------------------------------------------------------------
# HMO claims follow the HMO's invoice
# ---------------------------------------------------------------------------

def sync_hmo_claim(conn, invoice_id: Any) -> Optional[Dict[str, Any]]:
    """Keep the hospital's claim record (royan_insurance_claims) in step with the HMO share's invoice in the books.

    The HMO share of a bill is an invoice to the HMO (source BILLING_HMO). When the HMO pays it - or Finance credits
    part of it as disallowed - the claim for that bill moves: paid in full -> 'paid' (settled on the last payment),
    part paid or part disallowed -> 'approved' with the accepted amount, wholly disallowed -> 'rejected'. A payment
    that is later voided puts the claim back to 'submitted'. If the cashier never pressed "submit claim", the claim is
    recorded here so the claims register is complete. Called whenever an invoice's settlement changes."""
    inv = q1(conn, """SELECT id, invoice_number, customer_id, total, status, source_type, source_id
                      FROM fin_sales_invoices WHERE id=%s""", (invoice_id,))
    if not inv or inv["source_type"] != "BILLING_HMO" or not str(inv["source_id"] or "").isdigit():
        return None
    bill = q1(conn, "SELECT id, patient_id, hmo_id FROM royan_billing WHERE id=%s", (int(inv["source_id"]),))
    if not bill:
        return None
    alloc = {r["source_type"]: r for r in q(conn, """SELECT source_type, SUM(amount) AS amount, MAX(allocation_date) AS last
                                                    FROM fin_ar_allocations WHERE invoice_id=%s AND NOT reversed
                                                    GROUP BY source_type""", (inv["id"],))}
    paid = money((alloc.get("RECEIPT") or {}).get("amount"))
    credited = money((alloc.get("CREDIT_NOTE") or {}).get("amount"))
    total = money(inv["total"])
    open_ = total - paid - credited
    if inv["status"] == "VOID":
        return None
    if open_ <= 0 and paid > 0:
        status = "paid"
    elif open_ <= 0 and credited > 0:
        status = "rejected"
    elif paid > 0 or credited > 0:
        status = "approved"
    else:
        status = None
    accepted = total - credited if (paid > 0 or credited > 0) else None
    settled = (alloc.get("RECEIPT") or {}).get("last") if status == "paid" else None
    note = (f"Roy Books {inv['invoice_number']}: received ₦{paid:,.2f}"
            + (f", disallowed ₦{credited:,.2f}" if credited else "") + f", outstanding ₦{max(open_, 0):,.2f}")
    claims = q(conn, "SELECT id, status FROM royan_insurance_claims WHERE billing_id=%s", (bill["id"],))
    if not claims:
        if not status:
            return None
        hmo = q1(conn, """SELECT h.id, h.name FROM fin_customers c JOIN royan_hmos h ON h.id=c.hmo_id WHERE c.id=%s""",
                 (inv["customer_id"],))
        member = q1(conn, """SELECT membership_id FROM royan_patient_insurance WHERE patient_id=%s AND status='active'
                             ORDER BY is_primary DESC NULLS LAST LIMIT 1""", (bill["patient_id"],))
        row = q1(conn, """INSERT INTO royan_insurance_claims (billing_id, patient_id, hmo_provider, hmo_id, claim_amount, status,
                              approved_amount, settled_at, notes, external_source, external_id, hmo_provider_id)
                          VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'roy-books',%s,%s)
                          ON CONFLICT (external_source, external_id) DO NOTHING RETURNING id""",
                 (bill["id"], bill["patient_id"], (hmo or {}).get("name") or "HMO", (member or {}).get("membership_id") or "unknown",
                  total, status, accepted, settled, note, str(inv["id"]), (hmo or {}).get("id")))
        return {"created": row["id"] if row else None, "status": status}
    out = []
    for c in claims:
        new = status or ("submitted" if c["status"] in ("paid", "approved", "rejected") else c["status"])
        ex(conn, """UPDATE royan_insurance_claims SET status=%s, approved_amount=%s, settled_at=%s,
                        notes = trim(both E'\n' from COALESCE(regexp_replace(notes, E'(^|\n)Roy Books [^\n]*', '', 'g'), '') || E'\n' || %s)
                    WHERE id=%s""", (new, accepted, settled, note, c["id"]))
        out.append({"claim": c["id"], "from": c["status"], "to": new})
    return {"updated": out}



# ---------------------------------------------------------------------------
# Stock: the ledger, the books and the pharmacy shelf side by side
# ---------------------------------------------------------------------------

def stock_reconciliation(conn, entity_id: str, as_of: Optional[dt.date] = None) -> Dict[str, Any]:
    """Three figures that must agree once the books are live: the inventory accounts in the ledger, the stock Roy
    Books values (FIFO layers) and what is on the pharmacy's shelves (royan_inventory_batches). Royan's Sage expensed
    drugs on purchase (5000 Direct cost of drugs) and never carried a stock balance, so before go-live the ledger shows
    nil while the shelf holds real stock: that is the opening stock to be loaded, not a loss."""
    as_of = as_of or dt.date.today()
    gl = q(conn, """SELECT a.id::text AS account_id, a.code, a.name, COALESCE(SUM(g.debit-g.credit),0) AS balance
                    FROM fin_accounts a LEFT JOIN fin_v_ledger g ON g.account_id=a.id AND g.journal_date <= %s
                    WHERE a.legal_entity_id=%s AND a.subtype='INVENTORY' GROUP BY a.id ORDER BY a.code""", (as_of, entity_id))
    books = q1(conn, """SELECT COALESCE(SUM(qty_remaining*unit_cost),0) v, COUNT(DISTINCT sku) skus FROM fin_cost_layers
                        WHERE legal_entity_id=%s AND qty_remaining <> 0""", (entity_id,))
    shelf = q1(conn, """SELECT COUNT(*) lines, COUNT(DISTINCT formulary_id) items,
                               COALESCE(SUM(quantity_on_hand*unit_cost) FILTER (WHERE unit_cost > 0),0) value,
                               COUNT(*) FILTER (WHERE COALESCE(unit_cost,0) <= 0) no_cost,
                               COUNT(*) FILTER (WHERE expiry_date < %s) expired,
                               COALESCE(SUM(quantity_on_hand*unit_cost) FILTER (WHERE expiry_date < %s AND unit_cost > 0),0) expired_value
                        FROM royan_inventory_batches WHERE quantity_on_hand > 0""", (as_of, as_of))
    cogs = q1(conn, """SELECT COALESCE(SUM(g.debit-g.credit),0) v FROM fin_v_ledger g WHERE g.legal_entity_id=%s
                       AND g.subtype='COST_OF_SALES' AND g.journal_date BETWEEN %s AND %s""",
              (entity_id, as_of.replace(month=1, day=1), as_of))["v"]
    opening = q1(conn, "SELECT 1 FROM fin_inventory_transactions WHERE legal_entity_id=%s AND source_type='PHARMACY_OPENING' LIMIT 1",
                 (entity_id,))
    gl_total = sum((money(r["balance"]) for r in gl), Decimal("0"))
    return {"as_of": as_of, "ledger": gl, "ledger_total": gl_total, "books_value": money(books["v"]), "books_items": books["skus"],
            "shelf": {k: (money(v) if k.endswith("value") else v) for k, v in shelf.items()},
            "opening_stock_loaded": bool(opening), "cost_of_sales_ytd": money(cogs),
            "ledger_vs_books": gl_total - money(books["v"]), "books_vs_shelf": money(books["v"]) - money(shelf["value"]),
            "explanation": None if opening else (
                "Opening stock is not in the books yet. Royan's Sage expensed drugs when bought (5000 Direct cost of drugs) and "
                "carried no stock balance, so the ledger shows nil while the pharmacy holds stock. At go-live, load the pharmacy's "
                "batches as opening stock (Setup › Sage transfer & opening stock) and post the matching opening entry "
                "(Dr Inventory / Cr the account the accountant chooses) so ledger, books and shelf agree.")}


def set_batch_unit_cost(conn, ctx, ops_batch_id: Any, unit_cost: Any, reason: Optional[str] = None) -> Dict[str, Any]:
    """Give a pharmacy batch its unit cost (finance meeting: unit cost and valuation must be entered somewhere).

    A batch with no cost was left out of the go-live opening stock, so it is not in the books at all. Setting its cost
    records it on the pharmacy batch and brings the batch into the books at that cost, the same way the opening stock
    was posted: Dr Inventory / Cr Beginning Balance Equity, dated today, with an audit record. A batch the books
    already value keeps its cost here: changing that needs a stock adjustment (out at the old cost, in at the new),
    so the books never change value silently."""
    from src.fin import posting, rules
    ctx.require("inventory.adjustment.create")
    try:
        uc = Decimal(str(unit_cost))
    except Exception:
        raise invalid("Enter the unit cost as a number")
    if uc <= 0:
        raise invalid("The unit cost must be more than zero")
    b = q1(conn, """SELECT id, formulary_id, batch_number, quantity_on_hand, unit_cost, expiry_date
                    FROM royan_inventory_batches WHERE id=%s FOR UPDATE""", (ops_batch_id,))
    if not b:
        raise not_found("Batch", ops_batch_id)
    if not b["quantity_on_hand"] or Decimal(str(b["quantity_on_hand"])) <= 0:
        raise invalid("This batch has nothing on the shelf")
    in_books = q1(conn, """SELECT COALESCE(SUM(l.qty_remaining), 0) AS q, MAX(l.unit_cost) AS c FROM fin_cost_layers l
                           JOIN fin_batches fb ON fb.id = l.batch_id WHERE fb.legal_entity_id=%s AND fb.ops_batch_id=%s""",
                  (ctx.entity_id, b["id"]))
    if in_books and Decimal(str(in_books["q"] or 0)) > 0:
        raise FinError("INVALID_STATE_TRANSITION",
                       f"This batch is already valued in the books at {money(in_books['c'])} each. To change it, raise a stock "
                       "adjustment: take the quantity out at the old cost and back in at the new one.")
    sku = ensure_product(conn, ctx.entity_id, b["formulary_id"])
    bid = fin_batch_for_ops(conn, ctx.entity_id, sku, b["id"], b["batch_number"], b["expiry_date"])
    today = dt.date.today()
    ex(conn, "UPDATE royan_inventory_batches SET unit_cost=%s WHERE id=%s", (uc, b["id"]))
    t = inventory.receive(conn, ctx, sku=sku, quantity=b["quantity_on_hand"], unit_cost=uc, txn_type="OPENING_BALANCE",
                          txn_date=today, batch_id=bid, source_type="PHARMACY_OPENING", source_id=str(b["id"]),
                          reference="PHARMACY-OPENING-COSTED", reason=reason or "Unit cost entered: batch brought into the books",
                          mirror=False)
    value = money(t["total_cost"])
    inv = rules.account(conn, ctx.entity_id, "INVENTORY_DEFAULT")
    eq = rules.account(conn, ctx.entity_id, "OPENING_BALANCE_EQUITY")
    j = posting.post_system(conn, ctx, event_type="OPENING_STOCK_POSTED", journal_date=today, lines=[
        {"account_id": inv["id"], "debit": value, "product_sku": sku,
         "description": f"Opening stock costed: {sku} batch {b['batch_number']}"},
        {"account_id": eq["id"], "credit": value, "description": f"Opening stock costed: {sku} batch {b['batch_number']}"}],
        description=f"Opening stock costed - {sku} batch {b['batch_number']} ({b['quantity_on_hand']} at {uc})",
        source_type="MIGRATION", source_id=str(b["id"]), source_ref=f"COST-{b['id']}", journal_type="ADJUSTMENT")
    inventory.link_journal(conn, [str(t["id"])], j["id"])
    audit.record(conn, ctx, "BATCH_UNIT_COST_SET", "batch", str(b["id"]), ref=f"{sku} {b['batch_number']}",
                 before={"unit_cost": str(b["unit_cost"]) if b["unit_cost"] is not None else None},
                 after={"unit_cost": str(uc), "value": str(value)}, reason=reason)
    return {"ops_batch_id": b["id"], "sku": sku, "unit_cost": str(uc), "quantity": str(b["quantity_on_hand"]),
            "value": str(value), "journal": j["journal_number"]}


def count_overview(conn, entity_id: str) -> Dict[str, Any]:
    """What a stock count covers: every batch on the pharmacy's shelves with its expiry, unit cost and value, what Roy
    Books holds for it, and when the item was last counted - so Finance and Pharmacy count against the same list."""
    today = dt.date.today()
    rows = q(conn, """
        SELECT b.id AS ops_batch_id, b.formulary_id, f.code AS sku, COALESCE(f.generic_name, f.brand_name) AS product_name,
               f.strength, b.batch_number, b.expiry_date, b.quantity_on_hand AS shelf_qty, b.unit_cost,
               b.quantity_on_hand * COALESCE(b.unit_cost, 0) AS shelf_value, b.location,
               COALESCE(fb.status, 'NOT IN BOOKS') AS batch_status, bk.book_qty, bk.book_value, lc.last_counted
        FROM royan_inventory_batches b
        JOIN royan_drug_formulary f ON f.id = b.formulary_id
        LEFT JOIN fin_batches fb ON fb.legal_entity_id=%s AND fb.ops_batch_id = b.id
        LEFT JOIN LATERAL (SELECT SUM(l.qty_remaining) book_qty, SUM(l.qty_remaining*l.unit_cost) book_value
                           FROM fin_cost_layers l WHERE l.batch_id = fb.id) bk ON TRUE
        LEFT JOIN LATERAL (SELECT MAX(c.count_date) AS last_counted FROM fin_stock_count_lines cl
                           JOIN fin_stock_counts c ON c.id = cl.count_id AND c.status = 'POSTED'
                           JOIN fin_products p ON p.legal_entity_id = c.legal_entity_id AND p.sku = cl.sku
                           WHERE p.formulary_id = b.formulary_id) lc ON TRUE
        WHERE b.quantity_on_hand > 0
        ORDER BY lower(COALESCE(f.generic_name, f.brand_name)), b.expiry_date NULLS LAST""", (entity_id,))
    for r in rows:
        r["expired"] = bool(r["expiry_date"] and r["expiry_date"] < today)
        r["no_cost"] = not r["unit_cost"] or Decimal(str(r["unit_cost"])) <= 0
        r["difference"] = (Decimal(str(r["book_qty"] or 0)) - Decimal(str(r["shelf_qty"] or 0))) if r["book_qty"] is not None else None
    return {"lines": rows,
            "summary": {"items": len({r["formulary_id"] for r in rows}), "lines": len(rows),
                        "shelf_value": sum((Decimal(str(r["shelf_value"] or 0)) for r in rows), Decimal("0")),
                        "book_value": sum((Decimal(str(r["book_value"] or 0)) for r in rows), Decimal("0")),
                        "expired_lines": sum(1 for r in rows if r["expired"]),
                        "no_cost_lines": sum(1 for r in rows if r["no_cost"]),
                        "not_in_books": sum(1 for r in rows if r["batch_status"] == "NOT IN BOOKS"),
                        "never_counted": len({r["formulary_id"] for r in rows if not r["last_counted"]})}}


# ---------------------------------------------------------------------------
# Go live: from this day the hospital's activity posts into the books
# ---------------------------------------------------------------------------

def go_live(conn, ctx, cutover: dt.date) -> Dict[str, Any]:
    """Switch Roy Books on. Re-running is safe.

      1. The pharmacy's live batches become opening stock at the day before go-live (FIFO layers, expiry kept).
      2. Their value is posted as an opening entry - Dr Inventory / Cr Beginning Balance Equity - because Royan's
         Sage expensed drugs when bought and carried no stock balance; without it every dispense would credit an
         inventory account that never had a debit.
      3. The cut-over date is set: every bill, payment, discount, waiver, dispense and goods-received from that day
         posts as it happens, so the ledger, P&L, balance sheet and each patient's account move in real time.
    Finance's year-end opening balances can be loaded later (Setup › Opening balances) to re-base the books."""
    from src.fin import posting, rules, setup
    ctx.require("migration.load")
    out: Dict[str, Any] = {"cutover": cutover}
    as_of = cutover - dt.timedelta(days=1)
    if q1(conn, "SELECT 1 FROM fin_inventory_transactions WHERE legal_entity_id=%s AND source_type='PHARMACY_OPENING' LIMIT 1",
          (ctx.entity_id,)):
        out["pharmacy_stock"] = "already loaded"
    else:
        out["pharmacy_stock"] = load_pharmacy_opening_stock(conn, ctx, as_of)
    value = money(q1(conn, """SELECT COALESCE(SUM(total_cost),0) v FROM fin_inventory_transactions
                              WHERE legal_entity_id=%s AND source_type='PHARMACY_OPENING'""", (ctx.entity_id,))["v"])
    done = q1(conn, """SELECT id, journal_number FROM fin_journals WHERE legal_entity_id=%s AND source_ref='PHARMACY-OPENING'
                       AND status='POSTED'""", (ctx.entity_id,))
    if done:
        out["opening_entry"] = done["journal_number"]
    elif value > 0:
        inv = rules.account(conn, ctx.entity_id, "INVENTORY_DEFAULT")
        eq = rules.account(conn, ctx.entity_id, "OPENING_BALANCE_EQUITY")
        j = posting.post_system(conn, ctx, event_type="OPENING_STOCK_POSTED", journal_date=as_of, lines=[
            {"account_id": inv["id"], "debit": value, "description": "Opening pharmacy stock (live batches at cost)"},
            {"account_id": eq["id"], "credit": value, "description": "Opening pharmacy stock"}],
            description=f"Opening pharmacy stock at {as_of:%d %b %Y}", source_type="MIGRATION", source_id=ctx.entity_id,
            source_ref="PHARMACY-OPENING", journal_type="ADJUSTMENT")
        out["opening_entry"] = j["journal_number"]
    out["opening_stock_value"] = value
    setup.update_settings(conn, ctx, {"cutover_date": cutover})
    audit.record(conn, ctx, "BOOKS_LIVE", "settings", ctx.entity_id, metadata={k: str(v) for k, v in out.items()})
    return out


def ensure_scancare(conn, ctx, cutover: Optional[dt.date] = None) -> Dict[str, Any]:
    """Scancare (imaging) is a separate business with its own books: its own chart (the hospital template), bank and
    cash accounts, fiscal years, and the same go-live date as Royan. Hospital bills marked SCANCARE (every scan) post
    here - invoice, receipt, the patient's account in Scancare's ledger, Scancare's P&L and balance sheet."""
    from src.fin import setup
    from src.fin import periods
    ctx.require("finance.settings.edit")
    org = q1(conn, "SELECT o.code, o.name FROM fin_organizations o JOIN fin_legal_entities e ON e.organization_id=o.id ORDER BY e.created_at LIMIT 1")
    ent = setup.ensure_entity(conn, org_code=org["code"], org_name=org["name"], entity_code="SCN", entity_name="Scancare")
    created = not q1(conn, "SELECT 1 FROM fin_accounts WHERE legal_entity_id=%s LIMIT 1", (ent["id"],))
    if created:
        ex(conn, "SELECT fin_seed_hospital_template(%s, %s)", (ent["id"], (cutover or dt.date.today()).year))
    royan_cut = q1(conn, "SELECT cutover_date FROM fin_settings WHERE legal_entity_id=%s", (ctx.entity_id,))["cutover_date"]
    cut = cutover or royan_cut or dt.date.today()
    ex(conn, "UPDATE fin_settings SET cutover_date=COALESCE(cutover_date, %s) WHERE legal_entity_id=%s", (cut, ent["id"]))
    for y in (cut.year, cut.year + 1):
        if not q1(conn, "SELECT 1 FROM fin_fiscal_years WHERE legal_entity_id=%s AND start_date=%s", (ent["id"], dt.date(y, 1, 1))):
            from src.fin.context import system_context
            periods.create_fiscal_year(conn, system_context(conn, entity_id=str(ent["id"]), actor=ctx.actor_id), dt.date(y, 1, 1))
    audit.record(conn, ctx, "COMPANY_SET_UP", "legal_entity", ent["id"], ref="Scancare", metadata={"created": created, "cutover": str(cut)})
    return {"entity_id": str(ent["id"]), "code": "SCN", "name": "Scancare", "created": created, "cutover": cut}


# Where each kind of record comes from and which dates it covers - so finance can see what is in the system and where
# the gaps are (finance meeting, 10 Oct 2026: "a UI to show what data we have, what Hope data we have").
_COVERAGE = [
    ("Bills", "royan_billing", "billed_at"), ("Receipts", "royan_payments", "received_at"),
    ("Lab orders", "royan_lab_orders", "ordered_at"), ("Radiology / Scancare", "royan_radiology_orders", "COALESCE(ordered_at, order_date::timestamptz)"),
    ("Prescriptions", "royan_prescriptions", "prescribed_at"), ("Dispensing", "royan_dispensing", "dispensed_at"),
    ("Patients registered", "royan_patients", "registered_at"),
]


def data_coverage(conn, entity_id: str) -> Dict[str, Any]:
    ledger = q(conn, """SELECT origin, COUNT(*) AS lines, MIN(journal_date) AS date_from, MAX(journal_date) AS date_to
                        FROM fin_v_ledger WHERE legal_entity_id=%s GROUP BY origin ORDER BY MIN(journal_date)""", (entity_id,))
    s = q1(conn, "SELECT cutover_date FROM fin_settings WHERE legal_entity_id=%s", (entity_id,)) or {}
    ops = []
    for label, table, col in _COVERAGE:
        for r in q(conn, f"""SELECT CASE WHEN external_source IS NULL THEN 'Royan app' WHEN external_source='hope' THEN 'Hope'
                                         ELSE external_source END AS source,
                                    COUNT(*) AS records, MIN({col})::date AS date_from, MAX({col})::date AS date_to
                             FROM {table} GROUP BY 1 ORDER BY MIN({col})"""):
            ops.append({"record": label, **r})
    stock = q(conn, """SELECT department, COUNT(*) AS batches, MAX(source_updated_at)::date AS last_updated, string_agg(DISTINCT source, ', ') AS source
                       FROM royan_department_stock GROUP BY 1 ORDER BY 1""")
    sage_to = next((l["date_to"] for l in ledger if l["origin"] == "SAGE"), None)
    hope_to = max((o["date_to"] for o in ops if o["source"] == "Hope" and o["record"] == "Bills" and o["date_to"]), default=None)
    cut = s.get("cutover_date")
    gaps = []
    if sage_to and cut and (cut - sage_to).days > 1:
        gaps.append({"what": "General ledger", "date_from": sage_to + dt.timedelta(days=1), "date_to": cut - dt.timedelta(days=1),
                     "fix": "Upload finance's reconciled trial balance (Setup › Migration): the books are brought to it at its date."})
    if hope_to and cut and (cut - hope_to).days > 1:
        gaps.append({"what": "Hospital activity (bills, receipts, dispensing)", "date_from": hope_to + dt.timedelta(days=1),
                     "date_to": cut - dt.timedelta(days=1),
                     "fix": "Hope's last export ends here; a fresh Hope extract or the trial balance above covers it."})
    return {"ledger": ledger, "cutover": cut, "operations": ops, "department_stock": stock, "gaps": gaps}
