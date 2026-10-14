"""Department stores for the people who run them (finance meeting, Oct 2026).

Stock is kept by the departments and the pharmacy, not by finance: Immunisation works its vaccines, the lab its
reagents, urology its consumables - receive, use, count, write off. The same rules and stock ledger as Roy Books'
Stock page (src/fin/dept_stock.py): once finance has put a store in the books, every movement made here posts its
journal automatically. Putting a store in the books stays with finance (Roy Books › Stock).

Mounted under /stock/stores (the /stock prefix is already proxied to the backend).
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, HTTPException

from src.fin import dept_stock
from src.fin.context import system_context
from src.fin.db import plain, q, q1, tx
from src.fin.errors import FinError
from src.middleware import verify_jwt

router = APIRouter(prefix="/stock/stores", tags=["Department stores"])

# who may move a store's stock (seeing it is open to every signed-in member of staff)
MOVERS = {"admin", "pharmacist", "pharmacy", "lab", "lab_tech", "laboratory", "nurse", "doctor", "ops", "finance",
          "management", "radiology", "quality_assurance", "store", "stores"}


def _can_move(user: Dict[str, Any]) -> None:
    roles = {str(r).lower() for r in (user.get("roles") or [])}
    if not roles & MOVERS:
        raise HTTPException(status_code=403, detail="Your role cannot change department stock")


def _run(fn, user: Dict[str, Any]):
    try:
        with tx() as conn:
            ctx = system_context(conn, actor=str(user.get("email") or user.get("sub") or "staff"))
            return plain(fn(conn, ctx))
    except FinError as e:
        raise HTTPException(status_code=e.status, detail=e.message)


def _dates(d: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(d)
    for k in ("expiry_date", "move_date"):
        if out.get(k):
            out[k] = dt.date.fromisoformat(str(out[k])[:10])
    return out


@router.get("/inventory/departments")
def stores(user=Depends(verify_jwt)):
    return _run(lambda c, x: {"departments": dept_stock.overview(c), "pharmacy": None}, user)


@router.get("/inventory/departments/{department}")
def store_items(department: str, include_empty: bool = False, user=Depends(verify_jwt)):
    return _run(lambda c, x: dept_stock.items(c, department.upper(), include_empty), user)


@router.get("/inventory/departments/{department}/usage")
def store_usage(department: str, user=Depends(verify_jwt)):
    return _run(lambda c, x: dept_stock.usage(c, department.upper()), user)


@router.post("/inventory/departments/{department}/items")
def store_add(department: str, payload: Dict[str, Any] = Body(...), user=Depends(verify_jwt)):
    _can_move(user)
    return _run(lambda c, x: dept_stock.add_item(c, x, {**_dates(payload), "department": department}), user)


@router.get("/inventory/department-stock/{stock_id}")
def store_item(stock_id: int, user=Depends(verify_jwt)):
    def fn(conn, ctx):
        r = q1(conn, """SELECT s.*, s.quantity * COALESCE(s.unit_cost,0) AS value, (s.expiry_date < current_date) AS expired
                        FROM royan_department_stock s WHERE s.id=%s""", (stock_id,))
        if not r:
            raise HTTPException(status_code=404, detail="Not found")
        r["batches"] = q(conn, """SELECT id, batch_number, expiry_date, quantity, unit_cost, quantity * COALESCE(unit_cost,0) AS value
                                  FROM royan_department_stock WHERE department=%s AND item_name=%s AND is_active
                                  ORDER BY expiry_date NULLS LAST""", (r["department"], r["item_name"]))
        return r
    return _run(fn, user)


@router.get("/inventory/department-stock/{stock_id}/moves")
def store_moves(stock_id: int, user=Depends(verify_jwt)):
    return _run(lambda c, x: dept_stock.moves(c, stock_id), user)


@router.post("/inventory/department-stock/{stock_id}/adjust")
def store_adjust(stock_id: int, payload: Dict[str, Any] = Body(...), user=Depends(verify_jwt)):
    _can_move(user)
    return _run(lambda c, x: dept_stock.adjust(c, x, stock_id, _dates(payload)), user)
