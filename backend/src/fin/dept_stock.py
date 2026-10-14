"""Department stores other than the pharmacy (lab, immunisation, urology, ward, theatre...).

Each batch on a department's shelf is a row in royan_department_stock and every change to it is a movement in
royan_department_stock_moves with its reason - the store's own stock ledger. Hope's department stock was last
maintained years ago, so a store is first counted; when finance confirms the count the store is put in the books:
each item becomes a Roy Books product of that department (fin_products.department) with its batches as cost layers,
exactly like the pharmacy's, and the stock is posted Dr the department's inventory account / Cr opening balance
equity. From then on every movement moves the cost layers (FIFO) and posts a journal: stock used or written off to the
department's cost account, a delivery to goods-received-not-invoiced (cleared by the supplier's bill), a count
difference to stock adjustments. So every Stock page - status, valuation, unit activity, batches - reads each
department the same way.
"""
from __future__ import annotations

import datetime as dt
import re
from decimal import Decimal
from typing import Any, Dict, List, Optional

from src.fin import audit, inventory, posting, rules
from src.fin.db import ZERO, ex, money, q, q1, qty
from src.fin.errors import FinError, invalid, not_found

# inventory account and the account stock used / written off is charged to, per department
DEPT_ACCOUNTS = {
    "LAB": ("12200", "50200"),
    "UROLOGY": ("12100", "50100"),
    "IMMUNISATION": ("12100", "5400"),      # Sage's "Direct Cost of Vaccines"
}
DEFAULT_ACCOUNTS = ("12100", "50100")
REDUCING = {"ISSUE", "EXPIRED", "DAMAGED", "RETURN_TO_SUPPLIER"}
MOVE_TYPES = {"RECEIVE", "ISSUE", "COUNT", "EXPIRED", "DAMAGED", "RETURN_TO_SUPPLIER", "CORRECTION"}
# the Roy Books inventory movement each kind of store movement is
TXN_TYPE = {"RECEIVE": "PURCHASE", "ISSUE": "CONSUMPTION", "EXPIRED": "EXPIRY", "DAMAGED": "DAMAGE",
            "RETURN_TO_SUPPLIER": "RETURN_OUT", "COUNT": "STOCK_COUNT", "CORRECTION": "ADJUSTMENT"}


def _account(conn, entity_id: str, code: str) -> Dict[str, Any]:
    a = q1(conn, "SELECT id, code, status FROM fin_accounts WHERE legal_entity_id=%s AND code=%s", (entity_id, code))
    if not a:
        raise FinError("MAPPING_MISSING", f"Account {code} is not in the chart of accounts")
    if a["status"] != "ACTIVE":
        ex(conn, "UPDATE fin_accounts SET status='ACTIVE' WHERE id=%s", (a["id"],))
    return a


def _accounts(conn, entity_id: str, department: str):
    inv, use = DEPT_ACCOUNTS.get(department, DEFAULT_ACCOUNTS)
    return _account(conn, entity_id, inv), _account(conn, entity_id, use)


def _is_hospital(conn, entity_id: str) -> bool:
    """The department stores are Royan's; another company's books (Scancare) do not show them."""
    e = q1(conn, "SELECT code FROM fin_legal_entities WHERE id=%s", (entity_id,))
    return not e or e["code"] == "RHL"


