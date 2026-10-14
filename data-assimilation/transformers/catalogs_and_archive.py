"""Final Phase A3 transformers: radiology catalog, surgery catalog, and the
generic Hope reference archive.

The archive exists because the user's directive was to extract everything
"so we don't have to come back to it", explicitly including low-value data.
Rather than invent ~60 bespoke schemas for small reference tables (and for
large but consumer-less ones like ndc_masters / accounts / voucher_logs),
every remaining staged Hope row is preserved verbatim as jsonb, queryable
and promotable to a real table later if a consumer appears.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from transformers._helpers import EXTERNAL_SOURCE, safe_str


def _num(value: Any) -> Optional[float]:
    try:
        s = str(value).strip().replace(",", "")
        return round(float(s), 2) if s and s.lower() != "none" else None
    except (ValueError, TypeError):
        return None


def transform_radiology_catalog(raw_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Hope `radiologies` -> royan_radiology_catalog. Mirrors the lab catalog;
    gives radiology orders a real catalog behind their free-text test_name.
    """
    out = []
    for row in raw_rows:
        if safe_str(row.get("is_deleted")) == "1":
            continue
        name = safe_str(row.get("name"))
        ext_id = safe_str(row.get("id"))
        if not name or not ext_id:
            continue

        out.append({
            "name":              name,
            # Hope has no explicit modality column here -- test_group_id is
            # the closest thing, kept as a raw ref rather than guessed at.
            "test_group_ref":    safe_str(row.get("test_group_id")),
            "service_group_ref": safe_str(row.get("service_group_id")),
            "is_active":         safe_str(row.get("is_active")) != "0",
            "external_source":   EXTERNAL_SOURCE,
            "external_id":       ext_id,
        })
    return out


def transform_surgery_catalog(
    surgeries: List[Dict[str, Any]],
    categories: List[Dict[str, Any]],
    sub_categories: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    cat_by_id = {safe_str(c.get("id")): safe_str(c.get("name")) for c in categories}
    sub_by_id = {safe_str(c.get("id")): safe_str(c.get("name")) for c in sub_categories}

    out = []
    for row in surgeries:
        if safe_str(row.get("is_deleted")) == "1":
            continue
        name = safe_str(row.get("name"))
        ext_id = safe_str(row.get("id"))
        if not name or not ext_id:
            continue

        out.append({
            "name":              name,
            "description":       safe_str(row.get("description")),
            "category_name":     cat_by_id.get(safe_str(row.get("surgery_category_id"))),
            "sub_category_name": sub_by_id.get(safe_str(row.get("surgery_subcategory_id"))),
            "surgeon_fee":       _num(row.get("surgeon_fees")),
            "is_active":         True,
            "external_source":   EXTERNAL_SOURCE,
            "external_id":       ext_id,
        })
    return out


def transform_reference_archive(
    source_table: str, raw_rows: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """One archive row per source row, full payload as jsonb.

    Some Hope tables lost their primary key in the dump export (every row
    carries id = 0 -- review_patient_details was the known case). Where the
    row id is absent or non-unique, the row's ordinal position is used so
    external_id stays unique and deterministic across re-runs.
    """
    out = []
    seen: Dict[str, int] = {}
    for idx, row in enumerate(raw_rows, 1):
        row_id = safe_str(row.get("id"))
        key = row_id if row_id and row_id != "0" else f"row{idx}"
        n = seen.get(key, 0)
        seen[key] = n + 1
        if n:
            key = f"{key}#{n}"

        out.append({
            "source_table":    source_table,
            "source_row_id":   row_id,
            "payload":         row,
            "external_source": EXTERNAL_SOURCE,
            "external_id":     f"{source_table}:{key}",
        })
    return out
