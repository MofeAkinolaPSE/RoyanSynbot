"""Procurement & Stores: what to order, stock orders, suppliers (reportGUide.md s6).

  summary()          KPI cards: to order now, open orders, overdue deliveries, bought in 12 months
  reorder_plan()     per drug: live stock, real use, cover, status, suggested quantity, last supplier/price
  orders()           the stock orders (royan_replenishment_requests), newest first
  raise_order / approve / place / cancel     the steps, each owned by a role
  receive_for()      called when stock ARRIVES - pharmacy receipt or a Roy Books supplier delivery -
                     to close the open order for that drug. Nobody marks an order received by hand.
  suppliers()        who we buy from: 12-month spend, deliveries, last delivery, what we owe (books)

Demand is what the pharmacy actually dispensed (royan_dispensing - Hope's history plus this
system), averaged over the 180 days to the last day the pharmacy was trading (20+ dispensings). The page says that
date, so a gap in loaded dispensing is never mistaken for a drug nobody uses.
"""
from __future__ import annotations

import datetime as dt
import logging
import threading
import time
from typing import Any, Dict, List, Optional

from src.constants import (PHARMACY_DEFAULT_LEAD_TIME_DAYS, PHARMACY_DEFAULT_SAFETY_STOCK_DAYS,
                           PHARMACY_REVIEW_CYCLE_DAYS)
from src.fin.db import ex, q, q1, tx

log = logging.getLogger(__name__)

DEMAND_DAYS = 180
MIN_TRADING_DAY = 20          # dispensings in a day for it to count as the pharmacy trading
OPEN = ("recommended", "approved", "ordered")
STATUS_LABEL = {"recommended": "requested", "approved": "approved", "ordered": "with supplier",
                "received": "received", "cancelled": "cancelled"}
PLAN_STATUSES = ("out_of_stock", "reorder_now", "reorder_soon", "healthy", "no_recent_use")
APPROVE_ROLES = {"pharmacist", "ops", "finance", "management", "admin"}
_CACHE: Dict[str, Any] = {}


class OrderError(ValueError):
    pass


def _f(v: Any) -> float:
    return float(v or 0)


def _roles(user: Dict[str, Any]) -> set:
    return {str(r).lower() for r in (user.get("roles") or [])}


# ---------------------------------------------------------------------------
# Reorder plan
# ---------------------------------------------------------------------------

_PLAN_LOCK = threading.Lock()


def _last_trading_day(conn) -> Optional[dt.date]:
    """The last real trading day: a few stray entries after the loaded history (tests, a pilot day)
    must not move the window past it and make every drug look unused. Looks at the last 120 days
    first (an index range, not all 600k dispensings) and only falls back to the full history."""
    for recent in (True, False):
        where = ("WHERE dispensed_at >= (SELECT MAX(dispensed_at) FROM royan_dispensing) - interval '120 days'"
                 if recent else "")
        d = q1(conn, f"""SELECT MAX(d) AS d FROM (SELECT dispensed_at::date AS d FROM royan_dispensing {where}
                          GROUP BY 1 HAVING COUNT(*) >= {MIN_TRADING_DAY}) x""")["d"]
        if d:
            return d
    return None


def reorder_plan(refresh: bool = False) -> Dict[str, Any]:
    hit = _CACHE.get("plan")
    if hit and not refresh and time.monotonic() - hit[0] < 120:
        return hit[1]
    with _PLAN_LOCK:   # one rebuild at a time; the others wait for it and take its result
        hit = _CACHE.get("plan")
        if hit and not refresh and time.monotonic() - hit[0] < 120:
            return hit[1]
        return _reorder_plan_build()


