"""Procurement & Stores (reportGUide.md s6): request -> approve -> place -> received by the stock arriving."""
import datetime as dt

import pytest

from src.fin.db import q1
from src.services import stock_orders as so
from .conftest import user


def _supplier(conn):
    return q1(conn, "INSERT INTO suppliers (name) VALUES ('Flow Test Supplies Ltd') RETURNING id::text AS id")["id"]


def test_order_lifecycle_closes_on_receipt(conn, make_drug):
    fid = make_drug(qty=0)
    pharm = user("pharmacist")
    oid = so.raise_order(pharm, {"formulary_id": fid, "quantity": 200, "urgency": "urgent"})["id"]

    with pytest.raises(so.OrderError):                      # one open order per drug
        so.raise_order(pharm, {"formulary_id": fid, "quantity": 5})
    with pytest.raises(so.OrderError):                      # cannot place before approval
        so.place(pharm, oid, {"supplier_id": _supplier(conn), "expected_date": dt.date.today().isoformat()})
    with pytest.raises(PermissionError):                    # a nurse can raise, not approve
        so.approve(user("nurse"), oid)

    so.approve(pharm, oid)
    sup = _supplier(conn)
    so.place(pharm, oid, {"supplier_id": sup, "expected_date": (dt.date.today() + dt.timedelta(days=5)).isoformat()})
    o = next(x for x in so.orders("open")["orders"] if x["id"] == oid)
    assert o["status"] == "ordered" and o["supplier_id"] == sup and not o["overdue"]

    # stock arriving closes it - nobody marks it received
    closed = so.receive_for(conn, fid, 200, "pharmacy_receipt", "B-1")
    assert closed == oid
    r = q1(conn, "SELECT status, received_qty, received_source FROM royan_replenishment_requests WHERE id=%s", (oid,))
    assert r["status"] == "received" and float(r["received_qty"]) == 200 and r["received_source"] == "pharmacy_receipt"
    assert so.receive_for(conn, fid, 10, "pharmacy_receipt") is None     # nothing left open


def test_cancel_needs_reason(conn, make_drug):
    oid = so.raise_order(user("ops"), {"formulary_id": make_drug(), "quantity": 10})["id"]
    with pytest.raises(so.OrderError):
        so.cancel(user("ops"), oid, "  ")
    assert so.cancel(user("ops"), oid, "duplicate")["status"] == "cancelled"


def test_reorder_plan_shape_and_stock_matches_shelves(conn, make_drug):
    fid = make_drug(qty=40, unit_cost=50)
    plan = so.reorder_plan(refresh=True)
    assert plan["demand_to"] and plan["demand_days"] == 180
    assert set(plan["counts"]) == set(so.PLAN_STATUSES)
    mine = next(i for i in plan["items"] if i["formulary_id"] == fid)
    assert mine["on_hand"] == 40 and mine["value"] == 2000 and mine["status"] == "no_recent_use"
    for i in plan["items"]:
        assert i["status"] in so.PLAN_STATUSES and i["suggested_qty"] >= 0
        if i["status"] in ("reorder_now", "reorder_soon"):
            assert i["per_day"] > 0
    s = so.summary()
    assert s["reorder_now"] == plan["counts"]["reorder_now"]


def test_demand_window_ends_on_a_real_trading_day(conn):
    """Two stray dispensings after the loaded history once moved the window and made 535 drugs look unused."""
    hist = q1(conn, """SELECT COUNT(*) AS n FROM royan_dispensing WHERE dispensed_at::date > (
                         SELECT MAX(d) FROM (SELECT dispensed_at::date d FROM royan_dispensing GROUP BY 1 HAVING COUNT(*) >= 20) x) - 180""")
    plan = so.reorder_plan(refresh=True)
    used = [i for i in plan["items"] if i["per_day"] > 0]
    if hist["n"]:
        assert len(used) > 50, f"only {len(used)} drugs show use - the demand window ends at {plan['demand_to']}"
