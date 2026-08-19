"""Extract real purchase batches (real batch numbers + expiry dates) from
Hope's `inventory_purchase_item_details` (staged as hope_inv_purchase_item_details),
joined with `inventory_purchase_details` (hope_inv_purchase_details) for the
purchase date -> additional royan_inventory_batches rows, alongside (not
replacing) the synthetic "HOPE-INITIAL" current-stock batch created by
pharmacy_catalog.py.

item_id here is a different identifier space than pharmacy_items.id (the
source used for the formulary load) -- confirmed by direct inspection: only
~10-15 of the 37 rows' item_id values overlap with what's in the loaded
formulary. Rows that don't resolve are skipped, not guessed.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from transformers._helpers import EXTERNAL_SOURCE, safe_date, safe_str


def _to_number(value: Any) -> Optional[float]:
    try:
        s = str(value).strip().replace(",", "")
        if not s or s.lower() == "none":
            return None
        return float(s)
    except (ValueError, TypeError):
        return None


def transform(
    purchase_items: List[Dict[str, Any]],
    purchases: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    purchase_by_id = {safe_str(p.get("id")): p for p in purchases}

    out = []
    for row in purchase_items:
        raw = {k.lower(): v for k, v in row.items()}
        item_id = safe_str(raw.get("item_id"))
        batch_no = safe_str(raw.get("batch_no"))
        ext_id = safe_str(raw.get("id"))
        qty = _to_number(raw.get("qty"))
        if not item_id or not batch_no or not ext_id or not qty or qty <= 0:
            continue

        purchase = purchase_by_id.get(safe_str(raw.get("inventory_purchase_detail_id"))) or {}
        received_at = safe_date(purchase.get("vr_date")) or safe_date(purchase.get("create_time"))

        out.append({
            "_hope_item_id":     item_id,
            "batch_number":      batch_no,
            "quantity_received": qty,
            # 0, not qty: these are 2014-2018 purchase records, over a
            # decade old relative to the dump date -- treating the full
            # originally-received quantity as still "on hand" today would
            # claim long-since-consumed stock is currently available and
            # inflate total_qty_on_hand/stock_value. The current-stock
            # figure is already correctly captured by the "HOPE-INITIAL"
            # batch from pharmacy_catalog.py; this row exists purely to
            # carry the real batch_number/expiry_date into history. Setting
            # this to 0 also correctly excludes it from every "live stock"
            # query (WHERE quantity_on_hand > 0), so it shows up in a
            # drug's batch history/drill-down without touching current
            # metrics.
            "quantity_on_hand":  0,
            "unit_cost":         round(_to_number(raw.get("price")) or 0, 2),
            "received_at":       received_at,
            "expiry_date":       safe_date(raw.get("expiry_date")),
            "external_source":   EXTERNAL_SOURCE,
            # Prefixed, not the bare purchase_item_detail id: royan_inventory_batches'
            # (external_source, external_id) key is shared with pharmacy_catalog.py's
            # "HOPE-INITIAL" batches, which use the bare *drug* external_id (also a
            # small sequential number from a different Hope id space) -- an
            # unprefixed id here previously collided with and silently overwrote
            # a drug's real current-stock batch. Confirmed and fixed 2026-08-18.
            "external_id":       f"purchase:{ext_id}",
        })
    return out
