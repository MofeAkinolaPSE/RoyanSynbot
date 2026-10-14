"""Extract Royan's real Review-of-Systems / Physical-Exam finding picker
from Hope's template_categories + templates + template_sub_categories ->
royan_exam_templates + royan_exam_template_findings.

Confirmed real, well-populated reference data (not test/junk): 3 real
categories (Review Of System, Physical Examination, HPI), 151 real
organ-system rows (Eyes, Constitutional Symptoms, Ears/nose/mouth/throat,
...), 45,665 real selectable finding phrases per organ system (Negative,
Fever, Negative except HPI, ...). template_type_contents (per-patient
applied selections, stored as raw PHP serialize() blobs) is deliberately
excluded -- historical data, not reference/catalog data, out of scope here.
"""
from __future__ import annotations

from typing import Any, Dict, List, Set

from transformers._helpers import EXTERNAL_SOURCE, safe_str


def transform_exam_templates(
    raw_templates: List[Dict[str, Any]],
    raw_categories: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    category_name_by_id = {}
    for c in raw_categories:
        cid = safe_str(c.get("id"))
        name = safe_str(c.get("name"))
        if cid and name:
            category_name_by_id[cid] = name

    out = []
    for row in raw_templates:
        if safe_str(row.get("is_deleted")) == "1":
            continue
        organ_system = safe_str(row.get("category_name"))
        ext_id = safe_str(row.get("id"))
        if not organ_system or not ext_id:
            continue
        category = category_name_by_id.get(safe_str(row.get("template_category_id")), "General")

        out.append({
            "category":          category,
            "organ_system":      organ_system,
            "is_female_only":    safe_str(row.get("is_female_template")) == "1",
            "sort_order":        int(float(row.get("sort_order") or 0)),
            "is_active":         True,
            "external_source":   EXTERNAL_SOURCE,
            "external_id":       ext_id,
        })
    return out


def valid_template_ids(templates_payloads: List[Dict[str, Any]]) -> Set[str]:
    return {p["external_id"] for p in templates_payloads}


def transform_exam_template_findings(
    raw_sub_categories: List[Dict[str, Any]],
    valid_template_ext_ids: Set[str],
) -> List[Dict[str, Any]]:
    out = []
    sort_counters: Dict[str, int] = {}
    for row in raw_sub_categories:
        if safe_str(row.get("is_deleted")) == "1":
            continue
        template_id = safe_str(row.get("template_id"))
        if not template_id or template_id not in valid_template_ext_ids:
            continue
        finding = safe_str(row.get("sub_category"))
        ext_id = safe_str(row.get("id"))
        if not finding or not ext_id:
            continue

        sort_counters[template_id] = sort_counters.get(template_id, 0) + 1
        out.append({
            "_hope_template_ext_id": template_id,
            "finding":               finding,
            "is_default":            safe_str(row.get("is_default")) == "1",
            "sort_order":            sort_counters[template_id],
            "external_source":       EXTERNAL_SOURCE,
            "external_id":           ext_id,
        })
    return out
