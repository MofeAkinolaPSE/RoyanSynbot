"""Extract Hope's per-batch pharmacy pricing (`pharmacy_item_rates`, 2,006
rows, staged by extract_pharmacy_pricing.py) -> royan_pharmacy_item_rates.

Each row carries a full price set for one drug batch -- mrp,
purchase_price, cost_price, sale_price -- plus batch_number, expiry_date
and stock. item_id resolves 855/855 (100%) against royan_drug_formulary.

is_deleted is NOT used to filter here: these are historical price records,
and a superseded rate is still real pricing history worth keeping. It is
carried through as is_active instead.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from transformers._helpers import EXTERNAL_SOURCE, safe_date, safe_str


def _num(value: Any) -> Optional[float]:
    try:
        s = str(value).strip().replace(",", "")
        return round(float(s), 2) if s and s.lower() != "none" else None
    except (ValueError, TypeError):
        return None


def transform(raw_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for row in raw_rows:
        ext_id = safe_str(row.get("id"))
        item_id = safe_str(row.get("item_id"))
        if not ext_id or not item_id:
            continue

        out.append({
            "_hope_item_id":   item_id,
            "item_ref":        item_id,
            "batch_number":    safe_str(row.get("batch_number")),
            "expiry_date":     safe_date(row.get("expiry_date")),
            "mrp":             _num(row.get("mrp")),
            "purchase_price":  _num(row.get("purchase_price")),
            "cost_price":      _num(row.get("cost_price")),
            "sale_price":      _num(row.get("sale_price")),
            "stock":           _num(row.get("stock")),
            "loose_stock":     _num(row.get("loose_stock")),
            "vat_class_name":  safe_str(row.get("vat_class_name")),
            "is_active":       safe_str(row.get("is_deleted")) != "1",
            "external_source": EXTERNAL_SOURCE,
            "external_id":     ext_id,
        })
    return out
