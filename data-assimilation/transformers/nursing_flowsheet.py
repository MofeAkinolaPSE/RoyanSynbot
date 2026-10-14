"""Decode Hope's ICU nursing observation flowsheet
(`review_patient_details`, 48,815 rows) -> royan_nursing_flowsheet.

Decode chain (all three lookups staged by extract_final_sweep.py):
    review_patient_details.review_sub_categories_options_id
      -> review_sub_categories_options   (317)  name + unit
         .review_sub_categories_id
      -> review_sub_categories           (60)   name
         .review_category_id
      -> review_categories               (5)    name

Hope's own column comment calls `values` "serialized data for every hour
for the day". It is NOT serialized -- verified directly against the real
rows, each holds a plain scalar ("36.7", "170/90", "lying", "20"). Kept as
text, with value_numeric populated only where the value is genuinely
numeric ("170/90" is a blood pressure and stays text-only).

KEYING: all 48,815 rows carry id = 0 -- the table has no AUTO_INCREMENT
and the dump export preserved no primary key. external_id is built as a
deterministic composite instead:
    flowsheet:{patient}:{option}:{date}:{hourslot}:{actualtime}[:{n}]
The trailing occurrence counter only appears for the 217 rows where the
5-part composite still repeats, so re-running against the same staged data
produces identical ids and the load stays idempotent.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from transformers._helpers import EXTERNAL_SOURCE, safe_date, safe_str


def _numeric(text: Optional[str]) -> Optional[float]:
    if not text:
        return None
    try:
        return round(float(str(text).strip()), 4)
    except (ValueError, TypeError):
        return None


def _build_lookups(
    categories: List[Dict[str, Any]],
    sub_categories: List[Dict[str, Any]],
    options: List[Dict[str, Any]],
):
    cat_by_id = {safe_str(c.get("id")): safe_str(c.get("name")) for c in categories}

    sub_by_id: Dict[str, Dict[str, Optional[str]]] = {}
    for sc in sub_categories:
        sid = safe_str(sc.get("id"))
        if not sid:
            continue
        sub_by_id[sid] = {
            "name": safe_str(sc.get("name")),
            "category": cat_by_id.get(safe_str(sc.get("review_category_id"))),
        }

    opt_by_id: Dict[str, Dict[str, Optional[str]]] = {}
    for o in options:
        oid = safe_str(o.get("id"))
        if not oid:
            continue
        sub = sub_by_id.get(safe_str(o.get("review_sub_categories_id")), {})
        opt_by_id[oid] = {
            "name": safe_str(o.get("name")),
            "unit": safe_str(o.get("unit")),
            "sub_category": sub.get("name"),
            "category": sub.get("category"),
        }

    return sub_by_id, opt_by_id


def transform(
    raw_rows: List[Dict[str, Any]],
    categories: List[Dict[str, Any]],
    sub_categories: List[Dict[str, Any]],
    options: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    sub_by_id, opt_by_id = _build_lookups(categories, sub_categories, options)

    seen_keys: Dict[str, int] = {}
    out = []
    for row in raw_rows:
        if safe_str(row.get("is_deleted")) == "1":
            continue

        hope_pid = safe_str(row.get("patient_id"))
        value_text = safe_str(row.get("values"))
        if not hope_pid or not value_text:
            continue

        opt_id = safe_str(row.get("review_sub_categories_options_id"))
        opt = opt_by_id.get(opt_id or "", {})
        observation_name = opt.get("name")
        if not observation_name:
            # Unresolvable option id -- skip rather than store a nameless
            # clinical observation nobody can interpret.
            continue

        sub = sub_by_id.get(safe_str(row.get("review_sub_categories_id")), {})
        observed_date = safe_date(row.get("date"))
        hour_slot = safe_str(row.get("hourslot"))
        actual_time = safe_str(row.get("actualtime"))

        base = f"flowsheet:{hope_pid}:{opt_id}:{observed_date}:{hour_slot}:{actual_time}"
        n = seen_keys.get(base, 0)
        seen_keys[base] = n + 1
        ext_id = base if n == 0 else f"{base}:{n}"

        out.append({
            "_hope_patient_id":  hope_pid,
            "category_name":     opt.get("category") or sub.get("category"),
            "sub_category_name": opt.get("sub_category") or sub.get("name"),
            "observation_name":  observation_name,
            "unit":              opt.get("unit"),
            "value_text":        value_text,
            "value_numeric":     _numeric(value_text),
            "observed_date":     observed_date,
            "hour_slot":         hour_slot,
            "actual_time":       actual_time,
            "is_edited":         safe_str(row.get("is_edited")) == "1",
            "external_source":   EXTERNAL_SOURCE,
            "external_id":       ext_id,
        })
    return out