def overview(conn, entity_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Every store Royan runs (listed even while empty, so stock can be added), with what is on its shelves."""
    if entity_id and not _is_hospital(conn, entity_id):
        return []
    return q(conn, """SELECT st.code AS department, st.name, COALESCE(s.batches,0) AS batches, COALESCE(s.items,0) AS items,
                             COALESCE(s.value,0) AS value, COALESCE(s.expired_value,0) AS expired_value,
                             COALESCE(s.expired_batches,0) AS expired_batches, COALESCE(s.in_books,false) AS in_books, s.last_movement
                      FROM royan_stores st LEFT JOIN (
                          SELECT department, COUNT(*) FILTER (WHERE quantity > 0) AS batches, COUNT(DISTINCT item_name) AS items,
                                 COALESCE(SUM(quantity * COALESCE(unit_cost,0)),0) AS value,
                                 COALESCE(SUM(quantity * COALESCE(unit_cost,0)) FILTER (WHERE expiry_date < current_date),0) AS expired_value,
                                 COUNT(*) FILTER (WHERE quantity > 0 AND expiry_date < current_date) AS expired_batches,
                                 bool_or(in_books) AS in_books, MAX(updated_at) AS last_movement
                          FROM royan_department_stock WHERE is_active GROUP BY department) s ON s.department=st.code
                      WHERE st.is_active AND st.code <> 'PHARMACY' ORDER BY st.sort, st.name""")


def items(conn, department: str, include_empty: bool = False) -> List[Dict[str, Any]]:
    return q(conn, f"""SELECT s.*, s.quantity * COALESCE(s.unit_cost,0) AS value, (s.expiry_date < current_date) AS expired,
                              (SELECT COUNT(*) FROM royan_department_stock_moves m WHERE m.stock_id=s.id) AS moves
                       FROM royan_department_stock s WHERE s.department=%s AND s.is_active
                       {'' if include_empty else 'AND s.quantity > 0'} ORDER BY s.item_name, s.expiry_date NULLS LAST""",
             (department,))


def usage(conn, department: str) -> Dict[str, Any]:
    """What the department used: for Immunisation, the vaccines given (from the vaccination records)."""
    if department != "IMMUNISATION":
        return {"rows": []}
    rows = q(conn, """SELECT regexp_replace(upper(trim(vaccine_name)), '[[:space:]]+', ' ', 'g') AS item, COUNT(*) AS given,
                             COUNT(*) FILTER (WHERE date_given >= current_date - 90) AS last_90_days,
                             COUNT(*) FILTER (WHERE date_given >= date_trunc('year', current_date)) AS this_year,
                             MAX(date_given) AS last_given
                      FROM royan_immunisation WHERE trim(COALESCE(vaccine_name,'')) <> '' GROUP BY 1 ORDER BY 2 DESC LIMIT 60""")
    return {"title": "Vaccines given", "rows": rows}


def moves(conn, stock_id: int) -> List[Dict[str, Any]]:
    return q(conn, """SELECT m.*, j.journal_number FROM royan_department_stock_moves m
                      LEFT JOIN fin_journals j ON j.id=m.journal_id WHERE m.stock_id=%s ORDER BY m.created_at DESC""", (stock_id,))


def _slug(v: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "-", (v or "").upper()).strip("-")[:28]


def _fin_item(conn, ctx, s: Dict[str, Any]) -> Dict[str, Any]:
    """The Roy Books product + batch for a department batch (created the first time)."""
    if s.get("fin_sku"):
        return {"sku": s["fin_sku"], "batch_id": s.get("fin_batch_id")}
    inv, use = _accounts(conn, ctx.entity_id, s["department"])
    sku = f"{s['department'][:3]}-{_slug(s.get('item_code') or s['item_name'])}"
    same = q1(conn, "SELECT sku, name FROM fin_products WHERE legal_entity_id=%s AND sku=%s", (ctx.entity_id, sku))
    if same and same["name"] != s["item_name"]:
        sku = f"{sku[:30]}-{s['id']}"
    ex(conn, """INSERT INTO fin_products (legal_entity_id, sku, name, product_type, uom, inventory_account_id, cogs_account_id,
                reorder_level, is_batch_tracked, legacy_class, status, department)
                VALUES (%s,%s,%s,'INVENTORY','Each',%s,%s,%s,true,%s,'ACTIVE',%s) ON CONFLICT (legal_entity_id, sku) DO NOTHING""",
       (ctx.entity_id, sku, s["item_name"], inv["id"], use["id"], s.get("reorder_level"), s["department"].title(), s["department"]))
    batch_id = inventory.ensure_batch(conn, ctx.entity_id, sku, s.get("batch_number") or f"ST-{s['id']}", expiry_date=s.get("expiry_date"))
    ex(conn, "UPDATE royan_department_stock SET fin_sku=%s, fin_batch_id=%s WHERE id=%s", (sku, batch_id, s["id"]))
    return {"sku": sku, "batch_id": batch_id}


def _post(conn, ctx, *, department: str, value: Decimal, reduces: bool, move_type: str, ref: str, description: str,
          on: dt.date, source_id: str) -> Optional[str]:
    if value == 0:
        return None
    inv, use = _accounts(conn, ctx.entity_id, department)
    if move_type == "RECEIVE":
        other = rules.account(conn, ctx.entity_id, "GOODS_RECEIVED_NOT_INVOICED")   # cleared by the supplier's bill
    elif move_type in ("COUNT", "CORRECTION"):
        other = rules.account(conn, ctx.entity_id, "INVENTORY_ADJUSTMENT")
    else:
        other = use
    v = abs(value)
    lines = ([{"account_id": other["id"], "debit": v, "description": description}, {"account_id": inv["id"], "credit": v, "description": description}]
             if reduces else
             [{"account_id": inv["id"], "debit": v, "description": description}, {"account_id": other["id"], "credit": v, "description": description}])
    j = posting.post_system(conn, ctx, event_type="DEPARTMENT_STOCK_MOVED", journal_date=on, lines=lines, description=description,
                            source_type="DEPT_STOCK", source_id=source_id, source_ref=ref, journal_type="ADJUSTMENT")
    return str(j["id"])


def adjust(conn, ctx, stock_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
    """One movement on a batch: received, issued/used, counted (enter the counted quantity), expired, damaged, returned to
    the supplier or corrected. Once the store is in the books it moves the cost layers and posts a journal."""
    ctx.require("inventory.adjustment.create")
    s = q1(conn, "SELECT * FROM royan_department_stock WHERE id=%s FOR UPDATE", (stock_id,))
    if not s:
        raise not_found("Department stock", stock_id)
    move = str(data.get("move_type") or "").upper()
    if move not in MOVE_TYPES:
        raise invalid(f"Choose what happened: {', '.join(sorted(MOVE_TYPES))}")
    reason = (data.get("reason") or "").strip()
    if not reason:
        raise invalid("Give the reason for the movement")
    n = qty(data.get("quantity") or 0)
    cur = qty(s["quantity"])
    if move == "COUNT":
        change = n - cur
    elif move in REDUCING:
        change = -abs(n)
    elif move == "RECEIVE":
        change = abs(n)
    else:
        change = n
    if change == 0:
        raise invalid("Nothing changes: the quantity is the same")
    after = cur + change
    if after < 0:
        raise invalid(f"Only {cur} on the shelf")
    cost = money(data["unit_cost"]) if data.get("unit_cost") not in (None, "") else money(s["unit_cost"] or 0)
    value = money(change * cost)
    on = data.get("move_date") or dt.date.today()
    ex(conn, """UPDATE royan_department_stock SET quantity=%s, unit_cost=COALESCE(%s, unit_cost), updated_at=now(),
                batch_number=COALESCE(%s, batch_number), expiry_date=COALESCE(%s, expiry_date) WHERE id=%s""",
       (after, cost if data.get("unit_cost") not in (None, "") else None, data.get("batch_number") or None,
        data.get("expiry_date") or None, stock_id))
    m = q1(conn, """INSERT INTO royan_department_stock_moves (stock_id, department, move_type, quantity, quantity_after, unit_cost,
                    value, reason, created_by) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
           (stock_id, s["department"], move, change, after, cost, value, reason, ctx.actor_name or ctx.actor_id))
    jid = None
    # a batch left out of the books when the store was confirmed (expired) has no value there to take out
    if s["in_books"] and not (change < 0 and not s.get("fin_sku")):   # each movement: its own inventory txn + journal
        item = _fin_item(conn, ctx, s)
        ref = f"{s['department']}-{s['id']}"
        common = dict(sku=item["sku"], txn_type=TXN_TYPE[move], txn_date=on, batch_id=item["batch_id"], source_type="DEPT_STOCK",
                      source_id=f"MOVE:{m['id']}", reference=ref, reason=reason, mirror=False)
        if change > 0:
            t = inventory.receive(conn, ctx, quantity=change, unit_cost=cost, **common)
            value = money(t["total_cost"])
        else:
            t = inventory.issue(conn, ctx, quantity=-change, **common)
            value = -money(t["cost"])        # FIFO cost of what left the shelf
        jid = _post(conn, ctx, department=s["department"], value=value, reduces=change < 0, move_type=move, ref=ref, on=on,
                    source_id=f"MOVE:{m['id']}",
                    description=f"{s['department'].title()} store: {s['item_name']} {move.lower().replace('_', ' ')} ({reason})")
        if jid:
            inventory.link_journal(conn, [str(t["id"])], jid)
        ex(conn, "UPDATE royan_department_stock_moves SET journal_id=%s, value=%s WHERE id=%s", (jid, value, m["id"]))
    audit.record(conn, ctx, "DEPARTMENT_STOCK_MOVED", "department_stock", str(stock_id), reason=reason,
                 metadata={"move": move, "change": str(change), "value": str(value)})
    return {**m, "value": value, "posted": bool(jid)}


