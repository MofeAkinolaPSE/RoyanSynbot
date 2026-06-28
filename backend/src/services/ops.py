from __future__ import annotations

from typing import Dict, Any, List
from typing import Any as DBClient
from ..db import db
from ..cache import ttl_cache
from .forecasting import rolling_average
import datetime as _datetime_mod

import logging
logger = logging.getLogger("ops")

# These snapshot tables are legacy Sage/pharma imports that do not exist in the
# hospital deployment. All queries against them are wrapped in try/except so they
# return empty results instead of raising 500 errors.
_SAGE_TABLES_AVAILABLE = False


def _dt_to_str(val: object) -> str:
    """Coerce psycopg2 datetime/date to ISO string; passthrough for str/None."""
    if val is None:
        return ""
    if hasattr(val, 'isoformat'):
        return val.isoformat()
    return str(val)


MAX_ANALYTICS_ROWS = 3000


@ttl_cache(ttl_seconds=180, ignore_kwargs=("client",), tags=("logistics", "ops_kpis", "executive"))
def kpis(client: DBClient = db) -> Dict[str, Any]:
    """Operations KPIs: avg order fulfillment days, stock turnover.

    Returns zero-value defaults — Sage purchase order and invoice line tables
    do not exist in the hospital deployment.
    """
    if not _SAGE_TABLES_AVAILABLE:
        return {
            "fulfillment_days_avg": 0.0,
            "downtime_minutes_total": None,
            "stock_turnover": 0.0,
            "explain": {
                "fulfillment_days_avg": "unavailable — no purchase order source in hospital deployment",
                "downtime_minutes_total": "unavailable",
                "stock_turnover": "unavailable — no invoice line source in hospital deployment",
                "sources": [],
            },
        }

    import datetime

    def parse_date(s: str | None) -> datetime.date | None:
        if not s:
            return None
        try:
            return datetime.date.fromisoformat(str(s)[:10])
        except Exception:
            return None

    # Fulfillment time — derived from purchase orders (order_date → expected_delivery_date)
    fulfillment_days_avg = 0.0
    try:
        po_batch: str | None = None
        try:
            _b = client.table("sage_purchase_orders_snapshot").select("batch_id").order("imported_at", desc=True).limit(1).execute()
            po_batch = (_b.data or [{}])[0].get("batch_id")
        except Exception:
            pass

        po_q = client.table("sage_purchase_orders_snapshot").select("order_date,expected_delivery_date,status")
        if po_batch:
            po_q = po_q.eq("batch_id", po_batch)
        po_data = (po_q.order("order_date", desc=True).limit(MAX_ANALYTICS_ROWS).execute().data or [])

        deltas: List[float] = []
        for r in po_data:
            status = str(r.get("status") or "").lower()
            if status not in ("closed", "received", "complete", "completed"):
                continue
            od = parse_date(r.get("order_date"))
            ed = parse_date(r.get("expected_delivery_date"))
            if od and ed and ed >= od:
                deltas.append((ed - od).days)
        fulfillment_days_avg = round(sum(deltas) / len(deltas), 2) if deltas else 0.0
    except Exception as e:
        logger.debug(f"ops.kpis: purchase_orders_snapshot unavailable ({e}); using 0")

    # Approximate avg inventory qty from latest inventory snapshot
    avg_inventory_qty = 0.0
    try:
        sage_batch_id: str | None = None
        try:
            _ib = client.table("sage_inventory_snapshot").select("batch_id").order("imported_at", desc=True).limit(1).execute()
            sage_batch_id = (_ib.data or [{}])[0].get("batch_id")
        except Exception:
            pass
        inv_q = client.table("sage_inventory_snapshot").select("quantity")
        if sage_batch_id:
            inv_q = inv_q.eq("batch_id", sage_batch_id)
        inv = inv_q.order("imported_at", desc=True).limit(MAX_ANALYTICS_ROWS).execute()
        inv_vals = [float(r.get("quantity") or 0) for r in (inv.data or [])]
        avg_inventory_qty = (sum(inv_vals) / len(inv_vals)) if inv_vals else 0.0
    except Exception as e:
        logger.debug(f"ops.kpis: inventory_snapshot unavailable ({e}); using 0")

    # Stock turnover: total_sold_qty ÷ avg_inventory_qty
    sold_qty = 0.0
    try:
        il_batch: str | None = None
        try:
            _ilb = client.table("sage_invoice_lines_snapshot").select("batch_id").order("imported_at", desc=True).limit(1).execute()
            il_batch = (_ilb.data or [{}])[0].get("batch_id")
        except Exception:
            pass
        il_q = client.table("sage_invoice_lines_snapshot").select("quantity")
        if il_batch:
            il_q = il_q.eq("batch_id", il_batch)
        il_rows = il_q.limit(MAX_ANALYTICS_ROWS).execute().data or []
        sold_qty = sum(float(r.get("quantity") or 0) for r in il_rows)
    except Exception as e:
        logger.debug(f"ops.kpis: invoice_lines_snapshot unavailable ({e}); using 0")

    stock_turnover = round(sold_qty / avg_inventory_qty, 4) if avg_inventory_qty > 0 else 0.0

    return {
        "fulfillment_days_avg": fulfillment_days_avg,
        "downtime_minutes_total": None,
        "stock_turnover": stock_turnover,
        "explain": {
            "fulfillment_days_avg": "mean(expected_delivery_date - order_date) for closed POs",
            "downtime_minutes_total": "unavailable — no downtime data source",
            "stock_turnover": "sum(invoice_line_quantity) / avg_inventory_qty",
            "sources": ["sage_purchase_orders_snapshot", "sage_invoice_lines_snapshot", "sage_inventory_snapshot"],
        },
    }


