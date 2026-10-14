"""Extract Royan's real service price catalog from Hope's tariff_lists
(service names) + tariff_amounts (pricing) -> royan_tariff_catalog.

tariff_amounts carries one row per (tariff_list_id, tariff_standard_id) --
i.e. a per-payer pricing grid, using the same tariff_standards table
already loaded into royan_hmos (see transformers/hmo.py). Modeling the full
payer-specific grid is out of scope here; this collapses to one
representative charge_amount per service (max observed non_nabh_charges
across all payers/schedules for that service), which is a reasonable
"list price" proxy. cost_price is carried through where Hope populated it
(only 870/56,732 tariff_amounts rows, ~1.5% -- real where present, kept
as supplementary signal rather than the primary one).
"""
from __future__ import annotations

from typing import Any, Dict, List

from transformers._helpers import EXTERNAL_SOURCE, safe_str


def _to_float(value: Any) -> float:
    try:
        return float(str(value).replace(",", "")) if value not in (None, "") else 0.0
    except (ValueError, TypeError):
        return 0.0


def transform(tariff_lists_raw: List[Dict[str, Any]], tariff_amounts_raw: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    charge_by_list: Dict[str, float] = {}
    cost_by_list: Dict[str, float] = {}
    for row in tariff_amounts_raw:
        if safe_str(row.get("is_deleted")) == "1":
            continue
        list_id = safe_str(row.get("tariff_list_id"))
        if not list_id:
            continue
        charge = _to_float(row.get("non_nabh_charges"))
        if charge > charge_by_list.get(list_id, 0.0):
            charge_by_list[list_id] = charge
        cost = _to_float(row.get("cost_price"))
        if cost > cost_by_list.get(list_id, 0.0):
            cost_by_list[list_id] = cost

    out = []
    for row in tariff_lists_raw:
        if safe_str(row.get("is_deleted")) == "1":
            continue
        name = safe_str(row.get("name"))
        ext_id = safe_str(row.get("id"))
        if not name or not ext_id:
            continue

        out.append({
            "name":             name,
            "service_group":    safe_str(row.get("service_group")),
            "service_type":     safe_str(row.get("service_type")),
            "charge_amount":    charge_by_list.get(ext_id) or None,
            "cost_price":       cost_by_list.get(ext_id) or None,
            "is_active":        True,
            "external_source":  EXTERNAL_SOURCE,
            "external_id":      ext_id,
        })
    return out
