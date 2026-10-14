"""Department stores (lab, urology...): movements are a stock ledger; once counted and confirmed the store is in the
books, and every later movement posts a journal."""
from decimal import Decimal

import pytest

from src.fin import accounts, dept_stock, setup
from src.fin.db import q, q1
from src.fin.errors import FinError


def _ledger(conn, entity_id, code):
    r = q1(conn, "SELECT COALESCE(SUM(debit-credit),0) AS b FROM fin_v_ledger WHERE legal_entity_id=%s AND account_code=%s", (entity_id, code))
    return Decimal(str(r["b"]))


def test_department_store_movements_and_books(conn, make_entity):
    ctx, a = make_entity()
    for code, name, st in [("12200", "Inventory - Lab", "INVENTORY"), ("50200", "Lab reagents used", "COST_OF_SALES"),
                           ("30900", "Opening balance equity", "EQUITY"), ("58500", "Stock adjustments", "COST_OF_SALES")]:
        a[code] = accounts.create_account(conn, ctx, {"code": code, "name": name, "subtype": st, "is_control": st == "INVENTORY"})
    setup.set_mapping(conn, ctx, "OPENING_BALANCE_EQUITY", str(a["30900"]["id"]))
    setup.set_mapping(conn, ctx, "INVENTORY_ADJUSTMENT", str(a["58500"]["id"]))
    dept = "TLAB" + str(ctx.entity_id)[:6].upper()
    dept_stock.DEPT_ACCOUNTS[dept] = ("12200", "50200")
    s = dept_stock.add_item(conn, ctx, {"department": dept, "item_name": "Albumin reagent", "quantity": 10, "unit_cost": 1000,
                                        "reason": "Found on the shelf"})
    assert Decimal(str(s["quantity"])) == 10 and not s["in_books"]
    # not in the books yet: a movement changes the shelf, posts nothing
    m = dept_stock.adjust(conn, ctx, s["id"], {"move_type": "ISSUE", "quantity": 2, "reason": "Used"})
    assert not m["posted"] and Decimal(str(m["quantity_after"])) == 8
    with pytest.raises(FinError):
        dept_stock.adjust(conn, ctx, s["id"], {"move_type": "ISSUE", "quantity": 20, "reason": "Too many"})

    res = dept_stock.confirm(conn, ctx, dept)
    assert Decimal(res["value"]) == 8000 and res["journal"]
    assert _ledger(conn, ctx.entity_id, "12200") == 8000
    # counted 7: one short goes to stock adjustments; used 2 goes to the lab's cost
    dept_stock.adjust(conn, ctx, s["id"], {"move_type": "COUNT", "quantity": 7, "reason": "Monthly count"})
    dept_stock.adjust(conn, ctx, s["id"], {"move_type": "ISSUE", "quantity": 2, "reason": "FBC runs"})
    assert _ledger(conn, ctx.entity_id, "12200") == 5000
    assert _ledger(conn, ctx.entity_id, "58500") == 1000 and _ledger(conn, ctx.entity_id, "50200") == 2000
    assert len(q(conn, "SELECT 1 FROM royan_department_stock_moves WHERE stock_id=%s", (s["id"],))) == 5
    # the store's items are Roy Books products of that department, with FIFO layers the Stock pages read
    p = q1(conn, "SELECT sku, department FROM fin_products WHERE legal_entity_id=%s AND department=%s", (ctx.entity_id, dept))
    assert p, "the counted item became a product of its department"
    left = q1(conn, "SELECT COALESCE(SUM(qty_remaining),0) AS n, COALESCE(SUM(qty_remaining*unit_cost),0) AS v FROM fin_cost_layers WHERE legal_entity_id=%s AND sku=%s",
              (ctx.entity_id, p["sku"]))
    assert Decimal(str(left["n"])) == 5 and Decimal(str(left["v"])) == 5000