def _reorder_plan_build() -> Dict[str, Any]:
    t = dt.date.today()
    with tx() as conn:
        as_of = _last_trading_day(conn) or t
        start = as_of - dt.timedelta(days=DEMAND_DAYS)
        rows = q(conn, """
            WITH stock AS (
                SELECT formulary_id, SUM(quantity_on_hand) AS on_hand,
                       SUM(quantity_on_hand * COALESCE(unit_cost,0)) AS value,
                       SUM(quantity_on_hand) FILTER (WHERE expiry_date < %(t)s) AS expired,
                       MIN(expiry_date) FILTER (WHERE expiry_date >= %(t)s) AS next_expiry,
                       SUM(quantity_on_hand) FILTER (WHERE expiry_date >= %(t)s AND expiry_date < %(t)s::date + 90) AS expiring_90
                FROM royan_inventory_batches WHERE quantity_on_hand > 0 GROUP BY formulary_id),
            used AS (
                SELECT formulary_id, SUM(quantity_dispensed) AS qty, COUNT(*) AS dispensings, MAX(dispensed_at)::date AS last_used
                FROM royan_dispensing WHERE formulary_id IS NOT NULL AND dispensed_at::date > %(s)s AND dispensed_at::date <= %(a)s
                GROUP BY formulary_id),
            orders AS (
                SELECT formulary_id, SUM(requested_qty) AS qty, COUNT(*) AS n, MIN(expected_date) AS expected
                FROM royan_replenishment_requests WHERE status IN ('recommended','approved','ordered') GROUP BY formulary_id),
            last_buy AS (
                SELECT DISTINCT ON (p.formulary_id) p.formulary_id, h.supplier_id, h.supplier_name, h.unit_cost, h.received_date
                FROM fin_hist_purchase_lines h JOIN fin_products p ON p.sku=h.sku AND p.legal_entity_id=h.legal_entity_id
                WHERE p.formulary_id IS NOT NULL ORDER BY p.formulary_id, h.received_date DESC)
            SELECT f.id AS formulary_id, f.code, COALESCE(f.generic_name, f.brand_name) AS drug, f.brand_name, f.form, f.strength,
                   f.lead_time_days, f.safety_stock_days, f.reorder_level, f.unit_cost AS list_cost,
                   COALESCE(s.on_hand,0) AS on_hand, COALESCE(s.value,0) AS value, COALESCE(s.expired,0) AS expired,
                   s.next_expiry, COALESCE(s.expiring_90,0) AS expiring_90,
                   COALESCE(u.qty,0) AS used, COALESCE(u.dispensings,0) AS dispensings, u.last_used,
                   COALESCE(o.qty,0) AS on_order, COALESCE(o.n,0) AS open_orders, o.expected,
                   lb.supplier_id::text AS last_supplier_id, lb.supplier_name AS last_supplier, lb.unit_cost AS last_cost,
                   lb.received_date AS last_bought
            FROM royan_drug_formulary f
            LEFT JOIN stock s ON s.formulary_id=f.id LEFT JOIN used u ON u.formulary_id=f.id
            LEFT JOIN orders o ON o.formulary_id=f.id LEFT JOIN last_buy lb ON lb.formulary_id=f.id
            WHERE COALESCE(f.is_active, true) AND f.deprecated_at IS NULL
              AND (s.on_hand > 0 OR u.qty > 0 OR o.n > 0)""",
                 {"t": t, "s": start, "a": as_of})
    items: List[Dict[str, Any]] = []
    for r in rows:
        lead = int(r["lead_time_days"] or PHARMACY_DEFAULT_LEAD_TIME_DAYS)
        safety = int(r["safety_stock_days"] or PHARMACY_DEFAULT_SAFETY_STOCK_DAYS)
        on_hand = _f(r["on_hand"]) - _f(r["expired"])       # expired stock cannot be dispensed
        daily = _f(r["used"]) / DEMAND_DAYS
        cover = round(on_hand / daily, 1) if daily > 0 else None
        need_days = lead + safety
        target_days = need_days + PHARMACY_REVIEW_CYCLE_DAYS
        if daily <= 0:
            status = "out_of_stock" if on_hand <= 0 and r["open_orders"] == 0 and _f(r["used"]) > 0 else "no_recent_use"
            suggest = 0.0
        elif on_hand <= 0:
            status = "out_of_stock"
            suggest = daily * target_days
        elif cover < need_days:
            status = "reorder_now"
            suggest = daily * target_days - on_hand
        elif cover < target_days:
            status = "reorder_soon"
            suggest = daily * target_days - on_hand
        else:
            status = "healthy"
            suggest = 0.0
        suggest = max(0.0, round(suggest - _f(r["on_order"])))
        # stock that will not be used before it expires, at the current rate of use
        expiry_risk = None
        if r["next_expiry"] and on_hand > 0:
            days_left = (r["next_expiry"] - t).days
            usable = daily * max(days_left, 0)
            if _f(r["expiring_90"]) > usable:
                expiry_risk = round(_f(r["expiring_90"]) - usable)
        cost = _f(r["last_cost"] or r["list_cost"])
        items.append({
            "formulary_id": r["formulary_id"], "code": r["code"], "drug": r["drug"], "brand": r["brand_name"],
            "form": r["form"], "strength": r["strength"], "on_hand": on_hand, "expired": _f(r["expired"]),
            "value": round(_f(r["value"]), 2), "used_180d": _f(r["used"]), "per_day": round(daily, 2),
            "cover_days": cover, "lead_days": lead, "safety_days": safety, "status": status,
            "suggested_qty": suggest, "suggested_value": round(suggest * cost, 2) if cost else None,
            "on_order": _f(r["on_order"]), "open_orders": int(r["open_orders"]), "expected": r["expected"],
            "next_expiry": r["next_expiry"], "expiry_risk_qty": expiry_risk, "last_used": r["last_used"],
            "last_supplier_id": r["last_supplier_id"], "last_supplier": r["last_supplier"],
            "last_cost": _f(r["last_cost"]) if r["last_cost"] is not None else None, "last_bought": r["last_bought"],
        })
    rank = {s: i for i, s in enumerate(PLAN_STATUSES)}
    items.sort(key=lambda x: (rank[x["status"]], -(x["suggested_value"] or 0), x["drug"] or ""))
    counts = {s: sum(1 for i in items if i["status"] == s) for s in PLAN_STATUSES}
    out = {"demand_to": as_of, "demand_days": DEMAND_DAYS, "items": items, "counts": counts,
           "expiry_risk": sum(1 for i in items if i["expiry_risk_qty"]),
           "to_order_value": round(sum(i["suggested_value"] or 0 for i in items if i["status"] in ("out_of_stock", "reorder_now")), 2)}
    _CACHE["plan"] = (time.monotonic(), out)
    return out


