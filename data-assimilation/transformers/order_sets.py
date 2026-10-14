"""Extract Royan's real "treatment templates" from Hope's Order Set
subsystem (orderset_masters + order_subcategories + order_categories) ->
royan_order_sets + royan_order_set_items.

Only 4 of Hope's 44 orderset_masters rows are trustworthy -- confirmed by
inspecting real line-item content, not just row presence. Every master
marked is_deleted='1' (including clinically-named ones like "Bacterial
pneumonia", "UTI", "Knee Surgery") turned out to contain test/demo garbage
(e.g. "Bacterial pneumonia"'s medication list includes "cervical caps" and
"chloroform liquid", alphabetically clustered around "C" -- someone
scrolling a drug autocomplete for testing, not real clinical authorship).
The 4 masters actually marked is_deleted='0' are clean and clinically
coherent (real dosage/route/frequency, sensible drug choices, real allergy
flags). is_deleted is therefore the primary inclusion filter here -- the
reverse of its usual "just skip soft-deleted rows" role elsewhere in this
pipeline -- confirmed correct by reading actual content for every
candidate master, not just checking row counts. Loading the deleted
masters' content would put fabricated-looking, potentially dangerous drug
choices in front of a doctor as a selectable template.

Hope's dosage/strength/dose/route/frequency columns on order_subcategories
carry stale/garbage placeholder values on non-medication rows (e.g. a
"Critical" condition-status item showing dosage=500, route=23) -- these
fields are only trusted when the item's category is genuinely Medication.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

from transformers._helpers import EXTERNAL_SOURCE, safe_str

# order_categories.order_description (lowercased) -> our item_type enum
_ITEM_TYPE_BY_CATEGORY_NAME = {
    "medication":            "medication",
    "lab":                   "lab",
    "radiolgy":              "radiology",   # Hope's own typo, kept as the real key
    "diagnostic test":       "radiology",
    "diet":                  "diet",
    "activity":              "activity",
    "patient care":          "patient_care",
    "vital signs":           "vital_signs",
    "iv solution":           "iv_solution",
    "conditions":            "other",
    "commmunication oder":   "communication",   # Hope's own typo
    "intake and output":     "intake_output",
    "procedure/test":        "procedure",
    "allergy":               "allergy",
}


def _to_number(value: Any) -> Optional[float]:
    try:
        s = str(value).strip().replace(",", "")
        if not s or s.lower() == "none":
            return None
        return float(s)
    except (ValueError, TypeError):
        return None


def transform_order_sets(
    raw_masters: List[Dict[str, Any]],
    raw_items: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    # A master with no real (non-deleted) line items is just an empty shell
    # even if the master row itself isn't marked deleted (e.g. Hope's "test
    # order", is_deleted='0' but zero real content) -- not worth presenting
    # as a selectable template.
    masters_with_items = {
        safe_str(r.get("orderset_master_id"))
        for r in raw_items
        if safe_str(r.get("orderset_master_id")) and safe_str(r.get("is_deleted")) != "1"
    }

    out = []
    for row in raw_masters:
        if safe_str(row.get("is_deleted")) != "0":
            continue
        name = safe_str(row.get("name"))
        ext_id = safe_str(row.get("id"))
        if not name or not ext_id or ext_id not in masters_with_items:
            continue
        out.append({
            "name":              name,
            "is_shared":         True,
            "is_active":         True,
            "external_source":   EXTERNAL_SOURCE,
            "external_id":       ext_id,
        })
    return out


def valid_master_ids(order_sets_payloads: List[Dict[str, Any]]) -> Set[str]:
    return {p["external_id"] for p in order_sets_payloads}


def transform_order_set_items(
    raw_items: List[Dict[str, Any]],
    order_categories: List[Dict[str, Any]],
    valid_master_ext_ids: Set[str],
) -> List[Dict[str, Any]]:
    category_type_by_id: Dict[str, str] = {}
    for c in order_categories:
        cid = safe_str(c.get("id"))
        cname = (safe_str(c.get("order_description")) or "").strip().lower()
        if cid:
            category_type_by_id[cid] = _ITEM_TYPE_BY_CATEGORY_NAME.get(cname, "other")

    out = []
    sort_counters: Dict[str, int] = {}
    for row in raw_items:
        master_id = safe_str(row.get("orderset_master_id"))
        if not master_id or master_id not in valid_master_ext_ids:
            continue
        if safe_str(row.get("is_deleted")) == "1":
            continue
        name = safe_str(row.get("name"))
        ext_id = safe_str(row.get("id"))
        if not name or not ext_id:
            continue

        category_id = safe_str(row.get("order_category_id"))
        item_type = category_type_by_id.get(category_id, "other")
        is_medication = item_type == "medication"

        sort_counters[master_id] = sort_counters.get(master_id, 0) + 1

        out.append({
            "_hope_master_ext_id": master_id,
            "item_type":          item_type,
            "name":               name,
            # dosage-family fields are only meaningful (and only trustworthy --
            # see module docstring) for real medication rows
            "dosage":             safe_str(row.get("dosage")) if is_medication else None,
            "strength":           safe_str(row.get("strength")) if is_medication else None,
            "dose_form":          safe_str(row.get("dose_form")) if is_medication else None,
            "route":              safe_str(row.get("route")) if is_medication else None,
            "frequency":          safe_str(row.get("frequency")) if is_medication else None,
            "duration":           safe_str(row.get("day")) if is_medication else None,
            "quantity":           _to_number(row.get("qty")) if is_medication else None,
            "prn":                safe_str(row.get("prn")) == "1",
            "dispense":           safe_str(row.get("dispense")) == "1",
            "instruction":        safe_str(row.get("order_sentence")),
            "sort_order":         sort_counters[master_id],
            "external_source":    EXTERNAL_SOURCE,
            "external_id":        ext_id,
        })
    return out
