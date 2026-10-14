"""Extract Royan's real radiology report section templates from Hope's
radiology_templates/radiology_template_texts -> royan_radiology_report_templates
+ royan_radiology_report_template_texts.

Confirmed real, clinically-authored data (not test/junk): 184 template
rows (one per exam-type x report section, e.g. FINDINGS/OPINIONS/
IMPRESSION), 191 real selectable phrase snippets with genuine radiology
findings language (e.g. Doppler-study vascular findings). 172 of 184
belong to location_id=1 (the main hospital); the remaining 12 reference
location_ids (6, 9, 12, 19) that have no matching row in Hope's own
`locations` table -- kept raw as location_ref rather than resolved, since
there's nothing to resolve them against in this dump.
"""
from __future__ import annotations

from typing import Any, Dict, List, Set

from transformers._helpers import EXTERNAL_SOURCE, safe_str


def transform_templates(raw_templates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for row in raw_templates:
        if safe_str(row.get("is_deleted")) == "1":
            continue
        section = safe_str(row.get("template_name"))
        ext_id = safe_str(row.get("id"))
        if not section or not ext_id:
            continue

        out.append({
            "exam_type_ref":     safe_str(row.get("radiology_id")),
            "section":           section,
            "location_ref":      safe_str(row.get("location_id")),
            "is_active":         True,
            "external_source":   EXTERNAL_SOURCE,
            "external_id":       ext_id,
        })
    return out


def valid_template_ids(templates_payloads: List[Dict[str, Any]]) -> Set[str]:
    return {p["external_id"] for p in templates_payloads}


def transform_template_texts(
    raw_texts: List[Dict[str, Any]], valid_template_ext_ids: Set[str],
) -> List[Dict[str, Any]]:
    out = []
    sort_counters: Dict[str, int] = {}
    for row in raw_texts:
        if safe_str(row.get("is_deleted")) == "1":
            continue
        template_id = safe_str(row.get("template_id"))
        if not template_id or template_id not in valid_template_ext_ids:
            continue
        text = safe_str(row.get("template_text"))
        ext_id = safe_str(row.get("id"))
        if not text or not ext_id:
            continue

        sort_counters[template_id] = sort_counters.get(template_id, 0) + 1
        out.append({
            "_hope_template_ext_id": template_id,
            "text":                  text,
            "sort_order":            sort_counters[template_id],
            "external_source":       EXTERNAL_SOURCE,
            "external_id":           ext_id,
        })
    return out