def stock_turnover_series(client: DBClient = db, periods: int = 6) -> Dict[str, Any]:
    """Monthly stock turnover based on invoice lines and avg inventory quantities.
    Returns empty series when the legacy snapshot tables are absent."""
    if not _SAGE_TABLES_AVAILABLE:
        return {"series": []}

    orders: list = []
    try:
        il_batch: str | None = None
        try:
            _b = client.table("sage_invoice_lines_snapshot").select("batch_id").order("imported_at", desc=True).limit(1).execute()
            il_batch = (_b.data or [{}])[0].get("batch_id")
        except Exception:
            pass
        il_q = client.table("sage_invoice_lines_snapshot").select("imported_at,invoice_id,quantity")
        if il_batch:
            il_q = il_q.eq("batch_id", il_batch)
        orders = (il_q.order("imported_at", desc=True).limit(MAX_ANALYTICS_ROWS).execute().data or [])
    except Exception as e:
        logger.debug(f"ops.stock_turnover_series: invoice_lines_snapshot unavailable ({e})")
        return {"series": []}

    if not orders:
        return {"series": []}

    inv_date_map: Dict[str, str] = {}

    buckets: Dict[str, float] = {}
    for r in orders:
        invoice_id = r.get("invoice_id") or ""
        month = inv_date_map.get(invoice_id) or _dt_to_str(r.get("imported_at"))[:7]
        if not month:
            continue
        buckets[month] = buckets.get(month, 0.0) + float(r.get("quantity") or 0)
    months = sorted(buckets.keys())[-periods:]

    avg_inventory_qty = 1.0
    try:
        sage_batch_id: str | None = None
        try:
            _ib = client.table("sage_inventory_snapshot").select("batch_id").order("imported_at", desc=True).limit(1).execute()
            sage_batch_id = (_ib.data or [{}])[0].get("batch_id")
        except Exception:
            pass
        inv_q = client.table("sage_inventory_snapshot").select("quantity")
        if sage_batch_id:
            inv_q = inv_q.eq("batch_id", sage_batch_id)
        inv = inv_q.order("imported_at", desc=True).limit(MAX_ANALYTICS_ROWS).execute()
        inv_vals = [float(r.get("quantity") or 0) for r in (inv.data or [])]
        avg_inventory_qty = (sum(inv_vals) / len(inv_vals)) if inv_vals else 1.0
    except Exception as e:
        logger.debug(f"ops.stock_turnover_series: inventory_snapshot unavailable ({e})")

    series = [{"period": m, "turnover": round(buckets[m] / avg_inventory_qty, 4)} for m in months]
    return {"series": series}


def forecast_stock_turnover(client: DBClient = db, window: int = 3, horizon: int = 3) -> Dict[str, Any]:
    s = stock_turnover_series(client=client, periods=12)["series"]
    vals = [p["turnover"] for p in s]
    if not vals:
        return {"series": [], "rolling": [], "forecast": []}
    roll = rolling_average(vals, window=window)
    last = roll[-1]
    forecast = [last for _ in range(horizon)]
    return {"series": s, "rolling": roll, "forecast": forecast}