# ---------------------------------------------------------------------------
# Stock orders
# ---------------------------------------------------------------------------

_ORDER_SQL = """SELECT r.id, r.formulary_id, COALESCE(f.generic_name, f.brand_name, r.sku) AS drug, f.code,
                       r.requested_qty, r.unit, r.status, r.urgency, r.ward, r.notes, r.risk_tier_at_request,
                       r.created_by, r.created_at, r.approved_by, r.approved_at, r.ordered_by, r.ordered_at,
                       r.expected_date, r.supplier_id::text AS supplier_id, s.name AS supplier,
                       r.fulfilled_at, r.received_qty, r.received_source, r.received_ref, r.cancelled_reason, r.auto_generated
                FROM royan_replenishment_requests r
                LEFT JOIN royan_drug_formulary f ON f.id=r.formulary_id
                LEFT JOIN suppliers s ON s.id=r.supplier_id"""


def _names(conn, ids) -> Dict[str, str]:
    ids = [i for i in {str(x) for x in ids if x} if len(i) == 36]
    if not ids:
        return {}
    rows = q(conn, """SELECT u.id::text AS id, COALESCE(s.full_name, u.email) AS name FROM royan_users u
                      LEFT JOIN royan_staff s ON s.user_id=u.id WHERE u.id::text = ANY(%s)""", (ids,))
    return {r["id"]: r["name"] for r in rows}


def orders(status: Optional[str] = None, limit: int = 300) -> Dict[str, Any]:
    with tx() as conn:
        where, args = "", []
        if status == "open":
            where = "WHERE r.status IN ('recommended','approved','ordered')"
        elif status:
            where, args = "WHERE r.status=%s", [status]
        rows = q(conn, f"{_ORDER_SQL} {where} ORDER BY r.created_at DESC LIMIT %s", (*args, limit))
        names = _names(conn, [x for r in rows for x in (r["created_by"], r["approved_by"], r["ordered_by"])])
    t = dt.date.today()
    for r in rows:
        r["status_label"] = STATUS_LABEL.get(r["status"], r["status"])
        r["overdue"] = bool(r["status"] == "ordered" and r["expected_date"] and r["expected_date"] < t)
        for k in ("created_by", "approved_by", "ordered_by"):
            r[f"{k}_name"] = names.get(str(r[k]), r[k] if r[k] and len(str(r[k])) != 36 else None)
    return {"orders": rows}


def _order(conn, oid: int, lock: bool = True) -> Dict[str, Any]:
    r = q1(conn, f"SELECT * FROM royan_replenishment_requests WHERE id=%s{' FOR UPDATE' if lock else ''}", (oid,))
    if not r:
        raise LookupError("Stock order not found")
    return r