def add_item(conn, ctx, data: Dict[str, Any]) -> Dict[str, Any]:
    """A new item / batch on a department's shelf (a delivery, or an item missed when the store was loaded)."""
    ctx.require("inventory.adjustment.create")
    dept = str(data.get("department") or "").upper().strip()
    name = (data.get("item_name") or "").strip()
    if not dept or not name:
        raise invalid("Name the department and the item")
    if dept == "PHARMACY":
        raise invalid("Pharmacy stock is received in Pharmacy › Inventory")
    in_books = bool(q1(conn, "SELECT bool_or(in_books) b FROM royan_department_stock WHERE department=%s", (dept,))["b"])
    s = q1(conn, """INSERT INTO royan_department_stock (department, item_code, item_name, batch_number, expiry_date, quantity,
                    unit_cost, reorder_level, source, in_books) VALUES (%s,%s,%s,%s,%s,0,%s,%s,'MANUAL',%s) RETURNING *""",
           (dept, data.get("item_code") or None, name, data.get("batch_number") or None, data.get("expiry_date") or None,
            data.get("unit_cost") or None, data.get("reorder_level") or None, in_books))
    if qty(data.get("quantity") or 0) > 0:
        adjust(conn, ctx, s["id"], {"move_type": "RECEIVE", "quantity": data["quantity"], "unit_cost": data.get("unit_cost"),
                                    "reason": data.get("reason") or "Added to the store"})
    return q1(conn, "SELECT * FROM royan_department_stock WHERE id=%s", (s["id"],))


