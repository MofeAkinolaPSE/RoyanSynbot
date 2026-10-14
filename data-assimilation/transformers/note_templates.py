"""Extract Royan's real per-SOAP-section note templates from Hope's
note_templates/note_template_texts (shared dot-phrase library) and
doctor_templates/doctor_template_texts (personal, doctor-authored
full-paragraph templates) -> royan_note_templates + royan_note_template_texts.

Confirmed real, well-populated data (not test/junk like the Order Set
tables elsewhere in this project): note_template_texts.context_type cleanly
covers subjective/objective/assessment/plan (98.7% of 8,094 rows) plus a
few bonus categories matching other meeting asks (Chief Complaint, Review
of Systems); doctor_templates has a real category taxonomy (diagnosis,
examine, care_plan, histo_pathology, etc.), not placeholder/test names.

owner_staff_id distinguishes system (note_templates, null owner) from
personal (doctor_templates, owner resolved in the loader via Hope's
created_by numeric id against already-loaded royan_staff external ids)
templates.

Master external_id is prefixed per source table (note_template:/
doctor_template:) since both id sequences independently start at 1 and
share royan_note_templates' (external_source, external_id) key -- same
collision class already caught and fixed in pharmacy_purchase_batches.py.
"""
from __future__ import annotations

from typing import Any, Dict, List, Set

from transformers._helpers import EXTERNAL_SOURCE, safe_str

# Hope's own context_type spellings/casing, normalized to the CHECK-constraint values
_CONTEXT_TYPE_MAP = {
    "subjective": "subjective",
    "objective": "objective",
    "assessment": "assessment",
    "plan": "plan",
    "chiefcompalint": "chief_complaint",   # Hope's own typo, kept as the real key
    "review of system": "review_of_systems",
}


def transform_note_templates(raw_masters: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for row in raw_masters:
        if safe_str(row.get("is_deleted")) == "1":
            continue
        name = safe_str(row.get("template_name"))
        ext_id = safe_str(row.get("id"))
        if not name or not ext_id:
            continue
        out.append({
            "name":              name,
            "scope":             "system",
            "category":          safe_str(row.get("template_type")),
            "_hope_owner_id":    None,
            "is_shared":         True,
            "is_active":         True,
            "external_source":   EXTERNAL_SOURCE,
            "external_id":       f"note_template:{ext_id}",
        })
    return out


def transform_doctor_templates(raw_masters: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for row in raw_masters:
        if safe_str(row.get("is_deleted")) == "1":
            continue
        name = safe_str(row.get("template_name"))
        ext_id = safe_str(row.get("id"))
        if not name or not ext_id:
            continue
        out.append({
            "name":              name,
            "scope":             "personal",
            "category":          safe_str(row.get("template_type")),
            "_hope_owner_id":    safe_str(row.get("created_by")),
            # Meeting: a doctor's own template should be selectable by other
            # doctors too, not personal-only.
            "is_shared":         True,
            "is_active":         True,
            "external_source":   EXTERNAL_SOURCE,
            "external_id":       f"doctor_template:{ext_id}",
        })
    return out


def _valid_ext_ids(masters: List[Dict[str, Any]]) -> Set[str]:
    return {m["external_id"] for m in masters}


def transform_note_template_texts(
    raw_texts: List[Dict[str, Any]], valid_master_ext_ids: Set[str],
) -> List[Dict[str, Any]]:
    out = []
    sort_counters: Dict[str, int] = {}
    for row in raw_texts:
        if safe_str(row.get("is_deleted")) == "1":
            continue
        master_id = safe_str(row.get("template_id"))
        master_ext_id = f"note_template:{master_id}" if master_id else None
        if not master_ext_id or master_ext_id not in valid_master_ext_ids:
            continue
        text = safe_str(row.get("template_text"))
        ext_id = safe_str(row.get("id"))
        if not text or not ext_id:
            continue

        raw_ctx = (safe_str(row.get("context_type")) or "").strip().lower()
        context_type = _CONTEXT_TYPE_MAP.get(raw_ctx, "general")

        sort_counters[master_id] = sort_counters.get(master_id, 0) + 1
        out.append({
            "_hope_master_ext_id": master_ext_id,
            "context_type":       context_type,
            "text":               text,
            "sort_order":         sort_counters[master_id],
            "external_source":    EXTERNAL_SOURCE,
            "external_id":        f"note_template_text:{ext_id}",
        })
    return out


def transform_doctor_template_texts(
    raw_texts: List[Dict[str, Any]], valid_master_ext_ids: Set[str],
) -> List[Dict[str, Any]]:
    out = []
    sort_counters: Dict[str, int] = {}
    for row in raw_texts:
        if safe_str(row.get("is_deleted")) == "1":
            continue
        master_id = safe_str(row.get("template_id"))
        master_ext_id = f"doctor_template:{master_id}" if master_id else None
        if not master_ext_id or master_ext_id not in valid_master_ext_ids:
            continue
        text = safe_str(row.get("template_text"))
        ext_id = safe_str(row.get("id"))
        if not text or not ext_id:
            continue

        sort_counters[master_id] = sort_counters.get(master_id, 0) + 1
        out.append({
            "_hope_master_ext_id": master_ext_id,
            # doctor_template_texts has no context_type -- these are full
            # narrative paragraphs (case summary/HPI), not section-specific
            # dot-phrases, so "general" is the honest classification.
            "context_type":       "general",
            "text":               text,
            "sort_order":         sort_counters[master_id],
            "external_source":    EXTERNAL_SOURCE,
            "external_id":        f"doctor_template_text:{ext_id}",
        })
    return out