def raise_order(user: Dict[str, Any], data: Dict[str, Any]) -> Dict[str, Any]:
    fid = data.get("formulary_id")
    qty = _f(data.get("quantity"))
    if not fid or qty <= 0:
        raise OrderError("Choose the drug and a quantity above zero")
    with tx() as conn:
        f = q1(conn, "SELECT id, COALESCE(generic_name, brand_name, code) AS name FROM royan_drug_formulary WHERE id=%s", (fid,))
        if not f:
            raise LookupError("Drug not found")
        if q1(conn, "SELECT 1 FROM royan_replenishment_requests WHERE formulary_id=%s AND status IN ('recommended','approved','ordered')", (fid,)) \
                and not data.get("allow_second"):
            raise OrderError(f"{f['name']} already has an open stock order - add to it or cancel it first")
        r = q1(conn, """INSERT INTO royan_replenishment_requests (sku, formulary_id, requested_qty, status, created_by, notes,
                                                                urgency, unit, supplier_id, auto_generated)
                        VALUES (%s,%s,%s,'recommended',%s,%s,%s,%s,%s,false) RETURNING id""",
               (f["name"], fid, qty, str(user.get("sub") or "system"), (data.get("notes") or "").strip() or None,
                data.get("urgency") if data.get("urgency") in ("routine", "urgent", "stat") else "routine",
                data.get("unit"), data.get("supplier_id") or None))
    _CACHE.pop("plan", None)
    return {"id": r["id"]}


def approve(user: Dict[str, Any], oid: int) -> Dict[str, Any]:
    if not _roles(user) & APPROVE_ROLES:
        raise PermissionError("Approving a stock order needs pharmacy, operations, finance or management")
    with tx() as conn:
        o = _order(conn, oid)
        if o["status"] != "recommended":
            raise OrderError(f"Only a requested order can be approved (this one is {STATUS_LABEL[o['status']]})")
        ex(conn, "UPDATE royan_replenishment_requests SET status='approved', approved_by=%s, approved_at=now() WHERE id=%s",
           (str(user.get("sub")), oid))
    return {"id": oid, "status": "approved"}


def place(user: Dict[str, Any], oid: int, data: Dict[str, Any]) -> Dict[str, Any]:
    """Sent to the supplier, with the date it is expected."""
    exp = data.get("expected_date")
    if not data.get("supplier_id") or not exp:
        raise OrderError("Choose the supplier and the date the delivery is expected")
    with tx() as conn:
        o = _order(conn, oid)
        if o["status"] != "approved":
            raise OrderError(f"Only an approved order can be placed with a supplier (this one is {STATUS_LABEL[o['status']]})")
        ex(conn, """UPDATE royan_replenishment_requests SET status='ordered', ordered_by=%s, ordered_at=now(), supplier_id=%s,
                    expected_date=%s, requested_qty=COALESCE(%s, requested_qty) WHERE id=%s""",
           (str(user.get("sub")), data["supplier_id"], exp, data.get("quantity") or None, oid))
    return {"id": oid, "status": "ordered"}


def cancel(user: Dict[str, Any], oid: int, reason: str) -> Dict[str, Any]:
    if not (reason or "").strip():
        raise OrderError("Give a reason for cancelling")
    with tx() as conn:
        o = _order(conn, oid)
        if o["status"] not in OPEN:
            raise OrderError("This order is already closed")
        ex(conn, "UPDATE royan_replenishment_requests SET status='cancelled', cancelled_reason=%s WHERE id=%s", (reason.strip(), oid))
    _CACHE.pop("plan", None)
    return {"id": oid, "status": "cancelled"}


def receive_for(conn, formulary_id: Optional[int], quantity: float, source: str, ref: Optional[str] = None) -> Optional[int]:
    """Stock for this drug has arrived: close its oldest open order (placed first, then approved, then requested).
    Runs inside the caller's transaction, so the order closes exactly when the stock is recorded."""
    if not formulary_id or quantity <= 0:
        return None
    o = q1(conn, """SELECT id FROM royan_replenishment_requests WHERE formulary_id=%s AND status IN ('ordered','approved','recommended')
                    ORDER BY (status='ordered') DESC, (status='approved') DESC, created_at LIMIT 1 FOR UPDATE""", (formulary_id,))
    if not o:
        return None
    ex(conn, """UPDATE royan_replenishment_requests SET status='received', fulfilled_at=now(), received_qty=%s,
                received_source=%s, received_ref=%s WHERE id=%s""", (quantity, source, ref, o["id"]))
    _CACHE.pop("plan", None)
    return o["id"]


