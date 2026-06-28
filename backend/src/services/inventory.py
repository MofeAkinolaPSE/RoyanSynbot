from __future__ import annotations

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
from typing import Any as DBClient
from ..db import db
from ..constants import TABLE_INVENTORY_EVENTS

TABLE_INVENTORY_ITEMS = "inventory_items"

logger = logging.getLogger("inventory")


def record_inventory_event(
    sku: str,
    change: float,
    event_type: str,
    reference: str | None,
    user_id: str,
    client: DBClient = db
) -> Dict[str, Any]:
    if change == 0:
        raise ValueError("Quantity change cannot be zero")

    payload = {
        "sku": sku,
        "quantity_change": change,
        "event_type": event_type,
        "reference": reference,
        "performed_by": user_id,
    }

    try:
        resp = client.table(TABLE_INVENTORY_EVENTS).insert(payload).execute()
        logger.info(f"Recorded {event_type} for {sku}: {change} (Ref: {reference})")
        return resp.data[0] if resp.data else {}
    except Exception as e:
        logger.error(f"Failed to record inventory event: {e}")
        raise e


def get_realtime_stock(sku: str, client: DBClient = db) -> Dict[str, Any]:
    """Current stock = baseline from inventory_items + delta from royan_inventory_events."""
    baseline_qty = 0.0
    sku_name = sku

    try:
        item_resp = client.table(TABLE_INVENTORY_ITEMS).select("id,name").eq("sku", sku).limit(1).execute()
        item = (item_resp.data or [{}])[0]
        sku_name = item.get("name") or sku
    except Exception as e:
        logger.warning(f"get_realtime_stock: inventory_items lookup failed ({e})")

    events: list = []
    try:
        ev_resp = (
            client.table(TABLE_INVENTORY_EVENTS)
            .select("quantity_change,event_type,created_at")
            .eq("sku", sku)
            .execute()
        )
        events = ev_resp.data or []
    except Exception as e:
        logger.warning(f"get_realtime_stock: events query failed ({e})")

    delta_qty = sum(float(e["quantity_change"]) for e in events)
    current_qty = baseline_qty + delta_qty

    return {
        "sku": sku,
        "name": sku_name,
        "baseline": {"quantity": baseline_qty, "source": "inventory_items", "as_of": None},
        "events": {"count": len(events), "net_change": delta_qty},
        "current_stock": current_qty,
        "status": "In Stock" if current_qty > 0 else "Out of Stock",
    }


def get_inventory_summary(limit: int = 50, client: DBClient = db) -> List[Dict[str, Any]]:
    """Summary of all inventory items with running event totals."""
    items: List[Dict[str, Any]] = []
    try:
        items_resp = (
            client.table(TABLE_INVENTORY_ITEMS)
            .select("id,sku,name,unit_cost,reorder_level")
            .eq("is_active", True)
            .limit(limit)
            .execute()
        )
        items = items_resp.data or []
    except Exception as e:
        logger.error(f"get_inventory_summary: inventory_items query failed ({e})")
        return []

    if not items:
        return []

    skus = [i.get("sku") for i in items if i.get("sku")]

    events_by_sku: Dict[str, float] = {}
    if skus:
        try:
            ev_resp = (
                client.table(TABLE_INVENTORY_EVENTS)
                .select("sku,quantity_change")
                .in_("sku", skus)
                .execute()
            )
            for ev in (ev_resp.data or []):
                s = ev.get("sku")
                if s:
                    events_by_sku[s] = events_by_sku.get(s, 0.0) + float(ev.get("quantity_change") or 0)
        except Exception as e:
            logger.warning(f"get_inventory_summary: events bulk fetch failed ({e})")

    results = []
    for item in items:
        sku = item.get("sku") or str(item.get("id"))
        current_qty = events_by_sku.get(sku, 0.0)
        results.append({
            "sku": sku,
            "name": item.get("name") or sku,
            "baseline": {"quantity": 0.0, "source": "inventory_items", "as_of": None},
            "events": {"count": 0, "net_change": current_qty},
            "current_stock": current_qty,
            "status": "In Stock" if current_qty > 0 else "Out of Stock",
            "unit_cost": float(item.get("unit_cost") or 0),
            "reorder_level": item.get("reorder_level"),
        })

    return results


def get_recent_inventory_movements(limit: int = 20, client: DBClient = db) -> List[Dict[str, Any]]:
    """Recent inventory movement events for dashboards."""
    try:
        resp = (
            client.table(TABLE_INVENTORY_EVENTS)
            .select("sku,quantity_change,event_type,reference,created_at")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return [
            {
                "sku": r.get("sku"),
                "change": float(r.get("quantity_change") or 0),
                "event_type": r.get("event_type") or "movement",
                "reference": r.get("reference"),
                "created_at": r.get("created_at"),
            }
            for r in (resp.data or [])
        ]
    except Exception as e:
        logger.error(f"get_recent_inventory_movements failed: {e}")
        return []


def get_expiring_inventory(thresholds: List[int] | None = None, client: DBClient = db) -> Dict[str, Any]:
    """Expiry tracking — not applicable to this deployment (no expiry_date source)."""
    return {"items": [], "summary": {"count": 0, "note": "expiry tracking not available in hospital deployment"}}


def scan_and_alert_expiring(thresholds: List[int] | None = None, client: DBClient = db) -> Dict[str, Any]:
    return get_expiring_inventory(thresholds=thresholds, client=client)


def schedule_expiry_monitor(interval_minutes: int = 360, thresholds: List[int] | None = None) -> None:
    pass