def confirm(conn, ctx, department: str, on: Optional[dt.date] = None) -> Dict[str, Any]:
    """Finance has counted the store: put its stock in the books at cost - each item a product, each batch a cost layer
    (expired batches stay out until written off)."""
    ctx.require("inventory.adjustment.approve")
    dept = department.upper()
    if q1(conn, "SELECT 1 FROM royan_department_stock WHERE department=%s AND in_books LIMIT 1", (dept,)):
        raise FinError("DUPLICATE_RESOURCE", f"{dept.title()} stock is already in the books")
    on = on or dt.date.today()
    rows = q(conn, """SELECT * FROM royan_department_stock WHERE department=%s AND is_active AND quantity > 0
                      AND (expiry_date IS NULL OR expiry_date >= current_date)""", (dept,))
    value, txns = ZERO, []
    for r in rows:
        item = _fin_item(conn, ctx, r)
        t = inventory.receive(conn, ctx, sku=item["sku"], quantity=r["quantity"], unit_cost=r["unit_cost"] or 0, txn_type="OPENING_BALANCE",
                              txn_date=on, batch_id=item["batch_id"], source_type="DEPT_STOCK", source_id=f"OPEN:{r['id']}",
                              reference=f"{dept}-OPENING", reason="Store counted and put in the books", mirror=False)
        value += money(t["total_cost"])
        txns.append(str(t["id"]))
    inv, _ = _accounts(conn, ctx.entity_id, dept)
    obe = rules.account(conn, ctx.entity_id, "OPENING_BALANCE_EQUITY")
    j = None
    if value > 0:
        j = posting.post_system(conn, ctx, event_type="DEPARTMENT_STOCK_CONFIRMED", journal_date=on,
                                lines=[{"account_id": inv["id"], "debit": value, "description": f"{dept.title()} stock counted"},
                                       {"account_id": obe["id"], "credit": value, "description": f"{dept.title()} stock counted"}],
                                description=f"{dept.title()} store stock put in the books after the count", source_type="DEPT_STOCK",
                                source_id=f"CONFIRM:{dept}", source_ref=f"{dept}-OPENING", journal_type="ADJUSTMENT")
        inventory.link_journal(conn, txns, str(j["id"]))
    ex(conn, "UPDATE royan_department_stock SET in_books=true, updated_at=now() WHERE department=%s", (dept,))
    for r in rows:
        ex(conn, """INSERT INTO royan_department_stock_moves (stock_id, department, move_type, quantity, quantity_after, unit_cost, value,
                    reason, journal_id, created_by) VALUES (%s,%s,'CONFIRM',0,%s,%s,%s,'Counted and put in the books',%s,%s)""",
           (r["id"], dept, r["quantity"], r["unit_cost"], money(Decimal(str(r["quantity"])) * Decimal(str(r["unit_cost"] or 0))),
            j["id"] if j else None, ctx.actor_name or ctx.actor_id))
    audit.record(conn, ctx, "DEPARTMENT_STOCK_CONFIRMED", "department_stock", dept, metadata={"value": str(value), "batches": len(rows)})
    return {"department": dept, "value": str(value), "batches": len(rows), "journal": j["journal_number"] if j else None}