# ---------------------------------------------------------------------------
# Suppliers
# ---------------------------------------------------------------------------

def suppliers() -> Dict[str, Any]:
    with tx() as conn:
        to = q1(conn, "SELECT MAX(received_date) AS d FROM fin_hist_purchase_lines")["d"]
        rows = q(conn, """
            WITH buy AS (
                SELECT supplier_id, SUM(amount) FILTER (WHERE received_date > %(to)s::date - 365) AS spend_12m,
                       COUNT(DISTINCT grn_number) FILTER (WHERE received_date > %(to)s::date - 365) AS deliveries_12m,
                       COUNT(DISTINCT sku) FILTER (WHERE received_date > %(to)s::date - 365) AS products_12m,
                       MAX(received_date) AS last_delivery, SUM(amount) AS spend_all
                FROM fin_hist_purchase_lines GROUP BY supplier_id),
            owe AS (
                SELECT supplier_id, SUM(total - amount_settled) AS owed,
                       SUM(total - amount_settled) FILTER (WHERE due_date < current_date) AS overdue
                FROM fin_supplier_bills WHERE status IN ('POSTED','PARTIALLY_PAID') GROUP BY supplier_id),
            ord AS (
                SELECT supplier_id, COUNT(*) AS open_orders FROM royan_replenishment_requests
                WHERE status='ordered' GROUP BY supplier_id)
            SELECT s.id::text AS id, s.name, s.category, s.contact_name, s.phone, s.contact_email, s.payment_terms, s.status,
                   COALESCE(b.spend_12m,0) AS spend_12m, COALESCE(b.deliveries_12m,0) AS deliveries_12m,
                   COALESCE(b.products_12m,0) AS products_12m, b.last_delivery, COALESCE(b.spend_all,0) AS spend_all,
                   COALESCE(o.owed,0) AS owed, COALESCE(o.overdue,0) AS overdue, COALESCE(d.open_orders,0) AS open_orders
            FROM suppliers s LEFT JOIN buy b ON b.supplier_id=s.id LEFT JOIN owe o ON o.supplier_id=s.id
            LEFT JOIN ord d ON d.supplier_id=s.id
            ORDER BY COALESCE(b.spend_12m,0) DESC, s.name""", {"to": to or dt.date.today()})
    for r in rows:
        for k in ("spend_12m", "spend_all", "owed", "overdue"):
            r[k] = round(_f(r[k]), 2)
    active = [r for r in rows if r["spend_12m"] > 0]
    return {"purchases_to": to, "suppliers": rows, "active_12m": len(active),
            "spend_12m": round(sum(r["spend_12m"] for r in rows), 2),
            "owed": round(sum(r["owed"] for r in rows), 2), "overdue": round(sum(r["overdue"] for r in rows), 2)}


def summary() -> Dict[str, Any]:
    plan = reorder_plan()
    t = dt.date.today()
    with tx() as conn:
        o = q1(conn, """SELECT COUNT(*) FILTER (WHERE status='recommended') AS requested,
                               COUNT(*) FILTER (WHERE status='approved') AS approved,
                               COUNT(*) FILTER (WHERE status='ordered') AS ordered,
                               COUNT(*) FILTER (WHERE status='ordered' AND expected_date < %s) AS overdue
                        FROM royan_replenishment_requests""", (t,))
    s = suppliers()
    return {"demand_to": plan["demand_to"], "out_of_stock": plan["counts"]["out_of_stock"],
            "reorder_now": plan["counts"]["reorder_now"], "reorder_soon": plan["counts"]["reorder_soon"],
            "to_order_value": plan["to_order_value"], "expiry_risk": plan["expiry_risk"],
            "requested": int(o["requested"] or 0), "approved": int(o["approved"] or 0), "ordered": int(o["ordered"] or 0),
            "overdue_orders": int(o["overdue"] or 0), "purchases_12m": s["spend_12m"], "purchases_to": s["purchases_to"],
            "active_suppliers": s["active_12m"], "owed_suppliers": s["owed"]}
